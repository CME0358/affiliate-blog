#!/usr/bin/env python3
"""
run_ari_r2_supply_pipeline.py — R2 dental + esthetic production supply (ZERO SEND).

Pipeline:
  LOCAL_FILTER → LIGHTWEIGHT_DETECT → BUSINESS_SURFACE → FULL_PREFLIGHT
  → SEMANTIC_REFRESH → OPERATIONAL_READINESS → R2 QUEUE

REAL SENDS = 0 / FINAL_SUBMIT = 0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))

import run_ari_auto_ready_semantic_refresh as refresh_mod
import run_ari_full_preflight as fp_mod
from ari_pipeline.business_inquiry_surface import assess_from_lightweight_record
from ari_pipeline.candidate_pool import _candidate_id
from ari_pipeline.daily_fast_runner import (
    daily_queue_path,
    daily_state_path,
    init_daily_state,
    write_daily_state,
)
from ari_pipeline.orchestrator import (
    Stage,
    init_lightweight_run_from_pool,
    load_checkpoint,
    run_lightweight_detect_stage,
    save_checkpoint,
)
from ari_pipeline.production_queue_eligibility import assess_production_queue_eligibility
from ari_pipeline.proven_pattern_library import classify_candidate, load_pattern_library
from ari_pipeline.queue_evidence_contract import build_queue_authorization
from ari_pipeline.r2_industry_filter import (
    classify_r2_industry,
    industry_name_excluded_by_keywords,
    is_remodel_industry,
)
from ari_pipeline.r2_streaming_queue import (
    SUPPLY_CHECKPOINT as STREAMING_SUPPLY_CP,
    maybe_record_yield_checkpoint,
    save_supply_checkpoint,
    try_seal_next_batch,
)
from ari_pipeline.sent_domain_index import get_sent_domain_index, normalize_domain
from ari_pipeline.status_integrity import count_official_confirmed_sent
from automation_state import is_paused, set_paused
from config import INPUT_DIR, LOG_DIR, VAULT_ROOT
from form_field_resolver import clear_field_cache
from form_sender import get_real_submission_count, reset_real_submission_count, set_submit_forbidden
from inquiry_purpose_semantics import audit_selected_purpose
from parser import parse_md_list

OUTPUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"
QUEUE_DATE = "2026-08-13"
QUEUE_REVISION = "R2"
TARGET_READY = 400
PREFERRED_READY = 450
R2_YIELD_ATTEMPT = 35 / 42  # observed R1-fixed

CHECKPOINT = STREAMING_SUPPLY_CP
POOL_JSON = OUTPUT_DIR / "ARI-R2-Candidate-Pool-2026-08-13.json"
LW_RUN_ID = "r2_lw_2026-08-13"
PREFLIGHT_JSON = OUTPUT_DIR / "ARI-R2-Full-Preflight-2026-08-13.json"
REFRESH_JSON = OUTPUT_DIR / "ARI-R2-Semantic-Refresh-2026-08-13.json"
R2_QUEUE = daily_queue_path(QUEUE_DATE, revision=QUEUE_REVISION)
REPORT_JSON = OUTPUT_DIR / "ARI-R2-Supply-Report-2026-08-13.json"

# URL priority tiers — process high-yield contact surfaces first
_PRIORITY_STRONG = (
    "/contact", "/inquiry", "/inquiry/", "/otoiawase", "/toiawase", "/form",
    "/info", "/support/contact", "/company/contact", "/about/contact",
)
_PRIORITY_MEDIUM = (
    "/about", "/company", "/corporate", "/profile", "/access",
)
_PRIORITY_NEGATIVE = (
    "/reserve", "/reservation", "/booking", "/yoyaku", "/appointment",
    "/shoshin", "/初診", "/saishin", "/counseling-reserve", "/member",
)


def _r2_url_priority_score(website_url: str, *, review_count: int = 0) -> int:
    u = (website_url or "").lower()
    score = 0
    if any(k in u for k in _PRIORITY_STRONG):
        score += 100
    elif any(k in u for k in ("contact", "inquiry", "otoiawase", "toiawase", "問い合わせ", "問合せ")):
        score += 60
    if any(k in u for k in _PRIORITY_MEDIUM):
        score += 25
    if any(k in u for k in _PRIORITY_NEGATIVE):
        score -= 150
    # Established businesses slightly higher yield in practice
    score += min(int(review_count or 0) // 50, 15)
    return score


def _sort_r2_candidates(candidates: list[dict]) -> list[dict]:
    """High contact URL score first; dental before esthetic at equal score (~55% dental target)."""
    enriched: list[dict] = []
    for row in candidates:
        score = _r2_url_priority_score(row.get("website_url", ""), review_count=int(row.get("review_count") or 0))
        bucket = row.get("r2_industry_bucket", "")
        bucket_rank = 0 if bucket == "dental" else 1
        enriched.append({**row, "url_priority_score": score, "url_priority_tier": (
            "T1_CONTACT" if score >= 100 else "T2_MEDIUM" if score >= 25 else "T3_DEFAULT" if score >= 0 else "T4_RESERVATION"
        )})
    enriched.sort(key=lambda r: (
        -r["url_priority_score"],
        bucket_rank,
        r.get("area_name", ""),
        r.get("company_name", ""),
    ))
    return enriched


def _ensure_safety() -> None:
    if not is_paused("form-auto-sender"):
        set_paused("form-auto-sender", True, by="run_ari_r2_supply_pipeline.py")
    set_submit_forbidden(True)
    reset_real_submission_count()


def _load_cp() -> dict:
    if CHECKPOINT.exists():
        cp = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    else:
        cp = {}
    cp.setdefault("preflight_results", {})
    cp.setdefault("refresh_results", {})
    return cp


def _save_cp(state: dict) -> None:
    save_supply_checkpoint(state)


def build_r2_local_pool() -> dict:
    get_sent_domain_index.cache_clear()
    idx = get_sent_domain_index()
    all_companies = parse_md_list(str(INPUT_DIR))
    seen: set[str] = set()
    exclusions = Counter()
    dental: list[dict] = []
    esthetic: list[dict] = []

    for c in all_companies:
        industry = c.get("industry_name", "")
        name = c.get("company_name", "")
        dom = normalize_domain(c.get("website_url", ""))
        if not dom:
            exclusions["no_website"] += 1
            continue
        if dom in seen:
            exclusions["duplicate_domain"] += 1
            continue
        seen.add(dom)

        bucket = classify_r2_industry(industry)
        if bucket is None:
            if is_remodel_industry(industry):
                exclusions["remodel_excluded"] += 1
            else:
                exclusions["non_r2_industry"] += 1
            continue

        kw_ex = industry_name_excluded_by_keywords(industry, name)
        if kw_ex:
            exclusions[kw_ex] += 1
            continue

        if idx.is_confirmed_sent_domain(dom):
            exclusions["confirmed_sent"] += 1
            continue
        if idx.should_no_resend(dom):
            exclusions["historical_attempt"] += 1
            continue

        row = {
            "candidate_id": _candidate_id(c),
            "company_name": name,
            "domain": dom,
            "website_url": c.get("website_url", ""),
            "industry_name": industry,
            "area_name": c.get("area_name", ""),
            "place_id": c.get("place_id", ""),
            "rating": c.get("rating"),
            "review_count": c.get("review_count"),
            "r2_industry_bucket": bucket,
            "pool_date": QUEUE_DATE,
        }
        if bucket == "dental":
            dental.append(row)
        else:
            esthetic.append(row)

    candidates = _sort_r2_candidates(dental + esthetic)
    tier_counts = Counter(c.get("url_priority_tier") for c in candidates)
    tier_dental = Counter(c.get("url_priority_tier") for c in candidates if c.get("r2_industry_bucket") == "dental")

    pool = {
        "pool_date": QUEUE_DATE,
        "generated_at": datetime.now().isoformat(),
        "mode": "R2_DENTAL_ESTHETIC_LOCAL_FILTER",
        "prioritization": "URL_CONTACT_SCORE_DENTAL_FIRST",
        "stats": {
            "source_total": len(all_companies),
            "dental_available": len(dental),
            "esthetic_available": len(esthetic),
            "pool_size": len(candidates),
            "url_priority_tiers": dict(tier_counts),
            "dental_url_priority_tiers": dict(tier_dental),
            "tier1_contact_count": tier_counts.get("T1_CONTACT", 0),
            "exclusions": dict(exclusions),
        },
        "candidates": candidates,
    }
    POOL_JSON.parent.mkdir(parents=True, exist_ok=True)
    POOL_JSON.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")
    return pool


def reprioritize_lightweight_checkpoint(pool: dict) -> dict:
    """Reorder pending LW candidates by URL priority; preserve completed results by domain."""
    old = load_checkpoint(LW_RUN_ID) or {}
    old_by_domain = {
        (c.get("domain") or "").lower(): c
        for c in old.get("candidates") or []
        if c.get("domain")
    }
    merged: list[dict] = []
    preserved = 0
    for c in pool.get("candidates") or []:
        dom = (c.get("domain") or "").lower()
        prev = old_by_domain.get(dom)
        if prev and prev.get("status") == "completed":
            merged.append({**prev, **{k: c[k] for k in ("url_priority_score", "url_priority_tier", "r2_industry_bucket") if k in c}})
            preserved += 1
        else:
            merged.append({
                **c,
                "stage": Stage.LIGHTWEIGHT_DETECT.value,
                "status": "pending",
                "reason": "",
                "lightweight_outcome": "",
                "lightweight_classification": "",
                "lightweight_score": 0,
                "lightweight_reason": "",
                "form_url": c.get("form_url", ""),
                "form_type": "",
                "captcha": False,
                "message_variant": "",
                "mapping_hash": "",
                "effective_status": "not_sent",
                "last_checked_at": "",
            })

    state = {
        "run_id": LW_RUN_ID,
        "pool_date": pool.get("pool_date"),
        "started_at": old.get("started_at") or datetime.now().isoformat(),
        "reprioritized_at": datetime.now().isoformat(),
        "prioritization": pool.get("prioritization"),
        "current_stage": Stage.LIGHTWEIGHT_DETECT.value,
        "limits": old.get("limits") or {},
        "candidates": merged,
        "stats": old.get("stats") or {"processed": preserved, "by_outcome": {}, "runtime_errors": 0},
        "dry_run": False,
        "production_blocked": True,
        "preserved_completed": preserved,
    }
    _recompute_lw_stats(state)
    save_checkpoint(state)
    return state


def _recompute_lw_stats(state: dict) -> None:
    candidates = state.get("candidates") or []
    completed = [c for c in candidates if c.get("status") == "completed"]
    outcomes = Counter(c.get("lightweight_outcome") or "UNKNOWN" for c in completed)
    state["stats"]["processed"] = len(completed)
    state["stats"]["by_outcome"] = dict(outcomes)
    state["stats"]["runtime_errors"] = sum(
        1 for c in completed if c.get("lightweight_outcome") == "INTERNAL_ERROR"
    )


async def run_lightweight_batch(pool: dict, *, batch_size: int) -> dict:
    state = load_checkpoint(LW_RUN_ID)
    if not state:
        state = init_lightweight_run_from_pool(pool, LW_RUN_ID)
    idx = get_sent_domain_index()
    confirmed = set(idx.confirmed_domains)
    processed = {
        (c.get("domain") or "").lower()
        for c in state.get("candidates") or []
        if c.get("status") == "completed" and c.get("domain")
    }
    state = await run_lightweight_detect_stage(
        state,
        max_items=batch_size,
        confirmed_domains=confirmed,
        processed_domains=processed,
    )
    save_checkpoint(state)
    return state


def _preflight_candidates_from_lw(state: dict) -> list[dict]:
    out: list[dict] = []
    for c in state.get("candidates") or []:
        if c.get("lightweight_outcome") != "PREFLIGHT_CANDIDATE":
            continue
        ok, reason = assess_from_lightweight_record(c)
        if not ok:
            c["business_surface_rejected"] = reason
            continue
        out.append(c)
    return out


async def run_preflight_batch(candidates: list[dict], cp: dict, *, batch_size: int) -> list[dict]:
    results: dict[str, dict] = cp.get("preflight_results") or {}
    pending = [c for c in candidates if c.get("domain") not in results]
    batch = pending[:batch_size]
    total = len(candidates)
    for i, rec in enumerate(batch, 1):
        dom = rec.get("domain", "")
        idx = len(results) + 1
        before = get_real_submission_count()
        row = await fp_mod.preflight_one(rec, idx, total)
        if get_real_submission_count() > before:
            raise RuntimeError(f"SAFETY: submission during preflight {dom}")
        results[dom] = row
        cp["preflight_results"] = results
        _save_cp(cp)
    return list(results.values())


def _purpose_audit_from_result(result: dict) -> str:
    fn = result.get("fill_no_submit") or {}
    sem = result.get("semantic_evidence_v2") or {}
    snap = sem.get("canonical_snapshot") or {}
    for choice in snap.get("choices_applied") or []:
        label = choice.get("label") or choice.get("value") or ""
        verdict = audit_selected_purpose(label, context=choice.get("context") or "", category=choice.get("category") or "")
        if verdict == "INCOMPATIBLE":
            return "INCOMPATIBLE"
        if verdict == "AMBIGUOUS":
            return "AMBIGUOUS"
    if result.get("refresh_outcome") == refresh_mod.FORM_NOT_SUITABLE_STATE:
        return "INCOMPATIBLE"
    return "COMPATIBLE"


def _refresh_eligible_preflight_rows(rows: list[dict]) -> list[dict]:
    from preflight_classifier import AUTO_READY, FORM_NOT_SUITABLE, MANUAL_INTERVENTION_REQUIRED, NOT_READY
    from shared_form_prepare import RUNTIME_DIVERGENCE

    eligible: list[dict] = []
    for r in rows:
        cls = r.get("preflight_classification", "")
        outcome = r.get("preflight_outcome", "")
        if cls in (FORM_NOT_SUITABLE, MANUAL_INTERVENTION_REQUIRED):
            continue
        if outcome in ("CAPTCHA_MANUAL", "RUNTIME_DIVERGENCE", "FORM_NOT_SUITABLE", "UNKNOWN", "INTERNAL_ERROR"):
            continue
        if r.get("skip_reason") == RUNTIME_DIVERGENCE:
            continue
        fn = r.get("fill_no_submit") or {}
        if fn.get("captcha_detected"):
            continue
        eligible.append(r)
    return eligible


async def run_refresh_batch(preflight_rows: list[dict], cp: dict, *, batch_size: int) -> list[dict]:
    preflight_rows = _refresh_eligible_preflight_rows(preflight_rows)
    results: dict[str, dict] = cp.get("refresh_results") or {}
    pending = [r for r in preflight_rows if r.get("domain") not in results]
    batch = pending[:batch_size]
    total = len(preflight_rows)
    for row in batch:
        dom = row.get("domain", "")
        idx = len(results) + 1
        before = get_real_submission_count()
        result = await refresh_mod._refresh_one(row, idx, total)
        if get_real_submission_count() > before:
            raise RuntimeError(f"SAFETY: submission during refresh {dom}")
        result["purpose_audit"] = _purpose_audit_from_result(result)
        result["r2_supply"] = True
        results[dom] = result
        cp["refresh_results"] = results
        _save_cp(cp)
    return list(results.values())


def build_r2_queue(
    pool_candidates: list[dict],
    preflight_by: dict[str, dict],
    refresh_results: list[dict],
) -> dict[str, Any]:
    get_sent_domain_index.cache_clear()
    idx = get_sent_domain_index()
    refresh_by = {r["domain"]: r for r in refresh_results}
    library = load_pattern_library()
    source_by = {c["domain"]: c for c in pool_candidates}

    production_ready: list[dict] = []
    rejected: list[dict] = []

    for dom, src in source_by.items():
        pf = preflight_by.get(dom, {})
        rr = refresh_by.get(dom)
        merged = {**pf, **src}
        eligible, reason, detail = assess_production_queue_eligibility(
            merged, refresh_row=rr, sent_index=idx, library=library,
        )
        if not eligible:
            rejected.append({"domain": dom, "reason": reason, "detail": detail, "bucket": src.get("r2_industry_bucket")})
            continue
        if rr and rr.get("purpose_audit") not in ("COMPATIBLE", "NOT_APPLICABLE"):
            rejected.append({"domain": dom, "reason": f"purpose_{rr.get('purpose_audit')}", "bucket": src.get("r2_industry_bucket")})
            continue
        auth = build_queue_authorization(
            {
                "queue_revision": QUEUE_REVISION,
                "candidate_id": src.get("candidate_id"),
                "domain": dom,
                "production_eligibility": "production_ready",
                "semantic_hash": (rr.get("semantic_evidence_v2") or {}).get("semantic_hash") if rr else None,
            },
            rr or {},
        )
        snap = (rr.get("semantic_evidence_v2") or {}).get("canonical_snapshot") or {}
        purpose_label = ""
        for ch in snap.get("choices_applied") or []:
            if ch.get("category") in ("INQUIRY_CATEGORY", "UNKNOWN", None):
                purpose_label = ch.get("label") or ch.get("value") or ""
                break
        production_ready.append({
            "queue_index": len(production_ready) + 1,
            "queue_date": QUEUE_DATE,
            "queue_revision": QUEUE_REVISION,
            "candidate_id": src.get("candidate_id"),
            "company_name": src.get("company_name") or pf.get("company_name", ""),
            "domain": dom,
            "website_url": src.get("website_url") or pf.get("website_url", ""),
            "form_url": pf.get("form_url") or src.get("form_url", ""),
            "industry_name": src.get("industry_name") or pf.get("industry_name", ""),
            "area_name": src.get("area_name") or pf.get("area_name", ""),
            "place_id": src.get("place_id") or pf.get("place_id", ""),
            "r2_industry_bucket": src.get("r2_industry_bucket"),
            "classification": "PROVEN_FAST_PATH",
            "matched_pattern_id": detail.get("matched_pattern_id"),
            "pattern_tier": detail.get("pattern_tier"),
            "refresh_outcome": rr.get("refresh_outcome") if rr else None,
            "semantic_hash": auth.get("authorized_semantic_hash"),
            "production_eligibility": "production_ready",
            "queue_authorization": auth,
            "inquiry_purpose_audit": rr.get("purpose_audit") if rr else "",
            "selected_inquiry_purpose": purpose_label,
            "canonical_submit_target": snap.get("submit_target"),
        })

    dup = len(production_ready) != len({c["domain"] for c in production_ready})
    confirmed_contam = [c for c in production_ready if idx.is_confirmed_sent_domain(c["domain"])]

    payload = {
        "generated_at": datetime.now().isoformat(),
        "queue_date": QUEUE_DATE,
        "queue_revision": QUEUE_REVISION,
        "immutable": True,
        "source_pool": str(POOL_JSON),
        "refresh_artifact": str(REFRESH_JSON),
        "target_attempts": 300,
        "pool_size": len(production_ready),
        "proven_fast_path_count": len(production_ready),
        "selection_policy": "R2_DENTAL_ESTHETIC_REFRESH_READY_AND_CURRENT_POLICY",
        "rejected_count": len(rejected),
        "contamination": {
            "duplicate_domains": dup,
            "attempted_contamination": 0,
            "confirmed_sent_contamination": len(confirmed_contam),
        },
        "candidates": production_ready,
        "rejected": rejected,
    }
    R2_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    R2_QUEUE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def init_r2_terminal_state() -> None:
    effective = count_official_confirmed_sent()
    write_daily_state({
        **init_daily_state(
            date=QUEUE_DATE,
            target_attempts=300,
            queue_path=R2_QUEUE,
            effective_confirmed_baseline=effective,
        ),
        "queue_revision": QUEUE_REVISION,
        "status": "idle",
        "started_at": None,
    }, revision=QUEUE_REVISION)


def compile_stats(pool: dict, lw_state: dict, cp: dict, queue: dict | None) -> dict:
    lw_candidates = lw_state.get("candidates") or []
    lw_outcomes = Counter(c.get("lightweight_outcome") for c in lw_candidates if c.get("status") == "completed")
    pf_results = cp.get("preflight_results") or {}
    rf_results = cp.get("refresh_results") or {}
    rf_outcomes = Counter(r.get("refresh_outcome") for r in rf_results.values())
    purpose = Counter(r.get("purpose_audit") for r in rf_results.values() if r.get("purpose_audit"))

    ready_dental = ready_esthetic = 0
    if queue:
        for c in queue.get("candidates") or []:
            if c.get("r2_industry_bucket") == "dental":
                ready_dental += 1
            elif c.get("r2_industry_bucket") == "esthetic":
                ready_esthetic += 1

    raw_dental = sum(1 for c in pool.get("candidates") or [] if c.get("r2_industry_bucket") == "dental")
    raw_esthetic = sum(1 for c in pool.get("candidates") or [] if c.get("r2_industry_bucket") == "esthetic")
    lw_done = sum(1 for c in lw_candidates if c.get("status") == "completed")

    total_ready = ready_dental + ready_esthetic
    est_attempts = int(total_ready * R2_YIELD_ATTEMPT)

    return {
        "source": {
            "dental_available": raw_dental,
            "esthetic_available": raw_esthetic,
            "processed_local": len(pool.get("candidates") or []),
        },
        "pipeline": {
            "lightweight_processed": lw_done,
            "lightweight_outcomes": dict(lw_outcomes),
            "contact_form_preflight_candidates": lw_outcomes.get("PREFLIGHT_CANDIDATE", 0),
            "preflight_processed": len(pf_results),
            "refresh_processed": len(rf_results),
            "refresh_ready": rf_outcomes.get(refresh_mod.REFRESH_READY, 0),
            "excluded_by_purpose": sum(1 for r in rf_results.values() if r.get("purpose_audit") == "INCOMPATIBLE"),
            "purpose_breakdown": dict(purpose),
        },
        "r2": {
            "dental_ready": ready_dental,
            "esthetic_ready": ready_esthetic,
            "total_ready": total_ready,
            "expected_attempts": est_attempts,
            "estimated_total_attempts_today": 35 + est_attempts,
            "queue_path": str(R2_QUEUE) if queue else None,
        },
        "safety": {
            "real_sends": get_real_submission_count(),
            "final_submit": 0,
            "effective_confirmed_sent": count_official_confirmed_sent(),
        },
    }


async def run_pipeline(
    *,
    resume: bool,
    reprioritize: bool,
    lw_batch: int,
    pf_batch: int,
    rf_batch: int,
    max_cycles: int,
) -> dict:
    _ensure_safety()
    cp = _load_cp() if resume else {}
    pool = build_r2_local_pool() if reprioritize or not (resume and cp.get("pool")) else cp.get("pool") or build_r2_local_pool()
    cp["pool"] = pool

    if reprioritize:
        lw_meta = reprioritize_lightweight_checkpoint(pool)
        cp["reprioritized_at"] = lw_meta.get("reprioritized_at")
        cp["preserved_lw_completed"] = lw_meta.get("preserved_completed")
        _save_cp(cp)

    cycles = 0
    queue_payload: dict | None = None

    while cycles < max_cycles:
        cycles += 1
        streaming = __import__("ari_pipeline.r2_streaming_queue", fromlist=["load_streaming_state"]).load_streaming_state()
        ready_count = streaming.get("lane_a_ready_total", 0) + streaming.get("lane_b_ready_total", 0)
        if ready_count >= TARGET_READY:
            break

        # Lightweight
        lw_pending = sum(
            1 for c in (load_checkpoint(LW_RUN_ID) or {}).get("candidates") or []
            if c.get("stage") == Stage.LIGHTWEIGHT_DETECT.value and c.get("status") != "completed"
        ) if load_checkpoint(LW_RUN_ID) else len(pool.get("candidates") or [])

        if lw_pending > 0:
            lw_state = await run_lightweight_batch(pool, batch_size=lw_batch)
        else:
            lw_state = load_checkpoint(LW_RUN_ID) or {}

        pf_candidates = _preflight_candidates_from_lw(lw_state)
        pf_results_map = cp.get("preflight_results") or {}
        pf_pending = [c for c in pf_candidates if c.get("domain") not in pf_results_map]

        if pf_pending and len(pf_results_map) < len(pf_candidates):
            await run_preflight_batch(pf_candidates, cp, batch_size=pf_batch)
            PREFLIGHT_JSON.write_text(
                json.dumps({"results": list(cp["preflight_results"].values())}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        pf_rows = list((cp.get("preflight_results") or {}).values())
        rf_map = cp.get("refresh_results") or {}
        rf_pending = [r for r in pf_rows if r.get("domain") not in rf_map]

        if rf_pending:
            await run_refresh_batch(pf_rows, cp, batch_size=rf_batch)
            REFRESH_JSON.write_text(
                json.dumps({"results": list(cp["refresh_results"].values())}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        queue_payload = build_r2_queue(
            pool.get("candidates") or [],
            cp.get("preflight_results") or {},
            list((cp.get("refresh_results") or {}).values()),
        )
        cp["queue_ready_count"] = len(queue_payload.get("candidates") or [])
        _save_cp(cp)

        # Streaming micro-batch seal (R2-A, R2-B, …) — do not wait for 400
        try:
            from ari_pipeline.r2_streaming_queue import load_streaming_state, save_streaming_state
            st = load_streaming_state()
            maybe_record_yield_checkpoint(st, lw_state, cp)
            save_streaming_state(st)
            try_seal_next_batch(deadline_mode=False)
        except RuntimeError as seal_err:
            cp.setdefault("seal_errors", []).append(str(seal_err))
            _save_cp(cp)

        streaming = __import__("ari_pipeline.r2_streaming_queue", fromlist=["load_streaming_state"]).load_streaming_state()
        sealed_total = streaming.get("lane_a_ready_total", 0) + streaming.get("lane_b_ready_total", 0)
        if sealed_total >= TARGET_READY:
            break
        if lw_pending == 0 and not pf_pending and not rf_pending:
            break

    lw_state = load_checkpoint(LW_RUN_ID) or {}
    stats = compile_stats(pool, lw_state, cp, queue_payload)
    from ari_pipeline.r2_streaming_queue import load_streaming_state
    st = load_streaming_state()
    sealed_total = st.get("lane_a_ready_total", 0) + st.get("lane_b_ready_total", 0)
    gate = "READY_TO_RUN_R2" if sealed_total >= TARGET_READY else "STREAMING_SUPPLY_ACTIVE"

    if sealed_total >= TARGET_READY:
        init_r2_terminal_state()

    report = {
        "timestamp": datetime.now().isoformat(),
        "mode": "R2_DENTAL_ESTHETIC_SUPPLY",
        "gate": gate,
        "stats": stats,
        "cycles": cycles,
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reprioritize", action="store_true", help="Rebuild pool URL priority order and reorder LW checkpoint")
    parser.add_argument("--lw-batch", type=int, default=80)
    parser.add_argument("--pf-batch", type=int, default=40)
    parser.add_argument("--rf-batch", type=int, default=40)
    parser.add_argument("--max-cycles", type=int, default=200)
    args = parser.parse_args()

    clear_field_cache()
    report = asyncio.run(run_pipeline(
        resume=args.resume,
        reprioritize=args.reprioritize,
        lw_batch=args.lw_batch,
        pf_batch=args.pf_batch,
        rf_batch=args.rf_batch,
        max_cycles=args.max_cycles,
    ))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
