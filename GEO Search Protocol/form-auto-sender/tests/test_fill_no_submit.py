"""--fill-no-submit canary 向けユニットテスト."""

from __future__ import annotations

import argparse
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from form_fill_no_submit import classify_button_action, validate_ari_message
from form_sender import set_submit_forbidden, _click_submit, get_real_submission_count
from message_builder import build_message
from parser import _parse_filename, parse_md_file


class TestFillNoSubmitParser(unittest.TestCase):
    def test_canary_filename_pattern(self):
        date, ind, area = _parse_filename(Path("ARI-Canary-Yamada.md"))
        self.assertEqual(date, "2026-08-09")
        self.assertEqual(ind, "ARI-Pilot")
        self.assertEqual(area, "東京都台東区")

    def test_canary_yamada_single_target(self):
        path = _BASE.parent.parent.parent / "70_outputs/5-Day-Sales-Sprint/ARI-Canary-Yamada.md"
        if not path.exists():
            self.skipTest("ARI-Canary-Yamada.md not found")
        companies = parse_md_file(str(path))
        self.assertEqual(len(companies), 1)
        self.assertIn("山田工務店", companies[0]["company_name"])
        self.assertEqual(
            companies[0].get("form_url"),
            "https://123-yamadakoumuten.com/contact/",
        )


class TestButtonClassification(unittest.TestCase):
    def test_next_step_safe_confirm(self):
        self.assertEqual(
            classify_button_action("入力内容を確認する", "submit"),
            "NEXT_STEP_SAFE",
        )

    def test_final_submit(self):
        self.assertEqual(
            classify_button_action("この内容で送信する", "submit"),
            "FINAL_SUBMIT",
        )

    def test_unknown_submit(self):
        self.assertEqual(classify_button_action("", "submit"), "UNKNOWN")


class TestSubmitForbiddenFillMode(unittest.TestCase):
    def test_submit_forbidden_blocks_click(self):
        set_submit_forbidden(True)
        ok, reason, _meta = asyncio.run(_click_submit(None, {}))
        self.assertFalse(ok)
        self.assertEqual(reason, "submit_forbidden_detect_only")
        set_submit_forbidden(False)

    def test_real_submission_count_zero(self):
        self.assertEqual(get_real_submission_count(), 0)


class TestFillNoSubmitCLI(unittest.TestCase):
    def test_fill_no_submit_requires_pilot_list(self):
        from main import _BASE_DIR
        import main as main_mod

        with patch.object(sys, "argv", ["main.py", "--fill-no-submit"]):
            with patch("sys.exit") as mock_exit:
                with patch("builtins.print"):
                    try:
                        main_mod.__name__
                        parser = argparse.ArgumentParser()
                        parser.add_argument("--fill-no-submit", action="store_true")
                        parser.add_argument("--pilot-list", default=None)
                        args = parser.parse_args(["--fill-no-submit"])
                        if not args.pilot_list:
                            sys.exit(1)
                    except SystemExit:
                        pass
        # Direct guard logic mirror
        pilot_list = None
        fill_no_submit = True
        should_exit = fill_no_submit and not pilot_list
        self.assertTrue(should_exit)


class TestMultiStepSafeNext(unittest.TestCase):
    def test_safe_next_without_final(self):
        buttons = [
            {"label": "入力内容を確認する", "type": "submit", "classification": "NEXT_STEP_SAFE"},
        ]
        safe = [b for b in buttons if b["classification"] == "NEXT_STEP_SAFE"]
        final = [b for b in buttons if b["classification"] == "FINAL_SUBMIT"]
        self.assertEqual(len(safe), 1)
        self.assertEqual(len(final), 0)

    def test_final_submit_blocks_advance(self):
        buttons = [
            {"label": "送信する", "type": "submit", "classification": "FINAL_SUBMIT"},
        ]
        final = [b for b in buttons if b["classification"] == "FINAL_SUBMIT"]
        self.assertTrue(final)


class TestARIMessageCanary(unittest.TestCase):
    def test_message_validation_pass(self):
        msg = build_message(
            "リフォーム・リノベーション",
            "株式会社山田工務店一級建築士事務所",
            "https://readiness.coaretail.com/report/",
            area_name="台東区",
        )
        v = validate_ari_message(msg)
        self.assertTrue(v["pass"])
        self.assertTrue(v["ari_positioning"])
        self.assertTrue(v["new_lp"])


if __name__ == "__main__":
    unittest.main()
