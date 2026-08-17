"""Canonical Submit Target Contract — regression tests."""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from canonical_submit_target import (
    build_submit_target_record,
    derive_final_submit_identified,
    resolve_canonical_submit_target,
    validate_authorized_submit_target,
)
from shared_form_prepare import (
    FormPrepareResult,
    PreparedFormSnapshot,
    authorize_snapshot,
    build_canonical_prepared_snapshot,
    build_semantic_evidence_record,
    compute_semantic_hash,
    mark_snapshot_authorized,
    validate_snapshot_invariants,
    _fields_fingerprint,
    SEMANTIC_EVIDENCE_SCHEMA_VERSION,
)

SAKURA_SCOPE = "form#snow-monkey-form-8099"
SAKURA_SUBMIT = 'form#snow-monkey-form-8099 button[type="submit"]'
SAKURA_FIELDS = {
    "address_field": "#addr",
    "address_line2_field": 'input[name="アパート・マンション名"]',
    "contact_form_scope": SAKURA_SCOPE,
    "email_field": 'input[name="Eメール"]',
    "message_field": 'textarea[name="備考"]',
    "name_field": 'input[name="お名前"]',
    "phone_field": 'input[name="お電話番号"]',
    "postal_code_field": "#zip",
    "submit_button": SAKURA_SUBMIT,
}
SAKURA_FM = {
    "company": "MISSING", "name": "FILLED", "email": "FILLED", "phone": "FILLED",
    "subject": "MISSING", "message": "FILLED", "consent": "NOT_REQUIRED",
}
SAKURA_HASH = "bf3e8805dafd4d19"


def _live_valid(**overrides):
    base = {
        "valid": True,
        "reason": "valid",
        "matches": 1,
        "visible": True,
        "enabled": True,
        "element_type": "button:submit",
        "label": "送信",
        "selector": SAKURA_SUBMIT,
        "contact_form_scope": SAKURA_SCOPE,
        "final_submit_eligible": True,
    }
    base.update(overrides)
    return base


def _sakura_canonical():
    return build_canonical_prepared_snapshot(
        form_url="https://sakura-reform.com/contact/",
        fields=SAKURA_FIELDS,
        filled={"name": "FILLED", "email": "FILLED", "phone": "FILLED", "message": "FILLED", "consent": "NOT_REQUIRED"},
        choice_log={
            "applied": [{"category": "CONTACT_METHOD", "name": "連絡方法[]", "value": None, "label": "メール メール"}],
            "post_fill": {"applied": [{"category": "CONTACT_METHOD", "name": "連絡方法[]", "value": None, "label": "メール メール"}]},
        },
        field_map=SAKURA_FM,
        selection={"variant": "ARI_MESSAGE_V1", "message_length": 952},
        contact_form_scope=SAKURA_SCOPE,
        submit_target=SAKURA_SUBMIT,
    )


def _sakura_evidence():
    record = build_semantic_evidence_record(canonical_snapshot=_sakura_canonical())
    h = record["semantic_hash"]
    return {
        **record,
        "mapping_hash": h,
        "submit_target": SAKURA_SUBMIT,
        "contact_form_scope": SAKURA_SCOPE,
    }


def _discovery_response():
    return {
        "ok": True,
        "hint_candidates": [{
            "tag": "button",
            "type": "submit",
            "name": "",
            "id": "",
            "className": "",
            "value": "送信",
            "text": "送信",
            "label": "送信",
            "visible": True,
            "enabled": True,
            "inSelectedForm": True,
            "domOrder": 0,
            "formAction": "/contact/",
        }],
    }


def _mock_page_eval(js, arg=None):
    js_s = str(js)
    if "fields" in js_s or "_field" in js_s:
        return []
    if "captcha" in js_s.lower():
        return False
    if "hint_candidates" in js_s or "hintMatches" in js_s:
        return _discovery_response()
    if "finalBtn" in js_s and "hasConfirm" in js_s:
        return "FORM_ENTRY"
    return _live_valid()


def _prepared_sakura(*, final_submit_identified=False, authorized=False):
    snap = _sakura_canonical()
    h = compute_semantic_hash(snap)
    submit_record = build_submit_target_record(
        submit_selector=SAKURA_SUBMIT,
        contact_form_scope=SAKURA_SCOPE,
        live_state=_live_valid(),
    )
    prep = FormPrepareResult(
        ok=True,
        fields=dict(SAKURA_FIELDS),
        field_map=dict(SAKURA_FM),
        contact_form_scope=SAKURA_SCOPE,
        mapping_hash=h,
        snapshot=snap,
        final_submit_identified=final_submit_identified,
        canonical_submit_target=submit_record if final_submit_identified else {},
    )
    page = MagicMock()
    page.is_closed.return_value = False
    page.url = "https://sakura-reform.com/contact/"

    async def _eval(js, arg=None):
        return _mock_page_eval(js, arg)

    page.evaluate = AsyncMock(side_effect=_eval)
    baseline = {
        "form_url": "https://sakura-reform.com/contact/",
        "page_url": "https://sakura-reform.com/contact/",
        "contact_form_scope": SAKURA_SCOPE,
        "field_map": dict(SAKURA_FM),
        "mapping_hash": h,
        "fields_fingerprint": _fields_fingerprint(SAKURA_FIELDS),
        "submit_button": SAKURA_SUBMIT,
        "final_submit_identified": final_submit_identified,
        "canonical_submit_target": submit_record,
    }
    return PreparedFormSnapshot(
        prep=prep,
        form_url="https://sakura-reform.com/contact/",
        page_url="https://sakura-reform.com/contact/",
        page=page,
        invariant_baseline=baseline,
        authorized=authorized,
        authorization_hash=h if authorized else "",
    )


class TestSakuraRegression(unittest.IsolatedAsyncioTestCase):
    async def test_canonical_submit_valid_despite_legacy_flag_false(self):
        """Hash matches + canonical submit target valid → no false RUNTIME_DIVERGENCE."""
        prepared = _prepared_sakura(final_submit_identified=False, authorized=True)
        ok_auth, auth_reasons = authorize_snapshot(prepared, _sakura_evidence())
        self.assertTrue(ok_auth, auth_reasons)

        ok, reasons = await validate_snapshot_invariants(prepared)
        self.assertTrue(ok, reasons)
        self.assertTrue(prepared.prep.final_submit_identified)
        self.assertNotIn("submit_target:final_submit_not_identified", reasons)


class TestSubmitTargetMissing(unittest.IsolatedAsyncioTestCase):
    async def test_missing_live_target_blocks(self):
        prepared = _prepared_sakura(final_submit_identified=True, authorized=True)

        async def _eval(js, arg=None):
            if "captcha" in str(js).lower():
                return False
            if "hint_candidates" in str(js) or "hintMatches" in str(js):
                return {"ok": False, "reason": "submit_missing", "candidates": []}
            return {"valid": False, "reason": "submit_missing", "matches": 0}

        prepared.page.evaluate = AsyncMock(side_effect=_eval)
        ok, reasons = await validate_snapshot_invariants(prepared)
        self.assertFalse(ok)
        self.assertTrue(any("submit_target:submit_missing" in r for r in reasons))


class TestSubmitTargetChangesForm(unittest.IsolatedAsyncioTestCase):
    async def test_scope_change_blocks(self):
        prepared = _prepared_sakura(final_submit_identified=True, authorized=True)
        prepared.prep.contact_form_scope = "form#other"
        ok, reasons = await validate_snapshot_invariants(prepared)
        self.assertFalse(ok)
        self.assertTrue(any("form_identity" in r for r in reasons))


class TestAmbiguousSubmitButtons(unittest.IsolatedAsyncioTestCase):
    async def test_ambiguous_blocks(self):
        page = MagicMock()
        page.url = "https://example.com/contact/"

        async def _eval(js, arg=None):
            if "hint_candidates" in str(js) or "hintMatches" in str(js):
                return {
                    "ok": True,
                    "hint_candidates": [
                        {"tag": "input", "type": "submit", "value": "送信A", "label": "送信A", "visible": True, "enabled": True, "inSelectedForm": True, "domOrder": 0, "name": "", "id": "", "className": "", "formAction": ""},
                        {"tag": "input", "type": "submit", "value": "問い合わせ", "label": "問い合わせ", "visible": True, "enabled": True, "inSelectedForm": True, "domOrder": 1, "name": "", "id": "", "className": "", "formAction": ""},
                    ],
                }
            if "finalBtn" in str(js):
                return "FINAL_SUBMIT_READY"
            return {"valid": False, "reason": "submit_ambiguous", "matches": 2}

        page.evaluate = AsyncMock(side_effect=_eval)
        ok, record, reasons = await resolve_canonical_submit_target(
            page, contact_form_scope=SAKURA_SCOPE, submit_selector=SAKURA_SUBMIT,
        )
        self.assertFalse(ok)
        self.assertTrue(any("submit_ambiguous" in r for r in reasons))


class TestHiddenDisabledButton(unittest.IsolatedAsyncioTestCase):
    async def test_hidden_blocks(self):
        page = MagicMock()
        page.url = "https://example.com/contact/"

        async def _eval(js, arg=None):
            if "hint_candidates" in str(js) or "hintMatches" in str(js):
                return _discovery_response()
            if "finalBtn" in str(js):
                return "FORM_ENTRY"
            return _live_valid(valid=False, reason="submit_hidden", visible=False)

        page.evaluate = AsyncMock(side_effect=_eval)
        ok, _, reasons = await resolve_canonical_submit_target(
            page, contact_form_scope=SAKURA_SCOPE, submit_selector=SAKURA_SUBMIT,
        )
        self.assertFalse(ok)
        self.assertTrue(any("submit_hidden" in r for r in reasons))

    async def test_disabled_blocks(self):
        page = MagicMock()
        page.url = "https://example.com/contact/"

        async def _eval(js, arg=None):
            if "hint_candidates" in str(js) or "hintMatches" in str(js):
                return _discovery_response()
            if "finalBtn" in str(js):
                return "FORM_ENTRY"
            return _live_valid(valid=False, reason="submit_disabled", enabled=False)

        page.evaluate = AsyncMock(side_effect=_eval)
        ok, _, reasons = await resolve_canonical_submit_target(
            page, contact_form_scope=SAKURA_SCOPE, submit_selector=SAKURA_SUBMIT,
        )
        self.assertFalse(ok)
        self.assertTrue(any("submit_disabled" in r for r in reasons))


class TestCaptchaAppears(unittest.IsolatedAsyncioTestCase):
    async def test_captcha_blocks(self):
        prepared = _prepared_sakura(final_submit_identified=True, authorized=True)

        async def _eval(js, arg=None):
            if "captcha" in str(js).lower():
                return True
            return _live_valid()

        prepared.page.evaluate = AsyncMock(side_effect=_eval)
        ok, reasons = await validate_snapshot_invariants(prepared)
        self.assertFalse(ok)
        self.assertTrue(any("captcha" in r for r in reasons))


class TestConfirmationStepFinalSubmit(unittest.IsolatedAsyncioTestCase):
    async def test_multistep_final_selector_still_validates(self):
        confirm_submit = 'form[data-ari-form-scope="contact"] input[name="submitConfirm"]'
        page = MagicMock()
        page.url = "https://example.com/confirm/"

        async def _eval(js, arg=None):
            if "hint_candidates" in str(js) or "hintMatches" in str(js):
                return {
                    "ok": True,
                    "hint_candidates": [{
                        "tag": "input", "type": "submit", "name": "submitConfirm", "id": "",
                        "className": "", "value": "送信する", "text": "", "label": "送信する",
                        "visible": True, "enabled": True, "inSelectedForm": True, "domOrder": 0,
                        "formAction": "/confirm/",
                    }],
                }
            if "finalBtn" in str(js):
                return "FINAL_SUBMIT_READY"
            return {
                "valid": True, "reason": "valid", "matches": 1, "visible": True, "enabled": True,
                "element_type": "input:submit", "label": "送信する", "final_submit_eligible": True,
            }

        page.evaluate = AsyncMock(side_effect=_eval)
        ok, record, reasons = await resolve_canonical_submit_target(
            page, contact_form_scope='form[data-ari-form-scope="contact"]', submit_selector=confirm_submit,
        )
        self.assertTrue(ok, reasons)
        self.assertTrue(record.get("final_submit_eligible"))


class TestSingleSnapshotContract(unittest.TestCase):
    def test_shared_prepare_uses_canonical_resolver(self):
        import shared_form_prepare as sfp
        src = inspect.getsource(sfp.shared_prepare_form)
        self.assertIn("resolve_canonical_submit_target", src)
        self.assertNotIn("if final_btn:\n        result.final_submit_identified = True", src)


class TestDuplicateSubmitProtection(unittest.IsolatedAsyncioTestCase):
    async def test_already_submitted_blocked(self):
        prepared = _prepared_sakura(final_submit_identified=True, authorized=True, )
        prepared.submitted = True
        ok, reasons = await validate_snapshot_invariants(prepared)
        self.assertFalse(ok)
        self.assertTrue(any("duplicate_submit" in r for r in reasons))


class TestExistingSuccessPaths(unittest.TestCase):
    def test_cf7_and_dom_paths_unchanged(self):
        import form_sender
        src = inspect.getsource(form_sender.submit_prepared_form)
        self.assertIn("_click_submit", src)
        self.assertIn("cf7_feedback", src)


class TestDeriveFinalSubmitIdentified(unittest.TestCase):
    def test_derives_from_canonical_record(self):
        record = build_submit_target_record(
            submit_selector=SAKURA_SUBMIT,
            contact_form_scope=SAKURA_SCOPE,
            live_state=_live_valid(),
        )
        self.assertTrue(derive_final_submit_identified(submit_selector=SAKURA_SUBMIT, submit_target_record=record))

    def test_false_when_record_invalid(self):
        self.assertFalse(derive_final_submit_identified(submit_selector=SAKURA_SUBMIT, submit_target_record={}))


if __name__ == "__main__":
    unittest.main()
