"""Multi-step validation + form scope hardening tests."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from form_fill_no_submit import (
    BACK,
    FINAL_SUBMIT,
    NEXT_STEP_SAFE,
    _audit_buttons,
    _click_safe_next,
    _is_search_form_button,
    pick_final_submit_button,
)
from form_scope import is_search_form_meta, PICK_CONTACT_FORM_JS
from multistep_state import (
    CONFIRMATION,
    FINAL_SUBMIT_READY,
    VALIDATION_FAILED,
    detect_multistep_state,
    run_validation_feedback_once,
)
from preflight_classifier import classify_preflight
from required_choice_resolver import (
    CUSTOMER_TYPE,
    INQUIRY_CATEGORY,
    SERVICE_TYPE,
    UNSUITABLE_REQUIRED_CHOICE,
    classify_choice_group,
    resolve_rational_choice,
)
from submission_state import FORM_NOT_SUITABLE


class TestFormScope(unittest.TestCase):
    def test_search_form_meta_action_s(self):
        self.assertTrue(is_search_form_meta({"action": "/?s=", "id": ""}))
        self.assertTrue(is_search_form_meta({"action": "/?s=foo", "id": ""}))

    def test_search_form_button_excluded(self):
        btn = {"name": "s", "formAction": "/?s=", "formId": "keni_search"}
        self.assertTrue(_is_search_form_button(btn))

    def test_contact_form_preferred_over_search(self):
        html = """
        <form id="keni_search" action="/?s=" class="searchform">
          <input type="search" name="s"><input type="submit" name="search" value="検索">
        </form>
        <form id="contact" action="/contact/">
          <input name="name"><input type="email" name="email"><textarea name="message"></textarea>
          <input type="submit" name="submitConfirm" value="確認">
        </form>
        """
        import asyncio

        async def _run():
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(html)
                picked = await page.evaluate(PICK_CONTACT_FORM_JS)
                await browser.close()
                return picked

        picked = asyncio.run(_run())
        self.assertIsNotNone(picked)
        self.assertEqual(picked.get("id"), "contact")
        self.assertTrue(picked.get("hasTextarea"))


class TestRequiredChoiceResolver(unittest.TestCase):
    def test_inquiry_category_other(self):
        group = {
            "kind": "radio",
            "name": "mailToNum",
            "context": "お問い合わせ種類",
            "required": True,
            "options": [
                {"label": "見積依頼", "value": "1"},
                {"label": "その他", "value": "9"},
            ],
        }
        self.assertEqual(classify_choice_group(group), INQUIRY_CATEGORY)
        opt, cat, status = resolve_rational_choice(group)
        self.assertEqual(status, "selected")
        self.assertIn("その他", opt.get("label", ""))

    def test_customer_type_corporate(self):
        group = {
            "kind": "radio",
            "name": "type_s",
            "context": "法人 個人",
            "required": True,
            "options": [
                {"label": "個人", "value": "1"},
                {"label": "法人", "value": "2"},
            ],
        }
        self.assertEqual(classify_choice_group(group), CUSTOMER_TYPE)
        opt, _, status = resolve_rational_choice(group)
        self.assertEqual(status, "selected")
        self.assertIn("法人", opt.get("label", ""))

    def test_single_checkbox_other_selected(self):
        group = {
            "kind": "checkbox",
            "name": "form_reform_7",
            "context": "form_reform_7 その他",
            "required": False,
            "options": [{"label": "その他", "value": "other"}],
        }
        opt, cat, status = resolve_rational_choice(group)
        self.assertEqual(status, "selected")
        self.assertIn("その他", opt.get("label", ""))
        group = {
            "kind": "checkbox",
            "name": "form_reform[]",
            "context": "リフォーム箇所 必須",
            "required": True,
            "options": [
                {"label": "キッチン", "value": "kitchen"},
                {"label": "浴室", "value": "bath"},
            ],
        }
        self.assertEqual(classify_choice_group(group), SERVICE_TYPE)
        _, cat, status = resolve_rational_choice(group)
        self.assertEqual(status, "unsuitable")
        self.assertEqual(cat, UNSUITABLE_REQUIRED_CHOICE)

    def test_unsuitable_preflight_classification(self):
        pf = {
            "fill_no_submit": {
                "status": "skipped",
                "reason": "unsuitable_required_choices",
                "required_choices": {"unsuitable": [{"name": "form_reform[]"}]},
                "field_map": {},
            }
        }
        cls, reason, _ = classify_preflight(pf)
        self.assertEqual(cls, FORM_NOT_SUITABLE)
        self.assertIn("unsuitable_required", reason)


class TestMultistepState(unittest.TestCase):
    def test_confirmation_dom_detection(self):
        html = "<html><body><h1>入力内容の確認</h1><button>戻る</button><input type='submit' value='送信する'></body></html>"
        self.assertEqual(detect_multistep_state(html), FINAL_SUBMIT_READY)

    def test_validation_failed_detection(self):
        html = "<html><body><p>必須項目です</p><input aria-invalid='true'></body></html>"
        self.assertEqual(detect_multistep_state(html), VALIDATION_FAILED)

    def test_validation_feedback_max_one_retry(self):
        async def _run():
            page = AsyncMock()
            page.evaluate = AsyncMock(
                side_effect=[
                    VALIDATION_FAILED,
                    [],
                    {"applied": [], "skipped": [], "unsuitable": []},
                    CONFIRMATION,
                ]
            )
            log = {}
            with patch(
                "required_choice_resolver.apply_rational_required_choices",
                new=AsyncMock(return_value={"applied": [], "skipped": [], "unsuitable": []}),
            ):
                r1 = await run_validation_feedback_once(page, log)
                r2 = await run_validation_feedback_once(page, log)
            return r1, r2, log

        r1, r2, log = asyncio.run(_run())
        self.assertTrue(r1.get("retried"))
        self.assertEqual(log.get("validation_retry"), {"applied": [], "skipped": [], "unsuitable": []})
        self.assertFalse(r2.get("retried"))


class TestButtonScope(unittest.TestCase):
    def test_audit_excludes_search_submit(self):
        async def _run():
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(
                    """
                    <form id="keni_search" action="/?s=">
                      <input name="s"><input type="submit" name="search" value="検索">
                    </form>
                    <form id="contact">
                      <textarea name="msg"></textarea>
                      <input type="submit" name="submitConfirm" value="確認画面へ">
                    </form>
                    """
                )
                scoped = await _audit_buttons(page, "form#contact")
                await browser.close()
                return scoped

        buttons = asyncio.run(_run())
        names = [b.get("name") for b in buttons]
        self.assertNotIn("search", names)
        self.assertIn("submitConfirm", names)

    def test_back_and_final_coexist(self):
        buttons = [
            {"label": "戻る", "classification": BACK},
            {"label": "送信する", "classification": FINAL_SUBMIT},
        ]
        btn, err = pick_final_submit_button(buttons)
        self.assertIsNotNone(btn)
        self.assertEqual(err, "")

    def test_final_submit_not_clicked_in_dry_phase(self):
        async def _run():
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(
                    '<form id="contact">'
                    '<input type="submit" name="submitConfirm" value="確認画面へ">'
                    '</form>'
                )
                buttons = await _audit_buttons(page, "form#contact")
                ok, _ = await _click_safe_next(page, buttons, "form#contact")
                clicked_final = await page.evaluate(
                    "() => document.querySelector('[name=final]') !== null"
                )
                await browser.close()
                return ok, clicked_final

        ok, clicked_final = asyncio.run(_run())
        self.assertTrue(ok)
        self.assertFalse(clicked_final)


if __name__ == "__main__":
    unittest.main()
