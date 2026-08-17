"""
form_submit_canary.py — ARI 単発 submit canary（厳格安全ガード）

デフォルト: ライブ実行なし（SUBMIT_CANARY_LIVE=1 が無い限り submit 禁止）
- MAX_REAL_SUBMISSIONS = 1
- domain lock / single target / --limit 1 強制
- automation paused 必須（production resume しない）
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from automation_state import is_paused
from form_fill_no_submit import (
    _audit_buttons,
    _click_safe_next,
    _fill_standard_fields,
    classify_button_action,
    validate_ari_message,
)
from form_field_resolver import resolve_form_fields
from message_variant import format_selection_log_line, resolve_ari_message_for_form, selection_as_dict
from form_finder import NAV_TIMEOUT, _goto_settled, is_file_download_url
from form_sender import (
    get_real_submission_count,
    set_submit_forbidden,
    _record_real_submission,
)

MAX_REAL_SUBMISSIONS = 1
SUBMIT_CANARY_LIVE_ENV = "SUBMIT_CANARY_LIVE"

ALLOWED_CANARY_DOMAINS = frozenset({"123-yamadakoumuten.com"})
ALLOWED_PILOT_BASENAMES = frozenset({"ARI-Canary-Yamada.md"})
REQUIRED_COMPANY_KEYWORD = "山田工務店"


def is_live_execution_armed() -> bool:
    """ライブ submit には明示的な環境変数が必要。"""
    return os.environ.get(SUBMIT_CANARY_LIVE_ENV, "").strip() == "1"


def _domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _company_domains(company: dict) -> set[str]:
    domains: set[str] = set()
    for key in ("form_url", "website_url", "Web"):
        val = company.get(key) or company.get("web")
        if val:
            d = _domain_from_url(str(val))
            if d:
                domains.add(d)
    return domains


def validate_submit_canary_preconditions(
    pilot_list_path: str,
    companies: list[dict],
    limit: int | None,
) -> tuple[bool, str]:
    """
    submit-canary 実行前の静的ガード。
    Returns: (ok, error_code)
    """
    if limit is not None and limit != 1:
        return False, "limit_must_be_1"

    if len(companies) != 1:
        return False, "single_target_only"

    basename = Path(pilot_list_path.lstrip("@").strip()).name
    if basename not in ALLOWED_PILOT_BASENAMES:
        return False, f"pilot_list_not_allowed:{basename}"

    if not is_paused("form-auto-sender"):
        return False, "automation_must_stay_paused"

    if get_real_submission_count() >= MAX_REAL_SUBMISSIONS:
        return False, "max_real_submissions_reached"

    company = companies[0]
    name = company.get("company_name", "")
    if REQUIRED_COMPANY_KEYWORD not in name:
        return False, "company_keyword_mismatch"

    domains = _company_domains(company)
    if not domains or not domains <= ALLOWED_CANARY_DOMAINS:
        return False, f"domain_lock_failed:{','.join(sorted(domains)) or 'none'}"

    return True, ""


async def _click_final_submit(page, buttons: list[dict]) -> tuple[bool, str]:
    """FINAL_SUBMIT 分類ボタンのみクリック（live armed 時のみ呼ぶ）。"""
    final = [b for b in buttons if b.get("classification") == "FINAL_SUBMIT"]
    if len(final) != 1:
        return False, f"final_submit_ambiguous:{len(final)}"
    unknown = [b for b in buttons if b.get("classification") == "UNKNOWN"]
    if unknown:
        return False, "unknown_buttons_present"

    label = final[0].get("label", "")
    try:
        clicked = await page.evaluate(
            """(targetLabel) => {
              const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
              const sel = 'button, input[type="submit"], input[type="button"], [role="button"]';
              const forms = document.querySelectorAll('form');
              const roots = forms.length ? forms : [document.body];
              for (const root of roots) {
                for (const el of root.querySelectorAll(sel)) {
                  const t = norm((el.innerText || '') + ' ' + (el.textContent || '') + ' ' + (el.value || ''));
                  if (t.includes('送信') || t === targetLabel || targetLabel.includes(t)) {
                    if (t.includes('確認') && !t.includes('送信')) continue;
                    el.click();
                    return true;
                  }
                }
              }
              return false;
            }""",
            label,
        )
        if not clicked:
            return False, "final_submit_click_failed"
        return True, label
    except Exception as e:
        return False, str(e)


async def submit_canary(company: dict, message: str, lp_url: str) -> dict[str, Any]:
    """
    submit-canary 本体。
    デフォルト（live 未武装）: Playwright 起動せず implementation_ready を返す。
    """
    domains = _company_domains(company)
    if not domains or not domains <= ALLOWED_CANARY_DOMAINS:
        return {
            "status": "error",
            "reason": "domain_lock_failed",
            "live_execution": False,
            "overall": "BLOCKED",
        }

    msg_validation = validate_ari_message(message)
    base: dict[str, Any] = {
        "company_name": company.get("company_name", ""),
        "form_url": company.get("form_url", ""),
        "lp_url": lp_url,
        "message_validation": msg_validation,
        "live_execution": False,
        "real_submission_count": get_real_submission_count(),
        "max_real_submissions": MAX_REAL_SUBMISSIONS,
        "automation_paused": is_paused("form-auto-sender"),
        "allowed_domains": sorted(ALLOWED_CANARY_DOMAINS),
    }

    if not is_live_execution_armed():
        base.update({
            "status": "implementation_ready",
            "reason": "live_not_armed",
            "overall": "CANARY_SUBMISSION_IMPLEMENTATION_READY",
        })
        return base

    if get_real_submission_count() >= MAX_REAL_SUBMISSIONS:
        base.update({
            "status": "error",
            "reason": "max_real_submissions_reached",
            "overall": "BLOCKED",
        })
        return base

    if not is_paused("form-auto-sender"):
        base.update({
            "status": "error",
            "reason": "automation_must_stay_paused",
            "overall": "BLOCKED",
        })
        return base

    # ── Live path（SUBMIT_CANARY_LIVE=1 時のみ到達）────────────────────────
    set_submit_forbidden(False)

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {**base, "status": "error", "reason": "playwright_not_installed", "overall": "BLOCKED"}

    form_url_raw = company.get("form_url") or company.get("website_url", "")
    if not form_url_raw or is_file_download_url(str(form_url_raw).strip()):
        return {**base, "status": "error", "reason": "invalid_form_url", "overall": "BLOCKED"}

    network_posts: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="ja-JP")
        page = await context.new_page()
        page.on("request", lambda req: network_posts.append(req.url) if req.method == "POST" else None)

        try:
            if not await _goto_settled(page, str(form_url_raw).strip(), goto_timeout=NAV_TIMEOUT):
                return {**base, "status": "error", "reason": "timeout", "overall": "BLOCKED"}

            html = await page.content()
            fields, _ = await resolve_form_fields(page, html, str(form_url_raw).strip())
            if not fields:
                return {**base, "status": "error", "reason": "form_analysis_failed", "overall": "BLOCKED"}

            selection = await resolve_ari_message_for_form(
                page, fields, lp_url, allow_validation_fallback=False,
            )
            print(f"  📝 {format_selection_log_line(selection)}")
            base["message_selection"] = selection_as_dict(selection)
            base.update(selection.to_log_fields())
            if selection.skipped:
                return {
                    **base,
                    "status": "skipped",
                    "reason": selection.skip_reason or "compact_message_exceeds_maxlength",
                    "overall": "BLOCKED",
                }

            message = selection.message
            base["message_validation"] = validate_ari_message(message)

            await _fill_standard_fields(page, fields, message)
            buttons_s1 = await _audit_buttons(page)
            safe = [b for b in buttons_s1 if b.get("classification") == "NEXT_STEP_SAFE"]
            if safe:
                ok, _ = await _click_safe_next(page, buttons_s1)
                if ok:
                    import asyncio
                    await asyncio.sleep(1.0)

            buttons_s2 = await _audit_buttons(page)
            if get_real_submission_count() >= MAX_REAL_SUBMISSIONS:
                return {**base, "status": "error", "reason": "max_real_submissions_reached", "overall": "BLOCKED"}

            ok_final, detail = await _click_final_submit(page, buttons_s2)
            if not ok_final:
                return {**base, "status": "error", "reason": detail, "overall": "BLOCKED"}

            _record_real_submission()
            base["live_execution"] = True
            base["status"] = "sent"
            base["reason"] = ""
            base["overall"] = "CANARY_SUBMITTED"
            base["final_submit_label"] = detail
            base["network_post_count"] = len(network_posts)
        except Exception as e:
            return {**base, "status": "error", "reason": str(e), "overall": "BLOCKED"}
        finally:
            set_submit_forbidden(True)
            await browser.close()

    base["real_submission_count"] = get_real_submission_count()
    return base
