#!/usr/bin/env python3
"""
run_ari_night_factory.py — Overnight READY inventory manufacturing (ZERO SEND).

REAL SENDS = 0 / FINAL_SUBMIT = 0. Night Factory never submits.
Global production_limit may be > 0 only under authorized Terminal production ownership.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))

import run_ari_auto_ready_semantic_refresh as refresh_mod
import run_ari_full_preflight as fp_mod
import run_ari_r2_supply_pipeline as r2_pipe
from ari_pipeline.business_inquiry_surface import assess_from_lightweight_record
from ari_pipeline.limits import load_limits
from ari_pipeline.night_factory import (
    CHECKPOINT_JSON,
    DEFAULT_CONFIG,
    FACTORY_DATE,
    LOG_FILE,
    PID_FILE,
    RUN_ID,
    build_morning_inventory,
    effective_source_eligible,
    evaluate_ready,
    ingest_existing_evidence,
    initialize_source_inventory,
    load_attempted_domains,
    refresh_production_exclusions,
    load_factory_checkpoint,
    load_factory_state,
    load_ready_inventory,
    recalculate_ready_inventory,
    save_factory_checkpoint,
    save_factory_state,
    save_ready_inventory,
    stop_target,
)
from ari_pipeline.high_yield_source_scoring import (
    READY_PRIORITY_A,
    READY_PRIORITY_B,
    SLOW_PATH,
    build_high_yield_signatures,
    select_priority_pool,
    tier_counts,
)
from ari_pipeline.night_factory_pipeline import (
    NightFactoryPipeline,
    serial_lw_root_cause_report,
)
from ari_pipeline.pf_rf_hardening import (
    OUTCOME_PF_DEFERRED,
    STATUS_PF_COMPLETE,
    STATUS_PF_DEFERRED,
    STATUS_PF_IN_PROGRESS,
    STATUS_READY,
    STATUS_RF_COMPLETE,
    STATUS_RF_IN_PROGRESS,
    PfDefer,
    PfFastFail,
    attach_ready_rate,
    claim_domain,
    classify_pf_priority,
    compute_rolling_throughput,
    enter_nf_pf_budget,
    increment_defer_counters,
    make_deferred_row,
    mark_status,
    partition_by_priority,
    ready_insert_atomic,
    recover_stale_in_progress,
    release_domain,
    rf_should_accept,
    rf_sort_key,
    schedule_weighted,
    should_skip_browser_pf,
    structural_blocker_reason,
)
from ari_pipeline.orchestrator import (
    init_lightweight_run_from_pool,
    load_checkpoint,
    save_checkpoint,
)
from ari_pipeline.sent_domain_index import get_sent_domain_index
from ari_pipeline.status_integrity import count_official_confirmed_sent
from automation_state import is_paused, set_paused
from config import LOG_DIR
from ari_pipeline.production_ownership import (
    classify_sent_csv_delta,
    verify_authorized_terminal_owner,
)
from form_sender import (
    get_real_submission_count,
    get_submit_forbidden,
    reset_real_submission_count,
    set_submit_forbidden,
)

JOB_ID = "form-auto-sender"
NIGHT_FACTORY_LW_RUN_ID = f"night_factory_lw_{FACTORY_DATE.replace('-', '')}"
LANE_LW_RUN_IDS = (
    "r2_lw_2026-08-13",
    "r2_lane_b_lw_2026-08-13",
    "r2_lane_c_lw_2026-08-13",
)

_STOP_REQUESTED = False
_SENT_CSV_BASELINE: int | None = None


def _log(msg: str) -> None:
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _sent_csv_lines() -> int:
    p = LOG_DIR / "sent.csv"
    if not p.exists():
        return 0
    return sum(1 for _ in open(p, encoding="utf-8", errors="replace"))


def _ensure_safety() -> None:
    """Process-local Night Factory context. Must not mutate global production_limit."""
    if not is_paused(JOB_ID):
        set_paused(JOB_ID, True, by="run_ari_night_factory.py")
    set_submit_forbidden(True)
    reset_real_submission_count()
    if os.environ.get("ARI_TERMINAL_PRODUCTION_CONFIRM"):
        _log("WARNING: ARI_TERMINAL_PRODUCTION_CONFIRM set — Night Factory ignores production confirm")
    _assert_night_factory_zero_send_codepath()


def _assert_night_factory_zero_send_codepath() -> None:
    src = Path(__file__).read_text(encoding="utf-8")
    # Tokens are split so this assertion function does not match itself.
    forbidden = (
        "send" + "_form(",
        "submit_prepared" + "_form(",
        "_execute" + "_send(",
        "_execute" + "_send_terminal(",
        "run_daily_fast" + "_production(",
        "_set_production" + "_limit(",
        "set_submit_forbidden" + "(False)",
    )
    for token in forbidden:
        if token in src:
            raise RuntimeError(f"NIGHT_FACTORY_SAFETY_VIOLATION: forbidden_token={token}")


def _hard_stop(reason: str, state: dict | None = None) -> None:
    st = state or load_factory_state()
    st["hard_stop"] = reason
    st["stopped_at"] = datetime.now().isoformat()
    save_factory_state(st)
    _log(f"HARD STOP: {reason}")
    raise RuntimeError(f"NIGHT_FACTORY_SAFETY_VIOLATION: {reason}")


def _night_factory_pid() -> int:
    return os.getpid()


def _safety_check(*, state: dict | None = None) -> None:
    global _SENT_CSV_BASELINE
    if get_real_submission_count() > 0:
        _hard_stop("REAL_SEND_DETECTED", state)
    if not get_submit_forbidden():
        _hard_stop("submit_forbidden=false in Night Factory process", state)

    limits = load_limits(FACTORY_DATE)
    owner = verify_authorized_terminal_owner(night_factory_pid=_night_factory_pid())
    if limits.production_limit != 0 and not owner.get("valid"):
        _hard_stop(
            f"production_limit={limits.production_limit} without authorized owner ({owner.get('reason')})",
            state,
        )
    if not is_paused(JOB_ID):
        _hard_stop("automation_paused=false", state)

    lines = _sent_csv_lines()
    if _SENT_CSV_BASELINE is None:
        _SENT_CSV_BASELINE = lines
    elif lines > _SENT_CSV_BASELINE:
        classified = classify_sent_csv_delta(
            baseline=_SENT_CSV_BASELINE,
            current=lines,
            owner_valid=bool(owner.get("valid")),
            production_date=FACTORY_DATE,
        )
        if classified["kind"] == "UNAUTHORIZED_MUTATION":
            _hard_stop(f"UNAUTHORIZED_MUTATION sent.csv delta ({_SENT_CSV_BASELINE} -> {lines})", state)
        _log(
            f"AUTHORIZED_EXTERNAL_SENT_DELTA sent.csv {_SENT_CSV_BASELINE} -> {lines} "
            f"| owner_valid={bool(owner.get('valid'))}"
        )
        _SENT_CSV_BASELINE = lines
        refresh_meta = refresh_production_exclusions(load_ready_inventory(), load_factory_checkpoint())
        if state is not None:
            state.setdefault("stats", {})["last_exclusion_refresh"] = refresh_meta
            state["stats"]["last_authorized_sent_delta"] = classified
            save_factory_state(state)


def _record_fatal_error(exc: BaseException, *, exit_reason: str = "fatal_error") -> None:
    state = load_factory_state()
    state["last_error"] = f"{type(exc).__name__}: {exc}"
    state["last_error_timestamp"] = datetime.now().isoformat()
    state["exit_reason"] = exit_reason
    state["stopped_at"] = datetime.now().isoformat()
    save_factory_state(state)
    cp = load_factory_checkpoint()
    cp["last_error"] = state["last_error"]
    cp["last_error_timestamp"] = state["last_error_timestamp"]
    save_factory_checkpoint(cp)
    _log(f"FATAL: {state['last_error']}")
    traceback.print_exc()


def get_process_command(pid: int) -> str:
    try:
        return subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "command="],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError, OSError):
        return ""


def is_night_factory_worker_pid(pid: int, *, exclude_pids: set[int] | None = None) -> bool:
    """
    True only for a live Python worker running run_ari_night_factory.py as main.
    Excludes shell wrapper, -c helpers, and one-shot CLI invocations.
    """
    excluded = set(exclude_pids or ())
    excluded.add(os.getpid())
    if pid in excluded or pid <= 0:
        return False

    cmd = get_process_command(pid)
    if not cmd:
        return False

    lower = cmd.lower()
    if "run_ari_night_factory.sh" in lower:
        return False
    if " -c " in cmd and "run_ari_night_factory" in cmd:
        return False
    for flag in ("--status", "--validate", "--stop", "--bootstrap-report", "--cleanup-pid"):
        if flag in cmd:
            return False
    if "run_ari_night_factory.py" not in cmd:
        return False
    # Worker must be Python executing the runner script (not merely importing the module).
    return "python" in lower or cmd.endswith("run_ari_night_factory.py")


def pid_command_matches(pid: int) -> bool:
    """Backward-compatible alias."""
    return is_night_factory_worker_pid(pid)


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_worker_pid_status(*, exclude_pids: set[int] | None = None) -> dict[str, Any]:
    """Non-mutating worker PID probe for status."""
    if not PID_FILE.exists():
        return {"worker_running": False, "pid": None, "action": "none"}
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        return {"worker_running": False, "pid": None, "action": "invalid_pid_file"}

    if not _process_alive(pid):
        return {"worker_running": False, "pid": pid, "action": "dead_pid", "stale": True}
    if is_night_factory_worker_pid(pid, exclude_pids=exclude_pids):
        return {"worker_running": True, "pid": pid, "action": "active", "command": get_process_command(pid)}
    return {
        "worker_running": False,
        "pid": pid,
        "action": "wrong_process",
        "stale": True,
        "command": get_process_command(pid),
    }


def cleanup_stale_pid(*, exclude_pids: set[int] | None = None) -> dict[str, Any]:
    """Remove PID file unless a live Night Factory Python worker owns it."""
    excluded = set(exclude_pids or ())
    excluded.add(os.getpid())

    if not PID_FILE.exists():
        return {"action": "none", "active": False, "worker_running": False}

    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        PID_FILE.unlink(missing_ok=True)
        _log("STALE_PID_REMOVED pid=invalid reason=invalid_pid_file")
        return {"action": "removed_invalid", "active": False, "worker_running": False}

    alive = _process_alive(pid)
    if alive and is_night_factory_worker_pid(pid, exclude_pids=excluded):
        return {
            "action": "active",
            "active": True,
            "worker_running": True,
            "pid": pid,
            "command": get_process_command(pid),
        }

    PID_FILE.unlink(missing_ok=True)
    reason = "wrong_process" if alive else "dead"
    _log(f"STALE_PID_REMOVED pid={pid} reason={reason} command={get_process_command(pid)!r}")
    if alive:
        return {"action": "removed_wrong_process", "active": False, "worker_running": False, "pid": pid, "reason": reason}
    return {"action": "removed_dead", "active": False, "worker_running": False, "pid": pid, "reason": reason}


def ensure_worker_start_allowed() -> dict[str, Any]:
    """Pre-flight for worker startup; auto-removes stale PID files."""
    info = cleanup_stale_pid(exclude_pids={os.getpid()})
    if info.get("active"):
        return {
            "allowed": False,
            "reason": "worker_already_running",
            "pid": info.get("pid"),
            "command": info.get("command"),
        }
    return {"allowed": True, "pid_cleanup": info}


def ensure_lw_checkpoint(source: list[dict]) -> dict:
    """Ensure Night Factory LW checkpoint exists for the current source pool."""
    lw_st = load_checkpoint(NIGHT_FACTORY_LW_RUN_ID)
    if lw_st and lw_st.get("candidates"):
        return lw_st
    return _init_lw_pool(source)


def count_pipeline_pending(
    source: list[dict],
    cp: dict,
    lw_st: dict | None,
    *,
    allow_slow: bool = False,
) -> int:
    """Source candidates not yet screened by FAST_HTTP or LW."""
    done = {
        (c.get("domain") or "").lower()
        for c in (lw_st or {}).get("candidates") or []
        if c.get("status") == "completed"
    }
    fast_done = set((cp.get("fast_http_results") or {}).keys())
    exclusions = set((cp.get("exclusions") or {}).keys())
    n = 0
    for c in source:
        dom = (c.get("domain") or "").lower()
        if not dom or dom in done or dom in fast_done or dom in exclusions:
            continue
        if not allow_slow and c.get("ready_priority_tier") == SLOW_PATH:
            continue
        n += 1
    return n


def _ab_pending(source: list[dict], cp: dict, lw_st: dict | None) -> int:
    ab = [c for c in source if c.get("ready_priority_tier") in (READY_PRIORITY_A, READY_PRIORITY_B)]
    return count_pipeline_pending(ab, cp, lw_st, allow_slow=True)


def count_lw_pending(lw_st: dict | None) -> int:
    return sum(
        1 for c in (lw_st or {}).get("candidates") or []
        if c.get("status") != "completed"
    )


def has_downstream_pending(cp: dict) -> bool:
    pf_map = cp.get("preflight_results") or {}
    for c in _collect_pf_candidates(cp):
        if c.get("domain") not in pf_map:
            return True
    pf_rows = list(pf_map.values())
    rf_map = cp.get("refresh_results") or {}
    for r in r2_pipe._refresh_eligible_preflight_rows(pf_rows):
        if r.get("domain") not in rf_map:
            return True
    return False


def is_source_exhausted(source: list[dict], cp: dict, lw_st: dict | None) -> bool:
    """True only when source was initialized AND all pipeline stages have no pending work."""
    if not cp.get("source_initialized") or len(source) == 0:
        return False
    if count_pipeline_pending(source, cp, lw_st) > 0:
        return False
    if has_downstream_pending(cp):
        return False
    return True


def _should_stop_pipeline(stop_at: int, inv: dict) -> bool:
    total = len(inv.get("ready_primary") or []) + len(inv.get("ready_remodel_reserve") or [])
    return _STOP_REQUESTED or total >= stop_at


def _write_pid() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def _clear_pid() -> None:
    _clear_pid_if_owned()


def _clear_pid_if_owned() -> None:
    if not PID_FILE.exists():
        return
    try:
        owner = int(PID_FILE.read_text(encoding="utf-8").strip())
        if owner == os.getpid():
            PID_FILE.unlink(missing_ok=True)
    except ValueError:
        PID_FILE.unlink(missing_ok=True)


def _signal_handler(signum, _frame) -> None:
    global _STOP_REQUESTED
    _STOP_REQUESTED = True
    _log(f"Signal {signum} received — graceful stop after current micro-batch")


def _init_lw_pool(source: list[dict]) -> dict:
    pool = {
        "pool_date": FACTORY_DATE,
        "candidates": [
            {**c, "website_url": c.get("lw_entry_url") or c.get("website_url", "")}
            for c in source
        ],
    }
    return init_lightweight_run_from_pool(pool, NIGHT_FACTORY_LW_RUN_ID)


def _lane_processed_domains() -> set[str]:
    done: set[str] = set()
    for run_id in LANE_LW_RUN_IDS:
        st = load_checkpoint(run_id) or {}
        for c in st.get("candidates") or []:
            if c.get("status") == "completed" and c.get("domain"):
                done.add(c.get("domain").lower())
    return done


def _collect_pf_candidates(
    cp: dict,
    *,
    pool_by_dom: dict[str, dict] | None = None,
    priority_domains: set[str] | None = None,
) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    pf_map = cp.get("preflight_results") or {}
    deferred_map = cp.get("pf_deferred") or {}

    for run_id in (NIGHT_FACTORY_LW_RUN_ID,) + LANE_LW_RUN_IDS:
        lw = load_checkpoint(run_id) or {}
        for c in lw.get("candidates") or []:
            dom = (c.get("domain") or "").lower()
            if not dom or dom in seen or dom in pf_map or dom in deferred_map:
                continue
            if c.get("lightweight_outcome") != "PREFLIGHT_CANDIDATE":
                continue
            ok, reason = assess_from_lightweight_record(c)
            if not ok:
                continue
            seen.add(dom)
            src = (pool_by_dom or {}).get(dom) or {}
            out.append({**c, **{k: src[k] for k in ("ready_yield_score", "ready_priority_tier") if k in src}})

    def _sort_key(c: dict) -> tuple:
        dom = (c.get("domain") or "").lower()
        tier = c.get("ready_priority_tier") or ""
        tier_rank = 0 if tier == READY_PRIORITY_A else (1 if tier == READY_PRIORITY_B else 2)
        in_batch = 0 if priority_domains and dom in priority_domains else 1
        return (in_batch, tier_rank, -int(c.get("ready_yield_score") or 0))

    out.sort(key=_sort_key)
    if priority_domains:
        primary = [c for c in out if (c.get("domain") or "").lower() in priority_domains]
        secondary = [c for c in out if (c.get("domain") or "").lower() not in priority_domains]
        out = primary + secondary
    return out


def _record_ready_timestamps(inv: dict, state: dict) -> None:
    ts = datetime.now().isoformat()
    samples = list(state.get("stats", {}).get("ready_timestamps") or [])
    total = len(inv.get("ready_primary") or []) + len(inv.get("ready_remodel_reserve") or [])
    samples.append({"ts": ts, "ready_total": total})
    state.setdefault("stats", {})["ready_timestamps"] = samples[-120:]


def _ready_rate(state: dict) -> tuple[int, float]:
    samples = state.get("stats", {}).get("ready_timestamps") or []
    if len(samples) < 2:
        return 0, 0.0
    now = datetime.now().timestamp()
    hour_ago = now - 3600
    window = [s for s in samples if datetime.fromisoformat(s["ts"]).timestamp() >= hour_ago]
    if len(window) < 2:
        return 0, 0.0
    delta = window[-1]["ready_total"] - window[0]["ready_total"]
    return max(0, delta), float(delta)


def _eta_remaining(remaining: int, rate_per_hour: float) -> str:
    if rate_per_hour <= 0 or remaining <= 0:
        return "unknown"
    hours = remaining / rate_per_hour
    eta = datetime.now().timestamp() + hours * 3600
    return datetime.fromtimestamp(eta).strftime("%H:%M")


async def run_pipeline_chunk(
    *,
    source: list[dict],
    pool_by_dom: dict[str, dict],
    cp: dict,
    lw_st: dict,
    inv: dict,
    state: dict,
    config: dict,
    stop_at: int,
    max_source: int | None,
) -> Any:
    """Run one FAST_HTTP → LW → PF → RF → READY streaming chunk."""
    pbd = pool_by_dom

    async def _pf_batch(cp_inner: dict, *, batch_size: int) -> int:
        return await run_pf_batch(
            cp_inner,
            batch_size=batch_size,
            pool_by_dom=pbd,
            pf_workers=int(config.get("pf_workers", 2)),
        )

    async def _rf_batch(cp_inner: dict, *, batch_size: int) -> int:
        return await run_rf_batch(
            cp_inner,
            batch_size=batch_size,
            pool_by_dom=pbd,
            rf_workers=int(config.get("rf_workers", 2)),
        )

    pipeline = NightFactoryPipeline(
        source=source,
        pool_by_dom=pool_by_dom,
        cp=cp,
        lw_run_id=NIGHT_FACTORY_LW_RUN_ID,
        config=config,
        log=_log,
        pf_batch_fn=_pf_batch,
        rf_batch_fn=_rf_batch,
        collect_ready_fn=_collect_new_ready,
        load_inv_fn=load_ready_inventory,
        save_cp_fn=save_factory_checkpoint,
        save_state_fn=save_factory_state,
        safety_check_fn=_safety_check,
        stop_check_fn=_should_stop_pipeline,
        max_source=max_source,
    )
    return await pipeline.run(lw_state=lw_st, inv=inv, state=state, stop_at=stop_at)


async def run_pf_batch(
    cp: dict,
    *,
    batch_size: int,
    pool_by_dom: dict[str, dict] | None = None,
    priority_domains: set[str] | None = None,
    pf_workers: int = 2,
) -> int:
    """Preflight using Night Factory checkpoint only (does not mutate R2 supply CP)."""
    recover_stale_in_progress(cp)
    cands = _collect_pf_candidates(cp, pool_by_dom=pool_by_dom, priority_domains=priority_domains)
    results: dict[str, dict] = cp.get("preflight_results") or {}
    deferred: dict[str, dict] = cp.setdefault("pf_deferred", {})
    high, normal, structural = partition_by_priority(cands)
    # Structural DEFER: no browser. Remain available in pf_deferred (not rejection).
    for rec in structural:
        dom = (rec.get("domain") or "").lower()
        if not dom or dom in results or dom in deferred:
            continue
        reason = structural_blocker_reason(rec) or "structural_blocker"
        deferred[dom] = make_deferred_row(rec, reason)
        increment_defer_counters(cp, reason)
        mark_status(cp, dom, STATUS_PF_DEFERRED)
        _log(f"[PF] {dom} -> DEFER {reason} (no browser)")

    pending = schedule_weighted(high, normal, take=batch_size)
    pending = [c for c in pending if (c.get("domain") or "") not in results and (c.get("domain") or "") not in deferred]
    if not pending and not structural:
        return 0
    before = len(results)
    total = len(cands)
    sem = asyncio.Semaphore(max(1, min(2, pf_workers)))

    async def _one(rec: dict) -> tuple[str, dict | None, str | None]:
        dom = (rec.get("domain") or "").lower()
        if not claim_domain(f"pf:{dom}"):
            return dom, None, "duplicate_in_flight"
        mark_status(cp, dom, STATUS_PF_IN_PROGRESS)
        async with sem:
            try:
                if should_skip_browser_pf(rec):
                    reason = structural_blocker_reason(rec) or "structural_blocker"
                    return dom, make_deferred_row(rec, reason), reason
                sent_before = get_real_submission_count()
                with enter_nf_pf_budget():
                    try:
                        row = await asyncio.wait_for(
                            fp_mod.preflight_one(rec, len(results) + 1, total),
                            timeout=24.0,
                        )
                    except asyncio.TimeoutError:
                        return dom, make_deferred_row(rec, "pf_time_budget_exceeded"), "pf_time_budget_exceeded"
                    except (PfDefer, PfFastFail) as e:
                        return dom, make_deferred_row(rec, e.reason), e.reason
                if get_real_submission_count() > sent_before:
                    _hard_stop(f"submission during preflight {dom}")
                return dom, row, None
            except Exception as e:
                _log(f"[PF] {dom} SKIP {type(e).__name__}: {str(e)[:80]}")
                cp.setdefault("exclusions", {})[dom] = f"PF_SKIP:{type(e).__name__}"
                return dom, None, None
            finally:
                release_domain(f"pf:{dom}")

    pairs = await asyncio.gather(*[_one(rec) for rec in pending], return_exceptions=True)
    completed = 0
    for item in pairs:
        if isinstance(item, Exception):
            continue
        dom, row, defer_reason = item
        if not dom or not row:
            continue
        if row.get("preflight_outcome") == OUTCOME_PF_DEFERRED or defer_reason:
            deferred[dom] = row
            increment_defer_counters(cp, defer_reason or row.get("skip_reason") or "")
            mark_status(cp, dom, STATUS_PF_DEFERRED)
            _log(f"[PF] {dom} -> DEFER {row.get('skip_reason')}")
            completed += 1
            continue
        results[dom] = row
        mark_status(cp, dom, STATUS_PF_COMPLETE)
        _log(f"[PF] {dom} -> SEMANTIC_REFRESH")
        completed += 1
    cp["preflight_results"] = results
    cp["pf_deferred"] = deferred
    save_factory_checkpoint(cp)
    return completed


async def run_rf_batch(
    cp: dict,
    *,
    batch_size: int,
    pool_by_dom: dict[str, dict] | None = None,
    priority_domains: set[str] | None = None,
    rf_workers: int = 2,
) -> int:
    """Semantic refresh using Night Factory checkpoint only."""
    pf_rows = list((cp.get("preflight_results") or {}).values())
    results: dict[str, dict] = cp.get("refresh_results") or {}
    eligible = [r for r in r2_pipe._refresh_eligible_preflight_rows(pf_rows) if rf_should_accept(r)]

    def _rf_sort_key(row: dict) -> tuple:
        dom = (row.get("domain") or "").lower()
        src = (pool_by_dom or {}).get(dom) or {}
        tier = src.get("ready_priority_tier") or ""
        tier_rank = 0 if tier == READY_PRIORITY_A else (1 if tier == READY_PRIORITY_B else 2)
        in_batch = 0 if priority_domains and dom in priority_domains else 1
        harden = rf_sort_key(row)
        return (in_batch, harden[0], tier_rank, -int(src.get("ready_yield_score") or 0))

    eligible.sort(key=_rf_sort_key)
    if priority_domains:
        primary = [r for r in eligible if (r.get("domain") or "").lower() in priority_domains]
        secondary = [r for r in eligible if (r.get("domain") or "").lower() not in priority_domains]
        eligible = primary + secondary
    pending = [r for r in eligible if r.get("domain") not in results][:batch_size]
    if not pending:
        return 0
    before = len(results)
    total = len(eligible)
    sem = asyncio.Semaphore(max(1, min(2, rf_workers)))

    async def _one(row: dict) -> tuple[str, dict | None]:
        dom = (row.get("domain") or "").lower()
        if not claim_domain(f"rf:{dom}"):
            return dom, None
        mark_status(cp, dom, STATUS_RF_IN_PROGRESS)
        async with sem:
            try:
                sent_before = get_real_submission_count()
                result = await refresh_mod._refresh_one(row, len(results) + 1, total)
                if get_real_submission_count() > sent_before:
                    _hard_stop(f"submission during refresh {dom}")
                result["purpose_audit"] = r2_pipe._purpose_audit_from_result(result)
                result["r2_supply"] = False
                result["_source"] = "night_factory"
                return dom, result
            except Exception as e:
                _log(f"[RF] {dom} SKIP {type(e).__name__}: {str(e)[:80]}")
                return dom, None
            finally:
                release_domain(f"rf:{dom}")

    pairs = await asyncio.gather(*[_one(row) for row in pending], return_exceptions=True)
    for item in pairs:
        if isinstance(item, Exception):
            continue
        dom, result = item
        if result and dom:
            results[dom] = result
            mark_status(cp, dom, STATUS_RF_COMPLETE)
            _log(f"[RF] {dom} -> {result.get('refresh_outcome', '')}")
    cp["refresh_results"] = results
    save_factory_checkpoint(cp)
    return len(results) - before


def _collect_new_ready(
    pool_by_dom: dict[str, dict],
    cp: dict,
    inv: dict,
) -> dict:
    attempted = load_attempted_domains()
    excluded = set((inv.get("domains_primary") or []) + (inv.get("domains_remodel") or []))
    get_sent_domain_index.cache_clear()
    sent_idx = get_sent_domain_index()
    pf = cp.get("preflight_results") or {}
    rf = cp.get("refresh_results") or {}
    added_primary = added_remodel = 0

    for rec in (inv.get("ready_primary") or []) + (inv.get("ready_remodel_reserve") or []):
        if rec.get("consumed_by_production"):
            excluded.add((rec.get("domain") or "").lower())

    for dom, src in pool_by_dom.items():
        if dom in excluded:
            continue
        if sent_idx.is_confirmed_sent_domain(dom) or sent_idx.should_no_resend(dom):
            continue
        ok, bucket, rec, reason = evaluate_ready(dom, src, pf, rf, excluded=excluded, attempted=attempted)
        if not ok or not rec:
            continue
        if not ready_insert_atomic(inv, rec, bucket):
            continue
        if bucket == "remodel":
            added_remodel += 1
        else:
            added_primary += 1
        mark_status(cp, dom, STATUS_READY)
        excluded.add(dom)
        total = len(inv.get("ready_primary") or []) + len(inv.get("ready_remodel_reserve") or [])
        target = stop_target(load_factory_state().get("config") or DEFAULT_CONFIG)
        _log(f"[RF] {dom} -> READY | total={total}/{target} ({bucket})")

    if added_primary or added_remodel:
        save_ready_inventory(inv)
    return {"added_primary": added_primary, "added_remodel": added_remodel}


def validate_night_factory() -> dict[str, Any]:
    _ensure_safety()
    limits = load_limits(FACTORY_DATE)
    owner = verify_authorized_terminal_owner(night_factory_pid=_night_factory_pid())
    checks = {
        "real_sends": get_real_submission_count(),
        "final_submit": 0,
        "production_limit": limits.production_limit,
        "production_owner_valid": bool(owner.get("valid")),
        "production_owner_reason": owner.get("reason"),
        "automation_paused": is_paused(JOB_ID),
        "submit_forbidden": get_submit_forbidden(),
        "sent_csv_lines": _sent_csv_lines(),
        "terminal_confirm_ignored": bool(os.environ.get("ARI_TERMINAL_PRODUCTION_CONFIRM")),
        "night_factory_mutates_production_limit": False,
    }
    errors: list[str] = []
    if checks["real_sends"] != 0:
        errors.append("REAL_SENDS must be 0")
    if not checks["submit_forbidden"]:
        errors.append("Night Factory submit_forbidden must be true")
    if checks["production_limit"] != 0 and not checks["production_owner_valid"]:
        errors.append(
            f"production_limit={checks['production_limit']} without authorized Terminal owner"
        )
    if not checks["automation_paused"]:
        errors.append("automation_paused must be true")
    checks["serial_lw_root_cause"] = serial_lw_root_cause_report()
    checks["pass"] = len(errors) == 0
    checks["errors"] = errors
    checks["gate"] = (
        "READY_TO_RESUME_NIGHT_FACTORY_CONCURRENT" if checks["pass"] else "KEEP_NIGHT_FACTORY_PAUSED"
    )
    return checks


def status_report() -> dict[str, Any]:
    state = load_factory_state()
    inv = load_ready_inventory()
    cp = load_factory_checkpoint()
    config = state.get("config") or DEFAULT_CONFIG
    target = int(config.get("target_ready", 500))
    buffer = int(config.get("buffer", 50))
    stop_at = stop_target(config)
    primary = len(inv.get("ready_primary") or [])
    remodel = len(inv.get("ready_remodel_reserve") or [])
    total = primary + remodel
    last_hour, rate = _ready_rate(state)

    pid_info = read_worker_pid_status(exclude_pids={os.getpid()})
    if pid_info.get("stale") and PID_FILE.exists():
        cleanup_stale_pid(exclude_pids={os.getpid()})
    worker_running = bool(pid_info.get("worker_running"))
    pid = pid_info.get("pid") if worker_running else None
    uptime = None
    if worker_running and pid:
        started = state.get("started_at")
        if started:
            uptime = int(datetime.now().timestamp() - datetime.fromisoformat(started).timestamp())

    limits = load_limits(FACTORY_DATE)
    lw_st = load_checkpoint(NIGHT_FACTORY_LW_RUN_ID) or {}
    lw_done = sum(1 for c in lw_st.get("candidates") or [] if c.get("status") == "completed")
    fast_http = cp.get("fast_http_results") or {}
    throughput = (state.get("stats") or {}).get("throughput") or {}
    rolling = attach_ready_rate(compute_rolling_throughput(cp), state)
    pending = None
    if cp.get("source_initialized"):
        try:
            src, _, _ = initialize_source_inventory(state, cp, force_rebuild=False)
            pending = count_pipeline_pending(src, cp, lw_st)
        except Exception:
            pending = None

    report = {
        "worker_running": worker_running,
        "pid": pid if worker_running else None,
        "uptime_sec": uptime,
        "source_eligible": effective_source_eligible(state, cp),
        "source_initialized": bool(state.get("source_initialized") or cp.get("source_initialized")),
        "source_processed": max(lw_done, len(fast_http)),
        "lw_processed": lw_done,
        "fast_http_processed": len(fast_http),
        "fast_http_per_hour": throughput.get("fast_http_per_hour"),
        "browser_promoted": throughput.get("browser_promoted"),
        "lw_per_hour": throughput.get("lw_per_hour"),
        "pf_per_hour": (rolling.get("pf_per_hour") if rolling.get("pf_last_hour") else throughput.get("pf_per_hour")),
        "rf_per_hour": (rolling.get("rf_per_hour") if rolling.get("rf_last_hour") else throughput.get("rf_per_hour")),
        "READY_per_hour": rolling.get("READY_per_hour") or throughput.get("READY_per_hour") or round(rate, 1),
        "pf_last_hour": rolling.get("pf_last_hour"),
        "rf_last_hour": rolling.get("rf_last_hour"),
        "avg_pf_seconds": rolling.get("avg_pf_seconds"),
        "p50_pf_seconds": rolling.get("p50_pf_seconds"),
        "p95_pf_seconds": rolling.get("p95_pf_seconds"),
        "avg_rf_seconds": rolling.get("avg_rf_seconds"),
        "p50_rf_seconds": rolling.get("p50_rf_seconds"),
        "p95_rf_seconds": rolling.get("p95_rf_seconds"),
        "pf_high_pending": rolling.get("pf_high_pending"),
        "pf_normal_pending": rolling.get("pf_normal_pending"),
        "pf_deferred": rolling.get("pf_deferred"),
        "rf_pending": rolling.get("rf_pending"),
        "pf_fast_fail_count": rolling.get("pf_fast_fail_count"),
        "pf_timeout_defer_count": rolling.get("pf_timeout_defer_count"),
        "dynamic_form_defer_count": rolling.get("dynamic_form_defer_count"),
        "invisible_field_defer_count": rolling.get("invisible_field_defer_count"),
        "READY_yield_from_pf": rolling.get("READY_yield_from_pf"),
        "READY_yield_from_rf": rolling.get("READY_yield_from_rf"),
        "fast_lane_count": throughput.get("fast_lane_count"),
        "slow_lane_count": throughput.get("slow_lane_count"),
        "ETA_500": throughput.get("ETA_500"),
        "ETA_550": throughput.get("ETA_550"),
        "pipeline_pending": pending,
        "serial_lw_root_cause": serial_lw_root_cause_report(),
        "pf_processed": len(cp.get("preflight_results") or {}),
        "rf_processed": len(cp.get("refresh_results") or {}),
        "READY_PRIMARY": primary,
        "READY_REMODEL_RESERVE": remodel,
        "READY_TOTAL": total,
        "ready_last_hour": last_hour,
        "ready_per_hour": round(rate, 1),
        "target": target,
        "buffer": buffer,
        "stop_target": stop_at,
        "remaining_to_target": max(0, stop_at - total),
        "remaining_to_500": max(0, target - total),
        "remaining_to_550": max(0, stop_at - total),
        "eta": _eta_remaining(max(0, stop_at - total), rate),
        "REAL_SENDS": get_real_submission_count(),
        "FINAL_SUBMIT": 0,
        "production_limit": limits.production_limit,
        "automation_paused": is_paused(JOB_ID),
        "submit_forbidden": True,
        "last_checkpoint": state.get("last_checkpoint_at") or cp.get("updated_at"),
        "last_error": state.get("last_error"),
        "last_error_timestamp": state.get("last_error_timestamp"),
        "exit_reason": state.get("exit_reason"),
        "hard_stop": state.get("hard_stop"),
        "checkpoint_schema_version": cp.get("schema_version"),
        "effective_confirmed_sent": count_official_confirmed_sent(),
    }
    return report


def print_status() -> None:
    r = status_report()
    print(json.dumps(r, ensure_ascii=False, indent=2), flush=True)
    print(
        f"\nNIGHT FACTORY | READY {r['READY_TOTAL']}/{r['stop_target']} "
        f"(primary={r['READY_PRIMARY']} remodel={r['READY_REMODEL_RESERVE']}) "
        f"| {r['ready_per_hour']} READY/h | ETA {r['eta']}",
        flush=True,
    )


async def factory_loop(
    *,
    target_ready: int,
    buffer: int,
    lw_batch: int,
    pf_batch: int,
    rf_batch: int,
    resume: bool,
    max_cycles: int | None = None,
    pipeline_chunk: int = 200,
) -> dict[str, Any]:
    global _STOP_REQUESTED, _SENT_CSV_BASELINE

    _ensure_safety()
    start_gate = ensure_worker_start_allowed()
    if not start_gate.get("allowed"):
        raise RuntimeError(
            f"Night Factory worker already running (pid={start_gate.get('pid')})"
        )

    cleanup_stale_pid(exclude_pids={os.getpid()})
    _SENT_CSV_BASELINE = _sent_csv_lines()
    _write_pid()
    if int(PID_FILE.read_text(encoding="utf-8").strip()) != os.getpid():
        raise RuntimeError("PID ownership race — aborting startup")

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    state = load_factory_state()
    state.setdefault("stats", {})
    config = dict(DEFAULT_CONFIG)
    config.update({
        "target_ready": target_ready,
        "buffer": buffer,
        "lw_batch_size": lw_batch,
        "pipeline_chunk_size": pipeline_chunk,
        "pf_batch_size": pf_batch,
        "rf_batch_size": rf_batch,
        "pf_workers": int((state.get("config") or {}).get("pf_workers") or DEFAULT_CONFIG.get("pf_workers", 2)),
        "rf_workers": int((state.get("config") or {}).get("rf_workers") or DEFAULT_CONFIG.get("rf_workers", 2)),
        "checkpoint_interval_sec": int((state.get("config") or {}).get("checkpoint_interval_sec") or 300),
    })
    state["config"] = config
    prior_hard = state.get("hard_stop")
    state["hard_stop"] = None
    state["last_error"] = None
    if resume and state.get("exit_reason") in (
        "max_cycles_reached", "graceful_stop", "completed", None,
    ):
        state["exit_reason"] = None
        state["stopped_at"] = None
    elif resume and state.get("exit_reason") == "safety_violation" and isinstance(prior_hard, str) and (
        prior_hard.startswith("production_limit=")
    ):
        state["exit_reason"] = None
        state["stopped_at"] = None
        state["coexistence_hard_stop_resolved"] = prior_hard
    elif not resume:
        state["exit_reason"] = None
    if not state.get("started_at"):
        state["started_at"] = datetime.now().isoformat()
    save_factory_state(state)

    cp = load_factory_checkpoint()
    source, pool_by_dom, cp = initialize_source_inventory(state, cp, force_rebuild=False)
    _log(f"Source inventory initialized | eligible={len(source)} | resume={resume} | identity={cp.get('source_population_identity')}")

    ingest_meta = ingest_existing_evidence(cp, pool_by_dom)
    save_factory_checkpoint(cp)
    _log(f"Ingested evidence: {ingest_meta}")

    inv = recalculate_ready_inventory(pool_by_dom, cp)
    _record_ready_timestamps(inv, state)
    state["stats"]["ready_primary"] = len(inv.get("ready_primary") or [])
    state["stats"]["ready_remodel_reserve"] = len(inv.get("ready_remodel_reserve") or [])
    state["stats"]["ready_total"] = state["stats"]["ready_primary"] + state["stats"]["ready_remodel_reserve"]
    save_factory_state(state)

    stop_at = stop_target(config)
    _log(f"Night Factory start | target={target_ready} buffer={buffer} stop_at={stop_at} | source={len(source)}")

    lw_st = ensure_lw_checkpoint(source)
    cp["_source_cache_len"] = len(source)
    save_factory_checkpoint(cp)
    _log(f"LW checkpoint | candidates={len(lw_st.get('candidates') or [])} | pipeline_pending={count_pipeline_pending(source, cp, lw_st)}")
    _log(f"Serial LW root cause (fixed): {json.dumps(serial_lw_root_cause_report(), ensure_ascii=False)}")

    last_summary = time.time()
    last_checkpoint = time.time()
    cycle = 0
    chunk_size = int(config.get("pipeline_chunk_size", pipeline_chunk))

    while not _STOP_REQUESTED:
        cycle += 1
        if max_cycles is not None and cycle > max_cycles:
            state["exit_reason"] = "max_cycles_reached"
            _log(f"Max cycles reached ({max_cycles}) — graceful stop")
            break

        _safety_check(state=state)
        refresh_production_exclusions(load_ready_inventory(), cp)

        inv = load_ready_inventory()
        total = len(inv.get("ready_primary") or []) + len(inv.get("ready_remodel_reserve") or [])
        if total >= stop_at:
            state["exit_reason"] = "target_reached"
            _log(f"Target reached: READY_TOTAL={total} >= {stop_at}")
            break

        lw_st = load_checkpoint(NIGHT_FACTORY_LW_RUN_ID) or ensure_lw_checkpoint(source)
        allow_slow = _ab_pending(source, cp, lw_st) == 0
        config["allow_slow_path"] = allow_slow
        pending = count_pipeline_pending(source, cp, lw_st, allow_slow=allow_slow)

        if pending > 0:
            stats = await run_pipeline_chunk(
                source=source,
                pool_by_dom=pool_by_dom,
                cp=cp,
                lw_st=lw_st,
                inv=inv,
                state=state,
                config=config,
                stop_at=stop_at,
                max_source=chunk_size,
            )
            tp = stats.to_dict(ready_total=total, stop_target=stop_at)
            state.setdefault("stats", {})["throughput"] = tp
            state["stats"]["fast_http_processed"] = stats.fast_http_processed
            state["stats"]["lw_processed"] = sum(
                1 for c in (load_checkpoint(NIGHT_FACTORY_LW_RUN_ID) or {}).get("candidates") or []
                if c.get("status") == "completed"
            )
            _log(
                f"Pipeline chunk | FAST {stats.fast_http_processed} LW {stats.lw_completed} "
                f"promoted {stats.browser_promoted} | {tp.get('fast_http_per_hour', 0):.0f} FAST/h "
                f"{tp.get('lw_per_hour', 0):.0f} LW/h"
            )

        pf_added = await run_pf_batch(
            cp, batch_size=pf_batch, pool_by_dom=pool_by_dom,
            pf_workers=int(config.get("pf_workers", 2)),
        )
        state["stats"]["pf_processed"] = len(cp.get("preflight_results") or {})

        rf_added = await run_rf_batch(
            cp, batch_size=rf_batch, pool_by_dom=pool_by_dom,
            rf_workers=int(config.get("rf_workers", 2)),
        )
        state["stats"]["rf_processed"] = len(cp.get("refresh_results") or {})

        added = _collect_new_ready(pool_by_dom, cp, inv)
        inv = load_ready_inventory()
        _record_ready_timestamps(inv, state)

        primary = len(inv.get("ready_primary") or [])
        remodel = len(inv.get("ready_remodel_reserve") or [])
        total = primary + remodel
        state["stats"]["ready_primary"] = primary
        state["stats"]["ready_remodel_reserve"] = remodel
        state["stats"]["ready_total"] = total
        state["stats"]["source_eligible"] = len(source)
        save_factory_state(state)
        save_factory_checkpoint(cp)

        now = time.time()
        if now - last_checkpoint >= int(config.get("checkpoint_interval_sec", 300)):
            build_morning_inventory(inv, target=target_ready, cp=cp)
            state["last_checkpoint_at"] = datetime.now().isoformat()
            save_factory_state(state)
            last_checkpoint = now

        lw_st = load_checkpoint(NIGHT_FACTORY_LW_RUN_ID) or {}
        exhausted = is_source_exhausted(source, cp, lw_st)
        if exhausted and pf_added == 0 and rf_added == 0 and added["added_primary"] + added["added_remodel"] == 0:
            state["exit_reason"] = "source_exhausted"
            save_factory_state(state)
            _log("Source population exhausted — no pending work")
            break

        if pending == 0 and pf_added == 0 and rf_added == 0 and added["added_primary"] + added["added_remodel"] == 0:
            await asyncio.sleep(5)
            continue

        if not cp.get("source_initialized"):
            _log("WARNING: source not initialized — continuing (will not treat as exhausted)")

        now = time.time()
        if now - last_summary >= int(config.get("summary_interval_sec", 900)):
            tp = state.get("stats", {}).get("throughput") or {}
            _, rate = _ready_rate(state)
            _log(
                f"NIGHT FACTORY | READY {total}/{stop_at} | primary={primary} remodel={remodel} "
                f"| FAST {tp.get('fast_http_per_hour', 0)} /h LW {tp.get('lw_per_hour', 0)} /h "
                f"| {rate:.0f} READY/h | ETA {_eta_remaining(max(0, stop_at - total), rate)} "
                f"| proj overnight {tp.get('projected_overnight_ready', total)}"
            )
            last_summary = now

        await asyncio.sleep(2)

    if not state.get("exit_reason"):
        state["exit_reason"] = "graceful_stop" if _STOP_REQUESTED else "completed"
    state["stopped_at"] = datetime.now().isoformat()
    save_factory_state(state)
    build_morning_inventory(inv, target=target_ready, cp=cp)
    _clear_pid_if_owned()
    return status_report()


BENCHMARK_100_PF_DOMAINS = (
    "hhsantoku.co.jp", "rpg-heya.com", "classy-homes.jp", "ebisu-fudousan.com",
    "riumm.co.jp", "shotoku-re.co.jp", "lotus-ap.co.jp", "ko-yu.com",
    "chintai.sk-crew.jp", "orangeroom.jp", "townhousing.co.jp",
    "roomlab-hikifuneekimaeten.com", "hikarihome.co.jp", "akiba-estate.jp",
    "akb-o.jp", "axes.jp.net", "sanchafu.co.jp", "oddss-space.net",
    "nexture-gr.co.jp", "clcnet.jp", "sumutasu.jp", "fgh.co.jp",
    "d-actus.com", "shinjukuchintai.co.jp", "fukutsu.co.jp",
    "chintai.yoshizumihome.co.jp",
)


def audit_benchmark_pf_zero_ready(cp: dict | None = None) -> dict[str, Any]:
    """Classify why 26 benchmark PREFLIGHT_CANDIDATE produced READY=0."""
    cp = cp or load_factory_checkpoint()
    pf = cp.get("preflight_results") or {}
    rf = cp.get("refresh_results") or {}
    stages = cp.get("domain_stages") or {}

    def _classify(dom: str) -> tuple[str, dict]:
        p = pf.get(dom, {})
        r = rf.get(dom, {})
        stage = stages.get(dom, "")
        if not p:
            if stage == "PREFLIGHT_CANDIDATE":
                return "pf_backlog_starvation", {"detail": "LW passed but PF never reached this domain during benchmark window"}
            return "pf_not_run", {"stage": stage}
        pf_cls = p.get("preflight_classification") or ""
        pf_out = p.get("preflight_outcome") or ""
        fill = p.get("fill_no_submit") or {}
        if fill.get("captcha_detected"):
            return "captcha", {"pf_cls": pf_cls}
        if fill.get("form_not_suitable"):
            return "form_not_suitable", {"pf_cls": pf_cls}
        if "missing" in json.dumps(fill).lower() or pf_out == "VALIDATION_FAILED":
            return "required_field_unresolved", {"pf_out": pf_out, "fill": fill.get("reason")}
        if pf_cls == "NOT_READY":
            return "semantic_evidence_mismatch", {"pf_cls": pf_cls, "pf_out": pf_out}
        if not r:
            if pf_cls in ("AUTO_READY", "AUTO_READY_CANDIDATE", "CONFIRMATION_READY"):
                return "rf_backlog_starvation", {"pf_cls": pf_cls, "pf_out": pf_out}
            return "rf_pending", {"pf_cls": pf_cls}
        rf_out = r.get("refresh_outcome") or ""
        rf_reason = r.get("refresh_reason") or ""
        if rf_out == "VALIDATION_FAILED":
            return "validation_required", {"reason": rf_reason}
        if rf_out == "MATERIAL_SEMANTIC_CHANGE":
            return "semantic_evidence_mismatch", {"reason": rf_reason}
        if rf_out != "REFRESH_READY":
            return "other", {"rf_out": rf_out, "reason": rf_reason}
        return "refresh_ready_not_promoted", {"rf_out": rf_out}

    rows = []
    reasons = Counter()
    for dom in BENCHMARK_100_PF_DOMAINS:
        cls, meta = _classify(dom)
        reasons[cls] += 1
        rows.append({"domain": dom, "reason_class": cls, **meta})

    return {
        "benchmark_pf_count": len(BENCHMARK_100_PF_DOMAINS),
        "ready_yield": 0,
        "reason_distribution": dict(reasons),
        "failure_class_actions": {
            "pf_backlog_starvation": "generic_runtime_defect — PF queue prioritized old backlog over new LW candidates",
            "rf_backlog_starvation": "generic_runtime_defect — RF queue did not drain batch PF before benchmark end",
            "required_field_unresolved": "source_selection_or_form_unsuitable",
            "validation_required": "source_selection — deprioritize similar signatures",
            "semantic_evidence_mismatch": "source_selection — deprioritize",
            "captcha": "source_selection — exclude",
            "form_not_suitable": "legitimate_unsuitable — exclude",
        },
        "domains": rows,
    }


def _external_production_blocks_factory() -> bool:
    limits = load_limits(FACTORY_DATE)
    if limits.production_limit == 0:
        return False
    owner = verify_authorized_terminal_owner(night_factory_pid=_night_factory_pid())
    return not bool(owner.get("valid"))


def compute_high_yield_gate(*, ready_yield: int, ready_per_hour: float, ready_total: int, stop_at: int) -> str:
    if get_real_submission_count() != 0:
        return "NIGHT_FACTORY_NOT_READY"
    if _external_production_blocks_factory() or not is_paused(JOB_ID):
        return "NIGHT_FACTORY_NOT_READY"
    if ready_yield > 0 and ready_per_hour >= 3 and ready_total + ready_per_hour * 8 >= min(100, stop_at - ready_total):
        return "READY_TO_RESTART_NIGHT_FACTORY_HIGH_YIELD"
    if ready_yield > 0 and ready_per_hour > 0:
        return "HIGH_YIELD_SOURCE_INSUFFICIENT"
    return "HIGH_YIELD_SOURCE_INSUFFICIENT"


def _select_unprocessed_priority_a(
    source: list[dict],
    cp: dict,
    *,
    n: int,
) -> list[dict]:
    fast_done = set((cp.get("fast_http_results") or {}).keys())
    exclusions = set((cp.get("exclusions") or {}).keys())
    lw_st = load_checkpoint(NIGHT_FACTORY_LW_RUN_ID) or {}
    lw_done = {
        (c.get("domain") or "").lower()
        for c in lw_st.get("candidates") or []
        if c.get("status") == "completed"
    }
    blocked = fast_done | exclusions | lw_done
    candidates = select_priority_pool(source, READY_PRIORITY_A, exclude_domains=blocked)
    return candidates[:n]


async def run_high_yield_benchmark(*, n: int = 100, pf_batch: int = 4, rf_batch: int = 4) -> dict[str, Any]:
    """ZERO-SEND benchmark on N READY_PRIORITY_A candidates with PF/RF drain for batch."""
    global _SENT_CSV_BASELINE
    _ensure_safety()
    _SENT_CSV_BASELINE = _sent_csv_lines()
    t0 = time.time()

    state = load_factory_state()
    config = dict(DEFAULT_CONFIG)
    config.update(state.get("config") or {})
    config["pf_batch_size"] = pf_batch
    config["rf_batch_size"] = rf_batch
    cp = load_factory_checkpoint()
    source, pool_by_dom, cp = initialize_source_inventory(state, cp, force_rebuild=False)
    ingest_existing_evidence(cp, pool_by_dom)

    batch = _select_unprocessed_priority_a(source, cp, n=n)
    batch_domains = {(c.get("domain") or "").lower() for c in batch}
    batch_by_dom = {c["domain"]: c for c in batch}
    if len(batch) < n:
        _log(f"WARNING: only {len(batch)} READY_PRIORITY_A unprocessed (requested {n})")

    lw_st = ensure_lw_checkpoint(source)
    inv = load_ready_inventory()
    stop_at = stop_target(config)
    ready_before = len(inv.get("ready_primary") or []) + len(inv.get("ready_remodel_reserve") or [])
    pf_before = len(cp.get("preflight_results") or {})

    stats = await run_pipeline_chunk(
        source=batch,
        pool_by_dom={**pool_by_dom, **batch_by_dom},
        cp=cp,
        lw_st=lw_st,
        inv=inv,
        state=state,
        config=config,
        stop_at=stop_at,
        max_source=len(batch),
    )

    pf_batch_added = rf_batch_added = 0
    for _round in range(80):
        pf_n = await run_pf_batch(
            cp, batch_size=pf_batch, pool_by_dom=pool_by_dom, priority_domains=batch_domains,
        )
        rf_n = await run_rf_batch(
            cp, batch_size=rf_batch, pool_by_dom=pool_by_dom, priority_domains=batch_domains,
        )
        pf_batch_added += pf_n
        rf_batch_added += rf_n
        _collect_new_ready(pool_by_dom, cp, inv)
        if pf_n == 0 and rf_n == 0:
            break
        await asyncio.sleep(1)

    save_factory_checkpoint(cp)
    elapsed = time.time() - t0
    inv = load_ready_inventory()
    ready_after = len(inv.get("ready_primary") or []) + len(inv.get("ready_remodel_reserve") or [])
    ready_yield = ready_after - ready_before

    lw_st = load_checkpoint(NIGHT_FACTORY_LW_RUN_ID) or {}
    pf_candidates = sum(
        1 for c in lw_st.get("candidates") or []
        if (c.get("domain") or "").lower() in batch_domains
        and c.get("lightweight_outcome") == "PREFLIGHT_CANDIDATE"
    )
    refresh_ready = sum(
        1 for dom in batch_domains
        if (cp.get("refresh_results") or {}).get(dom, {}).get("refresh_outcome") == "REFRESH_READY"
    )

    tp = stats.to_dict(ready_total=ready_after, stop_target=stop_at)
    ready_per_hour = (ready_yield / max(elapsed / 3600, 1 / 3600)) if ready_yield else 0.0
    projected = ready_after + ready_per_hour * 8

    report = {
        "benchmark_type": "HIGH_YIELD_PRIORITY_A",
        "benchmark_n": len(batch),
        "tier_counts_full_pool": tier_counts(source),
        "HIGH_YIELD_SOURCE_SIGNATURES": build_high_yield_signatures(),
        "prior_benchmark_audit": audit_benchmark_pf_zero_ready(cp),
        "elapsed_sec": round(elapsed, 1),
        "source_processed": stats.fast_http_processed,
        "PREFLIGHT_CANDIDATE": pf_candidates,
        "REFRESH_READY": refresh_ready,
        "READY_before": ready_before,
        "READY_after": ready_after,
        "READY_yield": ready_yield,
        "READY_per_hour": round(ready_per_hour, 2),
        "prior_READY_yield_100": 0,
        "pf_batch_added": pf_batch_added,
        "rf_batch_added": rf_batch_added,
        "NEW_fast_http_per_hour": tp.get("fast_http_per_hour"),
        "NEW_lw_per_hour": tp.get("lw_per_hour"),
        "outcomes": dict(stats.outcomes),
        "projected_overnight_ready": round(projected, 0),
        "REAL_SENDS": get_real_submission_count(),
        "FINAL_SUBMIT": 0,
        "gate": compute_high_yield_gate(
            ready_yield=ready_yield,
            ready_per_hour=ready_per_hour,
            ready_total=ready_after,
            stop_at=stop_at,
        ),
        "sample_domains": [c.get("domain") for c in batch[:10]],
    }
    state.setdefault("stats", {})["high_yield_benchmark"] = report
    save_factory_state(state)
    return report


def compute_overnight_gate(*, ready_total: int, benchmark: dict | None = None) -> str:
    """Final gate for unattended overnight worker start."""
    v = validate_night_factory()
    if not v.get("pass"):
        return "DO_NOT_START_OVERNIGHT_FACTORY"
    if get_real_submission_count() != 0:
        return "DO_NOT_START_OVERNIGHT_FACTORY"
    if read_worker_pid_status(exclude_pids={os.getpid()}).get("worker_running"):
        return "DO_NOT_START_OVERNIGHT_FACTORY"
    bench = benchmark or (load_factory_state().get("stats") or {}).get("high_yield_benchmark") or {}
    ready_yield = int(bench.get("READY_yield") or 0)
    rph = float(bench.get("READY_per_hour") or 0)
    if ready_yield <= 0 and ready_total < 20:
        return "DO_NOT_START_OVERNIGHT_FACTORY"
    if ready_total >= 550:
        return "READY_TO_START_OVERNIGHT_FACTORY"
    if ready_yield > 0 or ready_total >= 15:
        return "READY_TO_START_OVERNIGHT_FACTORY"
    return "DO_NOT_START_OVERNIGHT_FACTORY"


def compute_final_gate(*, ready_total: int, stop_at: int, throughput: dict) -> str:
    """Return exactly one operational gate string."""
    rph = float(throughput.get("READY_per_hour") or 0)
    projected = float(throughput.get("projected_overnight_ready") or ready_total)
    if get_real_submission_count() != 0:
        return "NIGHT_FACTORY_NOT_READY"
    if _external_production_blocks_factory() or not is_paused(JOB_ID):
        return "NIGHT_FACTORY_NOT_READY"
    if projected >= stop_at or (rph > 0 and rph * 8 + ready_total >= stop_at):
        return "READY_TO_RESTART_NIGHT_FACTORY_FAST"
    if throughput.get("fast_http_per_hour"):
        return "THROUGHPUT_INSUFFICIENT_FOR_500"
    return "NIGHT_FACTORY_NOT_READY"


async def run_throughput_benchmark(*, n: int, pf_batch: int = 12, rf_batch: int = 12) -> dict[str, Any]:
    """ZERO-SEND benchmark on N source candidates (no PID file, no detached worker)."""
    global _SENT_CSV_BASELINE
    _ensure_safety()
    _SENT_CSV_BASELINE = _sent_csv_lines()
    t0 = time.time()

    state = load_factory_state()
    config = dict(DEFAULT_CONFIG)
    config.update(state.get("config") or {})
    config["pf_batch_size"] = pf_batch
    config["rf_batch_size"] = rf_batch
    cp = load_factory_checkpoint()
    source, pool_by_dom, cp = initialize_source_inventory(state, cp, force_rebuild=False)
    ingest_existing_evidence(cp, pool_by_dom)
    lw_st = ensure_lw_checkpoint(source)
    inv = load_ready_inventory()
    stop_at = stop_target(config)

    ready_before = len(inv.get("ready_primary") or []) + len(inv.get("ready_remodel_reserve") or [])

    stats = await run_pipeline_chunk(
        source=source,
        pool_by_dom=pool_by_dom,
        cp=cp,
        lw_st=lw_st,
        inv=inv,
        state=state,
        config=config,
        stop_at=stop_at,
        max_source=n,
    )

    await run_pf_batch(cp, batch_size=pf_batch)
    await run_rf_batch(cp, batch_size=rf_batch)
    _collect_new_ready(pool_by_dom, cp, inv)
    save_factory_checkpoint(cp)

    elapsed = time.time() - t0
    inv = load_ready_inventory()
    ready_after = len(inv.get("ready_primary") or []) + len(inv.get("ready_remodel_reserve") or [])
    tp = stats.to_dict(ready_total=ready_after, stop_target=stop_at)
    state.setdefault("stats", {})["throughput"] = tp
    save_factory_state(state)

    from ari_pipeline.night_factory_browser_pool import get_browser_pool
    pool = get_browser_pool()
    browser_launches = pool.launch_count if pool else stats.browser_launches

    report = {
        "benchmark_n": n,
        "elapsed_sec": round(elapsed, 1),
        "OLD_observed_LW_per_hour": 40,
        "NEW_fast_http_per_hour": tp.get("fast_http_per_hour"),
        "NEW_lw_per_hour": tp.get("lw_per_hour"),
        "NEW_pf_per_hour": tp.get("pf_per_hour"),
        "NEW_rf_per_hour": tp.get("rf_per_hour"),
        "NEW_READY_per_hour": tp.get("READY_per_hour"),
        "fast_http_processed": stats.fast_http_processed,
        "browser_promoted": stats.browser_promoted,
        "lw_completed": stats.lw_completed,
        "pf_completed": stats.pf_completed,
        "rf_completed": stats.rf_completed,
        "READY_before": ready_before,
        "READY_after": ready_after,
        "READY_yield": ready_after - ready_before,
        "avg_sec_per_source": round(elapsed / max(stats.fast_http_processed, 1), 2),
        "browser_launches": browser_launches,
        "timeout_counts": stats.timeouts,
        "outcomes": dict(stats.outcomes),
        "fast_lane_count": stats.fast_lane,
        "slow_lane_count": stats.slow_lane,
        "projected_overnight_ready": tp.get("projected_overnight_ready"),
        "ETA_500": tp.get("ETA_500"),
        "ETA_550": tp.get("ETA_550"),
        "REAL_SENDS": get_real_submission_count(),
        "FINAL_SUBMIT": 0,
        "serial_lw_root_cause": serial_lw_root_cause_report(),
        "gate": compute_final_gate(ready_total=ready_after, stop_at=stop_at, throughput=tp),
    }
    return report


def bootstrap_inventory_report() -> dict[str, Any]:
    """Pre-run inventory counts without browser work."""
    state = load_factory_state()
    cp = load_factory_checkpoint()
    source, pool_by_dom, cp = initialize_source_inventory(state, cp, force_rebuild=True)
    ingested = ingest_existing_evidence(cp, pool_by_dom)
    save_factory_checkpoint(cp)
    inv = recalculate_ready_inventory(pool_by_dom, cp)
    return {
        "source_eligible": len(source),
        "source_initialized": cp.get("source_initialized"),
        "source_population_identity": cp.get("source_population_identity"),
        "ingested": ingested,
        "ready_primary": len(inv.get("ready_primary") or []),
        "ready_remodel_reserve": len(inv.get("ready_remodel_reserve") or []),
        "ready_total": len(inv.get("ready_primary") or []) + len(inv.get("ready_remodel_reserve") or []),
    }


def compute_coexistence_gate() -> str:
    """Exactly one gate for Night Factory resume under Terminal coexistence."""
    if get_real_submission_count() != 0:
        return "KEEP_NIGHT_FACTORY_PAUSED"
    if not get_submit_forbidden():
        return "KEEP_NIGHT_FACTORY_PAUSED"
    if _external_production_blocks_factory():
        return "KEEP_NIGHT_FACTORY_PAUSED"
    return "READY_TO_RESUME_NIGHT_FACTORY_CONCURRENT"


def clear_resolved_coexistence_hard_stop() -> dict[str, Any]:
    """Clear production_limit hard_stop after coexistence contract is in place. Does not start worker."""
    set_submit_forbidden(True)
    state = load_factory_state()
    hs = state.get("hard_stop")
    before = {
        "hard_stop": hs,
        "exit_reason": state.get("exit_reason"),
        "ready_primary": (load_ready_inventory().get("stats") or {}).get("ready_primary"),
    }
    if isinstance(hs, str) and (hs.startswith("production_limit=") or "without authorized owner" in hs):
        state["hard_stop"] = None
        if state.get("exit_reason") == "safety_violation":
            state["exit_reason"] = None
        state["coexistence_hard_stop_resolved"] = hs
        save_factory_state(state)
    return {
        "cleared": state.get("hard_stop") is None,
        "before": before,
        "after_hard_stop": state.get("hard_stop"),
        "gate": compute_coexistence_gate(),
    }
    info = cleanup_stale_pid()
    if not info.get("active"):
        return {"stopped": False, "reason": "not running", "pid_cleanup": info}
    try:
        pid = int(info["pid"])
        os.kill(pid, signal.SIGTERM)
        return {"stopped": True, "pid": pid, "signal": "SIGTERM"}
    except (OSError, ValueError) as e:
        return {"stopped": False, "reason": str(e)}


def main() -> None:
    parser = argparse.ArgumentParser(description="ARI Night Factory — ZERO SEND READY manufacturing")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--bootstrap-report", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--cleanup-pid", action="store_true")
    parser.add_argument("--max-cycles", type=int, default=None)
    parser.add_argument("--target-ready", type=int, default=500)
    parser.add_argument("--buffer", type=int, default=50)
    parser.add_argument("--lw-batch", type=int, default=50)
    parser.add_argument("--pf-batch", type=int, default=12)
    parser.add_argument("--rf-batch", type=int, default=12)
    parser.add_argument("--benchmark-high-yield", type=int, default=None, metavar="N")
    parser.add_argument("--audit-benchmark-pf", action="store_true")
    parser.add_argument("--benchmark", type=int, default=None, metavar="N")
    parser.add_argument("--pipeline-chunk", type=int, default=200)
    parser.add_argument("--coexistence-gate", action="store_true")
    parser.add_argument("--clear-coexistence-hard-stop", action="store_true")
    args = parser.parse_args()

    if args.audit_benchmark_pf:
        print(json.dumps(audit_benchmark_pf_zero_ready(), ensure_ascii=False, indent=2), flush=True)
        return

    if args.benchmark_high_yield is not None:
        _ensure_safety()
        try:
            report = asyncio.run(run_high_yield_benchmark(
                n=args.benchmark_high_yield,
                pf_batch=args.pf_batch,
                rf_batch=args.rf_batch,
            ))
            print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
            print(
                f"\nHIGH_YIELD BENCHMARK | READY {report['READY_yield']}/{report['benchmark_n']} "
                f"({report['READY_per_hour']}/h) | PF={report['PREFLIGHT_CANDIDATE']} "
                f"REFRESH_READY={report['REFRESH_READY']} | gate={report['gate']}",
                flush=True,
            )
        except Exception as e:
            _record_fatal_error(e, exit_reason="high_yield_benchmark_failed")
            sys.exit(1)
        return

    if args.benchmark is not None:
        _ensure_safety()
        try:
            report = asyncio.run(run_throughput_benchmark(
                n=args.benchmark,
                pf_batch=args.pf_batch,
                rf_batch=args.rf_batch,
            ))
            print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
            print(
                f"\nBENCHMARK | OLD LW ~{report['OLD_observed_LW_per_hour']}/h "
                f"→ NEW FAST {report['NEW_fast_http_per_hour']}/h LW {report['NEW_lw_per_hour']}/h "
                f"READY {report['NEW_READY_per_hour']}/h | gate={report['gate']}",
                flush=True,
            )
        except Exception as e:
            _record_fatal_error(e, exit_reason="benchmark_failed")
            sys.exit(1)
        return

    if args.validate:
        print(json.dumps(validate_night_factory(), ensure_ascii=False, indent=2), flush=True)
        return
    if args.coexistence_gate:
        set_submit_forbidden(True)
        print(compute_coexistence_gate(), flush=True)
        return
    if args.clear_coexistence_hard_stop:
        print(json.dumps(clear_resolved_coexistence_hard_stop(), ensure_ascii=False, indent=2), flush=True)
        return
    if args.status:
        print_status()
        return
    if args.stop:
        print(json.dumps(stop_factory(), ensure_ascii=False, indent=2), flush=True)
        return
    if args.bootstrap_report:
        print(json.dumps(bootstrap_inventory_report(), ensure_ascii=False, indent=2), flush=True)
        return
    if args.cleanup_pid:
        print(json.dumps(cleanup_stale_pid(), ensure_ascii=False, indent=2), flush=True)
        return

    exit_code = 0
    try:
        start_gate = ensure_worker_start_allowed()
        if not start_gate.get("allowed"):
            payload = {
                "error": "Night Factory worker already running",
                "pid": start_gate.get("pid"),
                "command": start_gate.get("command"),
                "gate": "NIGHT_FACTORY_NOT_READY",
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr, flush=True)
            sys.exit(1)

        report = asyncio.run(factory_loop(
            target_ready=args.target_ready,
            buffer=args.buffer,
            lw_batch=args.lw_batch,
            pf_batch=args.pf_batch,
            rf_batch=args.rf_batch,
            resume=args.resume or True,
            max_cycles=args.max_cycles,
            pipeline_chunk=args.pipeline_chunk,
        ))
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    except RuntimeError as e:
        if "NIGHT_FACTORY_SAFETY_VIOLATION" in str(e):
            _record_fatal_error(e, exit_reason="safety_violation")
            exit_code = 2
        elif "worker already running" in str(e).lower():
            _record_fatal_error(e, exit_reason="worker_already_running")
            exit_code = 1
        else:
            _record_fatal_error(e)
            exit_code = 1
    except Exception as e:
        _record_fatal_error(e)
        exit_code = 1
    finally:
        _clear_pid_if_owned()

    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
