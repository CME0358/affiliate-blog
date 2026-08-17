"""Tests for deterministic observation resolver (zero send)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

# config.py は dotenv 必須のため、resolver 単体を直接ロードする
_resolver_path = _BASE / "observations" / "resolver.py"
_spec = importlib.util.spec_from_file_location("obs_resolver_test", _resolver_path)
assert _spec and _spec.loader
_resolver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_resolver)

build_check_summary = _resolver.build_check_summary
map_industry_to_form = _resolver.map_industry_to_form
resolve_observations = _resolver.resolve_observations
select_message_observations = _resolver.select_message_observations


class TestObservationResolver(unittest.TestCase):
    def test_booking_present(self):
        data = {
            "reservation_button": 20,
            "has_reservation_url": False,
            "faq": 20,
            "schema_org": 20,
            "local_business": 20,
            "site_reachable": True,
        }
        codes = [o["code"] for o in resolve_observations(data)]
        self.assertIn("OBS_BOOKING_PATH_PRESENT", codes)

    def test_booking_missing(self):
        data = {
            "reservation_button": 0,
            "has_reservation_url": False,
            "faq": 0,
            "schema_org": 0,
            "local_business": 0,
            "site_reachable": True,
        }
        codes = [o["code"] for o in resolve_observations(data)]
        self.assertIn("OBS_BOOKING_PATH_MISSING", codes)
        self.assertIn("OBS_SCHEMA_MISSING", codes)

    def test_faq_boundary_11_vs_12(self):
        weak = {"faq": 11, "schema_org": 20, "reservation_button": 20, "site_reachable": True}
        ok = {"faq": 12, "schema_org": 20, "reservation_button": 20, "site_reachable": True}
        self.assertIn("OBS_FAQ_STRUCTURE_WEAK", [o["code"] for o in resolve_observations(weak)])
        self.assertIn("OBS_FAQ_STRUCTURE_OK", [o["code"] for o in resolve_observations(ok)])

    def test_message_selection_max_two(self):
        data = {
            "reservation_button": 0,
            "has_reservation_url": False,
            "faq": 0,
            "schema_org": 0,
            "local_business": 0,
            "has_llms_txt": False,
            "site_reachable": True,
        }
        selected = select_message_observations(data)
        self.assertLessEqual(len(selected), 2)
        self.assertTrue(all(o.get("approved_copy") for o in selected))

    def test_check_summary_count(self):
        data = {
            "reservation_button": 20,
            "faq": 20,
            "schema_org": 20,
            "local_business": 20,
            "has_llms_txt": True,
            "site_reachable": True,
        }
        summary = build_check_summary(data)
        self.assertEqual(summary["total_teaser"], 23)
        self.assertGreaterEqual(summary["checked_count"], 3)
        self.assertFalse(summary["blocked"])

    def test_industry_map(self):
        self.assertEqual(map_industry_to_form("美容クリニック"), "美容・ヘルスケア")
        self.assertEqual(map_industry_to_form("パーソナルジム"), "フィットネス")
        self.assertEqual(map_industry_to_form("未知の業種"), "その他")


if __name__ == "__main__":
    unittest.main()
