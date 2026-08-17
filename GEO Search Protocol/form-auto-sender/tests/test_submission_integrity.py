"""Submission integrity — detect_submission_success / field mapping."""

import unittest

from form_sender import detect_submission_success


class TestDetectSubmissionSuccess(unittest.TestCase):
    def test_confirmation_only_fails(self):
        meta = {"confirmation_reached": True, "final_submit_clicked": False, "steps_clicked": 1}
        ok, reason = detect_submission_success(
            "https://example.com/contact/",
            "https://example.com/contact/",
            "<html>入力内容の確認</html>",
            meta,
        )
        self.assertFalse(ok)
        self.assertIn("confirmation", reason)

    def test_final_submit_with_success_message(self):
        meta = {"confirmation_reached": True, "final_submit_clicked": True, "steps_clicked": 2}
        ok, reason = detect_submission_success(
            "https://example.com/contact/",
            "https://example.com/contact/",
            "<html>送信完了しました</html>",
            meta,
        )
        self.assertTrue(ok)
        self.assertIn("success", reason)

    def test_final_submit_url_change_confirmation_page(self):
        meta = {"confirmation_reached": True, "final_submit_clicked": True, "steps_clicked": 2}
        ok, reason = detect_submission_success(
            "https://example.com/contact-confirmation/",
            "https://example.com/contact/",
            "<html><body>確認</body></html>",
            meta,
        )
        self.assertFalse(ok)
        self.assertIn("confirmation", reason)

    def test_same_url_final_click_no_success_fails(self):
        meta = {"confirmation_reached": True, "final_submit_clicked": True, "steps_clicked": 2}
        ok, reason = detect_submission_success(
            "https://example.com/contact/",
            "https://example.com/contact/",
            "<html>入力内容の確認</html>",
            meta,
        )
        self.assertFalse(ok)
        self.assertIn("success", reason.lower())

    def test_single_step_assumed_final(self):
        meta = {"confirmation_reached": False, "final_submit_clicked": True, "steps_clicked": 1}
        ok, reason = detect_submission_success(
            "https://example.com/thanks/",
            "https://example.com/contact/",
            "<html>ありがとう</html>",
            meta,
        )
        self.assertTrue(ok)


class TestZipPhoneMappingJS(unittest.TestCase):
    """form_field_resolver DOM JS — id=zip must not become phone_field."""

    def test_dom_js_contains_zip_guard(self):
        from form_field_resolver import _EXTRACT_FIELDS_JS
        self.assertIn("postal_code_field", _EXTRACT_FIELDS_JS)
        self.assertIn("'zip'", _EXTRACT_FIELDS_JS)


if __name__ == "__main__":
    unittest.main()
