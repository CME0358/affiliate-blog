"""Evidence reauthorization — semantic submit refinement regression tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from evidence_reauthorization import (
    EXPECTED_SEMANTIC_SUBMIT_REFINEMENT,
    EXPECTED_SELECTOR_REFINEMENT,
    MATERIAL_HASH_DRIFT,
    UNEXPLAINED_HASH_DRIFT,
    authorize_production_evidence,
    classify_hash_drift,
    is_generic_submit_selector,
)
from form_fill_no_submit import classify_button_action
from multistep_state import CONFIRMATION, FORM_ENTRY
from shared_form_prepare import SEMANTIC_EVIDENCE_SCHEMA_VERSION, build_semantic_evidence_record, compute_semantic_hash
from submit_target_semantics import (
    is_named_submit_selector,
    is_scoped_refinement_of,
    parse_submit_selector_identity,
)

SCOPE = 'form[data-ari-form-scope="contact"]'


def _snap(*, submit: str, scope: str = SCOPE) -> dict:
    fields = {
        "contact_form_scope": scope,
        "company_field": 'input[name="company"]',
        "name_field": 'input[name="name"]',
        "email_field": 'input[name="email"]',
        "phone_field": 'input[name="tel"]',
        "message_field": 'textarea[name="message"]',
        "submit_button": submit,
    }
    return {
        "semantic_evidence_schema_version": SEMANTIC_EVIDENCE_SCHEMA_VERSION,
        "contact_form_scope": scope,
        "submit_target": submit,
        "fields": fields,
        "field_map": {
            "company": "FILLED",
            "name": "FILLED",
            "email": "FILLED",
            "phone": "FILLED",
            "message": "FILLED",
            "subject": "MISSING",
            "consent": "NOT_REQUIRED",
        },
        "choices_applied": [],
        "choices_post_fill": [],
        "message_variant": "ARI_MESSAGE_V1",
        "message_length": 952,
        "consent": "NOT_REQUIRED",
    }


def _evidence(submit: str) -> dict:
    return build_semantic_evidence_record(canonical_snapshot=_snap(submit=submit))


def _cst(*, selector: str, hint: str, policy: str = "UNIQUE_HIGH_CONFIDENCE") -> dict:
    return {
        "submit_selector": selector,
        "selector_hint": hint,
        "resolution_policy": policy,
        "final_submit_eligible": True,
    }


class TestSelectorIdentity(unittest.TestCase):
    def test_generic_input_type_submit(self):
        self.assertTrue(is_generic_submit_selector("form input[type=\"submit\"]"))

    def test_name_submit(self):
        ident = parse_submit_selector_identity('input[name="submit"]')
        self.assertEqual(ident.get("name"), "submit")
        self.assertTrue(is_named_submit_selector('input[name="submit"]'))

    def test_scoped_refinement_named(self):
        pre = 'input[name="submitConfirm"]'
        prod = f'{SCOPE} input[name="submitConfirm"]'
        self.assertTrue(is_scoped_refinement_of(pre, prod))

    def test_not_refinement_different_name(self):
        self.assertFalse(is_scoped_refinement_of('input[name="submit"]', 'input[name="send"]'))


class TestMultistepClassification(unittest.TestCase):
    def test_submit_confirm_form_entry_is_next_step(self):
        self.assertEqual(
            classify_button_action("確認画面へ", "submit", name="submitConfirm", page_url="https://x/contact/"),
            "NEXT_STEP_SAFE",
        )

    def test_submit_confirm_on_confirm_page_can_be_final_if_send(self):
        self.assertEqual(
            classify_button_action("送信する", "submit", name="submitSend", page_url="https://x/contact/confirm/"),
            "FINAL_SUBMIT",
        )


class TestHashDriftClassification(unittest.TestCase):
    def test_generic_type_refinement(self):
        pre = _evidence('form input[type="submit"]')
        fresh = {"snapshot": _snap(submit=f'{SCOPE} .wpcf7-submit')}
        cls, reasons = classify_hash_drift(
            pre, fresh,
            canonical_submit_target=_cst(
                selector=f'{SCOPE} .wpcf7-submit',
                hint='form input[type="submit"]',
            ),
        )
        self.assertEqual(cls, EXPECTED_SELECTOR_REFINEMENT, reasons)

    def test_named_submit_confirm_refinement(self):
        pre = _evidence('input[name="submitConfirm"]')
        prod_sel = f'{SCOPE} input[name="submitConfirm"]'
        fresh = {"snapshot": _snap(submit=prod_sel)}
        cls, reasons = classify_hash_drift(
            pre, fresh,
            canonical_submit_target=_cst(selector=prod_sel, hint='input[name="submitConfirm"]'),
        )
        self.assertEqual(cls, EXPECTED_SEMANTIC_SUBMIT_REFINEMENT, reasons)

    def test_eight_renewal_regression_fixture(self):
        pre = _evidence('input[name="submitConfirm"]')
        prod_sel = f'{SCOPE} input[name="submitConfirm"]'
        fresh = {"snapshot": _snap(submit=prod_sel, scope=SCOPE)}
        cls, _ = classify_hash_drift(
            pre,
            fresh,
            canonical_submit_target=_cst(
                selector=prod_sel,
                hint='input[name="submitConfirm"]',
            ),
        )
        self.assertEqual(cls, EXPECTED_SEMANTIC_SUBMIT_REFINEMENT)

    def test_semantic_action_change_blocks(self):
        pre = _evidence('input[name="submitConfirm"]')
        fresh = {"snapshot": _snap(submit='input[name="submitSend"]')}
        cls, _ = classify_hash_drift(
            pre, fresh,
            canonical_submit_target=_cst(
                selector='input[name="submitSend"]',
                hint='input[name="submitConfirm"]',
            ),
        )
        self.assertEqual(cls, UNEXPLAINED_HASH_DRIFT)

    def test_material_field_change_blocks(self):
        pre = _evidence('input[name="submitConfirm"]')
        snap = _snap(submit=f'{SCOPE} input[name="submitConfirm"]')
        snap["field_map"]["email"] = "MISSING"
        fresh = {"snapshot": snap}
        cls, reasons = classify_hash_drift(pre, fresh, canonical_submit_target=_cst(
            selector=f'{SCOPE} input[name="submitConfirm"]',
            hint='input[name="submitConfirm"]',
        ))
        self.assertEqual(cls, MATERIAL_HASH_DRIFT)
        self.assertIn("semantic_core_changed", reasons)

    def test_named_final_send_value(self):
        pre = _evidence('input[name="submit"]')
        prod = f'{SCOPE} input[name="submit"][value="送信する"]'
        cls, _ = classify_hash_drift(
            _evidence('input[name="submit"]'),
            {"snapshot": _snap(submit=prod)},
            canonical_submit_target=_cst(selector=prod, hint='input[name="submit"]'),
        )
        self.assertEqual(cls, EXPECTED_SEMANTIC_SUBMIT_REFINEMENT)

    def test_hidden_named_not_in_refinement_path(self):
        self.assertFalse(is_scoped_refinement_of('input[name="a"]', 'input[name="b"]'))


class TestAuthorizeProductionEvidence(unittest.IsolatedAsyncioTestCase):
    async def test_authorize_named_scoped_refinement(self):
        from shared_form_prepare import FormPrepareResult, PreparedFormSnapshot, mark_snapshot_authorized

        prod_sel = f'{SCOPE} input[name="submitConfirm"]'
        snap = _snap(submit=prod_sel)
        prod_hash = compute_semantic_hash(snap)
        prep = FormPrepareResult(
            ok=True,
            fields=snap["fields"],
            field_map=snap["field_map"],
            contact_form_scope=SCOPE,
            mapping_hash=prod_hash,
            snapshot=snap,
            canonical_submit_target=_cst(selector=prod_sel, hint='input[name="submitConfirm"]'),
        )
        page = MagicMock()
        page.is_closed.return_value = False
        page.url = "https://eight-renewal.com/contact/"
        prepared = PreparedFormSnapshot(
            prep=prep,
            form_url="https://eight-renewal.com/contact/",
            page=page,
            authorized=False,
        )
        ok, reasons, meta = authorize_production_evidence(
            prepared,
            _evidence('input[name="submitConfirm"]'),
            allow_selector_refinement=True,
        )
        self.assertTrue(ok, reasons)
        self.assertTrue(meta.get("evidence_reauthorized"))
        self.assertEqual(meta.get("reauthorization_reason"), EXPECTED_SEMANTIC_SUBMIT_REFINEMENT)


if __name__ == "__main__":
    unittest.main()
