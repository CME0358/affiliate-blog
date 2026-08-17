"""Production path unification — shared runtime contract tests."""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from shared_form_prepare import (
    RUNTIME_DIVERGENCE,
    build_mapping_snapshot,
    compare_runtime_snapshots,
    compute_mapping_hash,
    shared_prepare_form,
)
from submission_state import CONFIRMED_SENT, UNKNOWN, classify_submission_outcome


class TestMappingHash(unittest.TestCase):
    def test_identical_snapshots_same_hash(self):
        snap = build_mapping_snapshot(
            fields={"name_field": "#name", "email_field": "#email"},
            filled={"name": "FILLED", "email": "FILLED"},
            choice_log={"applied": [{"category": "INQUIRY_CATEGORY", "name": "type", "value": "other"}]},
            field_map={"name": "FILLED", "email": "FILLED", "message": "FILLED", "consent": "FILLED"},
            contact_form_scope='form[data-ari-form-scope="contact"]',
        )
        h1 = compute_mapping_hash(snap)
        h2 = compute_mapping_hash(dict(snap))
        self.assertEqual(h1, h2)

    def test_different_choices_different_hash(self):
        base = dict(
            fields={"name_field": "#name"},
            filled={"name": "FILLED"},
            field_map={"name": "FILLED"},
            contact_form_scope="form.contact",
        )
        s1 = build_mapping_snapshot(**base, choice_log={"applied": [{"name": "a", "value": "1"}]})
        s2 = build_mapping_snapshot(**base, choice_log={"applied": [{"name": "b", "value": "2"}]})
        self.assertNotEqual(compute_mapping_hash(s1), compute_mapping_hash(s2))


class TestRuntimeDivergence(unittest.TestCase):
    def test_mapping_hash_mismatch_diverges(self):
        pre = {"mapping_hash": "aaa", "field_map": {"name": "FILLED"}}
        prod = {"mapping_hash": "bbb", "field_map": {"name": "FILLED"}}
        diverged, reasons = compare_runtime_snapshots(pre, prod)
        self.assertTrue(diverged)
        self.assertTrue(any("mapping_hash" in r for r in reasons))

    def test_field_regression_diverges(self):
        pre = {"mapping_hash": "x", "field_map": {"message": "FILLED", "consent": "FILLED"}}
        prod = {"mapping_hash": "x", "field_map": {"message": "MISSING", "consent": "MISSING"}}
        diverged, reasons = compare_runtime_snapshots(pre, prod)
        self.assertTrue(diverged)
        self.assertTrue(any("field_regression:message" in r for r in reasons))

    def test_runtime_divergence_constant(self):
        self.assertEqual(RUNTIME_DIVERGENCE, "RUNTIME_DIVERGENCE")


class TestSharedRuntimeImports(unittest.TestCase):
    def test_preflight_and_production_use_shared_prepare(self):
        import form_fill_no_submit
        import form_sender

        src_fill = inspect.getsource(form_fill_no_submit.fill_form_no_submit)
        src_send = inspect.getsource(form_sender.send_form)
        self.assertIn("shared_prepare_form", src_fill)
        self.assertIn("prepare_once", src_send)
        self.assertIn("authorize_snapshot", src_send)

    def test_send_form_no_legacy_page_fill_block(self):
        import form_sender
        src = inspect.getsource(form_sender.send_form)
        self.assertNotIn("await page.fill(fields[\"company_field\"]", src)
        self.assertNotIn("await page.fill(fields[\"name_field\"]", src)


class TestCf7ChoicesInProduction(unittest.TestCase):
    def test_required_choices_in_snapshot(self):
        snap = build_mapping_snapshot(
            fields={"message_field": "textarea"},
            filled={"message": "FILLED"},
            choice_log={
                "applied": [
                    {"category": "INQUIRY_CATEGORY", "name": "your-request", "value": "other", "label": "その他"},
                    {"category": "SERVICE_TYPE", "name": "your-work", "value": "other", "label": "その他"},
                ],
            },
            field_map={"message": "FILLED", "consent": "FILLED"},
        )
        names = [c["name"] for c in snap["choices_applied"]]
        self.assertIn("your-request", names)
        self.assertIn("your-work", names)


class TestHoneypotNotInSnapshot(unittest.TestCase):
    def test_honeypot_fields_excluded_from_mapping_fields(self):
        snap = build_mapping_snapshot(
            fields={
                "name_field": "#your-name",
                "spam-block_field": "#spam",
            },
            filled={"name": "FILLED"},
            choice_log={},
            field_map={"name": "FILLED"},
        )
        self.assertIn("name_field", snap["fields"])
        self.assertNotIn("spam-block_field", snap["fields"])


class TestSubmissionStateSameUrl(unittest.TestCase):
    def test_post_only_unknown_not_confirmed(self):
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact#form1",
            form_url="https://example.com/contact/",
            html="<html><form>...</form></html>",
            meta={
                "final_submit_clicked": True,
                "html_before": "<html><form>...</form></html>",
                "post_requests": ["https://example.com/contact"],
                "post_responses": [],
                "form_count_before": 1,
                "form_count_after": 1,
            },
        )
        self.assertEqual(outcome.state, UNKNOWN)
        self.assertNotEqual(outcome.state, CONFIRMED_SENT)

    def test_post_response_success_body_confirmed(self):
        before = "<html><title>お問い合わせ</title><form>input</form></html>"
        after = "<html><title>お問い合わせ</title><form>input</form><p>送信ありがとうございました</p></html>"
        outcome = classify_submission_outcome(
            final_url="https://example.com/contact#form1",
            form_url="https://example.com/contact/",
            html=after,
            meta={
                "final_submit_clicked": True,
                "html_before": before,
                "post_requests": ["https://example.com/contact"],
                "post_responses": [{
                    "url": "https://example.com/contact",
                    "status": 200,
                    "body_excerpt": "送信ありがとうございました",
                }],
                "form_count_before": 1,
                "form_count_after": 1,
            },
        )
        self.assertEqual(outcome.state, CONFIRMED_SENT)


class TestRuntimeDivergenceStopsSend(unittest.TestCase):
    def test_send_form_blocks_on_divergence(self):
        import form_sender
        src = inspect.getsource(form_sender.send_form)
        self.assertIn("RUNTIME_DIVERGENCE", src)
        self.assertIn("authorize_snapshot", src)

    def test_divergence_prevents_hash_match_send(self):
        pre = {"mapping_hash": "preflight_abc", "field_map": {"name": "FILLED"}}
        prod = {"mapping_hash": "production_xyz", "field_map": {"name": "FILLED"}}
        diverged, _ = compare_runtime_snapshots(pre, prod)
        self.assertTrue(diverged)


if __name__ == "__main__":
    unittest.main()
