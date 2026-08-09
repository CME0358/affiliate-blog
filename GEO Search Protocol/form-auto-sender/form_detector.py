"""
form_detector.py — 問い合わせフォーム検出のみ（submit 禁止）

Playwright でフォーム URL 探索 + DOM フィールド検査。
送信・fill・CAPTCHA 操作は一切行わない。
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from form_finder import RECAPTCHA_INDICATORS, _has_recaptcha, find_form_url, is_file_download_url
from form_field_resolver import extract_fields_from_dom
from form_sender import NAV_TIMEOUT, _goto_settled, set_submit_forbidden

EXTERNAL_PROVIDERS = (
    "google.com/forms",
    "docs.google.com/forms",
    "typeform.com",
    "hubspot.com",
    "form.run",
    "forms.gle",
    "jotform.com",
    "form-mailer.jp",
    "ssl.formmailer",
)

REASON_TO_TYPE: dict[str, str] = {
    "no_form_external_booking": "EXTERNAL_FORM",
    "no_contact_form_only_reservation": "CONTACT_PAGE_ONLY",
    "no_form_chain_site": "BLOCKED",
    "recaptcha_detected": "CAPTCHA",
    "form_find_timeout": "ERROR",
    "pdf_or_file_download": "ERROR",
    "website_url_is_none": "ERROR",
}


def _same_registrable_domain(a: str, b: str) -> bool:
    def root(host: str) -> str:
        h = (host or "").lower().lstrip("www.")
        parts = h.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else h

    try:
        return root(urlparse(a).netloc) == root(urlparse(b).netloc)
    except Exception:
        return False


def _external_provider(form_url: str) -> str | None:
    u = (form_url or "").lower()
    for frag in EXTERNAL_PROVIDERS:
        if frag in u:
            return frag
    return None


def _classify_field(fields: dict[str, Any] | None, key: str) -> str:
    if not fields:
        return "MISSING"
    sel = fields.get(key)
    if not sel:
        return "MISSING"
    return "FOUND"


async def _inspect_page_signals(page, html: str) -> dict[str, Any]:
    """ログイン・多段・同意チェックボックスの DOM 検査（fill/submit なし）。"""
    signals: dict[str, Any] = {
        "login_required": False,
        "multi_step": False,
        "consent": "MISSING",
        "subject": "MISSING",
        "submit_label": None,
    }
    hl = html.lower()
    if re.search(r'type\s*=\s*["\']password["\']', hl):
        signals["login_required"] = True
    if hl.count("<form") > 1 or "確認画面" in html or "confirm" in hl:
        signals["multi_step"] = True
    if re.search(r"type\s*=\s*['\"]checkbox['\"]", hl) and (
        "同意" in html or "privacy" in hl or "個人情報" in html
    ):
        signals["consent"] = "FOUND"
    elif re.search(r"type\s*=\s*['\"]checkbox['\"]", hl):
        signals["consent"] = "OPTIONAL"
    if re.search(r'name\s*=\s*["\'][^"\']*(subject|title|件名)[^"\']*["\']', hl, re.I):
        signals["subject"] = "FOUND"
    try:
        label = await page.evaluate(
            """() => {
              const s = document.querySelector(
                'button[type="submit"], input[type="submit"], .wpcf7-submit, .mwform-submit'
              );
              return s ? (s.value || s.innerText || s.textContent || '').trim().slice(0, 80) : null;
            }"""
        )
        signals["submit_label"] = label or None
    except Exception:
        pass
    return signals


def _field_map(fields: dict[str, Any] | None, signals: dict[str, Any]) -> dict[str, str]:
    return {
        "company": _classify_field(fields, "company_field"),
        "name": _classify_field(fields, "name_field"),
        "email": _classify_field(fields, "email_field"),
        "phone": _classify_field(fields, "phone_field"),
        "subject": signals.get("subject", "MISSING"),
        "message": _classify_field(fields, "message_field"),
        "consent": signals.get("consent", "MISSING"),
    }


def _confidence(form_type: str, field_map: dict[str, str], same_domain: bool) -> str:
    if form_type not in ("FORM_FOUND", "CAPTCHA"):
        return "LOW"
    core = sum(1 for k in ("email", "message") if field_map.get(k) == "FOUND")
    if form_type == "FORM_FOUND" and core >= 2 and same_domain:
        return "HIGH"
    if form_type in ("FORM_FOUND", "CAPTCHA") and field_map.get("message") == "FOUND":
        return "MEDIUM"
    return "LOW"


def _map_finder_to_type(form_result: dict, website_url: str) -> tuple[str, str]:
    status = form_result.get("status", "")
    reason = form_result.get("reason", "") or ""
    form_url = form_result.get("form_url") or ""

    if status == "found":
        if _external_provider(form_url):
            return "EXTERNAL_FORM", ""
        if not _same_registrable_domain(website_url, form_url):
            return "EXTERNAL_FORM", "cross_domain_form"
        return "FORM_FOUND", ""

    if status == "pending" or reason == "recaptcha_detected":
        return "CAPTCHA", reason

    if reason in REASON_TO_TYPE:
        return REASON_TO_TYPE[reason], reason

    if status == "no_form":
        return "NO_FORM", reason or "no_form"

    return "ERROR", reason or status


async def detect_form_only(company: dict, timeout_sec: int | None = None) -> dict[str, Any]:
    """
    1社分のフォーム検出（submit 禁止・fill 禁止）。
    """
    set_submit_forbidden(True)
    name = company.get("company_name", "")
    website = (company.get("website_url") or "").strip()
    industry = company.get("industry_name", "")

    base: dict[str, Any] = {
        "company_name": name,
        "industry_name": industry,
        "website_url": website,
        "contact_page_url": website,
        "form_url": None,
        "form_type": "ERROR",
        "confidence": "LOW",
        "captcha": False,
        "external_provider": None,
        "submit_label": None,
        "field_map": {},
        "field_names": [],
        "failure_reason": "",
    }

    if not website:
        base["form_type"] = "ERROR"
        base["failure_reason"] = "website_url_is_none"
        return base

    print(f"🔎  [DETECT-ONLY] {name} ({website})")
    try:
        form_result = await find_form_url(website, company_name=name, timeout_sec=timeout_sec)
    except Exception as e:
        base["form_type"] = "ERROR"
        base["failure_reason"] = str(e)[:200]
        base["confidence"] = "LOW"
        return base
    form_type, fail = _map_finder_to_type(form_result, website)
    form_url = form_result.get("form_url")
    base["form_url"] = form_url
    base["form_type"] = form_type
    base["failure_reason"] = fail

    if form_type in ("NO_FORM", "EXTERNAL_FORM", "CONTACT_PAGE_ONLY", "BLOCKED", "ERROR") and not form_url:
        base["confidence"] = "LOW"
        return base

    if not form_url:
        base["confidence"] = "LOW"
        return base

    # フォームページを開いて DOM 検査（fill/submit なし）
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        base["form_type"] = "ERROR"
        base["failure_reason"] = "playwright_not_installed"
        return base

    if is_file_download_url(str(form_url)):
        base["form_type"] = "ERROR"
        base["failure_reason"] = "pdf_or_file_download"
        return base

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await context.new_page()
        try:
            if not await _goto_settled(page, str(form_url).strip(), goto_timeout=NAV_TIMEOUT):
                base["form_type"] = "ERROR"
                base["failure_reason"] = "page_load_timeout"
                return base

            base["contact_page_url"] = page.url
            html = await page.content()
            base["captcha"] = _has_recaptcha(html) or any(
                ind in html.lower() for ind in RECAPTCHA_INDICATORS
            )

            if base["captcha"] and form_type == "FORM_FOUND":
                form_type = "CAPTCHA"
                base["form_type"] = "CAPTCHA"

            ext = _external_provider(form_url) or _external_provider(page.url)
            base["external_provider"] = ext
            if ext and form_type == "FORM_FOUND":
                form_type = "EXTERNAL_FORM"
                base["form_type"] = "EXTERNAL_FORM"

            signals = await _inspect_page_signals(page, html)
            fields = await extract_fields_from_dom(page)

            if (
                signals["login_required"]
                and base["form_type"] == "FORM_FOUND"
                and not (fields and fields.get("message_field") and fields.get("email_field"))
            ):
                base["form_type"] = "LOGIN_REQUIRED"
            elif signals["multi_step"] and base["form_type"] == "FORM_FOUND":
                base["form_type"] = "MULTI_STEP"

            base["field_map"] = _field_map(fields, signals)
            base["submit_label"] = signals.get("submit_label")
            if fields:
                base["field_names"] = sorted(k for k, v in fields.items() if v and k != "furigana_format")

            same_domain = _same_registrable_domain(website, page.url)
            base["confidence"] = _confidence(base["form_type"], base["field_map"], same_domain)

        except Exception as e:
            base["form_type"] = "ERROR"
            base["failure_reason"] = str(e)[:200]
            base["confidence"] = "LOW"
        finally:
            await browser.close()

    return base
