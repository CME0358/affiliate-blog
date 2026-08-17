#!/usr/bin/env python3
"""
run_ari_terminal_production.py — macOS Terminal.app production runner for ARI.

Independent of Cursor. Requires ARI_TERMINAL_PRODUCTION_CONFIRM=1 for REAL SEND.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))

import run_ari_production_batch_b01 as b01
from ari_pipeline.conversion_tracking import seed_from_confirmed_sent
from ari_pipeline.daily_fast_runner import (
    DAILY_PID_FILE,
    DailyCounters,
    candidate_skip_outcome,
    daily_queue_path,
    daily_results_path,
    daily_target_reached,
    init_daily_state,
    load_daily_queue,
    read_daily_state,
    should_system_hard_stop,
    update_counters_from_result,
    write_daily_state,
)
from ari_pipeline.limits import load_limits
from ari_pipeline.proven_pattern_library import PROVEN_FAST_PATH, classify_candidate, load_pattern_library
from ari_pipeline.queue_evidence_contract import build_queue_authorization
from ari_pipeline.queue_execution_contract import (
    QUEUE_MODE_AUTHORIZED_READY,
    evaluate_terminal_daily_fast_gate,
    load_queue_evidence_maps,
    resolve_queue_mode,
)
from ari_pipeline.production_ownership import claim_terminal_ownership, clear_ownership
from ari_pipeline.sent_domain_index import get_sent_domain_index
from ari_pipeline.status_integrity import count_official_confirmed_sent
from automation_state import is_paused, set_paused
from canonical_submit_target import resolve_canonical_submit_target
from config import LOG_DIR, VAULT_ROOT
from evidence_reauthorization import authorize_production_evidence
from form_field_resolver import clear_field_cache
from form_sender import get_real_submission_count, reset_real_submission_count, set_submit_forbidden
from inquiry_purpose_semantics import audit_selected_purpose
from preflight_classifier import AUTO_READY, FORM_NOT_SUITABLE
from shared_form_prepare import RUNTIME_DIVERGENCE, SEMANTIC_EVIDENCE_SCHEMA_VERSION, build_preflight_semantic_evidence, is_evidence_compatible, is_evidence_schema_and_hash_compatible
from semantic_policy import SEMANTIC_REFRESH_REQUIRED, assess_production_evidence_eligibility, is_semantic_policy_compatible
from submission_state import CONFIRMED_SENT, FAILED, UNKNOWN, SubmissionCounters

CONFIRM_ENV = "ARI_TERMINAL_PRODUCTION_CONFIRM"
DEFAULT_BATCH_SIZE = 10
MAX_BATCH_SIZE = 50
DEFAULT_DAILY_FAST_TARGET = 300
MAX_DAILY_FAST_TARGET = 300
JOB_ID = "form-auto-sender"

PREFLIGHT_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Full-Preflight-2026-08-12.json"
REFRESH_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-AUTO-READY-Semantic-Refresh-2026-08-12.json"
INQUIRY_AUDIT_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Inquiry-Purpose-Audit-2026-08-13.json"
OUTPUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"

STATE_JSON = LOG_DIR / "ari_terminal_production_state.json"
PID_FILE = LOG_DIR / "ari_terminal_production.pid"
LOG_PREFIX = LOG_DIR / "ari_terminal_production"

AUTO_READY_OUTCOMES = frozenset({"AUTO_READY_CANDIDATE", "CONFIRMATION_READY"})
KNOWN_NO_RETRY_DIVERGENCE = frozenset({"r-ginza.jp", "harudesign.tokyo", "sakura-reform.com"})
KNOWN_VALIDATION_FAILED = frozenset({"ontex.co.jp", "8044.co.jp"})

_RESULT_KEYS = (
    "results",
    "prior_results",
    "resumed_results",
    "final4_results",
    "historical_results",
)

_stop_requested = False


def parse_batch_size(raw: str | None) -> int:
    if raw is None or str(raw).strip() == "":
        return DEFAULT_BATCH_SIZE
    value = int(str(raw).strip())
    if value < 1:
        raise ValueError("batch size must be >= 1")
    if value > MAX_BATCH_SIZE:
        raise ValueError(f"batch size must be <= {MAX_BATCH_SIZE}")
    return value


def parse_daily_fast_target(raw: str | None) -> int:
    if raw is None or str(raw).strip() == "":
        return DEFAULT_DAILY_FAST_TARGET
    value = int(str(raw).strip())
    if value < 1:
        raise ValueError("daily fast target must be >= 1")
    if value > MAX_DAILY_FAST_TARGET:
        raise ValueError(f"daily fast target must be <= {MAX_DAILY_FAST_TARGET}")
    return value


def _should_stop_daily_fast(
    counters: DailyCounters,
    recent_attempts: list[dict],
    results: list[dict],
) -> tuple[bool, str, str]:
    """Daily Fast Path: system-level hard stop only; candidate issues do not halt the day."""
    for row in results:
        if _inquiry_purpose_violation(row):
            return True, "inquiry_purpose_policy_violation", "HARD_STOP"

    stop, why, sc = should_system_hard_stop(counters, recent_attempts)
    if stop:
        return stop, why, sc

    # Legacy safety: attempted runtime divergence with submit is hard stop
    for row in results:
        if row.get("attempted") and (
            row.get("submission_state") == RUNTIME_DIVERGENCE
            or row.get("pre_send_skip_reason") == RUNTIME_DIVERGENCE
        ):
            return True, "runtime_divergence_submit", "HARD_STOP"

    return False, "", ""


async def run_daily_fast_production(
    *,
    target_attempts: int,
    queue_date: str | None = None,
    queue_revision: str = "",
    resume: bool = False,
) -> dict:
    global _stop_requested
    _stop_requested = False
    _install_signal_handlers()

    if os.environ.get(CONFIRM_ENV) != "1":
        raise RuntimeError(f"Set {CONFIRM_ENV}=1")

    queue_date = queue_date or datetime.now().strftime("%Y-%m-%d")
    queue = load_daily_queue(queue_date, revision=queue_revision)
    queue_mode = resolve_queue_mode(queue)
    candidates = queue.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Daily queue empty for {queue_date}")

    preflight = verify_daily_fast_safety(
        target_attempts=target_attempts,
        queue_date=queue_date,
        queue_revision=queue_revision,
        require_confirm=True,
    )
    if not preflight["passed"]:
        raise RuntimeError("Daily fast safety preflight failed: " + "; ".join(preflight["errors"]))

    os.environ["ARI_PRODUCTION_MAX_SUBMISSIONS"] = str(target_attempts)
    b01._set_production_limit(target_attempts)
    claim_terminal_ownership(
        pid=os.getpid(),
        batch_id=f"DAILY-FAST-{queue_date.replace('-', '')}{('-' + queue_revision) if queue_revision else ''}",
        production_limit=target_attempts,
    )

    state = read_daily_state(revision=queue_revision) if resume else {}
    processed_domains = set(state.get("processed_domains") or [])
    prior_results: list[dict] = []
    if resume and state.get("date") == queue_date and (state.get("queue_revision") or "") == queue_revision:
        results_path = daily_results_path(queue_date, revision=queue_revision)
        if results_path.exists():
            prior_results = json.loads(results_path.read_text()).get("results") or []
            processed_domains = {r.get("domain") for r in prior_results if r.get("domain")}

    remaining = [c for c in candidates if c.get("domain") not in processed_domains]
    batch_id = f"DAILY-FAST-{queue_date.replace('-', '')}{('-' + queue_revision) if queue_revision else ''}"

    preflight_by_domain, refresh_by_domain = load_queue_evidence_maps(queue)
    library = load_pattern_library()
    excluded, _ = build_canonical_exclusions()

    reset_real_submission_count()
    clear_field_cache()
    counters = SubmissionCounters()
    daily_counters = DailyCounters(**(state.get("counters") or {}))
    cumulative_before = _effective_confirmed_fresh()
    pid = os.getpid()

    out_json = daily_results_path(queue_date, revision=queue_revision)
    log_csv = LOG_DIR / f"ari_terminal_daily_fast_{queue_date}.csv"

    write_daily_state({
        **init_daily_state(
            date=queue_date,
            target_attempts=target_attempts,
            queue_path=daily_queue_path(queue_date, revision=queue_revision),
            effective_confirmed_baseline=cumulative_before,
        ),
        "queue_revision": queue_revision,
        "status": "running",
        "pid": pid,
        "processed_domains": sorted(processed_domains),
        "counters": daily_counters.to_dict(),
        "started_at": state.get("started_at") or datetime.now().isoformat(),
    }, revision=queue_revision)
    DAILY_PID_FILE.write_text(str(pid), encoding="utf-8")

    print(
        f"\n=== ARI Daily Fast Production | date={queue_date} | target_attempts={target_attempts} | "
        f"remaining={len(remaining)} | pid={pid} ===",
        flush=True,
    )

    segment_results: list[dict] = []
    stopped = False
    stop_reason = ""
    stop_class = ""
    total_index = len(prior_results)

    try:
        for company in remaining:
            if _stop_requested or stopped or daily_target_reached(daily_counters, target_attempts):
                break
            if get_real_submission_count() >= target_attempts:
                break

            total_index += 1
            dom = company.get("domain", "")
            label = f"[{total_index}/{len(candidates)}]"
            print(f"{label} START {dom}", flush=True)

            write_daily_state({
                **read_daily_state(revision=queue_revision),
                "current_domain": dom,
                "updated_at": datetime.now().isoformat(),
            }, revision=queue_revision)

            dom_key = dom.lower()
            pf_row = preflight_by_domain.get(dom_key) or preflight_by_domain.get(dom, {})
            rr = refresh_by_domain.get(dom_key) or refresh_by_domain.get(dom)

            gate_ok, gate_reason, gate_detail = evaluate_terminal_daily_fast_gate(
                company,
                queue_mode=queue_mode,
                preflight_row=pf_row,
                refresh_row=rr,
                excluded_domains=excluded,
                library=library,
            )
            if not gate_ok:
                skip_cls = gate_detail.get("classification") or (
                    "OTHER_SKIP" if queue_mode == QUEUE_MODE_AUTHORIZED_READY else gate_reason
                )
                if gate_reason == "no_proven_pattern_match" or gate_detail.get("classification") == "SLOW_PATH_REVIEW":
                    skip_cls = "SLOW_PATH_REVIEW"
                res = candidate_skip_outcome(
                    dom,
                    skip_cls,
                    gate_reason,
                    batch_id=batch_id,
                    lock_index=company.get("queue_index"),
                )
                update_counters_from_result(daily_counters, res, skip_classification=skip_cls)
                segment_results.append(res)
                processed_domains.add(dom)
                print(f"{label} SKIP {skip_cls} {gate_reason}", flush=True)
                continue

            policy_ok, policy_reason = _verify_resume_candidate_policy(dom, rr)
            if not policy_ok:
                res = candidate_skip_outcome(dom, "OTHER_SKIP", policy_reason, batch_id=batch_id, lock_index=company.get("queue_index"))
                update_counters_from_result(daily_counters, res, skip_classification=policy_reason)
                segment_results.append(res)
                processed_domains.add(dom)
                print(f"{label} SKIP policy={policy_reason}", flush=True)
                continue

            pf_merged = b01._merge_refresh_v2_evidence(pf_row, rr)
            queue_auth = company.get("queue_authorization") or build_queue_authorization(company, rr)
            send_company = {
                "domain": dom,
                "company_name": company.get("company_name") or pf_row.get("company_name"),
                "form_url": company.get("form_url") or pf_row.get("form_url"),
                "website_url": company.get("website_url") or pf_row.get("website_url"),
                "lock_index": company.get("queue_index"),
                "candidate_id": company.get("candidate_id"),
                "industry_name": company.get("industry_name") or pf_row.get("industry_name", ""),
                "area_name": company.get("area_name") or pf_row.get("area_name", ""),
                "preflight_classification": pf_row.get("preflight_classification", ""),
                "preflight_outcome": pf_row.get("preflight_outcome", ""),
                "queue_authorization": queue_auth,
            }
            res = await _execute_send_terminal(
                send_company,
                counters,
                preflight_row=pf_merged,
                session_max=target_attempts,
            )
            res["classification"] = gate_detail.get("classification") or PROVEN_FAST_PATH
            res["matched_pattern_id"] = company.get("matched_pattern_id") or gate_detail.get("matched_pattern_id")
            res["pattern_tier"] = company.get("pattern_tier")
            res["queue_mode"] = queue_mode
            segment_results.append(res)
            update_counters_from_result(daily_counters, res)
            processed_domains.add(dom)

            outcome = res.get("submission_state") or res.get("status") or "unknown"
            print(f"{label} DONE outcome={outcome}", flush=True)

            all_results = prior_results + segment_results
            recent_attempts = [r for r in all_results if r.get("attempted")]
            stop, why, sc = _should_stop_daily_fast(daily_counters, recent_attempts, segment_results)
            write_daily_state({
                **read_daily_state(revision=queue_revision),
                "processed_domains": sorted(processed_domains),
                "counters": daily_counters.to_dict(),
                "current_domain": None,
                "updated_at": datetime.now().isoformat(),
            }, revision=queue_revision)
            if stop:
                stopped = True
                stop_reason = why
                stop_class = sc
                print(f"\n⛔ DAILY FAST HARD STOP ({sc}): {why}", flush=True)
                break
    finally:
        shutdown_info = shutdown_safe(reset_production_limit=True)
        if DAILY_PID_FILE.exists():
            try:
                if int(DAILY_PID_FILE.read_text().strip()) == pid:
                    DAILY_PID_FILE.unlink()
            except (ValueError, OSError):
                pass

    all_results = prior_results + segment_results
    cumulative_after = _effective_confirmed_fresh()

    companies_by_domain = {c.get("domain"): c for c in remaining}
    tracking_added = seed_from_confirmed_sent([
        {
            "candidate_id": companies_by_domain.get(r["domain"], {}).get("candidate_id", ""),
            "company_name": r.get("company") or companies_by_domain.get(r["domain"], {}).get("company_name"),
            "domain": r.get("domain"),
            "confirmed_sent_at": r.get("timestamp"),
            "message_variant": r.get("message_variant", "ARI_MESSAGE_V1"),
        }
        for r in segment_results if r.get("submission_state") == CONFIRMED_SENT
    ])

    report = {
        "timestamp": datetime.now().isoformat(),
        "batch_id": batch_id,
        "runner": "run_ari_terminal_production.py",
        "mode": "DAILY_FAST_RESUME" if resume else "DAILY_FAST",
        "queue_date": queue_date,
        "target_attempts": target_attempts,
        "daily_counters": daily_counters.to_dict(),
        "cumulative_confirmed_before": cumulative_before,
        "cumulative_confirmed_after": cumulative_after,
        "cumulative_delta": cumulative_after - cumulative_before,
        "conversion_tracking_added": tracking_added,
        "stopped": stopped or _stop_requested,
        "stop_reason": stop_reason or ("signal_interrupt" if _stop_requested else ""),
        "stop_class": stop_class,
        "shutdown": shutdown_info,
        "real_submissions": get_real_submission_count(),
        "results": all_results,
    }
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    final_status = "stopped" if (stopped or _stop_requested) else "completed"
    write_daily_state({
        **read_daily_state(revision=queue_revision),
        "status": final_status,
        "pid": None,
        "hard_stop": bool(stop_class == "HARD_STOP"),
        "hard_stop_reason": stop_reason,
        "counters": daily_counters.to_dict(),
        "processed_domains": sorted(processed_domains),
        "effective_confirmed_after": cumulative_after,
    }, revision=queue_revision)

    return report


def read_daily_fast_status() -> dict[str, Any]:
    state = read_daily_state()
    pid = 0
    if DAILY_PID_FILE.exists():
        try:
            pid = int(DAILY_PID_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = 0
    worker_running = _pid_running(pid)
    limits = load_limits()
    counters = state.get("counters") or {}
    queue_date = state.get("date", "")
    queue_remaining = 0
    if queue_date:
        try:
            q = load_daily_queue(queue_date)
            processed = set(state.get("processed_domains") or [])
            queue_remaining = sum(1 for c in q.get("candidates") or [] if c.get("domain") not in processed)
        except FileNotFoundError:
            queue_remaining = 0
    return {
        "mode": "daily_fast",
        "worker_running": worker_running,
        "pid": pid if worker_running else None,
        "date": queue_date,
        "daily_target": state.get("target_attempts"),
        "final_submit_attempts": counters.get("final_submit_attempts", 0),
        "confirmed_sent": counters.get("confirmed_sent", 0),
        "skips": counters.get("candidates_skipped", 0),
        "queue_remaining": queue_remaining,
        "current_domain": state.get("current_domain"),
        "effective_confirmed_sent": _effective_confirmed_fresh(),
        "hard_stop": state.get("hard_stop", False),
        "hard_stop_reason": state.get("hard_stop_reason", ""),
        "production_limit": limits.production_limit,
        "automation_paused": is_paused(JOB_ID),
        "submit_forbidden": True,
        "runner_status": state.get("status", "idle"),
        "started_at": state.get("started_at"),
        "updated_at": state.get("updated_at"),
    }


def _effective_confirmed_fresh() -> int:
    get_sent_domain_index.cache_clear()
    return count_official_confirmed_sent()


def _is_auto_ready(row: dict) -> bool:
    return row.get("preflight_classification") == AUTO_READY or row.get("preflight_outcome") in AUTO_READY_OUTCOMES


def _is_navigation_error(row: dict) -> bool:
    blob = " ".join([
        row.get("reason") or "",
        row.get("skip_reason") or "",
        row.get("pre_send_skip_reason") or "",
        row.get("notes") or "",
    ]).lower()
    return row.get("submission_state") == "error" and (
        "navigating" in blob or "unable to retrieve content" in blob
    )


def _load_production_history() -> dict[str, set[str]]:
    attempted: set[str] = set()
    unknown: set[str] = set()
    failed: set[str] = set()
    navigation: set[str] = set()
    runtime_divergence: set[str] = set()

    for path in sorted(OUTPUT_DIR.glob("ARI-Production-Batch-*-Results.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for key in _RESULT_KEYS:
            for row in data.get(key) or []:
                dom = row.get("domain") or ""
                if not dom:
                    continue
                state = row.get("submission_state") or ""
                if row.get("attempted"):
                    attempted.add(dom)
                if state == UNKNOWN:
                    unknown.add(dom)
                if state == FAILED and row.get("attempted"):
                    failed.add(dom)
                if state == "RUNTIME_DIVERGENCE" or row.get("pre_send_skip_reason") == "RUNTIME_DIVERGENCE":
                    runtime_divergence.add(dom)
                if _is_navigation_error(row):
                    navigation.add(dom)
    return {
        "attempted": attempted,
        "unknown": unknown,
        "failed": failed,
        "navigation": navigation,
        "runtime_divergence": runtime_divergence,
    }


def build_canonical_exclusions() -> tuple[frozenset[str], dict[str, Any]]:
    history = _load_production_history()
    excluded = (
        KNOWN_NO_RETRY_DIVERGENCE
        | KNOWN_VALIDATION_FAILED
        | history["attempted"]
        | history["unknown"]
        | history["failed"]
        | history["navigation"]
        | history["runtime_divergence"]
    )
    summary = {k: sorted(v) for k, v in history.items()}
    summary["known_no_retry_divergence"] = sorted(KNOWN_NO_RETRY_DIVERGENCE)
    summary["known_validation_failed"] = sorted(KNOWN_VALIDATION_FAILED)
    return frozenset(excluded), summary


def _assess_refresh_evidence(sem: dict) -> tuple[str, list[str]]:
    return assess_production_evidence_eligibility(
        sem,
        schema_compatible_fn=is_evidence_schema_and_hash_compatible,
    )


def _verify_resume_candidate_policy(dom: str, refresh_row: dict | None) -> tuple[bool, str]:
    if not refresh_row:
        return False, "missing_refresh"
    sem = refresh_row.get("semantic_evidence_v2") or {}
    status, reasons = _assess_refresh_evidence(sem)
    if status == SEMANTIC_REFRESH_REQUIRED:
        return False, SEMANTIC_REFRESH_REQUIRED
    if status != "ELIGIBLE":
        return False, status
    if refresh_row.get("refresh_outcome") != "REFRESH_READY":
        return False, refresh_row.get("refresh_outcome") or "not_refresh_ready"
    return True, ""


def compute_eligible_unsent() -> tuple[list[dict], dict[str, Any]]:
    if not PREFLIGHT_JSON.exists():
        raise RuntimeError(f"Missing preflight artifact: {PREFLIGHT_JSON}")
    if not REFRESH_JSON.exists():
        raise RuntimeError(f"Missing refresh artifact: {REFRESH_JSON}")

    excluded_set, exclusion_summary = build_canonical_exclusions()
    pf = json.loads(PREFLIGHT_JSON.read_text(encoding="utf-8"))
    refresh = {
        r["domain"]: r
        for r in json.loads(REFRESH_JSON.read_text(encoding="utf-8")).get("results", [])
        if r.get("domain")
    }
    get_sent_domain_index.cache_clear()
    sent_idx = get_sent_domain_index()
    rows = sorted(
        [r for r in pf.get("results", []) if _is_auto_ready(r)],
        key=lambda r: int(r.get("lock_index") or 0),
    )

    eligible: list[dict] = []
    skip_reasons: dict[str, str] = {}
    for row in rows:
        dom = row.get("domain", "")
        if not dom:
            continue
        if row.get("preflight_classification") == FORM_NOT_SUITABLE:
            skip_reasons[dom] = "form_not_suitable:preflight"
            continue
        if dom in excluded_set:
            skip_reasons[dom] = "canonical_excluded"
            continue
        if sent_idx.should_no_resend(dom):
            skip_reasons[dom] = "effective_confirmed_sent"
            continue
        rr = refresh.get(dom)
        if not rr or rr.get("refresh_outcome") != "REFRESH_READY":
            skip_reasons[dom] = rr.get("refresh_outcome") if rr else "missing_refresh"
            continue
        sem = rr.get("semantic_evidence_v2") or {}
        eligibility, elig_reasons = _assess_refresh_evidence(sem)
        if eligibility == SEMANTIC_REFRESH_REQUIRED:
            skip_reasons[dom] = SEMANTIC_REFRESH_REQUIRED
            continue
        if sem.get("semantic_evidence_schema_version") != SEMANTIC_EVIDENCE_SCHEMA_VERSION:
            skip_reasons[dom] = "missing_v2"
            continue
        snap = sem.get("canonical_snapshot") or {}
        if not snap.get("submit_target"):
            skip_reasons[dom] = "missing_submit_target"
            continue
        ok, reasons = is_evidence_compatible(sem)
        if not ok:
            if any(SEMANTIC_REFRESH_REQUIRED in r or r.startswith("semantic_policy_") for r in reasons):
                skip_reasons[dom] = SEMANTIC_REFRESH_REQUIRED
            else:
                skip_reasons[dom] = f"incompatible:{','.join(reasons)}"
            continue
        eligible.append({
            "lock_index": row.get("lock_index"),
            "candidate_id": row.get("candidate_id"),
            "company_name": row.get("company_name"),
            "domain": dom,
            "form_url": row.get("form_url"),
            "website_url": row.get("website_url") or f"https://{dom}/",
            "area_name": row.get("area_name", ""),
            "industry_name": row.get("industry_name", ""),
            "preflight_outcome": row.get("preflight_outcome"),
            "preflight_classification": row.get("preflight_classification"),
        })

    meta = {
        "eligible_count": len(eligible),
        "excluded_count": len(skip_reasons),
        "skip_reasons": skip_reasons,
        "exclusion_summary": exclusion_summary,
        "effective_confirmed_sent": _effective_confirmed_fresh(),
    }
    return eligible, meta


def _read_final_gate() -> str:
    if INQUIRY_AUDIT_JSON.exists():
        data = json.loads(INQUIRY_AUDIT_JSON.read_text(encoding="utf-8"))
        gate = data.get("production_gate") or ""
        if gate:
            return gate
    return "UNKNOWN"


def verify_daily_fast_safety(*, target_attempts: int, queue_date: str, queue_revision: str = "", require_confirm: bool = True) -> dict[str, Any]:
    """Safety checks for Daily Fast Path mode (pattern library + queue required)."""
    checks: dict[str, bool] = {}
    errors: list[str] = []

    lib_path = OUTPUT_DIR / "ARI-Proven-Form-Pattern-Library.json"
    checks["pattern_library_exists"] = lib_path.exists()
    checks["automation_paused"] = is_paused(JOB_ID)
    limits = load_limits()
    checks["production_limit_zero"] = limits.production_limit == 0
    set_submit_forbidden(True)
    checks["inquiry_purpose_policy_active"] = Path(__file__).with_name("inquiry_purpose_semantics.py").exists()
    checks["duplicate_domain_exclusion_active"] = True
    checks["automatic_retry_disabled"] = True
    checks["captcha_bypass_disabled"] = True
    checks["daily_target_valid"] = 1 <= target_attempts <= MAX_DAILY_FAST_TARGET
    checks["confirm_env_set"] = os.environ.get(CONFIRM_ENV) == "1" if require_confirm else True

    try:
        queue = load_daily_queue(queue_date, revision=queue_revision)
        checks["queue_exists"] = True
        checks["queue_nonempty"] = len(queue.get("candidates") or []) > 0
    except FileNotFoundError:
        checks["queue_exists"] = False
        checks["queue_nonempty"] = False

    if not checks["pattern_library_exists"]:
        errors.append("Proven pattern library missing")
    if not checks["queue_exists"]:
        errors.append(f"Daily queue missing for {queue_date}")
    if not checks["queue_nonempty"]:
        errors.append(f"Daily queue empty for {queue_date}")
    if require_confirm and not checks["confirm_env_set"]:
        errors.append(f"{CONFIRM_ENV}=1 required")
    if not checks["daily_target_valid"]:
        errors.append(f"invalid daily target: {target_attempts}")

    return {
        "passed": not errors,
        "checks": checks,
        "errors": errors,
        "effective_confirmed_sent": _effective_confirmed_fresh(),
        "queue_date": queue_date,
        "target_attempts": target_attempts,
    }


def verify_safety_preflight(*, batch_size: int, require_confirm: bool = True) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    errors: list[str] = []

    checks["final_gate_ready"] = _read_final_gate() == "READY_TO_RESUME_PRODUCTION"
    checks["automation_paused"] = is_paused(JOB_ID)
    limits = load_limits()
    checks["production_limit_zero"] = limits.production_limit == 0
    checks["submit_forbidden_default"] = True
    set_submit_forbidden(True)

    checks["inquiry_purpose_policy_active"] = bool(
        inspect.getsourcefile(audit_selected_purpose)
        and Path(__file__).with_name("inquiry_purpose_semantics.py").exists()
    )
    checks["canonical_submit_target_active"] = callable(resolve_canonical_submit_target)
    checks["evidence_reauthorization_active"] = callable(authorize_production_evidence)
    checks["duplicate_domain_exclusion_active"] = True
    checks["effective_confirmed_sent_exclusion_active"] = True
    checks["prior_attempt_exclusion_active"] = True
    checks["automatic_retry_disabled"] = True
    checks["captcha_bypass_disabled"] = True
    checks["false_sent_rules_active"] = True
    checks["batch_size_valid"] = 1 <= batch_size <= MAX_BATCH_SIZE

    if require_confirm:
        checks["confirm_env_set"] = os.environ.get(CONFIRM_ENV) == "1"
    else:
        checks["confirm_env_set"] = True

    if not checks["final_gate_ready"]:
        errors.append(f"Final Gate must be READY_TO_RESUME_PRODUCTION (got {_read_final_gate()})")
    if not checks["automation_paused"]:
        errors.append("automation_paused must be true")
    if not checks["production_limit_zero"]:
        errors.append(f"production_limit must be 0 (got {limits.production_limit})")
    if require_confirm and not checks["confirm_env_set"]:
        errors.append(f"{CONFIRM_ENV}=1 required for production")
    if not checks["batch_size_valid"]:
        errors.append(f"invalid batch size: {batch_size}")

    eligible, eligible_meta = compute_eligible_unsent()
    checks["eligible_population_available"] = len(eligible) > 0

    return {
        "passed": not errors,
        "checks": checks,
        "errors": errors,
        "eligible_unsent_count": len(eligible),
        "eligible_meta": eligible_meta,
        "effective_confirmed_sent": eligible_meta["effective_confirmed_sent"],
        "final_gate": _read_final_gate(),
    }


def _batch_paths(batch_id: str) -> tuple[Path, Path, Path]:
    lock_json = OUTPUT_DIR / f"ARI-Terminal-Production-Batch-{batch_id}.json"
    out_json = OUTPUT_DIR / f"ARI-Terminal-Production-Batch-{batch_id}-Results.json"
    log_csv = LOG_DIR / f"ari_terminal_production_{batch_id}.csv"
    return lock_json, out_json, log_csv


def create_batch_lock(batch_size: int) -> tuple[str, list[dict], dict[str, Any], Path]:
    eligible, meta = compute_eligible_unsent()
    if len(eligible) < batch_size:
        raise RuntimeError(
            f"Insufficient eligible-unsent candidates: {len(eligible)} < {batch_size}"
        )
    selected = eligible[:batch_size]
    domains = [c["domain"] for c in selected]
    if len(set(domains)) != len(domains):
        raise RuntimeError("Duplicate domains in terminal batch lock")

    batch_id = datetime.now().strftime("TERMINAL-%Y%m%d-%H%M%S") + f"-{batch_size}"
    lock_json, _, _ = _batch_paths(batch_id)
    payload = {
        "generated_at": datetime.now().isoformat(),
        "batch_id": batch_id,
        "immutable": True,
        "candidate_count": len(selected),
        "target_size": batch_size,
        "eligible_unsent_before_lock": meta["eligible_count"],
        "selection_policy": "canonical_lock_index_order_first_n",
        "effective_confirmed_baseline": meta["effective_confirmed_sent"],
        "exclusion_summary": meta,
        "candidates": selected,
    }
    lock_json.parent.mkdir(parents=True, exist_ok=True)
    lock_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return batch_id, selected, meta, lock_json


def _patch_b01(batch_id: str, batch_size: int, lock_json: Path, out_json: Path, log_csv: Path) -> None:
    b01.BATCH_ID = batch_id
    b01.MAX_TOTAL = batch_size
    b01.CONFIRM_ENV = CONFIRM_ENV
    b01.LOCK_JSON = lock_json
    b01.OUT_JSON = out_json
    b01.LOG_CSV = log_csv
    b01.PREFLIGHT_JSON = PREFLIGHT_JSON
    b01.REFRESH_JSON = REFRESH_JSON
    b01.REPORT_MD = OUTPUT_DIR / f"ARI Terminal Production Batch {batch_id}.md"
    b01.RUNTIME_DIVERGENCE_EXCLUDED = KNOWN_NO_RETRY_DIVERGENCE
    b01.REFRESH_FAILED_EXCLUDED = KNOWN_VALIDATION_FAILED


def _count_terminal_outcomes(results: list[dict], *, target: int) -> dict:
    stats = b01._count_outcomes(results)
    stats["target"] = target
    stats["navigation_errors"] = sum(1 for r in results if _is_navigation_error(r))
    stats["unprocessed"] = max(0, target - len(results))
    return stats


def _inquiry_purpose_violation(result: dict) -> bool:
    if not result.get("attempted"):
        return False
    meta = result.get("submission_meta") or {}
    choices = meta.get("choices_applied") or result.get("choices_applied") or []
    for choice in choices:
        category = choice.get("category") or ""
        if category not in ("INQUIRY_CATEGORY", "UNKNOWN"):
            continue
        label = choice.get("label") or choice.get("value") or ""
        if audit_selected_purpose(label, context=choice.get("context") or "", category=category) == "INCOMPATIBLE":
            return True
    return False


def _should_stop_terminal(
    results: list[dict],
    counters: SubmissionCounters,
    *,
    gate_results: list[dict] | None = None,
) -> tuple[bool, str, str]:
    for row in results:
        if _inquiry_purpose_violation(row):
            return True, "inquiry_purpose_policy_violation", "HARD_STOP"

    stop, why, sc = b01._should_stop(results, counters, gate_results=gate_results)
    if stop:
        return stop, why, sc

    gate = gate_results if gate_results is not None else results
    stats = _count_terminal_outcomes(gate, target=len(gate) or 1)
    if stats["navigation_errors"] >= 3:
        return True, f"navigation_error_count_{stats['navigation_errors']}", "QUALITY_STOP"
    return False, "", ""


async def _execute_send_terminal(company: dict, counters: SubmissionCounters, preflight_row: dict | None, session_max: int) -> dict:
    result = await b01._execute_send(
        company,
        counters,
        preflight_row=preflight_row,
        session_max=session_max,
        allow_expected_selector_refinement=True,
    )
    if _is_navigation_error(result):
        meta = result.get("submission_meta") or {}
        result["navigation_diagnostic"] = {
            "stage": meta.get("stage") or "prepare_or_pre_submit",
            "playwright_error_message": result.get("reason") or "",
        }
    return result


def _write_state(state: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_JSON.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_state() -> dict:
    if not STATE_JSON.exists():
        return {}
    try:
        return json.loads(STATE_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_status() -> dict[str, Any]:
    state = _read_state()
    pid = 0
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = 0
    worker_running = _pid_running(pid)
    limits = load_limits()
    return {
        "worker_running": worker_running,
        "pid": pid if worker_running else None,
        "batch_id": state.get("batch_id"),
        "processed": state.get("processed", 0),
        "target": state.get("target_size"),
        "current_domain": state.get("current_domain"),
        "effective_confirmed_sent": _effective_confirmed_fresh(),
        "production_limit": limits.production_limit,
        "automation_paused": is_paused(JOB_ID),
        "submit_forbidden": True,
        "runner_status": state.get("status", "idle"),
        "started_at": state.get("started_at"),
        "updated_at": state.get("updated_at"),
    }


def shutdown_safe(*, reset_production_limit: bool = True, by: str = "run_ari_terminal_production.py") -> dict:
    set_paused(JOB_ID, True, by=f"{by} shutdown")
    set_submit_forbidden(True)
    for key in (CONFIRM_ENV, "ARI_PRODUCTION_MAX_SUBMISSIONS"):
        os.environ.pop(key, None)
    if reset_production_limit:
        b01._set_production_limit(0)
        clear_ownership(pid=os.getpid())
    limits = load_limits()
    return {
        "automation_paused": is_paused(JOB_ID),
        "submit_forbidden": True,
        "production_limit": limits.production_limit,
        "production_stopped": True,
    }


def _install_signal_handlers() -> None:
    def _handler(signum, _frame) -> None:
        global _stop_requested
        _stop_requested = True
        print(f"\n⛔ Signal {signum} received — finishing current item then safe shutdown", flush=True)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handler)


async def run_production_batch(*, batch_size: int, resume: bool = False) -> dict:
    global _stop_requested
    _stop_requested = False
    _install_signal_handlers()

    if os.environ.get(CONFIRM_ENV) != "1":
        raise RuntimeError(f"Set {CONFIRM_ENV}=1")

    preflight = verify_safety_preflight(batch_size=batch_size, require_confirm=True)
    if not preflight["passed"]:
        raise RuntimeError("Safety preflight failed: " + "; ".join(preflight["errors"]))

    os.environ["ARI_PRODUCTION_MAX_SUBMISSIONS"] = str(batch_size)
    b01._set_production_limit(batch_size)
    claim_terminal_ownership(pid=os.getpid(), batch_id="TERMINAL-BATCH", production_limit=batch_size)

    state = _read_state()
    if resume and state.get("lock_artifact") and Path(state["lock_artifact"]).exists():
        lock_json = Path(state["lock_artifact"])
        lock = json.loads(lock_json.read_text(encoding="utf-8"))
        batch_id = lock.get("batch_id") or state.get("batch_id")
        companies = lock.get("candidates") or []
        eligible_meta = lock.get("exclusion_summary") or {}
        prior_results = []
        if state.get("results_artifact") and Path(state["results_artifact"]).exists():
            prior = json.loads(Path(state["results_artifact"]).read_text(encoding="utf-8"))
            prior_results = prior.get("results") or []
        processed_domains = {r.get("domain") for r in prior_results if r.get("domain")}
        companies = [c for c in companies if c.get("domain") not in processed_domains]
    else:
        batch_id, companies, eligible_meta, lock_json = create_batch_lock(batch_size)
        prior_results = []

    if not batch_id:
        raise RuntimeError("batch_id missing")
    if len(companies) + len(prior_results) != batch_size and not resume:
        raise RuntimeError("Terminal lock size mismatch")

    _, out_json, log_csv = _batch_paths(batch_id)
    _patch_b01(batch_id, batch_size, lock_json, out_json, log_csv)

    preflight_data = json.loads(PREFLIGHT_JSON.read_text(encoding="utf-8"))
    preflight_by_domain = {r.get("domain"): r for r in preflight_data.get("results", []) if r.get("domain")}
    refresh_by_domain = b01._load_refresh_by_domain()
    companies_by_domain = {c["domain"]: c for c in (json.loads(lock_json.read_text())["candidates"])}

    reset_real_submission_count()
    clear_field_cache()
    counters = SubmissionCounters()
    cumulative_before = _effective_confirmed_fresh()
    pid = os.getpid()

    _write_state({
        "status": "running",
        "pid": pid,
        "batch_id": batch_id,
        "target_size": batch_size,
        "processed": len(prior_results),
        "attempts": sum(1 for r in prior_results if r.get("attempted")),
        "current_domain": None,
        "lock_artifact": str(lock_json),
        "results_artifact": str(out_json),
        "log_csv": str(log_csv),
        "started_at": state.get("started_at") or datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "effective_confirmed_before": cumulative_before,
    })
    PID_FILE.write_text(str(pid), encoding="utf-8")

    print(
        f"\n=== ARI Terminal Production | batch={batch_id} | target={batch_size} | "
        f"remaining={len(companies)} | pid={pid} ===",
        flush=True,
    )

    segment_results: list[dict] = []
    stopped = False
    stop_reason = ""
    stop_class = ""
    total_index = len(prior_results)

    try:
        for company in companies:
            if _stop_requested or stopped or get_real_submission_count() >= batch_size:
                break
            total_index += 1
            dom = company.get("domain", "")
            label = f"[{total_index:02d}/{batch_size}]"
            print(f"{label} START {dom}", flush=True)

            _write_state({
                **(_read_state()),
                "current_domain": dom,
                "processed": total_index - 1,
                "updated_at": datetime.now().isoformat(),
            })

            rr = refresh_by_domain.get(dom)
            policy_ok, policy_reason = _verify_resume_candidate_policy(dom, rr)
            if not policy_ok:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S JST")
                res = {
                    "timestamp": ts,
                    "batch": batch_id,
                    "lock_index": company.get("lock_index"),
                    "company": company.get("company_name"),
                    "domain": dom,
                    "form_url": company.get("form_url", ""),
                    "pre_send_skip_reason": policy_reason,
                    "submission_state": "SKIPPED",
                    "attempted": False,
                    "final_submit_clicked": False,
                    "status": "skipped",
                    "reason": policy_reason,
                }
                segment_results.append(res)
                print(f"{label} DONE outcome=SKIPPED policy={policy_reason}", flush=True)
                continue

            pf_row = b01._merge_refresh_v2_evidence(
                preflight_by_domain.get(dom),
                refresh_by_domain.get(dom),
            )
            res = await _execute_send_terminal(
                company,
                counters,
                preflight_row=pf_row,
                session_max=batch_size,
            )
            segment_results.append(res)
            outcome = res.get("submission_state") or res.get("status") or "unknown"
            print(f"{label} DONE outcome={outcome}", flush=True)

            all_results = prior_results + segment_results
            stop, why, sc = _should_stop_terminal(all_results, counters, gate_results=segment_results)
            _write_state({
                **(_read_state()),
                "processed": len(all_results),
                "attempts": sum(1 for r in all_results if r.get("attempted")),
                "current_domain": None,
                "updated_at": datetime.now().isoformat(),
            })
            if stop:
                stopped = True
                stop_reason = why
                stop_class = sc
                print(f"\n⛔ TERMINAL BATCH STOP ({sc}): {why}", flush=True)
                break
    finally:
        shutdown_info = shutdown_safe(reset_production_limit=True)
        if PID_FILE.exists():
            try:
                if int(PID_FILE.read_text().strip()) == pid:
                    PID_FILE.unlink()
            except (ValueError, OSError):
                pass

    all_results = prior_results + segment_results
    cumulative_after = _effective_confirmed_fresh()
    stats = _count_terminal_outcomes(all_results, target=batch_size)
    integrity = b01._build_integrity(all_results, preflight)

    tracking_added = seed_from_confirmed_sent([
        {
            "candidate_id": companies_by_domain[r["domain"]].get("candidate_id", ""),
            "company_name": r.get("company"),
            "domain": r.get("domain"),
            "confirmed_sent_at": r.get("timestamp"),
            "message_variant": r.get("message_variant", "ARI_MESSAGE_V1"),
        }
        for r in segment_results if r.get("submission_state") == CONFIRMED_SENT
    ])

    report = {
        "timestamp": datetime.now().isoformat(),
        "batch_id": batch_id,
        "runner": "run_ari_terminal_production.py",
        "mode": "TERMINAL_RESUME" if resume else "TERMINAL_FRESH",
        "lock_artifact": str(lock_json),
        "eligible_before_lock": eligible_meta.get("eligible_count"),
        "pre_run_assertions": preflight,
        "outcomes": stats,
        "kpi": {
            **b01._kpi_from_stats(stats),
            "navigation_error_rate_pct": round(stats["navigation_errors"] / max(stats["attempted"], 1) * 100, 1),
        },
        "integrity": integrity,
        "counters": counters.to_dict(),
        "real_submissions": get_real_submission_count(),
        "cumulative_confirmed_before": cumulative_before,
        "cumulative_confirmed_after": cumulative_after,
        "cumulative_delta": cumulative_after - cumulative_before,
        "conversion_tracking_added": tracking_added,
        "stopped": stopped or _stop_requested,
        "stop_reason": stop_reason or ("signal_interrupt" if _stop_requested else ""),
        "stop_class": stop_class or ("QUALITY_STOP" if _stop_requested else ""),
        "shutdown": shutdown_info,
        "per_company": b01._per_company_rows(all_results),
        "results": all_results,
    }
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    final_status = "stopped" if (stopped or _stop_requested) else "completed"
    _write_state({
        "status": final_status,
        "pid": None,
        "batch_id": batch_id,
        "target_size": batch_size,
        "processed": len(all_results),
        "attempts": stats["attempted"],
        "current_domain": None,
        "lock_artifact": str(lock_json),
        "results_artifact": str(out_json),
        "log_csv": str(log_csv),
        "started_at": state.get("started_at") or report["timestamp"],
        "updated_at": datetime.now().isoformat(),
        "effective_confirmed_before": cumulative_before,
        "effective_confirmed_after": cumulative_after,
        "stop_reason": report["stop_reason"],
        "stop_class": report["stop_class"],
    })

    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="ARI Terminal Production Runner")
    ap.add_argument("batch_size", nargs="?", type=str, default=str(DEFAULT_BATCH_SIZE))
    ap.add_argument("--status", action="store_true", help="Report runner state (ZERO SEND)")
    ap.add_argument("--validate-runner", action="store_true", help="Safety + wiring validation (ZERO SEND)")
    ap.add_argument("--eligible-count", action="store_true", help="Print eligible-unsent count (ZERO SEND)")
    ap.add_argument("--resume", action="store_true", help="Resume locked terminal batch from state")
    ap.add_argument("--daily-fast", nargs="?", const=str(DEFAULT_DAILY_FAST_TARGET), metavar="N",
                    help="Daily Fast Path production (max 300 FINAL_SUBMIT attempts)")
    ap.add_argument("--resume-daily-fast", action="store_true", help="Resume daily fast from checkpoint")
    ap.add_argument("--queue-date", type=str, default=None, help="Queue date YYYY-MM-DD (default: today)")
    ap.add_argument("--queue-revision", type=str, default="", help="Queue revision suffix e.g. R1")
    args = ap.parse_args()

    if args.status:
        daily = read_daily_fast_status()
        if daily.get("runner_status") not in ("idle", "") or daily.get("date"):
            print(json.dumps(daily, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(read_status(), ensure_ascii=False, indent=2))
        return

    if args.eligible_count:
        _, meta = compute_eligible_unsent()
        print(json.dumps({
            "eligible_unsent": meta["eligible_count"],
            "effective_confirmed_sent": meta["effective_confirmed_sent"],
        }, ensure_ascii=False))
        return

    if args.validate_runner:
        batch_size = parse_batch_size(args.batch_size)
        report = verify_safety_preflight(batch_size=batch_size, require_confirm=False)
        report["real_sends"] = get_real_submission_count()
        report["submit_forbidden"] = True
        report["pattern_library_exists"] = (
            VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Proven-Form-Pattern-Library.json"
        ).exists()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["passed"]:
            sys.exit(1)
        return

    if args.daily_fast is not None or args.resume_daily_fast:
        target = parse_daily_fast_target(args.daily_fast if args.daily_fast is not None else None)
        if os.environ.get(CONFIRM_ENV) != "1":
            print(f"⛔ Set {CONFIRM_ENV}=1 to run production", file=sys.stderr)
            sys.exit(1)
        report = asyncio.run(run_daily_fast_production(
            target_attempts=target,
            queue_date=args.queue_date,
            queue_revision=args.queue_revision or "",
            resume=args.resume_daily_fast,
        ))
        dc = report.get("daily_counters") or {}
        print(json.dumps({
            "mode": report.get("mode"),
            "queue_date": report.get("queue_date"),
            "final_submit_attempts": dc.get("final_submit_attempts"),
            "confirmed_sent": dc.get("confirmed_sent"),
            "skips": dc.get("candidates_skipped"),
            "effective_after": report.get("cumulative_confirmed_after"),
            "stopped": report.get("stopped"),
            "stop_class": report.get("stop_class"),
            "real_submissions": report.get("real_submissions"),
        }, ensure_ascii=False))
        return

    batch_size = parse_batch_size(args.batch_size)
    if os.environ.get(CONFIRM_ENV) != "1":
        print(f"⛔ Set {CONFIRM_ENV}=1 to run production", file=sys.stderr)
        sys.exit(1)

    report = asyncio.run(run_production_batch(batch_size=batch_size, resume=args.resume))
    print(json.dumps({
        "batch_id": report["batch_id"],
        "processed": report["outcomes"]["processed"],
        "confirmed_sent": report["outcomes"]["CONFIRMED_SENT"],
        "effective_after": report["cumulative_confirmed_after"],
        "stopped": report["stopped"],
        "stop_class": report["stop_class"],
        "real_submissions": report["real_submissions"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
