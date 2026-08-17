#!/usr/bin/env python3
"""
run_ari_fast_path_queue_prep.py — Prepare dated Fast Production queues (ZERO SEND).
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))

import run_ari_terminal_production as rtp
from ari_pipeline.candidate_pool import _candidate_id, _industry_score, normalize_domain
from ari_pipeline.daily_fast_runner import daily_queue_path
from ari_pipeline.proven_pattern_library import (
    PROVEN_FAST_PATH,
    SLOW_PATH_REVIEW,
    classify_candidate,
    load_pattern_library,
    parse_daily_logs,
)
from ari_pipeline.sent_domain_index import get_sent_domain_index
from ari_pipeline.status_integrity import count_official_confirmed_sent
from config import INPUT_DIR, VAULT_ROOT
from form_sender import get_real_submission_count, set_submit_forbidden
from parser import parse_md_list
from ari_pipeline.production_queue_eligibility import (
    SEMANTIC_REFRESH_REQUIRED_ROUTE,
    assess_production_queue_eligibility,
)

OUTPUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"
PREFLIGHT_JSON = OUTPUT_DIR / "ARI-Full-Preflight-2026-08-12.json"
PREFLIGHT_CP = Path(__file__).resolve().parent / "logs/ari_checkpoints/full_preflight_2026-08-12.json"
REFRESH_JSON = OUTPUT_DIR / "ARI-AUTO-READY-Semantic-Refresh-2026-08-12.json"

QUEUE_DATES = ("2026-08-13", "2026-08-14", "2026-08-15")
FAST_PER_DAY = 1200  # pool size supporting 300 attempts with skips
ATTEMPTS_PER_DAY = 300


def _load_preflight_rows() -> dict[str, dict]:
    rows: dict[str, dict] = {}
    if PREFLIGHT_CP.exists():
        data = json.loads(PREFLIGHT_CP.read_text(encoding="utf-8"))
        for r in (data.get("results") or {}).values():
            dom = r.get("domain")
            if dom:
                rows[dom] = r
    elif PREFLIGHT_JSON.exists():
        for r in json.loads(PREFLIGHT_JSON.read_text()).get("results") or []:
            dom = r.get("domain")
            if dom:
                rows[dom] = r
    return rows


def _load_refresh_by_domain() -> dict[str, dict]:
    if not REFRESH_JSON.exists():
        return {}
    return {
        r["domain"]: r
        for r in json.loads(REFRESH_JSON.read_text()).get("results", [])
        if r.get("domain")
    }


def _url_contact_score(website_url: str) -> int:
    u = (website_url or "").lower()
    score = 0
    if any(k in u for k in ("/contact", "/inquiry", "/otoiawase", "/form", "/info")):
        score += 2
    if any(k in u for k in ("reform", "koumuten", "paint", "jutaku")):
        score += 1
    return score


def build_unsent_pool() -> list[dict]:
    get_sent_domain_index.cache_clear()
    idx = get_sent_domain_index()
    refresh = _load_refresh_by_domain()
    excluded, _ = rtp.build_canonical_exclusions()
    preflight = _load_preflight_rows()
    library = load_pattern_library()
    companies = parse_md_list(str(INPUT_DIR))
    seen: set[str] = set()
    pool: list[tuple[int, dict]] = []

    for c in companies:
        dom = normalize_domain(c.get("website_url", ""))
        if not dom or dom in seen:
            continue
        seen.add(dom)
        if idx.should_no_resend(dom) or dom in excluded:
            continue

        pf = preflight.get(dom, {})
        merged = {**c, **pf}
        merged["domain"] = dom
        merged["candidate_id"] = pf.get("candidate_id") or _candidate_id(c)

        cls = classify_candidate(
            merged, library=library, sent_index=idx,
            excluded_domains=excluded, refresh_row=refresh.get(dom),
        )
        merged["fast_path_classification"] = cls

        eligible, elig_reason, elig_detail = assess_production_queue_eligibility(
            merged, refresh_row=refresh.get(dom), library=library, sent_index=idx, excluded_domains=excluded,
        )
        merged["production_queue_eligible"] = eligible
        merged["production_queue_reason"] = elig_reason
        merged["production_queue_detail"] = elig_detail

        score = _industry_score(c.get("industry_name", ""))
        score += _url_contact_score(c.get("website_url", ""))
        if eligible:
            score += 300
        elif cls.get("classification") == PROVEN_FAST_PATH:
            score += 50  # pattern match but needs refresh — supply stage only
        elif pf.get("preflight_classification") == AUTO_READY:
            score += 100
        elif cls.get("classification") == SLOW_PATH_REVIEW and pf:
            score += 40
        pool.append((score, merged))

    pool.sort(key=lambda x: (-x[0], x[1].get("company_name", "")))
    return [c for _, c in pool]


def _queue_candidate(row: dict, *, queue_date: str, queue_index: int) -> dict:
    cls = row.get("fast_path_classification") or {}
    return {
        "queue_index": queue_index,
        "queue_date": queue_date,
        "candidate_id": row.get("candidate_id", ""),
        "company_name": row.get("company_name", ""),
        "domain": row.get("domain", ""),
        "website_url": row.get("website_url", ""),
        "form_url": row.get("form_url", ""),
        "industry_name": row.get("industry_name", ""),
        "area_name": row.get("area_name", ""),
        "place_id": row.get("place_id", ""),
        "preflight_classification": row.get("preflight_classification"),
        "preflight_outcome": row.get("preflight_outcome"),
        "classification": (
            "PROVEN_FAST_PATH" if row.get("production_queue_eligible")
            else cls.get("classification", "SLOW_PATH_REVIEW")
        ),
        "production_eligibility": row.get("production_queue_reason", ""),
        "matched_pattern_id": cls.get("matched_pattern_id"),
        "pattern_tier": cls.get("pattern_tier"),
        "framework": cls.get("framework"),
    }


def prepare_queues(pool: list[dict]) -> dict[str, Any]:
    # Only production-ready: proven pattern + current REFRESH_READY evidence
    ready = [c for c in pool if c.get("production_queue_eligible")]
    needs_refresh = [c for c in pool if not c.get("production_queue_eligible") and (c.get("fast_path_classification") or {}).get("classification") == PROVEN_FAST_PATH]

    ordered: list[dict] = []
    seen: set[str] = set()
    for c in ready:
        dom = c.get("domain", "")
        if dom in seen:
            continue
        seen.add(dom)
        ordered.append(c)

    queues: dict[str, Any] = {}
    offset = 0
    for date in QUEUE_DATES:
        slice_rows = ordered[offset: offset + FAST_PER_DAY]
        offset += FAST_PER_DAY
        candidates = [_queue_candidate(r, queue_date=date, queue_index=i + 1) for i, r in enumerate(slice_rows)]
        fast_count = sum(1 for c in candidates if c.get("classification") == PROVEN_FAST_PATH)
        payload = {
            "generated_at": datetime.now().isoformat(),
            "queue_date": date,
            "target_attempts": ATTEMPTS_PER_DAY,
            "pool_size": len(candidates),
            "proven_fast_path_count": fast_count,
            "auto_ready_buffer_count": sum(1 for c in candidates if c.get("preflight_classification") == AUTO_READY),
            "selection_policy": "production_ready_current_semantic_evidence_only",
            "needs_semantic_refresh_count": len(needs_refresh),
            "candidates": candidates,
        }
        path = daily_queue_path(date)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("immutable") and existing.get("candidates"):
                queues[date] = {
                    "path": str(path),
                    "pool_size": len(existing.get("candidates") or []),
                    "proven_fast_path_count": existing.get("proven_fast_path_count", 0),
                    "preserved_immutable": True,
                }
                continue
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        queues[date] = {
            "path": str(path),
            "pool_size": len(candidates),
            "proven_fast_path_count": fast_count,
        }

    return {
        "queues": queues,
        "total_unsent_pool": len(pool),
        "proven_fast_path_total": len(ready),
        "needs_semantic_refresh_total": len(needs_refresh),
        "auto_ready_total": sum(1 for c in pool if c.get("preflight_classification") == "AUTO_READY"),
        "classification_counts": dict(Counter(
            (c.get("fast_path_classification") or {}).get("classification", "UNKNOWN") for c in pool
        )),
    }


def throughput_forecast(pool: list[dict], queue_meta: dict) -> dict[str, Any]:
    cls = Counter((c.get("fast_path_classification") or {}).get("classification") for c in pool)
    ready_n = sum(1 for c in pool if c.get("production_queue_eligible"))
    needs_refresh_n = sum(1 for c in pool if not c.get("production_queue_eligible") and cls.get(PROVEN_FAST_PATH, 0) and (c.get("fast_path_classification") or {}).get("classification") == PROVEN_FAST_PATH)
    total = len(pool) or 1
    est_yield = min(1.0, ready_n / max(total, 1) * 0.85)
    attempts_per_1200 = int(1200 * est_yield)
    runtime_min_per_attempt = 2.5  # minutes incl skip/send interval
    est_runtime_hours = ATTEMPTS_PER_DAY * runtime_min_per_attempt / 60

    return {
        "remaining_source_count": total,
        "production_ready_count": ready_n,
        "needs_semantic_refresh_count": needs_refresh_n,
        "fast_path_match_rate_pct": round(cls.get(PROVEN_FAST_PATH, 0) / total * 100, 1),
        "slow_path_review_count": cls.get(SLOW_PATH_REVIEW, 0),
        "estimated_yield_per_1200_pool": attempts_per_1200,
        "estimated_runtime_hours_for_300_attempts": round(est_runtime_hours, 1),
        "aug_13_queue": queue_meta["queues"].get("2026-08-13", {}),
        "aug_14_queue": queue_meta["queues"].get("2026-08-14", {}),
        "aug_15_queue": queue_meta["queues"].get("2026-08-15", {}),
        "estimated_attempts_per_day": min(ATTEMPTS_PER_DAY, attempts_per_1200),
    }


def main() -> None:
    set_submit_forbidden(True)
    pool = build_unsent_pool()
    queue_meta = prepare_queues(pool)
    forecast = throughput_forecast(pool, queue_meta)

    audit_path = OUTPUT_DIR / "ARI-Proven-Form-Pattern-Library.json"
    library = load_pattern_library(audit_path) if audit_path.exists() else {}

    report = {
        "timestamp": datetime.now().isoformat(),
        "mode": "FAST_PATH_QUEUE_PREP",
        "real_sends": get_real_submission_count(),
        "effective_confirmed_sent": count_official_confirmed_sent(),
        "queue_meta": queue_meta,
        "throughput_forecast": forecast,
        "pattern_library": {
            "patterns": library.get("patterns_extracted"),
            "tier_a": library.get("tier_a_count"),
            "tier_b": library.get("tier_b_count"),
            "fast_path_eligible": library.get("fast_path_eligible_patterns"),
        },
    }
    out = OUTPUT_DIR / "ARI-Fast-Path-Queue-Prep-2026-08-13.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
