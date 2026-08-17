"""Tests for run_ari_terminal_production.py — ZERO SEND validation."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

import run_ari_terminal_production as rtp


class TestBatchSizeParsing(unittest.TestCase):
    def test_default_batch_size(self):
        self.assertEqual(rtp.parse_batch_size(None), rtp.DEFAULT_BATCH_SIZE)

    def test_explicit_batch_size(self):
        self.assertEqual(rtp.parse_batch_size("10"), 10)

    def test_rejects_zero(self):
        with self.assertRaises(ValueError):
            rtp.parse_batch_size("0")

    def test_rejects_over_max(self):
        with self.assertRaises(ValueError):
            rtp.parse_batch_size(str(rtp.MAX_BATCH_SIZE + 1))


class TestSafetyPreflight(unittest.TestCase):
    def test_validate_runner_zero_send(self):
        report = rtp.verify_safety_preflight(batch_size=10, require_confirm=False)
        self.assertIn("passed", report)
        self.assertIn("checks", report)
        self.assertIn("final_gate_ready", report["checks"])
        self.assertIn("automation_paused", report["checks"])
        self.assertIn("production_limit_zero", report["checks"])
        self.assertGreaterEqual(report["eligible_unsent_count"], 0)

    def test_fails_without_confirm_when_required(self):
        env = os.environ.copy()
        env.pop(rtp.CONFIRM_ENV, None)
        with patch.dict(os.environ, env, clear=True):
            report = rtp.verify_safety_preflight(batch_size=10, require_confirm=True)
        self.assertFalse(report["passed"])
        self.assertTrue(any("CONFIRM" in e for e in report["errors"]))


class TestEligibleSelection(unittest.TestCase):
    def test_compute_eligible_deterministic_order(self):
        eligible, meta = rtp.compute_eligible_unsent()
        indices = [int(c.get("lock_index") or 0) for c in eligible]
        self.assertEqual(indices, sorted(indices))
        self.assertIn("eligible_count", meta)
        self.assertIn("effective_confirmed_sent", meta)

    def test_build_exclusions_includes_attempted(self):
        excluded, summary = rtp.build_canonical_exclusions()
        self.assertIsInstance(excluded, frozenset)
        self.assertIn("attempted", summary)


class TestShutdown(unittest.TestCase):
    def test_shutdown_restores_safe_state(self):
        info = rtp.shutdown_safe(reset_production_limit=True, by="test")
        self.assertTrue(info["submit_forbidden"])
        self.assertEqual(info["production_limit"], 0)
        self.assertTrue(info["automation_paused"])


class TestStatusMode(unittest.TestCase):
    def test_status_shape(self):
        status = rtp.read_status()
        for key in (
            "worker_running",
            "pid",
            "batch_id",
            "processed",
            "target",
            "effective_confirmed_sent",
            "production_limit",
            "automation_paused",
            "submit_forbidden",
        ):
            self.assertIn(key, status)


class TestBatchLock(unittest.TestCase):
    def test_lock_artifact_immutable_fields(self):
        eligible, _ = rtp.compute_eligible_unsent()
        if len(eligible) < 1:
            self.skipTest("no eligible candidates for lock test")
        batch_id, selected, meta, lock_path = rtp.create_batch_lock(1)
        self.assertTrue(lock_path.exists())
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        self.assertTrue(payload.get("immutable"))
        self.assertEqual(payload["candidate_count"], 1)
        self.assertEqual(payload["batch_id"], batch_id)
        self.assertEqual(len(selected), 1)
        lock_path.unlink(missing_ok=True)


class TestStopGates(unittest.TestCase):
    def test_inquiry_purpose_violation_detected(self):
        row = {
            "attempted": True,
            "submission_meta": {
                "choices_applied": [
                    {"category": "INQUIRY_CATEGORY", "label": "資料請求", "context": ""},
                ],
            },
        }
        self.assertTrue(rtp._inquiry_purpose_violation(row))

    def test_compatible_purpose_not_violation(self):
        row = {
            "attempted": True,
            "submission_meta": {
                "choices_applied": [
                    {"category": "INQUIRY_CATEGORY", "label": "その他", "context": ""},
                ],
            },
        }
        self.assertFalse(rtp._inquiry_purpose_violation(row))


if __name__ == "__main__":
    unittest.main()
