"""
evidence_reauthorization.py — Production evidence authorization with selector-refinement drift.
"""

from __future__ import annotations

import re
from typing import Any

from shared_form_prepare import (
    compare_runtime_snapshots,
    compute_semantic_hash,
    extract_semantic_hash_payload,
    is_evidence_compatible,
)
from submit_target_semantics import (
    RESOLUTION_EQUIVALENT,
    RESOLUTION_UNIQUE,
    is_generic_typed_submit_selector,
    is_named_submit_selector,
    is_scoped_refinement_of,
)

EXPECTED_SELECTOR_REFINEMENT = "EXPECTED_SELECTOR_REFINEMENT"
EXPECTED_SEMANTIC_SUBMIT_REFINEMENT = "EXPECTED_SEMANTIC_SUBMIT_REFINEMENT"
MATERIAL_HASH_DRIFT = "MATERIAL_HASH_DRIFT"
UNEXPLAINED_HASH_DRIFT = "UNEXPLAINED_HASH_DRIFT"
NO_DRIFT = "NO_DRIFT"

_GENERIC_SUBMIT_PATTERNS = (
    re.compile(r"^form(\[[^\]]+\])?\s+input\[type=[\"']?submit[\"']?\]$", re.I),
    re.compile(r"^form(\#[^\s]+)?\s+input\[type=[\"']?submit[\"']?\]$", re.I),
    re.compile(r"^form(\#[^\s]+)?\s+button\[type=[\"']?submit[\"']?\]$", re.I),
)


def is_generic_submit_selector(selector: str) -> bool:
    s = (selector or "").strip()
    if not s:
        return False
    return any(p.match(s) for p in _GENERIC_SUBMIT_PATTERNS) or is_generic_typed_submit_selector(s)


def _snapshot_submit_target(snapshot: dict[str, Any]) -> str:
    fields = snapshot.get("fields") or {}
    return (snapshot.get("submit_target") or fields.get("submit_button") or "").strip()


def _semantic_core(snapshot: dict[str, Any]) -> dict[str, Any]:
    payload = extract_semantic_hash_payload(snapshot)
    fields = dict(payload.get("fields") or {})
    fields.pop("submit_button", None)
    payload["fields"] = fields
    return payload


def _validate_refinement_policy(
    *,
    pre_submit: str,
    prod_submit: str,
    canonical_submit_target: dict[str, Any],
    require_scoped_refinement: bool = False,
) -> tuple[bool, list[str]]:
    cst = canonical_submit_target or {}
    policy = cst.get("resolution_policy") or ""
    if policy not in (RESOLUTION_UNIQUE, RESOLUTION_EQUIVALENT):
        return False, [f"resolution_policy:{policy or 'missing'}"]

    hint = (cst.get("selector_hint") or "").strip()
    if hint and hint != pre_submit and not is_scoped_refinement_of(pre_submit, hint):
        return False, [f"selector_hint_mismatch:{hint}!={pre_submit}"]

    if not cst.get("final_submit_eligible"):
        return False, ["submit_not_eligible"]

    resolved = (cst.get("submit_selector") or prod_submit).strip()
    if resolved != prod_submit:
        return False, [f"resolved_selector_mismatch:{resolved}!={prod_submit}"]

    if require_scoped_refinement and not is_scoped_refinement_of(pre_submit, prod_submit):
        return False, [f"submit_not_refinement:{pre_submit}!={prod_submit}"]

    return True, []


def classify_hash_drift(
    preflight_evidence: dict[str, Any],
    fresh_runtime: dict[str, Any],
    *,
    canonical_submit_target: dict[str, Any] | None = None,
) -> tuple[str, list[str]]:
    pre_snap = preflight_evidence.get("canonical_snapshot") or preflight_evidence
    prod_snap = fresh_runtime.get("snapshot") or fresh_runtime

    pre_core = _semantic_core(pre_snap)
    prod_core = _semantic_core(prod_snap if isinstance(prod_snap, dict) else {})
    if pre_core != prod_core:
        return MATERIAL_HASH_DRIFT, ["semantic_core_changed"]

    pre_submit = _snapshot_submit_target(pre_snap)
    prod_submit = _snapshot_submit_target(prod_snap if isinstance(prod_snap, dict) else fresh_runtime)
    if pre_submit == prod_submit:
        return NO_DRIFT, []

    if not pre_submit or not prod_submit:
        return UNEXPLAINED_HASH_DRIFT, ["submit_target_missing"]

    cst = canonical_submit_target or {}

    if is_named_submit_selector(pre_submit):
        ok, reasons = _validate_refinement_policy(
            pre_submit=pre_submit,
            prod_submit=prod_submit,
            canonical_submit_target=cst,
            require_scoped_refinement=True,
        )
        if not ok:
            return UNEXPLAINED_HASH_DRIFT, reasons
        return EXPECTED_SEMANTIC_SUBMIT_REFINEMENT, []

    if is_generic_submit_selector(pre_submit):
        ok, reasons = _validate_refinement_policy(
            pre_submit=pre_submit,
            prod_submit=prod_submit,
            canonical_submit_target=cst,
            require_scoped_refinement=False,
        )
        if not ok:
            return UNEXPLAINED_HASH_DRIFT, reasons
        return EXPECTED_SELECTOR_REFINEMENT, []

    ok, reasons = _validate_refinement_policy(
        pre_submit=pre_submit,
        prod_submit=prod_submit,
        canonical_submit_target=cst,
        require_scoped_refinement=True,
    )
    if ok and is_scoped_refinement_of(pre_submit, prod_submit):
        return EXPECTED_SEMANTIC_SUBMIT_REFINEMENT, []

    return UNEXPLAINED_HASH_DRIFT, reasons or [f"submit_not_refinement:{pre_submit}!={prod_submit}"]


def authorize_production_evidence(
    prepared,
    preflight_evidence: dict[str, Any],
    *,
    allow_selector_refinement: bool = False,
) -> tuple[bool, list[str], dict[str, Any]]:
    """
    Authorize fresh production prepare against historical evidence.
    Allows scoped selector refinement when semantic core is unchanged.
    """
    meta: dict[str, Any] = {
        "evidence_reauthorized": False,
        "reauthorization_reason": "",
        "hash_drift_class": NO_DRIFT,
    }

    if not prepared.prep.ok or prepared.prep.blocked:
        return False, [f"prepare_blocked:{prepared.prep.reason}"], meta

    compatible, compat_reasons = is_evidence_compatible(preflight_evidence)
    if not compatible:
        return False, compat_reasons, meta

    fresh = prepared.to_runtime_snap()
    fresh["snapshot"] = prepared.prep.snapshot
    fresh["mapping_hash"] = prepared.prep.mapping_hash
    fresh["semantic_hash"] = prepared.prep.mapping_hash

    pre = dict(preflight_evidence or {})
    pre_hash = pre.get("semantic_hash") or pre.get("mapping_hash")
    if not pre_hash:
        snap = pre.get("canonical_snapshot") or pre
        pre_hash = compute_semantic_hash(snap)
    pre["mapping_hash"] = pre_hash
    pre["semantic_hash"] = pre_hash

    diverged, reasons = compare_runtime_snapshots(pre, fresh)
    if not diverged:
        meta["preflight_hash"] = pre_hash
        meta["production_hash"] = prepared.prep.mapping_hash
        return True, [], meta

    meta["preflight_hash"] = pre_hash
    meta["production_hash"] = prepared.prep.mapping_hash

    if not allow_selector_refinement:
        meta["hash_drift_class"] = UNEXPLAINED_HASH_DRIFT
        return False, reasons, meta

    if not all(r.startswith("mapping_hash:") for r in reasons):
        meta["hash_drift_class"] = MATERIAL_HASH_DRIFT
        return False, reasons, meta

    classification, class_reasons = classify_hash_drift(
        pre,
        fresh,
        canonical_submit_target=getattr(prepared.prep, "canonical_submit_target", None) or {},
    )
    meta["hash_drift_class"] = classification

    if classification in (EXPECTED_SELECTOR_REFINEMENT, EXPECTED_SEMANTIC_SUBMIT_REFINEMENT):
        meta["evidence_reauthorized"] = True
        meta["reauthorization_reason"] = classification
        meta["preflight_submit_target"] = _snapshot_submit_target(pre.get("canonical_snapshot") or pre)
        meta["production_submit_target"] = _snapshot_submit_target(prepared.prep.snapshot or {})
        return True, [], meta

    if classification == MATERIAL_HASH_DRIFT:
        return False, reasons + class_reasons, meta

    return False, reasons + class_reasons, meta
