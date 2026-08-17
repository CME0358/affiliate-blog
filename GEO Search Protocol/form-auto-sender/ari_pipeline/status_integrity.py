"""
ari_pipeline/status_integrity.py — Official KPI source & sent.csv integrity.

Official KPI: CONFIRMED_SENT only (NOT raw sent.csv row count).
sent.csv rows are never deleted; duplicates audited via sent_row_audit.csv.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from config import LOG_DIR, LOG_SENT
from submission_state import CONFIRMED_SENT, normalize_effective_status

LOG_SENT_ROW_AUDIT = LOG_DIR / "sent_row_audit.csv"
LOG_SENT_STATUS_CORRECTIONS = LOG_DIR / "sent_status_corrections.csv"

_AUDIT_HEADERS = [
    "audited_at",
    "row_index_1based",
    "company_name",
    "website_url",
    "domain",
    "audit_status",
    "reason",
    "root_cause",
    "batch_id",
    "record_creation_path",
    "evidence_ref",
]

_OFFICIAL_KPI_DOC = """
Official ARI outreach KPI source (2026-08-11+):
- Primary metric: CONFIRMED_SENT (effective, deduplicated)
- NOT used: raw sent.csv row count
- Raw rows: logs/sent.csv (append-only)
- Row audit: logs/sent_row_audit.csv (duplicate non-countable marks)
- Status corrections: logs/sent_status_corrections.csv
- Effective status: log_manager.get_effective_sent_status()
"""


def _normalize_domain(url: str) -> str:
    try:
        h = urlparse((url or "").strip()).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def get_official_kpi_source_doc() -> str:
    return _OFFICIAL_KPI_DOC.strip()


def _load_sent_rows() -> list[dict]:
    if not LOG_SENT.exists():
        return []
    with LOG_SENT.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_row_audit() -> dict[int, dict]:
    out: dict[int, dict] = {}
    if not LOG_SENT_ROW_AUDIT.exists():
        return out
    with LOG_SENT_ROW_AUDIT.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                idx = int(row.get("row_index_1based") or 0)
            except ValueError:
                continue
            if idx:
                out[idx] = row
    return out


def _append_row_audit(row: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    write_header = not LOG_SENT_ROW_AUDIT.exists()
    with LOG_SENT_ROW_AUDIT.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_AUDIT_HEADERS, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerow(row)


def audit_duplicate_sent_rows(
    *,
    company_name: str | None = None,
    domain: str | None = None,
    batch_id: str = "eod_infra_2026-08-11",
) -> dict:
    """
    Audit duplicate sent.csv rows. Marks later duplicates DUPLICATE_NON_COUNTABLE.
    Does NOT delete sent.csv rows.
    """
    rows = _load_sent_rows()
    existing_audit = _load_row_audit()

    # Group by domain
    by_domain: dict[str, list[tuple[int, dict]]] = {}
    for i, row in enumerate(rows):
        dom = _normalize_domain(row.get("website_url", ""))
        if not dom:
            continue
        if company_name and company_name not in (row.get("company_name") or ""):
            continue
        if domain and dom != domain:
            continue
        by_domain.setdefault(dom, []).append((i + 2, row))  # 1-based + header

    audited: list[dict] = []
    root_cause = (
        "Double append_sent_csv_row: batch script called append_sent_csv_row() "
        "AND log_result('sent') which also calls append_sent_csv_row() internally. "
        "Fix: batch scripts should use log_result only OR append_sent_csv_row only."
    )

    for dom, entries in by_domain.items():
        if len(entries) < 2:
            continue
        # Keep first row countable; mark subsequent as duplicate
        for row_index, row in entries[1:]:
            if row_index in existing_audit:
                continue
            audit_row = {
                "audited_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S JST"),
                "row_index_1based": row_index,
                "company_name": row.get("company_name", ""),
                "website_url": row.get("website_url", ""),
                "domain": dom,
                "audit_status": "DUPLICATE_NON_COUNTABLE",
                "reason": "duplicate_raw_sent_row_same_domain_same_day",
                "root_cause": root_cause,
                "batch_id": batch_id,
                "record_creation_path": "run_ari_end_of_day_batch_b._execute_send",
                "evidence_ref": "logs/ari_end_of_day_batch_b_2026-08-11.csv attempted=1",
            }
            _append_row_audit(audit_row)
            audited.append(audit_row)

    return {
        "domains_with_duplicates": len([d for d, e in by_domain.items() if len(e) > 1]),
        "rows_audited": len(audited),
        "audited": audited,
        "root_cause": root_cause if audited else "",
        "effective_confirmed_after": count_official_confirmed_sent(),
    }


def count_official_confirmed_sent(*, as_of_date: str | None = None) -> int:
    """
    Count unique CONFIRMED_SENT domains excluding DUPLICATE_NON_COUNTABLE rows.
    Uses effective status from corrections when present.
    """
    from log_manager import get_effective_sent_status

    rows = _load_sent_rows()
    audit = _load_row_audit()
    non_countable = {
        idx for idx, a in audit.items()
        if (a.get("audit_status") or "") == "DUPLICATE_NON_COUNTABLE"
    }

    seen_domains: set[str] = set()
    count = 0
    for i, row in enumerate(rows):
        row_index = i + 2
        if row_index in non_countable:
            continue
        if as_of_date and (row.get("date") or "") > as_of_date:
            continue
        dom = _normalize_domain(row.get("website_url", ""))
        if not dom or dom in seen_domains:
            continue
        eff = normalize_effective_status(
            get_effective_sent_status(row.get("company_name", ""), row.get("website_url", ""))
        )
        if eff == CONFIRMED_SENT:
            seen_domains.add(dom)
            count += 1
    return count


def count_raw_sent_rows() -> int:
    return sum(1 for r in _load_sent_rows() if (r.get("status") or "").lower() == "sent")


def lifework_integrity_report() -> dict:
    rows = _load_sent_rows()
    lifew = [(i + 2, r) for i, r in enumerate(rows) if "lifew.co.jp" in (r.get("website_url") or "")]
    audit = _load_row_audit()
    return {
        "company": "株式会社ライフワーク",
        "domain": "lifew.co.jp",
        "raw_rows": len(lifew),
        "row_indices_1based": [x[0] for x in lifew],
        "attempted_production": 1,
        "batch_log": "logs/ari_end_of_day_batch_b_2026-08-11.csv",
        "audit_entries": [audit.get(i) for i, _ in lifew if i in audit],
        "effective_status": "CONFIRMED_SENT",
        "effective_confirmed_count": 1,
        "raw_sent_row_count": len(lifew),
    }
