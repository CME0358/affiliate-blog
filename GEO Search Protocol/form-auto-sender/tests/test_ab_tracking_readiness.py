"""P1 — A/B assignment tracking readiness (no production enable)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent


def _load_module(name: str, rel_path: str):
    path = _BASE / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


ab_assignment = _load_module("ab_assignment_test", "ari_pipeline/ab_assignment.py")
ab_tracking = _load_module("ab_tracking_test", "ari_pipeline/ab_tracking.py")

assign_ab_arm = ab_assignment.assign_ab_arm
arm_metadata = ab_assignment.arm_metadata
encode_ab_notes = ab_tracking.encode_ab_notes
parse_ab_notes = ab_tracking.parse_ab_notes
recommended_schema_changes = ab_tracking.recommended_schema_changes


class TestAbAssignment(unittest.TestCase):
    def test_disabled_returns_none(self):
        self.assertIsNone(assign_ab_arm("abc123", enabled=False))

    def test_deterministic_when_enabled(self):
        a = assign_ab_arm("candidate_x", enabled=True)
        b = assign_ab_arm("candidate_x", enabled=True)
        self.assertEqual(a, b)
        self.assertIn(a, ("A", "B", "C"))

    def test_arm_metadata_production_default(self):
        meta = arm_metadata(None)
        self.assertEqual(meta["message_version"], "ARI_MESSAGE_V1")
        self.assertFalse(meta["uses_preview"])

    def test_notes_json_roundtrip(self):
        notes = encode_ab_notes(
            ab_arm="C",
            message_version="ARI_MESSAGE_V2",
            preview_token="tok123",
            preview_created_at="2026-08-15T00:00:00+00:00",
        )
        parsed = parse_ab_notes(notes)
        self.assertEqual(parsed["ab_arm"], "C")
        self.assertEqual(parsed["preview_token"], "tok123")

    def test_schema_evaluation_no_columns_now(self):
        rec = recommended_schema_changes()
        self.assertFalse(rec["add_columns_now"])


if __name__ == "__main__":
    unittest.main()
