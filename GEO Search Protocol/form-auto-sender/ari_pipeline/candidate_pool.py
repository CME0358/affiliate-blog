"""
ari_pipeline/candidate_pool.py — Build tomorrow's candidate pool from local data only (no web).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from config import INPUT_DIR, SKIP_INDUSTRIES, VAULT_ROOT
from log_manager import get_effective_sent_status, is_permanently_skipped
from parser import parse_md_list
from submission_state import (
    FORM_NOT_SUITABLE,
    MANUAL_INTERVENTION_REQUIRED,
    normalize_effective_status,
)

from ari_pipeline.sent_domain_index import get_sent_domain_index, normalize_domain

OUTPUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"

PREFERRED_INDUSTRY_KWS = (
    "リフォーム", "外壁", "塗装", "工務店", "建築", "住宅", "リノベ",
)
SECONDARY_INDUSTRY_KWS = (
    "税理士", "会計士", "行政書士", "司法書士", "士業",
)
LOW_PRIORITY_KWS = (
    "不動産", "法律事務所", "弁護士",
)
EXCLUDE_INDUSTRY_KWS = (
    "採用", "求人", "サポート専用", "整骨", "接骨", "鍼灸", "整体", "歯科",
)
EXCLUDE_NAME_KWS = (
    "採用", "求人", "カスタマーサポート", "ヘルプデスク",
)

LOCKED_DOMAINS = frozenset({
    "maru-kou.jp", "aoi-reform.com", "yamato-2013.co.jp", "space-m.net",
    "daiichi-jyusetu.co.jp", "lifew.co.jp", "mizoihome.com", "smile0033.com",
})


def _candidate_id(company: dict) -> str:
    dom = normalize_domain(company.get("website_url", ""))
    name = company.get("company_name", "")
    raw = f"{dom}|{name}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _industry_score(industry: str) -> int:
    ind = industry or ""
    if any(k in ind for k in EXCLUDE_INDUSTRY_KWS):
        return -100
    if any(k in ind for k in PREFERRED_INDUSTRY_KWS):
        return 100
    if any(k in ind for k in SECONDARY_INDUSTRY_KWS):
        return 50
    if any(k in ind for k in LOW_PRIORITY_KWS):
        return 10
    return 30


def _classify_exclusion(company: dict) -> tuple[bool, str]:
    """Domain-level exclusion using sent index + effective status policy."""
    name = company.get("company_name", "")
    url = company.get("website_url", "")
    dom = normalize_domain(url)
    industry = company.get("industry_name", "")

    if not dom or not url:
        return True, "no_website"

    idx = get_sent_domain_index()
    if dom in idx.confirmed_domains:
        return True, "EFFECTIVE_CONFIRMED_SENT"
    if dom in idx.historical_no_resend_domains:
        return True, "HISTORICAL_SENT_LEGACY"
    if dom in LOCKED_DOMAINS:
        return True, "FORENSIC_REVIEW_REQUIRED"

    if any(k in name for k in EXCLUDE_NAME_KWS):
        return True, "recruitment_or_support"
    if industry in SKIP_INDUSTRIES or any(k in industry for k in SKIP_INDUSTRIES):
        return True, "skip_industry"
    if any(k in industry for k in EXCLUDE_INDUSTRY_KWS):
        return True, "excluded_industry"

    if is_permanently_skipped(company)[0]:
        return True, "permanent_skip"

    eff = normalize_effective_status(get_effective_sent_status(name, url))
    if eff == FORM_NOT_SUITABLE:
        return True, "form_not_suitable"
    if eff == MANUAL_INTERVENTION_REQUIRED:
        return True, "manual_intervention"
    if eff in ("UNKNOWN", "CONFIRMATION_REACHED", "RUNTIME_DIVERGENCE"):
        return True, "FORENSIC_REVIEW_REQUIRED"

    return False, ""


def build_candidate_pool(
    *,
    pool_date: str = "2026-08-12",
    limit: int = 500,
    input_path: str | Path | None = None,
) -> dict:
    src = Path(input_path) if input_path else INPUT_DIR
    all_companies = parse_md_list(str(src))
    seen_domains: set[str] = set()
    exclusions = Counter()
    candidates: list[dict] = []

    scored: list[tuple[int, dict]] = []
    for c in all_companies:
        dom = normalize_domain(c.get("website_url", ""))
        if not dom:
            exclusions["no_website"] += 1
            continue
        if dom in seen_domains:
            exclusions["DUPLICATE_DOMAIN"] += 1
            continue
        seen_domains.add(dom)

        ex, reason = _classify_exclusion(c)
        if ex:
            exclusions[reason] += 1
            continue

        score = _industry_score(c.get("industry_name", ""))
        scored.append((score, c))

    scored.sort(key=lambda x: (-x[0], x[1].get("company_name", "")))

    for score, c in scored[:limit]:
        dom = normalize_domain(c.get("website_url", ""))
        candidates.append({
            "candidate_id": _candidate_id(c),
            "company_name": c.get("company_name", ""),
            "domain": dom,
            "website_url": c.get("website_url", ""),
            "industry_name": c.get("industry_name", ""),
            "area_name": c.get("area_name", ""),
            "place_id": c.get("place_id", ""),
            "rating": c.get("rating"),
            "review_count": c.get("review_count"),
            "priority_score": score,
            "stage": "LOCAL_FILTER",
            "status": "POOL_LOCKED",
            "source": str(src),
            "pool_date": pool_date,
            "locked_at": datetime.now().isoformat(),
        })

    industry_dist = Counter(c["industry_name"] for c in candidates)
    idx = get_sent_domain_index()
    stats = {
        "source_total": len(all_companies),
        "pool_size": len(candidates),
        "limit": limit,
        "exclusions": dict(exclusions),
        "exclusion_policy": (
            "Domain-level EFFECTIVE_CONFIRMED_SENT from sent.csv index (792 unique domains). "
            "NOT raw sent.csv row count (890) or fuzzy sales-list row matches (legacy ~885)."
        ),
        "official_confirmed_sent_domains": idx.effective_confirmed_sent,
        "industry_top20": industry_dist.most_common(20),
    }

    return {
        "pool_date": pool_date,
        "generated_at": datetime.now().isoformat(),
        "stats": stats,
        "candidates": candidates,
    }


def write_candidate_pool(pool_date: str = "2026-08-12", limit: int = 500) -> tuple[Path, Path]:
    pool = build_candidate_pool(pool_date=pool_date, limit=limit)
    return write_pool_artifacts(pool, pool_date=pool_date, limit=limit)


def write_pool_artifacts(pool: dict, *, pool_date: str | None = None, limit: int = 500) -> tuple[Path, Path]:
    pool_date = pool_date or pool.get("pool_date", "2026-08-12")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / f"ARI-Candidate-Pool-{pool_date}-500.json"
    md_path = OUTPUT_DIR / f"ARI Candidate Pool {pool_date}.md"
    json_path.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# ARI Candidate Pool {pool_date}",
        "",
        f"- Source total: {pool['stats']['source_total']}",
        f"- Pool size: {pool['stats']['pool_size']}",
        f"- Limit: {limit}",
        f"- Official CONFIRMED_SENT domains: {pool['stats']['official_confirmed_sent_domains']}",
        "",
        "## Exclusions",
        "",
        f"_{pool['stats']['exclusion_policy']}_",
        "",
    ]
    for k, v in sorted(pool["stats"]["exclusions"].items(), key=lambda x: -x[1]):
        lines.append(f"- {k}: {v}")
    lines.extend(["", "## Top Industries", ""])
    for ind, cnt in pool["stats"]["industry_top20"][:15]:
        lines.append(f"- {ind}: {cnt}")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path
