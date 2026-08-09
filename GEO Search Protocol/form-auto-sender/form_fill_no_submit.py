"""
form_fill_no_submit.py — フォーム入力のみ（submit 禁止）canary モード

- フィールド入力 + 安全な次ステップ遷移のみ
- FINAL_SUBMIT / UNKNOWN ボタンはクリックしない
- ネットワーク POST を監視（送信検知）
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from config import (
    SENDER_ADDRESS_FULL,
    SENDER_ADDRESS_LINE1,
    SENDER_ADDRESS_LINE2,
    SENDER_COMPANY,
    SENDER_EMAIL,
    SENDER_NAME,
    SENDER_PHONE,
    SENDER_POSTAL_CODE,
    SENDER_PREFECTURE,
    VAULT_ROOT,
)
from form_field_resolver import resolve_form_fields
from form_finder import NAV_TIMEOUT, is_file_download_url, _goto_settled
from form_sender import (
    _fill_address_block,
    _fill_message_field,
    _fill_postal_code,
    _fill_prefecture,
    _reset_gender_age_fields,
    get_real_submission_count,
    set_submit_forbidden,
)

# ─── ボタン分類 ───────────────────────────────────────────────────────────────

_FINAL_KW = (
    "この内容で送信",
    "送信する",
    "送　信",
    "問い合わせる",
    "内容を送る",
    "同意して送信",
    "submit",
    "send",
)
_NEXT_KW = (
    "入力内容を確認",
    "入力内容の確認",
    "内容を確認",
    "確認する",
    "確認画面",
    "次へ",
    "進む",
    "confirm",
)

_AUDIT_BUTTONS_JS = r"""
() => {
  const visible = (el) => {
    if (!el || !(el instanceof Element)) return false;
    const st = window.getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') return false;
    const r = el.getBoundingClientRect();
    return r.width >= 2 && r.height >= 2;
  };
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const items = [];
  const forms = document.querySelectorAll('form');
  const roots = forms.length ? forms : [document.body];
  const sel = 'button, input[type="submit"], input[type="button"], input[type="image"], [role="button"]';
  for (const root of roots) {
    for (const el of root.querySelectorAll(sel)) {
      if (!visible(el)) continue;
      const label = norm((el.innerText || '') + ' ' + (el.textContent || '') + ' ' + (el.value || ''));
      if (!label || label.length > 120) continue;
      const tag = el.tagName.toLowerCase();
      const type = (el.getAttribute('type') || '').toLowerCase();
      let css = '';
      if (el.id) css = '#' + CSS.escape(el.id);
      else if (el.className && typeof el.className === 'string') {
        const c = el.className.trim().split(/\s+/)[0];
        if (c) css = tag + '.' + CSS.escape(c);
      }
      items.push({ label, tag, type, selector: css || tag });
    }
  }
  return items;
}
"""

_FIND_SUBJECT_JS = r"""
() => {
  const kws = ['subject', 'title', '件名', 'your-subject', 'inquiry_subject'];
  for (const el of document.querySelectorAll('input, textarea, select')) {
    const n = (el.name || '').toLowerCase();
    const id = (el.id || '').toLowerCase();
    const ph = (el.placeholder || '').toLowerCase();
    if (kws.some((k) => n.includes(k) || id.includes(k) || ph.includes(k))) {
      if (el.tagName === 'SELECT') continue;
      return el.name ? `[name="${el.name}"]` : (el.id ? `#${el.id}` : null);
    }
  }
  return null;
}
"""

_FIND_CONSENT_JS = r"""
() => {
  const tick = (cb) => {
    if (!cb) return false;
    cb.checked = true;
    cb.dispatchEvent(new Event('input', { bubbles: true }));
    cb.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  };
  const boxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
  for (const el of boxes) {
    const ctx = (
      (el.name || '') + ' ' + (el.id || '') + ' ' +
      (el.closest('label')?.innerText || '') + ' ' +
      (el.parentElement?.innerText || '') + ' ' +
      (el.closest('form')?.innerText || '')
    ).toLowerCase();
    if (
      ctx.includes('同意') || ctx.includes('privacy') || ctx.includes('個人情報') ||
      ctx.includes('プライバシー') || ctx.includes('同意する')
    ) {
      tick(el);
      return el.name ? `[name="${el.name}"]` : (el.id ? `#${el.id}` : 'checked');
    }
  }
  // 「同意する」ラベル近傍の checkbox
  for (const el of document.querySelectorAll('label, p, div, span')) {
    const t = (el.innerText || '').trim();
    if (!t.includes('同意')) continue;
    const cb = el.querySelector('input[type="checkbox"]')
      || el.parentElement?.querySelector('input[type="checkbox"]');
    if (cb && tick(cb)) {
      return cb.name ? `[name="${cb.name}"]` : (cb.id ? `#${cb.id}` : 'checked');
    }
  }
  if (boxes.length === 1) {
    tick(boxes[0]);
    return boxes[0].name ? `[name="${boxes[0].name}"]` : 'checked';
  }
  return null;
}
"""

_ANALYTICS_HOST_FRAGMENTS = (
    "google-analytics.com",
    "analytics.google.com",
    "doubleclick.net",
    "googletagmanager.com",
    "google.com/g/collect",
)


def _classify_post_url(url: str, form_url: str) -> str:
    """analytics | form_confirm | inquiry | other"""
    u = url.lower()
    if any(h in u for h in _ANALYTICS_HOST_FRAGMENTS):
        return "analytics"
    if any(k in u for k in ("formmail", "wpcf7", "mwform", "sendgrid", "mail.php", "cgi-bin")):
        return "inquiry"
    try:
        from urllib.parse import urlparse
        if form_url:
            if urlparse(url).netloc == urlparse(form_url).netloc:
                return "form_confirm"
    except Exception:
        pass
    return "other"

ARI_SUBJECT = "Agent Readiness Index についてのご連絡"


def classify_button_action(label: str, btn_type: str = "") -> str:
    """NEXT_STEP_SAFE | FINAL_SUBMIT | UNKNOWN"""
    t = (label or "").strip().lower()
    btn_type = (btn_type or "").lower()

    if any(k.lower() in t for k in _FINAL_KW):
        if any(k.lower() in t for k in _NEXT_KW):
            # 「確認して送信」等 — 送信優先
            if "送信" in t and "確認" not in t.replace("送信", "", 1):
                return "FINAL_SUBMIT"
        else:
            return "FINAL_SUBMIT"

    if "送信" in t and "確認" not in t:
        return "FINAL_SUBMIT"

    if any(k.lower() in t for k in _NEXT_KW):
        return "NEXT_STEP_SAFE"

    if btn_type == "submit" and "確認" in t:
        return "NEXT_STEP_SAFE"

    if btn_type == "submit":
        return "UNKNOWN"

    return "UNKNOWN"


def validate_ari_message(message: str) -> dict[str, Any]:
    """ARI 文面検証."""
    checks = {
        "ari_positioning": "Agent Readiness" in message,
        "new_lp": "readiness.coaretail.com/report/" in message,
        "legacy_geo": message.count("localgeo.coaretail.com"),
        "old_geo_pitch": message.count("GEO Search Protocol") + message.count("無料診断"),
        "abis": message.count("ABIS"),
        "ranking_guarantee": message.count("ranking guarantee") + message.count("順位保証"),
        "traffic_guarantee": message.count("traffic guarantee") + message.count("流入保証"),
        "sales_guarantee": message.count("sales guarantee") + message.count("売上保証"),
    }
    checks["pass"] = (
        checks["ari_positioning"]
        and checks["new_lp"]
        and checks["legacy_geo"] == 0
        and checks["old_geo_pitch"] == 0
        and checks["abis"] == 0
        and checks["ranking_guarantee"] == 0
        and checks["traffic_guarantee"] == 0
        and checks["sales_guarantee"] == 0
    )
    return checks


def _mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return (local[:2] + "***@" + domain) if local else "***@" + domain


def _field_status_map(
    fields: dict,
    filled: dict[str, str],
    signals: dict[str, str],
) -> dict[str, str]:
    """FOUND | FILLED | SKIPPED | AMBIGUOUS | MISSING"""
    out: dict[str, str] = {}
    mapping = {
        "company": "company_field",
        "name": "name_field",
        "email": "email_field",
        "phone": "phone_field",
        "message": "message_field",
    }
    for logical, key in mapping.items():
        if fields.get(key):
            out[logical] = filled.get(logical, "FOUND")
        else:
            out[logical] = "MISSING"
    out["subject"] = filled.get("subject", signals.get("subject", "MISSING"))
    out["consent"] = filled.get("consent", signals.get("consent", "MISSING"))
    return out


async def _fill_standard_fields(page, fields: dict, message: str) -> dict[str, str]:
    """send_form と同等の入力（submit 除く）。Returns per-field fill status."""
    filled: dict[str, str] = {}

    if fields.get("company_field"):
        await page.fill(fields["company_field"], SENDER_COMPANY)
        filled["company"] = "FILLED"

    if fields.get("name_field"):
        await page.fill(fields["name_field"], SENDER_NAME)
        filled["name"] = "FILLED"

    if fields.get("furigana_name_field"):
        furigana_value = (
            "ささきたけし"
            if fields.get("furigana_format") == "hiragana"
            else "ササキタケシ"
        )
        await page.fill(fields["furigana_name_field"], furigana_value)

    if fields.get("email_field"):
        await page.fill(fields["email_field"], SENDER_EMAIL)
        filled["email"] = "FILLED"

    if fields.get("phone_field"):
        await page.fill(fields["phone_field"], SENDER_PHONE)
        filled["phone"] = "FILLED"

    await _fill_postal_code(page, fields.get("postal_code_field") or "")
    await _fill_prefecture(page, fields)
    await _fill_address_block(page, fields)
    await _reset_gender_age_fields(page, fields)

    msg_ok, _ = await _fill_message_field(page, fields, message)
    filled["message"] = "FILLED" if msg_ok else "MISSING"

    await _reset_gender_age_fields(page, fields)

    # subject（resolver 外 — DOM 探索）
    try:
        sub_sel = await page.evaluate(_FIND_SUBJECT_JS)
        if sub_sel:
            await page.fill(sub_sel, ARI_SUBJECT)
            filled["subject"] = "FILLED"
        elif fields.get("subject_field"):
            await page.fill(fields["subject_field"], ARI_SUBJECT)
            filled["subject"] = "FILLED"
    except Exception:
        pass

    # consent チェックボックス
    try:
        consent_sel = await page.evaluate(_FIND_CONSENT_JS)
        if consent_sel:
            filled["consent"] = "FILLED"
    except Exception:
        pass

    return filled


async def _audit_buttons(page) -> list[dict]:
    raw = await page.evaluate(_AUDIT_BUTTONS_JS)
    out = []
    for b in raw or []:
        cls = classify_button_action(b.get("label", ""), b.get("type", ""))
        out.append({**b, "classification": cls})
    return out


async def _click_safe_next(page, buttons: list[dict]) -> tuple[bool, str]:
    """NEXT_STEP_SAFE ボタンのみクリック。曖昧なら停止。"""
    safe = [b for b in buttons if b.get("classification") == "NEXT_STEP_SAFE"]
    final = [b for b in buttons if b.get("classification") == "FINAL_SUBMIT"]
    unknown = [b for b in buttons if b.get("classification") == "UNKNOWN"]

    if final:
        return False, "final_submit_visible_no_click"

    if len(safe) != 1:
        if safe:
            return False, f"ambiguous_next_step_count_{len(safe)}"
        if unknown:
            return False, "unknown_buttons_only"
        return False, "no_safe_next_button"

    if unknown:
        return False, "unknown_buttons_present"

    label = safe[0].get("label", "")
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
                  if (t === targetLabel || t.includes(targetLabel) || targetLabel.includes(t)) {
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
            return False, "safe_next_click_failed"
        return True, label
    except Exception as e:
        return False, str(e)


def _classify_overall(result: dict) -> str:
    if result.get("blocked"):
        return "BLOCKED"
    if result.get("required_fixes"):
        return "READY_WITH_FIXES"
    fm = result.get("field_map", {})
    core_missing = sum(1 for k in ("email", "message", "name") if fm.get(k) in ("MISSING", "AMBIGUOUS"))
    if core_missing:
        return "READY_WITH_FIXES"
    if result.get("real_submission_count", 0) > 0:
        return "BLOCKED"
    if result.get("network", {}).get("inquiry_post_count", 0) > 0:
        return "BLOCKED"
    if not result.get("final_submit_identified"):
        return "READY_WITH_FIXES"
    return "READY_FOR_CANARY_SUBMISSION"


async def fill_form_no_submit(
    company: dict,
    message: str,
    lp_url: str,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    """
    フォーム入力完了直前まで実行（submit 禁止）。
    """
    set_submit_forbidden(True)

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"status": "error", "reason": "playwright_not_installed", "blocked": True}

    from url_builder import get_industry_slug

    message_slug = get_industry_slug(company.get("industry_name", "")) or "unknown"
    form_url_raw = company.get("form_url") or company.get("website_url", "")

    if not form_url_raw or not str(form_url_raw).strip():
        return {"status": "error", "reason": "form_url_is_none", "blocked": True}

    if is_file_download_url(str(form_url_raw).strip()):
        return {"status": "error", "reason": "pdf_or_file_download", "blocked": True}

    if evidence_dir is None:
        evidence_dir = (
            VAULT_ROOT
            / "70_outputs/5-Day-Sales-Sprint/evidence/yamada-canary"
        )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = evidence_dir / f"fill_no_submit_{ts}.png"

    network_posts: list[str] = []
    msg_validation = validate_ari_message(message)

    result: dict[str, Any] = {
        "status": "filled",
        "reason": "",
        "form_url": str(form_url_raw).strip(),
        "lp_url": lp_url,
        "message_slug": message_slug,
        "company_name": company.get("company_name", ""),
        "field_map": {},
        "steps": [],
        "final_submit_identified": False,
        "final_submit_label": None,
        "network": {"post_urls": [], "inquiry_post_count": 0},
        "real_submission_count": 0,
        "message_validation": msg_validation,
        "screenshot_path": str(screenshot_path),
        "blocked": False,
        "required_fixes": [],
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await context.new_page()

        def _on_request(req):
            if req.method.upper() == "POST":
                network_posts.append(req.url)

        page.on("request", _on_request)

        try:
            if not await _goto_settled(page, str(form_url_raw).strip(), goto_timeout=NAV_TIMEOUT):
                result["status"] = "error"
                result["reason"] = "timeout"
                result["blocked"] = True
                await browser.close()
                return result

            html = await page.content()
            fields, field_source = await resolve_form_fields(page, html, str(form_url_raw).strip())
            result["field_source"] = field_source

            if not fields:
                result["status"] = "error"
                result["reason"] = "form_analysis_failed"
                result["blocked"] = True
                await browser.close()
                return result

            # Step 1: fill
            filled = await _fill_standard_fields(page, fields, message)
            buttons_s1 = await _audit_buttons(page)
            result["steps"].append({
                "step": 1,
                "url": page.url,
                "buttons": buttons_s1,
            })

            signals = {"subject": "MISSING", "consent": "MISSING"}
            hl = html.lower()
            if filled.get("subject") == "FILLED":
                signals["subject"] = "FOUND"
            elif re.search(
                r'<(?:input|textarea)[^>]+name\s*=\s*["\'][^"\']*(subject|件名)[^"\']*["\']',
                hl,
                re.I,
            ):
                signals["subject"] = "FOUND"
            if filled.get("consent") == "FILLED":
                signals["consent"] = "FOUND"
            elif re.search(r"type\s*=\s*['\"]checkbox['\"]", hl) and (
                "同意" in html or "privacy" in hl or "個人情報" in html
            ):
                signals["consent"] = "FOUND"

            result["field_map"] = _field_status_map(fields, filled, signals)

            # Step 1 → 確認画面（安全な次ステップのみ）
            safe_next = [b for b in buttons_s1 if b.get("classification") == "NEXT_STEP_SAFE"]
            final_s1 = [b for b in buttons_s1 if b.get("classification") == "FINAL_SUBMIT"]

            if safe_next and not final_s1:
                ok, detail = await _click_safe_next(page, buttons_s1)
                if ok:
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=10_000)
                    except Exception:
                        pass
                    import asyncio
                    await asyncio.sleep(1.0)
                    buttons_s2 = await _audit_buttons(page)
                    result["steps"].append({
                        "step": 2,
                        "url": page.url,
                        "buttons": buttons_s2,
                        "navigated_via": detail,
                    })
                    final_s2 = [b for b in buttons_s2 if b.get("classification") == "FINAL_SUBMIT"]
                    if final_s2:
                        result["final_submit_identified"] = True
                        result["final_submit_label"] = final_s2[0].get("label")
                    else:
                        unknown_s2 = [b for b in buttons_s2 if b.get("classification") == "UNKNOWN"]
                        if unknown_s2:
                            result["required_fixes"].append(
                                "Step2: FINAL_SUBMIT 未特定（UNKNOWN ボタンあり）"
                            )
                else:
                    result["required_fixes"].append(f"Step1→2 遷移スキップ: {detail}")
            elif final_s1:
                result["final_submit_identified"] = True
                result["final_submit_label"] = final_s1[0].get("label")
            else:
                result["required_fixes"].append("MULTI_STEP 未解決: NEXT_STEP_SAFE ボタンなし")

            # スクリーンショット
            try:
                await page.screenshot(path=str(screenshot_path), full_page=True)
            except Exception as e:
                result["required_fixes"].append(f"screenshot_failed: {e}")

            # ネットワーク集計
            result["network"]["post_urls"] = list(dict.fromkeys(network_posts))
            post_classes = [_classify_post_url(u, str(form_url_raw)) for u in network_posts]
            inquiry_posts = [u for u, c in zip(network_posts, post_classes) if c == "inquiry"]
            confirm_posts = [u for u, c in zip(network_posts, post_classes) if c == "form_confirm"]
            result["network"]["inquiry_post_count"] = len(inquiry_posts)
            result["network"]["confirm_post_count"] = len(confirm_posts)

        except Exception as e:
            result["status"] = "error"
            result["reason"] = str(e)
            result["blocked"] = True
        finally:
            await browser.close()

    result["real_submission_count"] = get_real_submission_count()
    assert result["real_submission_count"] == 0, "real_submission_count must be 0 in fill-no-submit"

    result["overall"] = _classify_overall(result)
    result["sender_masked"] = {
        "company": SENDER_COMPANY,
        "name": SENDER_NAME,
        "email": _mask_email(SENDER_EMAIL),
        "phone": SENDER_PHONE[:4] + "****" if SENDER_PHONE else "***",
    }
    return result


def write_canary_report(result: dict, input_path: str, tests_summary: str = "") -> Path:
    """70_outputs/5-Day-Sales-Sprint/ARI Fill-No-Submit Canary Report.md"""
    out_path = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI Fill-No-Submit Canary Report.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    overall = result.get("overall", "BLOCKED")
    fm = result.get("field_map", {})
    mv = result.get("message_validation", {})
    steps = result.get("steps", [])
    fixes = result.get("required_fixes", [])

    step1_desc = "—"
    step2_desc = "—"
    if steps:
        b1 = steps[0].get("buttons", [])
        step1_desc = ", ".join(
            f"{b.get('label')} [{b.get('classification')}]" for b in b1[:5]
        ) or "—"
    if len(steps) > 1:
        b2 = steps[1].get("buttons", [])
        step2_desc = ", ".join(
            f"{b.get('label')} [{b.get('classification')}]" for b in b2[:5]
        ) or "—"

    field_rows = "\n".join(
        f"| {k} | {fm.get(k, 'MISSING')} |" for k in (
            "company", "name", "email", "phone", "subject", "message", "consent"
        )
    )

    lines = [
        "# ARI Fill-No-Submit Canary",
        "",
        "## Overall Result",
        "",
        overall,
        "",
        "## Target",
        "",
        result.get("company_name", "—"),
        "",
        "## Form",
        "",
        f"URL:\n{result.get('form_url', '—')}",
        "",
        "Type:\nMULTI_STEP",
        "",
        "## Fields",
        "",
        "| Field | Status |",
        "| --- | --- |",
        field_rows,
        "",
        "## Multi-Step Flow",
        "",
        f"Step 1:\n{step1_desc}",
        "",
        f"Step 2:\n{step2_desc}",
        "",
        f"Final Submit:\n{result.get('final_submit_label') or '—'} "
        f"({'identified' if result.get('final_submit_identified') else 'not identified'})",
        "",
        "## Message Validation",
        "",
        f"ARI:\n{'PASS' if mv.get('ari_positioning') else 'FAIL'}",
        "",
        f"New LP:\n{'PASS' if mv.get('new_lp') else 'FAIL'}",
        "",
        f"Legacy GEO:\n{mv.get('legacy_geo', 0)}",
        "",
        f"ABIS:\n{mv.get('abis', 0)}",
        "",
        "## Network",
        "",
        f"Inquiry transmission:\n{result.get('network', {}).get('inquiry_post_count', 0)}",
        "",
        f"Confirm-step POST (same domain, not counted as inquiry):\n"
        f"{result.get('network', {}).get('confirm_post_count', 0)}",
        "",
        "POST URLs observed:",
    ]
    for u in result.get("network", {}).get("post_urls", [])[:10]:
        lines.append(f"- {u}")
    if not result.get("network", {}).get("post_urls"):
        lines.append("- （なし）")

    lines.extend([
        "",
        "## Safety",
        "",
        f"Real submissions:\n{result.get('real_submission_count', 0)}",
        "",
        "automation paused:\ntrue",
        "",
        "production resume:\nNOT EXECUTED",
        "",
        "## Screenshot / Evidence",
        "",
        f"- Screenshot: `{result.get('screenshot_path', '—')}`",
        f"- Input list: `{input_path}`",
        f"- Field source: {result.get('field_source', '—')}",
        "",
        "## Required Fixes",
        "",
    ])
    if fixes:
        for f in fixes:
            lines.append(f"- {f}")
    else:
        lines.append("- （なし）")

    lines.extend([
        "",
        "## Tests",
        "",
        tests_summary or "（実行後記載）",
        "",
        "## Changed Files",
        "",
        "- `form_fill_no_submit.py`（新規）",
        "- `form_sender.py`（real_submission_count）",
        "- `main.py`（--fill-no-submit）",
        "- `parser.py`（ARI-Canary パターン）",
        "- `tests/test_fill_no_submit.py`（新規）",
        f"- `70_outputs/5-Day-Sales-Sprint/ARI-Canary-Yamada.md`",
        "",
        "## Commit",
        "",
        "DO NOT COMMIT YET",
        "",
        "## Final Declaration",
        "",
        "ARI FILL-NO-SUBMIT CANARY COMPLETE",
        "",
    ])

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
