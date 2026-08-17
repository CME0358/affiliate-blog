"""Night Factory / Terminal production coexistence — ZERO SEND."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

import run_ari_night_factory as nf
from ari_pipeline.production_ownership import (
    classify_sent_csv_delta,
    command_is_authorized_terminal,
    verify_authorized_terminal_owner,
)


class TestCommandAuthorization(unittest.TestCase):
    def test_terminal_script_authorized(self):
        self.assertTrue(command_is_authorized_terminal("python run_ari_terminal_production.py --daily-fast 50"))

    def test_night_factory_not_authorized(self):
        self.assertFalse(command_is_authorized_terminal("python run_ari_night_factory.py --resume"))


class TestSafetyCoexistence(unittest.TestCase):
    def tearDown(self):
        nf._SENT_CSV_BASELINE = None

    def _run_check(self, **kwargs):
        nf._SENT_CSV_BASELINE = kwargs.get("baseline", 10)
        owner = kwargs.get("owner", {"valid": False, "reason": "no_owner"})
        sent_kind = kwargs.get("sent_kind")
        if sent_kind is None:
            if kwargs.get("sent_lines", 10) > kwargs.get("baseline", 10) and not owner.get("valid"):
                sent_kind = "UNAUTHORIZED_MUTATION"
            elif kwargs.get("sent_lines", 10) > kwargs.get("baseline", 10):
                sent_kind = "AUTHORIZED_EXTERNAL_SENT_DELTA"
            else:
                sent_kind = "NONE"
        patches = {
            "run_ari_night_factory.load_limits": MagicMock(return_value=MagicMock(production_limit=kwargs.get("limit", 0))),
            "run_ari_night_factory.is_paused": MagicMock(return_value=True),
            "run_ari_night_factory.get_real_submission_count": MagicMock(return_value=kwargs.get("real_sends", 0)),
            "run_ari_night_factory.get_submit_forbidden": MagicMock(return_value=kwargs.get("forbidden", True)),
            "run_ari_night_factory.verify_authorized_terminal_owner": MagicMock(return_value=owner),
            "run_ari_night_factory._sent_csv_lines": MagicMock(return_value=kwargs.get("sent_lines", 10)),
            "run_ari_night_factory.save_factory_state": MagicMock(),
            "run_ari_night_factory.refresh_production_exclusions": MagicMock(return_value={"marked": 0}),
            "run_ari_night_factory.load_ready_inventory": MagicMock(return_value={}),
            "run_ari_night_factory.load_factory_checkpoint": MagicMock(return_value={}),
            "run_ari_night_factory.classify_sent_csv_delta": MagicMock(return_value={"kind": sent_kind, "delta": 1}),
            "run_ari_night_factory._log": MagicMock(),
        }
        ctxs = [patch(k, v) for k, v in patches.items()]
        for c in ctxs:
            c.start()
        try:
            nf._safety_check(state={"stats": {}})
        finally:
            for c in ctxs:
                c.stop()

    def test_limit_50_valid_owner_continues(self):
        self._run_check(limit=50, owner={"valid": True, "reason": "authorized_terminal_owner"})

    def test_limit_50_no_owner_hard_stop(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._run_check(limit=50, owner={"valid": False, "reason": "no_owner"})
        self.assertIn("production_limit=50", str(ctx.exception))
        self.assertIn("without authorized owner", str(ctx.exception))

    def test_fake_reused_pid_hard_stop(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._run_check(
                limit=50,
                owner={"valid": False, "reason": "owner_pid_reused_or_unauthorized_command"},
            )
        self.assertIn("NIGHT_FACTORY_SAFETY_VIOLATION", str(ctx.exception))

    def test_own_final_submit_hard_stop(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._run_check(real_sends=1, limit=0)
        self.assertIn("REAL_SEND_DETECTED", str(ctx.exception))

    def test_authorized_sent_delta_continues(self):
        nf._SENT_CSV_BASELINE = 10
        with patch("run_ari_night_factory.load_limits", return_value=MagicMock(production_limit=50)), \
             patch("run_ari_night_factory.is_paused", return_value=True), \
             patch("run_ari_night_factory.get_real_submission_count", return_value=0), \
             patch("run_ari_night_factory.get_submit_forbidden", return_value=True), \
             patch("run_ari_night_factory.verify_authorized_terminal_owner", return_value={"valid": True, "reason": "authorized_terminal_owner"}), \
             patch("run_ari_night_factory._sent_csv_lines", return_value=15), \
             patch("run_ari_night_factory.save_factory_state"), \
             patch("run_ari_night_factory.refresh_production_exclusions", return_value={"marked": 2}) as refresh, \
             patch("run_ari_night_factory.load_ready_inventory", return_value={}), \
             patch("run_ari_night_factory.load_factory_checkpoint", return_value={}), \
             patch("run_ari_night_factory._log"):
            nf._safety_check(state={"stats": {}})
            refresh.assert_called()
        self.assertEqual(nf._SENT_CSV_BASELINE, 15)

    def test_unauthorized_sent_mutation_hard_stop(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._run_check(limit=0, sent_lines=11, baseline=10, owner={"valid": False, "reason": "no_owner"})
        self.assertIn("UNAUTHORIZED_MUTATION", str(ctx.exception))

    def test_terminal_ends_factory_continues(self):
        nf._SENT_CSV_BASELINE = 20
        with patch("run_ari_night_factory.load_limits", return_value=MagicMock(production_limit=0)), \
             patch("run_ari_night_factory.is_paused", return_value=True), \
             patch("run_ari_night_factory.get_real_submission_count", return_value=0), \
             patch("run_ari_night_factory.get_submit_forbidden", return_value=True), \
             patch("run_ari_night_factory.verify_authorized_terminal_owner", return_value={"valid": False, "reason": "no_owner"}), \
             patch("run_ari_night_factory._sent_csv_lines", return_value=20), \
             patch("run_ari_night_factory.save_factory_state"):
            nf._safety_check(state={"stats": {}})

    def test_zero_send_codepath_forbids_send_form(self):
        nf._assert_night_factory_zero_send_codepath()


class TestClassifySentDelta(unittest.TestCase):
    def test_authorized_owner(self):
        r = classify_sent_csv_delta(baseline=1, current=3, owner_valid=True)
        self.assertEqual(r["kind"], "AUTHORIZED_EXTERNAL_SENT_DELTA")

    def test_unauthorized(self):
        r = classify_sent_csv_delta(baseline=1, current=3, owner_valid=False, production_date="2099-01-01")
        self.assertEqual(r["kind"], "UNAUTHORIZED_MUTATION")


class TestOwnerPidEqualsFactory(unittest.TestCase):
    def test_same_pid_rejected(self):
        with patch("ari_pipeline.production_ownership.load_ownership", return_value={
            "production_owner": "TERMINAL_PRODUCTION",
            "production_pid": 123,
        }), patch("ari_pipeline.production_ownership.process_alive", return_value=True):
            v = verify_authorized_terminal_owner(night_factory_pid=123)
            self.assertFalse(v["valid"])
            self.assertEqual(v["reason"], "owner_pid_equals_night_factory")


class TestCoexistenceGate(unittest.TestCase):
    @patch("run_ari_night_factory._external_production_blocks_factory", return_value=False)
    @patch("run_ari_night_factory.get_submit_forbidden", return_value=True)
    @patch("run_ari_night_factory.get_real_submission_count", return_value=0)
    def test_ready_to_resume(self, *_):
        self.assertEqual(nf.compute_coexistence_gate(), "READY_TO_RESUME_NIGHT_FACTORY_CONCURRENT")

    @patch("run_ari_night_factory._external_production_blocks_factory", return_value=True)
    @patch("run_ari_night_factory.get_submit_forbidden", return_value=True)
    @patch("run_ari_night_factory.get_real_submission_count", return_value=0)
    def test_paused_without_owner(self, *_):
        self.assertEqual(nf.compute_coexistence_gate(), "KEEP_NIGHT_FACTORY_PAUSED")


class TestConcurrentExclusion(unittest.TestCase):
    def test_refresh_marks_without_deleting(self):
        inv = {
            "ready_primary": [{"domain": "sent-example.co.jp", "company_name": "X"}],
            "ready_remodel_reserve": [],
        }
        idx = MagicMock()
        idx.confirmed_domains = {"sent-example.co.jp"}
        idx.effective_confirmed_sent = 916
        idx.is_confirmed_sent_domain.return_value = True
        idx.should_no_resend.return_value = True
        with patch("ari_pipeline.night_factory.get_sent_domain_index", return_value=idx), \
             patch("ari_pipeline.night_factory.load_attempted_domains", return_value={"sent-example.co.jp"}), \
             patch("ari_pipeline.night_factory.save_ready_inventory") as save:
            from ari_pipeline.night_factory import refresh_production_exclusions
            meta = refresh_production_exclusions(inv, {"exclusions": {}})
        self.assertEqual(meta["marked"], 1)
        self.assertTrue(inv["ready_primary"][0]["consumed_by_production"])
        self.assertEqual(len(inv["ready_primary"]), 1)
        save.assert_called()


class TestSimulationLimit50(unittest.TestCase):
    def test_mock_terminal_owner_zero_send(self):
        from form_sender import get_real_submission_count, set_submit_forbidden
        set_submit_forbidden(True)
        nf._SENT_CSV_BASELINE = 100
        with patch("run_ari_night_factory.load_limits", return_value=MagicMock(production_limit=50)), \
             patch("run_ari_night_factory.is_paused", return_value=True), \
             patch("run_ari_night_factory.verify_authorized_terminal_owner", return_value={
                 "valid": True, "reason": "authorized_terminal_owner",
                 "ownership": {"production_owner": "TERMINAL_PRODUCTION", "production_pid": 99999, "production_batch_id": "SIM"},
             }), \
             patch("run_ari_night_factory._sent_csv_lines", return_value=100), \
             patch("run_ari_night_factory.save_factory_state"):
            nf._safety_check(state={"stats": {}})
        self.assertEqual(get_real_submission_count(), 0)


if __name__ == "__main__":
    unittest.main()
