"""Compatibility hardening tests — #14 multi-step, #16 CF7, #20 postmail."""

import unittest

from cf7_feedback import (
    analyze_cf7_invalid_fields,
    classify_cf7_feedback,
    parse_cf7_feedback_body,
)
from form_fill_no_submit import (
    BACK,
    FINAL_SUBMIT,
    NEXT_STEP_SAFE,
    classify_button_action,
    pick_final_submit_button,
)
from submission_state import (
    CONFIRMED_SENT,
    CONFIRMATION_REACHED,
    FAILED,
    FORM_NOT_SUITABLE,
    UNKNOWN,
    _detect_completion_transition,
    classify_submission_outcome,
    has_confirm_validation_errors,
)


class TestMultiStepHardening(unittest.TestCase):
    """Priority 1 — multi-step final completion contract."""

    def test_confirm_url_only_confirmation_reached(self):
        outcome = classify_submission_outcome(
            final_url="https://example.com/contacts/confirm",
            form_url="https://example.com/contacts/new",
            html="<html><body>確認</body></html>",
            meta={"confirmation_reached": True, "final_submit_clicked": False},
        )
        self.assertEqual(outcome.state, CONFIRMATION_REACHED)

    def test_confirm_final_thanks_confirmed_sent(self):
        before = "<html><body><form>input</form></body></html>"
        after = "<html><body><div>送信完了しました。ありがとうございました。</div></body></html>"
        meta = {
            "confirmation_reached": True,
            "final_submit_clicked": True,
            "html_before": before,
            "form_count_before": 1,
            "form_count_after": 0,
        }
        ok, _ = _detect_completion_transition(before, after, meta)
        self.assertTrue(ok)
        outcome = classify_submission_outcome(
            final_url="https://example.com/contacts/complete",
            form_url="https://example.com/contacts/new",
            html=after,
            meta=meta,
        )
        self.assertEqual(outcome.state, CONFIRMED_SENT)

    def test_back_and_final_picks_final_only(self):
        buttons = [
            {"label": "戻る", "type": "submit", "classification": BACK},
            {"label": "送信 commit", "type": "submit", "name": "commit", "classification": FINAL_SUBMIT},
        ]
        btn, err = pick_final_submit_button(buttons)
        self.assertIsNotNone(btn)
        self.assertEqual(btn["classification"], FINAL_SUBMIT)

    def test_form_action_confirm_is_next_on_input_page(self):
        self.assertEqual(
            classify_button_action(
                "送信 commit",
                "submit",
                name="commit",
                form_action="https://example.com/contacts/confirm",
                page_url="https://example.com/contacts/new",
            ),
            NEXT_STEP_SAFE,
        )

    def test_form_action_confirm_is_final_on_confirm_page(self):
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

    def test_confirm_validation_failed(self):
        html = "<html><body>山商を何でお知りになりましたか？を選択してください</body></html>"
        self.assertTrue(has_confirm_validation_errors(html))
        outcome = classify_submission_outcome(
            final_url="https://example.com/contacts/confirm",
            form_url="https://example.com/contacts/new",
            html=html,
            meta={
                "confirmation_reached": True,
                "final_submit_clicked": False,
                "confirm_validation_failed": True,
            },
        )
        self.assertEqual(outcome.state, FAILED)
        self.assertEqual(outcome.reason, "confirm_validation_failed")


class TestCf7InvalidFields(unittest.TestCase):
    """Priority 2 — CF7 validation / FORM_NOT_SUITABLE."""

    def test_analyze_invalid_fields_missing_name(self):
        analysis = analyze_cf7_invalid_fields([
            {"field": "your-name", "message": "必須", "idref": None},
        ])
        self.assertFalse(analysis["form_not_suitable"])
        self.assertEqual(analysis["missing_standard_fields"][0]["logical"], "name")

    def test_resolver_mappable_required_field(self):
        analysis = analyze_cf7_invalid_fields([
            {"field": "your-email", "message": "不正", "idref": None},
        ])
        self.assertEqual(analysis["missing_standard_fields"][0]["logical"], "email")

    def test_spam_block_unsuitable(self):
        body = {
            "status": "validation_failed",
            "message": "入力内容に不備があります。",
            "invalid_fields": [
                {"field": "spam-block-01", "message": "入力された文字列が間違っています", "idref": None},
            ],
        }
        result = parse_cf7_feedback_body(body)
        analysis = analyze_cf7_invalid_fields(result.invalid_fields)
        self.assertTrue(analysis["form_not_suitable"])
        state, reason = classify_cf7_feedback(result)
        self.assertEqual(state, FORM_NOT_SUITABLE)
        self.assertIn("spam-block-01", reason)

    def test_cf7_unsuitable_outcome(self):
        outcome = classify_submission_outcome(
            final_url="https://1stop86.com/contact/",
            form_url="https://1stop86.com/contact/",
            html="<html></html>",
            meta={
                "final_submit_clicked": True,
                "cf7_feedback": {
                    "status": "validation_failed",
                    "message": "validation",
                    "invalid_fields": [
                        {"field": "spam-block-01", "message": "wrong", "idref": None},
                    ],
                },
            },
        )
        self.assertEqual(outcome.state, FORM_NOT_SUITABLE)


class TestPostmailCompletion(unittest.TestCase):
    """Priority 3 — postmail completion detection."""

    def test_postmail_explicit_success_confirmed_sent(self):
        before = "<html><body><form><input name='word3'></form></body></html>"
        after = (
            "<html><body><p>お問い合わせありがとうございました。送信しました。</p></body></html>"
        )
        meta = {
            "final_submit_clicked": True,
            "final_url": "https://example.com/contact/postmail",
            "html_before": before,
            "form_count_before": 1,
            "form_count_after": 0,
        }
        ok, reason = _detect_completion_transition(before, after, meta)
        self.assertTrue(ok)
        self.assertIn("postmail", reason)
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact/postmail",
            form_url="https://example.com/contact.html",
            html=after,
            meta=meta,
        )
        self.assertEqual(outcome.state, CONFIRMED_SENT)

    def test_post_only_without_success_unknown(self):
        html = "<html><body><form><input name='word3'><input type='submit'></form></body></html>"
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact/postmail",
            form_url="https://example.com/contact.html",
            html=html,
            meta={
                "final_submit_clicked": True,
                "html_before": html,
                "post_requests": ["https://example.com/contact/postmail"],
                "form_count_before": 1,
                "form_count_after": 1,
            },
        )
        self.assertEqual(outcome.state, UNKNOWN)


if __name__ == "__main__":
    unittest.main()
