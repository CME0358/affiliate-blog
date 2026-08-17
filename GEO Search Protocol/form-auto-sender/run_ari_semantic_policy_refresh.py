#!/usr/bin/env python3
"""
run_ari_semantic_policy_refresh.py — ZERO-SEND semantic refresh under current policy.

Updates refresh evidence with current semantic_policy_version/fingerprint.
REAL SENDS = 0 / FINAL_SUBMIT = 0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))

import run_ari_auto_ready_semantic_refresh as refresh_mod
import run_ari_terminal_production as terminal
from automation_state import is_paused
from ari_pipeline.limits import load_limits
from ari_pipeline.status_integrity import count_official_confirmed_sent
from config import LOG_DIR, VAULT_ROOT
from form_field_resolver import clear_field_cache
from form_sender import get_real_submission_count, reset_real_submission_count, set_submit_forbidden
from inquiry_purpose_semantics import audit_selected_purpose
from preflight_classifier import FORM_NOT_SUITABLE
from semantic_policy import SEMANTIC_REFRESH_REQUIRED, is_semantic_policy_compatible

DATE = "2026-08-13"
TERMINAL_BATCH_ID = "TERMINAL-20260813-095059-10"
TERMINAL_LOCK = VAULT_ROOT / f"70_outputs/5-Day-Sales-Sprint/ARI-Terminal-Production-Batch-{TERMINAL_BATCH_ID}.json"
REFRESH_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-AUTO-READY-Semantic-Refresh-2026-08-12.json"
PREFLIGHT_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Full-Preflight-2026-08-12.json"
OUT_JSON = VAULT_ROOT / f"70_outputs/5-Day-Sales-Sprint/ARI-Semantic-Policy-Refresh-{DATE}.json"
OUT_MD = VAULT_ROOT / f"70_outputs/5-Day-Sales-Sprint/ARI Semantic Policy Refresh {DATE}.md"

TERMINAL_REMAINING = (
    "lively-h.co.jp",
    "bokuranoie.jp",
    "formgiving.jp",
    "nagumosoubi.co.jp",
    "tokyotensou.co.jp",
    "tosho-kensetsu.co.jp",
    "ishizawa-painting.co.jp",
)
PAINTCLUB_REGRESSION = "paintclub.jp"


def _load_refresh_index() -> dict[str, dict]:
    data = json.loads(REFRESH_JSON.read_text(encoding="utf-8"))
    return {r["domain"]: r for r in data.get("results", []) if r.get("domain")}


def _load_preflight_index() -> dict[str, dict]:
    data = json.loads(PREFLIGHT_JSON.read_text(encoding="utf-8"))
    return {r["domain"]: r for r in data.get("results", []) if r.get("domain")}


def detect_stale_domains(*, include_terminal_remaining: bool = True) -> list[str]:
    refresh = _load_refresh_index()
    stale: list[str] = []
    for dom, row in refresh.items():
        sem = row.get("semantic_evidence_v2") or {}
        ok, _ = is_semantic_policy_compatible(sem)
        if not ok:
            stale.append(dom)
    if include_terminal_remaining:
        for dom in TERMINAL_REMAINING:
            if dom not in stale:
                sem = (refresh.get(dom) or {}).get("semantic_evidence_v2") or {}
                ok, _ = is_semantic_policy_compatible(sem)
                if not ok:
                    stale.append(dom)
    if PAINTCLUB_REGRESSION not in stale:
        sem = (refresh.get(PAINTCLUB_REGRESSION) or {}).get("semantic_evidence_v2") or {}
        ok, _ = is_semantic_policy_compatible(sem)
        if not ok:
            stale.append(PAINTCLUB_REGRESSION)
    return sorted(set(stale))


def _purpose_audit_from_result(result: dict) -> str:
    snap = (result.get("semantic_evidence_v2") or {}).get("canonical_snapshot") or {}
    for choice in snap.get("choices_applied") or []:
        if choice.get("category") in ("INQUIRY_CATEGORY", "UNKNOWN"):
            return audit_selected_purpose(choice.get("label") or "", context=choice.get("context") or "")
    if result.get("refresh_outcome") == refresh_mod.FORM_NOT_SUITABLE_STATE:
        return "EXCLUDED_FORM_NOT_SUITABLE"
    return "NOT_APPLICABLE"


async def run_refresh(domains: list[str]) -> dict:
    set_submit_forbidden(True)
    reset_real_submission_count()
    clear_field_cache()

    limits = load_limits()
    if limits.production_limit != 0:
        raise RuntimeError(f"production_limit must be 0, got {limits.production_limit}")
    if not is_paused("form-auto-sender"):
        raise RuntimeError("automation must be paused")

    pf = _load_preflight_index()
    refresh_index = _load_refresh_index()
    population = [pf[d] for d in domains if d in pf]
    if len(population) != len(domains):
        missing = sorted(set(domains) - set(pf))
        raise RuntimeError(f"missing preflight rows: {missing}")

    submissions_before = get_real_submission_count()
    results: list[dict] = []
    total = len(population)

    for idx, row in enumerate(population, 1):
        before = get_real_submission_count()
        result = await refresh_mod._refresh_one(row, idx, total)
        if get_real_submission_count() > before:
            raise RuntimeError(f"SAFETY: submission during refresh {row.get('domain')}")
        result["semantic_policy_refresh"] = True
        result["prior_refresh_outcome"] = (refresh_index.get(row["domain"]) or {}).get("refresh_outcome")
        result["purpose_audit"] = _purpose_audit_from_result(result)
        results.append(result)

    if get_real_submission_count() > submissions_before:
        raise RuntimeError("SAFETY: submissions during refresh batch")

    # Merge into canonical refresh artifact
    merged = _load_refresh_index()
    for r in results:
        merged[r["domain"]] = r
    refresh_payload = json.loads(REFRESH_JSON.read_text(encoding="utf-8"))
    refresh_payload["results"] = [merged[d] for d in sorted(merged)]
    refresh_payload["semantic_policy_refresh_at"] = datetime.now().isoformat()
    REFRESH_JSON.write_text(json.dumps(refresh_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    stale_before = len(detect_stale_domains(include_terminal_remaining=False))
    eligible_after, eligible_meta = terminal.compute_eligible_unsent()

    stats = {
        "stale_candidates_detected": len(domains),
        "processed": len(results),
        "REFRESH_READY": sum(1 for r in results if r.get("refresh_outcome") == refresh_mod.REFRESH_READY),
        "FORM_NOT_SUITABLE": sum(1 for r in results if r.get("refresh_outcome") == refresh_mod.FORM_NOT_SUITABLE_STATE),
        "VALIDATION_FAILED": sum(1 for r in results if r.get("refresh_outcome") == refresh_mod.VALIDATION_FAILED),
        "CAPTCHA_MANUAL": sum(1 for r in results if r.get("refresh_outcome") == refresh_mod.CAPTCHA_MANUAL),
        "OTHER": sum(1 for r in results if r.get("refresh_outcome") not in (
            refresh_mod.REFRESH_READY,
            refresh_mod.FORM_NOT_SUITABLE_STATE,
            refresh_mod.VALIDATION_FAILED,
            refresh_mod.CAPTCHA_MANUAL,
        )),
        "purpose_incompatible": sum(1 for r in results if r.get("purpose_audit") == "INCOMPATIBLE"),
        "purpose_ambiguous": sum(1 for r in results if r.get("purpose_audit") == "AMBIGUOUS"),
        "purpose_compatible": sum(1 for r in results if r.get("purpose_audit") == "COMPATIBLE"),
        "purpose_not_applicable": sum(1 for r in results if r.get("purpose_audit") == "NOT_APPLICABLE"),
        "real_sends": get_real_submission_count(),
        "effective_confirmed_sent": count_official_confirmed_sent(),
        "eligible_unsent_after": len(eligible_after),
        "eligible_meta": eligible_meta,
    }

    ready_with_purpose = [
        r for r in results
        if r.get("refresh_outcome") == refresh_mod.REFRESH_READY
        and r.get("purpose_audit") in ("COMPATIBLE", "NOT_APPLICABLE", "EXCLUDED_FORM_NOT_SUITABLE")
    ]
    purpose_field_rows = [r for r in results if r.get("purpose_audit") in ("COMPATIBLE", "INCOMPATIBLE", "AMBIGUOUS")]
    if purpose_field_rows:
        compatible_count = sum(1 for r in purpose_field_rows if r.get("purpose_audit") == "COMPATIBLE")
        stats["correct_purpose_rate_pct"] = round(compatible_count / len(purpose_field_rows) * 100, 1)
    else:
        stats["correct_purpose_rate_pct"] = 100.0

    terminal_remaining_report = []
    for dom in TERMINAL_REMAINING:
        r = next((x for x in results if x["domain"] == dom), merged.get(dom))
        terminal_remaining_report.append({
            "domain": dom,
            "refresh_outcome": r.get("refresh_outcome") if r else "missing",
            "purpose_audit": _purpose_audit_from_result(r) if r else "missing",
            "policy_compatible": is_semantic_policy_compatible((r or {}).get("semantic_evidence_v2") or {})[0],
        })

    report = {
        "timestamp": datetime.now().isoformat(),
        "mode": "SEMANTIC_POLICY_ZERO_SEND_REFRESH",
        "terminal_batch_id": TERMINAL_BATCH_ID,
        "domains_requested": domains,
        "results": results,
        "stats": stats,
        "terminal_remaining_seven": terminal_remaining_report,
        "paintclub_regression": next((r for r in results if r["domain"] == PAINTCLUB_REGRESSION), None),
        "safety": {
            "real_sends": get_real_submission_count(),
            "final_submit": 0,
            "production_limit": load_limits().production_limit,
            "automation_paused": is_paused("form-auto-sender"),
            "submit_forbidden": True,
            "effective_confirmed_sent": count_official_confirmed_sent(),
        },
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# ARI Semantic Policy Refresh {DATE}",
        "",
        f"- processed: {stats['processed']}",
        f"- REFRESH_READY: {stats['REFRESH_READY']}",
        f"- FORM_NOT_SUITABLE: {stats['FORM_NOT_SUITABLE']}",
        f"- Correct Purpose Rate: {stats['correct_purpose_rate_pct']}%",
        f"- REAL_SENDS: {stats['real_sends']}",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detect-stale", action="store_true")
    ap.add_argument("--domains", nargs="*", help="Explicit domain list")
    ap.add_argument("--terminal-seven-plus-paintclub", action="store_true")
    args = ap.parse_args()

    if args.detect_stale:
        stale = detect_stale_domains()
        print(json.dumps({"stale_count": len(stale), "stale_domains": stale}, ensure_ascii=False, indent=2))
        return

    if args.domains:
        domains = args.domains
    elif args.terminal_seven_plus_paintclub:
        domains = sorted(set(TERMINAL_REMAINING) | {PAINTCLUB_REGRESSION})
    else:
        domains = detect_stale_domains()

    report = asyncio.run(run_refresh(domains))
    print(json.dumps({"stats": report["stats"], "terminal_remaining": report["terminal_remaining_seven"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
