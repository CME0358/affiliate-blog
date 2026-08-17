"""
ari_pipeline/orchestrator.py — Candidate processing pipeline with checkpoints.

Stages:
  LOCAL_FILTER → LIGHTWEIGHT_DETECT → PREFLIGHT_CANDIDATE → FULL_PREFLIGHT
  → AUTO_READY_LOCK → PRODUCTION_ELIGIBLE

Tonight: stops before PRODUCTION (production_limit=0). No web, no FINAL_SUBMIT.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from config import LOG_DIR, VAULT_ROOT
from ari_pipeline.limits import load_limits

CHECKPOINT_DIR = LOG_DIR / "ari_checkpoints"
OUTPUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"


class Stage(str, Enum):
    LOCAL_FILTER = "LOCAL_FILTER"
    LIGHTWEIGHT_DETECT = "LIGHTWEIGHT_DETECT"
    PREFLIGHT_CANDIDATE = "PREFLIGHT_CANDIDATE"
    FULL_PREFLIGHT = "FULL_PREFLIGHT"
    AUTO_READY_LOCK = "AUTO_READY_LOCK"
    PRODUCTION_ELIGIBLE = "PRODUCTION_ELIGIBLE"


STAGE_ORDER = list(Stage)


def _checkpoint_path(run_id: str) -> Path:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return CHECKPOINT_DIR / f"orchestrator_{run_id}.json"


def load_checkpoint(run_id: str) -> dict | None:
    p = _checkpoint_path(run_id)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_checkpoint(state: dict) -> Path:
    run_id = state.get("run_id", "default")
    p = _checkpoint_path(run_id)
    state["updated_at"] = datetime.now().isoformat()
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def init_orchestrator_from_pool(pool: dict, run_id: str | None = None) -> dict:
    run_id = run_id or f"run_{pool.get('pool_date', 'unknown')}"
    existing = load_checkpoint(run_id)
    if existing and existing.get("pool_date") == pool.get("pool_date"):
        return existing

    candidates = []
    for c in pool.get("candidates") or []:
        candidates.append({
            **c,
            "stage": Stage.LOCAL_FILTER.value,
            "status": "pending",
            "reason": "",
            "form_url": c.get("form_url", ""),
            "form_type": "",
            "captcha": False,
            "message_variant": "",
            "mapping_hash": "",
            "effective_status": "not_sent",
            "last_checked_at": "",
        })

    state = {
        "run_id": run_id,
        "pool_date": pool.get("pool_date"),
        "started_at": datetime.now().isoformat(),
        "current_stage": Stage.LOCAL_FILTER.value,
        "limits": load_limits(pool.get("pool_date")).to_dict(),
        "candidates": candidates,
        "stats": {"processed": 0, "by_stage": {}},
        "dry_run": True,
    }
    save_checkpoint(state)
    return state


def _advance_stage(stage: Stage) -> Stage | None:
    idx = STAGE_ORDER.index(stage)
    if idx + 1 >= len(STAGE_ORDER):
        return None
    return STAGE_ORDER[idx + 1]


def dry_run_stage(
    state: dict,
    stage: Stage,
    *,
    max_items: int | None = None,
) -> dict:
    """
    Dry-run: advance candidates through stage without web or submit.
    Simulates pass/fail based on existing metadata only.
    """
    limits = state.get("limits") or {}
    cap = max_items
    if stage == Stage.LIGHTWEIGHT_DETECT:
        cap = cap or limits.get("lightweight_limit", 500)
    elif stage == Stage.FULL_PREFLIGHT:
        cap = cap or limits.get("full_preflight_limit", 100)
    elif stage == Stage.AUTO_READY_LOCK:
        cap = cap or limits.get("auto_ready_limit", 50)
    elif stage == Stage.PRODUCTION_ELIGIBLE:
        cap = cap or limits.get("production_limit", 0)
        if cap == 0:
            for c in state.get("candidates") or []:
                if c.get("stage") == Stage.AUTO_READY_LOCK.value and c.get("status") == "completed":
                    c["reason"] = "production_limit_zero_stop"
            state["current_stage"] = Stage.AUTO_READY_LOCK.value
            state["production_blocked"] = True
            save_checkpoint(state)
            return state

    processed = 0
    ts = datetime.now().isoformat()
    for c in state.get("candidates") or []:
        if processed >= (cap or 999999):
            break
        if c.get("stage") != stage.value:
            continue
        if c.get("status") == "completed":
            continue

        c["last_checked_at"] = ts
        c["status"] = "completed"
        c["reason"] = f"dry_pass_{stage.value.lower()}"
        nxt = _advance_stage(stage)
        if nxt:
            c["stage"] = nxt.value
        processed += 1

    state["current_stage"] = stage.value
    state["stats"]["processed"] = sum(
        1 for c in state.get("candidates") or [] if c.get("status") == "completed"
    )
    state["stats"]["by_stage"] = {}
    for s in STAGE_ORDER:
        state["stats"]["by_stage"][s.value] = sum(
            1 for c in state.get("candidates") or [] if c.get("stage") == s.value
        )
    save_checkpoint(state)
    return state


def run_dry_pipeline(pool_path: Path, run_id: str | None = None) -> dict:
    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    state = init_orchestrator_from_pool(pool, run_id=run_id)

    for stage in STAGE_ORDER:
        if stage == Stage.PRODUCTION_ELIGIBLE:
            state = dry_run_stage(state, stage)
            break
        state = dry_run_stage(state, stage)

    out = OUTPUT_DIR / f"ari_orchestrator_dry_{state.get('pool_date', 'unknown')}.json"
    out.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def init_lightweight_run_from_pool(pool: dict, run_id: str) -> dict:
    """Initialize or resume a real lightweight-detect run (separate from dry_run checkpoints)."""
    existing = load_checkpoint(run_id)
    if existing and existing.get("pool_date") == pool.get("pool_date") and not existing.get("dry_run"):
        return existing

    candidates = []
    for c in pool.get("candidates") or []:
        candidates.append({
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
        "run_id": run_id,
        "pool_date": pool.get("pool_date"),
        "started_at": datetime.now().isoformat(),
        "current_stage": Stage.LIGHTWEIGHT_DETECT.value,
        "limits": load_limits(pool.get("pool_date")).to_dict(),
        "candidates": candidates,
        "stats": {"processed": 0, "by_outcome": {}, "runtime_errors": 0},
        "dry_run": False,
        "production_blocked": True,
    }
    save_checkpoint(state)
    return state


def map_lightweight_outcome(classification: str, reason: str, det: dict[str, Any]) -> str:
    """Map classifier output to funnel reporting bucket."""
    from lightweight_form_classifier import (
        LIKELY_NOT_READY,
        LW_FORM_NOT_SUITABLE,
        LW_MANUAL_INTERVENTION,
        PREFLIGHT_BOUNDARY,
    )

    if classification in PREFLIGHT_BOUNDARY:
        return "PREFLIGHT_CANDIDATE"
    if classification == LW_FORM_NOT_SUITABLE:
        return "FORM_NOT_SUITABLE"
    if classification == LW_MANUAL_INTERVENTION:
        return "CAPTCHA_MANUAL"
    if classification == LIKELY_NOT_READY:
        form_type = (det.get("form_type") or "").upper()
        failure = (det.get("failure_reason") or reason or "").lower()
        if form_type in ("NO_FORM", "BLOCKED") or "no_form" in failure:
            return "NO_FORM_FOUND"
        if form_type == "ERROR" or any(k in failure for k in ("timeout", "unreachable", "load", "playwright")):
            return "UNREACHABLE_ERROR"
        return "OTHER_SKIPPED"
    return "INTERNAL_ERROR"


def _recompute_lightweight_stats(state: dict) -> None:
    from collections import Counter

    candidates = state.get("candidates") or []
    completed = [c for c in candidates if c.get("status") == "completed"]
    outcomes = Counter(c.get("lightweight_outcome") or "UNKNOWN" for c in completed)
    state["stats"]["processed"] = len(completed)
    state["stats"]["by_outcome"] = dict(outcomes)
    state["stats"]["by_stage"] = {
        s.value: sum(1 for c in candidates if c.get("stage") == s.value)
        for s in STAGE_ORDER
    }
    state["stats"]["runtime_errors"] = sum(
        1 for c in completed if c.get("lightweight_outcome") == "INTERNAL_ERROR"
    )


async def run_lightweight_detect_stage(
    state: dict,
    *,
    max_items: int | None = None,
    confirmed_domains: set[str] | None = None,
    processed_domains: set[str] | None = None,
) -> dict:
    """
    Real lightweight detect: detect_form_only + classify_lightweight (no fill/submit).
    Stops after LIGHTWEIGHT_DETECT; advances PREFLIGHT_CANDIDATE outcomes only.
    """
    from form_detector import detect_form_only
    from form_sender import get_real_submission_count, set_submit_forbidden
    from lightweight_form_classifier import classify_lightweight, score_lightweight

    set_submit_forbidden(True)
    limits = state.get("limits") or {}
    cap = max_items if max_items is not None else limits.get("lightweight_limit", 500)
    confirmed = confirmed_domains or set()
    seen_domains = set(processed_domains or set())
    newly_processed = 0
    ts_base = datetime.now()

    for c in state.get("candidates") or []:
        if newly_processed >= cap:
            break
        if c.get("stage") != Stage.LIGHTWEIGHT_DETECT.value:
            continue
        if c.get("status") == "completed":
            dom_done = (c.get("domain") or "").lower()
            if dom_done:
                seen_domains.add(dom_done)
            continue

        dom = (c.get("domain") or "").lower()
        ts = datetime.now().isoformat()
        c["last_checked_at"] = ts

        if dom and dom in confirmed:
            c["status"] = "completed"
            c["lightweight_outcome"] = "ALREADY_CONFIRMED_SENT_EXCLUDED"
            c["reason"] = "confirmed_sent_excluded"
            c["stage"] = Stage.LIGHTWEIGHT_DETECT.value
            newly_processed += 1
            save_checkpoint(state)
            continue

        if dom and dom in seen_domains:
            c["status"] = "completed"
            c["lightweight_outcome"] = "DUPLICATE_EXCLUDED"
            c["reason"] = "duplicate_domain_excluded"
            c["stage"] = Stage.LIGHTWEIGHT_DETECT.value
            newly_processed += 1
            save_checkpoint(state)
            continue

        if dom:
            seen_domains.add(dom)

        submissions_before = get_real_submission_count()
        try:
            det = await detect_form_only(c)
            classification, reason, _ = classify_lightweight(det)
            score = score_lightweight(det, classification, c)
            outcome = map_lightweight_outcome(classification, reason, det)

            c["detection"] = {
                k: det.get(k)
                for k in (
                    "form_url", "form_type", "confidence", "captcha", "failure_reason",
                    "field_map", "submit_label", "external_provider", "contact_page_url",
                )
            }
            c["form_url"] = det.get("form_url") or ""
            c["form_type"] = det.get("form_type") or ""
            c["captcha"] = bool(det.get("captcha"))
            c["lightweight_classification"] = classification
            c["lightweight_score"] = score
            c["lightweight_reason"] = reason
            c["lightweight_outcome"] = outcome
            c["reason"] = reason or outcome
            c["status"] = "completed"

            if outcome == "PREFLIGHT_CANDIDATE":
                c["stage"] = Stage.PREFLIGHT_CANDIDATE.value
            else:
                c["stage"] = Stage.LIGHTWEIGHT_DETECT.value

            if get_real_submission_count() > submissions_before:
                c["lightweight_outcome"] = "SAFETY_VIOLATION"
                c["reason"] = "unexpected_real_submission"
                state.setdefault("safety_violations", []).append({
                    "candidate_id": c.get("candidate_id"),
                    "domain": dom,
                    "at": ts,
                })
        except Exception as e:
            c["status"] = "completed"
            c["lightweight_outcome"] = "INTERNAL_ERROR"
            c["lightweight_reason"] = str(e)[:200]
            c["reason"] = str(e)[:200]
            c["stage"] = Stage.LIGHTWEIGHT_DETECT.value

        newly_processed += 1
        _recompute_lightweight_stats(state)
        save_checkpoint(state)

        elapsed = (datetime.now() - ts_base).total_seconds()
        done = state["stats"]["processed"]
        total = len(state.get("candidates") or [])
        print(f"[lw {done}/{total}] {c.get('company_name', '')[:40]} → {c.get('lightweight_outcome')} ({elapsed:.0f}s elapsed)")

    state["current_stage"] = Stage.LIGHTWEIGHT_DETECT.value
    _recompute_lightweight_stats(state)
    save_checkpoint(state)
    return state
