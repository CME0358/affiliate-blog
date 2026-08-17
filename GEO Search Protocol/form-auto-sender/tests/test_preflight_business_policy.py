"""Preflight business-form downgrade policy tests."""

import unittest

from preflight_classifier import (
    FORM_NOT_SUITABLE,
    NOT_READY,
    bucket_not_ready_reason,
    classify_preflight,
    infer_business_unsuitable,
)


class TestBusinessUnsuitable(unittest.TestCase):
    def test_estimate_url(self):
        ok, tag = infer_business_unsuitable({}, "https://www.example.com/estimate/")
        self.assertTrue(ok)
        self.assertEqual(tag, "estimate_only")

    def test_validation_service_specific(self):
        fn = {
            "multistep_state": "VALIDATION_FAILED",
            "validation_feedback": {
                "errors": ["建物種別必須", "施工内容必須", "メールアドレス(確認用)必須"],
            },
        }
        ok, tag = infer_business_unsuitable(fn)
        self.assertTrue(ok)
        self.assertEqual(tag, "service_specific_required")

    def test_downgrade_and_reform_like(self):
        pf = {
            "form_url": "https://www.and-reform.com/estimate/",
            "fill_no_submit": {
                "status": "filled",
                "field_map": {"name": "FILLED", "email": "FILLED", "message": "FILLED"},
                "final_submit_identified": False,
                "message_validation": {"pass": True},
                "multistep_state": "VALIDATION_FAILED",
                "validation_feedback": {"errors": ["ご住所【必須】", "建物種別必須"]},
            },
        }
        cls, reason, _ = classify_preflight(pf)
        self.assertEqual(cls, FORM_NOT_SUITABLE)
        self.assertEqual(reason, "estimate_only")

    def test_bucket_no_final_submit(self):
        fn = {"reason": "", "multistep_state": None}
        self.assertEqual(bucket_not_ready_reason("no_final_submit", fn), "no_final_submit")


if __name__ == "__main__":
    unittest.main()
