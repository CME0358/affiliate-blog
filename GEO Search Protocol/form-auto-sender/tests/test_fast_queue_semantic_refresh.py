"""Regression tests for Fast Queue semantic refresh eligibility — ZERO SEND."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

import run_ari_fast_path_queue_prep as queue_prep
import run_ari_fast_queue_semantic_refresh as fq_refresh
import run_ari_terminal_production as rtp
from ari_pipeline.production_queue_eligibility import (
    SEMANTIC_REFRESH_REQUIRED_ROUTE,
    assess_production_queue_eligibility,
)
from ari_pipeline.proven_pattern_library import PROVEN_FAST_PATH
from config import VAULT_ROOT
from semantic_policy import current_semantic_policy_provenance
from shared_form_prepare import SEMANTIC_EVIDENCE_SCHEMA_VERSION

OUTPUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"


def _candidate(**kw) -> dict:
    base = {
        "domain": "example.co.jp",
        "form_url": "https://example.co.jp/contact/",
        "preflight_classification": "AUTO_READY",
        "form_type": "single_step",
        "fill_no_submit": {"multistep_state": "FINAL_SUBMIT_READY", "final_submit_label": "送信"},
        "lightweight_evidence": {"form_url": "https://example.co.jp/contact/", "form_type": "single_step", "field_map": {}},
    }
    base.update(kw)
    return base


def _mock_sent_index():
    idx = MagicMock()
    idx.should_no_resend.return_value = False
    idx.is_confirmed_sent_domain.return_value = False
    return idx


def _refresh_ready_row(**kw) -> dict:
    prov = current_semantic_policy_provenance()
    sem = {
        "semantic_evidence_schema_version": SEMANTIC_EVIDENCE_SCHEMA_VERSION,
        "semantic_policy_version": prov["semantic_policy_version"],
        "semantic_policy_fingerprint": prov["semantic_policy_fingerprint"],
        "semantic_hash": "abc123def4567890",
        "canonical_snapshot": {
            "submit_target": "form input[type='submit']",
            "fields": {"email": "[name=email]", "name": "[name=name]", "message": "[name=message]"},
            "field_map": {"email": "FOUND", "name": "FOUND", "message": "FOUND"},
            "semantic_policy_version": prov["semantic_policy_version"],
            "semantic_policy_fingerprint": prov["semantic_policy_fingerprint"],
        },
    }
    row = {"refresh_outcome": "REFRESH_READY", "semantic_evidence_v2": sem, "purpose_audit": "NOT_APPLICABLE"}
    row.update(kw)
    return row


class TestProductionQueueEligibility(unittest.TestCase):
    @patch("ari_pipeline.production_queue_eligibility.is_evidence_schema_and_hash_compatible", return_value=(True, []))
    @patch("ari_pipeline.proven_pattern_library.classify_candidate")
    def test_missing_refresh_blocked(self, mock_cls, _schema):
        mock_cls.return_value = {"classification": PROVEN_FAST_PATH, "matched_pattern_id": "PAT-1", "pattern_tier": "TIER_B"}
        ok, reason, _ = assess_production_queue_eligibility(_candidate(), refresh_row=None, sent_index=_mock_sent_index())
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_refresh")

    @patch("ari_pipeline.production_queue_eligibility.is_evidence_schema_and_hash_compatible", return_value=(True, []))
    @patch("ari_pipeline.proven_pattern_library.classify_candidate")
    def test_stale_fingerprint_blocked(self, mock_cls, _schema):
        mock_cls.return_value = {"classification": PROVEN_FAST_PATH, "matched_pattern_id": "PAT-1", "pattern_tier": "TIER_B"}
        stale = _refresh_ready_row()
        stale["semantic_evidence_v2"]["semantic_policy_fingerprint"] = "deadbeef00000000"
        ok, reason, _ = assess_production_queue_eligibility(_candidate(), refresh_row=stale, sent_index=_mock_sent_index())
        self.assertFalse(ok)
        self.assertEqual(reason, SEMANTIC_REFRESH_REQUIRED_ROUTE)

    @patch("ari_pipeline.production_queue_eligibility.is_evidence_schema_and_hash_compatible", return_value=(True, []))
    @patch("ari_pipeline.proven_pattern_library.classify_candidate")
    def test_current_refresh_ready_eligible(self, mock_cls, _schema):
        mock_cls.return_value = {"classification": PROVEN_FAST_PATH, "matched_pattern_id": "PAT-1", "pattern_tier": "TIER_B"}
        ok, reason, _ = assess_production_queue_eligibility(
            _candidate(), refresh_row=_refresh_ready_row(), sent_index=_mock_sent_index(),
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "production_ready")

    @patch("ari_pipeline.production_queue_eligibility.is_evidence_schema_and_hash_compatible", return_value=(True, []))
    @patch("ari_pipeline.proven_pattern_library.classify_candidate")
    def test_incompatible_purpose_blocked(self, mock_cls, _schema):
        mock_cls.return_value = {"classification": PROVEN_FAST_PATH}
        row = _refresh_ready_row(purpose_audit="INCOMPATIBLE")
        row["semantic_evidence_v2"]["canonical_snapshot"]["choices_applied"] = [
            {"category": "INQUIRY_CATEGORY", "label": "資料請求"}
        ]
        ok, reason, _ = assess_production_queue_eligibility(_candidate(), refresh_row=row, sent_index=_mock_sent_index())
        self.assertFalse(ok)
        self.assertIn("inquiry_purpose", reason)


class TestSkipOnlyNotAttempted(unittest.TestCase):
    def test_daily_fast_results_zero_attempted(self):
        p = OUTPUT_DIR / "ARI-Fast-Production-Results-2026-08-13.json"
        if not p.exists():
            self.skipTest("daily fast results missing")
        data = json.loads(p.read_text())
        self.assertEqual(data["daily_counters"]["final_submit_attempts"], 0)
        self.assertEqual(data["real_submissions"], 0)
        attempted = sum(1 for r in data["results"] if r.get("attempted"))
        self.assertEqual(attempted, 0)

    def test_skip_only_not_in_canonical_exclusions(self):
        q = OUTPUT_DIR / "ARI-Fast-Production-Queue-2026-08-13.json"
        if not q.exists():
            self.skipTest("source queue missing")
        domains = {c["domain"] for c in json.loads(q.read_text()).get("candidates", [])}
        excluded, _ = rtp.build_canonical_exclusions()
        self.assertEqual(len(domains & excluded), 0)


class TestQueuePrepContract(unittest.TestCase):
    @patch("run_ari_fast_path_queue_prep.build_unsent_pool")
    def test_proven_without_refresh_not_in_queue(self, mock_pool):
        c = _candidate(production_queue_eligible=False, production_queue_reason="missing_refresh")
        c["fast_path_classification"] = {"classification": PROVEN_FAST_PATH}
        mock_pool.return_value = [c]
        meta = queue_prep.prepare_queues(mock_pool.return_value)
        self.assertEqual(meta["proven_fast_path_total"], 0)


class TestSourceQueueVerification(unittest.TestCase):
    def test_source_queue_135(self):
        checks = fq_refresh.verify_source_unattempted()
        self.assertEqual(checks["source_queue_count"], 135)
        self.assertEqual(checks["unique_domains"], 135)


class TestR1QueuePath(unittest.TestCase):
    def test_r1_queue_filename(self):
        from ari_pipeline.daily_fast_runner import daily_queue_path
        p = daily_queue_path("2026-08-13", revision="R1")
        self.assertTrue(str(p).endswith("ARI-Fast-Production-Queue-2026-08-13-R1.json"))

    def test_r1_rejects_duplicate_domains(self):
        import tempfile
        from pathlib import Path
        q = json.loads((OUTPUT_DIR / "ARI-Fast-Production-Queue-2026-08-13.json").read_text())
        domains = [c["domain"] for c in q.get("candidates", [])]
        refresh_results = [{"domain": d, "refresh_outcome": "REFRESH_READY", "semantic_evidence_v2": _refresh_ready_row()["semantic_evidence_v2"], "purpose_audit": "NOT_APPLICABLE"} for d in domains[:3]]
        if len(domains) < 2:
            self.skipTest("need queue")
        tmp = Path(tempfile.mkdtemp()) / "test-r1.json"
        with patch("run_ari_fast_queue_semantic_refresh.R1_QUEUE", tmp):
            meta = fq_refresh.build_r1_queue(q, refresh_results)
        self.assertEqual(meta.get("duplicate_contamination"), 0)


if __name__ == "__main__":
    unittest.main()
