"""
semantic_policy.py — Canonical semantic policy identity for evidence provenance.

A semantic policy change that can affect prepared submission values must invalidate
evidence produced under a previous policy contract.
"""

from __future__ import annotations

import hashlib
from typing import Any

# Bump when any policy below can change submission semantics in production.
SEMANTIC_POLICY_VERSION = 1

# Stable component identifiers (generic — no domain-specific values).
POLICY_COMPONENTS: tuple[str, ...] = (
    "inquiry_purpose_semantics:v1",
    "required_choice_resolver:inquiry_category:v1",
    "submit_target_semantics:v1",
    "canonical_submit_target:v1",
)

SEMANTIC_REFRESH_REQUIRED = "SEMANTIC_REFRESH_REQUIRED"


def semantic_policy_fingerprint() -> str:
    canonical = "|".join(POLICY_COMPONENTS)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def current_semantic_policy_provenance() -> dict[str, Any]:
    return {
        "semantic_policy_version": SEMANTIC_POLICY_VERSION,
        "semantic_policy_fingerprint": semantic_policy_fingerprint(),
        "semantic_policy_components": list(POLICY_COMPONENTS),
    }


def extract_semantic_policy_provenance(evidence: dict[str, Any] | None) -> dict[str, Any]:
    if not evidence:
        return {}
    for key in ("semantic_policy_version", "semantic_policy_fingerprint"):
        if evidence.get(key) is not None:
            return {
                "semantic_policy_version": evidence.get("semantic_policy_version"),
                "semantic_policy_fingerprint": evidence.get("semantic_policy_fingerprint"),
            }
    snap = evidence.get("canonical_snapshot") or {}
    return {
        "semantic_policy_version": snap.get("semantic_policy_version"),
        "semantic_policy_fingerprint": snap.get("semantic_policy_fingerprint"),
    }


def is_semantic_policy_compatible(evidence: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """
    True when evidence was generated under the current semantic policy contract.
    Missing or stale policy provenance → SEMANTIC_REFRESH_REQUIRED (not runtime divergence).
    """
    if not evidence:
        return False, ["missing_evidence"]

    prov = extract_semantic_policy_provenance(evidence)
    version = prov.get("semantic_policy_version")
    fingerprint = prov.get("semantic_policy_fingerprint")

    if version is None and fingerprint is None:
        return False, [f"semantic_policy_missing:{SEMANTIC_REFRESH_REQUIRED}"]

    current = current_semantic_policy_provenance()
    reasons: list[str] = []

    if version != current["semantic_policy_version"]:
        reasons.append(
            f"semantic_policy_version_mismatch:{version}!={current['semantic_policy_version']}"
        )
    if fingerprint != current["semantic_policy_fingerprint"]:
        reasons.append(
            f"semantic_policy_fingerprint_mismatch:{fingerprint}!={current['semantic_policy_fingerprint']}"
        )

    if reasons:
        return False, reasons
    return True, []


def assess_production_evidence_eligibility(
    evidence: dict[str, Any] | None,
    *,
    schema_compatible_fn,
) -> tuple[str, list[str]]:
    """
    Returns eligibility status:
      ELIGIBLE | SEMANTIC_REFRESH_REQUIRED | INCOMPATIBLE
    """
    if not evidence:
        return "INCOMPATIBLE", ["missing_evidence"]

    policy_ok, policy_reasons = is_semantic_policy_compatible(evidence)
    if not policy_ok:
        if any(SEMANTIC_REFRESH_REQUIRED in r or "semantic_policy_" in r for r in policy_reasons):
            return SEMANTIC_REFRESH_REQUIRED, policy_reasons
        return "INCOMPATIBLE", policy_reasons

    schema_ok, schema_reasons = schema_compatible_fn(evidence)
    if not schema_ok:
        return "INCOMPATIBLE", schema_reasons

    return "ELIGIBLE", []
