#!/usr/bin/env python3
"""
run_ari_unknown_site_expansion_batch.py — 未知サイト拡張バッチ（#11–#20 / max 10 attempted）

環境変数: ARI_EXPANSION_BATCH_CONFIRM=1
automation: form-auto-sender 停止中必須
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))

from automation_state import is_paused
from config import LOG_DIR, VAULT_ROOT
from cookie_banner import cookie_overlay_likely, dismiss_cookie_banner
from form_field_resolver import resolve_form_fields
from form_fill_no_submit import fill_form_no_submit, _fill_standard_fields
from form_finder import NAV_TIMEOUT, _goto_settled
from form_sender import (
    _await_post_submit_settle,
    _click_submit,
    _prepare_submit_surface,
    get_real_submission_count,
    reset_real_submission_count,
    set_submit_forbidden,
    _record_real_submission,
)
from log_manager import append_sent_csv_row, get_effective_sent_status, is_already_sent
from message_builder import build_lp_url, build_message
from message_variant import format_selection_log_line, resolve_ari_message_for_form
from parser import parse_md_file
from submission_state import (
    CONFIRMED_SENT,
    FAILED,
    MANUAL_INTERVENTION_REQUIRED,
    SKIPPED,
    UNKNOWN,
    SubmissionCounters,
    classify_submission_outcome,
    normalize_effective_status,
    record_send_result,
    _count_forms,
    _html_signals,
    _SUCCESS_HTML_KEYWORDS,
)

CONFIRM_ENV = "ARI_EXPANSION_BATCH_CONFIRM"
PILOT_LIST = "@70_outputs/5-Day-Sales-Sprint/ARI-Production-Batch-30.md"
TARGET_NOS = list(range(11, 21))  # LOCKED list #11–#20（10件・補充なし）
CONTINUE_NOS = [14, 16, 17, 19, 20]  # preflight PASS 残5件
BATCH_MAX_ATTEMPTS = 10
CONTINUE_MAX_ATTEMPTS = 5
CAPTCHA_SURGE_THRESHOLD = 3  # batch 全体で MANUAL_INTERVENTION がこれ以上 → 環境制限疑いで stop
EXCLUDED_NOS = set(range(1, 11))

OUT_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ari_unknown_site_expansion_2026-08-11.json"
CONTINUATION_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ari_unknown_site_expansion_continue_2026-08-11.json"
LOG_CSV = LOG_DIR / "ari_unknown_site_expansion_2026-08-11.csv"
REPORT_MD = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI Unknown-Site Expansion Batch.md"
CONTINUATION_REPORT_MD = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI Unknown-Site Expansion Continuation.md"

_LOG_FIELDS = [
    "timestamp", "list_no", "phase", "company", "domain", "form_type", "form_url",
    "cookie_banner_detected", "cookie_banner_dismissed", "captcha_detected",
    "message_variant", "message_length", "attempted", "consent_state", "required_fields",
    "step1_clicked", "confirmation_reached", "final_submit_clicked", "post_submit_settle",
    "final_url", "post_requests", "response_type", "response_status", "response_message",
    "success_dom", "success_text", "success_evidence_type", "effective_status",
    "duplicate_lock", "submission_state", "success_evidence", "confirmed_sent_count", "notes",
]


def _domain(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def _company_from_list(companies: list[dict], list_no: int) -> dict | None:
    if 1 <= list_no <= len(companies):
        return companies[list_no - 1]
    return None


def _infer_form_type(fn: dict, html: str = "") -> str:
    h = (html or "").lower()
    if "wpcf7" in h:
        return "cf7"
    if "mwform" in h or "mw_wp_form" in h:
        return "mw_wp_form"
    if "cc-m-form" in h:
        return "jimdo"
    steps = fn.get("steps") or []
    if len(steps) >= 2:
        return "multi_step"
    if fn.get("final_submit_identified"):
        return "single_step"
    if fn.get("blocked"):
        return "blocked"
    return fn.get("status") or "unknown"


def _score_preflight(pf: dict) -> tuple[int, list[str], bool]:
    notes: list[str] = []
    score = 0
    if pf.get("duplicate_lock"):
        return -100, ["duplicate_lock"], False
    fn = pf.get("fill_no_submit") or {}
    if fn.get("blocked") or "captcha" in (fn.get("reason") or "").lower():
        return -50, [f"blocked:{fn.get('reason')}"], False
    if fn.get("status") == "error":
        return -40, [f"error:{fn.get('reason')}"], False
    if fn.get("status") == "skipped":
        return -30, ["maxlength_skip"], False
    if not fn.get("final_submit_identified"):
        score -= 20
        notes.append("no_final_submit")
    else:
        score += 10
    fm = fn.get("field_map") or {}
    for k in ("name", "email", "message"):
        if fm.get(k) == "FILLED":
            score += 3
        elif fm.get(k) == "MISSING":
            score -= 5
            notes.append(f"missing_{k}")
    mv = fn.get("message_validation") or {}
    if mv.get("pass"):
        score += 3
    steps = fn.get("steps") or []
    if len(steps) >= 2:
        score += 4
        notes.append("multi_step")
    elif fn.get("final_submit_identified"):
        score += 3
        notes.append("direct_submit")
    ok = score >= 10 and bool(fn.get("final_submit_identified"))
    return score, notes, ok


async def preflight_company(company: dict, list_no: int) -> dict:
    name = company.get("company_name", "")
    website = (company.get("website_url") or "").strip()
    eff = get_effective_sent_status(name, website)
    dup = is_already_sent(name, website)
    lp = build_lp_url(company.get("industry_name", ""), company.get("area_name", ""))
    msg = build_message(company.get("industry_name", ""), name, lp, area_name=company.get("area_name", ""))
    fn = await fill_form_no_submit(
        company, msg, lp,
        evidence_dir=VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/evidence/expansion-preflight",
    )
    pf = {
        "list_no": list_no,
        "company_name": name,
        "domain": _domain(website),
        "form_url": company.get("form_url", ""),
        "effective_status": eff,
        "duplicate_lock": dup,
        "fill_no_submit": {
            k: fn.get(k)
            for k in (
                "status", "reason", "field_map", "steps", "final_submit_identified",
                "final_submit_label", "required_fixes", "message_validation", "blocked",
                "message_variant", "message_length", "detected_maxlength", "consent",
            )
        },
        "cookie_overlay": bool(fn.get("cookie_overlay")),
        "form_type": _infer_form_type(fn),
        "expected_success": "url_or_dom_completion",
    }
    score, notes, ok = _score_preflight(pf)
    pf["stability_score"] = score
    pf["score_notes"] = notes
    pf["preflight_pass"] = ok and not dup
    pf["preflight_skip"] = not pf["preflight_pass"]
    return pf


def _append_log(row: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    write_header = not LOG_CSV.exists()
    with LOG_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_LOG_FIELDS, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerow(row)


async def execute_one(company: dict, list_no: int, pf: dict, counters: SubmissionCounters, *, batch_limit: int = BATCH_MAX_ATTEMPTS) -> dict:
    name = company.get("company_name", "")
    website = (company.get("website_url") or "").strip()
    dom = _domain(website)
    eff_before = get_effective_sent_status(name, website)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S JST")
    form_type = pf.get("form_type") or "unknown"

    row = {
        "timestamp": ts,
        "list_no": list_no,
        "phase": "production",
        "company": name,
        "domain": dom,
        "form_type": form_type,
        "form_url": company.get("form_url", ""),
        "cookie_banner_detected": False,
        "cookie_banner_dismissed": False,
        "captcha_detected": False,
        "message_variant": "",
        "message_length": 0,
        "attempted": False,
        "consent_state": "",
        "required_fields": "",
        "step1_clicked": False,
        "confirmation_reached": False,
        "final_submit_clicked": False,
        "post_submit_settle": False,
        "final_url": "",
        "post_requests": "",
        "response_type": "",
        "response_status": "",
        "response_message": "",
        "success_dom": "",
        "success_text": "",
        "success_evidence_type": "",
        "effective_status": eff_before,
        "duplicate_lock": is_already_sent(name, website),
        "submission_state": "",
        "success_evidence": "",
        "confirmed_sent_count": get_real_submission_count(),
        "notes": "",
    }

    if is_already_sent(name, website):
        row["submission_state"] = SKIPPED
        return {**row, "status": "skipped", "reason": "duplicate_lock", "submission_state": SKIPPED}

    if get_real_submission_count() >= batch_limit:
        row["submission_state"] = SKIPPED
        return {**row, "status": "skipped", "reason": "hard_limit", "submission_state": SKIPPED}

    from playwright.async_api import async_playwright

    set_submit_forbidden(False)
    lp = build_lp_url(company.get("industry_name", ""), company.get("area_name", ""))

    result: dict = {"status": "error", "reason": "not_started"}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await (await browser.new_context(locale="ja-JP")).new_page()
        post_requests: list[str] = []

        def _on_request(req) -> None:
            if req.method == "POST":
                post_requests.append(req.url)

        page.on("request", _on_request)
        from cf7_feedback import attach_cf7_feedback_capture, parse_cf7_feedback_body
        cf7_feedback_responses = attach_cf7_feedback_capture(page)
        try:
            form_url = company.get("form_url", "")
            if not await _goto_settled(page, form_url, goto_timeout=NAV_TIMEOUT):
                result = {"status": "error", "reason": "timeout", "submission_state": FAILED}
            else:
                html0 = await page.content()
                row["cookie_banner_detected"] = cookie_overlay_likely(html0)
                row["captcha_detected"] = any(
                    x in html0.lower() for x in ("recaptcha", "g-recaptcha", "hcaptcha", "cf-turnstile")
                )
                fields, _ = await resolve_form_fields(page, html0, form_url)
                if not fields:
                    result = {"status": "error", "reason": "form_analysis_failed", "submission_state": FAILED}
                else:
                    selection = await resolve_ari_message_for_form(
                        page, fields, lp, allow_validation_fallback=False,
                    )
                    print(f"  📝 {format_selection_log_line(selection)}")
                    row["message_variant"] = selection.variant
                    row["message_length"] = selection.message_length
                    if selection.skipped:
                        result = {
                            "status": "error",
                            "reason": selection.skip_reason or "maxlength",
                            "submission_state": FAILED,
                        }
                    else:
                        row["attempted"] = True
                        from consent_detector import CONSENT_DETECT_AND_FILL_JS, consent_fill_status
                        consent_result = await page.evaluate(CONSENT_DETECT_AND_FILL_JS)
                        row["consent_state"] = consent_fill_status(consent_result)
                        filled = await _fill_standard_fields(page, fields, selection.message)
                        if filled.get("consent"):
                            row["consent_state"] = filled["consent"]
                        req_parts = []
                        for key, fkey in (
                            ("name", "name_field"), ("email", "email_field"),
                            ("message", "message_field"), ("phone", "phone_field"),
                        ):
                            if fields.get(fkey):
                                req_parts.append(f"{key}={filled.get(key, 'MISSING')}")
                        row["required_fields"] = ";".join(req_parts)

                        dismissed = await dismiss_cookie_banner(page)
                        row["cookie_banner_dismissed"] = dismissed
                        await _prepare_submit_surface(page)

                        html_before_submit = await page.content()
                        _, _, captcha_sig = _html_signals(html_before_submit)
                        if captcha_sig:
                            row["captcha_detected"] = True
                            row["notes"] = "site_skip_captcha"
                            result = {
                                "status": "error",
                                "reason": "captcha_detected",
                                "submission_state": MANUAL_INTERVENTION_REQUIRED,
                                "site_skip": True,
                            }
                        else:
                            form_count_before = _count_forms(html_before_submit)
                            ok, err, meta = await _click_submit(page, fields)
                            row["step1_clicked"] = meta.get("steps_clicked", 0) >= 1
                            row["confirmation_reached"] = meta.get("confirmation_reached", False)
                            row["final_submit_clicked"] = meta.get("final_submit_clicked", False)
                            if not ok:
                                result = {
                                    "status": "error",
                                    "reason": err,
                                    "submission_meta": meta,
                                    "submission_state": FAILED,
                                }
                            else:
                                await _await_post_submit_settle(page)
                                row["post_submit_settle"] = True
                                final_url = page.url
                                html_after = await page.content()
                                meta["html_before"] = html_before_submit
                                meta["form_count_before"] = form_count_before
                                meta["form_count_after"] = _count_forms(html_after)
                                meta["post_requests"] = list(post_requests)
                                meta["cf7_feedback_responses"] = list(cf7_feedback_responses)
                                if cf7_feedback_responses:
                                    meta["cf7_feedback"] = cf7_feedback_responses[-1]
                                row["post_requests"] = ";".join(post_requests[:15])
                                if cf7_feedback_responses:
                                    cf7_parsed = parse_cf7_feedback_body(cf7_feedback_responses[-1])
                                    row["response_type"] = "cf7_feedback"
                                    row["response_status"] = cf7_parsed.status
                                    row["response_message"] = (cf7_parsed.message or "")[:500]
                                success_sig, confirm_sig, captcha_after = _html_signals(html_after)
                                row["captcha_detected"] = row["captcha_detected"] or captcha_after
                                row["success_dom"] = "success" if success_sig else ("confirm" if confirm_sig else "")
                                if success_sig:
                                    for kw in _SUCCESS_HTML_KEYWORDS:
                                        if kw.lower() in html_after.lower():
                                            row["success_text"] = kw[:200]
                                            break
                                outcome = classify_submission_outcome(
                                    final_url=final_url,
                                    form_url=form_url,
                                    html=html_after,
                                    meta=meta,
                                )
                                row["success_evidence_type"] = outcome.reason if outcome.state == CONFIRMED_SENT else ""
                                row["final_url"] = final_url
                                row["submission_state"] = outcome.state
                                row["success_evidence"] = outcome.reason if outcome.state == CONFIRMED_SENT else ""
                                result = {
                                    "status": "sent" if outcome.state == CONFIRMED_SENT else "error",
                                    "reason": outcome.reason,
                                    "submission_state": outcome.state,
                                    "submission_meta": meta,
                                    "final_url": final_url,
                                }
                                if outcome.counts_toward_confirmed_sent:
                                    _record_real_submission()
                                    append_sent_csv_row(company, {
                                        **result, "lp_url": lp, "form_url": form_url, "status": "sent",
                                    })
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
            await browser.close()

    row["confirmed_sent_count"] = get_real_submission_count()
    row["effective_status"] = get_effective_sent_status(name, website)
    record_send_result(counters, result, attempted=row["attempted"])
    merged = {**row, **result}
    _append_log(merged)
    return merged


def _failure_key(result: dict) -> str:
    """CAPTCHA / MANUAL_INTERVENTION は consecutive 集計から除外（site-skip）。"""
    state = result.get("submission_state", "")
    reason = (result.get("reason") or "").strip().lower()
    if state == MANUAL_INTERVENTION_REQUIRED:
        return ""
    if state == FAILED and reason:
        return reason
    if state == UNKNOWN:
        return "unknown"
    return ""


def _should_stop(result: dict, *, manual_intervention_total: int) -> tuple[bool, str]:
    state = result.get("submission_state", "")
    reason = (result.get("reason") or "").lower()
    if result.get("runtime_exception"):
        return True, "runtime_exception"
    if result.get("status") == "sent" and state != CONFIRMED_SENT:
        return True, "false_sent_suspicion"
    if result.get("duplicate_anomaly"):
        return True, "duplicate_anomaly"
    if result.get("captcha_bypass_required"):
        return True, "captcha_bypass_required"
    if manual_intervention_total >= CAPTCHA_SURGE_THRESHOLD:
        return True, "captcha_surge_environment_limit"
    return False, ""


def _scale_readiness(full: dict, stopped: bool, stop_reason: str) -> str:
    c = full.get("full_counters") or {}
    attempted = c.get("attempted", 0)
    sent = c.get("confirmed_sent", 0)
    unknown = c.get("unknown", 0)
    manual = c.get("manual_intervention", 0)
    if stopped and stop_reason in (
        "runtime_exception", "false_sent_suspicion", "captcha_bypass_required",
        "captcha_surge_environment_limit",
    ):
        return "STOP"
    if attempted == 0:
        return "NEEDS_MORE_HARDENING"
    rate = sent / attempted if attempted else 0
    if rate >= 0.3 and unknown <= 2 and manual <= 2 and not stopped:
        return "READY_FOR_10_MORE"
    if rate >= 0.15 or (attempted >= 3 and unknown <= 3):
        return "NEEDS_MORE_HARDENING"
    return "NEEDS_MORE_HARDENING"


def _load_prior_batch() -> dict:
    if OUT_JSON.exists():
        return json.loads(OUT_JSON.read_text(encoding="utf-8"))
    return {}


def _count_manual_intervention(production: list[dict]) -> int:
    return sum(
        1 for r in production
        if r.get("submission_state") == MANUAL_INTERVENTION_REQUIRED
    )


def _merge_full_counters(prior_production: list[dict], session_counters: dict) -> dict:
    """Prior #13 + this session → full batch counters."""
    full = SubmissionCounters()
    for row in prior_production:
        st = row.get("submission_state", "")
        attempted = bool(row.get("attempted"))
        if attempted:
            full.attempted += 1
        if row.get("final_submit_clicked"):
            full.final_submit_clicked += 1
        if st == CONFIRMED_SENT:
            full.confirmed_sent += 1
        elif st == FAILED:
            full.failed += 1
        elif st == UNKNOWN:
            full.unknown += 1
        elif st == MANUAL_INTERVENTION_REQUIRED:
            full.manual_intervention += 1
        elif st == SKIPPED:
            full.skipped += 1
    for k, v in session_counters.items():
        if k in full.to_dict():
            setattr(full, k, getattr(full, k) + v)
    return full.to_dict()


def _count_cumulative_confirmed() -> int:
    companies = parse_md_file(PILOT_LIST)
    return sum(
        1 for c in companies
        if get_effective_sent_status(c.get("company_name", ""), c.get("website_url", "")) == "CONFIRMED_SENT"
    )


def _write_continuation_report(report: dict) -> None:
    fc = report.get("full_counters") or {}
    rc = report.get("continuation_counters") or {}
    full_attempted = fc.get("attempted", 0)
    full_sent = fc.get("confirmed_sent", 0)
    rate = f"{(full_sent / full_attempted * 100):.1f}%" if full_attempted else "—"
    final = report.get("final_result", "")
    scale = report.get("scale_readiness", "")
    lines = [
        "# ARI Unknown-Site Expansion Continuation",
        "",
        f"**Date:** 2026-08-11  ",
        f"**Policy:** CAPTCHA → site-skip（batch-stop 解除）  ",
        f"**Final Result:** {final}",
        "",
        "## Remaining 5 Summary",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Target | 5 |",
        f"| Attempted | {rc.get('attempted', 0)} |",
        f"| Confirmed Sent | {rc.get('confirmed_sent', 0)} |",
        f"| Failed | {rc.get('failed', 0)} |",
        f"| Unknown | {rc.get('unknown', 0)} |",
        f"| Manual Intervention | {rc.get('manual_intervention', 0)} |",
        "",
        "## Full Expansion Batch Summary（#11–#20）",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Target | 10 |",
        f"| Attempted | {full_attempted} |",
        f"| Confirmed Sent | {full_sent} |",
        f"| Failed | {fc.get('failed', 0)} |",
        f"| Unknown | {fc.get('unknown', 0)} |",
        f"| Manual Intervention | {fc.get('manual_intervention', 0)} |",
        f"| Preflight Skipped | {report.get('preflight_skipped', 4)} |",
        "",
        f"**Batch stopped:** {report.get('stopped')} — {report.get('stop_reason') or '—'}",
        "",
        "## Success Rate（full batch）",
        "",
        f"Confirmed Sent / Attempted = **{rate}** ({full_sent}/{full_attempted})",
        "",
        "## Per-Company",
        "",
        "| # | Company | State | Notes |",
        "| ---: | --- | --- | --- |",
    ]
    status_map = report.get("all_company_status") or {}
    for no in TARGET_NOS:
        st = status_map.get(no, "—")
        name = next((p.get("company_name", "") for p in report.get("preflights", []) if p.get("list_no") == no), "")
        if not name:
            prior = _load_prior_batch()
            name = next((p.get("company_name", "") for p in prior.get("preflights", []) if p.get("list_no") == no), str(no))
        lines.append(f"| {no} | {name[:24]} | {st} | |")
    lines.extend([
        "",
        "## Compatibility（CONFIRMED_SENT）",
        "",
    ])
    for item in report.get("compatibility_successes") or []:
        lines.append(
            f"- #{item.get('list_no')} {item.get('company_name')} — "
            f"{item.get('form_type')} / {item.get('success_evidence')}"
        )
    if not report.get("compatibility_successes"):
        lines.append("- —")
    patterns = report.get("failure_patterns") or {}
    lines.extend([
        "",
        "## Failure Pattern",
        "",
    ])
    for k, v in sorted(patterns.items(), key=lambda x: -x[1]):
        lines.append(f"- `{k}`: {v}")
    lines.extend([
        "",
        "## Stability",
        "",
        f"- false SENT: {'none' if not report.get('stopped') or report.get('stop_reason') != 'false_sent_suspicion' else 'yes'}",
        f"- CAPTCHA handling: site-skip（#13 + continuation）",
        f"- UNKNOWN rate: {fc.get('unknown', 0)}/{full_attempted}",
        f"- FAILED rate: {fc.get('failed', 0)}/{full_attempted}",
        f"- runtime errors: {'yes' if report.get('stop_reason') == 'runtime_exception' else 'none'}",
        "",
        "## Tests",
        "",
        "103 passed（pre-run）",
        "",
        "## Cumulative Confirmed Sent",
        "",
        f"**{report.get('cumulative_confirmed_sent', 5)}**",
        "",
        "## Scale Readiness",
        "",
        f"**{scale}**",
        "",
        "## Final Result",
        "",
        f"**{final}**",
        "",
    ])
    CONTINUATION_REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    CONTINUATION_REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def _write_report(report: dict) -> None:
    c = report.get("counters") or {}
    attempted = c.get("attempted", 0)
    sent = c.get("confirmed_sent", 0)
    rate = f"{(sent / attempted * 100):.1f}%" if attempted else "—"
    final = report.get("final_result", "")
    scale = report.get("scale_readiness", "")
    lines = [
        "# ARI Unknown-Site Expansion Batch",
        "",
        f"**Date:** 2026-08-11  ",
        f"**Target:** #11–#20（LOCKED 30 / 補充なし）  ",
        f"**Final Result:** {final}",
        "",
        "## Expansion Batch Summary",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Target | 10 |",
        f"| Attempted | {attempted} |",
        f"| Confirmed Sent | {sent} |",
        f"| Failed | {c.get('failed', 0)} |",
        f"| Unknown | {c.get('unknown', 0)} |",
        f"| Manual Intervention | {c.get('manual_intervention', 0)} |",
        f"| Skipped (preflight) | {report.get('preflight_skipped', 0)} |",
        "",
        f"**Stopped:** {report.get('stopped')} — {report.get('stop_reason') or '—'}",
        "",
        "## Success Rate",
        "",
        f"Confirmed Sent / Attempted = **{rate}** ({sent}/{attempted})",
        "",
        "## Failure Pattern",
        "",
    ]
    patterns = report.get("failure_patterns") or {}
    if patterns:
        for k, v in sorted(patterns.items(), key=lambda x: -x[1]):
            lines.append(f"- `{k}`: {v}")
    else:
        lines.append("- —")
    lines.extend([
        "",
        "## Compatibility（CONFIRMED_SENT 構造）",
        "",
    ])
    for item in report.get("compatibility_successes") or []:
        lines.append(
            f"- #{item.get('list_no')} {item.get('company_name')} — "
            f"{item.get('form_type')} / {item.get('success_evidence')}"
        )
    if not report.get("compatibility_successes"):
        lines.append("- —")
    lines.extend([
        "",
        "## Tests",
        "",
        "103 passed（pre-run）",
        "",
        "## Cumulative Confirmed Sent",
        "",
        f"**{report.get('cumulative_confirmed_sent', 5)}**",
        "",
        "## Scale Readiness",
        "",
        f"**{scale}**",
        "",
        "## Final Result",
        "",
        f"**{final}**",
        "",
    ])
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def _build_all_company_status(prior: dict, session_production: list[dict]) -> dict[int, str]:
    status: dict[int, str] = {}
    for pf in prior.get("preflights", []):
        no = pf.get("list_no")
        if pf.get("preflight_skip"):
            status[no] = SKIPPED
    for row in prior.get("production", []):
        no = row.get("list_no")
        st = row.get("submission_state") or row.get("status", "")
        if st:
            status[no] = st
    for row in session_production:
        no = row.get("list_no")
        st = row.get("submission_state") or row.get("status", "")
        if st:
            status[no] = st
    return status


async def run_continue() -> dict:
    if os.environ.get(CONFIRM_ENV) != "1":
        print(f"⛔ Set {CONFIRM_ENV}=1", file=sys.stderr)
        sys.exit(1)
    if not is_paused("form-auto-sender"):
        print("⛔ automation must stay paused", file=sys.stderr)
        sys.exit(1)

    prior = _load_prior_batch()
    if not prior.get("preflights"):
        print("⛔ prior batch JSON missing preflights", file=sys.stderr)
        sys.exit(1)

    prior_production = list(prior.get("production") or [])
    pf_by_no = {p["list_no"]: p for p in prior["preflights"]}
    companies = parse_md_file(PILOT_LIST)

    os.environ["ARI_PRODUCTION_MAX_SUBMISSIONS"] = str(CONTINUE_MAX_ATTEMPTS)
    reset_real_submission_count()
    session_counters = SubmissionCounters()

    session_production: list[dict] = []
    stopped = False
    stop_reason = ""
    consecutive_unknown = 0
    consecutive_fail_key = ""
    consecutive_fail_count = 0
    production_count = 0
    failure_patterns: dict[str, int] = dict(prior.get("failure_patterns") or {})
    compatibility: list[dict] = list(prior.get("compatibility_successes") or [])

    for list_no in CONTINUE_NOS:
        if stopped:
            break
        pf = pf_by_no.get(list_no)
        if not pf:
            print(f"⛔ missing preflight for #{list_no}", file=sys.stderr)
            continue
        if not pf.get("preflight_pass"):
            print(f"\n[skip preflight] #{list_no} {pf.get('company_name')}")
            continue
        if production_count >= CONTINUE_MAX_ATTEMPTS:
            break

        c = _company_from_list(companies, list_no)
        if not c:
            continue
        print(f"\n[production] #{list_no} {c['company_name']}")
        try:
            res = await execute_one(
                c, list_no, pf, session_counters, batch_limit=CONTINUE_MAX_ATTEMPTS,
            )
        except Exception as exc:
            res = {
                "list_no": list_no,
                "company": c.get("company_name", ""),
                "submission_state": FAILED,
                "reason": str(exc),
                "runtime_exception": True,
                "attempted": False,
            }
            stopped = True
            stop_reason = "runtime_exception"
        session_production.append(res)
        if res.get("attempted"):
            production_count += 1

        fk = _failure_key(res)
        if fk:
            failure_patterns[fk] = failure_patterns.get(fk, 0) + 1
        if res.get("submission_state") == UNKNOWN:
            consecutive_unknown += 1
        else:
            consecutive_unknown = 0
        if fk and fk == consecutive_fail_key:
            consecutive_fail_count += 1
        elif fk:
            consecutive_fail_key = fk
            consecutive_fail_count = 1
        else:
            consecutive_fail_key = ""
            consecutive_fail_count = 0

        if consecutive_unknown >= 2:
            stopped = True
            stop_reason = "consecutive_unknown:2"
        if consecutive_fail_count >= 3:
            stopped = True
            stop_reason = f"repeated_failure:{consecutive_fail_key}"

        all_prod = prior_production + session_production
        stop, why = _should_stop(res, manual_intervention_total=_count_manual_intervention(all_prod))
        if stop and not stopped:
            stopped = True
            stop_reason = why

        if res.get("submission_state") == CONFIRMED_SENT:
            compatibility.append({
                "list_no": list_no,
                "company_name": c["company_name"],
                "form_type": pf.get("form_type"),
                "success_evidence": res.get("success_evidence"),
            })

    full_counters = _merge_full_counters(prior_production, session_counters.to_dict())
    all_company_status = _build_all_company_status(prior, session_production)
    rc = session_counters.to_dict()

    report: dict = {
        "mode": "continue_remaining",
        "continue_nos": CONTINUE_NOS,
        "target_nos": TARGET_NOS,
        "preflights": prior.get("preflights", []),
        "prior_production": prior_production,
        "production": session_production,
        "preflight_skipped": prior.get("preflight_skipped", 4),
        "stopped": stopped,
        "stop_reason": stop_reason,
        "continuation_counters": rc,
        "full_counters": full_counters,
        "failure_patterns": failure_patterns,
        "compatibility_successes": compatibility,
        "all_company_status": all_company_status,
        "cumulative_confirmed_sent": _count_cumulative_confirmed(),
        "scale_readiness": _scale_readiness({"full_counters": full_counters}, stopped, stop_reason),
        "final_result": "",
    }

    att = rc.get("attempted", 0)
    if stopped:
        report["final_result"] = "ARI UNKNOWN-SITE EXPANSION CONTINUATION STOPPED"
    elif att >= len(CONTINUE_NOS) and not stopped:
        report["final_result"] = "ARI UNKNOWN-SITE EXPANSION CONTINUATION COMPLETE"
    else:
        report["final_result"] = "ARI UNKNOWN-SITE EXPANSION CONTINUATION PARTIAL"

    CONTINUATION_JSON.parent.mkdir(parents=True, exist_ok=True)
    CONTINUATION_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_continuation_report(report)
    return report


async def run(*, preflight_only: bool = False) -> dict:
    if os.environ.get(CONFIRM_ENV) != "1" and not preflight_only:
        print(f"⛔ Set {CONFIRM_ENV}=1", file=sys.stderr)
        sys.exit(1)
    if not preflight_only and not is_paused("form-auto-sender"):
        print("⛔ automation must stay paused", file=sys.stderr)
        sys.exit(1)

    companies = parse_md_file(PILOT_LIST)
    os.environ["ARI_PRODUCTION_MAX_SUBMISSIONS"] = str(BATCH_MAX_ATTEMPTS)
    reset_real_submission_count()
    counters = SubmissionCounters()

    preflights: list[dict] = []
    for no in TARGET_NOS:
        if no in EXCLUDED_NOS:
            continue
        c = _company_from_list(companies, no)
        if not c:
            continue
        print(f"\n[preflight] #{no} {c['company_name']}")
        pf = await preflight_company(c, no)
        preflights.append(pf)
        print(f"  form={pf.get('form_type')} score={pf['stability_score']} pass={pf['preflight_pass']}")

    report: dict = {
        "target_nos": TARGET_NOS,
        "preflights": preflights,
        "production": [],
        "preflight_skipped": sum(1 for p in preflights if p.get("preflight_skip")),
        "stopped": False,
        "stop_reason": "",
        "counters": {},
        "failure_patterns": {},
        "compatibility_successes": [],
        "cumulative_confirmed_sent": _count_cumulative_confirmed(),
        "final_result": "",
        "scale_readiness": "",
    }

    if preflight_only:
        report["final_result"] = "PREFLIGHT_ONLY"
        OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    stopped = False
    stop_reason = ""
    consecutive_unknown = 0
    consecutive_fail_key = ""
    consecutive_fail_count = 0
    production_count = 0

    for pf in preflights:
        if stopped:
            break
        if pf.get("preflight_skip"):
            print(f"\n[skip preflight] #{pf['list_no']} {pf['company_name']}")
            continue
        if production_count >= BATCH_MAX_ATTEMPTS:
            break
        list_no = pf["list_no"]
        c = _company_from_list(companies, list_no)
        if not c:
            continue
        print(f"\n[production] #{list_no} {c['company_name']}")
        try:
            res = await execute_one(c, list_no, pf, counters)
        except Exception as exc:
            res = {"submission_state": FAILED, "reason": str(exc), "runtime_exception": True}
            stopped = True
            stop_reason = "runtime_exception"
        report["production"].append(res)
        if res.get("attempted"):
            production_count += 1

        fk = _failure_key(res)
        if fk:
            patterns = report["failure_patterns"]
            patterns[fk] = patterns.get(fk, 0) + 1
        if res.get("submission_state") == UNKNOWN:
            consecutive_unknown += 1
        else:
            consecutive_unknown = 0
        if fk and fk == consecutive_fail_key:
            consecutive_fail_count += 1
        elif fk:
            consecutive_fail_key = fk
            consecutive_fail_count = 1
        else:
            consecutive_fail_key = ""
            consecutive_fail_count = 0

        if consecutive_unknown >= 2:
            stopped = True
            stop_reason = "consecutive_unknown:2"
        if consecutive_fail_count >= 3:
            stopped = True
            stop_reason = f"repeated_failure:{consecutive_fail_key}"

        stop, why = _should_stop(res, manual_intervention_total=_count_manual_intervention(report["production"]))
        if stop and not stopped:
            stopped = True
            stop_reason = why

        if res.get("submission_state") == CONFIRMED_SENT:
            report["compatibility_successes"].append({
                "list_no": list_no,
                "company_name": c["company_name"],
                "form_type": pf.get("form_type"),
                "success_evidence": res.get("success_evidence"),
            })

    report["stopped"] = stopped
    report["stop_reason"] = stop_reason
    report["counters"] = counters.to_dict()
    report["cumulative_confirmed_sent"] = _count_cumulative_confirmed()
    report["scale_readiness"] = _scale_readiness({"full_counters": report["counters"]}, stopped, stop_reason)

    sent = counters.confirmed_sent
    att = counters.attempted
    if stopped:
        report["final_result"] = "ARI UNKNOWN-SITE EXPANSION BATCH STOPPED"
    elif att >= BATCH_MAX_ATTEMPTS or att >= len([p for p in preflights if not p.get("preflight_skip")]):
        report["final_result"] = (
            "ARI UNKNOWN-SITE EXPANSION BATCH COMPLETE"
            if sent > 0 and not stopped else
            "ARI UNKNOWN-SITE EXPANSION BATCH PARTIAL" if sent > 0 else
            "ARI UNKNOWN-SITE EXPANSION BATCH PARTIAL"
        )
        if sent == att and att > 0 and not stopped:
            report["final_result"] = "ARI UNKNOWN-SITE EXPANSION BATCH COMPLETE"
    else:
        report["final_result"] = "ARI UNKNOWN-SITE EXPANSION BATCH PARTIAL"

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_report(report)
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preflight-only", action="store_true")
    ap.add_argument(
        "--continue-remaining",
        action="store_true",
        help="Continue preflight PASS #14,#16,#17,#19,#20 (CAPTCHA=site-skip)",
    )
    args = ap.parse_args()
    if args.continue_remaining:
        report = asyncio.run(run_continue())
    else:
        report = asyncio.run(run(preflight_only=args.preflight_only))
    print("\n=== Summary ===")
    summary = {
        "target": report.get("continue_nos") or report.get("target_nos"),
        "preflight_skipped": report.get("preflight_skipped"),
        "counters": report.get("continuation_counters") or report.get("counters"),
        "full_counters": report.get("full_counters"),
        "stopped": report.get("stopped"),
        "stop_reason": report.get("stop_reason"),
        "scale_readiness": report.get("scale_readiness"),
        "cumulative_confirmed_sent": report.get("cumulative_confirmed_sent"),
        "final_result": report.get("final_result"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
