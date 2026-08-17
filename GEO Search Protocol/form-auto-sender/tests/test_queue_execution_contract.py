"""Regression tests for queue execution contract (AUTHORIZED_READY vs PROVEN_PATTERN_FAST)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ari_pipeline.queue_evidence_contract import build_queue_authorization
from ari_pipeline.queue_execution_contract import (
    QUEUE_MODE_AUTHORIZED_READY,
    QUEUE_MODE_PROVEN_PATTERN_FAST,
    audit_queue_contract_parity,
    evaluate_authorized_ready_gate,
    evaluate_proven_pattern_fast_gate,
    evaluate_terminal_daily_fast_gate,
    load_queue_evidence_maps,
    resolve_queue_mode,
    terminal_consumer_eligible_for_queue,
)
from ari_pipeline.proven_pattern_library import PROVEN_FAST_PATH, SLOW_PATH_REVIEW


def _sample_refresh_row(dom: str = "example.co.jp") -> dict:
    sem_hash = "abc123" * 5 + "abcd"
    return {
        "domain": dom,
        "refresh_outcome": "REFRESH_READY",
        "purpose_audit": "COMPATIBLE",
        "semantic_evidence_v2": {
            "semantic_hash": sem_hash,
            "semantic_evidence_schema_version": "v2",
            "semantic_policy_fingerprint": "fp-test",
            "canonical_snapshot": {
                "submit_target": {"selector": "#submit", "label": "送信"},
                "field_map": {"name": "FILLED", "email": "FILLED", "message": "FILLED"},
                "choices_applied": [{"category": "INQUIRY_CATEGORY", "label": "お問い合わせ"}],
            },
        },
    }


def _sample_queue_record(dom: str = "example.co.jp", rr: dict | None = None) -> dict:
    rr = rr or _sample_refresh_row(dom)
    rec = {
        "domain": dom,
        "company_name": "Example Co",
        "website_url": f"https://{dom}/",
        "form_url": f"https://{dom}/contact",
        "production_eligibility": "production_ready",
        "inquiry_purpose_audit": "COMPATIBLE",
        "queue_revision": "TEST",
    }
    rec["queue_authorization"] = build_queue_authorization(rec, rr)
    return rec


class TestQueueModeResolution(unittest.TestCase):
    def test_default_legacy_fast_path(self):
        self.assertEqual(resolve_queue_mode({}), QUEUE_MODE_PROVEN_PATTERN_FAST)

    def test_explicit_authorized_ready(self):
        self.assertEqual(
            resolve_queue_mode({"queue_mode": QUEUE_MODE_AUTHORIZED_READY}),
            QUEUE_MODE_AUTHORIZED_READY,
        )


class TestAuthorizedReadyGate(unittest.TestCase):
    @patch("ari_pipeline.queue_evidence_contract.assess_production_evidence_eligibility", return_value=("ELIGIBLE", []))
    def test_authorized_ready_without_proven_pattern(self, _schema):
        rr = _sample_refresh_row("no-pattern.co.jp")
        rec = _sample_queue_record("no-pattern.co.jp", rr)
        pf = {"fill_no_submit": {"captcha_detected": False}}
        ok, reason, detail = evaluate_authorized_ready_gate(rec, preflight_row=pf, refresh_row=rr)
        self.assertTrue(ok, reason)
        self.assertEqual(detail.get("queue_mode"), QUEUE_MODE_AUTHORIZED_READY)

    @patch("ari_pipeline.queue_evidence_contract.assess_production_evidence_eligibility", return_value=("ELIGIBLE", []))
    def test_missing_authorization_fails(self, _schema):
        rec = {"domain": "example.co.jp", "production_eligibility": "production_ready"}
        ok, reason, _ = evaluate_authorized_ready_gate(rec, preflight_row={}, refresh_row=None)
        self.assertFalse(ok)
        self.assertIn("refresh", reason.lower())


class TestProvenPatternFastGate(unittest.TestCase):
    @patch("ari_pipeline.queue_evidence_contract.assess_production_evidence_eligibility", return_value=("ELIGIBLE", []))
    @patch("ari_pipeline.proven_pattern_library.classify_candidate")
    def test_proven_pattern_fast_requires_match(self, mock_cls, _schema):
        mock_cls.return_value = {"classification": SLOW_PATH_REVIEW, "reason": "no_proven_pattern_match"}
        rr = _sample_refresh_row()
        rec = _sample_queue_record(rr=rr)
        ok, reason, detail = evaluate_proven_pattern_fast_gate(rec, preflight_row={}, refresh_row=rr)
        self.assertFalse(ok)
        self.assertEqual(reason, "no_proven_pattern_match")
        self.assertEqual(detail["classification"], SLOW_PATH_REVIEW)

    @patch("ari_pipeline.queue_evidence_contract.assess_production_evidence_eligibility", return_value=("ELIGIBLE", []))
    @patch("ari_pipeline.proven_pattern_library.classify_candidate")
    def test_proven_pattern_fast_passes_with_match(self, mock_cls, _schema):
        mock_cls.return_value = {
            "classification": PROVEN_FAST_PATH,
            "matched_pattern_id": "PAT-1",
        }
        rr = _sample_refresh_row()
        rec = _sample_queue_record(rr=rr)
        pf = {"fill_no_submit": {"captcha_detected": False}}
        ok, reason, _ = evaluate_proven_pattern_fast_gate(rec, preflight_row=pf, refresh_row=rr)
        self.assertTrue(ok, reason)


class TestQueueModePreservedThroughLoad(unittest.TestCase):
    def test_queue_mode_in_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            cp = Path(tmp) / "night_factory_20260814.json"
            cp.write_text(json.dumps({"preflight_results": {}, "refresh_results": {}}))
            payload = {
                "queue_mode": QUEUE_MODE_AUTHORIZED_READY,
                "evidence_checkpoint_id": "night_factory_20260814",
            }
            with patch("ari_pipeline.queue_execution_contract.LOG_DIR", Path(tmp)):
                mode = resolve_queue_mode(payload)
                self.assertEqual(mode, QUEUE_MODE_AUTHORIZED_READY)


class TestP01Requeueable(unittest.TestCase):
    def test_skip_only_domains_not_attempted(self):
        from config import VAULT_ROOT

        results_path = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Fast-Production-Results-2026-08-14-MORNING-P01.json"
        if not results_path.exists():
            self.skipTest("P01 results missing")
        data = json.loads(results_path.read_text())
        for row in data.get("results") or []:
            self.assertFalse(row.get("attempted"))
            self.assertFalse(row.get("final_submit_clicked"))
            self.assertEqual(row.get("submission_state"), "SKIPPED")


class TestTerminalConsumerForQueueMode(unittest.TestCase):
    @patch("ari_pipeline.queue_evidence_contract.assess_production_evidence_eligibility", return_value=("ELIGIBLE", []))
    def test_authorized_ready_terminal_consumer(self, _schema):
        rr = _sample_refresh_row("auth-only.co.jp")
        rec = _sample_queue_record("auth-only.co.jp", rr)
        pf = {"fill_no_submit": {"captcha_detected": False}}
        ok, reason = terminal_consumer_eligible_for_queue(
            rec,
            queue_mode=QUEUE_MODE_AUTHORIZED_READY,
            refresh_row=rr,
            preflight_row=pf,
        )
        self.assertTrue(ok, reason)


class TestAuditParity(unittest.TestCase):
    @patch("ari_pipeline.queue_evidence_contract.assess_production_evidence_eligibility", return_value=("ELIGIBLE", []))
    def test_audit_parity_empty_mismatch_on_authorized(self, _schema):
        rr = _sample_refresh_row("parity.co.jp")
        rec = _sample_queue_record("parity.co.jp", rr)
        pf = {"fill_no_submit": {"captcha_detected": False}}
        with patch("ari_pipeline.queue_execution_contract.load_queue_evidence_maps") as mock_maps:
            mock_maps.return_value = ({"parity.co.jp": pf}, {"parity.co.jp": rr})
            report = audit_queue_contract_parity(
                {
                    "queue_mode": QUEUE_MODE_AUTHORIZED_READY,
                    "candidates": [rec],
                },
                sample_size=1,
            )
        self.assertTrue(report["parity_pass"])


if __name__ == "__main__":
    unittest.main()
