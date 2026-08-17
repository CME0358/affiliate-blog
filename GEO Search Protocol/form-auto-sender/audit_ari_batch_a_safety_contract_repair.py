#!/usr/bin/env python3
"""Read-only Batch-A forensic and zero-submit Remaining36 reclassification."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

import run_ari_146_live_revalidation as rv
from audit_ari_mw_wp_form_candidates23 import fingerprint_one
from audit_safe149_live_presubmit import audit_one
from form_sender import (get_real_submission_count, get_submit_forbidden,
                         reset_real_submission_count, set_submit_forbidden)

CANDIDATE = rv.OUT_DIR / "ARI-Safe-Single-Step70-Production-Authorization-Candidate-2026-08-17.json"
EXECUTION = rv.OUT_DIR / "ARI-Safe-Single-Step-BatchA10-Production-Execution-2026-08-17.json"
PRESEND = rv.OUT_DIR / "ARI-Safe-Single-Step-BatchA10-Pre-Send-Gate-2026-08-17.json"
CONFIRM_OUT = rv.OUT_DIR / "ARI-BatchA-Confirmation3-Forensic-2026-08-17.json"
CHECKBOX_OUT = rv.OUT_DIR / "ARI-BatchA-Required-Checkbox2-Forensic-2026-08-17.json"
POST_OUT = rv.OUT_DIR / "ARI-BatchA-Post-Only-Unknown4-Forensic-2026-08-17.json"
REMAINING_OUT = rv.OUT_DIR / "ARI-Safe-Single-Step-Remaining36-Reclassification-2026-08-17.json"
SUMMARY_OUT = rv.OUT_DIR / "ARI-BatchA-Safety-Contract-Repair-Audit-2026-08-17.json"
CONFIRM3 = ("keita-dental.gr.jp", "kk-dc.com", "kodama-dental.net")
CHECKBOX2 = ("ishiyama-dental.com", "kk-dc.com")
POST4 = ("itoh-dental.net", "j-dol.com", "kaigan-dental.com", "kodomo-haisha.net")
HISTORY = (rv.LOG_DIR / "sent.csv", rv.LOG_DIR / ".sent_index.csv", rv.LOG_DIR / "error.csv",
           rv.LOG_DIR / ".failure_cooldown.csv", rv.LOG_DIR / "permanent_skip.csv")


def file_hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def state() -> dict:
    s = rv.load_json(rv.BASE / "automation_state.json"); limits = rv.load_json(rv.LOG_DIR / "ari_daily_limits.json")
    p = subprocess.run(["launchctl", "list", "com.coaretail.form-auto-sender"], capture_output=True, text=True, check=False)
    return {"automation_paused": s["form-auto-sender"]["paused"], "production_limit": limits["production_limit"],
            "production_enabled": limits["production_enabled"], "launchagent_running": p.returncode == 0 and '"PID" =' in p.stdout,
            "raw_state": s, "raw_limits": limits}


def operational(x: dict) -> dict:
    return {k: x[k] for k in ("automation_paused", "production_limit", "production_enabled", "launchagent_running")}


def by_domain(path: Path, key: str = "results") -> dict[str, dict]:
    return {r["domain"]: r for r in rv.load_json(path).get(key) or [] if r.get("domain")}


async def inspect_dom(browser, row: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        context = await browser.new_context(ignore_https_errors=False); page = await context.new_page(); page.set_default_timeout(25_000)
        out = {"domain": row["domain"], "form_url": row["form_url"], "strict_tls": True, "form_fill": False,
               "post_requests": 0, "final_submit": 0, "error": ""}
        try:
            await page.goto(row["form_url"], wait_until="domcontentloaded", timeout=25_000); await page.wait_for_timeout(900)
            out.update(await page.evaluate(r"""() => {
              const visible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
              const label = e => {
                const byFor = e.id ? document.querySelector(`label[for="${CSS.escape(e.id)}"]`) : null;
                return ((byFor?.innerText || e.closest('label')?.innerText || e.parentElement?.innerText || '')).replace(/\s+/g,' ').trim().slice(0,240);
              };
              const forms = [...document.forms].map((f,i) => ({order:i, action:f.action||'', method:(f.method||'').toLowerCase(),
                id:f.id||'', className:f.className||'', text:(f.innerText||'').replace(/\s+/g,' ').trim().slice(0,300),
                is_search:!!f.querySelector('input[type="search"],input[name="s"]')}));
              const required = [...document.querySelectorAll('input[required],select[required],textarea[required],input[aria-required="true"],select[aria-required="true"],textarea[aria-required="true"],.wpcf7-validates-as-required')]
                .filter(visible).map(e => ({tag:e.tagName.toLowerCase(),type:(e.type||'').toLowerCase(),name:e.name||'',id:e.id||'',
                  value:e.value||'',checked:!!e.checked,label:label(e),form_action:e.form?.action||''}));
              const controls=[...document.querySelectorAll('button,input[type="submit"],input[type="button"],input[type="image"]')].filter(visible)
                .map((e,i)=>({order:i,tag:e.tagName.toLowerCase(),type:(e.type||'').toLowerCase(),name:e.name||'',value:e.value||'',
                  label:((e.innerText||e.value||'')).replace(/\s+/g,' ').trim(),form_action:e.form?.action||'',form_id:e.form?.id||''}));
              return {page_url:location.href, form_count:forms.length, forms, required_controls:required, controls,
                has_search_form:forms.some(f=>f.is_search), assets:[...document.querySelectorAll('script[src]')].map(x=>x.src).filter(x=>/contact|form|mail|mw-wp/i.test(x)).slice(0,20)};
            }"""))
        except Exception as exc:
            out["error"] = f"{type(exc).__name__}:{str(exc)[:400]}"
        finally:
            await context.close()
        return out


def production_forensics(execution: dict[str, dict], presend: dict[str, dict], dom: dict[str, dict]) -> tuple[list[dict], list[dict], list[dict]]:
    confirmation = []
    for d in CONFIRM3:
        prod = execution[d]; ev = prod.get("completion_evidence") or {}; current = dom[d]
        post = [x for x in ev.get("post_responses") or [] if "analytics" not in str(x.get("url"))]
        if d == "kk-dc.com": root = "SEARCH_SCOPE_CONTAMINATION_AFTER_CF7_VALIDATION"
        else: root = "GENERIC_CONFIRMATION_AUTO_FOLLOW"
        confirmation.append({"domain": d, "production_state": prod["state"], "root_cause": root,
            "initial_post": post[0] if post else None, "confirmation_reached": bool(ev.get("confirmation_reached")),
            "final_control_clicked": bool(prod.get("final_submit_clicked")), "final_url": prod.get("final_url"),
            "completion_evidence": ev, "pre_send_validation": presend.get(d), "current_read_only_dom": current})

    checkboxes = []
    for d in CHECKBOX2:
        prod = execution[d]; ev = prod.get("completion_evidence") or {}; current = dom[d]
        feedback = ev.get("cf7_feedback") or {}; invalid = feedback.get("invalid_fields") or []
        names = []
        for item in invalid:
            text = json.dumps(item, ensure_ascii=False)
            names += re.findall(r"checkbox[-_][0-9]+", text, re.I)
        required_checks = [x for x in current.get("required_controls") or [] if x.get("type") in {"checkbox", "radio"}]
        pre = ((presend.get(d) or {}).get("live_validation") or {})
        applied = pre.get("required_choices_applied") or []
        classification = "CONSENT_RESOLVER_GAP" if required_checks and any("同意" in (x.get("label") or "") for x in required_checks) else "REQUIRED_CHOICE_GAP"
        checkboxes.append({"domain": d, "classification": classification, "invalid_field_names": sorted(set(names)),
            "production_feedback": feedback, "current_required_checkbox_radio": required_checks,
            "preflight_required_choices_applied": applied, "preflight_field_map": pre.get("field_map"),
            "finding": "required checkbox/radio was not preserved as a selected production value"})

    post_only = []
    for d in POST4:
        prod = execution[d]; ev = prod.get("completion_evidence") or {}; responses = ev.get("post_responses") or []
        blob = json.dumps(responses, ensure_ascii=False).lower()
        if d == "itoh-dental.net": proposed, reason = "TRUE_UNKNOWN", "HTTP 200 custom PHP response lacks explicit success or failure evidence"
        elif d == "j-dol.com": proposed, reason = "FAILED", "explicit response error: タイプが未記入"
        elif d == "kaigan-dental.com": proposed, reason = "FAILED", "form POST returned HTTP 500"
        else: proposed, reason = "FAILED", "invalid form response contains required add field error"
        post_only.append({"domain": d, "current_history_state": "UNKNOWN", "proposed_classification": proposed,
            "reason": reason, "post_requests": ev.get("post_requests") or [], "post_responses": responses,
            "final_url": prod.get("final_url"), "history_write_performed": False})
    return confirmation, checkboxes, post_only


def required_risk(dom: dict, live: dict) -> tuple[bool, str]:
    risky = [x for x in dom.get("required_controls") or [] if x.get("type") in {"checkbox", "radio"}]
    applied_names = {str(x.get("name") or "") for x in live.get("required_choices_applied") or []}
    unresolved = [x for x in risky if x.get("name") not in applied_names and not x.get("checked")]
    if unresolved: return True, "unresolved_required_checkbox_or_radio"
    invalid = live.get("validation_state") or []
    if any(any(k in json.dumps(x, ensure_ascii=False).lower() for k in ("checkbox", "address", "type", "category", "add")) for x in invalid):
        return True, "post_fill_required_field_invalid"
    return False, ""


async def main() -> None:
    state_before = state()
    if operational(state_before) != {"automation_paused": True, "production_limit": 0, "production_enabled": False, "launchagent_running": False}:
        raise RuntimeError("STOP unsafe production state")
    hashes_before = {str(p): file_hash(p) for p in HISTORY}; set_submit_forbidden(True); reset_real_submission_count()
    candidate = rv.load_json(CANDIDATE); rows = candidate.get("candidates") or []
    if candidate.get("exact_count") != 46 or len(rows) != 46: raise RuntimeError("STOP candidate source mismatch")
    batch10 = tuple(candidate.get("exact_ordered_domains") or ())[:10]
    remaining = rows[10:]
    if len(remaining) != 36 or set(batch10) & {r["domain"] for r in remaining}: raise RuntimeError("STOP Remaining36 identity mismatch")
    inventory = {r["domain"]: r for r in rv.load_json(rv.FIXED_INVENTORY).get("records") or []}
    if any(r["domain"] not in inventory for r in rows): raise RuntimeError("STOP inventory join failure")
    execution = by_domain(EXECUTION); presend = by_domain(PRESEND)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            inspect_sem = asyncio.Semaphore(4)
            forensic_domains = tuple(dict.fromkeys(CONFIRM3 + CHECKBOX2 + POST4))
            forensic_dom_rows = await asyncio.gather(*(inspect_dom(browser, inventory[d], inspect_sem) for d in forensic_domains))
            forensic_dom = {r["domain"]: r for r in forensic_dom_rows}
            fp_sem = asyncio.Semaphore(4)
            fingerprints = await asyncio.gather(*(fingerprint_one(browser, inventory[r["domain"]], fp_sem) for r in remaining))
            audit_sem = asyncio.Semaphore(3)
            items = [{"row": inventory[r["domain"]], "ready": inventory[r["domain"]], "message": inventory[r["domain"]]["message"]} for r in remaining]
            audits = await asyncio.gather(*(audit_one(browser, item, i, audit_sem) for i, item in enumerate(items, 1)))
            dom_sem = asyncio.Semaphore(4)
            dom_rows = await asyncio.gather(*(inspect_dom(browser, inventory[r["domain"]], dom_sem) for r in remaining))
        finally:
            await browser.close()

    confirmation, checkboxes, post_only = production_forensics(execution, presend, forensic_dom)
    fp_by = {r["domain"]: r for r in fingerprints}; audit_by = {r["domain"]: r for r in audits}; dom_by = {r["domain"]: r for r in dom_rows}
    results = []
    for order, candidate_row in enumerate(remaining, 1):
        d = candidate_row["domain"]; fp = fp_by[d]; live = audit_by[d]; dom = dom_by[d]
        expected = candidate_row.get("semantic_evidence_hash") or ""; actual = live.get("audit_mapping_hash") or ""
        risk, risk_reason = required_risk(dom, live); cls = "HOLD"; reason = ""
        custom_confirmation_action = any(re.search(r"(?:mail|postmail).*\.(?:php|cgi)(?:$|\?)", str(f.get("action") or ""), re.I) for f in dom.get("forms") or [])
        if fp.get("classification") == "MW_WP_FORM_CONFIRMED": cls, reason = "CONFIRMATION_FLOW", "mw_wp_form_detected"
        elif fp.get("classification") == "MULTISTEP_OTHER" or custom_confirmation_action: cls, reason = "CONFIRMATION_FLOW", "confirmation_or_custom_mail_action"
        elif fp.get("classification") == "UNKNOWN" or dom.get("error"): cls, reason = "HOLD", "single_step_identity_unresolved"
        elif risk: cls, reason = "REQUIRED_FIELD_RISK", risk_reason
        elif dom.get("has_search_form") and dom.get("form_count", 0) > 1: cls, reason = "HOLD", "contact_search_scope_ambiguity"
        elif not expected or not actual or expected != actual: cls, reason = "RUNTIME_DIVERGENCE", "semantic_hash_divergence"
        elif live.get("classification") != "SAFE_TO_SUBMIT" or not live.get("final_submit_control_found"): cls, reason = "HOLD", str(live.get("blocker_reason") or live.get("classification"))
        else: cls, reason = "SAFE_SINGLE_STEP", "strict_tls_zero_submit_parity"
        results.append({"order": order, "domain": d, "company_name": inventory[d].get("company_name"),
            "classification": cls, "reason": reason, "fingerprint": fp, "zero_submit_validation": live,
            "read_only_dom": dom, "expected_semantic_hash": expected, "runtime_semantic_hash": actual})

    counts = Counter(r["classification"] for r in results); state_after = state(); hashes_after = {str(p): file_hash(p) for p in HISTORY}
    safety = {"submit_forbidden": get_submit_forbidden(), "real_sends": get_real_submission_count(), "final_submit": 0,
        "history_mutation": hashes_before != hashes_after, "production_state_changed": operational(state_before) != operational(state_after),
        "tls_bypass": 0, "captcha_bypass": 0}
    now = datetime.now(timezone.utc).isoformat()
    rv.atomic_json(CONFIRM_OUT, {"generated_at": now, "targets": 3, "results": confirmation, "history_mutation": False})
    rv.atomic_json(CHECKBOX_OUT, {"generated_at": now, "targets": 2, "results": checkboxes, "history_mutation": False})
    rv.atomic_json(POST_OUT, {"generated_at": now, "targets": 4, "results": post_only, "history_mutation": False})
    rv.atomic_json(REMAINING_OUT, {"generated_at": now, "source": str(CANDIDATE), "source_count": 36,
        "excluded_attempted_domains": list(batch10), "classification": dict(counts), "results": results,
        "safe_single_step_domains": [r["domain"] for r in results if r["classification"] == "SAFE_SINGLE_STEP"],
        "production_authorized": False, "safety": safety})
    rv.atomic_json(SUMMARY_OUT, {"generated_at": now, "confirmation_forensic": str(CONFIRM_OUT),
        "checkbox_forensic": str(CHECKBOX_OUT), "post_only_forensic": str(POST_OUT),
        "remaining36": str(REMAINING_OUT), "remaining36_classification": dict(counts), "safety": safety,
        "state_before": state_before, "state_after": state_after, "history_hash_before": hashes_before,
        "history_hash_after": hashes_after, "production_authorization": None})
    if not (get_submit_forbidden() and get_real_submission_count() == 0 and hashes_before == hashes_after and operational(state_before) == operational(state_after)):
        raise RuntimeError("STOP safety invariant failed")
    print(json.dumps({"confirmation": len(confirmation), "checkbox": len(checkboxes), "post_only": len(post_only),
        "remaining36": dict(counts), "accounting": sum(counts.values()), "safety": safety}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
