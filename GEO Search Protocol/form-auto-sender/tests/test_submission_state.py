"""Success State Contract — classify_submission_outcome / effective status / counters."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from submission_state import (
    CONFIRMATION_REACHED,
    CONFIRMED_SENT,
    MANUAL_INTERVENTION_REQUIRED,
    UNKNOWN,
    SubmissionCounters,
    classify_submission_outcome,
    should_block_duplicate_send,
)
from log_manager import get_effective_sent_status, is_already_sent


class TestClassifySubmissionOutcome(unittest.TestCase):
    def test_confirmation_page_only(self):
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact-confirmation/",
            form_url="https://example.com/contact/",
            html="<html>入力内容の確認</html>",
            meta={"confirmation_reached": True, "final_submit_clicked": False},
        )
        self.assertEqual(outcome.state, CONFIRMATION_REACHED)
        self.assertFalse(outcome.counts_toward_confirmed_sent)

    def test_confirmation_then_final_submit_thanks(self):
        outcome = classify_submission_outcome(
            final_url="https://example.com/thanks/",
            form_url="https://example.com/contact/",
            html="<html>送信完了しました。お問い合わせありがとうございました。</html>",
            meta={"confirmation_reached": True, "final_submit_clicked": True},
        )
        self.assertEqual(outcome.state, CONFIRMED_SENT)
        self.assertTrue(outcome.counts_toward_confirmed_sent)

    def test_final_submit_no_completion_evidence(self):
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact/",
            form_url="https://example.com/contact/",
            html="<html><body>form</body></html>",
            meta={"confirmation_reached": True, "final_submit_clicked": True},
        )
        self.assertEqual(outcome.state, UNKNOWN)

    def test_captcha_manual_intervention(self):
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact/",
            form_url="https://example.com/contact/",
            html='<html><div class="g-recaptcha"></div></html>',
            meta={},
            captcha_hint=True,
        )
        self.assertEqual(outcome.state, MANUAL_INTERVENTION_REQUIRED)

    def test_success_looking_url_without_success_dom(self):
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact-confirmation/",
            form_url="https://example.com/contact/",
            html="<html><body>氏名 確認</body></html>",
            meta={"confirmation_reached": True, "final_submit_clicked": True},
        )
        self.assertNotEqual(outcome.state, CONFIRMED_SENT)
        self.assertIn(outcome.state, (CONFIRMATION_REACHED, UNKNOWN))


class TestEffectiveStatus(unittest.TestCase):
    def test_raw_sent_plus_correction_confirmation_reached(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            sent = log_dir / "sent.csv"
            corrections = log_dir / "sent_status_corrections.csv"
            sent.write_text(
                "date,company_name,industry_name,area_name,website_url,form_url,lp_url,place_id,status\n"
                "2026-08-11,Test Co,,,https://example.com,,,,sent\n",
                encoding="utf-8",
            )
            corrections.write_text(
                "corrected_at,company_name,website_url,place_id,original_status,corrected_status,reason,audit_ref,batch_id\n"
                "2026-08-11 10:00:00 JST,Test Co,https://example.com,,sent,CONFIRMATION_REACHED,audit,ref,batch\n",
                encoding="utf-8",
            )
            with patch("log_manager.LOG_SENT", sent), patch(
                "log_manager.LOG_SENT_STATUS_CORRECTIONS", corrections
            ):
                eff = get_effective_sent_status("Test Co", "https://example.com")
                self.assertEqual(eff, CONFIRMATION_REACHED)
                self.assertFalse(should_block_duplicate_send(eff))
                self.assertFalse(is_already_sent("Test Co", "https://example.com"))

    def test_confirmed_sent_blocks_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            sent = log_dir / "sent.csv"
            corrections = log_dir / "sent_status_corrections.csv"
            sent.write_text(
                "date,company_name,industry_name,area_name,website_url,form_url,lp_url,place_id,status\n"
                "2026-08-11,Confirmed Co,,,https://confirmed.example,,,,sent\n",
                encoding="utf-8",
            )
            corrections.write_text(
                "corrected_at,company_name,website_url,place_id,original_status,corrected_status,reason,audit_ref,batch_id\n",
                encoding="utf-8",
            )
            with patch("log_manager.LOG_SENT", sent), patch(
                "log_manager.LOG_SENT_STATUS_CORRECTIONS", corrections
            ):
                eff = get_effective_sent_status("Confirmed Co", "https://confirmed.example")
                self.assertEqual(eff, CONFIRMED_SENT)
                self.assertTrue(is_already_sent("Confirmed Co", "https://confirmed.example"))


class TestSubmissionCounters(unittest.TestCase):
    def test_counter_separation(self):
        counters = SubmissionCounters()
        counters.record(
            classify_submission_outcome(
                final_url="https://x.com/confirm/",
                form_url="https://x.com/contact/",
                html="確認",
                meta={"confirmation_reached": True, "final_submit_clicked": False},
            )
        )
        counters.record(
            classify_submission_outcome(
                final_url="https://x.com/thanks/",
                form_url="https://x.com/contact/",
                html="送信完了",
                meta={"final_submit_clicked": True},
            )
        )
        d = counters.to_dict()
        self.assertEqual(d["attempted"], 2)
        self.assertEqual(d["confirmed_sent"], 1)
        self.assertEqual(d["confirmation_reached"], 1)


if __name__ == "__main__":
    unittest.main()
