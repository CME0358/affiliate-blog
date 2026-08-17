"""R2 dental + esthetic supply — ZERO SEND regression tests."""

from __future__ import annotations

import asyncio
import sys
import unittest
from unittest.mock import MagicMock, patch

_BASE = __import__("pathlib").Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

import run_ari_production_batch_b01 as b01
from ari_pipeline.business_inquiry_surface import assess_business_inquiry_surface
from ari_pipeline.production_queue_eligibility import assess_production_queue_eligibility
from ari_pipeline.proven_pattern_library import PROVEN_FAST_PATH, classify_candidate
from ari_pipeline.queue_evidence_contract import build_queue_authorization, terminal_consumer_eligible_offline
from ari_pipeline.r2_industry_filter import classify_r2_industry, is_remodel_industry
from inquiry_purpose_semantics import audit_selected_purpose, classify_inquiry_purpose_option
from semantic_policy import current_semantic_policy_provenance
from shared_form_prepare import SEMANTIC_EVIDENCE_SCHEMA_VERSION, compute_semantic_hash


from run_ari_r2_supply_pipeline import _r2_url_priority_score, _sort_r2_candidates


class TestUrlPriority(unittest.TestCase):
    def test_contact_url_high_priority(self):
        self.assertGreater(
            _r2_url_priority_score("https://clinic.jp/contact/"),
            _r2_url_priority_score("https://clinic.jp/"),
        )

    def test_reservation_url_deprioritized(self):
        self.assertLess(
            _r2_url_priority_score("https://clinic.jp/reserve/first"),
            _r2_url_priority_score("https://clinic.jp/"),
        )

    def test_dental_sorted_before_esthetic_at_equal_score(self):
        rows = _sort_r2_candidates([
            {"domain": "e.co.jp", "website_url": "https://e.co.jp/contact", "r2_industry_bucket": "esthetic", "company_name": "E", "area_name": "A"},
            {"domain": "d.co.jp", "website_url": "https://d.co.jp/contact", "r2_industry_bucket": "dental", "company_name": "D", "area_name": "A"},
        ])
        self.assertEqual(rows[0]["r2_industry_bucket"], "dental")


class TestR2IndustryFilter(unittest.TestCase):
    def test_dental_included(self):
        self.assertEqual(classify_r2_industry("歯科医院"), "dental")

    def test_esthetic_included(self):
        self.assertEqual(classify_r2_industry("エステサロン"), "esthetic")

    def test_remodel_excluded(self):
        self.assertTrue(is_remodel_industry("リフォーム・リノベーション"))
        self.assertIsNone(classify_r2_industry("外壁塗装"))


class TestBusinessInquirySurface(unittest.TestCase):
    def test_dental_appointment_form_excluded(self):
        ok, reason = assess_business_inquiry_surface(form_url="https://clinic.jp/reserve/first-visit")
        self.assertFalse(ok)
        self.assertEqual(reason, "patient_reservation_url")

    def test_dental_treatment_consultation_excluded(self):
        ok, reason = assess_business_inquiry_surface(form_heading="初診予約フォーム")
        self.assertFalse(ok)

    def test_esthetic_reservation_excluded(self):
        ok, _ = assess_business_inquiry_surface(page_title="カウンセリング予約")
        self.assertFalse(ok)

    def test_general_inquiry_accepted(self):
        ok, reason = assess_business_inquiry_surface(form_url="https://salon.jp/contact/", form_heading="お問い合わせ")
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_business_inquiry_accepted(self):
        ok, _ = assess_business_inquiry_surface(form_heading="法人のお問い合わせ")
        self.assertTrue(ok)


class TestInquiryPurposeDentalEsthetic(unittest.TestCase):
    def test_compatible_sonota(self):
        cls, _ = classify_inquiry_purpose_option({"label": "その他"})
        self.assertEqual(cls, "INQUIRY_PURPOSE_COMPATIBLE")

    def test_reservation_rejected(self):
        cls, _ = classify_inquiry_purpose_option({"label": "初診予約"})
        self.assertEqual(cls, "INQUIRY_PURPOSE_INCOMPATIBLE")

    def test_counseling_reservation_rejected(self):
        cls, _ = classify_inquiry_purpose_option({"label": "カウンセリング予約"})
        self.assertEqual(cls, "INQUIRY_PURPOSE_INCOMPATIBLE")

    def test_misleading_catalog_rejected(self):
        cls, _ = classify_inquiry_purpose_option({"label": "資料請求"})
        self.assertEqual(cls, "INQUIRY_PURPOSE_INCOMPATIBLE")

    def test_general_inquiry_compatible(self):
        self.assertEqual(audit_selected_purpose("一般お問い合わせ"), "COMPATIBLE")


def _mock_sent_index():
    idx = MagicMock()
    idx.should_no_resend.return_value = False
    idx.is_confirmed_sent_domain.return_value = False
    return idx


def _refresh_row(**kw) -> dict:
    prov = current_semantic_policy_provenance()
    snap = {
        "submit_target": "form input[type='submit']",
        "fields": {"email": "[name=email]", "name": "[name=name]", "message": "[name=message]"},
        "field_map": {"email": "FOUND", "name": "FOUND", "message": "FOUND"},
        "semantic_policy_version": prov["semantic_policy_version"],
        "semantic_policy_fingerprint": prov["semantic_policy_fingerprint"],
        "choices_applied": [{"category": "INQUIRY_CATEGORY", "label": "その他"}],
    }
    sem = {
        "semantic_evidence_schema_version": SEMANTIC_EVIDENCE_SCHEMA_VERSION,
        "semantic_policy_version": prov["semantic_policy_version"],
        "semantic_policy_fingerprint": prov["semantic_policy_fingerprint"],
        "semantic_hash": compute_semantic_hash(snap),
        "canonical_snapshot": snap,
    }
    row = {"refresh_outcome": "REFRESH_READY", "semantic_evidence_v2": sem, "purpose_audit": "COMPATIBLE"}
    row.update(kw)
    return row


class TestProducerConsumerParity(unittest.IsolatedAsyncioTestCase):
    @patch("run_ari_production_batch_b01.get_sent_domain_index")
    @patch("run_ari_production_batch_b01.is_already_sent", return_value=False)
    @patch("run_ari_production_batch_b01.get_effective_sent_status", return_value="not_sent")
    async def test_producer_ready_terminal_ready(self, _es, _ia, mock_idx):
        idx = MagicMock()
        idx.should_no_resend.return_value = False
        mock_idx.return_value = idx
        rr = _refresh_row(domain="dental-test.jp")
        pf = {
            "domain": "dental-test.jp",
            "fill_no_submit": {
                "field_map": {"name": "FOUND", "email": "FOUND", "message": "FOUND"},
                "final_submit_identified": True,
            },
            "preflight_classification": "NOT_READY",
            "preflight_outcome": "UNKNOWN",
        }
        pf_merged = b01._merge_refresh_v2_evidence(pf, rr)
        queue_rec = {
            "domain": "dental-test.jp",
            "company_name": "Test Dental",
            "website_url": "https://dental-test.jp/",
            "industry_name": "歯科医院",
            "production_eligibility": "production_ready",
            "queue_authorization": build_queue_authorization(
                {"domain": "dental-test.jp", "production_eligibility": "production_ready", "queue_revision": "R2"},
                rr,
            ),
        }
        with patch("ari_pipeline.production_queue_eligibility.is_evidence_schema_and_hash_compatible", return_value=(True, [])):
            with patch("ari_pipeline.proven_pattern_library.classify_candidate") as mock_cls:
                mock_cls.return_value = {"classification": PROVEN_FAST_PATH, "matched_pattern_id": "P1", "pattern_tier": "TIER_B"}
                ok, _, _ = assess_production_queue_eligibility(
                    {**pf, **queue_rec}, refresh_row=rr, sent_index=_mock_sent_index(),
                )
        self.assertTrue(ok)
        tok, _ = terminal_consumer_eligible_offline(
            queue_rec, refresh_row=rr, preflight_row=pf, classify_fn=classify_candidate, excluded_domains=set(),
        )
        self.assertTrue(tok)
        send_co = {
            "domain": "dental-test.jp",
            "company_name": "Test Dental",
            "website_url": "https://dental-test.jp/",
            "queue_authorization": queue_rec["queue_authorization"],
            "preflight_classification": "NOT_READY",
            "preflight_outcome": "UNKNOWN",
        }
        pre_ok, reason, _ = await b01._pre_send_check(send_co, pf_merged)
        self.assertTrue(pre_ok, reason)


class TestStreamingQueueRevision(unittest.TestCase):
    def test_next_revision_starts_at_a(self):
        from ari_pipeline.r2_streaming_queue import _next_revision_letter
        self.assertEqual(_next_revision_letter([]), "R2-A")

    def test_next_revision_skips_used(self):
        from ari_pipeline.r2_streaming_queue import _next_revision_letter
        self.assertEqual(_next_revision_letter(["R2-A"]), "R2-B")


class TestLaneCFilter(unittest.TestCase):
    def test_real_estate_included(self):
        from ari_pipeline.r2_lane_c_filter import lane_c_industry_tier
        self.assertEqual(lane_c_industry_tier("不動産会社"), 1)

    def test_dental_excluded(self):
        from ari_pipeline.r2_lane_c_filter import lane_c_industry_tier
        self.assertIsNone(lane_c_industry_tier("歯科医院"))

    def test_contact_url_scores_higher(self):
        from ari_pipeline.r2_lane_c_filter import lane_c_url_pattern_score
        self.assertGreater(
            lane_c_url_pattern_score("https://example.jp/contact/"),
            lane_c_url_pattern_score("https://example.jp/"),
        )

    def test_reservation_url_deprioritized(self):
        from ari_pipeline.r2_lane_c_filter import build_lane_c_pool
        pool = build_lane_c_pool([
            {"company_name": "X", "website_url": "https://move-x.jp/reserve/", "industry_name": "引越し業者", "area_name": "A"},
        ], pool_date="2026-08-13")
        self.assertEqual(pool["stats"]["pool_size"], 0)


class TestLaneBFilter(unittest.TestCase):
    def test_remodel_excluded_from_lane_b(self):
        from ari_pipeline.r2_lane_b_filter import build_lane_b_pool
        pool = build_lane_b_pool([
            {"company_name": "X", "website_url": "https://remodel-x.jp/", "industry_name": "リフォーム・リノベーション", "area_name": "A"},
        ], pool_date="2026-08-13")
        self.assertEqual(pool["stats"]["pool_size"], 0)


if __name__ == "__main__":
    unittest.main()

