"""Tests for deterministic preview video_segment classification."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_path = _BASE / "observations" / "video_segment.py"
_spec = importlib.util.spec_from_file_location("video_segment_test", _path)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

classify_video_segment = _mod.classify_video_segment
normalize_video_segment = _mod.normalize_video_segment
resolve_preview_video_asset = _mod.resolve_preview_video_asset
validate_p1_video_segment = _mod.validate_p1_video_segment

_builder_path = _BASE / "observations" / "snapshot_builder.py"
_builder_spec = importlib.util.spec_from_file_location("snapshot_builder_test", _builder_path)
assert _builder_spec and _builder_spec.loader
_builder = importlib.util.module_from_spec(_builder_spec)
_builder_spec.loader.exec_module(_builder)
public_snapshot_view = _builder.public_snapshot_view


class TestVideoSegment(unittest.TestCase):
    def test_dental(self):
        for industry in ("歯科", "矯正歯科", "インプラント専門"):
            self.assertEqual(classify_video_segment(industry), "dental")

    def test_clinic(self):
        for industry in ("美容クリニック", "AGAクリニック", "医療脱毛サロン"):
            self.assertEqual(classify_video_segment(industry), "clinic")

    def test_tax(self):
        for industry in ("税理士", "会計事務所", "公認会計士"):
            self.assertEqual(classify_video_segment(industry), "tax")

    def test_estate(self):
        for industry in ("不動産", "不動産仲介", "不動産売買"):
            self.assertEqual(classify_video_segment(industry), "estate")

    def test_membership(self):
        for industry in ("パーソナルジム", "ピラティススタジオ", "ヨガ教室", "会員制サロン"):
            self.assertEqual(classify_video_segment(industry), "membership")

    def test_default_membership_unknown(self):
        for industry in ("防水工事", "", None, "  "):
            self.assertEqual(classify_video_segment(industry), "membership")

    def test_ambiguous_not_inferred(self):
        self.assertEqual(classify_video_segment("美容・ヘルスケア"), "membership")
        self.assertEqual(classify_video_segment("医療"), "membership")

    def test_dental_before_clinic(self):
        self.assertEqual(classify_video_segment("歯科クリニック"), "dental")

    def test_normalize_legacy_generic(self):
        self.assertEqual(normalize_video_segment("generic"), "membership")
        self.assertEqual(normalize_video_segment(None), "membership")
        self.assertEqual(normalize_video_segment("estate"), "estate")

    def test_public_snapshot_view_video_segment(self):
        view = public_snapshot_view({
            "token": "t",
            "company_name": "Co",
            "url": "https://x.com",
            "industry": "その他",
            "video_segment": "tax",
            "preview": {"observations": [], "check_summary": {}},
        })
        self.assertEqual(view["video_segment"], "tax")

    def test_public_snapshot_view_legacy_generic_normalized(self):
        view = public_snapshot_view({
            "token": "t",
            "preview": {"observations": [], "check_summary": {}},
            "video_segment": "generic",
        })
        self.assertEqual(view["video_segment"], "membership")

    def test_public_snapshot_view_missing_video_segment(self):
        view = public_snapshot_view({
            "token": "t",
            "preview": {"observations": [], "check_summary": {}},
        })
        self.assertEqual(view["video_segment"], "membership")

    def test_resolve_preview_video_asset(self):
        self.assertEqual(resolve_preview_video_asset("dental"), "scene-04-booking.mov")
        self.assertEqual(resolve_preview_video_asset("clinic"), "scene-05-action.mov")
        self.assertEqual(resolve_preview_video_asset("generic"), "scene-01-ai-search.mp4")

    def test_validate_p1_dental_pass(self):
        status, reason = validate_p1_video_segment("歯科・歯医者", "dental")
        self.assertEqual(status, "PASS")
        self.assertEqual(reason, "")

    def test_validate_p1_clinic_pass(self):
        status, reason = validate_p1_video_segment("美容クリニック", "clinic")
        self.assertEqual(status, "PASS")
        self.assertEqual(reason, "")

    def test_validate_p1_membership_review(self):
        status, reason = validate_p1_video_segment("皮膚科", "membership")
        self.assertEqual(status, "REVIEW")
        self.assertIn("VIDEO_SEGMENT_MISMATCH", reason)

    def test_validate_p1_dental_wrong_segment_review(self):
        status, reason = validate_p1_video_segment("歯科", "clinic")
        self.assertEqual(status, "REVIEW")
        self.assertIn("dental", reason)


if __name__ == "__main__":
    unittest.main()
