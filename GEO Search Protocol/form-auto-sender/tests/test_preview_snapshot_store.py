"""P2 — Preview snapshot store contract tests (Python)."""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent


def _load_store():
    path = _BASE / "observations" / "preview_snapshot_store.py"
    spec = importlib.util.spec_from_file_location("preview_store_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


FIXTURE = {
    "version": 1,
    "token": "py-test-token-xyz",
    "company_name": "Python Co",
    "url": "https://py.example",
    "industry": "その他",
    "created_at": "2026-08-15T00:00:00+00:00",
    "expires_at": "2027-08-15T00:00:00+00:00",
    "preview": {
        "observations": [],
        "check_summary": {"checked_count": 0, "total_teaser": 23, "check_items": []},
        "blocked": False,
    },
}


class TestPreviewSnapshotStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store_mod = _load_store()
        os.environ["PREVIEW_STORE_BACKEND"] = "memory"
        os.environ.pop("VERCEL", None)
        cls.store_mod.reset_preview_snapshot_store()

    def setUp(self):
        self.store_mod.reset_preview_snapshot_store()
        self.store = self.store_mod.create_preview_snapshot_store("memory")

    def test_save_get(self):
        self.store.save(FIXTURE)
        loaded = self.store.get("py-test-token-xyz")
        self.assertEqual(loaded["company_name"], "Python Co")

    def test_unknown_null(self):
        self.assertIsNone(self.store.get("missing"))

    def test_expired_null(self):
        expired = {**FIXTURE, "token": "exp-py", "expires_at": "2020-01-01T00:00:00+00:00"}
        self.store.save(expired)
        self.assertIsNone(self.store.get("exp-py"))

    def test_delete(self):
        self.store.save(FIXTURE)
        self.assertTrue(self.store.delete("py-test-token-xyz"))
        self.assertIsNone(self.store.get("py-test-token-xyz"))

    def test_invalid_token(self):
        self.assertIsNone(self.store.get("bad token!"))

    def test_vercel_forbids_filesystem(self):
        prev = os.environ.copy()
        try:
            os.environ["VERCEL"] = "1"
            os.environ["PREVIEW_STORE_BACKEND"] = "filesystem"
            with self.assertRaises(self.store_mod.PreviewStoreError):
                self.store_mod.create_preview_snapshot_store()
        finally:
            os.environ.clear()
            os.environ.update(prev)
            self.store_mod.reset_preview_snapshot_store()

    def test_upstash_unconfigured_raises(self):
        prev = os.environ.copy()
        try:
            os.environ.pop("UPSTASH_REDIS_REST_URL", None)
            os.environ.pop("UPSTASH_REDIS_REST_TOKEN", None)
            os.environ["PREVIEW_STORE_BACKEND"] = "upstash"
            store = self.store_mod.create_preview_snapshot_store("upstash")
            with self.assertRaises(self.store_mod.PreviewStoreError):
                store.save(FIXTURE)
        finally:
            os.environ.clear()
            os.environ.update(prev)
            self.store_mod.reset_preview_snapshot_store()


if __name__ == "__main__":
    unittest.main()
