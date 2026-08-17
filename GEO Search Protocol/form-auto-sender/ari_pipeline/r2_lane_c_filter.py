"""
r2_lane_c_filter.py — Emergency Lane C: pattern-first generic contact supply.

Priority: real estate, moving, staffing, ordinary B2B/B2C service forms.
Excludes: remodel, dental, esthetic, medical, reservation-heavy surfaces.
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

# Priority tier 1 — explicit emergency target industries
LANE_C_TIER1_KWS = (
    "不動産", "賃貸", "物件", "プロパティ", "property", "real estate",
    "引越", "moving", "引っ越",
    "人材派遣", " staffing", "staffing", "recruit", "人材", "派遣",
)

# Priority tier 2 — ordinary B2B/B2C services (generic inquiry likely)
LANE_C_TIER2_KWS = (
    "清掃", "害虫", "害獣", "ガス", "電気", "水道", "リサイクル",
    "廃棄", "保管", "倉庫", "物流", "配送", "運送", "修理",
    "メンテナンス", "保守", "設備", "警備", "セキュリティ",
    "印刷", "看板", "広告", "デザイン", "制作", "コンサル",
    "税理", "会計", "司法書士", "行政書士", "社労士",
)

# Hard exclude — healthcare / beauty / reservation-heavy
LANE_C_EXCLUDE_KWS = (
    "歯科", "デンタル", "エステ", "美容", "クリニック", "病院", "医院",
    "医療", "精神科", "心療", "皮膚", "整形", "眼科", "耳鼻",
    "産婦", "小児", "内科", "外科", "透析", "薬局", "ドラッグ",
    "脱毛", "痩身", "ネイル", "まつげ",
    "予約専用", "初診", "再診", "診察",
)

_URL_STRONG = (
    "/contact", "/contact/", "/inquiry", "/inquiry/", "/otoiawase", "/toiawase",
    "/form", "/info/contact", "/support/contact", "/company/contact",
)
_URL_NEGATIVE = (
    "/reserve", "/reservation", "/booking", "/yoyaku", "/予約",
    "/appointment", "/shoshin", "/saishin",
)


def lane_c_industry_tier(industry: str, company_name: str = "") -> int | None:
    """Return 1, 2, or None if excluded."""
    blob = f"{industry} {company_name}"
    if is_remodel_industry(industry):
        return None
    if classify_r2_industry(industry) is not None:
        return None
    if any(k in blob for k in LANE_C_EXCLUDE_KWS):
        return None
    if any(k in blob for k in LANE_C_TIER1_KWS):
        return 1
    if any(k in blob for k in LANE_C_TIER2_KWS):
        return 2
    return None


def lane_c_url_pattern_score(website_url: str) -> int:
    u = (website_url or "").lower()
    score = 0
    if any(k in u for k in _URL_STRONG):
        score += 120
    elif any(k in u for k in ("contact", "inquiry", "otoiawase", "toiawase", "問い合わせ", "問合せ")):
        score += 70
    if any(k in u for k in _URL_NEGATIVE):
        score -= 200
    return score


def infer_contact_url(website_url: str) -> str:
    """When root URL only, infer likely contact path for LW (pattern-first)."""
    u = (website_url or "").strip().rstrip("/")
    if not u:
        return ""
    low = u.lower()
    if any(k in low for k in _URL_STRONG + ("contact", "inquiry", "otoiawase")):
        return u
    # pattern-first: try /contact/ before full site crawl
    return f"{u}/contact/"


def build_lane_c_pool(companies: list[dict], *, pool_date: str) -> dict[str, Any]:
    get_sent_domain_index.cache_clear()
    idx = get_sent_domain_index()
    seen: set[str] = set()
    exclusions = Counter()
    candidates: list[dict] = []

    for c in companies:
        industry = c.get("industry_name", "")
        name = c.get("company_name", "")
        dom = normalize_domain(c.get("website_url", ""))
        website = c.get("website_url", "")
        if not dom or dom in seen:
            continue
        seen.add(dom)

        tier = lane_c_industry_tier(industry, name)
        if tier is None:
            exclusions["excluded_industry"] += 1
            continue

        kw_ex = industry_name_excluded_by_keywords(industry, name)
        if kw_ex:
            exclusions[kw_ex] += 1
            continue

        if idx.is_confirmed_sent_domain(dom) or idx.should_no_resend(dom):
            exclusions["sent_or_attempted"] += 1
            continue

        url_score = lane_c_url_pattern_score(website)
        if url_score < -100:
            exclusions["reservation_url"] += 1
            continue

        lw_url = website if url_score >= 70 else infer_contact_url(website)

        candidates.append({
            "candidate_id": _candidate_id(c),
            "company_name": name,
            "domain": dom,
            "website_url": website,
            "lw_entry_url": lw_url,
            "industry_name": industry,
            "area_name": c.get("area_name", ""),
            "place_id": c.get("place_id", ""),
            "rating": c.get("rating"),
            "review_count": c.get("review_count"),
            "lane_c_tier": tier,
            "lane_c_bucket": industry,
            "supply_lane": "C",
            "url_pattern_score": url_score,
            "pool_date": pool_date,
        })

    candidates.sort(key=lambda r: (
        -r["url_pattern_score"],
        r["lane_c_tier"],
        -(int(r.get("review_count") or 0)),
        r.get("company_name", ""),
    ))

    tier_counts = Counter(c["lane_c_tier"] for c in candidates)
    url_tiers = Counter(
        "T1_URL" if c["url_pattern_score"] >= 120 else "T2_INFER" if c["url_pattern_score"] >= 70 else "T3_ROOT"
        for c in candidates
    )

    return {
        "pool_date": pool_date,
        "mode": "R2_LANE_C_PATTERN_FIRST",
        "prioritization": "URL_PATTERN_THEN_INDUSTRY_TIER",
        "stats": {
            "pool_size": len(candidates),
            "tier1_industries": tier_counts.get(1, 0),
            "tier2_industries": tier_counts.get(2, 0),
            "url_priority_tiers": dict(url_tiers),
            "contact_url_in_source": url_tiers.get("T1_URL", 0),
            "inferred_contact_paths": sum(1 for c in candidates if c.get("lw_entry_url") != c.get("website_url")),
            "exclusions": dict(exclusions),
        },
        "candidates": candidates,
    }
