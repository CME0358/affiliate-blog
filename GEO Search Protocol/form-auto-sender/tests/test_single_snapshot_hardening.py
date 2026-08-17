"""Single-Snapshot Production Hardening tests."""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from ari_pipeline.conversion_tracking import record_auto_reply, update_reply_tracking
from shared_form_prepare import (
    FormPrepareResult,
    PreparedFormSnapshot,
    RUNTIME_DIVERGENCE,
    authorize_snapshot,
    build_mapping_snapshot,
    build_preflight_semantic_evidence,
    build_semantic_evidence_record,
    compute_mapping_hash,
    mark_snapshot_authorized,
    prepare_once,
    validate_snapshot_invariants,
    SEMANTIC_EVIDENCE_SCHEMA_VERSION,
)


def _base_snap(**overrides):
    snap = build_mapping_snapshot(
        fields={"name_field": "#n", "email_field": "#e", "message_field": "#m", "submit_button": "form input[type=submit]"},
        filled={"name": "FILLED", "email": "FILLED", "message": "FILLED", "consent": "FILLED"},
        choice_log={"applied": [], "post_fill": {"applied": []}},
        field_map={"company": "MISSING", "name": "FILLED", "email": "FILLED", "phone": "MISSING",
                   "subject": "MISSING", "message": "FILLED", "consent": "FILLED"},
        contact_form_scope='form[data-ari-form-scope="contact"]',
    )
    snap.update(overrides)
    snap["mapping_hash"] = compute_mapping_hash(snap)
    return snap


def _v2_evidence(snap: dict) -> dict:
    canonical = {
        "semantic_evidence_schema_version": SEMANTIC_EVIDENCE_SCHEMA_VERSION,
        "form_url": "https://example.com/contact",
        "submit_target": (snap.get("fields") or {}).get("submit_button", "form input[type=submit]"),
        "contact_form_scope": snap.get("contact_form_scope", ""),
        "fields": snap.get("fields") or {},
        "field_map": snap.get("field_map") or {},
        "choices_applied": snap.get("choices_applied") or [],
        "choices_post_fill": snap.get("choices_post_fill") or [],
        "message_variant": snap.get("message_variant", ""),
        "message_length": snap.get("message_length", 0),
        "consent": snap.get("consent", "MISSING"),
    }
    record = build_semantic_evidence_record(canonical_snapshot=canonical)
    return build_preflight_semantic_evidence({"fill_no_submit": {"semantic_evidence": record}})


def _prepared_from_snap(snap: dict, **kwargs) -> PreparedFormSnapshot:
    prep = FormPrepareResult(
        ok=True,
        fields={"name_field": "#n", "email_field": "#e", "message_field": "#m",
                "submit_button": snap.get("fields", {}).get("submit_button", "form input[type=submit]"),
                "contact_form_scope": snap.get("contact_form_scope")},
        field_map=snap["field_map"],
        contact_form_scope=snap.get("contact_form_scope"),
        mapping_hash=snap["mapping_hash"],
        snapshot=snap,
        final_submit_identified=True,
    )
    page = MagicMock()
    page.is_closed.return_value = False
    page.url = "https://example.com/contact"

    async def _eval(js, arg=None):
        if "captcha" in str(js).lower():
            return False
        if "fields" in str(js) or "_field" in str(js):
            return []
        return {
            "valid": True,
            "reason": "valid",
            "matches": 1,
            "visible": True,
            "enabled": True,
            "element_type": "input:submit",
            "label": "送信",
            "final_submit_eligible": True,
        }

    page.evaluate = AsyncMock(side_effect=_eval)
    baseline = {
        "form_url": "https://example.com/contact",
        "page_url": "https://example.com/contact",
        "contact_form_scope": snap.get("contact_form_scope"),
        "field_map": dict(snap["field_map"]),
        "mapping_hash": snap["mapping_hash"],
        "fields_fingerprint": "abc123",
        "submit_button": snap.get("fields", {}).get("submit_button", "form input[type=submit]"),
        "final_submit_identified": True,
        "canonical_submit_target": {
            "submit_selector": snap.get("fields", {}).get("submit_button", "form input[type=submit]"),
            "contact_form_scope": snap.get("contact_form_scope", ""),
            "visible": True,
            "enabled": True,
            "final_submit_eligible": True,
        },
    }
    return PreparedFormSnapshot(
        prep=prep,
        form_url="https://example.com/contact",
        page_url="https://example.com/contact",
        page=page,
        invariant_baseline=baseline,
        **kwargs,
    )


class TestStableFormEligible(unittest.TestCase):
    def test_identical_snapshot_authorizes(self):
        snap = _base_snap()
        prepared = _prepared_from_snap(snap)
        ok, reasons = authorize_snapshot(prepared, _v2_evidence(snap))
        self.assertTrue(ok, reasons)
        self.assertEqual(reasons, [])


class TestDynamicPrefectureSinglePrepare(unittest.TestCase):
    def test_single_prepare_no_false_divergence_from_second_prepare(self):
        """Same session snapshot compared to itself — no double-prepare false positive."""
        snap = _base_snap(choices_applied=[
            {"category": "PREFECTURE", "name": "zip2", "value": "13", "label": "東京都"},
        ], choices_post_fill=[{"category": "PREFECTURE", "name": "zip2", "value": "13"}])
        snap["mapping_hash"] = compute_mapping_hash(snap)
        prepared = _prepared_from_snap(snap)
        ok, reasons = authorize_snapshot(prepared, _v2_evidence(snap))
        self.assertTrue(ok, reasons)

    def test_send_form_uses_prepare_once_not_double_prepare(self):
        import form_sender
        src = inspect.getsource(form_sender.send_form)
        self.assertIn("prepare_once", src)
        self.assertNotIn("shared_prepare_form(", src)


class TestTrueSemanticFieldChange(unittest.TestCase):
    def test_field_regression_blocks(self):
        pre = _base_snap()
        prod_snap = _base_snap(field_map={
            "company": "MISSING", "name": "FILLED", "email": "FILLED", "phone": "MISSING",
            "subject": "MISSING", "message": "MISSING", "consent": "FILLED",
        })
        prod_snap["mapping_hash"] = compute_mapping_hash(prod_snap)
        prepared = _prepared_from_snap(prod_snap)
        ok, reasons = authorize_snapshot(prepared, _v2_evidence(pre))
        self.assertFalse(ok)
        self.assertTrue(any("field_regression" in r or "mapping_hash" in r for r in reasons))


class TestRequiredChoiceSemanticChange(unittest.TestCase):
    def test_choice_change_blocks(self):
        pre = _base_snap(choices_applied=[
            {"category": "PREFECTURE", "name": "zip2", "value": "13", "label": "東京都"},
        ])
        pre["mapping_hash"] = compute_mapping_hash(pre)
        prod = _base_snap(choices_applied=[])
        prod["mapping_hash"] = compute_mapping_hash(prod)
        prepared = _prepared_from_snap(prod)
        ok, reasons = authorize_snapshot(prepared, _v2_evidence(pre))
        self.assertFalse(ok)
        self.assertTrue(any("mapping_hash" in r for r in reasons))


class TestCaptchaAfterPrepare(unittest.IsolatedAsyncioTestCase):
    async def test_captcha_blocks_submit(self):
        snap = _base_snap()
        prepared = _prepared_from_snap(snap, authorized=True)
        prepared.authorization_hash = snap["mapping_hash"]
        prepared.page.evaluate = AsyncMock(return_value=True)
        ok, reasons = await validate_snapshot_invariants(prepared)
        self.assertFalse(ok)
        self.assertTrue(any("captcha" in r for r in reasons))


class TestFormIdentityChange(unittest.IsolatedAsyncioTestCase):
    async def test_scope_change_blocks(self):
        snap = _base_snap()
        prepared = _prepared_from_snap(snap, authorized=True)
        prepared.authorization_hash = snap["mapping_hash"]
        prepared.prep.contact_form_scope = 'form[data-ari-form-scope="other"]'
        ok, reasons = await validate_snapshot_invariants(prepared)
        self.assertFalse(ok)
        self.assertTrue(any("form_identity" in r for r in reasons))


class TestSubmitTargetChange(unittest.IsolatedAsyncioTestCase):
    async def test_submit_target_change_blocks(self):
        snap = _base_snap()
        prepared = _prepared_from_snap(snap, authorized=True)
        prepared.authorization_hash = snap["mapping_hash"]
        prepared.prep.fields["submit_button"] = "form input[name=other]"
        ok, reasons = await validate_snapshot_invariants(prepared)
        self.assertFalse(ok)
        self.assertTrue(any("submit_target" in r for r in reasons))


class TestPageNavigationAfterAuth(unittest.IsolatedAsyncioTestCase):
    async def test_navigation_blocks(self):
        snap = _base_snap()
        prepared = _prepared_from_snap(snap, authorized=True)
        prepared.authorization_hash = snap["mapping_hash"]
        prepared.page.url = "https://example.com/other-page"
        ok, reasons = await validate_snapshot_invariants(prepared)
        self.assertFalse(ok)
        self.assertTrue(any("navigation" in r for r in reasons))


class TestDuplicateSubmitProtection(unittest.IsolatedAsyncioTestCase):
    async def test_second_submit_blocked(self):
        snap = _base_snap()
        prepared = _prepared_from_snap(snap, authorized=True, submitted=True)
        prepared.authorization_hash = snap["mapping_hash"]
        ok, reasons = await validate_snapshot_invariants(prepared)
        self.assertFalse(ok)
        self.assertTrue(any("duplicate_submit" in r for r in reasons))

    async def test_unauthorized_submit_blocked(self):
        snap = _base_snap()
        prepared = _prepared_from_snap(snap, authorized=False)
        ok, reasons = await validate_snapshot_invariants(prepared)
        self.assertFalse(ok)
        self.assertTrue(any("not_authorized" in r for r in reasons))


class TestAutoReplyTracking(unittest.TestCase):
    def test_plazaone_auto_reply_not_positive(self):
        import tempfile
        import ari_pipeline.conversion_tracking as ct

        with tempfile.TemporaryDirectory() as tmp:
            track = Path(tmp) / "tracking.csv"
            ct.TRACKING_CSV = track
            updated, msg = record_auto_reply(
                domain="plazaone.jp",
                company_name="(株)プラザワンカンパニー",
                candidate_id="118521f3b50aeac3",
                notes="Automatic reply received",
            )
            self.assertTrue(updated, msg)
            row = ct._find_tracking_row("plazaone.jp")
            self.assertIsNotNone(row)
            self.assertEqual(row["reply_classification"], "AUTO_REPLY")
            self.assertEqual(row["positive_reply"], "false")
            self.assertEqual(row["purchase_status"], "none")
            self.assertEqual(row["notes"], "Automatic reply received")

            updated2, msg2 = record_auto_reply(
                domain="plazaone.jp",
                candidate_id="118521f3b50aeac3",
                notes="Automatic reply received",
            )
            self.assertFalse(updated2)
            self.assertEqual(msg2, "already_recorded")


class TestPreflightSemanticEvidence(unittest.TestCase):
    def test_build_from_full_preflight_row(self):
        row = {
            "fill_no_submit": {
                "field_map": {"name": "FILLED", "email": "FILLED", "message": "FILLED", "consent": "FILLED"},
                "contact_form_scope": 'form[data-ari-form-scope="contact"]',
                "required_choices": {
                    "applied": [{"category": "PREFECTURE", "name": "zip2", "label": "東京都"}],
                    "post_fill_applied": [{"category": "PREFECTURE", "name": "zip2"}],
                },
            },
        }
        ev = build_preflight_semantic_evidence(row)
        self.assertEqual(len(ev["choices_applied"]), 1)
        self.assertEqual(ev["choices_applied"][0]["category"], "PREFECTURE")


class TestRGinzaRegression(unittest.TestCase):
    def test_double_prepare_architecture_removed_from_b01(self):
        import run_ari_production_batch_b01 as b01
        src = inspect.getsource(b01._pre_send_check)
        self.assertNotIn("fill_form_no_submit", src)
        self.assertIn("preflight_semantic_evidence", src)

    def test_r_ginza_offline_hash_reconstruction(self):
        """Forensic: adding PREFECTURE to production snapshot reproduces preflight hash."""
        prod = _base_snap(choices_applied=[], choices_post_fill=[])
        prod["mapping_hash"] = compute_mapping_hash(prod)
        with_pref = dict(prod)
        with_pref["choices_applied"] = [
            {"category": "PREFECTURE", "name": "zip2", "value": None, "label": "東京都"},
        ]
        with_pref["choices_post_fill"] = [
            {"category": "PREFECTURE", "name": "zip2", "value": None},
        ]
        h_with = compute_mapping_hash(with_pref)
        h_without = compute_mapping_hash(prod)
        self.assertNotEqual(h_with, h_without)


class TestSubmitForbiddenDryPath(unittest.IsolatedAsyncioTestCase):
    async def test_submit_prepared_respects_forbidden(self):
        from form_sender import set_submit_forbidden, submit_prepared_form

        snap = _base_snap()
        prepared = mark_snapshot_authorized(_prepared_from_snap(snap))
        set_submit_forbidden(True)
        with patch("shared_form_prepare.validate_snapshot_invariants", new=AsyncMock(return_value=(True, []))):
            result = await submit_prepared_form(
                prepared, lp_url="https://example.com", message_slug="test",
            )
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "submit_forbidden")
        set_submit_forbidden(False)


if __name__ == "__main__":
    unittest.main()
