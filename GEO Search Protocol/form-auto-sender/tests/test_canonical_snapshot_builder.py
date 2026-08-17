"""Canonical Snapshot Builder v2 tests."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from shared_form_prepare import (
    SEMANTIC_EVIDENCE_SCHEMA_VERSION,
    SEMANTIC_EVIDENCE_SCHEMA_VERSION_V1,
    build_canonical_prepared_snapshot,
    build_preflight_semantic_evidence,
    build_semantic_evidence_record,
    compute_semantic_hash,
    evidence_schema_version,
    extract_semantic_hash_payload,
    is_evidence_compatible,
    serialize_canonical_snapshot,
)


HARUDESIGN_PROD_FIELDS = {
    "address_field": 'input[name="your-email"]',
    "address_line1_field": "",
    "address_line2_field": "",
    "age_field": "",
    "city_field": "",
    "company_field": "",
    "contact_form_scope": 'form[data-ari-form-scope="contact"]',
    "email_field": 'input[name="your-email"]',
    "furigana_format": "",
    "furigana_name_field": "",
    "gender_field": "",
    "message_field": 'textarea[name="your-message"]',
    "name_field": 'input[name="your-name"]',
    "phone_field": 'input[name="your-tel"]',
    "postal_code_field": "",
    "prefecture_field": "",
    "submit_button": 'form input[type="submit"]',
}

HARUDESIGN_FIELD_MAP = {
    "company": "MISSING",
    "name": "FILLED",
    "email": "FILLED",
    "phone": "FILLED",
    "subject": "MISSING",
    "message": "FILLED",
    "consent": "NOT_REQUIRED",
}


def _harudesign_canonical(**overrides):
    snap = build_canonical_prepared_snapshot(
        form_url="https://harudesign.tokyo/contact/",
        fields=HARUDESIGN_PROD_FIELDS,
        filled={"name": "FILLED", "email": "FILLED", "phone": "FILLED", "message": "FILLED", "consent": "NOT_REQUIRED"},
        choice_log={"applied": [], "post_fill": {"applied": []}},
        field_map=HARUDESIGN_FIELD_MAP,
        selection={"variant": "ARI_MESSAGE_V1", "message_length": 952},
        contact_form_scope='form[data-ari-form-scope="contact"]',
    )
    snap.update(overrides)
    return snap


class TestFullSnapshotPreservation(unittest.TestCase):
    def test_export_reload_preserves_hash(self):
        canonical = _harudesign_canonical()
        record = build_semantic_evidence_record(canonical_snapshot=canonical, source="test")
        export_fn = {
            "semantic_evidence": record,
            "preflight_mapping_hash": record["semantic_hash"],
            "prepare_snapshot": extract_semantic_hash_payload(canonical),
        }
        row = {"fill_no_submit": export_fn, "form_url": canonical["form_url"]}
        loaded = build_preflight_semantic_evidence(row)
        self.assertEqual(loaded["semantic_evidence_schema_version"], SEMANTIC_EVIDENCE_SCHEMA_VERSION)
        self.assertEqual(loaded["semantic_hash"], record["semantic_hash"])
        ok, reasons = is_evidence_compatible(loaded)
        self.assertTrue(ok, reasons)


class TestHarudesignRegression(unittest.TestCase):
    def test_production_equivalent_hash(self):
        canonical = _harudesign_canonical()
        h = compute_semantic_hash(canonical)
        self.assertEqual(h, "b2506fecbc5fb0b4")
        self.assertTrue(len(canonical["fields"]) >= 10)


class TestDictOrdering(unittest.TestCase):
    def test_insertion_order_independent_hash(self):
        a = _harudesign_canonical()
        b = _harudesign_canonical()
        b["fields"] = dict(reversed(list(b["fields"].items())))
        self.assertEqual(compute_semantic_hash(a), compute_semantic_hash(b))
        self.assertEqual(serialize_canonical_snapshot(a), serialize_canonical_snapshot(b))


class TestFieldOrdering(unittest.TestCase):
    def test_discovery_order_independent(self):
        fields_a = {"name_field": "#n", "email_field": "#e", "message_field": "#m", "submit_button": "form input[type=submit]"}
        fields_b = {"submit_button": "form input[type=submit]", "message_field": "#m", "email_field": "#e", "name_field": "#n"}
        fm = {"company": "MISSING", "name": "FILLED", "email": "FILLED", "phone": "MISSING",
              "subject": "MISSING", "message": "FILLED", "consent": "FILLED"}
        s1 = build_canonical_prepared_snapshot(fields=fields_a, filled={}, choice_log={}, field_map=fm)
        s2 = build_canonical_prepared_snapshot(fields=fields_b, filled={}, choice_log={}, field_map=fm)
        self.assertEqual(compute_semantic_hash(s1), compute_semantic_hash(s2))


class TestTrueFieldMappingChange(unittest.TestCase):
    def test_field_map_change_changes_hash(self):
        a = _harudesign_canonical()
        b = _harudesign_canonical()
        b["field_map"] = dict(b["field_map"])
        b["field_map"]["phone"] = "MISSING"
        self.assertNotEqual(compute_semantic_hash(a), compute_semantic_hash(b))


class TestRequiredChoiceChange(unittest.TestCase):
    def test_prefecture_change_changes_hash(self):
        a = _harudesign_canonical()
        b = _harudesign_canonical()
        b["choices_applied"] = [{"category": "PREFECTURE", "name": "zip2", "value": "13", "label": "東京都"}]
        self.assertNotEqual(compute_semantic_hash(a), compute_semantic_hash(b))


class TestFormIdentityChange(unittest.TestCase):
    def test_scope_change_changes_hash(self):
        a = _harudesign_canonical()
        b = _harudesign_canonical(contact_form_scope='form#other')
        self.assertNotEqual(compute_semantic_hash(a), compute_semantic_hash(b))


class TestSubmitTargetChange(unittest.TestCase):
    def test_submit_target_change_changes_hash(self):
        a = _harudesign_canonical()
        b = _harudesign_canonical()
        b["fields"] = dict(b["fields"])
        b["fields"]["submit_button"] = 'form input[name="send"]'
        self.assertNotEqual(compute_semantic_hash(a), compute_semantic_hash(b))


class TestSchemaVersionMismatch(unittest.TestCase):
    def test_v1_not_compatible(self):
        v1 = {
            "semantic_evidence_schema_version": SEMANTIC_EVIDENCE_SCHEMA_VERSION_V1,
            "fields": {},
            "field_map": HARUDESIGN_FIELD_MAP,
            "mapping_hash": "abc",
        }
        ok, reasons = is_evidence_compatible(v1)
        self.assertFalse(ok)
        self.assertTrue(any("schema_version_mismatch" in r for r in reasons))

    def test_v2_compatible(self):
        record = build_semantic_evidence_record(canonical_snapshot=_harudesign_canonical())
        loaded = build_preflight_semantic_evidence({"fill_no_submit": {"semantic_evidence": record}})
        ok, reasons = is_evidence_compatible(loaded)
        self.assertTrue(ok, reasons)


class TestHistoricalEvidenceImmutable(unittest.TestCase):
    def test_refresh_creates_new_record_without_mutating_historical(self):
        historical_row = {
            "domain": "example.com",
            "fill_no_submit": {
                "field_map": HARUDESIGN_FIELD_MAP,
                "contact_form_scope": 'form[data-ari-form-scope="contact"]',
                "mapping_hash": None,
            },
        }
        historical_copy = copy.deepcopy(historical_row)
        refresh_record = build_semantic_evidence_record(
            canonical_snapshot=_harudesign_canonical(),
            source="semantic_refresh",
            refreshed_at="2026-08-12T19:00:00",
            historical_schema_version=SEMANTIC_EVIDENCE_SCHEMA_VERSION_V1,
        )
        self.assertEqual(refresh_record["semantic_evidence_schema_version"], SEMANTIC_EVIDENCE_SCHEMA_VERSION)
        self.assertEqual(historical_row, historical_copy)
        self.assertNotIn("semantic_evidence", historical_row["fill_no_submit"])


if __name__ == "__main__":
    unittest.main()
