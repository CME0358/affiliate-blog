"""
queue_execution_contract.py — Explicit queue execution modes and evidence resolution.

queue_mode:
  AUTHORIZED_READY      — Night Factory / current-policy READY + queue_authorization is sufficient.
  PROVEN_PATTERN_FAST   — Legacy Fast Path; requires live Proven Pattern match at execution time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ari_pipeline.proven_pattern_library import PROVEN_FAST_PATH, classify_candidate, load_pattern_library
from ari_pipeline.queue_evidence_contract import (
    authorized_evidence_operational_ready,
    build_queue_authorization,
    validate_queue_authorization,
)
from config import LOG_DIR, VAULT_ROOT
from inquiry_purpose_semantics import audit_selected_purpose

QUEUE_MODE_AUTHORIZED_READY = "AUTHORIZED_READY"
QUEUE_MODE_PROVEN_PATTERN_FAST = "PROVEN_PATTERN_FAST"
VALID_QUEUE_MODES = frozenset({QUEUE_MODE_AUTHORIZED_READY, QUEUE_MODE_PROVEN_PATTERN_FAST})

OUTPUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"
LEGACY_PREFLIGHT_JSON = OUTPUT_DIR / "ARI-Full-Preflight-2026-08-12.json"
LEGACY_REFRESH_JSON = OUTPUT_DIR / "ARI-AUTO-READY-Semantic-Refresh-2026-08-12.json"


def resolve_queue_mode(queue_payload: dict[str, Any]) -> str:
    """Read queue_mode from schema; default legacy Fast Path."""
    mode = (queue_payload or {}).get("queue_mode")
    if mode in VALID_QUEUE_MODES:
        return mode
    return QUEUE_MODE_PROVEN_PATTERN_FAST


def resolve_evidence_checkpoint_path(queue_payload: dict[str, Any]) -> Path | None:
    checkpoint_id = (queue_payload or {}).get("evidence_checkpoint_id")
    if checkpoint_id:
        path = LOG_DIR / f"ari_checkpoints/{checkpoint_id}.json"
        if path.exists():
            return path
    supply_lane = (queue_payload or {}).get("supply_lane", "")
    if supply_lane == "NIGHT_FACTORY":
        from ari_pipeline.night_factory import CHECKPOINT_JSON

        if CHECKPOINT_JSON.exists():
            return CHECKPOINT_JSON
    return None


def _normalize_domain_map(raw: dict[str, dict]) -> dict[str, dict]:
    return {(k or "").lower(): v for k, v in raw.items()}


def load_queue_evidence_maps(queue_payload: dict[str, Any]) -> tuple[dict[str, dict], dict[str, dict]]:
    """
    Resolve PF/RF evidence for queue execution.
    Priority: evidence_checkpoint_id → supply_lane NIGHT_FACTORY checkpoint → legacy artifacts.
    """
    cp_path = resolve_evidence_checkpoint_path(queue_payload)
    if cp_path:
        cp = json.loads(cp_path.read_text(encoding="utf-8"))
        return (
            _normalize_domain_map(cp.get("preflight_results") or {}),
            _normalize_domain_map(cp.get("refresh_results") or {}),
        )

    pf_by: dict[str, dict] = {}
    rf_by: dict[str, dict] = {}
    if LEGACY_PREFLIGHT_JSON.exists():
        data = json.loads(LEGACY_PREFLIGHT_JSON.read_text(encoding="utf-8"))
        rows = data.get("results") or data.get("preflight_results") or []
        if isinstance(rows, dict):
            rows = list(rows.values())
        for r in rows:
            dom = (r.get("domain") or "").lower()
            if dom:
                pf_by[dom] = r
    if LEGACY_REFRESH_JSON.exists():
        data = json.loads(LEGACY_REFRESH_JSON.read_text(encoding="utf-8"))
        for r in data.get("results") or []:
            dom = (r.get("domain") or "").lower()
            if dom:
                rf_by[dom] = r
    return pf_by, rf_by


def _inquiry_purpose_compatible(refresh_row: dict | None, queue_record: dict | None = None) -> tuple[bool, str]:
    rr = refresh_row or {}
    audit = (queue_record or {}).get("inquiry_purpose_audit") or rr.get("purpose_audit") or "COMPATIBLE"
    if audit == "INCOMPATIBLE":
        return False, "incompatible_inquiry_purpose"
    sem = rr.get("semantic_evidence_v2") or {}
    snap = sem.get("canonical_snapshot") or {}
    for choice in snap.get("choices_applied") or []:
        if choice.get("category") not in ("INQUIRY_CATEGORY", "UNKNOWN", None):
            continue
        label = choice.get("label") or choice.get("value") or ""
        verdict = audit_selected_purpose(
            label,
            context=choice.get("context") or "",
            category=choice.get("category") or "",
        )
        if verdict == "INCOMPATIBLE":
            return False, "incompatible_inquiry_purpose"
        if verdict == "AMBIGUOUS":
            return False, "ambiguous_inquiry_purpose"
    return True, ""


def evaluate_authorized_ready_gate(
    queue_record: dict,
    *,
    preflight_row: dict | None,
    refresh_row: dict | None,
    excluded_domains: frozenset[str] | set[str] | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """
    AUTHORIZED_READY execution gate — queue_authorization is source of truth.
    Does NOT require Proven Pattern re-match.
    """
    dom = (queue_record.get("domain") or "").lower()
    detail: dict[str, Any] = {"domain": dom, "queue_mode": QUEUE_MODE_AUTHORIZED_READY}

    if excluded_domains and dom in excluded_domains:
        return False, "canonical_excluded", detail

    authorization = queue_record.get("queue_authorization") or build_queue_authorization(
        queue_record, refresh_row or {}
    )
    ok, reason = validate_queue_authorization(authorization, refresh_row)
    detail["authorization_ok"] = ok
    if not ok:
        return False, reason, detail

    ok_purpose, purpose_reason = _inquiry_purpose_compatible(refresh_row, queue_record)
    if not ok_purpose:
        return False, purpose_reason, detail

    op_ok, op_reason = authorized_evidence_operational_ready(refresh_row)
    if not op_ok:
        return False, op_reason, detail

    pf_row = preflight_row or {}
    fn = pf_row.get("fill_no_submit") or {}
    if fn.get("captcha_detected"):
        return False, "captcha_detected", detail

    detail["terminal_ready"] = True
    return True, "authorized_ready", detail


def evaluate_proven_pattern_fast_gate(
    queue_record: dict,
    *,
    preflight_row: dict | None,
    refresh_row: dict | None,
    excluded_domains: frozenset[str] | set[str] | None = None,
    library=None,
) -> tuple[bool, str, dict[str, Any]]:
    """Legacy Fast Path — requires live Proven Pattern match."""
    dom = queue_record.get("domain", "")
    merged = {**(preflight_row or {}), **queue_record}
    library = library or load_pattern_library()
    cls = classify_candidate(
        merged,
        library=library,
        excluded_domains=excluded_domains,
        refresh_row=refresh_row,
    )
    detail = {
        "domain": dom,
        "queue_mode": QUEUE_MODE_PROVEN_PATTERN_FAST,
        "classification": cls.get("classification"),
        "matched_pattern_id": cls.get("matched_pattern_id"),
    }
    if cls.get("classification") != PROVEN_FAST_PATH:
        return False, cls.get("reason") or "not_proven_fast_path", detail

    ok, reason, auth_detail = evaluate_authorized_ready_gate(
        queue_record,
        preflight_row=preflight_row,
        refresh_row=refresh_row,
        excluded_domains=excluded_domains,
    )
    detail.update(auth_detail)
    return ok, reason, detail


def evaluate_terminal_daily_fast_gate(
    queue_record: dict,
    *,
    queue_mode: str,
    preflight_row: dict | None,
    refresh_row: dict | None,
    excluded_domains: frozenset[str] | set[str] | None = None,
    library=None,
) -> tuple[bool, str, dict[str, Any]]:
    """Unified Terminal daily-fast pre-attempt gate (ZERO SEND)."""
    if queue_mode == QUEUE_MODE_AUTHORIZED_READY:
        return evaluate_authorized_ready_gate(
            queue_record,
            preflight_row=preflight_row,
            refresh_row=refresh_row,
            excluded_domains=excluded_domains,
        )
    return evaluate_proven_pattern_fast_gate(
        queue_record,
        preflight_row=preflight_row,
        refresh_row=refresh_row,
        excluded_domains=excluded_domains,
        library=library,
    )


def terminal_consumer_eligible_for_queue(
    queue_record: dict,
    *,
    queue_mode: str,
    refresh_row: dict | None,
    preflight_row: dict | None,
    classify_fn=None,
    excluded_domains=None,
    library=None,
) -> tuple[bool, str]:
    """Offline audit mirroring Terminal daily-fast gate for a queue mode."""
    ok, reason, _ = evaluate_terminal_daily_fast_gate(
        queue_record,
        queue_mode=queue_mode,
        preflight_row=preflight_row,
        refresh_row=refresh_row,
        excluded_domains=excluded_domains,
        library=library,
    )
    if ok:
        return True, "terminal_consumer_ready"
    return False, reason


def audit_queue_contract_parity(
    queue_payload: dict[str, Any],
    *,
    sample_size: int | None = None,
) -> dict[str, Any]:
    """
    Zero-send parity: producer READY records vs Terminal gate for queue_mode.
    Uses queue-resolved evidence (not legacy global artifacts).
    """
    mode = resolve_queue_mode(queue_payload)
    pf_by, rf_by = load_queue_evidence_maps(queue_payload)
    candidates = queue_payload.get("candidates") or []
    if not candidates:
        return {"parity_pass": False, "error": "empty_queue", "queue_mode": mode}

    n = sample_size if sample_size is not None else len(candidates)
    sample = candidates[:n]
    mismatches: list[dict] = []

    for rec in sample:
        dom = (rec.get("domain") or "").lower()
        pf = pf_by.get(dom) or {}
        rr = rf_by.get(dom) or {}
        ok, reason, detail = evaluate_terminal_daily_fast_gate(
            rec,
            queue_mode=mode,
            preflight_row=pf,
            refresh_row=rr,
        )
        if not ok:
            mismatches.append({"domain": dom, "reason": reason, **detail})

    purpose_ok = all(
        (c.get("inquiry_purpose_audit") or "COMPATIBLE") in ("COMPATIBLE", "NOT_APPLICABLE", "")
        for c in sample
    )
    return {
        "queue_mode": mode,
        "sample_size": len(sample),
        "queue_size": len(candidates),
        "parity_pass": len(mismatches) == 0,
        "producer_terminal_ready_rate": (len(sample) - len(mismatches)) / max(len(sample), 1),
        "correct_purpose_rate": 1.0 if purpose_ok else 0.0,
        "mismatches": mismatches,
    }
