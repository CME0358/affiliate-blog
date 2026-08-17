"""Generic inquiry-purpose semantic policy tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from inquiry_purpose_semantics import (
    INQUIRY_PURPOSE_AMBIGUOUS,
    INQUIRY_PURPOSE_COMPATIBLE,
    INQUIRY_PURPOSE_INCOMPATIBLE,
    REASON_AMBIGUOUS,
    REASON_NO_COMPATIBLE,
    audit_selected_purpose,
    classify_inquiry_purpose_option,
    resolve_inquiry_purpose_choice,
)
from preflight_classifier import FORM_NOT_SUITABLE, classify_preflight
from required_choice_resolver import INQUIRY_CATEGORY, resolve_rational_choice


def _group(*, options: list[dict], required: bool = True, context: str = "お問い合わせ種類") -> dict:
    return {
        "kind": "radio",
        "name": "purpose",
        "context": context,
        "required": required,
        "options": options,
    }


class TestInquiryPurposeClassification(unittest.TestCase):
    def test_otoiawase_compatible(self):
        cls, _ = classify_inquiry_purpose_option({"label": "お問い合わせ"})
        self.assertEqual(cls, INQUIRY_PURPOSE_COMPATIBLE)

    def test_general_inquiry_compatible(self):
        cls, rank = classify_inquiry_purpose_option({"label": "一般のお問い合わせ"})
        self.assertEqual(cls, INQUIRY_PURPOSE_COMPATIBLE)
        self.assertEqual(rank, 0)

    def test_other_compatible(self):
        cls, _ = classify_inquiry_purpose_option({"label": "その他"})
        self.assertEqual(cls, INQUIRY_PURPOSE_COMPATIBLE)

    def test_consultation_compatible(self):
        cls, _ = classify_inquiry_purpose_option({"label": "ご相談"})
        self.assertEqual(cls, INQUIRY_PURPOSE_COMPATIBLE)

    def test_shiryo_seikyu_incompatible(self):
        cls, _ = classify_inquiry_purpose_option({"label": "資料請求"})
        self.assertEqual(cls, INQUIRY_PURPOSE_INCOMPATIBLE)

    def test_mitsumori_irai_incompatible(self):
        cls, _ = classify_inquiry_purpose_option({"label": "見積依頼"})
        self.assertEqual(cls, INQUIRY_PURPOSE_INCOMPATIBLE)

    def test_raiten_yoyaku_incompatible(self):
        cls, _ = classify_inquiry_purpose_option({"label": "来店予約"})
        self.assertEqual(cls, INQUIRY_PURPOSE_INCOMPATIBLE)

    def test_saiyo_incompatible(self):
        cls, _ = classify_inquiry_purpose_option({"label": "採用について"})
        self.assertEqual(cls, INQUIRY_PURPOSE_INCOMPATIBLE)

    def test_not_equivalent_shiryo_vs_otoiawase(self):
        a, _ = classify_inquiry_purpose_option({"label": "資料請求"})
        b, _ = classify_inquiry_purpose_option({"label": "お問い合わせ"})
        self.assertNotEqual(a, b)


class TestInquiryPurposeResolution(unittest.TestCase):
    def test_mixed_selects_compatible_other(self):
        g = _group(options=[
            {"label": "見積依頼", "value": "1"},
            {"label": "その他", "value": "9"},
        ])
        opt, status, reason = resolve_inquiry_purpose_choice(g)
        self.assertEqual(status, "selected")
        self.assertIn("その他", opt.get("label", ""))
        self.assertEqual(reason, "")

    def test_only_incompatible_unsuitable(self):
        g = _group(options=[
            {"label": "資料請求", "value": "1"},
            {"label": "見積依頼", "value": "2"},
        ])
        opt, status, reason = resolve_inquiry_purpose_choice(g)
        self.assertIsNone(opt)
        self.assertEqual(status, "unsuitable")
        self.assertEqual(reason, REASON_NO_COMPATIBLE)

    def test_ambiguous_only_unsuitable(self):
        g = _group(options=[{"label": "一般", "value": "x"}])
        opt, status, reason = resolve_inquiry_purpose_choice(g)
        self.assertIsNone(opt)
        self.assertEqual(status, "unsuitable")
        self.assertEqual(reason, REASON_AMBIGUOUS)

    def test_required_no_compatible_via_resolver(self):
        g = _group(options=[{"label": "カタログ請求", "value": "c"}])
        opt, cat, status = resolve_rational_choice(g)
        self.assertIsNone(opt)
        self.assertEqual(status, "unsuitable")

    def test_prefers_general_inquiry_over_other(self):
        g = _group(options=[
            {"label": "その他", "value": "9"},
            {"label": "一般のお問い合わせ", "value": "1"},
            {"label": "お問い合わせ", "value": "2"},
        ])
        opt, status, _ = resolve_inquiry_purpose_choice(g)
        self.assertEqual(status, "selected")
        self.assertIn("一般のお問い合わせ", opt.get("label", ""))

    def test_optional_incompatible_skips(self):
        g = _group(required=False, options=[{"label": "資料請求", "value": "1"}])
        opt, status, _ = resolve_inquiry_purpose_choice(g)
        self.assertIsNone(opt)
        self.assertEqual(status, "skip")


class TestPreflightIntegration(unittest.TestCase):
    def test_inquiry_purpose_no_compatible_preflight(self):
        pf = {
            "fill_no_submit": {
                "status": "skipped",
                "reason": REASON_NO_COMPATIBLE,
                "required_choices": {
                    "unsuitable": [{"name": "purpose", "reason": REASON_NO_COMPATIBLE}],
                },
                "field_map": {},
            }
        }
        cls, reason, _ = classify_preflight(pf)
        self.assertEqual(cls, FORM_NOT_SUITABLE)
        self.assertEqual(reason, REASON_NO_COMPATIBLE)


class TestProductionAuditHelpers(unittest.TestCase):
    def test_audit_compatible_other(self):
        self.assertEqual(audit_selected_purpose("その他", category=INQUIRY_CATEGORY), "COMPATIBLE")

    def test_audit_incompatible_catalog(self):
        self.assertEqual(
            audit_selected_purpose("新コンセプト資料", context="catalog 資料"),
            "INCOMPATIBLE",
        )


if __name__ == "__main__":
    unittest.main()
