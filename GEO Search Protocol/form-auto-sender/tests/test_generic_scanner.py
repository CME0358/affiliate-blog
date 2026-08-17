"""Unit tests for generic preview scanner and observations (zero send)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from observations.generic_scanner import scan_domain
from observations.generic_scan_store import MemoryGenericScanStore, reset_generic_scan_store, save_generic_scan
from observations.resolver import resolve_observations, select_message_observations

SAMPLE_HTML = """
<html><head><title>テスト法律事務所</title>
<meta name="description" content="東京で企業法務・相談を扱う法律事務所です。お問い合わせフォームからご連絡ください。">
<script type="application/ld+json">{"@context":"https://schema.org"}</script>
</head><body>
<a href="/contact">お問い合わせ</a>
<h2>よくある質問</h2><p>Q. 相談料は？</p>
<p>""" + ("サービス内容の説明。" * 200) + """</p>
</body></html>
"""


class TestGenericScanner(unittest.TestCase):
    def test_scan_success_with_mock_fetch(self):
        def fake_fetch(url, timeout=15):
            from observations.generic_scanner import FetchResult
            if url.endswith("llms.txt"):
                return FetchResult(False, 404, url, "", "404")
            return FetchResult(True, 200, url, SAMPLE_HTML)

        with patch("observations.generic_scanner._fetch", side_effect=fake_fetch):
            row = scan_domain(
                website_url="https://example-law.jp",
                domain="example-law.jp",
                industry_name="弁護士事務所",
                delay_sec=0,
            )
        self.assertTrue(row["site_reachable"])
        self.assertTrue(row["action_path_present"])
        self.assertTrue(row["faq_present"])
        self.assertTrue(row["schema_present"])
        self.assertEqual(row["evidence_source"], "generic_scan")

    def test_not_found_semantics_no_missing_wording(self):
        row = {
            "evidence_source": "generic_scan",
            "site_reachable": True,
            "action_path_scanned": True,
            "action_path_present": False,
            "faq_scanned": True,
            "faq_present": False,
            "schema_scanned": True,
            "schema_present": False,
            "service_info_scanned": True,
            "service_info_ok": False,
            "service_info_weak": True,
            "llms_txt_scanned": True,
            "has_llms_txt": False,
        }
        obs = select_message_observations(row)
        self.assertGreaterEqual(len(obs), 1)
        copies = " ".join(o["approved_copy"] for o in obs)
        self.assertNotIn("存在しません", copies)
        self.assertNotIn("対応していません", copies)
        self.assertTrue(
            "確認できませんでした" in copies
            or "見つけられませんでした" in copies
            or "可能性があります" in copies
        )

    def test_no_booking_semantics_on_generic(self):
        row = {
            "evidence_source": "generic_scan",
            "site_reachable": True,
            "action_path_scanned": True,
            "action_path_present": True,
            "faq_scanned": True,
            "faq_present": True,
            "schema_scanned": True,
            "schema_present": True,
            "service_info_scanned": True,
            "service_info_ok": True,
            "service_info_weak": False,
            "llms_txt_scanned": True,
            "has_llms_txt": False,
        }
        codes = [o["code"] for o in resolve_observations(row)]
        self.assertNotIn("OBS_BOOKING_PATH_PRESENT", codes)
        self.assertNotIn("OBS_BOOKING_PATH_MISSING", codes)
        self.assertIn("OBS_ACTION_PATH_PRESENT", codes)

    def test_reservation_regression(self):
        data = {
            "reservation_button": 20,
            "faq": 20,
            "schema_org": 20,
            "local_business": 20,
            "site_reachable": True,
        }
        codes = [o["code"] for o in resolve_observations(data)]
        self.assertIn("OBS_BOOKING_PATH_PRESENT", codes)
        self.assertNotIn("OBS_ACTION_PATH_PRESENT", codes)

    def test_generic_scan_store(self):
        reset_generic_scan_store()
        import observations.generic_scan_store as store_mod
        store_mod._STORE = MemoryGenericScanStore()
        row = {"domain": "example.co.jp", "evidence_source": "generic_scan", "site_reachable": True}
        save_generic_scan(row)
        loaded = store_mod.load_generic_scan("example.co.jp")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["domain"], "example.co.jp")


if __name__ == "__main__":
    unittest.main()
