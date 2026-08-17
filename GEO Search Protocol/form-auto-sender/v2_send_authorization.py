"""
v2_send_authorization.py — Immutable ARI_MESSAGE_V2 send payload authorization.

Human-reviewed send artifact → immutable payload → prepare → authorize → submit.
No send-time re-resolution or re-personalization.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from message_variant import VARIANT_V2
from shared_form_prepare import PreparedFormSnapshot, mark_snapshot_authorized

V1_FALLBACK_MARKER = "無料AI推薦スコア診断"
AISCAN_MARKER = "aiscan.coaretail.com"


@dataclass(frozen=True)
class ImmutableV2SendPayload:
    """Frozen send contract — must match human-reviewed artifact exactly."""

    domain: str
    company_display_name: str
    subject: str
    message: str
    preview_url: str
    preview_token: str
    message_variant: str = VARIANT_V2
    candidate_id: str = ""
    video_segment: str = ""
    commercial_fit_score: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def expected_salutation(self) -> str:
        return f"{self.company_display_name}様の公式サイトを拝見し、"


def validate_v2_payload_parity(
    prepared: PreparedFormSnapshot,
    payload: ImmutableV2SendPayload,
) -> tuple[bool, list[str]]:
    """Field-level parity between prepared form state and immutable V2 payload."""
    reasons: list[str] = []
    prep = prepared.prep

    if not prep.ok or prep.blocked:
        return False, [f"prepare_blocked:{prep.reason}"]

    selection = prep.selection
    if not selection or selection.skipped:
        reasons.append("selection_skipped")
    elif selection.variant != VARIANT_V2:
        reasons.append(f"variant_mismatch:expected={VARIANT_V2}:actual={selection.variant}")

    if prep.message != payload.message:
        reasons.append("message_body_mismatch")

    if payload.preview_url not in (prep.message or ""):
        reasons.append("preview_url_missing_in_message")

    if payload.preview_token and payload.preview_token not in (prep.message or ""):
        reasons.append("preview_token_missing_in_message")

    salutation = payload.expected_salutation
    if salutation not in (prep.message or ""):
        reasons.append("company_display_name_salutation_mismatch")

    if V1_FALLBACK_MARKER in (prep.message or "") or AISCAN_MARKER in (prep.message or ""):
        reasons.append("v1_fallback_detected")

    return not bool(reasons), reasons


def authorize_v2_fixed_snapshot(
    prepared: PreparedFormSnapshot,
    payload: ImmutableV2SendPayload,
) -> tuple[bool, list[str]]:
    """
    Authorize a fresh production snapshot against immutable V2 send payload.
    Does NOT compare to legacy preflight evidence — V2 canary uses payload contract.
    """
    ok, reasons = validate_v2_payload_parity(prepared, payload)
    if not ok:
        return False, reasons
    mark_snapshot_authorized(prepared)
    return True, []


def build_v2_send_payload(
    *,
    domain: str,
    company_display_name: str,
    message: str,
    preview_url: str,
    preview_token: str,
    subject: str,
    candidate_id: str = "",
    video_segment: str = "",
    commercial_fit_score: int | None = None,
    extra: dict[str, Any] | None = None,
) -> ImmutableV2SendPayload:
    return ImmutableV2SendPayload(
        domain=domain,
        company_display_name=company_display_name,
        subject=subject,
        message=message,
        preview_url=preview_url,
        preview_token=preview_token,
        candidate_id=candidate_id,
        video_segment=video_segment,
        commercial_fit_score=commercial_fit_score,
        extra=extra or {},
    )
