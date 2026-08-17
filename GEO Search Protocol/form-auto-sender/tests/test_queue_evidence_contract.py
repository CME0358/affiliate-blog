"""Regression tests for queue evidence producer/consumer contract — ZERO SEND."""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

import run_ari_production_batch_b01 as b01
import run_ari_fast_queue_semantic_refresh as fq_refresh
from ari_pipeline.production_queue_eligibility import assess_production_queue_eligibility
from ari_pipeline.proven_pattern_library import PROVEN_FAST_PATH, classify_candidate
from ari_pipeline.queue_evidence_contract import (
    REFRESH_ARTIFACT_ID,
    build_queue_authorization,
    terminal_consumer_eligible_offline,
    validate_queue_authorization,
)
from config import VAULT_ROOT
from semantic_policy import current_semantic_policy_provenance
from shared_form_prepare import SEMANTIC_EVIDENCE_SCHEMA_VERSION, compute_semantic_hash

OUTPUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"
R1_QUEUE = OUTPUT_DIR / "ARI-Fast-Production-Queue-2026-08-13-R1.json"
REFRESH_JSON = OUTPUT_DIR / "ARI-AUTO-READY-Semantic-Refresh-2026-08-12.json"
PREFLIGHT_JSON = OUTPUT_DIR / "ARI-Full-Preflight-2026-08-12.json"


def _mock_sent_index():
    idx = MagicMock()
    idx.should_no_resend.return_value = False
    idx.is_confirmed_sent_domain.return_value = False
    return idx


def _refresh_ready_row(domain: str = "example.co.jp", **kw) -> dict:
    prov = current_semantic_policy_provenance()
    snap = {
        "submit_target": "form input[type='submit']",
        "fields": {"email": "[name=email]", "name": "[name=name]", "message": "[name=message]"},
        "field_map": {"email": "FOUND", "name": "FOUND", "message": "FOUND"},
        "semantic_policy_version": prov["semantic_policy_version"],
        "semantic_policy_fingerprint": prov["semantic_policy_fingerprint"],
    }
    sem = {
        "semantic_evidence_schema_version": SEMANTIC_EVIDENCE_SCHEMA_VERSION,
        "semantic_policy_version": prov["semantic_policy_version"],
        "semantic_policy_fingerprint": prov["semantic_policy_fingerprint"],
        "semantic_hash": compute_semantic_hash(snap),
        "canonical_snapshot": snap,
        "field_map": snap["field_map"],
    }
    row = {
        "domain": domain,
        "refresh_outcome": "REFRESH_READY",
        "semantic_evidence_v2": sem,
        "purpose_audit": "NOT_APPLICABLE",
    }
    row.update(kw)
    return row


def _pf_row(**kw) -> dict:
    base = {
        "domain": "example.co.jp",
        "preflight_classification": "NOT_READY",
        "preflight_outcome": "UNKNOWN",
        "fill_no_submit": {
            "field_map": {"name": "FOUND", "email": "FOUND", "message": "FOUND"},
            "final_submit_identified": True,
            "multistep_state": "FINAL_SUBMIT_READY",
        },
    }
    base.update(kw)
    return base


class TestQueueAuthorization(unittest.TestCase):
    def test_build_authorization_lineage(self):
        q = {"domain": "x.co.jp", "candidate_id": "C1", "queue_revision": "R1", "production_eligibility": "production_ready"}
        rr = _refresh_ready_row("x.co.jp")
        auth = build_queue_authorization(q, rr)
        self.assertEqual(auth["authorized_semantic_hash"], rr["semantic_evidence_v2"]["semantic_hash"])
        self.assertEqual(auth["refresh_artifact_id"], REFRESH_ARTIFACT_ID)
        self.assertEqual(auth["refresh_outcome"], "REFRESH_READY")

    def test_validate_hash_mismatch(self):
        q = build_queue_authorization({"domain": "x.co.jp"}, _refresh_ready_row("x.co.jp"))
        q["authorized_semantic_hash"] = "deadbeef"
        ok, reason = validate_queue_authorization(q, _refresh_ready_row("x.co.jp"))
        self.assertFalse(ok)
        self.assertIn("semantic_hash_mismatch", reason)

    def test_validate_stale_fingerprint(self):
        rr = _refresh_ready_row()
        rr["semantic_evidence_v2"]["semantic_policy_fingerprint"] = "0" * 16
        q = build_queue_authorization({"domain": "x.co.jp"}, rr)
        ok, reason = validate_queue_authorization(q, rr)
        self.assertFalse(ok)
        self.assertIn("semantic_refresh_required", reason.lower())


class TestPreSendQueueAuthorization(unittest.IsolatedAsyncioTestCase):
    @patch("run_ari_production_batch_b01.get_sent_domain_index")
    @patch("run_ari_production_batch_b01.is_already_sent", return_value=False)
    @patch("run_ari_production_batch_b01.get_effective_sent_status", return_value="not_sent")
    async def test_not_ready_preflight_passes_with_queue_auth(self, _es, _ia, mock_get_idx):
        idx = MagicMock()
        idx.should_no_resend.return_value = False
        mock_get_idx.return_value = idx
        rr = _refresh_ready_row("legacy-not-ready.co.jp")
        pf = b01._merge_refresh_v2_evidence(_pf_row(domain="legacy-not-ready.co.jp"), rr)
        company = {
            "domain": "legacy-not-ready.co.jp",
            "company_name": "Test Co",
            "website_url": "https://legacy-not-ready.co.jp/",
            "preflight_classification": "NOT_READY",
            "preflight_outcome": "UNKNOWN",
            "queue_authorization": build_queue_authorization(
                {"domain": "legacy-not-ready.co.jp", "production_eligibility": "production_ready"},
                rr,
            ),
        }
        ok, reason, _ = await b01._pre_send_check(company, pf)
        self.assertTrue(ok, reason)
        self.assertEqual(reason, "")

    @patch("run_ari_production_batch_b01.get_sent_domain_index")
    @patch("run_ari_production_batch_b01.is_already_sent", return_value=False)
    @patch("run_ari_production_batch_b01.get_effective_sent_status", return_value="not_sent")
    async def test_legacy_path_still_requires_auto_ready(self, _es, _ia, mock_get_idx):
        idx = MagicMock()
        idx.should_no_resend.return_value = False
        mock_get_idx.return_value = idx
        pf = _pf_row(domain="example.co.jp", preflight_classification="NOT_READY", preflight_outcome="UNKNOWN")
        company = {
            "domain": "example.co.jp",
            "company_name": "Test Co",
            "website_url": "https://example.co.jp/",
            "preflight_classification": "NOT_READY",
            "preflight_outcome": "UNKNOWN",
        }
        ok, reason, _ = await b01._pre_send_check(company, pf)
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("preflight_not_auto_ready"))


class TestR1ProducerConsumerParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not R1_QUEUE.exists():
            raise unittest.SkipTest("R1 queue missing")
        cls.queue = json.loads(R1_QUEUE.read_text())
        cls.candidates = cls.queue.get("candidates") or []
        cls.refresh_by = {}
        if REFRESH_JSON.exists():
            for r in json.loads(REFRESH_JSON.read_text()).get("results", []):
                if r.get("domain"):
                    cls.refresh_by[r["domain"]] = r
        cls.pf_by = {}
        if PREFLIGHT_JSON.exists():
            for r in json.loads(PREFLIGHT_JSON.read_text()).get("results", []):
                if r.get("domain"):
                    cls.pf_by[r["domain"]] = r

    def test_r1_queue_has_authorization_after_rebuild(self):
        """Existing R1 may lack queue_authorization; runtime builds from refresh row."""
        if not self.candidates:
            self.skipTest("empty R1")
        sample = self.candidates[0]
        rr = self.refresh_by.get(sample["domain"])
        if not rr:
            self.skipTest("no refresh row")
        auth = sample.get("queue_authorization") or build_queue_authorization(sample, rr)
        ok, _ = validate_queue_authorization(auth, rr)
        self.assertTrue(ok)

    @patch("ari_pipeline.production_queue_eligibility.is_evidence_schema_and_hash_compatible", return_value=(True, []))
    def test_producer_ready_count(self, _schema):
        ready = 0
        for c in self.candidates:
            dom = c["domain"]
            pf = self.pf_by.get(dom, {})
            merged = {**pf, **c}
            ok, _, _ = assess_production_queue_eligibility(
                merged, refresh_row=self.refresh_by.get(dom), sent_index=_mock_sent_index(),
            )
            if ok:
                ready += 1
        self.assertGreaterEqual(ready, 10)

    def test_consumer_ready_after_fix(self):
        if not self.refresh_by:
            self.skipTest("refresh artifact missing")
        terminal_ready = 0
        for c in self.candidates:
            dom = c["domain"]
            pf = self.pf_by.get(dom, {})
            rr = self.refresh_by.get(dom)
            record = dict(c)
            if not record.get("queue_authorization") and rr:
                record["queue_authorization"] = build_queue_authorization(record, rr)
            ok, _ = terminal_consumer_eligible_offline(
                record,
                refresh_row=rr,
                preflight_row=pf,
                classify_fn=classify_candidate,
                excluded_domains=set(),
            )
            if ok:
                terminal_ready += 1
        self.assertGreaterEqual(terminal_ready, 10)


class TestR1ZeroSendIntegration(unittest.IsolatedAsyncioTestCase):
    """10 R1 candidates through exact b01 pre-send path — REAL SENDS = 0."""

    @classmethod
    def setUpClass(cls):
        if not R1_QUEUE.exists():
            raise unittest.SkipTest("R1 queue missing")
        cls.candidates = (json.loads(R1_QUEUE.read_text()).get("candidates") or [])[:10]
        cls.refresh_by = {}
        if REFRESH_JSON.exists():
            for r in json.loads(REFRESH_JSON.read_text()).get("results", []):
                if r.get("domain"):
                    cls.refresh_by[r["domain"]] = r
        cls.pf_by = {}
        if PREFLIGHT_JSON.exists():
            for r in json.loads(PREFLIGHT_JSON.read_text()).get("results", []):
                if r.get("domain"):
                    cls.pf_by[r["domain"]] = r

    @patch("run_ari_production_batch_b01.get_sent_domain_index")
    @patch("run_ari_production_batch_b01.is_already_sent", return_value=False)
    @patch("run_ari_production_batch_b01.get_effective_sent_status", return_value="not_sent")
    async def test_ten_r1_reach_pre_send_ready(self, _es, _ia, mock_get_idx):
        idx = MagicMock()
        idx.should_no_resend.return_value = False
        mock_get_idx.return_value = idx
        if len(self.candidates) < 10:
            self.skipTest("need 10 R1 candidates")
        ready_candidates: list[dict] = []
        for c in self.candidates:
            dom = c["domain"]
            pf_row = self.pf_by.get(dom, {})
            rr = self.refresh_by.get(dom)
            if not rr:
                continue
            pf_merged = b01._merge_refresh_v2_evidence(pf_row, rr)
            queue_auth = c.get("queue_authorization") or build_queue_authorization(c, rr)
            send_company = {
                "domain": dom,
                "company_name": c.get("company_name") or pf_row.get("company_name", dom),
                "form_url": c.get("form_url") or pf_row.get("form_url", ""),
                "website_url": c.get("website_url") or pf_row.get("website_url", f"https://{dom}/"),
                "preflight_classification": pf_row.get("preflight_classification", ""),
                "preflight_outcome": pf_row.get("preflight_outcome", ""),
                "queue_authorization": queue_auth,
            }
            ok, reason, _ = await b01._pre_send_check(send_company, pf_merged)
            if ok:
                ready_candidates.append(c)
            if len(ready_candidates) >= 10:
                break
        self.assertEqual(len(ready_candidates), 10, "need 10 R1 candidates passing authorized pre-send")


class TestBuildR1EmbedsAuthorization(unittest.TestCase):
    def test_r1_record_contains_queue_authorization(self):
        import tempfile
        q = {"candidates": [{"domain": "a.co.jp", "candidate_id": "1"}]}
        rr = [_refresh_ready_row("a.co.jp")]
        tmp = Path(tempfile.mkdtemp()) / "test-r1.json"
        with patch("run_ari_fast_queue_semantic_refresh._load_preflight_index", return_value={"a.co.jp": _pf_row(domain="a.co.jp")}):
            with patch("run_ari_fast_queue_semantic_refresh.get_sent_domain_index", return_value=_mock_sent_index()):
                with patch("ari_pipeline.production_queue_eligibility.is_evidence_schema_and_hash_compatible", return_value=(True, [])):
                    with patch("ari_pipeline.proven_pattern_library.classify_candidate") as mock_cls:
                        mock_cls.return_value = {
                            "classification": PROVEN_FAST_PATH,
                            "matched_pattern_id": "PAT-1",
                            "pattern_tier": "TIER_B",
                        }
                        with patch("run_ari_fast_queue_semantic_refresh.R1_QUEUE", tmp):
                            meta = fq_refresh.build_r1_queue(q, rr)
        self.assertEqual(meta["production_ready_count"], 1)
        payload = json.loads(tmp.read_text())
        rec = payload["candidates"][0]
        self.assertIn("queue_authorization", rec)
        self.assertEqual(rec["queue_authorization"]["refresh_outcome"], "REFRESH_READY")


if __name__ == "__main__":
    unittest.main()
