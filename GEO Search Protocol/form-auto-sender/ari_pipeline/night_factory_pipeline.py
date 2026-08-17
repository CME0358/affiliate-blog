"""
night_factory_pipeline.py — High-throughput streaming Night Factory (ZERO SEND).

Stage 0 FAST_HTTP → bounded Playwright LW → PF → RF → READY
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from datetime import datetime
from typing import Any, Callable

from ari_pipeline.business_inquiry_surface import assess_from_lightweight_record
from ari_pipeline.fast_http_screen import (
    fast_http_screen,
    fast_outcome_to_lw,
)
from ari_pipeline.night_factory_browser_pool import get_browser_pool, shutdown_browser_pool
from ari_pipeline.orchestrator import (
    Stage,
    map_lightweight_outcome,
    save_checkpoint,
)
from ari_pipeline.high_yield_source_scoring import sort_by_ready_priority
from ari_pipeline.r2_lane_c_filter import lane_c_url_pattern_score
from form_detector import detect_form_only_at_url
from form_sender import get_real_submission_count, set_submit_forbidden
from lightweight_form_classifier import classify_lightweight, score_lightweight

LogFn = Callable[[str], None]


class ThroughputStats:
    def __init__(self) -> None:
        self.started_at = time.monotonic()
        self.fast_http_processed = 0
        self.browser_promoted = 0
        self.lw_completed = 0
        self.pf_completed = 0
        self.rf_completed = 0
        self.ready_added = 0
        self.fast_lane = 0
        self.slow_lane = 0
        self.browser_launches = 0
        self.timeouts = 0
        self.outcomes: Counter = Counter()
        self._ready_samples: list[tuple[float, int]] = []

    def record_ready(self, total: int) -> None:
        self._ready_samples.append((time.monotonic(), total))
        self._ready_samples = self._ready_samples[-200:]

    def rate_per_hour(self, count: int) -> float:
        elapsed_h = max((time.monotonic() - self.started_at) / 3600, 1 / 3600)
        return count / elapsed_h

    def ready_per_hour(self) -> float:
        if len(self._ready_samples) < 2:
            return 0.0
        now = time.monotonic()
        window = [(t, n) for t, n in self._ready_samples if now - t <= 3600]
        if len(window) < 2:
            t0, n0 = self._ready_samples[0]
            t1, n1 = self._ready_samples[-1]
        else:
            t0, n0 = window[0]
            t1, n1 = window[-1]
        dt = t1 - t0
        if dt < 1:
            return 0.0
        return max(0.0, (n1 - n0) / dt * 3600)

    def eta_hours(self, remaining: int, rate: float) -> float | None:
        if rate <= 0 or remaining <= 0:
            return None
        return remaining / rate

    def to_dict(self, *, ready_total: int, stop_target: int) -> dict[str, Any]:
        rph = self.ready_per_hour()
        remaining = max(0, stop_target - ready_total)
        eta_h = self.eta_hours(remaining, rph)
        return {
            "fast_http_processed": self.fast_http_processed,
            "fast_http_per_hour": round(self.rate_per_hour(self.fast_http_processed), 1),
            "browser_promoted": self.browser_promoted,
            "lw_per_hour": round(self.rate_per_hour(self.lw_completed), 1),
            "pf_per_hour": round(self.rate_per_hour(self.pf_completed), 1),
            "rf_per_hour": round(self.rate_per_hour(self.rf_completed), 1),
            "READY_per_hour": round(rph, 1),
            "fast_lane_count": self.fast_lane,
            "slow_lane_count": self.slow_lane,
            "browser_launches": self.browser_launches,
            "timeout_counts": self.timeouts,
            "outcomes": dict(self.outcomes),
            "ETA_500": round(eta_h, 2) if eta_h and stop_target >= 500 else None,
            "ETA_550": round(eta_h, 2) if eta_h else None,
            "projected_overnight_ready": round(ready_total + rph * 8, 0) if rph else ready_total,
        }


class NightFactoryPipeline:
    def __init__(
        self,
        *,
        source: list[dict],
        pool_by_dom: dict[str, dict],
        cp: dict,
        lw_run_id: str,
        config: dict,
        log: LogFn,
        pf_batch_fn,
        rf_batch_fn,
        collect_ready_fn,
        load_inv_fn,
        save_cp_fn,
        save_state_fn,
        safety_check_fn,
        stop_check_fn,
        max_source: int | None = None,
    ) -> None:
        self.source = source
        self.pool_by_dom = pool_by_dom
        self.cp = cp
        self.lw_run_id = lw_run_id
        self.config = config
        self.log = log
        self.pf_batch_fn = pf_batch_fn
        self.rf_batch_fn = rf_batch_fn
        self.collect_ready_fn = collect_ready_fn
        self.load_inv_fn = load_inv_fn
        self.save_cp_fn = save_cp_fn
        self.save_state_fn = save_state_fn
        self.safety_check_fn = safety_check_fn
        self.stop_check_fn = stop_check_fn
        self.max_source = max_source

        self.stats = ThroughputStats()
        self.fast_workers = int(config.get("fast_http_workers", 12))
        self.lw_workers = int(config.get("lw_workers", 2))
        self.pf_workers = min(2, max(1, int(config.get("pf_workers", 2))))
        self.rf_workers = min(2, max(1, int(config.get("rf_workers", 2))))

        self._fast_q: asyncio.Queue[dict | None] = asyncio.Queue()
        self._lw_q: asyncio.Queue[tuple[dict, Any] | None] = asyncio.Queue()
        self._stop = asyncio.Event()
        self._lw_records: dict[str, dict] = {}
        self._browser_pool = get_browser_pool(max_contexts=self.lw_workers)

    def _pending_domains(self, lw_state: dict) -> list[dict]:
        done = {
            (c.get("domain") or "").lower()
            for c in lw_state.get("candidates") or []
            if c.get("status") == "completed"
        }
        fast_done = set((self.cp.get("fast_http_results") or {}).keys())
        exclusions = set((self.cp.get("exclusions") or {}).keys())
        allow_slow = bool(self.config.get("allow_slow_path", False))
        pending: list[dict] = []
        for c in self.source:
            dom = c.get("domain", "").lower()
            if dom in done or dom in fast_done or dom in exclusions:
                continue
            tier = c.get("ready_priority_tier") or ""
            if not allow_slow and tier == "SLOW_PATH":
                continue
            pending.append(c)
        pending.sort(
            key=lambda r: (
                0 if r.get("ready_priority_tier") == "READY_PRIORITY_A" else (
                    1 if r.get("ready_priority_tier") == "READY_PRIORITY_B" else 2
                ),
                -int(r.get("ready_yield_score") or 0),
                -lane_c_url_pattern_score(r.get("lw_entry_url") or r.get("website_url", "")),
                r.get("industry_tier", 99),
            )
        )
        if self.max_source:
            pending = pending[: self.max_source]
        return pending

    def _apply_lw_record(self, c: dict, *, outcome: str, det: dict | None = None, fast_meta: dict | None = None) -> None:
        dom = (c.get("domain") or "").lower()
        rec = {
            **c,
            "stage": Stage.LIGHTWEIGHT_DETECT.value,
            "status": "completed",
            "lightweight_outcome": outcome,
            "last_checked_at": datetime.now().isoformat(),
        }
        if det:
            rec["detection"] = {
                k: det.get(k)
                for k in (
                    "form_url", "form_type", "confidence", "captcha", "failure_reason",
                    "field_map", "submit_label", "external_provider", "contact_page_url",
                )
            }
            rec["form_url"] = det.get("form_url") or c.get("lw_entry_url") or ""
            rec["form_type"] = det.get("form_type") or ""
            rec["captcha"] = bool(det.get("captcha"))
            classification, reason, _ = classify_lightweight(det)
            rec["lightweight_classification"] = classification
            rec["lightweight_score"] = score_lightweight(det, classification, c)
            mapped = map_lightweight_outcome(classification, reason, det)
            rec["lightweight_outcome"] = mapped
            rec["lightweight_reason"] = reason
            outcome = mapped
            if mapped == "PREFLIGHT_CANDIDATE":
                rec["stage"] = Stage.PREFLIGHT_CANDIDATE.value
        if fast_meta:
            rec["fast_http"] = fast_meta
        self._lw_records[dom] = rec
        self.stats.outcomes[outcome] += 1
        if outcome == "PREFLIGHT_CANDIDATE":
            self.cp.setdefault("domain_stages", {})[dom] = "PREFLIGHT_CANDIDATE"
        elif outcome:
            self.cp.setdefault("exclusions", {})[dom] = outcome

    async def _persist_lw_checkpoint(self, lw_state: dict) -> None:
        by_dom = { (c.get("domain") or "").lower(): c for c in lw_state.get("candidates") or [] }
        for dom, rec in self._lw_records.items():
            by_dom[dom] = rec
        lw_state["candidates"] = list(by_dom.values()) if by_dom else lw_state.get("candidates") or []
        lw_state["stats"] = lw_state.get("stats") or {}
        lw_state["stats"]["processed"] = sum(
            1 for c in lw_state["candidates"] if c.get("status") == "completed"
        )
        save_checkpoint(lw_state)
        self.save_cp_fn(self.cp)
        self._lw_records.clear()

    async def _fast_worker(self, wid: int) -> None:
        while not self._stop.is_set():
            try:
                c = await asyncio.wait_for(self._fast_q.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            if c is None:
                self._fast_q.task_done()
                break
            dom = c.get("domain", "")
            try:
                result = await fast_http_screen(c)
                self.cp.setdefault("fast_http_results", {})[dom] = {
                    "outcome": result.outcome,
                    "lane": result.lane,
                    "promote_browser": result.promote_browser,
                    "elapsed_sec": result.elapsed_sec,
                    "reason": result.reason,
                    "signals": result.signals,
                    "url": result.url,
                }
                self.stats.fast_http_processed += 1
                if result.lane == "NIGHT_FAST_LANE":
                    self.stats.fast_lane += 1
                else:
                    self.stats.slow_lane += 1

                lw_out = fast_outcome_to_lw(result.outcome)
                if lw_out and not result.promote_browser:
                    self._apply_lw_record(c, outcome=lw_out, fast_meta=self.cp["fast_http_results"][dom])
                    if lw_out == "SLOW_PATH_REVIEW":
                        self.cp.setdefault("exclusions", {})[dom] = "SLOW_PATH_REVIEW"
                    self.log(f"[FAST {wid:02d}] {dom} -> {result.outcome} ({result.elapsed_sec:.1f}s)")
                elif result.promote_browser:
                    self.stats.browser_promoted += 1
                    await self._lw_q.put((c, result))
                    self.log(f"[FAST {wid:02d}] {dom} -> PROMOTE_BROWSER ({result.elapsed_sec:.1f}s)")
                else:
                    self.log(f"[FAST {wid:02d}] {dom} -> {result.outcome}")
            except Exception as e:
                self.log(f"[FAST {wid:02d}] {dom} ERROR {e}")
            finally:
                self._fast_q.task_done()

    async def _lw_worker(self, wid: int) -> None:
        while not self._stop.is_set():
            try:
                item = await asyncio.wait_for(self._lw_q.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            if item is None:
                self._lw_q.task_done()
                break
            c, fast_result = item
            dom = c.get("domain", "")
            url = fast_result.url or c.get("lw_entry_url") or c.get("website_url", "")
            t0 = time.monotonic()
            try:
                set_submit_forbidden(True)
                before = get_real_submission_count()
                det = await detect_form_only_at_url(
                    c, url, browser_pool=self._browser_pool, timeout_sec=18,
                )
                if get_real_submission_count() > before:
                    raise RuntimeError("SAFETY: submission during LW")
                classification, reason, _ = classify_lightweight(det)
                outcome = map_lightweight_outcome(classification, reason, det)
                self._apply_lw_record(c, outcome=outcome, det=det, fast_meta={"promoted_from": fast_result.outcome})
                self.stats.lw_completed += 1
                elapsed = time.monotonic() - t0
                if det.get("failure_reason") == "page_load_timeout":
                    self.stats.timeouts += 1
                self.log(f"[LW {wid:02d}] {dom} -> {outcome} ({elapsed:.1f}s)")
            except Exception as e:
                self._apply_lw_record(c, outcome="INTERNAL_ERROR", fast_meta={"error": str(e)[:120]})
                self.log(f"[LW {wid:02d}] {dom} -> INTERNAL_ERROR {e}")
            finally:
                self._lw_q.task_done()

    async def _downstream_loop(self, lw_state: dict, inv: dict, state: dict, stop_at: int) -> None:
        """PF / RF / READY streaming while FAST/LW workers run."""
        last_summary = time.monotonic()
        last_checkpoint = time.monotonic()
        checkpoint_interval = int(self.config.get("checkpoint_interval_sec", 300))
        while not self._stop.is_set():
            self.safety_check_fn(state=state)
            if self.stop_check_fn(stop_at, inv):
                self._stop.set()
                break

            if self._lw_records:
                await self._persist_lw_checkpoint(lw_state)

            pf_n = await self.pf_batch_fn(self.cp, batch_size=int(self.config.get("pf_batch_size", 12)))
            if pf_n:
                self.stats.pf_completed += pf_n

            rf_n = await self.rf_batch_fn(self.cp, batch_size=int(self.config.get("rf_batch_size", 12)))
            if rf_n:
                self.stats.rf_completed += rf_n

            added_info = self.collect_ready_fn(self.pool_by_dom, self.cp, inv)
            inv.clear()
            inv.update(self.load_inv_fn())
            added_n = 0
            if isinstance(added_info, dict):
                added_n = int(added_info.get("added_primary", 0) + added_info.get("added_remodel", 0))
            elif added_info:
                added_n = int(added_info)
            primary = len(inv.get("ready_primary") or [])
            remodel = len(inv.get("ready_remodel_reserve") or [])
            total = primary + remodel
            self.stats.record_ready(total)
            self.stats.ready_added = total

            state.setdefault("stats", {})
            state["stats"]["fast_http_processed"] = self.stats.fast_http_processed
            state["stats"]["lw_processed"] = lw_state.get("stats", {}).get("processed", 0) + len(self._lw_records)
            state["stats"]["throughput"] = self.stats.to_dict(ready_total=total, stop_target=stop_at)
            state["stats"]["pf_processed"] = len(self.cp.get("preflight_results") or {})
            state["stats"]["rf_processed"] = len(self.cp.get("refresh_results") or {})
            state["stats"]["ready_total"] = total
            state["last_checkpoint_at"] = datetime.now().isoformat()
            self.save_cp_fn(self.cp)
            self.save_state_fn(state)

            now = time.monotonic()
            if now - last_checkpoint >= checkpoint_interval:
                from ari_pipeline.night_factory import build_morning_inventory
                build_morning_inventory(inv, target=int(self.config.get("target_ready", 500)), cp=self.cp)
                last_checkpoint = now
            if now - last_summary >= int(self.config.get("summary_interval_sec", 900)):
                tp = self.stats.to_dict(ready_total=total, stop_target=stop_at)
                self.log(
                    f"NIGHT FACTORY | READY {total}/{stop_at} | FAST {self.stats.fast_http_processed} "
                    f"| LW {self.stats.lw_completed} | {tp['READY_per_hour']:.0f} READY/h "
                    f"| proj overnight {tp['projected_overnight_ready']:.0f}"
                )
                last_summary = now

            await asyncio.sleep(2)

    async def run(self, *, lw_state: dict, inv: dict, state: dict, stop_at: int) -> ThroughputStats:
        pending = self._pending_domains(lw_state)
        self.log(f"Pipeline feed | pending={len(pending)} fast_workers={self.fast_workers} lw_workers={self.lw_workers}")

        fast_tasks = [asyncio.create_task(self._fast_worker(i)) for i in range(self.fast_workers)]
        lw_tasks = [asyncio.create_task(self._lw_worker(i)) for i in range(self.lw_workers)]
        self._worker_tasks = fast_tasks + lw_tasks
        downstream = asyncio.create_task(self._downstream_loop(lw_state, inv, state, stop_at))

        for c in pending:
            if self._stop.is_set():
                break
            await self._fast_q.put(c)

        await self._fast_q.join()

        for _ in range(self.lw_workers):
            await self._lw_q.put(None)
        await self._lw_q.join()

        for _ in range(self.fast_workers):
            await self._fast_q.put(None)

        await asyncio.gather(*fast_tasks, return_exceptions=True)
        await asyncio.gather(*lw_tasks, return_exceptions=True)

        self._stop.set()
        downstream.cancel()
        try:
            await downstream
        except asyncio.CancelledError:
            pass
        await self._persist_lw_checkpoint(lw_state)
        await shutdown_browser_pool()
        return self.stats


def serial_lw_root_cause_report() -> dict[str, str]:
    return {
        "configured_lw_workers": "Config-only — never passed to orchestrator",
        "orchestrator_loop": "run_lightweight_detect_stage uses sequential for/await (one candidate at a time)",
        "detect_form_only": "Each call runs find_form_url (20–30 link crawl) then async_playwright().chromium.launch() per candidate",
        "night_factory_batch": "run_lw_batch awaited run_lightweight_detect_stage serially — no asyncio.gather",
        "fix": "NightFactoryPipeline: FAST_HTTP x12 concurrent + shared browser pool x2 LW contexts",
    }
