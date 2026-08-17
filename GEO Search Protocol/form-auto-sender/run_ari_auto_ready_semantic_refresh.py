#!/usr/bin/env python3
"""
run_ari_auto_ready_semantic_refresh.py — ZERO-SEND refresh of 49 AUTO_READY candidates.

Persists canonical v2 semantic evidence without FINAL_SUBMIT.
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
from ari_pipeline.sent_domain_index import get_sent_domain_index
from ari_pipeline.status_integrity import count_official_confirmed_sent
from config import LOG_DIR, VAULT_ROOT
from form_field_resolver import clear_field_cache
from form_fill_no_submit import fill_form_no_submit
from form_sender import get_real_submission_count, reset_real_submission_count, set_submit_forbidden
from message_builder import build_lp_url, build_message
from preflight_classifier import AUTO_READY, FORM_NOT_SUITABLE, MANUAL_INTERVENTION_REQUIRED, NOT_READY
from shared_form_prepare import (
    SEMANTIC_EVIDENCE_SCHEMA_VERSION,
    build_preflight_semantic_evidence,
    compute_semantic_hash,
    evidence_schema_version,
    extract_semantic_hash_payload,
    is_evidence_compatible,
)

POOL_DATE = "2026-08-12"
PREFLIGHT_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Full-Preflight-2026-08-12.json"
OUT_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-AUTO-READY-Semantic-Refresh-2026-08-12.json"
OUT_MD = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI AUTO READY Semantic Refresh 2026-08-12.md"
CHECKPOINT = LOG_DIR / "ari_checkpoints/auto_ready_semantic_refresh_2026-08-12.json"

AUTO_READY_OUTCOMES = frozenset({"AUTO_READY_CANDIDATE", "CONFIRMATION_READY"})
CONFIRMED_SENT_DOMAINS = frozenset({"plazaone.jp", "dig-life.jp"})
B01_DIVERGENCE_DOMAINS = frozenset({"r-ginza.jp", "harudesign.tokyo"})
B01_REMAINING = frozenset({
    "live-art.co.jp", "stylehome.jp", "bestrehome-bestwing.com",
    "room375.com", "sakura-reform.com", "axis-g.com",
})
EFFECTIVE_BASELINE = 794

REFRESH_READY = "REFRESH_READY"
MATERIAL_SEMANTIC_CHANGE = "MATERIAL_SEMANTIC_CHANGE"
REQUIRED_CHOICE_VARIATION = "REQUIRED_CHOICE_VARIATION"
CAPTCHA_MANUAL = "CAPTCHA_MANUAL"
FORM_NOT_SUITABLE_STATE = "FORM_NOT_SUITABLE"
VALIDATION_FAILED = "VALIDATION_FAILED"
UNREACHABLE_ERROR = "UNREACHABLE_ERROR"
OTHER = "OTHER_CANONICAL_STATE"


def _load_auto_ready_population() -> list[dict]:
    data = json.loads(PREFLIGHT_JSON.read_text(encoding="utf-8"))
    rows = [
        r for r in data.get("results", [])
        if r.get("preflight_outcome") in AUTO_READY_OUTCOMES
        or r.get("preflight_classification") == AUTO_READY
    ]
    domains = [r.get("domain") for r in rows]
    if len(rows) != 49:
        raise RuntimeError(f"AUTO_READY count={len(rows)}, expected 49")
    if len(set(domains)) != len(domains):
        raise RuntimeError("Duplicate domains in AUTO_READY population")
    return rows


def _historical_field_map(row: dict) -> dict:
    fn = row.get("fill_no_submit") or {}
    return fn.get("field_map") or row.get("required_field_profile") or {}


def _field_map_materially_changed(hist: dict, current: dict) -> bool:
    for key in ("name", "email", "message", "consent"):
        h = hist.get(key)
        c = current.get(key)
        if h in ("FILLED", "FOUND") and c in ("MISSING", "AMBIGUOUS", None):
            return True
        if h in ("MISSING",) and c in ("FILLED", "FOUND"):
            return True
    return False


def _choice_categories(choice_log: dict) -> set[str]:
    cats = set()
    for bucket in ("applied",):
        for item in (choice_log or {}).get(bucket) or []:
            if item.get("category"):
                cats.add(item["category"])
    post = (choice_log or {}).get("post_fill") or {}
    for item in post.get("applied") or []:
        if item.get("category"):
            cats.add(item["category"])
    return cats


def _classify_refresh(row: dict, fn: dict, historical: dict) -> tuple[str, str]:
    domain = row.get("domain", "")
    if fn.get("captcha_detected"):
        return CAPTCHA_MANUAL, "captcha_detected"
    if fn.get("form_not_suitable") or fn.get("reason") == "form_not_suitable":
        return FORM_NOT_SUITABLE_STATE, fn.get("reason") or "form_not_suitable"
    if fn.get("status") == "error":
        reason = fn.get("reason") or "error"
        if "timeout" in reason or "unreachable" in reason:
            return UNREACHABLE_ERROR, reason
        return OTHER, reason
    if fn.get("multistep_state") == "VALIDATION_FAILED":
        return VALIDATION_FAILED, "validation_failed"
    if fn.get("blocked") or fn.get("status") not in ("filled",):
        return OTHER, fn.get("reason") or fn.get("status") or "blocked"

    sem = fn.get("semantic_evidence") or {}
    if sem.get("semantic_evidence_schema_version") != SEMANTIC_EVIDENCE_SCHEMA_VERSION:
        return OTHER, "missing_v2_semantic_evidence"

    snap = sem.get("canonical_snapshot") or {}
    if not snap.get("fields"):
        return OTHER, "empty_canonical_fields"

    hist_fm = _historical_field_map(historical)
    cur_fm = fn.get("field_map") or snap.get("field_map") or {}
    if _field_map_materially_changed(hist_fm, cur_fm):
        return MATERIAL_SEMANTIC_CHANGE, "field_map_material_change"

    hist_rc = ((historical.get("fill_no_submit") or {}).get("required_choices") or {})
    hist_cats = _choice_categories(hist_rc)
    cur_cats = set()
    for item in snap.get("choices_applied") or []:
        if item.get("category"):
            cur_cats.add(item["category"])
    for item in snap.get("choices_post_fill") or []:
        if item.get("category"):
            cur_cats.add(item["category"])

    if hist_cats and hist_cats != cur_cats:
        return MATERIAL_SEMANTIC_CHANGE, f"choice_category_change:{sorted(hist_cats)}->{sorted(cur_cats)}"

    if "PREFECTURE" in cur_cats or len(cur_cats) >= 2:
        pass  # flagged in risk report, not auto-block unless variation detected

    if domain in CONFIRMED_SENT_DOMAINS:
        return REFRESH_READY, "already_confirmed_sent_excluded_from_future_production"

    return REFRESH_READY, "canonical_v2_valid"


def load_checkpoint() -> dict | None:
    if CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    return None


def save_checkpoint(state: dict) -> None:
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


async def _refresh_one(row: dict, idx: int, total: int) -> dict:
    t0 = time.monotonic()
    dom = row.get("domain", "")
    work = dict(row)
    lp = build_lp_url(work.get("industry_name", ""), work.get("area_name", ""))
    msg = build_message(work.get("industry_name", ""), work.get("company_name", ""), lp, area_name=work.get("area_name", ""))

    submissions_before = get_real_submission_count()
    fn = await fill_form_no_submit(
        work, msg, lp,
        evidence_dir=VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/evidence/semantic-refresh-2026-08-12",
    )
    if get_real_submission_count() > submissions_before:
        raise RuntimeError(f"SAFETY_VIOLATION: submission during refresh for {dom}")

    outcome, reason = _classify_refresh(row, fn, row)
    sem = fn.get("semantic_evidence") or {}
    elapsed = round(time.monotonic() - t0, 1)

    result = {
        "domain": dom,
        "company_name": row.get("company_name"),
        "candidate_id": row.get("candidate_id"),
        "form_url": row.get("form_url"),
        "historical_schema_version": evidence_schema_version(row),
        "refresh_outcome": outcome,
        "refresh_reason": reason,
        "semantic_evidence_schema_version": sem.get("semantic_evidence_schema_version"),
        "semantic_hash": sem.get("semantic_hash"),
        "field_map": fn.get("field_map"),
        "choice_categories": sorted(_choice_categories(fn.get("required_choices") or {})),
        "future_production_eligible": outcome == REFRESH_READY and dom not in CONFIRMED_SENT_DOMAINS,
        "already_confirmed_sent": dom in CONFIRMED_SENT_DOMAINS,
        "b01_divergence_historical": dom in B01_DIVERGENCE_DOMAINS,
        "b01_remaining_unprocessed": dom in B01_REMAINING,
        "elapsed_seconds": elapsed,
        "refreshed_at": datetime.now().isoformat(),
        "semantic_evidence_v2": sem,
        "historical_v1_preserved": True,
    }
    print(f"[{idx:02d}/{total}] {dom} -> {outcome} ({reason}) hash={sem.get('semantic_hash', '—')}", flush=True)
    return result


def assert_pre_run(population: list[dict]) -> dict:
    limits = load_limits(POOL_DATE)
    checks = {
        "auto_ready_count_49": len(population) == 49,
        "production_limit_0": limits.production_limit == 0,
        "production_enabled_false": not limits.production_enabled,
        "automation_paused": is_paused("form-auto-sender"),
        "effective_confirmed_sent_794": count_official_confirmed_sent() == EFFECTIVE_BASELINE,
    }
    set_submit_forbidden(True)
    checks["submit_forbidden"] = True
    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise RuntimeError(f"Pre-run FAIL CLOSED: {failed}")
    return {"passed": True, "checks": checks}


async def run_refresh(resume: bool = False) -> dict:
    population = _load_auto_ready_population()
    pre = assert_pre_run(population)
    reset_real_submission_count()
    clear_field_cache()

    state = load_checkpoint() if resume else None
    results: list[dict] = list((state or {}).get("results", {}).values()) if state else []
    done_domains = {r["domain"] for r in results}

    for i, row in enumerate(population, 1):
        dom = row.get("domain", "")
        if dom in done_domains:
            continue
        results.append(await _refresh_one(row, i, len(population)))
        save_checkpoint({"results": {r["domain"]: r for r in results}, "updated_at": datetime.now().isoformat()})

    oc = Counter(r["refresh_outcome"] for r in results)
    eligible_unsent = [r for r in results if not r.get("already_confirmed_sent")]
    refresh_ready = [r for r in eligible_unsent if r["refresh_outcome"] == REFRESH_READY]
    b01_rem = [r for r in results if r.get("b01_remaining_unprocessed")]
    b01_ready = [r for r in b01_rem if r["refresh_outcome"] == REFRESH_READY]

    prefecture = [r for r in results if "PREFECTURE" in (r.get("choice_categories") or [])]
    dynamic = [r for r in results if len(r.get("choice_categories") or []) > 0]

    report = {
        "report_id": "ARI-AUTO-READY-Semantic-Refresh-2026-08-12",
        "generated_at": datetime.now().isoformat(),
        "mode": "ZERO_SEND_SEMANTIC_REFRESH",
        "schema_version": SEMANTIC_EVIDENCE_SCHEMA_VERSION,
        "pre_run": pre,
        "population": {
            "source_auto_ready": 49,
            "processed": len(results),
            "confirmed_sent_in_population": sorted(CONFIRMED_SENT_DOMAINS),
        },
        "outcomes": dict(oc),
        "yield": {
            "refresh_ready": oc.get(REFRESH_READY, 0),
            "refresh_ready_over_original_49": round(100 * oc.get(REFRESH_READY, 0) / 49, 1),
            "refresh_ready_over_eligible_unsent": round(100 * len(refresh_ready) / max(1, len(eligible_unsent)), 1),
            "eligible_unsent_count": len(eligible_unsent),
        },
        "b01_remaining_6": {
            "total": len(b01_rem),
            "refresh_ready": len(b01_ready),
            "not_ready": len(b01_rem) - len(b01_ready),
            "domains": {r["domain"]: r["refresh_outcome"] for r in b01_rem},
        },
        "population_risk": {
            "prefecture_pattern": len(prefecture),
            "dynamic_choice_pattern": len(dynamic),
            "required_choice_variation_count": oc.get(REQUIRED_CHOICE_VARIATION, 0),
        },
        "safety": {
            "real_sends": get_real_submission_count(),
            "final_submit": 0,
            "effective_confirmed_sent": count_official_confirmed_sent(),
            "sent_csv_new_rows": 0,
        },
        "results": results,
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_md(report)
    return report


def _write_md(report: dict) -> None:
    oc = report.get("outcomes", {})
    lines = [
        "# ARI AUTO READY Semantic Refresh 2026-08-12",
        "",
        f"**Mode:** ZERO_SEND | **Schema:** v{SEMANTIC_EVIDENCE_SCHEMA_VERSION}",
        "",
        "## Population",
        "",
        f"- Source AUTO_READY: **49**",
        f"- Processed: **{report['population']['processed']}**",
        "",
        "## Outcomes",
        "",
        "| Outcome | Count |",
        "| --- | ---: |",
    ]
    for k, v in sorted(oc.items()):
        lines.append(f"| {k} | {v} |")
    y = report.get("yield", {})
    lines.extend([
        "",
        "## Yield",
        "",
        f"- REFRESH_READY / 49: **{y.get('refresh_ready_over_original_49')}%** ({y.get('refresh_ready', 0)}/49)",
        f"- REFRESH_READY / eligible unsent: **{y.get('refresh_ready_over_eligible_unsent')}%**",
        "",
        "## B01 Remaining 6",
        "",
        f"- REFRESH_READY: **{report['b01_remaining_6']['refresh_ready']}**",
        f"- Not ready: **{report['b01_remaining_6']['not_ready']}**",
        "",
        "## Safety",
        "",
        f"- REAL_SENDS: **{report['safety']['real_sends']}**",
        f"- EFFECTIVE_CONFIRMED_SENT: **{report['safety']['effective_confirmed_sent']}**",
    ])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not is_paused("form-auto-sender"):
        set_paused("form-auto-sender", True, by="run_ari_auto_ready_semantic_refresh.py")
    set_submit_forbidden(True)
    limits = load_limits(POOL_DATE)
    limits.production_limit = 0
    limits.production_enabled = False
    limits.save()
    report = asyncio.run(run_refresh(resume=args.resume))
    print(json.dumps({"outcomes": report["outcomes"], "yield": report["yield"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
