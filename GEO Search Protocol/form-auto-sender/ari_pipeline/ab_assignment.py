"""
ari_pipeline/ab_assignment.py — A/B arm assignment (tracking readiness only).

PRODUCTION DISABLED by default. Callers must pass enabled=True explicitly for pilot.
"""

from __future__ import annotations

import hashlib
from typing import Literal

AbArm = Literal["A", "B", "C"]

ARM_MESSAGE_VERSION = {
    "A": "ARI_MESSAGE_V1",
    "B": "ARI_MESSAGE_V2",
    "C": "ARI_MESSAGE_V2",
}

ARM_USES_PREVIEW = {
    "A": False,
    "B": False,
    "C": True,
}


def assign_ab_arm(
    candidate_id: str,
    *,
    enabled: bool = False,
    weights: tuple[int, int, int] = (90, 5, 5),
) -> AbArm | None:
    """
    Deterministic arm from candidate_id. Returns None when disabled (production default).
    """
    if not enabled:
        return None
    if not candidate_id:
        return "A"

    total = sum(weights)
    if total <= 0:
        return "A"

    digest = hashlib.sha256(f"ari_ab_v1:{candidate_id}".encode()).hexdigest()
    bucket = int(digest[:8], 16) % total
    a, b, c = weights
    if bucket < a:
        return "A"
    if bucket < a + b:
        return "B"
    return "C"


def arm_metadata(arm: AbArm | None) -> dict[str, str | bool]:
    if arm is None:
        return {
            "ab_arm": "",
            "message_version": "ARI_MESSAGE_V1",
            "uses_preview": False,
        }
    return {
        "ab_arm": arm,
        "message_version": ARM_MESSAGE_VERSION[arm],
        "uses_preview": ARM_USES_PREVIEW[arm],
    }
