"""CF7 feedback response contract + consent detector tests."""

import unittest

from cf7_feedback import (
    CF7_MAIL_SENT,
    CF7_VALIDATION_FAILED,
    classify_cf7_feedback,
    is_cf7_feedback_url,
    parse_cf7_feedback_body,
)
from consent_detector import consent_fill_status
from submission_state import (
    CONFIRMED_SENT,
    FAILED,
    UNKNOWN,
    classify_submission_outcome,
)


class TestCf7FeedbackUrl(unittest.TestCase):
    def test_is_cf7_feedback_url(self):
        self.assertTrue(is_cf7_feedback_url(
            "https://example.com/wp-json/contact-form-7/v1/contact-forms/8/feedback"
        ))
        self.assertFalse(is_cf7_feedback_url("https://example.com/contact/"))


class TestCf7ResponseClassification(unittest.TestCase):
    def test_case2_validation_failed(self):
        body = {
            "status": CF7_VALIDATION_FAILED,
            "message": "入力内容に問題があります。",
            "invalid_fields": [{"field": "your-name", "message": "必須"}],
        }
        result = parse_cf7_feedback_body(body)
        state, reason = classify_cf7_feedback(result)
        self.assertEqual(state, "FAILED")
        self.assertEqual(reason, "validation_failed")

    def test_case3_mail_sent_confirmed(self):
        body = {
            "status": CF7_MAIL_SENT,
            "message": "送信しました。",
            "invalid_fields": [],
        }
        result = parse_cf7_feedback_body(body)
        state, reason = classify_cf7_feedback(result)
        self.assertEqual(state, CONFIRMED_SENT)
        self.assertEqual(reason, "cf7_mail_sent")

    def test_case4_invalid_fields_failed_validation(self):
        body = {
            "status": CF7_MAIL_SENT,
            "message": "ok",
            "invalid_fields": [{"field": "your-email", "message": "invalid"}],
        }
        result = parse_cf7_feedback_body(body)
        state, reason = classify_cf7_feedback(result)
        self.assertEqual(state, "FAILED")
        self.assertEqual(reason, "validation_failed")

    def test_mail_failed(self):
        body = {"status": "mail_failed", "message": "failed", "invalid_fields": []}
        result = parse_cf7_feedback_body(body)
        state, reason = classify_cf7_feedback(result)
        self.assertEqual(state, "FAILED")
        self.assertEqual(reason, "cf7_mail_failed")


class TestCf7SubmissionOutcome(unittest.TestCase):
    def test_case5_post_unknown_response(self):
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact/",
            form_url="https://example.com/contact/",
            html="<html><form></form></html>",
            meta={
                "final_submit_clicked": True,
                "post_requests": [
                    "https://example.com/wp-json/contact-form-7/v1/contact-forms/8/feedback",
                ],
            },
        )
        self.assertEqual(outcome.state, UNKNOWN)
        self.assertEqual(outcome.reason, "cf7_response_unknown")

    def test_case6_dom_and_cf7_success(self):
        after = (
            '<div class="wpcf7"><form class="wpcf7-form sent">'
            '<div class="wpcf7-response-output wpcf7-mail-sent-ok">送信しました</div></form></div>'
        )
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact/",
            form_url="https://example.com/contact/",
            html=after,
            meta={
                "final_submit_clicked": True,
                "html_before": '<form class="wpcf7-form"></form>',
                "cf7_feedback": {
                    "status": CF7_MAIL_SENT,
                    "message": "送信しました",
                    "invalid_fields": [],
                },
            },
        )
        self.assertEqual(outcome.state, CONFIRMED_SENT)

    def test_cf7_mail_sent_without_dom(self):
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact/",
            form_url="https://example.com/contact/",
            html="<html><form></form></html>",
            meta={
                "final_submit_clicked": True,
                "cf7_feedback": {
                    "status": CF7_MAIL_SENT,
                    "message": "ありがとうございます",
                    "invalid_fields": [],
                },
            },
        )
        self.assertEqual(outcome.state, CONFIRMED_SENT)
        self.assertEqual(outcome.reason, "cf7_mail_sent")

    def test_cf7_validation_failed_not_unknown(self):
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact/",
            form_url="https://example.com/contact/",
            html="<html></html>",
            meta={
                "final_submit_clicked": True,
                "cf7_feedback": {
                    "status": CF7_VALIDATION_FAILED,
                    "message": "validation",
                    "invalid_fields": [{"field": "your-name", "message": "必須"}],
                },
            },
        )
        self.assertEqual(outcome.state, FAILED)
        self.assertEqual(outcome.reason, "validation_failed")


class TestConsentDetector(unittest.TestCase):
    def test_case1_consent_fill_status_filled(self):
        result = {"present": True, "filled": True, "source": "wpcf7-acceptance"}
        self.assertEqual(consent_fill_status(result), "FILLED")

    def test_consent_not_required_when_absent(self):
        self.assertEqual(consent_fill_status({"present": False, "filled": False}), "NOT_REQUIRED")
        self.assertEqual(consent_fill_status(None), "NOT_REQUIRED")

    def test_consent_missing_when_present_not_filled(self):
        result = {"present": True, "filled": False, "source": "wpcf7-acceptance"}
        self.assertEqual(consent_fill_status(result), "MISSING")


if __name__ == "__main__":
    unittest.main()
