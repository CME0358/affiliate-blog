"""
ari_pipeline/ab_tracking.py — A/B tracking field evaluation and notes encoding.

Minimal additive change: encode preview metadata in `notes` JSON until dedicated
columns are warranted. Existing HEADERS unchanged for backward compatibility.
"""

from __future__ import annotations

import json
from typing import Any


def encode_ab_notes(
    *,
    ab_arm: str = "",
    message_version: str = "",
    preview_token: str = "",
    preview_created_at: str = "",
    extra: dict[str, Any] | None = None,
) -> str:
    payload = {
        "ab_arm": ab_arm or None,
        "message_version": message_version or None,
        "preview_token": preview_token or None,
        "preview_created_at": preview_created_at or None,
    }
    if extra:
        payload.update(extra)
    cleaned = {k: v for k, v in payload.items() if v}
    if not cleaned:
        return ""
    return json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))


def parse_ab_notes(notes: str) -> dict[str, Any]:
    if not notes or not notes.strip().startswith("{"):
        return {}
    try:
        data = json.loads(notes)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def recommended_schema_changes() -> dict[str, Any]:
    """
    Evaluation: dedicated columns vs notes JSON.

    Current HEADERS already include `message_variant` — sufficient for arm A vs V2
    distinction at send time. Preview-specific fields are sparse until pilot volume
    justifies migration.
    """
    return {
        "add_columns_now": False,
        "rationale": (
            "Use message_variant for ARI_MESSAGE_V1|V2|COMPACT at CONFIRMED_SENT. "
            "Encode ab_arm, preview_token, preview_created_at in notes JSON during pilot. "
            "Promote to columns when >100 V2 sends/week or BI tooling requires it."
        ),
        "notes_json_fields": [
            "ab_arm",
            "message_version",
            "preview_token",
            "preview_created_at",
        ],
        "existing_field_mapping": {
            "message_variant": "ARI_MESSAGE_V1 | ARI_MESSAGE_V2 | ARI_MESSAGE_COMPACT",
            "lp_visit_known": "remains unknown until attribution closes",
        },
    }
