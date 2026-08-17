"""
ari_pipeline/sent_domain_index.py — Fast domain-level sent status index (local only).

Builds once from sent.csv + sent_row_audit.csv + sent_status_corrections.csv.
Used for pool exclusions and count reconciliation (avoids O(n) sent.csv scans per company).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache

from config import LOG_DIR, LOG_SENT
from submission_state import CONFIRMED_SENT, normalize_effective_status

LOG_SENT_ROW_AUDIT = LOG_DIR / "sent_row_audit.csv"
LOG_SENT_STATUS_CORRECTIONS = LOG_DIR / "sent_status_corrections.csv"


def normalize_domain(url: str) -> str:
    from urllib.parse import urlparse

    try:
        h = urlparse((url or "").strip()).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


@dataclass
class SentDomainIndex:
    """Domain-level effective status from sent.csv (countable rows only)."""

    confirmed_domains: set[str] = field(default_factory=set)
    historical_no_resend_domains: set[str] = field(default_factory=set)
    duplicate_non_countable_rows: int = 0
    raw_sent_rows: int = 0
    raw_unique_companies: int = 0
    raw_unique_domains: int = 0
    false_sent_corrected_domains: set[str] = field(default_factory=set)
    domain_to_status: dict[str, str] = field(default_factory=dict)

    @property
    def effective_confirmed_sent(self) -> int:
        return len(self.confirmed_domains)

    def is_confirmed_sent_domain(self, domain: str) -> bool:
        return domain in self.confirmed_domains

    def should_no_resend(self, domain: str) -> bool:
        """Domains that must not receive automated outreach again."""
        return domain in self.confirmed_domains or domain in self.historical_no_resend_domains


def build_sent_domain_index() -> SentDomainIndex:
    idx = SentDomainIndex()
    if not LOG_SENT.exists():
        return idx

    # Latest correction per domain
    corrections: dict[str, str] = {}
    if LOG_SENT_STATUS_CORRECTIONS.exists():
        with LOG_SENT_STATUS_CORRECTIONS.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                dom = normalize_domain(row.get("website_url", ""))
                if dom:
                    corrections[dom] = row.get("corrected_status", "")

    non_countable: set[int] = set()
    if LOG_SENT_ROW_AUDIT.exists():
        with LOG_SENT_ROW_AUDIT.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if (row.get("audit_status") or "") == "DUPLICATE_NON_COUNTABLE":
                    try:
                        non_countable.add(int(row.get("row_index_1based") or 0))
                    except ValueError:
                        pass
    idx.duplicate_non_countable_rows = len(non_countable)

    rows = list(csv.DictReader(LOG_SENT.open(encoding="utf-8", newline="")))
    idx.raw_sent_rows = sum(1 for r in rows if (r.get("status") or "").lower() == "sent")
    idx.raw_unique_companies = len({r.get("company_name", "") for r in rows if (r.get("status") or "").lower() == "sent"})
    idx.raw_unique_domains = len(
        {normalize_domain(r.get("website_url", "")) for r in rows if normalize_domain(r.get("website_url", ""))}
    )

    seen_domain: set[str] = set()
    for i, row in enumerate(rows):
        row_index = i + 2
        if row_index in non_countable:
            continue
        dom = normalize_domain(row.get("website_url", ""))
        if not dom or dom in seen_domain:
            continue
        seen_domain.add(dom)

        if dom in corrections:
            eff = normalize_effective_status(corrections[dom])
        else:
            eff = normalize_effective_status(row.get("status") or "sent")

        idx.domain_to_status[dom] = eff
        if eff == CONFIRMED_SENT:
            idx.confirmed_domains.add(dom)
        elif eff not in ("not_sent", "NOT_SENT", ""):
            idx.historical_no_resend_domains.add(dom)
            if eff not in (CONFIRMED_SENT,):
                idx.false_sent_corrected_domains.add(dom)

    return idx


@lru_cache(maxsize=1)
def get_sent_domain_index() -> SentDomainIndex:
    return build_sent_domain_index()
