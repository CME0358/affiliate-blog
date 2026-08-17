"""Jimdo / cookie-overlay submit detection hardening tests."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from cookie_banner import cookie_overlay_likely
from form_fill_no_submit import FINAL_SUBMIT, classify_button_action, pick_final_submit_button
from form_sender import _is_usable_submit_selector


class TestSubmitSelectorValidation(unittest.TestCase):
    def test_rejects_generic_input_button(self):
        self.assertFalse(_is_usable_submit_selector("input"))
        self.assertFalse(_is_usable_submit_selector("button"))
        self.assertFalse(_is_usable_submit_selector(""))

    def test_accepts_form_scoped_submit(self):
        self.assertTrue(_is_usable_submit_selector("form.cc-m-form input[type='submit']"))
        self.assertTrue(_is_usable_submit_selector("#contact-submit"))


class TestJimdoButtonClassification(unittest.TestCase):
    def test_jimdo_submit_value_classified_final(self):
        self.assertEqual(classify_button_action("送信", "submit"), FINAL_SUBMIT)

    def test_generic_button_text_send(self):
        self.assertEqual(classify_button_action("send", "submit"), FINAL_SUBMIT)

    def test_pick_final_from_jimdo_audit_shape(self):
        buttons = [
            {
                "label": "送信",
                "type": "submit",
                "selector": "form.cc-m-form input[type=\"submit\"]",
                "classification": FINAL_SUBMIT,
            }
        ]
        btn, err = pick_final_submit_button(buttons)
        self.assertIsNotNone(btn)
        self.assertEqual(err, "")

    def test_no_final_submit_fails_pick(self):
        buttons = [{"label": "次へ", "type": "button", "classification": "NEXT_STEP_SAFE"}]
        btn, err = pick_final_submit_button(buttons)
        self.assertIsNone(btn)
        self.assertIn("not_found", err)


class TestCookieOverlayHeuristic(unittest.TestCase):
    def test_detects_jimdo_cookie_markup(self):
        html = '<div id="cookie-settings"><button id="cookie-settings-all">同意</button></div>'
        self.assertTrue(cookie_overlay_likely(html))

    def test_plain_form_no_cookie(self):
        self.assertFalse(cookie_overlay_likely("<form><input type='submit'></form>"))


class TestCookieDismissIntegration(unittest.TestCase):
    def test_prepare_submit_surface_calls_dismiss(self):
        async def _run():
            from form_sender import _prepare_submit_surface

            page = MagicMock()
            with patch("cookie_banner.dismiss_cookie_banner", new_callable=AsyncMock) as dismiss:
                dismiss.return_value = True
                await _prepare_submit_surface(page)
                dismiss.assert_awaited_once_with(page)

        asyncio.run(_run())

    def test_click_submit_without_cookie_dismiss_still_prepares(self):
        async def _run():
            from form_sender import _click_submit, set_submit_forbidden

            set_submit_forbidden(True)
            page = MagicMock()
            with patch("form_sender._prepare_submit_surface", new_callable=AsyncMock):
                ok, reason, _ = await _click_submit(page, {})
                self.assertFalse(ok)
                self.assertEqual(reason, "submit_forbidden_detect_only")

        asyncio.run(_run())


class TestJimdoSubmitLiveNoSend(unittest.TestCase):
    """Live Jimdo page — fill + detect only (POST blocked)."""

    def test_seiren_fill_no_submit_ready_with_cookie_overlay(self):
        async def _run():
            from consent_detector import CONSENT_DETECT_AND_FILL_JS
            from form_field_resolver import resolve_form_fields
            from form_fill_no_submit import _audit_buttons, _fill_standard_fields, pick_final_submit_button
            from form_finder import NAV_TIMEOUT, _goto_settled
            from form_sender import _click_submit, set_submit_forbidden
            from message_variant import resolve_ari_message_for_form
            from message_builder import build_lp_url
            from parser import parse_md_file

            batch = _BASE.parent.parent.parent / "70_outputs/5-Day-Sales-Sprint/ARI-Production-Batch-30.md"
            if not batch.exists():
                return "skip"
            company = parse_md_file(str(batch))[1]
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await (await browser.new_context(locale="ja-JP")).new_page()
                await page.route(
                    "**/*",
                    lambda route: route.abort()
                    if route.request.method == "POST"
                    else route.continue_(),
                )
                url = company.get("form_url", "")
                if not await _goto_settled(page, url, goto_timeout=NAV_TIMEOUT):
                    await browser.close()
                    return "goto_fail"
                await page.wait_for_timeout(2000)
                html = await page.content()
                fields, _ = await resolve_form_fields(page, html, page.url)
                lp = build_lp_url(company.get("industry_name", ""), company.get("area_name", ""))
                sel = await resolve_ari_message_for_form(page, fields, lp, allow_validation_fallback=False)
                await page.evaluate(CONSENT_DETECT_AND_FILL_JS)
                await _fill_standard_fields(page, fields, sel.message)
                audited = await _audit_buttons(page)
                btn, err = pick_final_submit_button(audited)
                if not btn:
                    await browser.close()
                    return f"no_final:{err}"
                set_submit_forbidden(False)
                ok, reason, meta = await _click_submit(page, fields)
                await browser.close()
                if not ok:
                    return f"click_fail:{reason}"
                if not meta.get("final_submit_clicked"):
                    return "no_final_clicked"
                return "ready"

        result = asyncio.run(_run())
        if result == "skip":
            self.skipTest("batch file missing")
        self.assertEqual(result, "ready", result)


if __name__ == "__main__":
    unittest.main()


def tearDownModule():
    """Live asyncio.run() tests must not leave the default loop closed."""
    asyncio.set_event_loop(asyncio.new_event_loop())
