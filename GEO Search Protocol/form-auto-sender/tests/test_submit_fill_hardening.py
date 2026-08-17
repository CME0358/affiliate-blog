"""Submit + fill compatibility hardening tests."""

import unittest

from fill_compat import HIDDEN_SYSTEM, safe_fill
from form_fill_no_submit import (
    FINAL_SUBMIT,
    NEXT_STEP_SAFE,
    _is_auxiliary_unknown_button,
    classify_button_action,
)
from message_variant import SKIP_INSUFFICIENT_CAPACITY, select_ari_message_variant


class TestSafeFill(unittest.TestCase):
    def test_hidden_field_not_filled(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(
                '<form>'
                '<input type="hidden" name="trap" value="">'
                '<input type="text" name="visible" id="vis">'
                '</form>'
            )
            ok, reason = page.evaluate(
                """async () => {
                  const mod = await import('data:text/javascript,');
                  return [false, 'sync'];
                }"""
            )
            browser.close()
        # async safe_fill tested via sync wrapper below
        import asyncio

        async def _run():
            from playwright.async_api import async_playwright
            async with async_playwright() as ap:
                browser = await ap.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(
                    '<form>'
                    '<input type="hidden" name="trap" value="">'
                    '<input type="text" name="visible" id="vis">'
                    '</form>'
                )
                h_ok, h_reason = await safe_fill(page, 'input[name="trap"]', "x")
                v_ok, _ = await safe_fill(page, "#vis", "hello")
                await browser.close()
                return h_ok, h_reason, v_ok

        h_ok, h_reason, v_ok = asyncio.run(_run())
        self.assertFalse(h_ok)
        self.assertEqual(h_reason, HIDDEN_SYSTEM)
        self.assertTrue(v_ok)

    def test_honeypot_offscreen_skipped(self):
        import asyncio

        async def _run():
            from playwright.async_api import async_playwright
            async with async_playwright() as ap:
                browser = await ap.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(
                    '<form>'
                    '<input type="text" name="website" style="display:none">'
                    '<input type="text" name="email" id="em">'
                    '</form>'
                )
                h_ok, h_reason = await safe_fill(page, 'input[name="website"]', "spam")
                e_ok, _ = await safe_fill(page, "#em", "a@b.co")
                await browser.close()
                return h_ok, e_ok

        h_ok, e_ok = asyncio.run(_run())
        self.assertFalse(h_ok)
        self.assertTrue(e_ok)


class TestSubmitClassification(unittest.TestCase):
    def test_auxiliary_zip_button(self):
        self.assertTrue(_is_auxiliary_unknown_button({"label": "住所検索 zip2addr", "className": "zip2addr"}))

    def test_pre_action_is_next_on_input_page(self):
        self.assertEqual(
            classify_button_action(
                "submit form_submit",
                "submit",
                form_action="https://example.com/estimate/pre/",
                page_url="https://example.com/estimate/",
                class_name="form_submit",
            ),
            NEXT_STEP_SAFE,
        )

    def test_submitconfirm_is_next(self):
        self.assertEqual(
            classify_button_action(
                "submit submitconfirm",
                "submit",
                name="submitConfirm",
                form_action="https://example.com/contact/confirm",
                page_url="https://example.com/contact/",
            ),
            NEXT_STEP_SAFE,
        )

    def test_form_submit_id_final_single_step(self):
        self.assertEqual(
            classify_button_action(
                "submit form_submit",
                "submit",
                el_id="form_submit",
                form_action="https://example.com/contact",
                page_url="https://example.com/contact",
            ),
            FINAL_SUBMIT,
        )

    def test_confirm_page_submit_is_final(self):
        self.assertEqual(
            classify_button_action(
                "送信 commit",
                "submit",
                name="commit",
                form_action="https://example.com/contacts/confirm",
                page_url="https://example.com/contacts/confirm",
            ),
            FINAL_SUBMIT,
        )


class TestPrefectureAddressSeparation(unittest.TestCase):
    def test_select_prefecture_not_address_field(self):
        from form_field_resolver import _sanitize_resolved_fields

        fields = {
            "prefecture_field": 'select[name="pref"]',
            "address_field": 'select[name="pref"]',
        }
        cleaned = _sanitize_resolved_fields(fields)
        self.assertIsNone(cleaned["address_field"])
        self.assertEqual(cleaned["prefecture_field"], 'select[name="pref"]')

    def test_japanese_name_field_resolved(self):
        from playwright.sync_api import sync_playwright
        from form_field_resolver import _EXTRACT_FIELDS_JS, _fields_usable

        html = """
        <form id="mailform">
          <input type="text" name="お名前(必須)">
          <input type="text" name="email(必須)">
          <input type="text" name="電話番号">
          <textarea name="msg"></textarea>
        </form>
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(html)
            result = page.evaluate(_EXTRACT_FIELDS_JS)
            browser.close()
        self.assertIn("お名前", result.get("name_field") or "")
        self.assertTrue(_fields_usable(result))


class TestMessageCapacity(unittest.TestCase):
    def test_maxlength_under_300_form_not_suitable(self):
        sel = select_ari_message_variant("https://example.com/lp", 20)
        self.assertTrue(sel.skipped)
        self.assertEqual(sel.skip_reason, SKIP_INSUFFICIENT_CAPACITY)


if __name__ == "__main__":
    unittest.main()
