"""ARI パイロット向けユニットテスト（送信なし）."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from automation_state import is_paused
from config import LP_URL_OVERRIDE, SKIP_INDUSTRIES
from list_filter import get_config_exclusion_label
from message_builder import build_message
from parser import parse_md_file, _parse_filename
from url_builder import build_lp_url


class TestARIConfig(unittest.TestCase):
    def test_lp_override_points_to_readiness(self):
        self.assertIn("readiness.coaretail.com/report", LP_URL_OVERRIDE)
        self.assertNotIn("localgeo", LP_URL_OVERRIDE)

    def test_skip_industries_preserved(self):
        self.assertIn("歯科", SKIP_INDUSTRIES)
        self.assertIn("整体院", SKIP_INDUSTRIES)


class TestARIMessage(unittest.TestCase):
    def test_message_has_no_geo_legacy(self):
        msg = build_message(
            "ホワイトニング・審美歯科",
            "テスト歯科",
            "https://readiness.coaretail.com/report/",
            area_name="台東区",
        )
        self.assertIn("Agent Readiness", msg)
        self.assertIn("発見・理解・比較・推薦", msg)
        self.assertIn("readiness.coaretail.com/report/", msg)
        self.assertNotIn("localgeo", msg)
        self.assertNotIn("GEO", msg)
        self.assertNotIn("無料AI推薦スコア診断", msg)
        self.assertNotIn("ABIS", msg)

    def test_build_lp_url_uses_override(self):
        url = build_lp_url("飲食店", "台東区")
        self.assertEqual(url, LP_URL_OVERRIDE)


class TestPilotParser(unittest.TestCase):
    def test_pilot_filename_pattern(self):
        date, ind, area = _parse_filename(Path("ARI-Pilot-25.md"))
        self.assertEqual(date, "2026-08-09")
        self.assertEqual(ind, "ARI-Pilot")
        self.assertEqual(area, "東京都台東区")


class TestPilotExclusionBypass(unittest.TestCase):
    def test_whitening_would_be_excluded_without_pilot(self):
        company = {
            "company_name": "テスト",
            "industry_name": "ホワイトニング・審美歯科",
            "area_name": "台東区",
        }
        label = get_config_exclusion_label(company)
        self.assertIsNotNone(label)
        self.assertIn("歯科", label)


class TestPauseGuard(unittest.TestCase):
    def test_automation_still_paused(self):
        self.assertTrue(is_paused("form-auto-sender"))


class TestBulkGuard(unittest.TestCase):
    def test_bulk_inventory_blocked(self):
        from main import ensure_not_bulk_inventory
        from config import INPUT_DIR

        with patch("sys.exit") as mock_exit:
            with patch("builtins.print"):
                ensure_not_bulk_inventory(str(INPUT_DIR), pilot=False)
            mock_exit.assert_called_once_with(1)


class TestDetectOnly(unittest.TestCase):
    def test_submit_forbidden_blocks_click(self):
        import asyncio
        from form_sender import set_submit_forbidden, _click_submit

        set_submit_forbidden(True)
        ok, reason = asyncio.get_event_loop().run_until_complete(_click_submit(None, {}))
        self.assertFalse(ok)
        self.assertEqual(reason, "submit_forbidden_detect_only")
        set_submit_forbidden(False)

    def test_detect_only_requires_pilot_list(self):
        from main import write_detection_log
        from pathlib import Path

        sample = [{
            "company_name": "テスト社",
            "industry_name": "飲食店",
            "website_url": "https://example.com",
            "contact_page_url": "https://example.com/contact",
            "form_url": "https://example.com/contact",
            "form_type": "FORM_FOUND",
            "confidence": "HIGH",
            "captcha": False,
            "external_provider": None,
            "submit_label": "送信",
            "field_map": {"email": "FOUND", "message": "FOUND"},
            "failure_reason": "",
        }]
        path = write_detection_log(sample, "ARI-Pilot-25.md")
        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8")
        self.assertIn("FORM_FOUND", text)
        self.assertIn("実送信**: 0", text)

    def test_map_finder_form_found(self):
        from form_detector import _map_finder_to_type

        ft, _ = _map_finder_to_type(
            {"status": "found", "form_url": "https://example.com/contact"},
            "https://example.com",
        )
        self.assertEqual(ft, "FORM_FOUND")

    def test_confidence_high(self):
        from form_detector import _confidence

        self.assertEqual(
            _confidence(
                "FORM_FOUND",
                {"email": "FOUND", "message": "FOUND"},
                True,
            ),
            "HIGH",
        )


if __name__ == "__main__":
    unittest.main()
