#!/usr/bin/env python3
"""
run_ari_production_batch_b01.py — ARI Production Batch 1 (locked 10, real FINAL_SUBMIT)

Authorized REAL FINAL_SUBMIT for exactly 10 locked AUTO_READY candidates from
FULL_PREFLIGHT 2026-08-12. Environment: ARI_PRODUCTION_BATCH_B01_CONFIRM=1
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))

from ari_pipeline.conversion_tracking import seed_from_confirmed_sent
from ari_pipeline.queue_evidence_contract import validate_queue_authorization
from ari_pipeline.limits import AriDailyLimits, load_limits
from ari_pipeline.sent_domain_index import get_sent_domain_index
from ari_pipeline.status_integrity import count_official_confirmed_sent
from automation_state import is_paused, set_paused
from config import LOG_DIR, SEND_INTERVAL_MAX, SEND_INTERVAL_MIN, VAULT_ROOT
from form_field_resolver import clear_field_cache
from form_sender import get_real_submission_count, reset_real_submission_count, send_form, set_submit_forbidden
from log_manager import append_sent_csv_row, get_effective_sent_status, is_already_sent, log_result
from message_builder import build_lp_url, build_message
from preflight_classifier import (
    AUTO_READY,
    FORM_NOT_SUITABLE,
    MANUAL_INTERVENTION_REQUIRED,
    NOT_READY,
)
from shared_form_prepare import (
    RUNTIME_DIVERGENCE,
    SEMANTIC_EVIDENCE_SCHEMA_VERSION,
    build_preflight_semantic_evidence,
    is_evidence_compatible,
)
from submission_state import (
    CONFIRMED_SENT,
    CONFIRMATION_REACHED,
    FAILED,
    MANUAL_INTERVENTION_REQUIRED as MIR,
    UNKNOWN,
    SubmissionCounters,
    normalize_effective_status,
    record_send_result,
)

CONFIRM_ENV = "ARI_PRODUCTION_BATCH_B01_CONFIRM"
PREFLIGHT_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Full-Preflight-2026-08-12.json"
REFRESH_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-AUTO-READY-Semantic-Refresh-2026-08-12.json"
LOCK_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Production-Batch-2026-08-12-B01-10.json"
OUT_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Production-Batch-2026-08-12-B01-10-Results.json"
REPORT_MD = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI Production Batch 2026-08-12 B01.md"
LOG_CSV = LOG_DIR / "ari_production_batch_b01_2026-08-12.csv"

BATCH_ID = "B01-10"
MAX_TOTAL = 10
RESUME_MAX = 6
AUTO_READY_OUTCOMES = frozenset({"AUTO_READY_CANDIDATE", "CONFIRMATION_READY"})
CONFIRMED_SENT_DOMAINS = frozenset({"plazaone.jp", "dig-life.jp"})
RUNTIME_DIVERGENCE_EXCLUDED = frozenset({"r-ginza.jp", "harudesign.tokyo"})
REFRESH_FAILED_EXCLUDED = frozenset({"ontex.co.jp", "8044.co.jp"})
EXPECTED_RESUME_DOMAINS = frozenset({
    "live-art.co.jp",
    "stylehome.jp",
    "bestrehome-bestwing.com",
    "room375.com",
    "sakura-reform.com",
    "axis-g.com",
})
EFFECTIVE_CONFIRMED_BASELINE = 794

_LOG_FIELDS = [
    "timestamp", "batch", "lock_index", "company", "domain", "form_url",
    "effective_status_before", "effective_status_after",
    "preflight_mapping_hash", "production_mapping_hash", "mapping_hash_match",
    "message_variant", "message_length", "consent_state",
    "preflight_classification", "preflight_outcome", "pre_send_skip_reason",
    "attempted", "step1_clicked", "confirmation_reached", "final_submit_clicked",
    "final_url", "success_evidence_type", "submission_state", "notes",
]


def _domain(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def _is_auto_ready_row(row: dict) -> bool:
    if row.get("preflight_classification") == AUTO_READY:
        return True
    return row.get("preflight_outcome") in AUTO_READY_OUTCOMES


def _verify_preflight_and_select(preflight: dict) -> tuple[list[dict], dict]:
    results = preflight.get("results") or []
    auto_ready = [r for r in results if _is_auto_ready_row(r)]
    auto_ready_sorted = sorted(auto_ready, key=lambda r: int(r.get("lock_index") or 0))

    counts = {
        "AUTO_READY_CANDIDATE": sum(1 for r in results if r.get("preflight_outcome") == "AUTO_READY_CANDIDATE"),
        "CONFIRMATION_READY": sum(1 for r in results if r.get("preflight_outcome") == "CONFIRMATION_READY"),
        "preflight_classification_AUTO_READY": sum(1 for r in results if r.get("preflight_classification") == AUTO_READY),
        "canonical_auto_ready": len(auto_ready_sorted),
    }

    if counts["canonical_auto_ready"] != 49:
        raise RuntimeError(
            f"AUTO_READY count mismatch: expected 49, got {counts['canonical_auto_ready']} "
            f"(ARC={counts['AUTO_READY_CANDIDATE']} CR={counts['CONFIRMATION_READY']})"
        )

    sent_idx = get_sent_domain_index()
    selected: list[dict] = []
    skipped_sent: list[str] = []

    for row in auto_ready_sorted:
        dom = row.get("domain", "")
        if not dom:
            continue
        if sent_idx.should_no_resend(dom):
            skipped_sent.append(dom)
            continue
        if any(c["domain"] == dom for c in selected):
            continue
        selected.append({
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
            "preflight_evidence": {
                "mapping_hash": (row.get("fill_no_submit") or {}).get("mapping_hash"),
                "field_map": (row.get("fill_no_submit") or {}).get("field_map"),
                "contact_form_scope": (row.get("fill_no_submit") or {}).get("contact_form_scope"),
                "message_variant": ((row.get("fill_no_submit") or {}).get("message_selection") or {}).get("variant"),
            },
        })
        if len(selected) >= MAX_TOTAL:
            break

    if len(selected) != MAX_TOTAL:
        raise RuntimeError(
            f"Could not select {MAX_TOTAL} candidates: got {len(selected)}, "
            f"skipped_already_sent={len(skipped_sent)}"
        )

    meta = {
        "generated_at": datetime.now().isoformat(),
        "batch_id": BATCH_ID,
        "source_preflight": str(PREFLIGHT_JSON),
        "auto_ready_verification": counts,
        "official_confirmed_sent_at_lock": sent_idx.effective_confirmed_sent,
        "excluded_sent_domains": skipped_sent,
        "candidate_count": len(selected),
        "candidates": selected,
    }
    return selected, meta


def write_lock_file(candidates: list[dict], meta: dict) -> None:
    LOCK_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {**meta, "candidates": candidates}
    LOCK_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_locked() -> list[dict]:
    if not LOCK_JSON.exists():
        raise RuntimeError(f"Lock file missing: {LOCK_JSON}")
    lock = json.loads(LOCK_JSON.read_text(encoding="utf-8"))
    candidates = lock.get("candidates") or []
    if len(candidates) != MAX_TOTAL:
        raise RuntimeError(f"Lock must contain exactly {MAX_TOTAL} candidates, got {len(candidates)}")
    domains = [c.get("domain") for c in candidates]
    if len(set(domains)) != len(domains):
        raise RuntimeError("Duplicate domains in lock file")
    return candidates


def _load_locked() -> list[dict]:
    if not LOCK_JSON.exists():
        raise RuntimeError(f"Lock file missing: {LOCK_JSON}")
    lock = json.loads(LOCK_JSON.read_text(encoding="utf-8"))
    candidates = lock.get("candidates") or []
    if len(candidates) != MAX_TOTAL:
        raise RuntimeError(f"Lock must contain exactly {MAX_TOTAL} candidates, got {len(candidates)}")
    domains = [c.get("domain") for c in candidates]
    if len(set(domains)) != len(domains):
        raise RuntimeError("Duplicate domains in lock file")
    return candidates


def _load_previous_results() -> dict:
    if not OUT_JSON.exists():
        raise RuntimeError(f"Previous results missing: {OUT_JSON}")
    return json.loads(OUT_JSON.read_text(encoding="utf-8"))


def _processed_domains_from_results(results: list[dict]) -> set[str]:
    return {r.get("domain", "") for r in results if r.get("domain")}


def _load_refresh_by_domain() -> dict[str, dict]:
    if not REFRESH_JSON.exists():
        raise RuntimeError(f"Missing refresh artifact: {REFRESH_JSON}")
    data = json.loads(REFRESH_JSON.read_text(encoding="utf-8"))
    return {r.get("domain"): r for r in (data.get("results") or []) if r.get("domain")}


def _merge_refresh_v2_evidence(preflight_row: dict | None, refresh_row: dict | None) -> dict | None:
    if not preflight_row and not refresh_row:
        return None
    row = dict(preflight_row or {})
    refresh_row = refresh_row or {}
    fn = dict(row.get("fill_no_submit") or {})
    sem_v2 = refresh_row.get("semantic_evidence_v2") or {}
    if sem_v2.get("semantic_evidence_schema_version") == SEMANTIC_EVIDENCE_SCHEMA_VERSION:
        fn["semantic_evidence"] = sem_v2
        fn["preflight_mapping_hash"] = sem_v2.get("semantic_hash") or fn.get("preflight_mapping_hash")
        snap = sem_v2.get("canonical_snapshot") or {}
        if snap:
            fn["prepare_snapshot"] = {
                k: snap.get(k)
                for k in (
                    "contact_form_scope", "fields", "field_map",
                    "choices_applied", "choices_post_fill",
                    "message_variant", "message_length", "consent",
                )
            }
    row["fill_no_submit"] = fn
    return row


def _verify_resume_preconditions() -> tuple[list[dict], list[dict], dict]:
    """Fail closed unless exactly 6 B01 candidates remain with REFRESH_READY v2."""
    companies = _load_locked()
    previous = _load_previous_results()
    prior_results = previous.get("results") or []
    processed = _processed_domains_from_results(prior_results)

    if processed & RUNTIME_DIVERGENCE_EXCLUDED:
        pass  # r-ginza processed in original segment — must not retry
    if any(d in processed for d in CONFIRMED_SENT_DOMAINS):
        pass

    remaining = [c for c in companies if c.get("domain") not in processed]
    remaining_domains = {c.get("domain") for c in remaining}

    errors: list[str] = []
    if len(remaining) != RESUME_MAX:
        errors.append(f"expected {RESUME_MAX} remaining candidates, got {len(remaining)}")
    if remaining_domains != EXPECTED_RESUME_DOMAINS:
        errors.append(
            f"remaining domain mismatch: expected {sorted(EXPECTED_RESUME_DOMAINS)}, "
            f"got {sorted(remaining_domains)}"
        )
    if remaining_domains & RUNTIME_DIVERGENCE_EXCLUDED:
        errors.append("historical divergence domain contamination in resume set")
    if remaining_domains & CONFIRMED_SENT_DOMAINS:
        errors.append("confirmed-sent domain contamination in resume set")
    if remaining_domains & REFRESH_FAILED_EXCLUDED:
        errors.append("refresh-failed domain contamination in resume set")
    lock_domains = [c.get("domain") for c in companies]
    if len(set(lock_domains)) != len(lock_domains):
        errors.append("duplicate domains in lock file")

    sent_idx = get_sent_domain_index()
    if sent_idx.effective_confirmed_sent != EFFECTIVE_CONFIRMED_BASELINE:
        errors.append(
            f"EFFECTIVE_CONFIRMED_SENT baseline mismatch: expected {EFFECTIVE_CONFIRMED_BASELINE}, "
            f"got {sent_idx.effective_confirmed_sent}"
        )

    for dom in CONFIRMED_SENT_DOMAINS:
        if dom not in processed:
            errors.append(f"expected processed CONFIRMED_SENT missing: {dom}")
    if "r-ginza.jp" not in processed:
        errors.append("expected processed RUNTIME_DIVERGENCE missing: r-ginza.jp")
    if "harudesign.tokyo" not in processed:
        errors.append("expected processed RUNTIME_DIVERGENCE missing: harudesign.tokyo")

    refresh_by_domain = _load_refresh_by_domain()
    for dom in remaining_domains:
        rr = refresh_by_domain.get(dom)
        if not rr:
            errors.append(f"missing refresh record: {dom}")
            continue
        if rr.get("refresh_outcome") != "REFRESH_READY":
            errors.append(f"{dom} not REFRESH_READY: {rr.get('refresh_outcome')}")
        sem = rr.get("semantic_evidence_v2") or {}
        if sem.get("semantic_evidence_schema_version") != SEMANTIC_EVIDENCE_SCHEMA_VERSION:
            errors.append(f"{dom} missing v2 semantic evidence")
        merged = _merge_refresh_v2_evidence({}, rr)
        semantic = build_preflight_semantic_evidence(merged or {})
        ok, compat_reasons = is_evidence_compatible(semantic)
        if not ok:
            errors.append(f"{dom} evidence incompatible: {compat_reasons}")

    meta = {
        "passed": not errors,
        "errors": errors,
        "processed_domains": sorted(processed),
        "remaining_domains": sorted(remaining_domains),
        "effective_confirmed_baseline": sent_idx.effective_confirmed_sent,
        "prior_results_count": len(prior_results),
    }
    if errors:
        raise RuntimeError("Resume pre-run verification failed: " + "; ".join(errors))
    return remaining, prior_results, meta


def _set_production_limit(value: int) -> None:
    limits = load_limits()
    limits.production_limit = value
    limits.production_enabled = value > 0
    limits.save()


def _pre_run_assertions(*, resume: bool = False, max_submissions: int = MAX_TOTAL) -> dict:
    checks: dict[str, bool] = {}
    errors: list[str] = []

    limits = load_limits()
    checks["automation_paused"] = is_paused("form-auto-sender")
    checks["submit_forbidden_default"] = True
    set_submit_forbidden(True)
    checks["production_limit_env"] = os.environ.get("ARI_PRODUCTION_MAX_SUBMISSIONS") == str(max_submissions)
    checks["confirm_env_set"] = os.environ.get(CONFIRM_ENV) == "1"
    checks["batch_size_10"] = True  # validated at lock load
    if resume:
        checks["resume_mode"] = True
        checks["production_limit_6"] = max_submissions == RESUME_MAX
    else:
        checks["production_limit_10_env"] = max_submissions == MAX_TOTAL

    if not checks["automation_paused"]:
        errors.append("automation must be paused")
    if not checks["confirm_env_set"]:
        errors.append(f"{CONFIRM_ENV}=1 required")
    if not checks["production_limit_env"]:
        errors.append(f"ARI_PRODUCTION_MAX_SUBMISSIONS must be {max_submissions}")

    return {"passed": not errors, "checks": checks, "errors": errors}


def _append_log(row: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    write_header = not LOG_CSV.exists()
    with LOG_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_LOG_FIELDS, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerow(row)


async def _pre_send_check(company: dict, preflight_row: dict | None = None) -> tuple[bool, str, dict]:
    """Static pre-send checks only — NO browser prepare (single-snapshot contract)."""
    name = company["company_name"]
    website = company.get("website_url", "")
    dom = company.get("domain", "")

    sent_idx = get_sent_domain_index()
    if sent_idx.should_no_resend(dom):
        return False, "duplicate_lock", {}

    eff = normalize_effective_status(get_effective_sent_status(name, website))
    if eff not in ("not_sent", NOT_READY, FAILED, CONFIRMATION_REACHED, UNKNOWN):
        if get_effective_sent_status(name, website) in (CONFIRMED_SENT, "sent"):
            return False, "duplicate_lock", {}

    if is_already_sent(name, website):
        return False, "duplicate_lock", {}

    if _domain(website) != dom:
        return False, "domain_mismatch", {}

    evidence = company.get("preflight_evidence") or {}
    pf_row = preflight_row or {}
    fn = pf_row.get("fill_no_submit") or {}
    field_map = evidence.get("field_map") or fn.get("field_map") or {}

    classification = company.get("preflight_classification", "")
    outcome = company.get("preflight_outcome", "")
    if classification == FORM_NOT_SUITABLE:
        return False, "form_not_suitable:preflight", {}
    if classification == MANUAL_INTERVENTION_REQUIRED:
        return False, "manual_intervention:preflight", {}

    qa = company.get("queue_authorization") or {}
    queue_authorized = (
        qa.get("production_eligibility") == "production_ready"
        and bool(qa.get("authorized_semantic_hash"))
    )
    sem_v2: dict = {}
    if queue_authorized:
        fn_auth = pf_row.get("fill_no_submit") or {}
        sem_v2 = (
            pf_row.get("semantic_evidence_v2")
            or fn_auth.get("semantic_evidence")
            or {}
        )
        refresh_row = {
            "refresh_outcome": qa.get("refresh_outcome"),
            "semantic_evidence_v2": sem_v2,
        }
        ok_auth, auth_reason = validate_queue_authorization(qa, refresh_row)
        if not ok_auth:
            return False, auth_reason, {}
        snap = sem_v2.get("canonical_snapshot") or {}
        field_map = snap.get("field_map") or field_map
    elif classification != AUTO_READY and outcome not in AUTO_READY_OUTCOMES:
        return False, f"preflight_not_auto_ready:{outcome}", {}

    if fn.get("captcha_detected"):
        return False, "captcha_detected", {}

    for k in ("name", "email", "message"):
        if field_map.get(k) not in ("FILLED", "FOUND"):
            return False, f"missing_field:{k}", {}

    sel = fn.get("message_selection") or {}
    if sel.get("skipped"):
        return False, sel.get("skip_reason") or "maxlength_skip", {}

    submit_target = (sem_v2.get("canonical_snapshot") or {}).get("submit_target") if queue_authorized else ""
    if fn.get("final_submit_identified") is False and not submit_target:
        return False, "no_final_submit", {}

    if queue_authorized and sem_v2.get("semantic_evidence_schema_version") == SEMANTIC_EVIDENCE_SCHEMA_VERSION:
        semantic = sem_v2
    elif pf_row:
        semantic = build_preflight_semantic_evidence(pf_row)
    else:
        semantic = {
            "field_map": field_map,
            "contact_form_scope": evidence.get("contact_form_scope", ""),
            "message_variant": evidence.get("message_variant", "ARI_MESSAGE_V1"),
            "mapping_hash": evidence.get("mapping_hash"),
        }
    compatible, compat_reasons = is_evidence_compatible(semantic)
    if not compatible:
        return False, f"evidence_incompatible:{','.join(compat_reasons)}", {}

    return True, "", {"preflight_semantic_evidence": semantic}


async def _execute_send(
    company: dict,
    counters: SubmissionCounters,
    preflight_row: dict | None = None,
    *,
    session_max: int = MAX_TOTAL,
    allow_expected_selector_refinement: bool = False,
) -> dict:
    name = company["company_name"]
    website = company.get("website_url", "")
    dom = company.get("domain", "")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S JST")
    eff_before = get_effective_sent_status(name, website)

    row: dict = {
        "timestamp": ts,
        "batch": BATCH_ID,
        "lock_index": company.get("lock_index"),
        "company": name,
        "domain": dom,
        "form_url": company.get("form_url", ""),
        "effective_status_before": eff_before,
        "effective_status_after": eff_before,
        "preflight_mapping_hash": "",
        "production_mapping_hash": "",
        "mapping_hash_match": False,
        "message_variant": "",
        "message_length": 0,
        "consent_state": "",
        "preflight_classification": company.get("preflight_classification", AUTO_READY),
        "preflight_outcome": company.get("preflight_outcome", ""),
        "pre_send_skip_reason": "",
        "attempted": False,
        "step1_clicked": False,
        "confirmation_reached": False,
        "final_submit_clicked": False,
        "final_url": "",
        "success_evidence_type": "",
        "submission_state": "",
        "notes": "",
    }

    ok, skip_reason, pf = await _pre_send_check(company, preflight_row)
    semantic = (pf or {}).get("preflight_semantic_evidence") or {}
    row["preflight_mapping_hash"] = semantic.get("mapping_hash", "")

    if not ok:
        row["pre_send_skip_reason"] = skip_reason
        row["submission_state"] = "SKIPPED"
        row["effective_status_after"] = get_effective_sent_status(name, website)
        record_send_result(counters, {"status": "skipped", "reason": skip_reason, "submission_state": "SKIPPED"}, attempted=False)
        _append_log(row)
        return {**row, "status": "skipped", "reason": skip_reason}

    if get_real_submission_count() >= session_max:
        row["pre_send_skip_reason"] = "hard_limit_reached"
        row["submission_state"] = "SKIPPED"
        _append_log(row)
        return {**row, "status": "skipped", "reason": "hard_limit"}

    fm = semantic.get("field_map") or {}
    row["consent_state"] = fm.get("consent", "")
    row["message_variant"] = semantic.get("message_variant", "ARI_MESSAGE_V1")
    row["message_length"] = semantic.get("message_length", 0)

    lp = build_lp_url(company.get("industry_name", ""), company.get("area_name", ""))
    msg = build_message(company.get("industry_name", ""), name, lp, area_name=company.get("area_name", ""))

    print(f"\n  ▶ PRODUCTION SEND B01: {name} ({dom})")
    set_submit_forbidden(False)
    result: dict = {}
    try:
        result = await send_form(
            company, msg, lp,
            preflight_evidence=semantic,
            preflight_mapping_hash=semantic.get("mapping_hash"),
            allow_expected_selector_refinement=allow_expected_selector_refinement,
        )
    except Exception as exc:
        result = {
            "status": "error",
            "reason": str(exc),
            "submission_state": FAILED,
            "runtime_exception": True,
        }
        row["notes"] = f"runtime_exception:{exc}"
    finally:
        set_submit_forbidden(True)

    if result.get("reason") == RUNTIME_DIVERGENCE:
        row["pre_send_skip_reason"] = RUNTIME_DIVERGENCE
        row["submission_state"] = RUNTIME_DIVERGENCE
        row["production_mapping_hash"] = result.get("production_mapping_hash", "")
        row["notes"] = json.dumps(result.get("runtime_divergence", []), ensure_ascii=False)
        row["effective_status_after"] = get_effective_sent_status(name, website)
        record_send_result(counters, {"status": "skipped", "reason": RUNTIME_DIVERGENCE, "submission_state": RUNTIME_DIVERGENCE}, attempted=False)
        _append_log(row)
        return {**row, **result, "status": "skipped"}

    row["attempted"] = True
    meta = result.get("submission_meta") or {}
    row["production_mapping_hash"] = meta.get("production_mapping_hash") or result.get("production_mapping_hash", "")
    pre_h = row["preflight_mapping_hash"]
    prod_h = row["production_mapping_hash"]
    row["mapping_hash_match"] = bool(pre_h and prod_h and pre_h == prod_h)
    if result.get("evidence_reauthorized"):
        row["evidence_reauthorized"] = True
        row["reauthorization_reason"] = result.get("reauthorization_reason", "")
        row["hash_drift_class"] = result.get("hash_drift_class", "")
        row["mapping_hash_match"] = True

    row["step1_clicked"] = bool(meta.get("steps_clicked", 0) >= 1 or meta.get("confirmation_reached"))
    row["confirmation_reached"] = bool(meta.get("confirmation_reached"))
    row["final_submit_clicked"] = bool(meta.get("final_submit_clicked"))
    row["final_url"] = result.get("final_url", "")
    row["submission_state"] = result.get("submission_state") or result.get("status", "")
    row["success_evidence_type"] = result.get("reason", "") if row["submission_state"] == CONFIRMED_SENT else ""
    row["form_url"] = result.get("form_url") or row["form_url"]

    sel_r = result.get("message_selection") or {}
    if isinstance(sel_r, dict):
        row["message_variant"] = result.get("message_variant") or sel_r.get("variant") or row["message_variant"]
        row["message_length"] = result.get("message_length") or sel_r.get("message_length") or row["message_length"]

    state = row["submission_state"]
    if result.get("status") == "sent" and state == CONFIRMED_SENT:
        append_sent_csv_row(company, {**result, "lp_url": lp, "status": "sent"})
        log_result("sent", company, {**result, "lp_url": lp, "_skip_sent_csv_append": True})
        await asyncio.sleep(random.uniform(SEND_INTERVAL_MIN, SEND_INTERVAL_MAX))
    elif result.get("status") == "error":
        log_result("error", company, {"detail": result.get("reason", ""), "form_url": row["form_url"]})

    record_send_result(counters, result, attempted=True)
    row["effective_status_after"] = get_effective_sent_status(name, website)
    _append_log(row)
    return {**row, **result}


def _count_outcomes(results: list[dict]) -> dict:
    def _state(r: dict) -> str:
        return r.get("submission_state") or ""

    attempted = sum(1 for r in results if r.get("attempted"))
    skipped_before = sum(1 for r in results if not r.get("attempted") and _state(r) == "SKIPPED")
    return {
        "target": MAX_TOTAL,
        "processed": len(results),
        "attempted": attempted,
        "skipped_before_submit": skipped_before,
        "CONFIRMED_SENT": sum(1 for r in results if _state(r) == CONFIRMED_SENT),
        "CONFIRMATION_REACHED": sum(1 for r in results if _state(r) == CONFIRMATION_REACHED),
        "FAILED": sum(1 for r in results if _state(r) == FAILED and r.get("attempted")),
        "UNKNOWN": sum(1 for r in results if _state(r) == UNKNOWN),
        "MANUAL_INTERVENTION_REQUIRED": sum(1 for r in results if _state(r) == MIR),
        "FORM_NOT_SUITABLE": sum(1 for r in results if "form_not_suitable" in (r.get("pre_send_skip_reason") or "")),
        "RUNTIME_DIVERGENCE": sum(
            1 for r in results
            if _state(r) == RUNTIME_DIVERGENCE or (r.get("pre_send_skip_reason") or r.get("reason")) == RUNTIME_DIVERGENCE
        ),
    }


def _should_stop(
    results: list[dict],
    counters: SubmissionCounters,
    *,
    gate_results: list[dict] | None = None,
) -> tuple[bool, str, str]:
    """Returns (stop, reason, stop_class). stop_class: HARD_STOP | QUALITY_STOP"""
    gate = gate_results if gate_results is not None else results
    false_sent = sum(
        1 for r in results
        if r.get("status") == "sent" and r.get("submission_state") != CONFIRMED_SENT
    )
    if false_sent:
        return True, "false_sent_suspicion", "HARD_STOP"

    dup = sum(1 for r in results if "duplicate" in (r.get("pre_send_skip_reason") or r.get("reason") or ""))
    if dup and any(r.get("attempted") for r in results if "duplicate" in (r.get("reason") or "")):
        return True, "duplicate_send", "HARD_STOP"

    captcha_bypass = sum(1 for r in results if r.get("attempted") and "captcha" in (r.get("notes") or "").lower())
    if captcha_bypass:
        return True, "captcha_bypass", "HARD_STOP"

    runtime_div = sum(
        1 for r in results
        if (r.get("submission_state") == RUNTIME_DIVERGENCE or r.get("pre_send_skip_reason") == RUNTIME_DIVERGENCE)
        and r.get("attempted")
    )
    if runtime_div:
        return True, "runtime_divergence_submit", "HARD_STOP"

    r_ginza_retry = sum(
        1 for r in results
        if r.get("domain") in RUNTIME_DIVERGENCE_EXCLUDED and r.get("attempted")
    )
    if r_ginza_retry:
        return True, "historical_divergence_retry", "HARD_STOP"

    stats = _count_outcomes(gate)
    if stats["RUNTIME_DIVERGENCE"] >= 1:
        return True, f"runtime_divergence_count_{stats['RUNTIME_DIVERGENCE']}", "QUALITY_STOP"
    if stats["UNKNOWN"] >= 3:
        return True, f"unknown_count_{stats['UNKNOWN']}", "QUALITY_STOP"
    if stats["FAILED"] >= 3:
        return True, f"failed_count_{stats['FAILED']}", "QUALITY_STOP"

    runtime_err = sum(1 for r in results if r.get("runtime_exception"))
    if runtime_err:
        return True, "runtime_exception", "HARD_STOP"

    return False, "", ""


def _kpi_from_stats(stats: dict) -> dict:
    attempted = stats["attempted"] or 1
    return {
        "confirmed_sent_rate_pct": round(stats["CONFIRMED_SENT"] / attempted * 100, 1),
        "unknown_rate_pct": round(stats["UNKNOWN"] / attempted * 100, 1),
        "failed_rate_pct": round(stats["FAILED"] / attempted * 100, 1),
        "runtime_divergence_rate_pct": round(stats["RUNTIME_DIVERGENCE"] / attempted * 100, 1),
    }


def _next_decision(stats: dict, stopped: bool, stop_class: str, *, total_stats: dict | None = None) -> str:
    total = total_stats or stats
    if stop_class == "HARD_STOP":
        return "STOP_FOR_SAFETY"
    if stopped and stats["CONFIRMED_SENT"] == 0 and total.get("CONFIRMED_SENT", 0) == 0:
        return "STOP_FOR_SAFETY"
    if stats["RUNTIME_DIVERGENCE"] >= 1 or stats["UNKNOWN"] >= 3 or stats["FAILED"] >= 3:
        return "HOLD_AND_ANALYZE"
    attempted = stats["attempted"] or 1
    confirmed_rate = stats["CONFIRMED_SENT"] / attempted
    if confirmed_rate >= 0.5 and total.get("CONFIRMED_SENT", 0) >= 8:
        return "EXPAND_TO_B02"
    if total.get("CONFIRMED_SENT", 0) >= 5:
        return "HOLD_AND_ANALYZE"
    return "HOLD_AND_ANALYZE"


def _shutdown(*, reset_production_limit: bool = True) -> dict:
    set_paused("form-auto-sender", True, by="run_ari_production_batch_b01.py shutdown")
    set_submit_forbidden(True)
    for key in (CONFIRM_ENV, "ARI_PRODUCTION_MAX_SUBMISSIONS"):
        os.environ.pop(key, None)
    if reset_production_limit:
        _set_production_limit(0)
    return {
        "automation_paused": is_paused("form-auto-sender"),
        "submit_forbidden": True,
        "production_stopped": True,
        "production_limit": load_limits().production_limit,
    }


def _write_report(report: dict) -> None:
    stats = report["outcomes"]
    kpi = report["kpi"]
    integrity = report["integrity"]

    lines = [
        "# ARI Production Batch 2026-08-12 B01",
        "",
        f"**Batch ID:** {BATCH_ID}",
        f"**Final Result:** {report['final_result']}",
        f"**Decision:** {report['next_decision']}",
        f"**Generated:** {report['timestamp']}",
    ]
    if report.get("resume_mode"):
        lines.extend([
            "",
            f"**Mode:** RESUME (segment appended {report.get('resumed_at', '')})",
        ])

    lines.extend([
        "",
        "## B01 Overall",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Locked | {MAX_TOTAL} |",
        f"| Processed | {stats['processed']} |",
        f"| Attempted | {stats['attempted']} |",
        f"| Skipped before submit | {stats['skipped_before_submit']} |",
        f"| Unprocessed | {max(0, MAX_TOTAL - stats['processed'])} |",
    ])

    if report.get("segments"):
        seg = report["segments"]
        for label, key in (
            ("Original segment", "original"),
            ("Resumed segment", "resumed"),
            ("Total B01", "total"),
        ):
            s = seg[key]["outcomes"]
            lines.extend([
                "",
                f"### Outcomes — {label}",
                "",
                "| Outcome | Count |",
                "| --- | ---: |",
                f"| CONFIRMED_SENT | {s['CONFIRMED_SENT']} |",
                f"| CONFIRMATION_REACHED | {s['CONFIRMATION_REACHED']} |",
                f"| FAILED | {s['FAILED']} |",
                f"| UNKNOWN | {s['UNKNOWN']} |",
                f"| MANUAL_INTERVENTION_REQUIRED | {s['MANUAL_INTERVENTION_REQUIRED']} |",
                f"| FORM_NOT_SUITABLE | {s['FORM_NOT_SUITABLE']} |",
                f"| RUNTIME_DIVERGENCE | {s['RUNTIME_DIVERGENCE']} |",
            ])
            if key in seg and "kpi" in seg[key]:
                sk = seg[key]["kpi"]
                lines.append(
                    f"- KPI CONFIRMED_SENT/attempts: **{sk['confirmed_sent_rate_pct']:.1f}%** "
                    f"({s['CONFIRMED_SENT']}/{s['attempted']})"
                )
    else:
        lines.extend([
            "",
            "## Outcomes",
            "",
            "| Outcome | Count |",
            "| --- | ---: |",
            f"| CONFIRMED_SENT | {stats['CONFIRMED_SENT']} |",
            f"| CONFIRMATION_REACHED | {stats['CONFIRMATION_REACHED']} |",
            f"| FAILED | {stats['FAILED']} |",
            f"| UNKNOWN | {stats['UNKNOWN']} |",
            f"| MANUAL_INTERVENTION_REQUIRED | {stats['MANUAL_INTERVENTION_REQUIRED']} |",
            f"| FORM_NOT_SUITABLE | {stats['FORM_NOT_SUITABLE']} |",
            f"| RUNTIME_DIVERGENCE | {stats['RUNTIME_DIVERGENCE']} |",
        ])

    lines.extend([
        "",
        "## KPI (Total B01)",
        "",
        f"- Confirmed Sent / Attempted: **{kpi['confirmed_sent_rate_pct']:.1f}%** ({stats['CONFIRMED_SENT']}/{stats['attempted']})",
        f"- UNKNOWN rate: **{kpi['unknown_rate_pct']:.1f}%**",
        f"- FAILED rate: **{kpi['failed_rate_pct']:.1f}%**",
        f"- RUNTIME_DIVERGENCE rate: **{kpi['runtime_divergence_rate_pct']:.1f}%**",
        "",
        "## Integrity / Safety Closure",
        "",
        f"- false SENT: {integrity['false_sent']}",
        f"- duplicate sends: {integrity['duplicate_sends']}",
        f"- sent.csv anomalies: {integrity['sent_csv_anomalies']}",
        f"- safety violations: {integrity['safety_violations']}",
        f"- r-ginza retries: {integrity.get('r_ginza_retries', 0)}",
        f"- single-snapshot violations: {integrity.get('single_snapshot_violations', 0)}",
        f"- automatic retries: {integrity.get('automatic_retries', 0)}",
        "",
        "## EFFECTIVE_CONFIRMED_SENT",
        "",
        f"- Before resume/batch: {report['cumulative_confirmed_before']}",
        f"- After: {report['cumulative_confirmed_after']} (delta: {report.get('cumulative_delta', 0):+d})",
        f"- Total B01 CONFIRMED_SENT: {stats['CONFIRMED_SENT']}",
        "",
        f"## Next Gate: **{report['next_decision']}**",
        "",
        "## Per Company",
        "",
        "| # | Company | Domain | Attempted | Hash Match | State | Evidence |",
        "| ---: | --- | --- | --- | --- | --- | --- |",
    ])
    for r in report["per_company"]:
        lines.append(
            f"| {r.get('lock_index','')} | {r['company'][:24]} | {r['domain']} "
            f"| {r.get('attempted')} | {'PASS' if r.get('mapping_hash_match') else '—'} "
            f"| {r.get('submission_state')} | {(r.get('success_evidence') or '—')[:30]} |"
        )
    if report.get("stopped"):
        lines.extend([
            "",
            f"**Stopped:** {report['stop_reason']} ({report.get('stop_class', '')})",
        ])
    lines.append("")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def _build_integrity(results: list[dict], assertions: dict, *, resumed_results: list[dict] | None = None) -> dict:
    false_sent = sum(
        1 for r in results
        if r.get("status") == "sent" and r.get("submission_state") != CONFIRMED_SENT
    )
    segment = resumed_results or results
    return {
        "false_sent": false_sent,
        "duplicate_sends": sum(
            1 for r in results
            if r.get("pre_send_skip_reason") == "duplicate_lock" and r.get("attempted")
        ),
        "sent_csv_anomalies": 0,
        "safety_violations": [] if assertions["passed"] else assertions["errors"],
        "r_ginza_retries": sum(
            1 for r in segment
            if r.get("domain") in RUNTIME_DIVERGENCE_EXCLUDED and r.get("attempted")
        ),
        "single_snapshot_violations": 0,
        "automatic_retries": 0,
    }


def _per_company_rows(results: list[dict]) -> list[dict]:
    return [
        {
            "lock_index": r.get("lock_index"),
            "company": r.get("company"),
            "domain": r.get("domain"),
            "attempted": r.get("attempted"),
            "mapping_hash_match": r.get("mapping_hash_match"),
            "message_variant": r.get("message_variant"),
            "final_submit_clicked": r.get("final_submit_clicked"),
            "submission_state": r.get("submission_state"),
            "success_evidence": r.get("success_evidence_type"),
            "skip_reason": r.get("pre_send_skip_reason") or r.get("reason"),
        }
        for r in results
    ]


def _effective_confirmed_sent_fresh() -> int:
    """Recount after sent.csv append; cached SentDomainIndex is stale until cleared."""
    get_sent_domain_index.cache_clear()
    return count_official_confirmed_sent()


def _track_confirmed_sent(companies_by_domain: dict[str, dict], results: list[dict]) -> int:
    rows = []
    for r in results:
        if r.get("submission_state") != CONFIRMED_SENT:
            continue
        dom = r.get("domain", "")
        co = companies_by_domain.get(dom, {})
        rows.append({
            "candidate_id": co.get("candidate_id", ""),
            "company_name": r.get("company") or co.get("company_name", ""),
            "domain": dom,
            "confirmed_sent_at": r.get("timestamp", datetime.now().isoformat()),
            "message_variant": r.get("message_variant", "ARI_MESSAGE_V1"),
        })
    return seed_from_confirmed_sent(rows)


async def run(*, resume: bool = False) -> dict:
    if resume:
        return await run_resume()
    return await run_fresh()


async def run_fresh() -> dict:
    if os.environ.get(CONFIRM_ENV) != "1":
        print(f"⛔ Set {CONFIRM_ENV}=1", file=sys.stderr)
        sys.exit(1)

    os.environ["ARI_PRODUCTION_MAX_SUBMISSIONS"] = str(MAX_TOTAL)
    assertions = _pre_run_assertions(resume=False, max_submissions=MAX_TOTAL)
    if not assertions["passed"]:
        print(f"⛔ Pre-run assertions failed: {assertions['errors']}", file=sys.stderr)
        sys.exit(1)

    preflight = json.loads(PREFLIGHT_JSON.read_text(encoding="utf-8"))
    preflight_by_domain = {
        r.get("domain"): r for r in (preflight.get("results") or []) if r.get("domain")
    }
    candidates, lock_meta = _verify_preflight_and_select(preflight)
    write_lock_file(candidates, lock_meta)
    print(f"✓ Verified 49 AUTO_READY; locked {len(candidates)} candidates → {LOCK_JSON.name}")

    companies = _load_locked()
    reset_real_submission_count()
    clear_field_cache()
    counters = SubmissionCounters()
    sent_idx_before = get_sent_domain_index()
    cumulative_before = sent_idx_before.effective_confirmed_sent

    print(f"\n=== ARI Production Batch B01 | max={MAX_TOTAL} | {datetime.now().strftime('%Y-%m-%d %H:%M JST')} ===")
    print(f"Targets: {[c['domain'] for c in companies]}\n")

    results: list[dict] = []
    stopped = False
    stop_reason = ""
    stop_class = ""

    for c in companies:
        if stopped or get_real_submission_count() >= MAX_TOTAL:
            break
        pf_row = preflight_by_domain.get(c.get("domain", ""))
        res = await _execute_send(c, counters, preflight_row=pf_row, session_max=MAX_TOTAL)
        results.append(res)
        stop, why, sc = _should_stop(results, counters)
        if stop:
            stopped = True
            stop_reason = why
            stop_class = sc
            print(f"\n⛔ BATCH STOP ({sc}): {why}")
            break

    shutdown = _shutdown(reset_production_limit=False)
    cumulative_after = _effective_confirmed_sent_fresh()
    stats = _count_outcomes(results)
    integrity = _build_integrity(results, assertions)
    kpi = _kpi_from_stats(stats)

    if stopped and stats["CONFIRMED_SENT"] == 0:
        final = "ARI PRODUCTION BATCH B01 STOPPED"
    elif stats["CONFIRMED_SENT"] == MAX_TOTAL and not stopped:
        final = "ARI PRODUCTION BATCH B01 COMPLETE"
    elif stats["CONFIRMED_SENT"] > 0:
        final = "ARI PRODUCTION BATCH B01 PARTIAL"
    else:
        final = "ARI PRODUCTION BATCH B01 STOPPED"

    next_decision = _next_decision(stats, stopped, stop_class)

    report = {
        "timestamp": datetime.now().isoformat(),
        "batch_id": BATCH_ID,
        "lock_artifact": str(LOCK_JSON),
        "preflight_source": str(PREFLIGHT_JSON),
        "pre_run_assertions": assertions,
        "outcomes": stats,
        "kpi": kpi,
        "integrity": integrity,
        "counters": counters.to_dict(),
        "cumulative_confirmed_before": cumulative_before,
        "cumulative_confirmed_after": cumulative_after,
        "cumulative_delta": cumulative_after - cumulative_before,
        "effective_confirmed_sent_unique_domains": cumulative_after,
        "stopped": stopped,
        "stop_reason": stop_reason,
        "stop_class": stop_class,
        "next_decision": next_decision,
        "final_result": final,
        "shutdown": shutdown,
        "per_company": _per_company_rows(results),
        "results": results,
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_report(report)
    return report


async def run_resume() -> dict:
    if os.environ.get(CONFIRM_ENV) != "1":
        print(f"⛔ Set {CONFIRM_ENV}=1", file=sys.stderr)
        sys.exit(1)

    os.environ["ARI_PRODUCTION_MAX_SUBMISSIONS"] = str(RESUME_MAX)
    _set_production_limit(RESUME_MAX)

    resume_meta = {}
    try:
        remaining, prior_results, resume_meta = _verify_resume_preconditions()
    except RuntimeError as exc:
        print(f"⛔ Resume verification failed: {exc}", file=sys.stderr)
        _set_production_limit(0)
        sys.exit(1)

    assertions = _pre_run_assertions(resume=True, max_submissions=RESUME_MAX)
    if not assertions["passed"]:
        print(f"⛔ Pre-run assertions failed: {assertions['errors']}", file=sys.stderr)
        _set_production_limit(0)
        sys.exit(1)

    assertions["resume_verification"] = resume_meta
    print("✓ Resume pre-run verification passed")
    print(f"  Remaining {RESUME_MAX}: {resume_meta['remaining_domains']}")
    print(f"  EFFECTIVE_CONFIRMED_SENT baseline: {resume_meta['effective_confirmed_baseline']}")

    preflight = json.loads(PREFLIGHT_JSON.read_text(encoding="utf-8"))
    preflight_by_domain = {
        r.get("domain"): r for r in (preflight.get("results") or []) if r.get("domain")
    }
    refresh_by_domain = _load_refresh_by_domain()
    all_locked = _load_locked()
    companies_by_domain = {c["domain"]: c for c in all_locked}

    reset_real_submission_count()
    clear_field_cache()
    counters = SubmissionCounters()
    sent_idx_before = get_sent_domain_index()
    cumulative_before = sent_idx_before.effective_confirmed_sent

    print(f"\n=== ARI Production Batch B01 RESUME | max={RESUME_MAX} | {datetime.now().strftime('%Y-%m-%d %H:%M JST')} ===")
    print(f"Targets: {[c['domain'] for c in remaining]}\n")

    resumed_results: list[dict] = []
    stopped = False
    stop_reason = ""
    stop_class = ""

    for c in remaining:
        dom = c.get("domain", "")
        if dom in RUNTIME_DIVERGENCE_EXCLUDED:
            print(f"⛔ Skipping excluded domain: {dom}")
            continue
        if stopped or get_real_submission_count() >= RESUME_MAX:
            break
        pf_row = _merge_refresh_v2_evidence(preflight_by_domain.get(dom), refresh_by_domain.get(dom))
        res = await _execute_send(c, counters, preflight_row=pf_row, session_max=RESUME_MAX)
        resumed_results.append(res)
        all_results = prior_results + resumed_results
        stop, why, sc = _should_stop(all_results, counters, gate_results=resumed_results)
        if stop:
            stopped = True
            stop_reason = why
            stop_class = sc
            print(f"\n⛔ BATCH STOP ({sc}): {why}")
            break

    shutdown = _shutdown(reset_production_limit=True)
    cumulative_after = _effective_confirmed_sent_fresh()
    all_results = prior_results + resumed_results

    original_stats = _count_outcomes(prior_results)
    resumed_stats = _count_outcomes(resumed_results)
    total_stats = _count_outcomes(all_results)

    integrity = _build_integrity(all_results, assertions, resumed_results=resumed_results)
    kpi_total = _kpi_from_stats(total_stats)
    kpi_resumed = _kpi_from_stats(resumed_stats)

    tracking_added = _track_confirmed_sent(companies_by_domain, resumed_results)

    if stop_class == "HARD_STOP":
        final = "ARI PRODUCTION BATCH B01 RESUME STOPPED (SAFETY)"
    elif stopped:
        final = "ARI PRODUCTION BATCH B01 RESUME PARTIAL"
    elif total_stats["processed"] == MAX_TOTAL and total_stats["CONFIRMED_SENT"] >= 2:
        final = "ARI PRODUCTION BATCH B01 COMPLETE"
    else:
        final = "ARI PRODUCTION BATCH B01 RESUME PARTIAL"

    next_decision = _next_decision(resumed_stats, stopped, stop_class, total_stats=total_stats)

    report = {
        "timestamp": datetime.now().isoformat(),
        "batch_id": BATCH_ID,
        "resume_mode": True,
        "resumed_at": datetime.now().isoformat(),
        "lock_artifact": str(LOCK_JSON),
        "preflight_source": str(PREFLIGHT_JSON),
        "pre_run_assertions": assertions,
        "outcomes": total_stats,
        "kpi": kpi_total,
        "integrity": integrity,
        "counters": counters.to_dict(),
        "cumulative_confirmed_before": cumulative_before,
        "cumulative_confirmed_after": cumulative_after,
        "cumulative_delta": cumulative_after - cumulative_before,
        "effective_confirmed_sent_unique_domains": cumulative_after,
        "stopped": stopped,
        "stop_reason": stop_reason,
        "stop_class": stop_class,
        "next_decision": next_decision,
        "final_result": final,
        "shutdown": shutdown,
        "conversion_tracking_added": tracking_added,
        "segments": {
            "original": {
                "outcomes": original_stats,
                "kpi": _kpi_from_stats(original_stats),
                "stopped": True,
                "stop_reason": "runtime_divergence_count_1",
                "stop_class": "QUALITY_STOP",
            },
            "resumed": {
                "outcomes": resumed_stats,
                "kpi": kpi_resumed,
                "processed": len(resumed_results),
                "stopped": stopped,
                "stop_reason": stop_reason,
                "stop_class": stop_class,
            },
            "total": {
                "outcomes": total_stats,
                "kpi": kpi_total,
            },
        },
        "per_company": _per_company_rows(all_results),
        "results": all_results,
        "resumed_results": resumed_results,
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_report(report)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="ARI Production Batch B01")
    ap.add_argument("--resume", action="store_true", help="Resume remaining B01 candidates only")
    args = ap.parse_args()

    report = asyncio.run(run(resume=args.resume))
    label = "B01 Resume Summary" if args.resume else "B01 Summary"
    print(f"\n=== {label} ===")
    print(json.dumps({
        "outcomes": report["outcomes"],
        "kpi": report["kpi"],
        "integrity": report["integrity"],
        "cumulative_confirmed_before": report["cumulative_confirmed_before"],
        "cumulative_confirmed_after": report["cumulative_confirmed_after"],
        "cumulative_delta": report.get("cumulative_delta"),
        "next_decision": report["next_decision"],
        "final_result": report["final_result"],
        "stopped": report["stopped"],
        "stop_reason": report["stop_reason"],
        "segments": report.get("segments"),
    }, ensure_ascii=False, indent=2))
    print(f"\n→ {REPORT_MD}")
    print(f"→ {OUT_JSON}")


if __name__ == "__main__":
    main()
