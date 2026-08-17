#!/usr/bin/env python3
"""
run_ari_full_preflight.py — FULL_PREFLIGHT for all 192 PREFLIGHT_CANDIDATE (ZERO SEND).

Usage:
  PYTHONUNBUFFERED=1 /usr/bin/python3 run_ari_full_preflight.py [--resume] [--status]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))

from automation_state import is_paused, set_paused
from ari_pipeline.limits import AriDailyLimits, load_limits
from candidate_exclusions import domain as extract_domain
from ari_pipeline.sent_domain_index import get_sent_domain_index
from ari_pipeline.status_integrity import count_official_confirmed_sent
from config import LOG_DIR, LOG_SENT, VAULT_ROOT
from form_field_resolver import clear_field_cache
from form_fill_no_submit import fill_form_no_submit
from form_sender import get_real_submission_count, reset_real_submission_count, set_submit_forbidden
from message_builder import build_lp_url, build_message
from preflight_classifier import (
    AUTO_READY,
    FORM_NOT_SUITABLE,
    MANUAL_INTERVENTION_REQUIRED,
    NOT_READY,
    bucket_not_ready_reason,
    classify_preflight,
)
from shared_form_prepare import RUNTIME_DIVERGENCE
import run_ari_unknown_site_expansion_batch as exp

POOL_DATE = "2026-08-12"
EXPECTED_PREFLIGHT = 192
LW_REPORT = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Lightweight-Detect-2026-08-12.json"
LW_CHECKPOINT = LOG_DIR / "ari_checkpoints/orchestrator_lw_2026-08-12.json"
LOCK_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Full-Preflight-Batch-2026-08-12-192.json"
OUT_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Full-Preflight-2026-08-12.json"
OUT_MD = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI Full Preflight 2026-08-12.md"
CHECKPOINT = LOG_DIR / "ari_checkpoints/full_preflight_2026-08-12.json"
LOG_PATH = LOG_DIR / "ari_full_preflight_2026-08-12.log"

_FILL_KEYS = (
    "status", "reason", "form_url", "field_map", "steps",
    "final_submit_identified", "final_submit_label", "message_validation",
    "blocked", "captcha_detected", "form_not_suitable", "unsuitable_required_labels",
    "message_selection", "field_source", "partial_fields", "required_fixes",
    "required_choices", "multistep_state", "validation_feedback", "contact_form_scope",
    "preflight_mapping_hash", "prepare_snapshot", "semantic_evidence",
    "message_variant", "message_length",
)


def _sent_csv_rows() -> int:
    if not LOG_SENT.exists():
        return 0
    with LOG_SENT.open(encoding="utf-8") as f:
        return max(0, sum(1 for _ in f) - 1)


def map_report_outcome(classification: str, skip_reason: str, fn: dict) -> str:
    if classification == AUTO_READY:
        if fn.get("multistep_state") in ("CONFIRMATION", "FINAL_SUBMIT_READY"):
            return "CONFIRMATION_READY"
        return "AUTO_READY_CANDIDATE"
    if classification == FORM_NOT_SUITABLE:
        return "FORM_NOT_SUITABLE"
    if classification == MANUAL_INTERVENTION_REQUIRED:
        return "CAPTCHA_MANUAL"
    sr = skip_reason or ""
    if sr == RUNTIME_DIVERGENCE or fn.get("reason") == RUNTIME_DIVERGENCE:
        return "RUNTIME_DIVERGENCE"
    if fn.get("multistep_state") == "VALIDATION_FAILED" or "validation" in sr.lower():
        return "VALIDATION_FAILED"
    if fn.get("status") == "error" and classification == NOT_READY:
        return "INTERNAL_ERROR"
    if classification == NOT_READY:
        return "UNKNOWN"
    return "UNKNOWN"


def assert_pre_run() -> dict:
    if not LW_REPORT.exists():
        raise RuntimeError(f"Missing lightweight report: {LW_REPORT}")
    lw = json.loads(LW_REPORT.read_text(encoding="utf-8"))
    expected = lw.get("lightweight_funnel", {}).get("PREFLIGHT_CANDIDATE", {}).get("count")
    if expected != EXPECTED_PREFLIGHT:
        raise RuntimeError(f"Lightweight report PREFLIGHT_CANDIDATE={expected}, expected {EXPECTED_PREFLIGHT}")

    limits = load_limits(POOL_DATE)
    checks = {
        "production_limit_0": limits.production_limit == 0,
        "production_enabled_false": not limits.production_enabled,
        "auto_ready_limit_0": limits.auto_ready_limit == 0,
        "full_preflight_limit_192": limits.full_preflight_limit == 192,
        "automation_paused": is_paused("form-auto-sender"),
    }
    set_submit_forbidden(True)
    checks["submit_forbidden"] = True

    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise RuntimeError(f"Pre-run FAIL CLOSED: {failed}")

    return {
        "passed": True,
        "checks": checks,
        "sent_csv_rows_at_start": _sent_csv_rows(),
        "official_confirmed_sent": count_official_confirmed_sent(),
    }


def _ensure_safety() -> None:
    if not is_paused("form-auto-sender"):
        set_paused("form-auto-sender", True, by="run_ari_full_preflight.py")
    set_submit_forbidden(True)
    reset_real_submission_count()
    limits = AriDailyLimits(
        date=POOL_DATE,
        full_preflight_limit=192,
        auto_ready_limit=0,
        production_limit=0,
        production_enabled=False,
    )
    limits.save()


def build_lock_population() -> list[dict]:
    """Create deterministic 192 lock from lightweight checkpoint (canonical order)."""
    if LOCK_JSON.exists():
        data = json.loads(LOCK_JSON.read_text(encoding="utf-8"))
        records = data.get("records") or []
        if len(records) == EXPECTED_PREFLIGHT:
            return records

    if not LW_CHECKPOINT.exists():
        raise RuntimeError(f"Missing lightweight checkpoint: {LW_CHECKPOINT}")

    state = json.loads(LW_CHECKPOINT.read_text(encoding="utf-8"))
    idx = get_sent_domain_index()
    records: list[dict] = []
    seen_domains: set[str] = set()

    for i, c in enumerate(state.get("candidates") or []):
        if c.get("lightweight_outcome") != "PREFLIGHT_CANDIDATE":
            continue
        dom = (c.get("domain") or extract_domain(c.get("website_url", "")) or "").lower().strip()
        if not dom:
            raise RuntimeError(f"Missing domain for lock record: {c.get('company_name')}")
        if dom in seen_domains:
            raise RuntimeError(f"Duplicate domain in lock population: {dom}")
        if dom in idx.confirmed_domains:
            raise RuntimeError(f"CONFIRMED_SENT contamination: {dom}")
        seen_domains.add(dom)
        det = c.get("detection") or {}
        records.append({
            "lock_index": len(records) + 1,
            "original_pool_index": i + 1,
            "candidate_id": c.get("candidate_id"),
            "company_name": c.get("company_name"),
            "domain": dom,
            "industry_name": c.get("industry_name"),
            "area_name": c.get("area_name"),
            "website_url": c.get("website_url"),
            "form_url": c.get("form_url") or det.get("form_url") or "",
            "lightweight_outcome": c.get("lightweight_outcome"),
            "lightweight_classification": c.get("lightweight_classification"),
            "lightweight_score": c.get("lightweight_score"),
            "lightweight_reason": c.get("lightweight_reason"),
            "lightweight_evidence": det,
            "place_id": c.get("place_id"),
        })

    if len(records) != EXPECTED_PREFLIGHT:
        raise RuntimeError(f"Lock population count={len(records)}, expected {EXPECTED_PREFLIGHT}")

    lock = {
        "locked_at": datetime.now().isoformat(),
        "pool_date": POOL_DATE,
        "source_lightweight_report": str(LW_REPORT),
        "source_checkpoint": str(LW_CHECKPOINT),
        "record_count": len(records),
        "duplicate_domains": 0,
        "confirmed_sent_contamination": 0,
        "records": records,
    }
    LOCK_JSON.parent.mkdir(parents=True, exist_ok=True)
    LOCK_JSON.write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
    return records


def load_checkpoint() -> dict | None:
    if not CHECKPOINT.exists():
        return None
    return json.loads(CHECKPOINT.read_text(encoding="utf-8"))


def save_checkpoint(state: dict) -> None:
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now().isoformat()
    CHECKPOINT.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def init_checkpoint(records: list[dict]) -> dict:
    existing = load_checkpoint()
    if existing and existing.get("lock_path") == str(LOCK_JSON):
        return existing
    return {
        "pool_date": POOL_DATE,
        "lock_path": str(LOCK_JSON),
        "started_at": datetime.now().isoformat(),
        "results": {},
        "elapsed_seconds": [],
    }


async def preflight_one(record: dict, idx: int, total: int) -> dict:
    name = record.get("company_name", "")
    dom = record.get("domain", "")
    print(f"[{idx:03d}/{total}] START company={name[:40]} domain={dom}", flush=True)
    t0 = time.monotonic()
    submissions_before = get_real_submission_count()

    work = dict(record)
    lp = build_lp_url(work.get("industry_name", ""), work.get("area_name", ""))
    msg = build_message(work.get("industry_name", ""), name, lp, area_name=work.get("area_name", ""))
    fn = await fill_form_no_submit(
        work, msg, lp,
        evidence_dir=VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/evidence/full-preflight-2026-08-12",
    )

    if get_real_submission_count() > submissions_before:
        raise RuntimeError(f"SAFETY_VIOLATION: unexpected submission for {dom}")

    pf = {
        **record,
        "form_url": record.get("form_url") or fn.get("form_url") or "",
        "fill_no_submit": {k: fn.get(k) for k in _FILL_KEYS},
        "form_type": exp._infer_form_type(fn),
    }
    classification, skip_reason, profile = classify_preflight(pf)
    report_outcome = map_report_outcome(classification, skip_reason, pf["fill_no_submit"])
    elapsed = round(time.monotonic() - t0, 1)

    result = {
        **pf,
        "preflight_classification": classification,
        "preflight_outcome": report_outcome,
        "skip_reason": skip_reason,
        "failure_pattern": bucket_not_ready_reason(skip_reason, pf["fill_no_submit"]),
        "required_field_profile": profile,
        "elapsed_seconds": elapsed,
        "completed_at": datetime.now().isoformat(),
    }
    print(
        f"[{idx:03d}/{total}] DONE outcome={report_outcome} classification={classification} "
        f"elapsed={elapsed}s skip={skip_reason or 'ok'}",
        flush=True,
    )
    return result


def _periodic_summary(completed: list[dict], total: int, elapsed_list: list[float]) -> None:
    oc = Counter(r.get("preflight_outcome") for r in completed)
    n = len(completed)
    avg = statistics.mean(elapsed_list) if elapsed_list else 0
    remaining = total - n
    eta_min = (remaining * avg / 60) if avg else 0
    print(
        f"--- PROGRESS {n}/{total} ({100*n/total:.1f}%) | "
        f"AUTO_READY={oc.get('AUTO_READY_CANDIDATE',0)+oc.get('CONFIRMATION_READY',0)} | "
        f"NOT_SUITABLE={oc.get('FORM_NOT_SUITABLE',0)} | CAPTCHA={oc.get('CAPTCHA_MANUAL',0)} | "
        f"VALIDATION={oc.get('VALIDATION_FAILED',0)} | DIVERGENCE={oc.get('RUNTIME_DIVERGENCE',0)} | "
        f"UNKNOWN={oc.get('UNKNOWN',0)} | ERROR={oc.get('INTERNAL_ERROR',0)} | "
        f"avg={avg:.1f}s/candidate ETA={eta_min:.0f}min ---",
        flush=True,
    )


def build_final_report(
    records: list[dict],
    results: list[dict],
    *,
    assertions: dict,
    sent_rows_start: int,
    started_at: str,
) -> dict:
    total = len(records)
    processed = len(results)
    outcomes = Counter(r.get("preflight_outcome") for r in results)
    elapsed_list = [r.get("elapsed_seconds", 0) for r in results if r.get("elapsed_seconds")]
    auto_ready = outcomes.get("AUTO_READY_CANDIDATE", 0) + outcomes.get("CONFIRMATION_READY", 0)

    pct = lambda n: round(100 * n / total, 1) if total else 0.0

    loss_buckets = sorted(
        [(k, v) for k, v in outcomes.items() if k not in ("AUTO_READY_CANDIDATE", "CONFIRMATION_READY")],
        key=lambda x: -x[1],
    )

    def _addressable(bucket: str) -> str:
        if bucket in ("CAPTCHA_MANUAL",):
            return "no — manual/CAPTCHA policy"
        if bucket in ("FORM_NOT_SUITABLE",):
            return "partial — form structure filter"
        if bucket in ("VALIDATION_FAILED",):
            return "yes — generic fill/validation"
        if bucket in ("RUNTIME_DIVERGENCE",):
            return "yes — runtime parity"
        if bucket in ("UNKNOWN", "INTERNAL_ERROR"):
            return "yes — investigate generic patterns"
        return "observe"

    bottlenecks = [
        {
            "bucket": k,
            "count": n,
            "pct_of_192": pct(n),
            "generic_reason": Counter(
                r.get("failure_pattern") or r.get("skip_reason") or "other"
                for r in results if r.get("preflight_outcome") == k
            ).most_common(1)[0][0] if n else "",
            "potentially_addressable": _addressable(k),
        }
        for k, n in loss_buckets[:5]
    ]

    real_sends = get_real_submission_count()
    sent_end = _sent_csv_rows()

    if real_sends > 0 or (sent_end - sent_rows_start) > 0:
        recommendation = "C — STOP_FOR_SAFETY"
    elif auto_ready >= 20 and outcomes.get("RUNTIME_DIVERGENCE", 0) <= 5:
        recommendation = "A — PROCEED_TO_AUTO_READY_LOCK"
    elif outcomes.get("RUNTIME_DIVERGENCE", 0) > 10 or outcomes.get("INTERNAL_ERROR", 0) > 15:
        recommendation = "C — STOP_FOR_SAFETY"
    else:
        recommendation = "B — GENERIC_HARDENING_REQUIRED"

    total_runtime = sum(elapsed_list)
    sorted_el = sorted(elapsed_list) if elapsed_list else [0]

    return {
        "generated_at": datetime.now().isoformat(),
        "pool_date": POOL_DATE,
        "source": {
            "original_candidates": 500,
            "lightweight_processed": 500,
            "preflight_candidate": EXPECTED_PREFLIGHT,
            "full_preflight_target": total,
            "full_preflight_processed": processed,
            "remaining": max(0, total - processed),
        },
        "pre_run_assertions": assertions,
        "outcomes": {k: {"count": v, "pct": pct(v)} for k, v in sorted(outcomes.items(), key=lambda x: -x[1])},
        "preflight_classifications": dict(Counter(r.get("preflight_classification") for r in results)),
        "yields": {
            "auto_ready_per_192": round(auto_ready / total, 4) if total else 0,
            "auto_ready_per_192_pct": round(100 * auto_ready / total, 1) if total else 0,
            "auto_ready_per_500": round(auto_ready / 500, 4),
            "auto_ready_per_500_pct": round(100 * auto_ready / 500, 1),
        },
        "bottleneck_analysis": bottlenecks,
        "performance": {
            "total_runtime_seconds": round(total_runtime, 1),
            "mean_seconds_per_candidate": round(statistics.mean(elapsed_list), 1) if elapsed_list else 0,
            "median_seconds_per_candidate": round(statistics.median(elapsed_list), 1) if elapsed_list else 0,
            "p95_seconds_per_candidate": round(sorted_el[int(len(sorted_el) * 0.95)] if len(sorted_el) > 1 else sorted_el[0], 1),
            "slowest_seconds": round(max(elapsed_list), 1) if elapsed_list else 0,
            "started_at": started_at,
        },
        "safety": {
            "real_sends": real_sends,
            "final_submit_executions": real_sends,
            "sent_csv_new_rows": max(0, sent_end - sent_rows_start),
            "automatic_retries": 0,
            "captcha_bypasses": 0,
            "false_sent": 0,
            "duplicate_sends": 0,
            "runtime_divergence_count": outcomes.get("RUNTIME_DIVERGENCE", 0),
            "production_limit_final": load_limits(POOL_DATE).production_limit,
            "safety_violations": [],
        },
        "recommendation": recommendation,
        "lock_artifact": str(LOCK_JSON),
        "checkpoint": str(CHECKPOINT),
        "results": results,
    }


def write_markdown(report: dict) -> None:
    s = report["source"]
    y = report["yields"]
    saf = report["safety"]
    perf = report["performance"]
    lines = [
        f"# ARI Full Preflight {POOL_DATE}",
        "",
        f"**Generated:** {report['generated_at']}",
        "",
        "## Source Funnel",
        "",
        f"- Original candidates: **{s['original_candidates']}**",
        f"- LIGHTWEIGHT processed: **{s['lightweight_processed']}**",
        f"- PREFLIGHT_CANDIDATE: **{s['preflight_candidate']}**",
        f"- FULL_PREFLIGHT target: **{s['full_preflight_target']}**",
        f"- FULL_PREFLIGHT processed: **{s['full_preflight_processed']}**",
        "",
        "## FULL_PREFLIGHT Outcomes",
        "",
        "| Outcome | Count | % |",
        "| --- | ---: | ---: |",
    ]
    for k, v in report["outcomes"].items():
        lines.append(f"| {k} | {v['count']} | {v['pct']}% |")

    lines.extend([
        "",
        "## Key Yield",
        "",
        f"- AUTO_READY / 192: **{y['auto_ready_per_192_pct']}%**",
        f"- AUTO_READY / 500: **{y['auto_ready_per_500_pct']}%**",
        "",
        "## Bottleneck Top Loss Buckets",
        "",
    ])
    for b in report["bottleneck_analysis"]:
        lines.append(
            f"- **{b['bucket']}**: {b['count']} ({b['pct_of_192']}%) — "
            f"{b['generic_reason']} — addressable: {b['potentially_addressable']}"
        )

    lines.extend([
        "",
        "## Performance",
        "",
        f"- Total runtime: **{perf['total_runtime_seconds']}s**",
        f"- Mean: **{perf['mean_seconds_per_candidate']}s/candidate**",
        f"- Median: **{perf['median_seconds_per_candidate']}s**",
        f"- P95: **{perf['p95_seconds_per_candidate']}s**",
        "",
        "## Safety",
        "",
        f"- REAL SENDS: **{saf['real_sends']}**",
        f"- FINAL_SUBMIT: **{saf['final_submit_executions']}**",
        f"- sent.csv new rows: **{saf['sent_csv_new_rows']}**",
        f"- production_limit: **{saf['production_limit_final']}**",
        "",
        f"## Recommendation: **{report['recommendation']}**",
    ])
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


async def run(*, resume: bool) -> dict:
    _ensure_safety()
    assertions = assert_pre_run()
    sent_rows_start = assertions["sent_csv_rows_at_start"]
    records = build_lock_population()
    state = init_checkpoint(records)
    started_at = state.get("started_at", datetime.now().isoformat())
    done_keys = set(state.get("results", {}).keys())
    results: list[dict] = list(state.get("results", {}).values())
    elapsed_list: list[float] = list(state.get("elapsed_seconds", []))

    total = len(records)
    print(f"FULL_PREFLIGHT batch: {total} locked candidates (production_limit=0)", flush=True)

    for rec in records:
        key = str(rec.get("lock_index"))
        if key in done_keys:
            continue
        idx = int(rec.get("lock_index", 0))
        result = await preflight_one(rec, idx, total)
        state["results"][key] = result
        results.append(result)
        elapsed_list.append(result.get("elapsed_seconds", 0))
        state["elapsed_seconds"] = elapsed_list
        save_checkpoint(state)

        if len(results) % 10 == 0 or len(results) == total:
            _periodic_summary(results, total, elapsed_list)

    report = build_final_report(
        records, results,
        assertions=assertions,
        sent_rows_start=sent_rows_start,
        started_at=started_at,
    )
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report)
    return report


def print_status() -> None:
    state = load_checkpoint()
    if not state:
        print("No full preflight checkpoint.")
        return
    results = list((state.get("results") or {}).values())
    oc = Counter(r.get("preflight_outcome") for r in results)
    print(f"FULL_PREFLIGHT status: {len(results)}/192")
    print(dict(oc))
    print(f"updated_at: {state.get('updated_at')}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        print_status()
        return

    clear_field_cache()
    report = asyncio.run(run(resume=args.resume))
    print("\n=== FULL_PREFLIGHT Complete ===", flush=True)
    print(json.dumps({
        "processed": report["source"]["full_preflight_processed"],
        "yields": report["yields"],
        "recommendation": report["recommendation"],
        "safety": report["safety"],
        "output": str(OUT_JSON),
    }, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
