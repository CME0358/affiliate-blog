"""High-yield source scoring tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from ari_pipeline.high_yield_source_scoring import (
    READY_PRIORITY_A,
    READY_PRIORITY_B,
    SLOW_PATH,
    build_high_yield_signatures,
    score_source_candidate,
    tier_counts,
)
from ari_pipeline.night_factory import build_source_pool


class TestHighYieldScoring(unittest.TestCase):
    def test_signatures_shape(self):
        sigs = build_high_yield_signatures()
        self.assertIn("known_contact_url", sigs)
        self.assertIn("historical_framework_weights", sigs)

    def test_priority_a_known_contact(self):
        c = {
            "domain": "example-re.jp",
            "website_url": "https://example-re.jp/",
            "lw_entry_url": "https://example-re.jp/contact/",
            "industry_name": "不動産",
            "company_name": "Example Estate",
        }
        hs = score_source_candidate(c)
        self.assertEqual(hs.tier, READY_PRIORITY_A)
        self.assertGreaterEqual(hs.score, 220)

    def test_slow_path_captcha_fast(self):
        c = {
            "domain": "bad.example.jp",
            "website_url": "https://bad.example.jp/",
            "industry_name": "不動産",
        }
        cp = {"fast_http_results": {"bad.example.jp": {"outcome": "CAPTCHA"}}}
        hs = score_source_candidate(c, cp=cp)
        self.assertEqual(hs.tier, SLOW_PATH)

    def test_pool_tiers_populated(self):
        pool = build_source_pool()
        tiers = tier_counts(pool)
        self.assertGreater(tiers.get(READY_PRIORITY_A, 0), 100)
        self.assertGreater(tiers.get(READY_PRIORITY_B, 0), 100)


if __name__ == "__main__":
    unittest.main()
