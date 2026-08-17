"""Night Factory throughput pipeline — FAST_HTTP, lanes, concurrency (ZERO SEND)."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

import run_ari_night_factory as nf
from ari_pipeline.fast_http_screen import FastScreenResult, classify_lane, fast_outcome_to_lw
from ari_pipeline.night_factory import (
    load_factory_checkpoint,
    load_factory_state,
    load_ready_inventory,
    recalculate_ready_inventory,
    save_factory_checkpoint,
)
from ari_pipeline.night_factory_pipeline import NightFactoryPipeline, serial_lw_root_cause_report


class TestSerialLwRootCause(unittest.TestCase):
    def test_root_cause_documents_fix(self):
        report = serial_lw_root_cause_report()
        self.assertIn("sequential", report["orchestrator_loop"].lower())
        self.assertIn("NightFactoryPipeline", report["fix"])


class TestFastHttpScreen(unittest.TestCase):
    def test_known_contact_url_fast_lane(self):
        c = {
            "domain": "example.co.jp",
            "website_url": "https://example.co.jp/",
            "lw_entry_url": "https://example.co.jp/contact/",
        }
        self.assertEqual(classify_lane(c), "NIGHT_FAST_LANE")

    def test_unreachable_maps_to_lw_outcome(self):
        self.assertEqual(fast_outcome_to_lw("UNREACHABLE"), "UNREACHABLE_ERROR")

    def test_slow_path_review(self):
        self.assertEqual(fast_outcome_to_lw("SLOW_PATH"), "SLOW_PATH_REVIEW")


class TestPipelinePending(unittest.TestCase):
    def test_fast_http_results_exclude_pending(self):
        source = [{"domain": "a.com"}, {"domain": "b.com"}]
        cp = {"fast_http_results": {"a.com": {}}, "exclusions": {}}
        lw_st = {"candidates": []}
        self.assertEqual(nf.count_pipeline_pending(source, cp, lw_st), 1)


class TestLaneRouting(unittest.TestCase):
    @patch("ari_pipeline.night_factory_pipeline.fast_http_screen", new_callable=AsyncMock)
    def test_unreachable_fast_rejection_no_browser(self, mock_fast):
        async def _run():
            mock_fast.return_value = FastScreenResult(
                domain="dead.test",
                url="https://dead.test/",
                lane="NIGHT_FAST_LANE",
                outcome="UNREACHABLE",
                promote_browser=False,
                elapsed_sec=0.5,
                reason="dns_fail",
            )
            cp = {"exclusions": {}, "fast_http_results": {}}
            lw_state = {"candidates": [], "stats": {}}
            state = {"stats": {}}
            inv = {"ready_primary": [], "ready_remodel_reserve": []}
            pipeline = NightFactoryPipeline(
                source=[{"domain": "dead.test", "website_url": "https://dead.test/"}],
                pool_by_dom={},
                cp=cp,
                lw_run_id="test_lw",
                config={"fast_http_workers": 2, "lw_workers": 1},
                log=lambda _m: None,
                pf_batch_fn=AsyncMock(return_value=0),
                rf_batch_fn=AsyncMock(return_value=0),
                collect_ready_fn=lambda *_a, **_k: {"added_primary": 0, "added_remodel": 0},
                load_inv_fn=lambda: inv,
                save_cp_fn=lambda _c: None,
                save_state_fn=lambda _s: None,
                safety_check_fn=lambda **_: None,
                stop_check_fn=lambda *_a: False,
                max_source=1,
            )
            with patch("ari_pipeline.night_factory_pipeline.shutdown_browser_pool", new=AsyncMock()):
                stats = await pipeline.run(lw_state=lw_state, inv=inv, state=state, stop_at=550)
            return stats, cp

        stats, cp = asyncio.run(_run())
        self.assertEqual(stats.fast_http_processed, 1)
        self.assertEqual(stats.browser_promoted, 0)
        self.assertIn("dead.test", cp.get("exclusions", {}))


class TestBoundedConcurrency(unittest.TestCase):
    @patch("ari_pipeline.night_factory_pipeline.fast_http_screen", new_callable=AsyncMock)
    def test_fast_workers_run_concurrently(self, mock_fast):
        concurrent = 0
        peak = 0
        lock = asyncio.Lock()

        async def slow_fast(candidate):
            nonlocal concurrent, peak
            async with lock:
                concurrent += 1
                peak = max(peak, concurrent)
            await asyncio.sleep(0.15)
            async with lock:
                concurrent -= 1
            return FastScreenResult(
                domain=candidate["domain"],
                url=candidate.get("website_url", ""),
                lane="NIGHT_FAST_LANE",
                outcome="UNREACHABLE",
                promote_browser=False,
                elapsed_sec=0.1,
            )

        mock_fast.side_effect = slow_fast

        async def _run():
            source = [
                {"domain": f"d{i}.test", "website_url": f"https://d{i}.test/"}
                for i in range(6)
            ]
            cp = {"exclusions": {}, "fast_http_results": {}}
            lw_state = {"candidates": [], "stats": {}}
            state = {"stats": {}}
            inv = {"ready_primary": [], "ready_remodel_reserve": []}
            mock_pool = MagicMock()
            mock_pool.context = MagicMock()
            pipeline = NightFactoryPipeline(
                source=source,
                pool_by_dom={},
                cp=cp,
                lw_run_id="test_lw",
                config={"fast_http_workers": 4, "lw_workers": 1},
                log=lambda _m: None,
                pf_batch_fn=AsyncMock(return_value=0),
                rf_batch_fn=AsyncMock(return_value=0),
                collect_ready_fn=lambda *_a, **_k: {"added_primary": 0, "added_remodel": 0},
                load_inv_fn=lambda: inv,
                save_cp_fn=lambda _c: None,
                save_state_fn=lambda _s: None,
                safety_check_fn=lambda **_: None,
                stop_check_fn=lambda *_a: False,
                max_source=6,
            )
            pipeline._browser_pool = mock_pool
            with patch("ari_pipeline.night_factory_pipeline.shutdown_browser_pool", new=AsyncMock()):
                stats = await asyncio.wait_for(
                    pipeline.run(lw_state=lw_state, inv=inv, state=state, stop_at=550),
                    timeout=30,
                )
            return stats

        stats = asyncio.run(_run())
        self.assertEqual(stats.fast_http_processed, 6)
        self.assertGreaterEqual(peak, 2, f"expected concurrent FAST workers, peak={peak}")


class TestCheckpointResume(unittest.TestCase):
    def test_existing_ready_preserved(self):
        cp = load_factory_checkpoint()
        before = load_ready_inventory()
        ready_before = len(before.get("ready_primary") or []) + len(before.get("ready_remodel_reserve") or [])
        self.assertGreaterEqual(ready_before, 9)

    def test_fast_http_additive(self):
        cp = load_factory_checkpoint()
        cp.setdefault("fast_http_results", {})["__test_domain__"] = {"outcome": "UNREACHABLE"}
        save_factory_checkpoint(cp)
        cp2 = load_factory_checkpoint()
        self.assertIn("__test_domain__", cp2.get("fast_http_results", {}))
        cp2["fast_http_results"].pop("__test_domain__", None)
        save_factory_checkpoint(cp2)


class TestNoProductionExecution(unittest.TestCase):
    @patch("run_ari_night_factory.get_real_submission_count", return_value=0)
    @patch("run_ari_night_factory.is_paused", return_value=True)
    @patch("run_ari_night_factory.load_limits")
    def test_validate_zero_send_gate(self, mock_limits, _paused, _rs):
        mock_limits.return_value.production_limit = 0
        v = nf.validate_night_factory()
        self.assertEqual(v["real_sends"], 0)
        self.assertEqual(v["final_submit"], 0)
        self.assertTrue(v["pass"])


class TestTargetAccounting(unittest.TestCase):
    def test_compute_final_gate_insufficient_when_no_throughput(self):
        gate = nf.compute_final_gate(ready_total=9, stop_at=550, throughput={})
        self.assertEqual(gate, "NIGHT_FACTORY_NOT_READY")

    @patch("run_ari_night_factory.get_real_submission_count", return_value=0)
    @patch("run_ari_night_factory.is_paused", return_value=True)
    @patch("run_ari_night_factory.load_limits")
    def test_compute_final_gate_ready_when_projected_ok(self, mock_limits, _paused, _rs):
        mock_limits.return_value.production_limit = 0
        gate = nf.compute_final_gate(
            ready_total=9,
            stop_at=550,
            throughput={"READY_per_hour": 80, "projected_overnight_ready": 649, "fast_http_per_hour": 400},
        )
        self.assertEqual(gate, "READY_TO_RESTART_NIGHT_FACTORY_FAST")


if __name__ == "__main__":
    unittest.main()
