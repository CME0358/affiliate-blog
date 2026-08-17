"""
observations/crawler_join.py — Join outbound candidates to latest crawler CSV rows by domain.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_OBS_ROOT = Path(__file__).resolve().parent
_VAULT_ROOT = _OBS_ROOT.parents[3]  # observations → form-auto-sender → GEO Search Protocol → 10_Projects → Obsidian_Vault
CRAWLER_ROOT = _VAULT_ROOT / "40_Sales" / "営業自動化ツール" / "reservation_crawler"

MASTER_INDEX_CSV = CRAWLER_ROOT / "data" / "master" / "agent_readiness_index_all.csv"
MASTER_RESERVATION_CSV = CRAWLER_ROOT / "data" / "master" / "reservation_results_all.csv"
FITNESS_INDEX_CSV = CRAWLER_ROOT / "data" / "fitness_master" / "agent_readiness_index_all.csv"
FITNESS_RESERVATION_CSV = CRAWLER_ROOT / "data" / "fitness_master" / "reservation_results_all.csv"


def normalize_domain(url: str) -> str:
    """Local copy — avoid config-dependent import for observation tooling."""
    raw = (url or "").strip().lower()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    try:
        host = urlparse(raw).netloc or urlparse(raw).path.split("/")[0]
    except Exception:
        return ""
    return host.removeprefix("www.")


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def _load_index_by_domain() -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for path in (MASTER_INDEX_CSV, FITNESS_INDEX_CSV):
        for row in _read_csv(path):
            dom = normalize_domain(row.get("url", ""))
            if not dom:
                continue
            prev = rows.get(dom)
            if not prev or (row.get("run_date", "") or "") >= (prev.get("run_date", "") or ""):
                rows[dom] = row
    return rows


@lru_cache(maxsize=1)
def _load_reservation_by_domain() -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for path in (MASTER_RESERVATION_CSV, FITNESS_RESERVATION_CSV):
        for row in _read_csv(path):
            dom = normalize_domain(row.get("url", ""))
            if not dom:
                continue
            prev = rows.get(dom)
            if not prev or (row.get("run_date", "") or "") >= (prev.get("run_date", "") or ""):
                rows[dom] = row
    return rows


def lookup_crawler_data(
    website_url: str,
    *,
    company_name: str = "",
) -> dict[str, Any] | None:
    """Return merged crawler row for domain, or None if not found."""
    dom = normalize_domain(website_url)
    if not dom:
        return None

    index_row = _load_index_by_domain().get(dom)
    if not index_row:
        return None

    reservation_row = _load_reservation_by_domain().get(dom, {})
    merged = dict(index_row)
    merged.update({
        k: v for k, v in reservation_row.items()
        if k not in merged or not merged.get(k)
    })
    if company_name and not merged.get("clinic_name"):
        merged["clinic_name"] = company_name
    merged["site_reachable"] = True
    return merged


def lookup_crawler_data_for_company(company: dict[str, Any]) -> dict[str, Any] | None:
    return lookup_crawler_data(
        company.get("website_url") or company.get("url") or "",
        company_name=company.get("company_name") or company.get("clinic_name") or "",
    )


def lookup_generic_scan(domain: str) -> dict[str, Any] | None:
    from observations.generic_scan_store import load_generic_scan

    dom = normalize_domain(domain) or (domain or "").lower().removeprefix("www.")
    if not dom:
        return None
    row = load_generic_scan(dom)
    if not row or row.get("evidence_source") != "generic_scan":
        return None
    return row


def lookup_preview_evidence(
    company: dict[str, Any],
    *,
    prefer: str = "auto",
) -> tuple[dict[str, Any] | None, str]:
    """
    Unified preview evidence lookup.

    Priority:
      1. valid reservation crawler evidence
      2. valid generic scan evidence (site_reachable + scanned signals)
      3. none

    Returns (evidence_row, source_label).
    """
    reservation = lookup_crawler_data_for_company(company)
    if reservation and prefer in ("auto", "reservation"):
        reservation = {**reservation, "evidence_source": "reservation_crawler"}
        return reservation, "reservation_crawler"

    dom = company.get("domain") or normalize_domain(
        company.get("website_url") or company.get("url") or ""
    )
    generic = lookup_generic_scan(dom)
    if generic and generic.get("site_reachable") and prefer in ("auto", "generic"):
        return generic, "generic_scan"

    if prefer == "auto" and generic:
        return None, "generic_scan_unreachable"

    return None, "none"
