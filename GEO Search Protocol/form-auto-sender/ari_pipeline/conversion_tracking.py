"""
ari_pipeline/conversion_tracking.py — Reply / purchase tracking schema.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from config import LOG_DIR, VAULT_ROOT

TRACKING_CSV = LOG_DIR / "ari_conversion_tracking.csv"
SCHEMA_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ari_conversion_tracking_schema.json"

REPLY_CLASSIFICATIONS = (
    "NONE",
    "AUTO_REPLY",
    "NEGATIVE",
    "INTERESTED",
    "QUESTION",
    "MEETING_REQUEST",
    "PURCHASED",
)

HEADERS = [
    "candidate_id",
    "company_name",
    "domain",
    "confirmed_sent_at",
    "message_variant",
    "reply_status",
    "reply_at",
    "reply_classification",
    "positive_reply",
    "lp_visit_known",
    "purchase_status",
    "purchase_at",
    "revenue",
    "notes",
    "updated_at",
]

FUNNEL_STAGES = [
    "Candidates",
    "AUTO_READY",
    "CONFIRMED_SENT",
    "Reply",
    "Positive Reply",
    "Purchase",
]


def schema_document() -> dict:
    return {
        "version": "1.0",
        "created_at": datetime.now().isoformat(),
        "funnel": FUNNEL_STAGES,
        "reply_classifications": list(REPLY_CLASSIFICATIONS),
        "fields": {
            h: _field_desc(h) for h in HEADERS
        },
        "kpi_note": "0.3% hypothesis must specify which funnel stage it applies to",
        "csv_path": str(TRACKING_CSV),
    }


def _field_desc(name: str) -> str:
    desc = {
        "candidate_id": "Stable hash from domain+company",
        "confirmed_sent_at": "ISO datetime when CONFIRMED_SENT recorded",
        "message_variant": "ARI_MESSAGE_V1 or ARI_MESSAGE_COMPACT",
        "reply_status": "raw reply state: none/pending/received",
        "reply_classification": "NONE|AUTO_REPLY|NEGATIVE|INTERESTED|QUESTION|MEETING_REQUEST|PURCHASED",
        "positive_reply": "true if INTERESTED|MEETING_REQUEST|PURCHASED",
        "lp_visit_known": "true|false|unknown",
        "purchase_status": "none|pending|confirmed",
        "revenue": "numeric JPY if known",
    }
    return desc.get(name, "")


def ensure_tracking_csv() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not TRACKING_CSV.exists():
        with TRACKING_CSV.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=HEADERS).writeheader()
    return TRACKING_CSV


def write_schema() -> tuple[Path, Path]:
    SCHEMA_JSON.parent.mkdir(parents=True, exist_ok=True)
    schema = schema_document()
    SCHEMA_JSON.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = ensure_tracking_csv()
    return SCHEMA_JSON, csv_path


def seed_from_confirmed_sent(rows: list[dict]) -> int:
    """Append tracking rows for new CONFIRMED_SENT (idempotent by candidate_id)."""
    ensure_tracking_csv()
    existing_ids: set[str] = set()
    with TRACKING_CSV.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("candidate_id"):
                existing_ids.add(row["candidate_id"])

    added = 0
    with TRACKING_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS, extrasaction="ignore")
        for r in rows:
            cid = r.get("candidate_id", "")
            if not cid or cid in existing_ids:
                continue
            w.writerow({
                "candidate_id": cid,
                "company_name": r.get("company_name", ""),
                "domain": r.get("domain", ""),
                "confirmed_sent_at": r.get("confirmed_sent_at", ""),
                "message_variant": r.get("message_variant", "ARI_MESSAGE_V1"),
                "reply_status": "none",
                "reply_classification": "NONE",
                "positive_reply": "false",
                "lp_visit_known": "unknown",
                "purchase_status": "none",
                "updated_at": datetime.now().isoformat(),
            })
            existing_ids.add(cid)
            added += 1
    return added


def _load_tracking_rows() -> list[dict]:
    ensure_tracking_csv()
    with TRACKING_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _find_tracking_row(domain: str, candidate_id: str | None = None) -> dict | None:
    domain = (domain or "").lower().strip()
    for row in _load_tracking_rows():
        if candidate_id and row.get("candidate_id") == candidate_id:
            return row
        if domain and (row.get("domain") or "").lower() == domain:
            return row
    return None


def update_reply_tracking(
    *,
    domain: str,
    company_name: str = "",
    candidate_id: str = "",
    reply_classification: str,
    positive_reply: bool | None = None,
    reply_status: str = "received",
    notes: str = "",
    confirmed_sent_at: str = "",
    message_variant: str = "ARI_MESSAGE_V1",
) -> tuple[bool, str]:
    """
    Update conversion tracking for a domain. Idempotent — no duplicate rows.
    Returns (updated, message).
    """
    if reply_classification not in REPLY_CLASSIFICATIONS:
        return False, f"invalid_classification:{reply_classification}"

    ensure_tracking_csv()
    rows = _load_tracking_rows()
    existing = _find_tracking_row(domain, candidate_id or None)
    now = datetime.now().isoformat()

    if positive_reply is None:
        positive_reply = reply_classification in ("INTERESTED", "MEETING_REQUEST", "PURCHASED")

    if existing:
        for row in rows:
            match = (
                (candidate_id and row.get("candidate_id") == candidate_id)
                or (domain and (row.get("domain") or "").lower() == domain.lower())
            )
            if not match:
                continue
            if row.get("reply_classification") == reply_classification and row.get("notes") == notes:
                return False, "already_recorded"
            row["reply_status"] = reply_status
            row["reply_classification"] = reply_classification
            row["positive_reply"] = "true" if positive_reply else "false"
            row["reply_at"] = row.get("reply_at") or now
            if notes:
                row["notes"] = notes
            row["updated_at"] = now
            break
    else:
        rows.append({
            "candidate_id": candidate_id,
            "company_name": company_name,
            "domain": domain,
            "confirmed_sent_at": confirmed_sent_at,
            "message_variant": message_variant,
            "reply_status": reply_status,
            "reply_at": now,
            "reply_classification": reply_classification,
            "positive_reply": "true" if positive_reply else "false",
            "lp_visit_known": "unknown",
            "purchase_status": "none",
            "purchase_at": "",
            "revenue": "",
            "notes": notes,
            "updated_at": now,
        })

    with TRACKING_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return True, "updated"


def record_auto_reply(
    *,
    domain: str,
    company_name: str = "",
    candidate_id: str = "",
    confirmed_sent_at: str = "",
    message_variant: str = "ARI_MESSAGE_V1",
    notes: str = "Automatic reply received",
) -> tuple[bool, str]:
    """Record AUTO_REPLY — not a positive reply, no purchase."""
    return update_reply_tracking(
        domain=domain,
        company_name=company_name,
        candidate_id=candidate_id,
        reply_classification="AUTO_REPLY",
        positive_reply=False,
        reply_status="received",
        notes=notes,
        confirmed_sent_at=confirmed_sent_at,
        message_variant=message_variant,
    )
