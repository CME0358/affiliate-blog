#!/usr/bin/env python3

import asyncio
import csv
import json
from collections import Counter
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from form_field_resolver import clear_field_cache
from form_sender import (
    get_real_submission_count,
    reset_real_submission_count,
    set_submit_forbidden,
)
from shared_form_prepare import shared_prepare_form


OUT_DIR = Path(
    "/Users/takeshisasaki/Downloads/Obsidian_Vault/"
    "70_outputs/5-Day-Sales-Sprint"
)

SOURCE = OUT_DIR / "ARI-Safe200-Persistent-V2-Manifest-2026-08-16.json"

OUT_JSON = OUT_DIR / "ARI-Safe149-Live-PreSubmit-Audit-2026-08-16.json"
OUT_CSV = OUT_DIR / "ARI-Safe149-Live-PreSubmit-Audit-2026-08-16.csv"

REGRESSION_DOMAINS = (
    "0339235248.com",
    "2nd-street.biz",
)

CONCURRENCY = 3
NAV_TIMEOUT_MS = 25000


def objdict(obj):
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    return {}


def flatten_choices(choice_log):
    choice_log = choice_log or {}

    applied = list(choice_log.get("applied") or [])
    skipped = list(choice_log.get("skipped") or [])
    unsuitable = list(choice_log.get("unsuitable") or [])

    post = choice_log.get("post_fill") or {}

    applied += list(post.get("applied") or [])
    skipped += list(post.get("skipped") or [])
    unsuitable += list(post.get("unsuitable") or [])

    return applied, skipped, unsuitable, post


async def requiredness_for_choice(page, item):
    name = str(item.get("name") or "")
    context = str(item.get("context") or "")

    textual_required = (
        "必須" in name
        or "必須" in context
        or "required" in context.lower()
        or "validates-as-required" in context.lower()
    )

    try:
        dom_required = await page.evaluate(
            """({name}) => {
                const els = Array.from(
                    document.querySelectorAll('input,select,textarea')
                ).filter(el => (el.name || '') === name);

                return els.some(el => {
                    const cls = (el.className || '').toString().toLowerCase();
                    const aria = (el.getAttribute('aria-required') || '').toLowerCase();

                    return (
                        el.required === true ||
                        aria === 'true' ||
                        cls.includes('validates-as-required')
                    );
                });
            }""",
            {"name": name},
        )
    except Exception:
        dom_required = False

    return bool(textual_required or dom_required)


async def browser_validation(page, contact_scope):
    try:
        return await page.evaluate(
            """(scope) => {
                let root = document;

                if (scope) {
                    try {
                        const hit = document.querySelector(scope);
                        if (hit) root = hit;
                    } catch (_) {}
                }

                return Array.from(
                    root.querySelectorAll(
                        'input:invalid,select:invalid,textarea:invalid'
                    )
                ).map(el => ({
                    name: el.name || '',
                    type: el.type || el.tagName.toLowerCase(),
                    required: !!el.required,
                    aria_required: el.getAttribute('aria-required') || '',
                    class_name: (el.className || '').toString(),
                    validation_message: el.validationMessage || ''
                }));
            }""",
            contact_scope or "",
        )
    except Exception:
        return []


async def detect_captcha(page):
    try:
        return await page.evaluate(
            """() => {
                const html = document.documentElement.innerHTML.toLowerCase();

                return !!(
                    document.querySelector(
                        '.g-recaptcha, .h-captcha, .cf-turnstile, ' +
                        '[data-sitekey], iframe[src*="recaptcha"], ' +
                        'iframe[src*="hcaptcha"], iframe[src*="turnstile"]'
                    ) ||
                    html.includes('captcha')
                );
            }"""
        )
    except Exception:
        return False


def classify(
    result,
    unknown_required,
    unsuitable,
    invalid_controls,
    captcha,
):
    reason = str(result.get("reason") or "")

    if captcha:
        return "FORM_BLOCKED", "captcha_detected"

    if unsuitable:
        return (
            "UNSUITABLE_REQUIRED_CHOICE",
            "unsuitable_required_choice",
        )

    if unknown_required:
        return (
            "UNKNOWN_REQUIRED_CHOICE",
            "unknown_required_choice",
        )

    if invalid_controls:
        return (
            "VALIDATION_BLOCKED",
            "browser_validation_not_clear",
        )

    if reason in (
        "form_not_suitable",
        "dynamic_form_unresolved",
        "external_iframe",
        "message_field_not_found",
    ):
        return "FORM_BLOCKED", reason

    if not result.get("fields"):
        return "FORM_BLOCKED", reason or "form_fields_unresolved"

    if not result.get("final_submit_identified"):
        return (
            "OTHER_REVIEW",
            reason or "final_submit_not_identified",
        )

    if result.get("ok") is True:
        return "SAFE_TO_SUBMIT", "pre_submit_state_reached"

    return "OTHER_REVIEW", reason or "prepare_not_ok"


async def audit_one(browser, item, rank, sem):
    async with sem:
        row = item.get("row") or {}
        ready = item.get("ready") or {}

        domain = row.get("domain") or ready.get("domain") or ""
        company = (
            row.get("company_name")
            or ready.get("company_name")
            or ""
        )
        form_url = (
            row.get("form_url")
            or ready.get("form_url")
            or ""
        )
        message = item.get("message") or ""
        lp_url = row.get("preview_url") or ""

        base = {
            "rank": rank,
            "candidate_id": row.get("candidate_id") or "",
            "domain": domain,
            "company_display_name": company,
            "form_url": form_url,
            "classification": "OTHER_REVIEW",
            "contact_form_scope": None,
            "field_map": {},
            "required_choices_applied": [],
            "required_choices_skipped": [],
            "required_choices_unsuitable": [],
            "required_choices_post_fill": {},
            "consent_state": None,
            "validation_state": [],
            "final_submit_control_found": False,
            "final_submit_label": None,
            "captcha_detected": False,
            "blocker_reason": "",
            "production_mapping_hash": None,
            "audit_mapping_hash": None,
            "audit_timestamp": datetime.now().isoformat(),
            "final_submit_clicked": False,
            "submission_attempted": False,
        }

        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(NAV_TIMEOUT_MS)

        try:
            await page.goto(
                form_url,
                wait_until="domcontentloaded",
                timeout=NAV_TIMEOUT_MS,
            )

            await page.wait_for_timeout(700)

            result_obj = await shared_prepare_form(
                page,
                form_url,
                message,
                lp_url,
                allow_validation_fallback=False,
                fixed_message_variant="ARI_MESSAGE_V2",
            )

            result = objdict(result_obj)

            applied, skipped, unsuitable, post = flatten_choices(
                result.get("choice_log")
            )

            unknown_required = []

            for choice in skipped:
                category = str(choice.get("category") or "").upper()

                if category != "UNKNOWN":
                    continue

                if await requiredness_for_choice(page, choice):
                    unknown_required.append(choice)

            contact_scope = result.get("contact_form_scope")
            invalid_controls = await browser_validation(
                page,
                contact_scope,
            )

            captcha = await detect_captcha(page)

            classification, blocker = classify(
                result,
                unknown_required,
                unsuitable,
                invalid_controls,
                captcha,
            )

            filled = result.get("filled") or {}

            base.update({
                "classification": classification,
                "contact_form_scope": contact_scope,
                "field_map":
                    result.get("field_map")
                    or filled
                    or {},
                "required_choices_applied": applied,
                "required_choices_skipped": skipped,
                "required_choices_unsuitable": unsuitable,
                "required_choices_post_fill": post,
                "consent_state":
                    filled.get("consent")
                    if isinstance(filled, dict)
                    else None,
                "validation_state": invalid_controls,
                "final_submit_control_found":
                    bool(result.get("final_submit_identified")),
                "final_submit_label":
                    result.get("final_submit_label"),
                "captcha_detected": captcha,
                "blocker_reason": blocker,
                "production_mapping_hash": None,
                "audit_mapping_hash":
                    result.get("mapping_hash") or None,
                "prepare_reason": result.get("reason") or "",
                "field_source": result.get("field_source") or "",
                "unknown_required_choices":
                    unknown_required,
            })

        except Exception as exc:
            base.update({
                "classification": "FORM_BLOCKED",
                "blocker_reason":
                    f"{type(exc).__name__}:{str(exc)[:400]}",
            })

        finally:
            await context.close()

        if get_real_submission_count() != 0:
            raise RuntimeError(
                "SAFETY_VIOLATION: submission count changed"
            )

        print(
            f"[{rank:03d}] "
            f"{domain} | "
            f"{base['classification']} | "
            f"{base['blocker_reason']}",
            flush=True,
        )

        return base


async def run_regression(browser, source):
    print()
    print("======================================")
    print("REGRESSION 2 — ZERO SEND")
    print("======================================")

    sem = asyncio.Semaphore(1)
    results = []

    for dom in REGRESSION_DOMAINS:
        hit = None
        rank = None

        for i, item in enumerate(source, 1):
            row = item.get("row") or {}
            if (row.get("domain") or "") == dom:
                hit = item
                rank = i
                break

        if not hit:
            raise RuntimeError(
                f"REGRESSION DOMAIN MISSING: {dom}"
            )

        r = await audit_one(
            browser,
            hit,
            rank,
            sem,
        )

        results.append(r)

    bad = [
        r
        for r in results
        if r["classification"] == "SAFE_TO_SUBMIT"
    ]

    print()
    for r in results:
        print(
            r["domain"],
            "=>",
            r["classification"],
            "|",
            r["blocker_reason"],
        )

        if r.get("unknown_required_choices"):
            print(
                "  UNKNOWN REQUIRED:",
                [
                    x.get("name")
                    for x in r["unknown_required_choices"]
                ],
            )

        if r.get("required_choices_unsuitable"):
            print(
                "  UNSUITABLE:",
                [
                    x.get("name")
                    for x in r["required_choices_unsuitable"]
                ],
            )

        if r.get("validation_state"):
            print(
                "  INVALID:",
                [
                    x.get("name")
                    for x in r["validation_state"]
                ],
            )

    if bad:
        print()
        print("REGRESSION: FAIL")
        print("STOP: known-risk domain classified SAFE_TO_SUBMIT")
        return False, results

    print()
    print("REGRESSION: PASS")
    return True, results


async def main():
    set_submit_forbidden(True)
    reset_real_submission_count()
    clear_field_cache()

    before = get_real_submission_count()

    if before != 0:
        raise RuntimeError(
            f"STOP: initial submission counter = {before}"
        )

    data = json.loads(
        SOURCE.read_text(encoding="utf-8")
    )

    source = data.get("selected") or []

    if len(source) != 149:
        raise RuntimeError(
            f"STOP: expected 149 source rows, got {len(source)}"
        )

    print("======================================")
    print("SAFE149 LIVE PRE-SUBMIT AUDIT")
    print("======================================")
    print("SOURCE:", len(source))
    print("SUBMIT FORBIDDEN: YES")
    print("PRODUCTION: OFF")
    print("REAL SENDS: 0")
    print("FINAL SUBMIT: 0")
    print()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True
        )

        try:
            regression_ok, regression = await run_regression(
                browser,
                source,
            )

            if not regression_ok:
                payload = {
                    "overall_result": "REGRESSION_FAIL",
                    "source_count": len(source),
                    "regression": regression,
                    "results": [],
                    "real_sends": 0,
                    "final_submit": 0,
                }

                OUT_JSON.write_text(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                return

            print()
            print("======================================")
            print("FULL 149 AUDIT START")
            print("CONCURRENCY:", CONCURRENCY)
            print("======================================")

            sem = asyncio.Semaphore(CONCURRENCY)

            tasks = [
                asyncio.create_task(
                    audit_one(
                        browser,
                        item,
                        i,
                        sem,
                    )
                )
                for i, item in enumerate(source, 1)
            ]

            results = await asyncio.gather(*tasks)

        finally:
            await browser.close()

    after = get_real_submission_count()

    if after != before:
        raise RuntimeError(
            f"SAFETY_VIOLATION: {before} -> {after}"
        )

    counts = Counter(
        r["classification"]
        for r in results
    )

    captcha_count = sum(
        bool(r.get("captcha_detected"))
        for r in results
    )

    payload = {
        "overall_result": "COMPLETE",
        "source_count": len(source),
        "audited_count": len(results),
        "classification_distribution": dict(counts),
        "captcha_count": captcha_count,
        "regression": regression,
        "results": results,
        "real_sends": 0,
        "final_submit": 0,
    }

    OUT_JSON.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    csv_fields = [
        "rank",
        "candidate_id",
        "domain",
        "company_display_name",
        "form_url",
        "classification",
        "contact_form_scope",
        "consent_state",
        "final_submit_control_found",
        "final_submit_label",
        "captcha_detected",
        "blocker_reason",
        "audit_mapping_hash",
        "audit_timestamp",
        "final_submit_clicked",
        "submission_attempted",
    ]

    with OUT_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=csv_fields,
        )

        writer.writeheader()

        for r in results:
            writer.writerow({
                k: r.get(k)
                for k in csv_fields
            })

    print()
    print("======================================")
    print("LIVE PRE-SUBMIT AUDIT COMPLETE")
    print("======================================")
    print("SOURCE:", len(source))
    print("AUDITED:", len(results))

    for name in (
        "SAFE_TO_SUBMIT",
        "UNKNOWN_REQUIRED_CHOICE",
        "UNSUITABLE_REQUIRED_CHOICE",
        "FORM_BLOCKED",
        "VALIDATION_BLOCKED",
        "OTHER_REVIEW",
    ):
        print(
            f"{name}:",
            counts.get(name, 0),
        )

    print("CAPTCHA:", captcha_count)

    print()
    print("=== SAFETY ===")
    print("SUBMIT FORBIDDEN: YES")
    print("REAL SENDS:", after)
    print("FINAL SUBMIT: 0")

    print()
    print("JSON:", OUT_JSON)
    print("CSV:", OUT_CSV)


if __name__ == "__main__":
    asyncio.run(main())
