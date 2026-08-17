"""Tests for Proven Pattern Fast Path + Daily Fast runner — ZERO SEND."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from ari_pipeline.daily_fast_runner import (
    DailyCounters,
    candidate_skip_outcome,
    daily_target_reached,
    should_system_hard_stop,
    update_counters_from_result,
)
from ari_pipeline.proven_pattern_library import (
    PROVEN_FAST_PATH,
    SLOW_PATH_REVIEW,
    TIER_A,
    TIER_B,
    TIER_C,
    assign_tier,
    audit_historical_successes,
    classify_candidate,
    infer_framework_from_signals,
    match_proven_pattern,
    minimum_pattern_support_met,
    normalize_success_evidence,
    parse_daily_logs,
)
import run_ari_terminal_production as rtp


class TestPatternExtraction(unittest.TestCase):
    def test_normalize_success_evidence_cf7(self):
        self.assertEqual(normalize_success_evidence("wpcf7_mail_sent_ok"), "cf7_mail_sent")

    def test_infer_framework_cf7(self):
        fw = infer_framework_from_signals(form_url="https://example.com/contact wpcf7")
        self.assertEqual(fw, "contact_form_7")

    def test_audit_historical_successes_shape(self):
        audit = audit_historical_successes()
        self.assertGreaterEqual(audit["successes_audited"], 800)
        self.assertGreater(audit["patterns_extracted"], 0)
        self.assertIn("tier_a_count", audit)
        self.assertIn("patterns", audit)

    def test_parse_daily_logs_nonempty(self):
        logs = parse_daily_logs()
        self.assertGreater(len(logs), 0)


class TestTierAssignment(unittest.TestCase):
    def test_tier_a_with_auto_reply(self):
        self.assertEqual(
            assign_tier(domain_count=1, auto_reply_count=1, success_evidence="unknown"),
            TIER_A,
        )

    def test_tier_b_single_strong(self):
        self.assertEqual(
            assign_tier(domain_count=1, auto_reply_count=0, success_evidence="cf7_mail_sent"),
            TIER_B,
        )

    def test_tier_c_weak_single(self):
        self.assertEqual(
            assign_tier(domain_count=1, auto_reply_count=0, success_evidence="unknown"),
            TIER_C,
        )

    def test_minimum_support_two_domains(self):
        self.assertTrue(minimum_pattern_support_met(tier=TIER_B, domain_count=2, auto_reply_count=0))

    def test_minimum_support_tier_c_false(self):
        self.assertFalse(minimum_pattern_support_met(tier=TIER_C, domain_count=5, auto_reply_count=0))


class TestFastPathMatching(unittest.TestCase):
    def _sample_candidate(self) -> dict:
        return {
            "domain": "example.co.jp",
            "form_url": "https://example.co.jp/contact/",
            "preflight_classification": "AUTO_READY",
            "form_type": "single_step",
            "fill_no_submit": {"multistep_state": "FINAL_SUBMIT_READY", "final_submit_label": "送信"},
            "lightweight_evidence": {"form_url": "https://example.co.jp/contact/", "form_type": "single_step"},
        }

    def test_no_detection_evidence_is_slow_path(self):
        cls = classify_candidate({"domain": "x.co.jp", "website_url": "https://x.co.jp/contact/"})
        self.assertEqual(cls["classification"], SLOW_PATH_REVIEW)

    def test_match_requires_detection(self):
        lib = audit_historical_successes()
        match = match_proven_pattern(self._sample_candidate(), lib)
        # May or may not match depending on library — must not crash
        self.assertTrue(match is None or "matched_pattern_id" in match)


class TestDailyFastCounters(unittest.TestCase):
    def test_skip_does_not_count_as_attempt(self):
        c = DailyCounters()
        res = candidate_skip_outcome("a.co.jp", "SLOW_PATH_REVIEW", "no_match", batch_id="T")
        update_counters_from_result(c, res, skip_classification="SLOW_PATH_REVIEW")
        self.assertEqual(c.final_submit_attempts, 0)
        self.assertEqual(c.candidates_skipped, 1)

    def test_daily_target_reached(self):
        c = DailyCounters(final_submit_attempts=300)
        self.assertTrue(daily_target_reached(c, 300))

    def test_system_hard_stop_false_sent(self):
        c = DailyCounters(false_sent=1)
        stop, why, sc = should_system_hard_stop(c, [])
        self.assertTrue(stop)
        self.assertEqual(why, "false_sent")
        self.assertEqual(sc, "HARD_STOP")


class TestDailyFastStopPolicy(unittest.TestCase):
    def test_runtime_divergence_skip_does_not_hard_stop_daily(self):
        c = DailyCounters()
        res = {
            "attempted": False,
            "submission_state": "RUNTIME_DIVERGENCE",
            "pre_send_skip_reason": "RUNTIME_DIVERGENCE",
        }
        update_counters_from_result(c, res, skip_classification="RUNTIME_DIVERGENCE")
        stop, _, _ = rtp._should_stop_daily_fast(c, [], [res])
        self.assertFalse(stop)

    def test_inquiry_purpose_violation_hard_stops(self):
        c = DailyCounters()
        row = {
            "attempted": True,
            "submission_meta": {
                "choices_applied": [{"category": "INQUIRY_CATEGORY", "label": "資料請求"}],
            },
        }
        stop, why, sc = rtp._should_stop_daily_fast(c, [row], [row])
        self.assertTrue(stop)
        self.assertEqual(why, "inquiry_purpose_policy_violation")


class TestDailyFastSafety(unittest.TestCase):
    def test_verify_daily_fast_safety_zero_send(self):
        from config import VAULT_ROOT
        lib = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Proven-Form-Pattern-Library.json"
        if not lib.exists():
            self.skipTest("pattern library not built")
        qpath = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Fast-Production-Queue-2026-08-13.json"
        if not qpath.exists():
            self.skipTest("queue not prepared")
        report = rtp.verify_daily_fast_safety(
            target_attempts=300,
            queue_date="2026-08-13",
            require_confirm=False,
        )
        self.assertIn("passed", report)
        self.assertTrue(report["checks"]["pattern_library_exists"])


class TestDailyFastTargetParsing(unittest.TestCase):
    def test_default_300(self):
        self.assertEqual(rtp.parse_daily_fast_target(None), 300)

    def test_rejects_over_max(self):
        with self.assertRaises(ValueError):
            rtp.parse_daily_fast_target("301")


class TestQueueIsolation(unittest.TestCase):
    def test_queues_no_duplicate_domains_across_dates(self):
        from config import VAULT_ROOT
        dates = ("2026-08-13", "2026-08-14", "2026-08-15")
        seen: set[str] = set()
        for d in dates:
            p = VAULT_ROOT / f"70_outputs/5-Day-Sales-Sprint/ARI-Fast-Production-Queue-{d}.json"
            if not p.exists():
                continue
            data = json.loads(p.read_text())
            for c in data.get("candidates") or []:
                dom = c.get("domain", "")
                self.assertNotIn(dom, seen, f"duplicate {dom} on {d}")
                seen.add(dom)


if __name__ == "__main__":
    unittest.main()
