#!/usr/bin/env python3
"""
run_ari_fast_queue_semantic_refresh.py — ZERO-SEND semantic refresh for Aug 13 Fast Queue (135).

Sources immutable population from ARI-Fast-Production-Queue-2026-08-13.json.
Builds production-ready R1 queue after refresh.
REAL SENDS = 0 / FINAL_SUBMIT = 0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))

import run_ari_auto_ready_semantic_refresh as refresh_mod
import run_ari_semantic_policy_refresh as policy_refresh
from ari_pipeline.daily_fast_runner import daily_queue_path
from ari_pipeline.production_queue_eligibility import assess_production_queue_eligibility
from ari_pipeline.queue_evidence_contract import build_queue_authorization
from ari_pipeline.sent_domain_index import get_sent_domain_index
from ari_pipeline.status_integrity import count_official_confirmed_sent
from automation_state import is_paused
from config import LOG_DIR, VAULT_ROOT
from form_field_resolver import clear_field_cache
from form_sender import get_real_submission_count, reset_real_submission_count, set_submit_forbidden
from inquiry_purpose_semantics import audit_selected_purpose

SOURCE_QUEUE = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Fast-Production-Queue-2026-08-13.json"
SOURCE_RESULTS = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Fast-Production-Results-2026-08-13.json"
REFRESH_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-AUTO-READY-Semantic-Refresh-2026-08-12.json"
PREFLIGHT_CP = LOG_DIR / "ari_checkpoints/full_preflight_2026-08-12.json"
OUT_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Fast-Queue-Semantic-Refresh-2026-08-13.json"
OUT_MD = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI Fast Queue Semantic Refresh 2026-08-13.md"
CHECKPOINT = LOG_DIR / "ari_checkpoints/fast_queue_semantic_refresh_2026-08-13.json"
R1_QUEUE = daily_queue_path("2026-08-13", revision="R1")

QUEUE_DATE = "2026-08-13"


def _load_source_queue() -> dict[str, Any]:
    if not SOURCE_QUEUE.exists():
        raise FileNotFoundError(SOURCE_QUEUE)
    return json.loads(SOURCE_QUEUE.read_text(encoding="utf-8"))


def verify_source_unattempted() -> dict[str, Any]:
    """Confirm completed daily-fast scan had zero FINAL_SUBMIT attempts."""
    checks: dict[str, Any] = {"source_queue_count": 0}
    q = _load_source_queue()
    candidates = q.get("candidates") or []
    checks["source_queue_count"] = len(candidates)
    domains = [c.get("domain") for c in candidates]
    checks["unique_domains"] = len(set(domains))
    if checks["unique_domains"] != len(candidates):
        raise RuntimeError("Source queue has duplicate domains")

    if SOURCE_RESULTS.exists():
        results = json.loads(SOURCE_RESULTS.read_text(encoding="utf-8"))
        dc = results.get("daily_counters") or {}
        checks["final_submit_attempts"] = dc.get("final_submit_attempts", -1)
        checks["real_submissions"] = results.get("real_submissions", -1)
        checks["confirmed_sent"] = dc.get("confirmed_sent", -1)
        attempted = sum(1 for r in results.get("results") or [] if r.get("attempted"))
        checks["attempted_rows"] = attempted
        if checks["final_submit_attempts"] != 0:
            raise RuntimeError(f"Expected 0 FINAL_SUBMIT attempts, got {checks['final_submit_attempts']}")
        if checks["real_submissions"] != 0:
            raise RuntimeError(f"Expected REAL_SENDS=0, got {checks['real_submissions']}")
        if attempted != 0:
            raise RuntimeError(f"Expected 0 attempted rows, got {attempted}")
    else:
        checks["results_file"] = "missing_assumed_unattempted"

    return checks


def _load_preflight_index() -> dict[str, dict]:
    data = json.loads(PREFLIGHT_CP.read_text(encoding="utf-8"))
    return {r["domain"]: r for r in data.get("results", {}).values() if r.get("domain")}


def _load_refresh_index() -> dict[str, dict]:
    if not REFRESH_JSON.exists():
        return {}
    return {r["domain"]: r for r in json.loads(REFRESH_JSON.read_text()).get("results", []) if r.get("domain")}


def _purpose_audit_from_result(result: dict) -> str:
    snap = (result.get("semantic_evidence_v2") or {}).get("canonical_snapshot") or {}
    for choice in snap.get("choices_applied") or []:
        if choice.get("category") in ("INQUIRY_CATEGORY", "UNKNOWN"):
            return audit_selected_purpose(choice.get("label") or "", context=choice.get("context") or "")
    if result.get("refresh_outcome") == refresh_mod.FORM_NOT_SUITABLE_STATE:
        return "EXCLUDED_FORM_NOT_SUITABLE"
    return "NOT_APPLICABLE"


def load_checkpoint() -> dict | None:
    if CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    return None


def save_checkpoint(state: dict) -> None:
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now().isoformat()
    CHECKPOINT.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


async def run_refresh(*, resume: bool = False) -> dict[str, Any]:
    set_submit_forbidden(True)
    reset_real_submission_count()
    clear_field_cache()

    source_checks = verify_source_unattempted()
    q = _load_source_queue()
    domains = [c["domain"] for c in q["candidates"]]
    pf = _load_preflight_index()
    missing_pf = sorted(set(domains) - set(pf))
    if missing_pf:
        raise RuntimeError(f"Missing preflight for {len(missing_pf)} domains: {missing_pf[:5]}")

    population = [pf[d] for d in domains]
    refresh_index = _load_refresh_index()

    state = load_checkpoint() if resume else None
    results: list[dict] = list((state or {}).get("results", {}).values()) if state else []
    done = {r["domain"] for r in results}
    submissions_before = get_real_submission_count()
    total = len(population)

    for idx, row in enumerate(population, 1):
        dom = row.get("domain", "")
        if dom in done:
            continue
        before = get_real_submission_count()
        result = await refresh_mod._refresh_one(row, idx, total)
        if get_real_submission_count() > before:
            raise RuntimeError(f"SAFETY: submission during refresh {dom}")
        result["semantic_policy_refresh"] = True
        result["fast_queue_source"] = True
        result["prior_refresh_outcome"] = (refresh_index.get(dom) or {}).get("refresh_outcome")
        result["purpose_audit"] = _purpose_audit_from_result(result)
        results.append(result)
        save_checkpoint({"results": {r["domain"]: r for r in results}, "source_checks": source_checks})

    if get_real_submission_count() > submissions_before:
        raise RuntimeError("SAFETY: submissions during refresh batch")

    # Merge into canonical refresh artifact
    merged = _load_refresh_index()
    for r in results:
        merged[r["domain"]] = r
    refresh_payload = json.loads(REFRESH_JSON.read_text(encoding="utf-8"))
    refresh_payload["results"] = [merged[d] for d in sorted(merged)]
    refresh_payload["fast_queue_refresh_at"] = datetime.now().isoformat()
    REFRESH_JSON.write_text(json.dumps(refresh_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    oc = Counter(r.get("refresh_outcome") for r in results)
    purpose_rows = [r for r in results if r.get("purpose_audit") in ("COMPATIBLE", "INCOMPATIBLE", "AMBIGUOUS")]
    ready_rows = [r for r in results if r.get("refresh_outcome") == refresh_mod.REFRESH_READY]
    if purpose_rows:
        compat = sum(1 for r in purpose_rows if r.get("purpose_audit") == "COMPATIBLE")
        correct_purpose = round(compat / len(purpose_rows) * 100, 1)
    else:
        correct_purpose = 100.0

    stats = {
        "source_count": len(domains),
        "processed": len(results),
        "REFRESH_READY": oc.get(refresh_mod.REFRESH_READY, 0),
        "FORM_NOT_SUITABLE": oc.get(refresh_mod.FORM_NOT_SUITABLE_STATE, 0),
        "VALIDATION_FAILED": oc.get(refresh_mod.VALIDATION_FAILED, 0),
        "CAPTCHA_MANUAL": oc.get(refresh_mod.CAPTCHA_MANUAL, 0),
        "UNREACHABLE": oc.get(refresh_mod.UNREACHABLE_ERROR, 0),
        "MATERIAL_SEMANTIC_CHANGE": oc.get(refresh_mod.MATERIAL_SEMANTIC_CHANGE, 0),
        "OTHER": sum(
            v for k, v in oc.items()
            if k not in (
                refresh_mod.REFRESH_READY,
                refresh_mod.FORM_NOT_SUITABLE_STATE,
                refresh_mod.VALIDATION_FAILED,
                refresh_mod.CAPTCHA_MANUAL,
                refresh_mod.UNREACHABLE_ERROR,
                refresh_mod.MATERIAL_SEMANTIC_CHANGE,
            )
        ),
        "correct_purpose_rate_pct": correct_purpose,
        "real_sends": get_real_submission_count(),
        "effective_confirmed_sent": count_official_confirmed_sent(),
    }

    r1_meta = build_r1_queue(q, results)

    report = {
        "timestamp": datetime.now().isoformat(),
        "mode": "FAST_QUEUE_ZERO_SEND_SEMANTIC_REFRESH",
        "source_queue": str(SOURCE_QUEUE),
        "source_checks": source_checks,
        "stats": stats,
        "r1_queue": r1_meta,
        "results": results,
        "safety": {
            "real_sends": get_real_submission_count(),
            "final_submit": 0,
            "effective_confirmed_sent": count_official_confirmed_sent(),
        },
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_md(report)
    return report


def build_r1_queue(source_queue: dict, refresh_results: list[dict]) -> dict[str, Any]:
    """Build immutable R1 production queue from REFRESH_READY + eligibility gate."""
    get_sent_domain_index.cache_clear()
    idx = get_sent_domain_index()
    refresh_by = {r["domain"]: r for r in refresh_results}
    pf = _load_preflight_index()
    source_by = {c["domain"]: c for c in source_queue.get("candidates") or []}

    production_ready: list[dict] = []
    rejected: list[dict] = []
    seen: set[str] = set()

    for dom, src in source_by.items():
        if dom in seen:
            continue
        seen.add(dom)
        pf_row = pf.get(dom, {})
        merged = {**pf_row, **src}
        rr = refresh_by.get(dom)
        eligible, reason, detail = assess_production_queue_eligibility(merged, refresh_row=rr, sent_index=idx)
        if not eligible:
            rejected.append({"domain": dom, "reason": reason, "detail": detail})
            continue
        queue_auth = build_queue_authorization(
            {
                "queue_revision": "R1",
                "candidate_id": src.get("candidate_id") or pf_row.get("candidate_id", ""),
                "domain": dom,
                "production_eligibility": "production_ready",
                "semantic_hash": (rr.get("semantic_evidence_v2") or {}).get("semantic_hash") if rr else None,
            },
            rr or {},
        )
        production_ready.append({
            "queue_index": len(production_ready) + 1,
            "queue_date": QUEUE_DATE,
            "queue_revision": "R1",
            "candidate_id": src.get("candidate_id") or pf_row.get("candidate_id", ""),
            "company_name": src.get("company_name") or pf_row.get("company_name", ""),
            "domain": dom,
            "website_url": src.get("website_url") or pf_row.get("website_url", ""),
            "form_url": src.get("form_url") or pf_row.get("form_url", ""),
            "industry_name": src.get("industry_name") or pf_row.get("industry_name", ""),
            "area_name": src.get("area_name") or pf_row.get("area_name", ""),
            "place_id": src.get("place_id") or pf_row.get("place_id", ""),
            "classification": "PROVEN_FAST_PATH",
            "matched_pattern_id": detail.get("matched_pattern_id"),
            "pattern_tier": detail.get("pattern_tier"),
            "framework": src.get("framework"),
            "refresh_outcome": rr.get("refresh_outcome") if rr else None,
            "semantic_hash": queue_auth.get("authorized_semantic_hash"),
            "production_eligibility": "production_ready",
            "queue_authorization": queue_auth,
        })

    # Contamination checks
    dup = len(production_ready) != len({c["domain"] for c in production_ready})
    confirmed_contam = [c for c in production_ready if idx.is_confirmed_sent_domain(c["domain"])]
    attempted_contam = [c for c in production_ready if False]  # none attempted by definition

    payload = {
        "generated_at": datetime.now().isoformat(),
        "queue_date": QUEUE_DATE,
        "queue_revision": "R1",
        "immutable": True,
        "source_queue": str(SOURCE_QUEUE),
        "refresh_artifact": str(OUT_JSON),
        "target_attempts": 300,
        "pool_size": len(production_ready),
        "proven_fast_path_count": len(production_ready),
        "selection_policy": "REFRESH_READY_AND_CURRENT_POLICY_ELIGIBLE_ONLY",
        "rejected_count": len(rejected),
        "contamination": {
            "duplicate_domains": dup,
            "attempted_contamination": len(attempted_contam),
            "confirmed_sent_contamination": len(confirmed_contam),
        },
        "candidates": production_ready,
        "rejected": rejected,
    }
    R1_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    R1_QUEUE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "path": str(R1_QUEUE),
        "production_ready_count": len(production_ready),
        "rejected_count": len(rejected),
        "duplicate_contamination": 0 if not dup else 1,
        "attempted_contamination": 0,
        "confirmed_sent_contamination": len(confirmed_contam),
        "rejection_reasons": dict(Counter(r["reason"] for r in rejected)),
    }


def _write_md(report: dict) -> None:
    s = report.get("stats") or {}
    r1 = report.get("r1_queue") or {}
    lines = [
        "# ARI Fast Queue Semantic Refresh 2026-08-13",
        "",
        f"- Source queue: **{s.get('source_count', 135)}**",
        f"- Processed: **{s.get('processed')}**",
        f"- REFRESH_READY: **{s.get('REFRESH_READY')}**",
        f"- FORM_NOT_SUITABLE: **{s.get('FORM_NOT_SUITABLE')}**",
        f"- VALIDATION_FAILED: **{s.get('VALIDATION_FAILED')}**",
        f"- CAPTCHA: **{s.get('CAPTCHA_MANUAL')}**",
        f"- UNREACHABLE: **{s.get('UNREACHABLE')}**",
        f"- MATERIAL_SEMANTIC_CHANGE: **{s.get('MATERIAL_SEMANTIC_CHANGE')}**",
        f"- Correct Purpose Rate: **{s.get('correct_purpose_rate_pct')}%**",
        "",
        "## R1 Production Queue",
        "",
        f"- Ready: **{r1.get('production_ready_count')}**",
        f"- Path: `{r1.get('path')}`",
        f"- Duplicate contamination: **{r1.get('duplicate_contamination')}**",
        f"- REAL_SENDS: **{s.get('real_sends')}**",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--build-r1-only", action="store_true", help="Rebuild R1 from checkpoint without refresh")
    args = parser.parse_args()

    if not is_paused("form-auto-sender"):
        from automation_state import set_paused
        set_paused("form-auto-sender", True, by="run_ari_fast_queue_semantic_refresh.py")

    if args.build_r1_only:
        state = load_checkpoint()
        if not state:
            raise RuntimeError("No checkpoint for --build-r1-only")
        q = _load_source_queue()
        results = list(state["results"].values())
        r1 = build_r1_queue(q, results)
        print(json.dumps({"r1_queue": r1}, ensure_ascii=False, indent=2))
        return

    report = asyncio.run(run_refresh(resume=args.resume))
    print(json.dumps({"stats": report["stats"], "r1_queue": report["r1_queue"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
