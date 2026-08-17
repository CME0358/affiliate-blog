"""Final submit compatibility — BACK/FINAL/same-URL success detection."""

import unittest

from form_fill_no_submit import (
    BACK,
    FINAL_SUBMIT,
    NEXT_STEP_SAFE,
    classify_button_action,
    pick_final_submit_button,
)
from submission_state import (
    CONFIRMED_SENT,
    UNKNOWN,
    _detect_completion_transition,
    classify_submission_outcome,
)


class TestBackFinalClassification(unittest.TestCase):
    """Case A / B"""

    def test_case_a_back_and_final_picks_final(self):
        buttons = [
            {"label": "戻る submitBack", "type": "submit", "name": "submitBack", "classification": BACK},
            {"label": "送信する send", "type": "submit", "name": "send", "classification": FINAL_SUBMIT},
        ]
        btn, err = pick_final_submit_button(buttons)
        self.assertIsNotNone(btn)
        self.assertEqual(err, "")
        self.assertEqual(btn["classification"], FINAL_SUBMIT)
        self.assertEqual(classify_button_action("戻る submitBack", "submit", name="submitBack"), BACK)
        self.assertEqual(classify_button_action("送信する send", "submit", name="send"), FINAL_SUBMIT)

    def test_case_b_back_only_no_final(self):
        buttons = [
            {"label": "戻る", "type": "button", "classification": BACK},
        ]
        btn, err = pick_final_submit_button(buttons)
        self.assertIsNone(btn)
        self.assertIn("not_found", err)


class TestSameUrlSuccessDetection(unittest.TestCase):
    """Case C / D / E"""

    def test_case_c_same_url_success_dom(self):
        before = "<html><body><form>input</form></body></html>"
        after = "<html><body><form class='wpcf7-form sent'>送信完了しました</form></body></html>"
        ok, reason = _detect_completion_transition(before, after, {"final_submit_clicked": True})
        self.assertTrue(ok)
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact/",
            form_url="https://example.com/contact/",
            html=after,
            meta={"final_submit_clicked": True, "html_before": before},
        )
        self.assertEqual(outcome.state, CONFIRMED_SENT)

    def test_case_d_form_replaced_completion(self):
        before = "<html><body><form><input></form></body></html>"
        after = "<html><body><div class='thanks'>お問い合わせありがとうございました</div></body></html>"
        meta = {"final_submit_clicked": True, "html_before": before, "form_count_before": 1, "form_count_after": 0}
        ok, reason = _detect_completion_transition(before, after, meta)
        self.assertTrue(ok)
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact/",
            form_url="https://example.com/contact/",
            html=after,
            meta=meta,
        )
        self.assertEqual(outcome.state, CONFIRMED_SENT)

    def test_case_e_click_only_unknown(self):
        html = "<html><body><form>unchanged</form></body></html>"
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact/",
            form_url="https://example.com/contact/",
            html=html,
            meta={"final_submit_clicked": True, "html_before": html},
        )
        self.assertEqual(outcome.state, UNKNOWN)

    def test_case_f_thanks_url(self):
        outcome = classify_submission_outcome(
            final_url="https://www.mashimo.biz/thanks/",
            form_url="https://www.mashimo.biz/contact/",
            html="<html>送信完了</html>",
            meta={"final_submit_clicked": True, "confirmation_reached": True},
        )
        self.assertEqual(outcome.state, CONFIRMED_SENT)


class TestMashimoRegression(unittest.TestCase):
    """Case — #3 mashimo flow unchanged"""

    def test_mashimo_thanks_confirmed_sent(self):
        outcome = classify_submission_outcome(
            final_url="https://www.mashimo.biz/thanks/",
            form_url="https://www.mashimo.biz/contact/",
            html="<html><title>送信完了</title>お問い合わせありがとうございました</html>",
            meta={"confirmation_reached": True, "final_submit_clicked": True, "steps_clicked": 2},
        )
        self.assertEqual(outcome.state, CONFIRMED_SENT)
        self.assertTrue(outcome.counts_toward_confirmed_sent)

    def test_mashimo_confirmation_only_not_sent(self):
        outcome = classify_submission_outcome(
            final_url="https://www.mashimo.biz/contact-confirmation/",
            form_url="https://www.mashimo.biz/contact/",
            html="<html>確認</html>",
            meta={"confirmation_reached": True, "final_submit_clicked": False},
        )
        self.assertNotEqual(outcome.state, CONFIRMED_SENT)


class TestWpcf7Completion(unittest.TestCase):
    def test_wpcf7_mail_sent_ok(self):
        before = '<div class="wpcf7"><form class="wpcf7-form"></form></div>'
        after = '<div class="wpcf7"><form class="wpcf7-form sent"><div class="wpcf7-response-output wpcf7-mail-sent-ok">送信しました</div></form></div>'
        ok, reason = _detect_completion_transition(before, after, {})
        self.assertTrue(ok)
        self.assertIn("wpcf7", reason)


class TestMwWpFormCompletion(unittest.TestCase):
    """MW WP Form same-URL — plugin-generic completion state."""

    def test_mw_wp_form_input_to_complete(self):
        before = '<div class="mw_wp_form mw_wp_form_input"><form method="post"></form></div>'
        after = '<div class="mw_wp_form mw_wp_form_complete"><p>送信が完了しました</p></div>'
        meta = {
            "final_submit_clicked": True,
            "html_before": before,
            "form_count_before": 1,
            "form_count_after": 0,
        }
        ok, reason = _detect_completion_transition(before, after, meta)
        self.assertTrue(ok)
        self.assertIn("mw_wp_form", reason)
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact/",
            form_url="https://example.com/contact/",
            html=after,
            meta=meta,
        )
        self.assertEqual(outcome.state, CONFIRMED_SENT)

    def test_mw_wp_form_complete_form_removed_no_success_text(self):
        before = '<div class="mw_wp_form mw_wp_form_confirm"><form></form></div>'
        after = '<div class="mw_wp_form mw_wp_form_complete"></div>'
        meta = {
            "final_submit_clicked": True,
            "confirmation_reached": True,
            "html_before": before,
            "form_count_before": 1,
            "form_count_after": 0,
        }
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact/",
            form_url="https://example.com/contact/",
            html=after,
            meta=meta,
        )
        self.assertEqual(outcome.state, CONFIRMED_SENT)


class TestExternalConfirmation(unittest.TestCase):
    def test_external_confirmation_requires_explicit_flag(self):
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact/",
            form_url="https://example.com/contact/",
            html="<html></html>",
            meta={"final_submit_clicked": True},
        )
        self.assertNotEqual(outcome.reason, "external_confirmation")

    def test_external_confirmation_confirmed_sent(self):
        from submission_state import EXTERNAL_CONFIRMATION

        outcome = classify_submission_outcome(
            final_url="https://example.com/contact/",
            form_url="https://example.com/contact/",
            html="<html></html>",
            meta={
                "final_submit_clicked": True,
                "confirmation_reached": True,
                "external_confirmation": {
                    "confirmed": True,
                    "type": "automatic_acknowledgement_email",
                },
            },
        )
        self.assertEqual(outcome.state, CONFIRMED_SENT)
        self.assertEqual(outcome.reason, "external_confirmation")
        self.assertEqual(outcome.evidence.external_confirmation_type, "automatic_acknowledgement_email")


if __name__ == "__main__":
    unittest.main()
