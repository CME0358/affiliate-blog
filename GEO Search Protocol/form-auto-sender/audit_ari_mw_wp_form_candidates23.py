#!/usr/bin/env python3
"""Strict-TLS fingerprint + confirmation-only validation for remaining-96 candidates."""
from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

import form_field_resolver
import run_ari_146_live_revalidation as rv
from form_fill_no_submit import (FINAL_SUBMIT, NEXT_STEP_SAFE, _audit_buttons,
                                 _click_safe_next, pick_final_submit_button)
from form_sender import (get_real_submission_count, get_submit_forbidden,
                         reset_real_submission_count, set_submit_forbidden)
from mw_wp_form_state import (MW_COMPLETE, MW_CONFIRMATION, MW_INITIAL, cookie_hints,
                              detect_mw_wp_form_state_dom)
from shared_form_prepare import prepare_once

EXCLUDED10 = {
    "hiraki-dc.com", "honfleur.jp", "hokushikai.com", "ilchibrainyoga-ginza.com",
    "homedental-clinic.com", "kaatsu-hoasen.com", "horiuchi-dentalclinic.com",
    "lailaps-hokusei.jp", "ikebukuro-minnano.com", "mariart.net",
}
FINGERPRINT_OUT = rv.OUT_DIR / "ARI-MW-WP-Form-Candidate23-Fingerprint-2026-08-17.json"
VALIDATION_OUT = rv.OUT_DIR / "ARI-MW-WP-Form-Confirmation-Validation-2026-08-17.json"
IMPACT_OUT = rv.OUT_DIR / "ARI-Remaining96-Multistep-Classification-2026-08-17.json"
HISTORY = (rv.LOG_DIR / "sent.csv", rv.LOG_DIR / ".sent_index.csv", rv.LOG_DIR / "error.csv",
           rv.LOG_DIR / ".failure_cooldown.csv", rv.LOG_DIR / "permanent_skip.csv")


def file_hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def launchagent_running() -> bool:
    p = subprocess.run(["launchctl", "list", "com.coaretail.form-auto-sender"], capture_output=True, text=True, check=False)
    return p.returncode == 0 and '"PID" =' in p.stdout


def state() -> dict:
    s = rv.load_json(rv.BASE / "automation_state.json"); limits = rv.load_json(rv.LOG_DIR / "ari_daily_limits.json")
    return {"automation_paused": s["form-auto-sender"]["paused"], "production_limit": limits["production_limit"],
            "production_enabled": limits["production_enabled"], "launchagent_running": launchagent_running(),
            "raw_state": s, "raw_limits": limits}


def operational_state(value: dict) -> dict:
    return {k: value[k] for k in ("automation_paused", "production_limit", "production_enabled", "launchagent_running")}


def source_rows() -> tuple[list[dict], list[dict]]:
    live = rv.load_json(rv.OUT_JSON)
    remaining = [r for r in live.get("results", []) if r.get("revalidation_classification") == "PRODUCTION_READY" and r.get("domain") not in EXCLUDED10]
    candidates = [r for r in remaining if any(x in json.dumps(r, ensure_ascii=False).lower() for x in ("submitconfirm", "確認画面へ"))]
    if len(remaining) != 96:
        raise RuntimeError(f"STOP remaining source mismatch: {len(remaining)}")
    if len({r['domain'] for r in candidates}) != len(candidates):
        raise RuntimeError("STOP duplicate candidate domain")
    return remaining, candidates


async def fingerprint_one(browser, row: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        context = await browser.new_context(ignore_https_errors=False)
        page = await context.new_page(); page.set_default_timeout(25_000)
        base = {"domain": row["domain"], "company_name": row.get("company_display_name") or row.get("company_name"),
                "form_url": row.get("form_url"), "classification": "UNKNOWN", "strict_tls": True}
        try:
            await page.goto(row["form_url"], wait_until="domcontentloaded", timeout=25_000); await page.wait_for_timeout(700)
            mw = await detect_mw_wp_form_state_dom(page); cookies = cookie_hints(await context.cookies())
            buttons = await _audit_buttons(page, None)
            confirm_buttons = [b for b in buttons if b.get("classification") == NEXT_STEP_SAFE]
            if (mw.get("plugin_present") and mw.get("state") == MW_INITIAL and mw.get("form_id")
                    and mw.get("token_field_present") and mw.get("asset_hints")):
                cls = "MW_WP_FORM_CONFIRMED"
            elif confirm_buttons or any("確認画面" in (b.get("label") or "") or "submitconfirm" in (b.get("name") or "").lower() for b in buttons):
                cls = "MULTISTEP_OTHER"
            elif buttons:
                cls = "SINGLE_STEP_FALSE_POSITIVE"
            else:
                cls = "UNKNOWN"
            base.update({"classification": cls, "mw_evidence": mw, "cookie_name_hints": cookies,
                         "same_url_post": bool(mw.get("form_action") and mw.get("form_action", "").rstrip("/") == page.url.rstrip("/")),
                         "buttons": buttons, "post_requests": 0, "form_fill": False})
        except Exception as exc:
            base["error"] = f"{type(exc).__name__}:{str(exc)[:500]}"
        finally:
            await context.close()
        return base


async def validate_one(browser, source: dict, inventory: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        domain = source["domain"]; row = inventory[domain]
        context = await browser.new_context(ignore_https_errors=False); page = await context.new_page(); page.set_default_timeout(25_000)
        result = {"domain": domain, "company_name": row.get("company_name"), "classification": "ERROR",
                  "input_state": False, "confirm_state": False, "complete_state": False,
                  "final_submit_clicked": False, "strict_tls": True}
        try:
            await page.goto(row["form_url"], wait_until="domcontentloaded", timeout=25_000); await page.wait_for_timeout(700)
            prepared = await prepare_once(page, row["form_url"], row["message"], row["preview_url"],
                                          allow_validation_fallback=False, fixed_message_variant="ARI_MESSAGE_V2")
            before = await detect_mw_wp_form_state_dom(page); result["input_state"] = before.get("state") == MW_INITIAL
            buttons = await _audit_buttons(page, prepared.prep.contact_form_scope)
            nexts = [b for b in buttons if b.get("classification") == NEXT_STEP_SAFE]
            finals = [b for b in buttons if b.get("classification") == FINAL_SUBMIT]
            if not result["input_state"] or len(nexts) != 1 or finals:
                result.update(classification="HOLD", reason="initial_state_or_next_target_ambiguous", before=before, initial_buttons=buttons)
                return result
            clicked, detail = await _click_safe_next(page, buttons, prepared.prep.contact_form_scope)
            if not clicked:
                result.update(classification="HOLD", reason=detail, before=before); return result
            try: await page.wait_for_load_state("domcontentloaded", timeout=12_000)
            except Exception: pass
            await page.wait_for_timeout(1_200)
            after = await detect_mw_wp_form_state_dom(page); result["confirm_state"] = after.get("state") == MW_CONFIRMATION
            result["complete_state"] = after.get("state") == MW_COMPLETE
            confirm_buttons = await _audit_buttons(page, None); final, final_reason = pick_final_submit_button(confirm_buttons)
            if result["confirm_state"] and final and not result["complete_state"]:
                result.update(classification="CONFIRMATION_REACHED", reason="mw_wp_form_input_to_confirm",
                              before=before, after=after, final_control={k: final.get(k) for k in ("label","name","tag","type","selector")})
            else:
                result.update(classification="HOLD", reason=final_reason or "confirm_state_not_reproduced", before=before, after=after,
                              confirmation_buttons=confirm_buttons)
        except Exception as exc:
            result["reason"] = f"{type(exc).__name__}:{str(exc)[:500]}"
        finally:
            await context.close()
        return result


async def main() -> None:
    state_before = state()
    if not (state_before["automation_paused"] is True and state_before["production_limit"] == 0
            and state_before["production_enabled"] is False and not state_before["launchagent_running"]):
        raise RuntimeError("STOP production state unsafe")
    hashes_before = {str(p): file_hash(p) for p in HISTORY}
    remaining, candidates = source_rows()
    inventory_rows = rv.load_json(rv.FIXED_INVENTORY).get("records", [])
    inventory = {r["domain"]: r for r in inventory_rows}
    if any(r["domain"] not in inventory for r in candidates): raise RuntimeError("STOP inventory join failure")
    set_submit_forbidden(True); reset_real_submission_count()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            fingerprint_sem = asyncio.Semaphore(5)
            fingerprints = await asyncio.gather(*(fingerprint_one(browser, r, fingerprint_sem) for r in candidates))
            mw_rows = [x for x in fingerprints if x["classification"] == "MW_WP_FORM_CONFIRMED"]
            validation_sem = asyncio.Semaphore(2)
            validations = await asyncio.gather(*(validate_one(browser, x, inventory, validation_sem) for x in mw_rows))
        finally:
            await browser.close()
    validation_by = {r["domain"]: r for r in validations}; fp_by = {r["domain"]: r for r in fingerprints}
    remaining_classes = []
    candidate_domains = set(fp_by)
    for row in remaining:
        domain = row["domain"]
        if domain not in candidate_domains: cls = "SAFE_SINGLE_STEP"
        else:
            fp = fp_by[domain]; val = validation_by.get(domain)
            if fp["classification"] == "MW_WP_FORM_CONFIRMED": cls = "MW_WP_MULTISTEP" if val and val["classification"] == "CONFIRMATION_REACHED" else "HOLD"
            elif fp["classification"] == "MULTISTEP_OTHER": cls = "OTHER_MULTISTEP"
            elif fp["classification"] == "SINGLE_STEP_FALSE_POSITIVE": cls = "SAFE_SINGLE_STEP"
            else: cls = "UNKNOWN"
        remaining_classes.append({"domain": domain, "classification": cls})
    state_after = state(); hashes_after = {str(p): file_hash(p) for p in HISTORY}
    safety = {"submit_forbidden": get_submit_forbidden(), "real_sends": get_real_submission_count(), "final_submit": 0,
              "unknown_retries": 0, "history_mutation": hashes_before != hashes_after,
              "production_state_changed": operational_state(state_before) != operational_state(state_after),
              "production_state_metadata_changed": (state_before["raw_state"] != state_after["raw_state"]
                                                     or state_before["raw_limits"] != state_after["raw_limits"]),
              "tls_bypass": 0, "captcha_bypass": 0}
    now = datetime.now(timezone.utc).isoformat()
    rv.atomic_json(FINGERPRINT_OUT, {"generated_at": now, "remaining_source": 96, "targets": len(candidates),
        "classification": dict(Counter(x["classification"] for x in fingerprints)), "results": fingerprints,
        "strict_tls": True, "form_fill": False, "post_requests": 0})
    rv.atomic_json(VALIDATION_OUT, {"generated_at": now, "targets": len(validations),
        "classification": dict(Counter(x["classification"] for x in validations)), "results": validations,
        "submit_forbidden": True, "real_sends": 0, "final_submit": 0})
    rv.atomic_json(IMPACT_OUT, {"generated_at": now, "targets": len(remaining_classes),
        "classification": dict(Counter(x["classification"] for x in remaining_classes)), "results": remaining_classes,
        "safety": safety, "state_before": state_before, "state_after": state_after,
        "history_hash_before": hashes_before, "history_hash_after": hashes_after,
        "production_authorization": None})
    print(json.dumps({"fingerprint_targets": len(candidates), "fingerprint": dict(Counter(x["classification"] for x in fingerprints)),
        "mw_validation": dict(Counter(x["classification"] for x in validations)),
        "remaining96": dict(Counter(x["classification"] for x in remaining_classes)), "safety": safety}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    form_field_resolver.put_cached_fields = lambda *args, **kwargs: None
    asyncio.run(main())
