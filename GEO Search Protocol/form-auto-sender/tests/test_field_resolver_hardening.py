"""Field resolver hardening — confidence scoring, scope, failure classification."""

import unittest

from form_field_resolver import (
    _EXTRACT_FIELDS_JS,
    _fields_usable,
    classify_form_analysis_failure,
)
from message_variant import (
    MIN_MESSAGE_CAPACITY,
    SKIP_INSUFFICIENT_CAPACITY,
    select_ari_message_variant,
)


class TestExtractFieldsJS(unittest.TestCase):
    def test_js_parses_without_syntax_error(self):
        from playwright.sync_api import sync_playwright

        html = """
        <form class="wpcf7-form">
          <input name="your-name" type="text" aria-label="お名前">
          <input name="your-email" type="email" aria-label="メールアドレス">
          <input name="your-tel" type="tel" aria-label="お電話番号">
          <textarea name="your-message" aria-label="お問い合わせ詳細"></textarea>
          <input type="submit" value="送信">
        </form>
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(html)
            result = page.evaluate(_EXTRACT_FIELDS_JS)
            browser.close()

        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("email_field"))
        self.assertTrue(result.get("name_field"))
        self.assertTrue(result.get("message_field"))
        self.assertTrue(result.get("phone_field"))
        self.assertTrue(_fields_usable(result))

    def test_zip_not_mapped_to_phone(self):
        from playwright.sync_api import sync_playwright

        html = """
        <form id="contact-form">
          <input name="zipcode" type="text" placeholder="郵便番号">
          <input name="tel" type="tel" placeholder="電話番号">
          <textarea name="comment"></textarea>
          <input name="email" type="email">
          <input name="name" type="text">
        </form>
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(html)
            result = page.evaluate(_EXTRACT_FIELDS_JS)
            browser.close()

        phone = result.get("phone_field") or ""
        self.assertIn("tel", phone.lower())
        self.assertNotIn("zip", phone.lower())

    def test_search_form_excluded_from_contact_form(self):
        from playwright.sync_api import sync_playwright

        html = """
        <form class="search-form"><input name="s" type="search" placeholder="検索"></form>
        <form class="wpcf7-form">
          <input name="your-email" type="email">
          <input name="your-name" type="text">
          <textarea name="your-message"></textarea>
        </form>
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(html)
            result = page.evaluate(_EXTRACT_FIELDS_JS)
            browser.close()

        email = result.get("email_field") or ""
        self.assertIn("your-email", email)

    def test_alternate_naming_cf7_and_comment(self):
        from playwright.sync_api import sync_playwright

        html = """
        <form>
          <input name="name" type="text" aria-label="必須ご担当者名">
          <input name="email" type="text" aria-label="必須メールアドレス">
          <input name="tel" type="text" placeholder="電話番号">
          <textarea name="comment" placeholder="お問い合わせ内容"></textarea>
        </form>
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(html)
            result = page.evaluate(_EXTRACT_FIELDS_JS)
            browser.close()

        self.assertTrue(_fields_usable(result))
        self.assertIn("comment", result.get("message_field", ""))


class TestFailureClassification(unittest.TestCase):
    def test_email_not_found(self):
        partial = {"name_field": "#n"}
        self.assertEqual(
            classify_form_analysis_failure(partial),
            "email_field_not_found",
        )

    def test_external_iframe(self):
        self.assertEqual(
            classify_form_analysis_failure(None, iframe_detected=True),
            "external_iframe",
        )


class TestMessageCapacity(unittest.TestCase):
    def test_maxlength_under_300_skips(self):
        sel = select_ari_message_variant("https://example.com/lp", 20)
        self.assertTrue(sel.skipped)
        self.assertEqual(sel.skip_reason, SKIP_INSUFFICIENT_CAPACITY)
        self.assertLess(20, MIN_MESSAGE_CAPACITY)


if __name__ == "__main__":
    unittest.main()
