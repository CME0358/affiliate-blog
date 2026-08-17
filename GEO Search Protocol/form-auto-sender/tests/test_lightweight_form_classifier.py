"""Tests for lightweight_form_classifier."""

from __future__ import annotations

import unittest

from lightweight_form_classifier import (
    LIKELY_AUTO_READY,
    LIKELY_NOT_READY,
    LW_FORM_NOT_SUITABLE,
    LW_MANUAL_INTERVENTION,
    PREFLIGHT_CANDIDATE,
    classify_lightweight,
    is_proven_segment,
    pool_segment_score,
    score_lightweight,
)


class TestLightweightClassifier(unittest.TestCase):
    def test_likely_auto_ready_high_confidence(self):
        det = {
            "form_type": "FORM_FOUND",
            "form_url": "https://example.com/contact",
            "captcha": False,
            "confidence": "HIGH",
            "submit_label": "送信する",
            "field_map": {
                "email": "FOUND",
                "message": "FOUND",
                "name": "FOUND",
                "phone": "FOUND",
                "consent": "FOUND",
            },
        }
        cls, reason, _ = classify_lightweight(det)
        self.assertEqual(cls, LIKELY_AUTO_READY)
        self.assertEqual(reason, "")

    def test_preflight_candidate_missing_email_message(self):
        """JS/dynamic fields — preflight へ進める。"""
        det = {
            "form_type": "MULTI_STEP",
            "form_url": "https://example.com/contact",
            "captcha": False,
            "confidence": "LOW",
            "submit_label": "確認する",
            "field_map": {
                "email": "MISSING",
                "message": "MISSING",
                "name": "FOUND",
            },
        }
        cls, reason, _ = classify_lightweight(det)
        self.assertEqual(cls, PREFLIGHT_CANDIDATE)
        self.assertIn("preflight_worthy", reason)

    def test_manual_intervention_captcha(self):
        det = {"form_type": "CAPTCHA", "captcha": True, "field_map": {}}
        cls, reason, _ = classify_lightweight(det)
        self.assertEqual(cls, LW_MANUAL_INTERVENTION)

    def test_form_not_suitable_external(self):
        det = {
            "form_type": "EXTERNAL_FORM",
            "form_url": "https://forms.gle/abc",
            "external_provider": "forms.gle",
            "field_map": {},
        }
        cls, _, _ = classify_lightweight(det)
        self.assertEqual(cls, LW_FORM_NOT_SUITABLE)

    def test_likely_not_ready_no_form_url(self):
        det = {"form_type": "NO_FORM", "form_url": None, "failure_reason": "no_form"}
        cls, _, _ = classify_lightweight(det)
        self.assertEqual(cls, LIKELY_NOT_READY)

    def test_proven_segment_priority(self):
        reform_taito = {
            "industry_name": "リフォーム・リノベーション",
            "area_name": "東京都台東区",
            "company_name": "テスト工務",
            "review_count": 15,
        }
        self.assertTrue(is_proven_segment(reform_taito))
        self.assertGreater(pool_segment_score(reform_taito)[0], pool_segment_score({
            "industry_name": "リフォーム・リノベーション",
            "area_name": "東京都新宿区",
            "company_name": "テスト",
            "review_count": 15,
        })[0])

    def test_preflight_candidate_scores_higher_than_not_ready(self):
        det = {
            "form_type": "FORM_FOUND",
            "form_url": "https://example.com/contact",
            "captcha": False,
            "submit_label": "送信",
            "field_map": {"email": "MISSING", "message": "MISSING"},
        }
        cls, _, _ = classify_lightweight(det)
        self.assertEqual(cls, PREFLIGHT_CANDIDATE)
        company = {"industry_name": "外壁塗装", "area_name": "東京都足立区", "review_count": 10}
        self.assertGreater(score_lightweight(det, cls, company), score_lightweight(det, LIKELY_NOT_READY, company))


if __name__ == "__main__":
    unittest.main()
