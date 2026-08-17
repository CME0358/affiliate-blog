"""
queue_evidence_contract.py — Immutable queue ↔ Terminal evidence handoff contract.

Producer marks READY only with authorized semantic evidence.
Terminal must validate the SAME evidence referenced by the queue record.
"""

from __future__ import annotations

from typing import Any

from semantic_policy import SEMANTIC_REFRESH_REQUIRED, assess_production_evidence_eligibility
from shared_form_prepare import (
    SEMANTIC_EVIDENCE_SCHEMA_VERSION,
    build_preflight_semantic_evidence,
    is_evidence_compatible,
    is_evidence_schema_and_hash_compatible,
)

REFRESH_ARTIFACT_ID = "ARI-AUTO-READY-Semantic-Refresh-2026-08-12.json"


def build_queue_authorization(queue_candidate: dict, refresh_row: dict) -> dict[str, Any]:
    """Embed immutable evidence lineage on queue records at production time."""
    sem = refresh_row.get("semantic_evidence_v2") or {}
    snap = sem.get("canonical_snapshot") or {}
    return {
        "production_eligibility": queue_candidate.get("production_eligibility", "production_ready"),
        "authorized_semantic_hash": sem.get("semantic_hash") or queue_candidate.get("semantic_hash"),
        "semantic_policy_version": sem.get("semantic_policy_version") or snap.get("semantic_policy_version"),
        "semantic_policy_fingerprint": sem.get("semantic_policy_fingerprint") or snap.get("semantic_policy_fingerprint"),
        "evidence_schema_version": sem.get("semantic_evidence_schema_version"),
        "refresh_outcome": refresh_row.get("refresh_outcome"),
        "refresh_artifact_id": REFRESH_ARTIFACT_ID,
        "candidate_id": queue_candidate.get("candidate_id"),
        "domain": queue_candidate.get("domain"),
        "queue_revision": queue_candidate.get("queue_revision"),
    }


def authorized_evidence_operational_ready(refresh_row: dict | None) -> tuple[bool, str]:
    """Field map + submit target gates from authorized semantic evidence."""
    sem = (refresh_row or {}).get("semantic_evidence_v2") or {}
    snap = sem.get("canonical_snapshot") or {}
    field_map = snap.get("field_map") or {}
    for k in ("name", "email", "message"):
        if field_map.get(k) not in ("FILLED", "FOUND"):
            return False, f"missing_field:{k}"
    if not snap.get("submit_target"):
        return False, "no_final_submit"
    return True, ""


def validate_queue_authorization(
    authorization: dict[str, Any] | None,
    refresh_row: dict | None,
) -> tuple[bool, str]:
    if not authorization:
        return False, "missing_queue_authorization"
    if authorization.get("production_eligibility") != "production_ready":
        return False, "queue_not_production_ready"
    if not refresh_row:
        return False, "refresh_artifact_not_resolved"
    if refresh_row.get("refresh_outcome") != "REFRESH_READY":
        return False, f"refresh_not_ready:{refresh_row.get('refresh_outcome')}"

    sem = refresh_row.get("semantic_evidence_v2") or {}
    auth_hash = authorization.get("authorized_semantic_hash")
    live_hash = sem.get("semantic_hash")
    if not auth_hash or not live_hash:
        return False, "missing_semantic_hash"
    if auth_hash != live_hash:
        return False, f"semantic_hash_mismatch:{auth_hash}!={live_hash}"

    if authorization.get("evidence_schema_version") and sem.get("semantic_evidence_schema_version"):
        if authorization["evidence_schema_version"] != sem["semantic_evidence_schema_version"]:
            return False, "evidence_schema_version_mismatch"

    fp = authorization.get("semantic_policy_fingerprint")
    if fp and sem.get("semantic_policy_fingerprint") and fp != sem["semantic_policy_fingerprint"]:
        return False, "semantic_policy_fingerprint_mismatch"

    status, reasons = assess_production_evidence_eligibility(
        sem,
        schema_compatible_fn=is_evidence_schema_and_hash_compatible,
    )
    if status == SEMANTIC_REFRESH_REQUIRED:
        return False, SEMANTIC_REFRESH_REQUIRED
    if status != "ELIGIBLE":
        return False, f"evidence_{status.lower()}"

    return True, ""


async def daily_fast_pre_send_check(
    company: dict,
    *,
    queue_record: dict,
    preflight_row: dict | None,
    refresh_row: dict | None,
    duplicate_check_fn,
    domain_match_fn,
) -> tuple[bool, str, dict]:
    """
    Terminal consumer pre-send for authorized queue records.
    Does NOT require legacy AUTO_READY preflight when queue authorization validates.
    """
    dom = company.get("domain", "")
    name = company.get("company_name", "")
    website = company.get("website_url", "")

    if duplicate_check_fn(name, website, dom):
        return False, "duplicate_lock", {}

    if domain_match_fn(website, dom):
        return False, "domain_mismatch", {}

    authorization = queue_record.get("queue_authorization") or build_queue_authorization(queue_record, refresh_row or {})
    ok, reason = validate_queue_authorization(authorization, refresh_row)
    if not ok:
        return False, reason, {}

    pf_row = preflight_row or {}
    fn = pf_row.get("fill_no_submit") or {}
    evidence = company.get("preflight_evidence") or {}
    field_map = evidence.get("field_map") or fn.get("field_map") or {}

    if fn.get("captcha_detected"):
        return False, "captcha_detected", {}

    for k in ("name", "email", "message"):
        if field_map.get(k) not in ("FILLED", "FOUND"):
            return False, f"missing_field:{k}", {}

    sel = fn.get("message_selection") or {}
    if sel.get("skipped"):
        return False, sel.get("skip_reason") or "maxlength_skip", {}

    if fn.get("final_submit_identified") is False:
        return False, "no_final_submit", {}

    semantic = build_preflight_semantic_evidence(pf_row) if pf_row else {}
    if not semantic:
        sem = (refresh_row or {}).get("semantic_evidence_v2") or {}
        semantic = sem if sem.get("semantic_evidence_schema_version") == SEMANTIC_EVIDENCE_SCHEMA_VERSION else {}

    compatible, compat_reasons = is_evidence_compatible(semantic)
    if not compatible:
        return False, f"evidence_incompatible:{','.join(compat_reasons)}", {}

    return True, "", {
        "preflight_semantic_evidence": semantic,
        "queue_authorization": authorization,
    }


def terminal_consumer_eligible_offline(
    queue_record: dict,
    *,
    refresh_row: dict | None,
    preflight_row: dict | None,
    classify_fn,
    excluded_domains,
    library=None,
    queue_mode: str | None = None,
) -> tuple[bool, str]:
    """Mirror Terminal daily-fast gates without browser (offline audit)."""
    from ari_pipeline.queue_execution_contract import (
        QUEUE_MODE_PROVEN_PATTERN_FAST,
        terminal_consumer_eligible_for_queue,
    )

    mode = queue_mode or QUEUE_MODE_PROVEN_PATTERN_FAST
    return terminal_consumer_eligible_for_queue(
        queue_record,
        queue_mode=mode,
        refresh_row=refresh_row,
        preflight_row=preflight_row,
        classify_fn=classify_fn,
        excluded_domains=excluded_domains,
        library=library,
    )
