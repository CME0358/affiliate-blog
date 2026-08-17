"""Semantic policy evidence compatibility regression tests."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

import run_ari_terminal_production as terminal
from inquiry_purpose_semantics import REASON_NO_COMPATIBLE
from semantic_policy import (
    SEMANTIC_POLICY_VERSION,
    SEMANTIC_REFRESH_REQUIRED,
    assess_production_evidence_eligibility,
    current_semantic_policy_provenance,
    is_semantic_policy_compatible,
    semantic_policy_fingerprint,
)
from shared_form_prepare import (
    SEMANTIC_EVIDENCE_SCHEMA_VERSION,
    build_semantic_evidence_record,
    compare_runtime_snapshots,
    compute_semantic_hash,
    is_evidence_compatible,
    is_evidence_schema_and_hash_compatible,
)


def _base_snapshot(**overrides) -> dict:
    snap = {
        "form_url": "http://example.com/contact",
        "contact_form_scope": "form.contact",
        "submit_target": "form input[type=\"submit\"]",
        "fields": {
            "name_field": "input[name=\"name\"]",
            "email_field": "input[name=\"email\"]",
            "message_field": "textarea",
            "submit_button": "form input[type=\"submit\"]",
        },
        "field_map": {
            "company": "MISSING",
            "name": "FILLED",
            "email": "FILLED",
            "phone": "MISSING",
            "subject": "MISSING",
            "message": "FILLED",
            "consent": "NOT_REQUIRED",
        },
        "choices_applied": [],
        "choices_post_fill": [],
        "message_variant": "ARI_MESSAGE_V1",
        "message_length": 952,
        "consent": "NOT_REQUIRED",
    }
    snap.update(overrides)
    return snap


def _current_evidence(**snap_overrides) -> dict:
    return build_semantic_evidence_record(
        canonical_snapshot=_base_snapshot(**snap_overrides),
        source="test",
    )


def _old_policy_evidence(**snap_overrides) -> dict:
    record = _current_evidence(**snap_overrides)
    record.pop("semantic_policy_version", None)
    record.pop("semantic_policy_fingerprint", None)
    record.pop("semantic_policy_components", None)
    return record


class TestSemanticPolicyIdentity(unittest.TestCase):
    def test_current_policy_provenance_stable(self):
        p1 = current_semantic_policy_provenance()
        p2 = current_semantic_policy_provenance()
        self.assertEqual(p1, p2)
        self.assertEqual(p1["semantic_policy_version"], SEMANTIC_POLICY_VERSION)
        self.assertEqual(len(p1["semantic_policy_fingerprint"]), 16)


class TestEligibilityGate(unittest.TestCase):
    def test_current_policy_evidence_eligible(self):
        ev = _current_evidence()
        status, reasons = assess_production_evidence_eligibility(
            ev, schema_compatible_fn=is_evidence_schema_and_hash_compatible,
        )
        self.assertEqual(status, "ELIGIBLE")
        self.assertEqual(reasons, [])
        ok, _ = is_evidence_compatible(ev)
        self.assertTrue(ok)

    def test_old_policy_evidence_requires_refresh(self):
        ev = _old_policy_evidence()
        status, reasons = assess_production_evidence_eligibility(
            ev, schema_compatible_fn=is_evidence_schema_and_hash_compatible,
        )
        self.assertEqual(status, SEMANTIC_REFRESH_REQUIRED)
        self.assertTrue(any(SEMANTIC_REFRESH_REQUIRED in r for r in reasons))
        ok, policy_reasons = is_semantic_policy_compatible(ev)
        self.assertFalse(ok)

    def test_paintclub_old_evidence_not_eligible(self):
        old = _old_policy_evidence(choices_applied=[])
        status, _ = assess_production_evidence_eligibility(
            old, schema_compatible_fn=is_evidence_schema_and_hash_compatible,
        )
        self.assertEqual(status, SEMANTIC_REFRESH_REQUIRED)

        refreshed = _current_evidence(
            choices_applied=[
                {
                    "category": "INQUIRY_CATEGORY",
                    "name": "問合せ種別",
                    "label": "ご相談 / ご依頼 / その他",
                },
            ],
        )
        status2, _ = assess_production_evidence_eligibility(
            refreshed, schema_compatible_fn=is_evidence_schema_and_hash_compatible,
        )
        self.assertEqual(status2, "ELIGIBLE")
        self.assertNotEqual(refreshed["semantic_hash"], old["semantic_hash"])

    def test_compatible_choice_stable_hash(self):
        choice = {
            "category": "INQUIRY_CATEGORY",
            "name": "問合せ種別",
            "label": "ご相談 / ご依頼 / その他",
        }
        ev1 = _current_evidence(choices_applied=[choice], choices_post_fill=[choice])
        ev2 = _current_evidence(choices_applied=[choice], choices_post_fill=[choice])
        self.assertEqual(ev1["semantic_hash"], ev2["semantic_hash"])
        ok, _ = is_evidence_compatible(ev1)
        self.assertTrue(ok)

    def test_no_inquiry_field_policy_upgrade_still_valid(self):
        ev = _current_evidence(choices_applied=[], choices_post_fill=[])
        status, _ = assess_production_evidence_eligibility(
            ev, schema_compatible_fn=is_evidence_schema_and_hash_compatible,
        )
        self.assertEqual(status, "ELIGIBLE")

    def test_batch_lock_rejects_stale_evidence(self):
        eligible, meta = terminal.compute_eligible_unsent()
        self.assertIn("skip_reasons", meta)
        stale_domains = [d for d, r in meta["skip_reasons"].items() if r == SEMANTIC_REFRESH_REQUIRED]
        if not stale_domains:
            self.skipTest("no stale evidence domains in current preflight pool")
        self.assertGreater(len(stale_domains), 0)


class TestInquiryPurposePreserved(unittest.TestCase):
    def test_incompatible_purpose_form_not_suitable_path(self):
        from preflight_classifier import FORM_NOT_SUITABLE, classify_preflight

        fn = {
            "field_map": {"name": "FILLED", "email": "FILLED", "message": "FILLED", "consent": "NOT_REQUIRED"},
            "reason": REASON_NO_COMPATIBLE,
            "required_choices": {"unsuitable": [{"reason": REASON_NO_COMPATIBLE}]},
        }
        cls, reason, _ = classify_preflight({"fill_no_submit": fn})
        self.assertEqual(cls, FORM_NOT_SUITABLE)

    def test_purpose_material_change_diverges(self):
        pre = build_semantic_evidence_record(
            canonical_snapshot=_base_snapshot(
                choices_applied=[{"category": "INQUIRY_CATEGORY", "name": "t", "label": "その他"}],
            ),
        )
        prod_snap = _base_snapshot(
            choices_applied=[{"category": "INQUIRY_CATEGORY", "name": "t", "label": "資料請求"}],
        )
        prod = {
            "mapping_hash": compute_semantic_hash(prod_snap),
            "field_map": prod_snap["field_map"],
            "choices_applied": prod_snap["choices_applied"],
            "contact_form_scope": prod_snap["contact_form_scope"],
        }
        diverged, reasons = compare_runtime_snapshots(
            {"mapping_hash": pre["semantic_hash"], **pre["canonical_snapshot"]},
            prod,
        )
        self.assertTrue(diverged)
        self.assertTrue(any("mapping_hash" in r for r in reasons))


class TestTerminalLockImmutability(unittest.TestCase):
    def test_existing_lock_unchanged(self):
        lock_path = _BASE.parent.parent.parent / "70_outputs/5-Day-Sales-Sprint/ARI-Terminal-Production-Batch-TERMINAL-20260813-095059-10.json"
        if not lock_path.exists():
            self.skipTest("terminal lock missing")
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        self.assertTrue(lock.get("immutable"))
        self.assertEqual(lock.get("candidate_count"), 10)
        domains = [c["domain"] for c in lock["candidates"]]
        self.assertIn("paintclub.jp", domains)
        self.assertEqual(len(domains), 10)

    def test_historical_results_immutable(self):
        results_path = _BASE.parent.parent.parent / "70_outputs/5-Day-Sales-Sprint/ARI-Terminal-Production-Batch-TERMINAL-20260813-095059-10-Results.json"
        if not results_path.exists():
            self.skipTest("terminal results missing")
        data = json.loads(results_path.read_text(encoding="utf-8"))
        paint = next(r for r in data["results"] if r["domain"] == "paintclub.jp")
        self.assertEqual(paint["submission_state"], "RUNTIME_DIVERGENCE")
        self.assertFalse(paint.get("attempted"))


if __name__ == "__main__":
    unittest.main()
