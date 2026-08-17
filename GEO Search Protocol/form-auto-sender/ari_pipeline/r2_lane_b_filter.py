"""
r2_lane_b_filter.py — Evidence-ranked fallback supply lane (non-remodeling).

Uses historical CONFIRMED_SENT industry distribution from local MD dataset.
Lane A = dental + esthetic. Lane B = highest-throughput non-remodel industries.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from ari_pipeline.candidate_pool import _candidate_id
from ari_pipeline.r2_industry_filter import (
    classify_r2_industry,
    industry_name_excluded_by_keywords,
    is_remodel_industry,
)
from ari_pipeline.sent_domain_index import get_sent_domain_index, normalize_domain
from parser import parse_md_list


def _confirmed_industry_counts(companies: list[dict]) -> Counter[str]:
    get_sent_domain_index.cache_clear()
    idx = get_sent_domain_index()
    by_dom = {normalize_domain(c.get("website_url", "")): c for c in companies}
    counts: Counter[str] = Counter()
    for dom in idx.confirmed_domains:
        row = by_dom.get(dom)
        if not row:
            continue
        ind = (row.get("industry_name") or "").strip()
        if ind and not is_remodel_industry(ind) and classify_r2_industry(ind) is None:
            counts[ind] += 1
    return counts


def rank_lane_b_industries(companies: list[dict], *, top_n: int = 15) -> list[dict[str, Any]]:
    """Rank non-remodel, non-R2 industries by historical CONFIRMED_SENT count."""
    counts = _confirmed_industry_counts(companies)
    ranked = [
        {"industry_name": ind, "confirmed_sent_count": n}
        for ind, n in counts.most_common(top_n)
    ]
    return ranked


def build_lane_b_pool(companies: list[dict], *, pool_date: str) -> dict[str, Any]:
    """Build fallback candidate pool from evidence-ranked industries."""
    get_sent_domain_index.cache_clear()
    idx = get_sent_domain_index()
    ranked = rank_lane_b_industries(companies)
    allowed = {r["industry_name"] for r in ranked[:12]}

    seen: set[str] = set()
    exclusions = Counter()
    candidates: list[dict] = []

    for c in companies:
        industry = c.get("industry_name", "")
        name = c.get("company_name", "")
        dom = normalize_domain(c.get("website_url", ""))
        if not dom or dom in seen:
            continue
        if is_remodel_industry(industry) or classify_r2_industry(industry) is not None:
            continue
        if industry not in allowed:
            exclusions["industry_not_in_lane_b_rank"] += 1
            continue
        if industry_name_excluded_by_keywords(industry, name):
            exclusions["keyword_excluded"] += 1
            continue
        if idx.is_confirmed_sent_domain(dom) or idx.should_no_resend(dom):
            exclusions["sent_or_attempted"] += 1
            continue
        seen.add(dom)
        candidates.append({
            "candidate_id": _candidate_id(c),
            "company_name": name,
            "domain": dom,
            "website_url": c.get("website_url", ""),
            "industry_name": industry,
            "area_name": c.get("area_name", ""),
            "place_id": c.get("place_id", ""),
            "rating": c.get("rating"),
            "review_count": c.get("review_count"),
            "lane_b_bucket": industry,
            "supply_lane": "B",
            "pool_date": pool_date,
        })

    return {
        "pool_date": pool_date,
        "mode": "R2_LANE_B_EVIDENCE_RANKED",
        "industry_ranking": ranked,
        "stats": {
            "pool_size": len(candidates),
            "allowed_industries": sorted(allowed),
            "exclusions": dict(exclusions),
        },
        "candidates": candidates,
    }


def should_activate_lane_b(metrics: dict[str, Any], *, ready_count: int, min_ready: int = 20) -> bool:
    """Activate Lane B when Lane A yield cannot supply next micro-batch in time."""
    if ready_count >= min_ready:
        return False
    processed = metrics.get("processed") or 0
    if processed < 50:
        return False
    if metrics.get("refresh_ready_rate", 0) == 0 and processed >= 50:
        return True
    chain = (
        metrics.get("contact_form_rate", 0)
        * metrics.get("preflight_processed_rate", 0)
        * metrics.get("refresh_ready_rate", 0)
    )
    return chain < 0.02
