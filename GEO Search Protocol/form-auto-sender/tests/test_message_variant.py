"""ARI メッセージ maxlength フォールバックのユニットテスト."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from automation_state import is_paused
from form_fill_no_submit import validate_ari_message
from form_sender import get_real_submission_count
from message_variant import (
    SKIP_COMPACT_EXCEEDS,
    VARIANT_COMPACT,
    VARIANT_SKIP,
    VARIANT_V1,
    build_ari_message_compact,
    build_ari_message_v1,
    select_ari_message_variant,
)

LP = "https://readiness.coaretail.com/report/"


class TestMessageVariantSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v1 = build_ari_message_v1(LP)
        cls.compact = build_ari_message_compact(LP)
        cls.v1_len = len(cls.v1)
        cls.compact_len = len(cls.compact)

    def test_case1_maxlength_larger_than_v1(self):
        sel = select_ari_message_variant(LP, self.v1_len + 100)
        self.assertEqual(sel.variant, VARIANT_V1)
        self.assertFalse(sel.skipped)
        self.assertEqual(sel.message, self.v1)

    def test_case2_maxlength_between_compact_and_v1(self):
        between = self.compact_len + 50
        self.assertLess(self.compact_len, between)
        self.assertLess(between, self.v1_len)
        sel = select_ari_message_variant(LP, between)
        self.assertEqual(sel.variant, VARIANT_COMPACT)
        self.assertEqual(sel.fallback_reason, "message_exceeds_maxlength")
        self.assertFalse(sel.skipped)

    def test_case3_maxlength_smaller_than_compact(self):
        sel = select_ari_message_variant(LP, self.compact_len - 1)
        self.assertTrue(sel.skipped)
        self.assertEqual(sel.variant, VARIANT_SKIP)
        self.assertEqual(sel.skip_reason, SKIP_COMPACT_EXCEEDS)
        self.assertEqual(sel.message, "")

    def test_case4_no_maxlength_uses_v1(self):
        sel = select_ari_message_variant(LP, None)
        self.assertEqual(sel.variant, VARIANT_V1)
        self.assertIsNone(sel.detected_maxlength)
        self.assertFalse(sel.skipped)

    def test_case5_compact_preserves_urls_signature_newlines(self):
        msg = self.compact
        self.assertIn("readiness.coaretail.com/report/", msg)
        self.assertIn("tiktok.com/@coaretail/video/7646962366919265543", msg)
        self.assertIn("合同会社コア・リテール", msg)
        self.assertIn("佐々木", msg)
        self.assertGreater(msg.count("\n"), 5)
        v = validate_ari_message(msg)
        self.assertTrue(v["pass"])
        self.assertTrue(v["tiktok_url"])

    def test_v1_unchanged(self):
        sel = select_ari_message_variant(LP, None)
        self.assertIn("SEOやMEOなどの検索上位表示", sel.message)
        self.assertIn("佐々木と申します", sel.message)

    def test_no_truncate_on_skip(self):
        sel = select_ari_message_variant(LP, 100)
        self.assertTrue(sel.skipped)
        self.assertEqual(len(sel.message), 0)


class TestMessageVariantSafety(unittest.TestCase):
    def test_automation_still_paused(self):
        self.assertTrue(is_paused("form-auto-sender"))

    def test_real_submissions_zero(self):
        self.assertEqual(get_real_submission_count(), 0)


if __name__ == "__main__":
    unittest.main()
