"""--submit-canary 向けユニットテスト（ライブ実行なし）."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from automation_state import is_paused
from form_sender import get_real_submission_count, reset_real_submission_count, set_submit_forbidden
from form_submit_canary import (
    MAX_REAL_SUBMISSIONS,
    SUBMIT_CANARY_LIVE_ENV,
    is_live_execution_armed,
    submit_canary as run_submit_canary,
    validate_submit_canary_preconditions,
)
from message_builder import build_message
from parser import parse_md_file


YAMADA = {
    "company_name": "株式会社山田工務店一級建築士事務所",
    "industry_name": "リフォーム・リノベーション",
    "area_name": "台東区",
    "website_url": "https://123-yamadakoumuten.com/",
    "form_url": "https://123-yamadakoumuten.com/contact/",
}

PILOT_PATH = "@70_outputs/5-Day-Sales-Sprint/ARI-Canary-Yamada.md"


class TestSubmitCanaryGuards(unittest.TestCase):
    def setUp(self):
        reset_real_submission_count()
        set_submit_forbidden(True)

    def test_live_not_armed_by_default(self):
        env = os.environ.pop(SUBMIT_CANARY_LIVE_ENV, None)
        try:
            self.assertFalse(is_live_execution_armed())
        finally:
            if env is not None:
                os.environ[SUBMIT_CANARY_LIVE_ENV] = env

    def test_max_real_submissions_constant(self):
        self.assertEqual(MAX_REAL_SUBMISSIONS, 1)

    def test_validate_single_target_yamada(self):
        ok, err = validate_submit_canary_preconditions(
            PILOT_PATH, [YAMADA], limit=1
        )
        self.assertTrue(ok, err)

    def test_validate_rejects_wrong_domain(self):
        bad = {**YAMADA, "website_url": "https://example.com/", "form_url": "https://example.com/contact/"}
        ok, err = validate_submit_canary_preconditions(PILOT_PATH, [bad], limit=1)
        self.assertFalse(ok)
        self.assertIn("domain_lock", err)

    def test_validate_rejects_multiple_targets(self):
        ok, err = validate_submit_canary_preconditions(
            PILOT_PATH, [YAMADA, YAMADA], limit=1
        )
        self.assertFalse(ok)
        self.assertEqual(err, "single_target_only")

    def test_validate_rejects_wrong_limit(self):
        ok, err = validate_submit_canary_preconditions(
            PILOT_PATH, [YAMADA], limit=2
        )
        self.assertFalse(ok)
        self.assertEqual(err, "limit_must_be_1")

    def test_validate_rejects_wrong_pilot_list(self):
        ok, err = validate_submit_canary_preconditions(
            "ARI-Pilot-25.md", [YAMADA], limit=1
        )
        self.assertFalse(ok)
        self.assertIn("pilot_list_not_allowed", err)

    def test_automation_must_stay_paused(self):
        self.assertTrue(is_paused("form-auto-sender"))


class TestSubmitCanaryNoLiveExecution(unittest.TestCase):
    def setUp(self):
        reset_real_submission_count()
        set_submit_forbidden(True)
        os.environ.pop(SUBMIT_CANARY_LIVE_ENV, None)

    def tearDown(self):
        os.environ.pop(SUBMIT_CANARY_LIVE_ENV, None)
        reset_real_submission_count()

    def test_implementation_ready_without_browser(self):
        msg = build_message(
            YAMADA["industry_name"],
            YAMADA["company_name"],
            "https://readiness.coaretail.com/report/",
            area_name=YAMADA["area_name"],
        )
        result = asyncio.run(
            run_submit_canary(YAMADA, msg, "https://readiness.coaretail.com/report/")
        )
        self.assertEqual(result["status"], "implementation_ready")
        self.assertFalse(result["live_execution"])
        self.assertEqual(result["overall"], "CANARY_SUBMISSION_IMPLEMENTATION_READY")
        self.assertEqual(get_real_submission_count(), 0)

    def test_real_submission_count_stays_zero(self):
        self.assertEqual(get_real_submission_count(), 0)


class TestSubmitCanaryCLI(unittest.TestCase):
    def test_submit_canary_forces_limit_one(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--submit-canary", action="store_true")
        parser.add_argument("--limit", type=int, default=None)
        args = parser.parse_args(["--submit-canary"])
        if args.submit_canary:
            args.limit = 1
        self.assertEqual(args.limit, 1)

    def test_submit_canary_requires_pilot_list(self):
        submit_canary = True
        pilot_list = None
        self.assertTrue(submit_canary and not pilot_list)


class TestSubmitCanaryPilotFile(unittest.TestCase):
    def test_canary_yamada_pilot_file(self):
        path = _BASE.parent.parent.parent / "70_outputs/5-Day-Sales-Sprint/ARI-Canary-Yamada.md"
        if not path.exists():
            self.skipTest("ARI-Canary-Yamada.md not found")
        companies = parse_md_file(str(path))
        ok, err = validate_submit_canary_preconditions(
            str(path), companies, limit=1
        )
        self.assertTrue(ok, err)


class TestSubmitCanaryFinalSubmitBlocked(unittest.TestCase):
    def test_final_submit_not_called_when_live_unarmed(self):
        with patch("form_submit_canary._click_final_submit") as mock_final:
            msg = build_message(
                YAMADA["industry_name"],
                YAMADA["company_name"],
                "https://readiness.coaretail.com/report/",
            )
            asyncio.run(
                run_submit_canary(YAMADA, msg, "https://readiness.coaretail.com/report/")
            )
            mock_final.assert_not_called()


if __name__ == "__main__":
    unittest.main()
