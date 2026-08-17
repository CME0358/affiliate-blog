"""
ari_pipeline/production_queue_eligibility.py — Fast production queue eligibility gate.

Production queues may only include candidates with:
  PROVEN_FAST_PATH pattern match
  AND current semantic evidence (REFRESH_READY + policy compatible + ELIGIBLE)
"""

from __future__ import annotations

from typing import Any

from ari_pipeline.proven_pattern_library import (
    CAPTCHA_MANUAL,
    DUPLICATE_ALREADY_SENT,
    FORM_NOT_SUITABLE,
    PROVEN_FAST_PATH,
    classify_candidate,
    load_pattern_library,
)
from inquiry_purpose_semantics import audit_selected_purpose
from preflight_classifier import AUTO_READY
from semantic_policy import SEMANTIC_REFRESH_REQUIRED, assess_production_evidence_eligibility
from shared_form_prepare import is_evidence_schema_and_hash_compatible

SEMANTIC_REFRESH_REQUIRED_ROUTE = "SEMANTIC_REFRESH_REQUIRED"


def inquiry_purpose_refresh_compatible(refresh_row: dict | None) -> tuple[bool, str]:
    if not refresh_row:
        return True, ""
    if refresh_row.get("refresh_outcome") == "FORM_NOT_SUITABLE":
        return False, "form_not_suitable"
    sem = refresh_row.get("semantic_evidence_v2") or {}
    snap = sem.get("canonical_snapshot") or {}
    for choice in snap.get("choices_applied") or []:
        if choice.get("category") not in ("INQUIRY_CATEGORY", "UNKNOWN"):
            continue
        label = choice.get("label") or choice.get("value") or ""
        verdict = audit_selected_purpose(label, context=choice.get("context") or "", category=choice.get("category") or "")
        if verdict == "INCOMPATIBLE":
            return False, "incompatible_inquiry_purpose"
        if verdict == "AMBIGUOUS":
            return False, "ambiguous_inquiry_purpose"
    purpose_audit = refresh_row.get("purpose_audit")
    if purpose_audit == "INCOMPATIBLE":
        return False, "incompatible_inquiry_purpose"
    return True, ""


def assess_production_queue_eligibility(
    candidate: dict,
    *,
    refresh_row: dict | None = None,
    library: dict | None = None,
    sent_index=None,
    excluded_domains: frozenset[str] | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """
    Returns (eligible, reason, detail).
    eligible=True only when candidate is production-ready under current policy.
    """
    library = library or load_pattern_library()
    dom = candidate.get("domain", "")

    cls = classify_candidate(
        candidate,
        library=library,
        sent_index=sent_index,
        excluded_domains=excluded_domains,
        refresh_row=refresh_row,
    )
    detail: dict[str, Any] = {
        "domain": dom,
        "classification": cls.get("classification"),
        "matched_pattern_id": cls.get("matched_pattern_id"),
        "pattern_tier": cls.get("pattern_tier"),
    }

    if cls.get("classification") == DUPLICATE_ALREADY_SENT:
        return False, "effective_confirmed_sent", detail
    if cls.get("classification") in (CAPTCHA_MANUAL, FORM_NOT_SUITABLE):
        return False, cls.get("classification", "").lower(), detail
    if cls.get("classification") != PROVEN_FAST_PATH:
        return False, "not_proven_fast_path", detail

    if not refresh_row:
        detail["eligibility"] = SEMANTIC_REFRESH_REQUIRED_ROUTE
        return False, "missing_refresh", detail

    if refresh_row.get("refresh_outcome") != "REFRESH_READY":
        detail["refresh_outcome"] = refresh_row.get("refresh_outcome")
        return False, refresh_row.get("refresh_outcome") or "not_refresh_ready", detail

    sem = refresh_row.get("semantic_evidence_v2") or {}
    status, reasons = assess_production_evidence_eligibility(
        sem,
        schema_compatible_fn=is_evidence_schema_and_hash_compatible,
    )
    detail["evidence_eligibility"] = status
    detail["evidence_reasons"] = reasons

    if status == SEMANTIC_REFRESH_REQUIRED:
        return False, SEMANTIC_REFRESH_REQUIRED_ROUTE, detail
    if status != "ELIGIBLE":
        return False, status.lower(), detail

    ok, purpose_reason = inquiry_purpose_refresh_compatible(refresh_row)
    if not ok:
        detail["purpose_reason"] = purpose_reason
        return False, purpose_reason, detail

    from ari_pipeline.queue_evidence_contract import authorized_evidence_operational_ready

    op_ok, op_reason = authorized_evidence_operational_ready(refresh_row)
    if not op_ok:
        detail["operational_reason"] = op_reason
        return False, op_reason, detail

    detail["eligible"] = True
    return True, "production_ready", detail
