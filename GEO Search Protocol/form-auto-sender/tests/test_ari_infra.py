"""Tests for ARI end-of-day infrastructure (no production sends)."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from ari_pipeline.limits import AriDailyLimits, load_limits
from ari_pipeline.orchestrator import Stage, dry_run_stage, init_orchestrator_from_pool
from ari_pipeline.status_integrity import (
    audit_duplicate_sent_rows,
    count_official_confirmed_sent,
    get_official_kpi_source_doc,
)
from ari_pipeline.conversion_tracking import REPLY_CLASSIFICATIONS, schema_document
from ari_pipeline.forensic_queue import build_forensic_queue
from automation_state import is_paused


class TestOfficialKpi(unittest.TestCase):
    def test_kpi_doc_says_not_raw_row_count(self):
        doc = get_official_kpi_source_doc()
        self.assertIn("CONFIRMED_SENT", doc)
        self.assertIn("NOT used: raw sent.csv row count", doc)

    def test_official_count_le_raw_rows(self):
        from ari_pipeline.status_integrity import count_raw_sent_rows
        self.assertLessEqual(count_official_confirmed_sent(), count_raw_sent_rows())


class TestLimits(unittest.TestCase):
    def test_production_limit_zero_tonight(self):
        lim = AriDailyLimits(production_limit=0, production_enabled=False)
        self.assertEqual(lim.production_limit, 0)
        self.assertFalse(lim.production_enabled)

    def test_daily_candidate_limit_500(self):
        lim = AriDailyLimits()
        self.assertEqual(lim.daily_candidate_limit, 500)


class TestOrchestrator(unittest.TestCase):
    def test_dry_run_stops_before_production(self):
        pool = {
            "pool_date": "2026-08-12-test",
            "candidates": [
                {
                    "candidate_id": "abc",
                    "company_name": "Test Co",
                    "domain": "example.com",
                    "website_url": "https://example.com/",
                    "industry_name": "工務店",
                    "area_name": "東京都",
                }
            ],
        }
        state = init_orchestrator_from_pool(pool, run_id="test_run")
        for stage in Stage:
            state = dry_run_stage(state, stage)
            if stage == Stage.PRODUCTION_ELIGIBLE:
                break
        self.assertTrue(state.get("production_blocked"))

    def test_idempotent_stage_skip_completed(self):
        pool = {"pool_date": "t", "candidates": [{
            "candidate_id": "x", "company_name": "A", "domain": "a.com",
            "website_url": "https://a.com", "industry_name": "リフォーム", "area_name": "東京",
        }]}
        state = init_orchestrator_from_pool(pool, run_id="idempotent_test")
        state = dry_run_stage(state, Stage.LOCAL_FILTER)
        before = state["stats"]["processed"]
        state = dry_run_stage(state, Stage.LOCAL_FILTER)
        self.assertEqual(state["stats"]["processed"], before)


class TestForensicQueue(unittest.TestCase):
    def test_no_auto_retry(self):
        q = build_forensic_queue()
        for item in q["items"]:
            self.assertFalse(item.get("auto_retry"))
            self.assertTrue(item.get("requires_manual_decision"))

    def test_known_cases_present(self):
        q = build_forensic_queue()
        domains = {i.get("domain") for i in q["items"]}
        self.assertIn("daiichi-jyusetu.co.jp", domains)
        self.assertIn("mizoihome.com", domains)


class TestConversionSchema(unittest.TestCase):
    def test_funnel_stages(self):
        s = schema_document()
        self.assertIn("CONFIRMED_SENT", s["funnel"])
        self.assertIn("Purchase", s["funnel"])

    def test_reply_classifications(self):
        self.assertIn("MEETING_REQUEST", REPLY_CLASSIFICATIONS)


class TestDuplicateAudit(unittest.TestCase):
    def test_audit_does_not_delete_sent_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            sent = log_dir / "sent.csv"
            sent.write_text(
                "date,company_name,industry_name,area_name,website_url,form_url,lp_url,place_id,status\n"
                "2026-08-11,CoA,,,https://a.com/,,,,sent\n"
                "2026-08-11,CoA,,,https://a.com/,,,,sent\n",
                encoding="utf-8",
            )
            audit_path = log_dir / "sent_row_audit.csv"
            import ari_pipeline.status_integrity as si
            orig_sent = si.LOG_SENT
            orig_audit = si.LOG_SENT_ROW_AUDIT
            si.LOG_SENT = sent
            si.LOG_SENT_ROW_AUDIT = audit_path
            try:
                result = audit_duplicate_sent_rows(domain="a.com", batch_id="test")
                self.assertEqual(result["rows_audited"], 1)
                self.assertEqual(len(list(csv.DictReader(sent.open()))), 2)
            finally:
                si.LOG_SENT = orig_sent
                si.LOG_SENT_ROW_AUDIT = orig_audit


class TestCountReconciliation(unittest.TestCase):
    def test_sent_domain_index_confirmed_matches_official(self):
        from ari_pipeline.sent_domain_index import get_sent_domain_index

        get_sent_domain_index.cache_clear()
        idx = get_sent_domain_index()
        self.assertEqual(idx.effective_confirmed_sent, count_official_confirmed_sent())
        self.assertLessEqual(idx.effective_confirmed_sent, idx.raw_sent_rows)

    def test_sent_domain_index_cache_stale_after_sent_csv_append(self):
        """Regression: batch runner must not read cached index after append_sent_csv_row."""
        import ari_pipeline.sent_domain_index as sdi
        import ari_pipeline.status_integrity as si
        import config
        import log_manager as lm
        from ari_pipeline.sent_domain_index import get_sent_domain_index

        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            sent_path = log_dir / "sent.csv"
            orig_log_dir = config.LOG_DIR
            orig_sent = lm.LOG_SENT
            orig_sdi_sent = sdi.LOG_SENT
            orig_si_sent = si.LOG_SENT
            try:
                config.LOG_DIR = log_dir
                lm.LOG_DIR = log_dir
                lm.LOG_SENT = sent_path
                sdi.LOG_SENT = sent_path
                si.LOG_SENT = sent_path
                lm._ensure_sent_csv()

                get_sent_domain_index.cache_clear()
                before = get_sent_domain_index().effective_confirmed_sent

                lm.append_sent_csv_row(
                    {"company_name": "Cache Test Co", "website_url": "https://cache-test.example/"},
                    {"status": "sent"},
                )

                stale = get_sent_domain_index().effective_confirmed_sent
                get_sent_domain_index.cache_clear()
                fresh = count_official_confirmed_sent()

                self.assertEqual(before, 0)
                self.assertEqual(stale, 0)
                self.assertEqual(fresh, 1)
            finally:
                get_sent_domain_index.cache_clear()
                config.LOG_DIR = orig_log_dir
                lm.LOG_DIR = orig_log_dir
                lm.LOG_SENT = orig_sent
                sdi.LOG_SENT = orig_sdi_sent
                si.LOG_SENT = orig_si_sent

    def test_exclusion_categories_not_legacy_confirmed_sent(self):
        from ari_pipeline.candidate_pool import _classify_exclusion

        ex, reason = _classify_exclusion({
            "company_name": "Test",
            "website_url": "https://lifew.co.jp/",
            "industry_name": "リフォーム",
        })
        self.assertTrue(ex)
        self.assertEqual(reason, "EFFECTIVE_CONFIRMED_SENT")


class TestSafety(unittest.TestCase):
    def test_automation_paused(self):
        self.assertTrue(is_paused("form-auto-sender"))


if __name__ == "__main__":
    unittest.main()
