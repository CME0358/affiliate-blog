"""Final submit execution validation — multi-step / mashimo guards."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from form_fill_no_submit import classify_button_action, BACK, FINAL_SUBMIT
from form_sender import detect_submission_success, get_real_submission_count, reset_real_submission_count
from log_manager import get_effective_sent_status, is_already_sent
from submission_state import (
    CONFIRMATION_REACHED,
    CONFIRMED_SENT,
    UNKNOWN,
    classify_submission_outcome,
)


class TestMultiStepOutcome(unittest.TestCase):
    def test_step1_only_confirmation_reached(self):
        outcome = classify_submission_outcome(
            final_url="https://www.mashimo.biz/contact-confirmation/",
            form_url="https://www.mashimo.biz/contact/",
            html="<html>問い合わせフォーム 確認</html>",
            meta={"confirmation_reached": True, "final_submit_clicked": False},
        )
        self.assertEqual(outcome.state, CONFIRMATION_REACHED)

    def test_step2_click_no_evidence_unknown(self):
        outcome = classify_submission_outcome(
            final_url="https://www.mashimo.biz/contact-confirmation/",
            form_url="https://www.mashimo.biz/contact/",
            html="<html>確認</html>",
            meta={"confirmation_reached": True, "final_submit_clicked": True},
        )
        self.assertEqual(outcome.state, CONFIRMATION_REACHED)

    def test_step2_thanks_confirmed_sent(self):
        outcome = classify_submission_outcome(
            final_url="https://example.com/thanks/",
            form_url="https://example.com/contact/",
            html="<html>送信完了しました。お問い合わせありがとうございました。</html>",
            meta={"confirmation_reached": True, "final_submit_clicked": True},
        )
        self.assertEqual(outcome.state, CONFIRMED_SENT)

    def test_back_button_classified_as_back(self):
        self.assertEqual(classify_button_action("戻る submitBack", "submit", name="submitBack"), BACK)
        self.assertEqual(classify_button_action("送信する", "submit"), FINAL_SUBMIT)

    def test_detect_success_url_confirmation_not_sent(self):
        ok, reason = detect_submission_success(
            "https://example.com/contact-confirmation/",
            "https://example.com/contact/",
            "<html>確認</html>",
            {"confirmation_reached": True, "final_submit_clicked": True},
        )
        self.assertFalse(ok)
        self.assertIn("confirmation", reason)


class TestHardLimit(unittest.TestCase):
    def test_max_one_real_submission(self):
        reset_real_submission_count()
        os.environ["ARI_PRODUCTION_MAX_SUBMISSIONS"] = "1"
        from form_sender import _record_real_submission
        _record_real_submission()
        with self.assertRaises(RuntimeError):
            _record_real_submission()
        reset_real_submission_count()
        os.environ.pop("ARI_PRODUCTION_MAX_SUBMISSIONS", None)


class TestEffectiveStatusMashimo(unittest.TestCase):
    def test_confirmation_reached_not_duplicate_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            sent = log_dir / "sent.csv"
            corrections = log_dir / "sent_status_corrections.csv"
            sent.write_text(
                "date,company_name,industry_name,area_name,website_url,form_url,lp_url,place_id,status\n"
                "2026-08-11,弁護士法人ましも法律事務所,,,https://www.mashimo.biz/,,,,sent\n",
                encoding="utf-8",
            )
            corrections.write_text(
                "corrected_at,company_name,website_url,place_id,original_status,corrected_status,reason,audit_ref,batch_id\n"
                "2026-08-11 09:15:00 JST,弁護士法人ましも法律事務所,https://www.mashimo.biz/,,sent,CONFIRMATION_REACHED,audit,ref,batch\n",
                encoding="utf-8",
            )
            with patch("log_manager.LOG_SENT", sent), patch(
                "log_manager.LOG_SENT_STATUS_CORRECTIONS", corrections
            ):
                eff = get_effective_sent_status("弁護士法人ましも法律事務所", "https://www.mashimo.biz/")
                self.assertEqual(eff, CONFIRMATION_REACHED)
                self.assertFalse(is_already_sent("弁護士法人ましも法律事務所", "https://www.mashimo.biz/"))


if __name__ == "__main__":
    unittest.main()
