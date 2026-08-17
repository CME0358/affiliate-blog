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
from form_scope import is_search_form_meta
from fill_compat import safe_fill
from form_field_resolver import (
    classify_form_analysis_failure,
    extract_partial_fields_from_dom,
    resolve_form_fields,
)
from message_variant import (
    format_selection_log_line,
    resolve_ari_message_for_form,
    selection_as_dict,
)
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

# Button classification constants (exported for tests)
BACK = "BACK"
NEXT_STEP_SAFE = "NEXT_STEP_SAFE"
FINAL_SUBMIT = "FINAL_SUBMIT"
UNKNOWN = "UNKNOWN"

_BACK_KW = (
    "戻る",
    "back",
    "submitback",
    "btn_back",
    "go-back",
    "return",
)
_BACK_KW_STRICT = (
    "修正",
    "cancel",
    "訂正",
)

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

_CONFIRM_ACTION_FRAGMENTS = (
    "/confirm",
    "confirmation",
    "confirm.php",
    "/conf/",
    "/pre/",
    "/preview",
    "pre.php",
    "/check",
)

_UNSUITABLE_DOM_FIELD_FRAGMENTS = (
    "spam-block",
    "honeypot",
    "image_auth",
    "image-auth",
    "quiz-",
    "cf-turnstile",
    "g-recaptcha",
)

_AUDIT_BUTTONS_IN_SCOPE_JS = r"""
(scope) => {
  const visible = (el) => {
    if (!el || !(el instanceof Element)) return false;
    const st = window.getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') return false;
    const r = el.getBoundingClientRect();
    return r.width >= 2 && r.height >= 2;
  };
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const items = [];
  let roots = [];
  if (scope) {
    const scoped = document.querySelector(scope);
    if (scoped) roots = [scoped];
  }
  if (!roots.length) {
    const forms = document.querySelectorAll('form');
    roots = forms.length ? Array.from(forms) : [document.body];
  }
  const sel = 'button, input[type="submit"], input[type="button"], input[type="image"], [role="button"], a[role="button"], a.btn, a.button';
  for (const root of roots) {
    for (const el of root.querySelectorAll(sel)) {
      if (!visible(el)) continue;
      const name = el.getAttribute('name') || '';
      const id = el.id || '';
      const cls = (el.getAttribute('class') || '').trim();
      const label = norm(
        (el.innerText || '') + ' ' + (el.textContent || '') + ' ' + (el.value || '') + ' '
        + (el.getAttribute('alt') || '') + ' ' + name + ' ' + cls
        + ' ' + (el.getAttribute('data-action') || '') + ' ' + (el.getAttribute('aria-label') || '')
      );
      if (!label || label.length > 120) continue;
      const tag = el.tagName.toLowerCase();
      const type = (el.getAttribute('type') || '').toLowerCase();
      const form = el.closest('form');
      let css = '';
      if (scope && id) css = scope + ' #' + CSS.escape(id);
      else if (scope && name && (type === 'submit' || type === 'button' || tag === 'button')) {
        const esc = name.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
        css = scope + ' ' + tag + '[name="' + esc + '"]';
      } else if (id) css = '#' + CSS.escape(id);
      else if (name && (type === 'submit' || type === 'button' || tag === 'button')) {
        const esc = name.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
        css = tag + '[name="' + esc + '"]';
      } else if (form && form.id && type === 'submit') {
        css = 'form#' + CSS.escape(form.id) + ' ' + tag + '[type="submit"]';
      } else if (form && (form.className || '').includes('cc-m-form') && type === 'submit') {
        css = 'form.cc-m-form ' + tag + '[type="submit"]';
      } else if (form && type === 'submit') {
        css = 'form ' + tag + '[type="submit"]';
      } else if (cls) {
        const c = cls.split(/\s+/)[0];
        if (c) css = tag + '.' + CSS.escape(c);
      }
      items.push({
        label, tag, type, selector: css || tag,
        id: id || null, name: name || null,
        className: cls.slice(0, 200) || null,
        value: (el.value || '').slice(0, 80) || null,
        disabled: !!el.disabled,
        ariaDisabled: (el.getAttribute('aria-disabled') || '').toLowerCase() === 'true',
        onclick: el.getAttribute('onclick') ? 'yes' : null,
        formId: form ? (form.id || null) : null,
        formAction: form ? (form.getAttribute('action') || null) : null,
        domOrder: items.length,
      });
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

from consent_detector import (
    CONSENT_DETECT_AND_FILL_JS,
    FIND_CONSENT_JS as _FIND_CONSENT_JS,
    consent_fill_status,
)
from multistep_state import (
    CONFIRMATION,
    FINAL_SUBMIT_READY,
    VALIDATION_FAILED,
    detect_multistep_state_dom,
    run_validation_feedback_once,
)
from required_choice_resolver import apply_rational_required_choices

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


def classify_button_action(
    label: str,
    btn_type: str = "",
    *,
    name: str = "",
    el_id: str = "",
    form_action: str = "",
    page_url: str = "",
    class_name: str = "",
) -> str:
    """BACK | NEXT_STEP_SAFE | FINAL_SUBMIT | UNKNOWN"""
    t = (label or "").strip().lower()
    btn_type = (btn_type or "").lower()
    name_l = (name or "").lower()
    id_l = (el_id or "").lower()
    cls_l = (class_name or "").lower()
    blob = f"{t} {name_l} {id_l} {cls_l}"
    action_l = (form_action or "").lower()
    page_l = (page_url or "").lower()
    on_confirm_page = any(f in page_l for f in _CONFIRM_ACTION_FRAGMENTS)
    action_targets_confirm = any(f in action_l for f in _CONFIRM_ACTION_FRAGMENTS)

    if any(x in blob for x in _BACK_KW):
        return BACK
    if any(x in t for x in _BACK_KW_STRICT) and "送信" not in t:
        return BACK

    if action_targets_confirm and not on_confirm_page:
        return NEXT_STEP_SAFE

    if "submitconfirm" in name_l or (name_l == "confirm" and btn_type == "submit"):
        return NEXT_STEP_SAFE if not on_confirm_page else FINAL_SUBMIT

    if any(k in cls_l for k in ("btn-confirm", "confirm", "form_submit", "btn-submit")):
        if action_targets_confirm and not on_confirm_page:
            return NEXT_STEP_SAFE
        if on_confirm_page and "submit" in cls_l:
            return FINAL_SUBMIT

    if any(k.lower() in t for k in _FINAL_KW):
        if any(k.lower() in t for k in _NEXT_KW):
            if "送信" in t and "確認" not in t.replace("送信", "", 1):
                return FINAL_SUBMIT
        else:
            return FINAL_SUBMIT

    if "送信" in t and "確認" not in t:
        return FINAL_SUBMIT

    if any(k.lower() in t for k in _NEXT_KW):
        return NEXT_STEP_SAFE

    if btn_type == "submit" and "確認" in t:
        return NEXT_STEP_SAFE

    if btn_type == "submit" and ("submit" in id_l or "form_submit" in cls_l):
        if action_targets_confirm and not on_confirm_page:
            return NEXT_STEP_SAFE
        return FINAL_SUBMIT

    if btn_type == "submit":
        return UNKNOWN

    return UNKNOWN


def validate_ari_message(message: str) -> dict[str, Any]:
    """ARI 文面検証."""
    checks = {
        "ari_positioning": "Agent Readiness" in message,
        "new_lp": "readiness.coaretail.com/report/" in message,
        "new_copy": (
            "Agent Readiness Company Report" in message
            and "佐々木" in message
            and "SEOやMEO" in message
        ),
        "tiktok_url": "tiktok.com/@coaretail/video/7646962366919265543" in message,
        "legacy_geo": message.count("localgeo.coaretail.com"),
        "old_geo_pitch": message.count("GEO Search Protocol") + message.count("無料診断") + message.count("無料AI推薦"),
        "competitor_wording": message.count("競合比較") + message.count("競合スコア") + message.count("業界平均比較"),
        "abis": message.count("ABIS"),
        "ranking_guarantee": message.count("ranking guarantee") + message.count("順位保証"),
        "traffic_guarantee": message.count("traffic guarantee") + message.count("流入保証"),
        "sales_guarantee": message.count("sales guarantee") + message.count("売上保証"),
    }
    checks["pass"] = (
        checks["ari_positioning"]
        and checks["new_lp"]
        and checks["new_copy"]
        and checks["tiktok_url"]
        and checks["legacy_geo"] == 0
        and checks["old_geo_pitch"] == 0
        and checks["competitor_wording"] == 0
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

    def _norm(val: str) -> str:
        if isinstance(val, str) and val.startswith("SKIPPED"):
            return "MISSING"
        return val

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
            out[logical] = _norm(filled.get(logical, "FOUND"))
        else:
            out[logical] = "MISSING"
    out["subject"] = _norm(filled.get("subject", signals.get("subject", "MISSING")))
    consent_val = filled.get("consent", signals.get("consent", "MISSING"))
    out["consent"] = consent_val
    return out


from shared_form_prepare import (
    _fill_standard_fields,
    build_canonical_prepared_snapshot,
    build_semantic_evidence_record,
    compute_mapping_hash,
    shared_prepare_form,
)


async def _wait_fill_settle(page, ms: int = 800) -> None:
    try:
        await page.wait_for_timeout(ms)
    except Exception:
        pass
    try:
        await page.evaluate(
            "() => new Promise(r => {"
            "if (document.readyState === 'complete') { r(true); return; }"
            "window.addEventListener('load', () => r(true), { once: true });"
            "setTimeout(() => r(true), 500);"
            "})"
        )
    except Exception:
        pass


def _is_search_form_button(btn: dict) -> bool:
    meta = {"action": btn.get("formAction"), "id": btn.get("formId")}
    if is_search_form_meta(meta):
        return True
    name = (btn.get("name") or "").lower()
    if name == "s":
        return True
    fid = (btn.get("formId") or "").lower()
    if any(k in fid for k in ("search", "keni_search")):
        return True
    action = (btn.get("formAction") or "").lower()
    if "?s=" in action or "&s=" in action:
        return True
    cls = (btn.get("className") or "").lower()
    if "searchform" in cls or "search-form" in cls:
        return True
    return False


async def _audit_buttons(page, contact_scope: str | None = None) -> list[dict]:
    if contact_scope:
        raw = await page.evaluate(_AUDIT_BUTTONS_IN_SCOPE_JS, contact_scope)
    else:
        raw = await page.evaluate(_AUDIT_BUTTONS_IN_SCOPE_JS, None)
    page_url = page.url
    out = []
    for b in raw or []:
        if _is_search_form_button(b):
            continue
        cls = classify_button_action(
            b.get("label", ""),
            b.get("type", ""),
            name=b.get("name") or "",
            el_id=b.get("id") or "",
            form_action=b.get("formAction") or "",
            page_url=page_url,
            class_name=b.get("className") or "",
        )
        out.append({**b, "classification": cls})
    return out


_UNSUITABLE_REQUIRED_LABEL_JS = r"""
() => {
  const patterns = [
    '顧客番号', '契約番号', '予約番号', '会員番号', 'お客様番号', '顧客ID', '会員ID',
    '紹介者', '案件番号', '注文番号', '保証番号', '受付番号', 'お客様ID',
  ];
  const found = [];
  for (const el of document.querySelectorAll('input, textarea, select')) {
    const row = el.closest('tr, dl, li, div') || el.parentElement;
    const label = (
      (row && row.querySelector('th, dt, label') ? row.querySelector('th, dt, label').innerText : '')
      + ' ' + (el.placeholder || '') + ' ' + (el.name || '')
    ).trim();
    if (patterns.some((p) => label.includes(p))) {
      found.push(label.slice(0, 80));
    }
  }
  return [...new Set(found)];
}
"""

_UNSUITABLE_FIELD_DETECT_JS = r"""
() => {
  const out = [];
  for (const el of document.querySelectorAll('input, textarea, select')) {
    const name = (el.name || '').toLowerCase();
    const cls = (el.className || '').toLowerCase();
    const id = (el.id || '').toLowerCase();
    const blob = name + ' ' + cls + ' ' + id;
    const patterns = ['spam-block', 'honeypot', 'image_auth', 'image-auth', 'quiz', 'turnstile', 'recaptcha'];
    if (patterns.some((p) => blob.includes(p))) {
      out.push({ name: el.name || '', className: el.className || '', id: el.id || '' });
    }
  }
  return out;
}
"""


async def detect_unsuitable_form_fields(page) -> list[dict]:
    """DOM 上の honeypot / image-auth / spam-block 等を検出。"""
    try:
        raw = await page.evaluate(_UNSUITABLE_FIELD_DETECT_JS)
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


def pick_final_submit_button(buttons: list[dict]) -> tuple[dict | None, str]:
    """BACK 共存時も FINAL_SUBMIT を1件選択。戻るボタンは除外。"""
    finals = [b for b in buttons if b.get("classification") == FINAL_SUBMIT]
    if len(finals) == 1:
        return finals[0], ""
    if len(finals) > 1:
        return None, f"final_submit_ambiguous:{len(finals)}"
    return None, "final_submit_not_found"


async def click_final_submit_button(
    page,
    buttons: list[dict] | None = None,
) -> tuple[bool, str, dict | None]:
    """FINAL_SUBMIT 分類ボタンのみクリック。BACK はクリックしない。"""
    if buttons is None:
        buttons = await _audit_buttons(page)
    btn, err = pick_final_submit_button(buttons)
    if not btn:
        backs = [b for b in buttons if b.get("classification") == BACK]
        if backs and not [b for b in buttons if b.get("classification") == FINAL_SUBMIT]:
            return False, "back_only_no_final_submit", None
        return False, err or "final_submit_not_found", None

    label = btn.get("label", "")
    sel = (btn.get("selector") or "").strip()
    if sel:
        try:
            await page.click(sel, timeout=8_000)
            return True, label, btn
        except Exception:
            pass
    try:
        clicked = await page.evaluate(
            """(target) => {
              const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
              const backKws = ['戻る', 'back', 'submitback', '修正', 'cancel'];
              const isBack = (t) => backKws.some((k) => t.toLowerCase().includes(k)) && !t.includes('送信');
              const sel = 'button, input[type="submit"], input[type="button"], [role="button"]';
              const forms = document.querySelectorAll('form');
              const roots = forms.length ? forms : [document.body];
              for (const root of roots) {
                for (const el of root.querySelectorAll(sel)) {
                  const t = norm((el.innerText || '') + ' ' + (el.textContent || '') + ' ' + (el.value || '') + ' ' + (el.getAttribute('name') || ''));
                  if (isBack(t)) continue;
                  if (target.selector && el.matches && el.matches(target.selector.split(' ').slice(-1)[0].replace(/^[^.]+\\./, '.'))) {
                    el.click(); return true;
                  }
                  if (t.includes('送信') || t === target.label || target.label.includes(t)) {
                    if (t.includes('確認') && !t.includes('送信')) continue;
                    el.click();
                    return true;
                  }
                }
              }
              return false;
            }""",
            {"label": label, "selector": sel},
        )
        if clicked:
            return True, label, btn
    except Exception as e:
        return False, str(e), btn
    return False, "final_submit_click_failed", btn


_SELECT_INQUIRY_RADIOS_JS = r"""
() => {
  const prefer = ['その他', '一般', 'ご相談', 'お問い合わせ', '法人', '個人'];
  let clicked = 0;
  const groups = new Map();
  for (const el of document.querySelectorAll('input[type="radio"]')) {
    const name = el.name;
    if (!name) continue;
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(el);
  }
  for (const [, radios] of groups) {
    let picked = null;
    for (const el of radios) {
      const row = el.closest('tr, li, label, div') || el.parentElement;
      const txt = ((row && row.textContent) || '') + ' ' + (el.id || '');
      for (const p of prefer) {
        if (txt.includes(p)) { picked = el; break; }
      }
      if (picked) break;
    }
    if (picked && !picked.checked) {
      picked.click();
      clicked += 1;
    }
  }
  return clicked;
}
"""


def _is_auxiliary_unknown_button(btn: dict) -> bool:
    label = (btn.get("label") or "").lower()
    cls = (btn.get("className") or "").lower()
    return any(
        k in label or k in cls
        for k in ("住所検索", "zip2addr", "自動住所", "郵便", "search", "aid")
    )


async def _fill_corporate_company_if_needed(
    page,
    choice_log: dict,
    fields: dict,
) -> None:
    """法人選択後に company / 法人名フィールドを補完。"""
    applied = choice_log.get("applied") or []
    corporate = any(
        a.get("category") == "CUSTOMER_TYPE"
        and "法人" in (a.get("label") or "")
        for a in applied
    )
    if not corporate:
        return
    if fields.get("company_field"):
        await safe_fill(page, fields["company_field"], SENDER_COMPANY)
        return
    try:
        sel = await page.evaluate(
            r"""() => {
              const kws = ['法人名', 'company', 'corp'];
              for (const el of document.querySelectorAll('input, textarea')) {
                const blob = (
                  (el.name || '') + ' ' + (el.id || '') + ' ' + (el.placeholder || '')
                  + ' ' + ((el.labels && el.labels[0] && el.labels[0].textContent) || '')
                ).toLowerCase();
                if (kws.some(k => blob.includes(k))) {
                  if (el.name) return '[name="' + el.name.replace(/"/g, '\\"') + '"]';
                  if (el.id) return '#' + el.id;
                }
              }
              return null;
            }"""
        )
        if sel:
            await safe_fill(page, sel, SENDER_COMPANY)
    except Exception:
        pass


async def _prepare_dynamic_form_fields(page, contact_scope: str | None = None) -> dict:
    try:
        return await apply_rational_required_choices(page, scope_selector=contact_scope)
    except Exception:
        return {"applied": [], "skipped": [], "unsuitable": []}


_CLICK_IN_SCOPE_JS = r"""
(args) => {
  const { scope, name, tag, type, selector } = args;
  const root = scope ? document.querySelector(scope) : document;
  if (!root) return false;
  let el = null;
  if (name) {
    el = root.querySelector((tag || 'input') + '[name="' + name.replace(/"/g, '\\"') + '"]');
  }
  if (!el && selector) {
    const local = selector.replace(/^form[^ ]*\\s+/, '');
    el = root.querySelector(local) || root.querySelector(selector);
  }
  if (!el && (type || tag)) {
    el = root.querySelector((tag || 'button') + '[type="' + (type || 'submit') + '"]');
  }
  if (el) { el.click(); return true; }
  return false;
}
"""


async def _click_button_scoped(page, btn: dict, contact_scope: str | None) -> bool:
    """Contact form 内のボタンのみクリック（search form 誤クリック防止）。"""
    if _is_search_form_button(btn):
        return False
    name = btn.get("name")
    sel = (btn.get("selector") or "").strip()
    tag = btn.get("tag") or "input"
    btn_type = btn.get("type") or "submit"
    candidates: list[str] = []
    if contact_scope and name:
        esc = name.replace("\\", "\\\\").replace('"', '\\"')
        candidates.append(f'{contact_scope} {tag}[name="{esc}"]')
        if btn_type:
            candidates.append(f'{contact_scope} {tag}[type="{btn_type}"][name="{esc}"]')
    if sel and contact_scope:
        if sel.startswith("form ") or sel.startswith("form."):
            local = sel.split(" ", 1)[1] if " " in sel else sel
            candidates.append(f"{contact_scope} {local}")
        elif not sel.startswith(contact_scope):
            candidates.append(f"{contact_scope} {sel}")
        else:
            candidates.append(sel)
    elif sel:
        candidates.append(sel)
    for css in candidates:
        try:
            await page.click(css, timeout=8_000)
            return True
        except Exception:
            continue
    try:
        clicked = await page.evaluate(
            _CLICK_IN_SCOPE_JS,
            {
                "scope": contact_scope,
                "name": name,
                "tag": tag,
                "type": btn_type,
                "selector": sel,
            },
        )
        if clicked:
            return True
    except Exception:
        pass
    if name and not _is_search_form_button(btn):
        esc = name.replace("\\", "\\\\").replace('"', '\\"')
        try:
            await page.click(f'{tag}[name="{esc}"]', timeout=8_000)
            return True
        except Exception:
            pass
    return False


async def _click_safe_next(
    page,
    buttons: list[dict],
    contact_scope: str | None = None,
) -> tuple[bool, str]:
    """NEXT_STEP_SAFE ボタンのみクリック。曖昧なら停止。"""
    safe = [b for b in buttons if b.get("classification") == NEXT_STEP_SAFE]
    final = [b for b in buttons if b.get("classification") == FINAL_SUBMIT]
    unknown = [b for b in buttons if b.get("classification") == UNKNOWN]

    if final:
        return False, "final_submit_visible_no_click"

    if len(safe) != 1:
        if safe:
            return False, f"ambiguous_next_step_count_{len(safe)}"
        if unknown:
            return False, "unknown_buttons_only"
        return False, "no_safe_next_button"

    if unknown:
        blocking = [b for b in unknown if not _is_auxiliary_unknown_button(b)]
        if blocking:
            return False, "unknown_buttons_present"

    btn = safe[0]
    label = btn.get("label", "")
    if await _click_button_scoped(page, btn, contact_scope):
        return True, label
    return False, "safe_next_click_failed"


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

    submission_count_at_start = get_real_submission_count()

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
        "message_validation": {},
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
            from submission_state import _html_signals
            _, _, captcha_sig = _html_signals(html)
            if captcha_sig:
                result["captcha_detected"] = True
                result["status"] = "skipped"
                result["reason"] = "captcha_detected"
                result["blocked"] = True
                await browser.close()
                return result

            unsuitable = await detect_unsuitable_form_fields(page)
            if unsuitable:
                result["form_not_suitable"] = True
                result["unsuitable_fields"] = unsuitable
                result["status"] = "skipped"
                result["reason"] = "form_not_suitable"
                result["blocked"] = True
                await browser.close()
                return result

            try:
                bad_labels = await page.evaluate(_UNSUITABLE_REQUIRED_LABEL_JS)
                if bad_labels:
                    result["unsuitable_required_labels"] = bad_labels
            except Exception:
                pass

            prep = await shared_prepare_form(
                page,
                str(form_url_raw).strip(),
                message,
                lp_url,
                allow_validation_fallback=True,
                html=html,
            )
            result["field_source"] = prep.field_source
            result["contact_form_scope"] = prep.contact_form_scope
            result["preflight_mapping_hash"] = prep.mapping_hash
            result["prepare_snapshot"] = prep.snapshot
            canonical = build_canonical_prepared_snapshot(
                form_url=str(form_url_raw).strip(),
                fields=prep.fields or {},
                filled=prep.filled or {},
                choice_log=prep.choice_log or {},
                field_map=prep.field_map or {},
                selection=prep.selection,
                contact_form_scope=prep.contact_form_scope,
                submit_target=(prep.fields or {}).get("submit_button"),
            )
            result["semantic_evidence"] = build_semantic_evidence_record(
                canonical_snapshot=canonical,
                source="fill_form_no_submit",
            )
            result["cookie_banner"] = prep.cookie_banner_dismissed
            result["cookie_overlay"] = prep.cookie_overlay

            if prep.blocked or not prep.ok:
                if prep.reason == "form_not_suitable":
                    result["form_not_suitable"] = True
                    result["status"] = "skipped"
                elif prep.reason == "unsuitable_required_choices":
                    result["form_not_suitable"] = True
                    result["status"] = "skipped"
                else:
                    result["status"] = "error" if prep.reason != "compact_message_exceeds_maxlength" else "skipped"
                result["reason"] = prep.reason
                result["blocked"] = True
                if prep.partial_fields:
                    result["partial_fields"] = prep.partial_fields
                await browser.close()
                return result

            fields = prep.fields
            selection = prep.selection
            message = prep.message
            choice_log = prep.choice_log
            filled = prep.filled

            result["message_selection"] = selection_as_dict(selection)
            result.update(selection.to_log_fields())
            result["message_validation"] = prep.message_validation
            result["required_choices"] = choice_log
            result["field_map"] = prep.field_map
            result["final_submit_identified"] = prep.final_submit_identified
            result["final_submit_label"] = prep.final_submit_label
            result["canonical_submit_target"] = prep.canonical_submit_target

            contact_scope = prep.contact_form_scope
            buttons_s1 = prep.buttons or await _audit_buttons(page, contact_scope)
            result["steps"].append({
                "step": 1,
                "url": page.url,
                "buttons": buttons_s1,
            })

            # Skip duplicate field_map computation — already in prep
            signals = {"subject": prep.field_map.get("subject", "MISSING"), "consent": prep.field_map.get("consent", "MISSING")}
            _ = signals  # kept for step2 logic compatibility

            # Step 1 → 確認画面（安全な次ステップのみ）
            safe_next = [b for b in buttons_s1 if b.get("classification") == "NEXT_STEP_SAFE"]
            final_s1 = [b for b in buttons_s1 if b.get("classification") == "FINAL_SUBMIT"]

            if safe_next and not final_s1:
                ok, detail = await _click_safe_next(page, buttons_s1, contact_scope)
                if ok:
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=10_000)
                    except Exception:
                        pass
                    import asyncio
                    await asyncio.sleep(1.5)

                    current_url = page.url
                    if re.search(r"[?&]s=", current_url) and "contact" not in current_url.lower():
                        result["required_fixes"].append("search_form_navigation_leak")
                        result["multistep_state"] = FORM_ENTRY
                    else:
                        state = await detect_multistep_state_dom(page)
                        result["multistep_state"] = state

                        if state == VALIDATION_FAILED:
                            fb = await run_validation_feedback_once(page, choice_log)
                            result["validation_feedback"] = fb
                            await _fill_corporate_company_if_needed(page, choice_log, fields)
                            await _wait_fill_settle(page)
                            ok_retry, detail_retry = await _click_safe_next(
                                page,
                                await _audit_buttons(page, contact_scope),
                                contact_scope,
                            )
                            if ok_retry:
                                await asyncio.sleep(1.5)
                                state = await detect_multistep_state_dom(page)
                                result["multistep_state"] = state
                                detail = f"{detail} → retry:{detail_retry}"

                    buttons_s2 = await _audit_buttons(page, contact_scope)
                    # SPA confirm: URL 変化なしでも送信ボタンが現れるケース
                    if not [b for b in buttons_s2 if b.get("classification") == FINAL_SUBMIT]:
                        confirm_html = (await page.content()).lower()
                        ms = result.get("multistep_state")
                        if ms in (CONFIRMATION, FINAL_SUBMIT_READY) or any(
                            k in confirm_html for k in ("入力内容の確認", "確認画面", "送信内容の確認")
                        ):
                            for b in buttons_s2:
                                lbl = (b.get("label") or "").lower()
                                if "送信" in lbl and "確認" not in lbl.replace("送信", "", 1):
                                    b["classification"] = FINAL_SUBMIT
                                elif lbl.strip() in ("送信", "送信する", "送　信"):
                                    b["classification"] = FINAL_SUBMIT
                    result["steps"].append({
                        "step": 2,
                        "url": page.url,
                        "buttons": buttons_s2,
                        "navigated_via": detail,
                        "multistep_state": result.get("multistep_state"),
                    })
                    final_btn, _ = pick_final_submit_button(buttons_s2)
                    if final_btn:
                        result["final_submit_identified"] = True
                        result["final_submit_label"] = final_btn.get("label")
                    else:
                        unknown_s2 = [b for b in buttons_s2 if b.get("classification") == "UNKNOWN"]
                        backs_s2 = [b for b in buttons_s2 if b.get("classification") == BACK]
                        if backs_s2 and result.get("multistep_state") in (CONFIRMATION, FINAL_SUBMIT_READY):
                            result["required_fixes"].append(
                                "Step2: BACK present but FINAL_SUBMIT not classified"
                            )
                        elif unknown_s2:
                            result["required_fixes"].append(
                                "Step2: FINAL_SUBMIT 未特定（UNKNOWN ボタンあり）"
                            )
                else:
                    result["required_fixes"].append(f"Step1→2 遷移スキップ: {detail}")
            elif final_s1:
                result["final_submit_identified"] = True
                result["final_submit_label"] = final_s1[0].get("label")
            elif safe_next:
                result["required_fixes"].append("MULTI_STEP: NEXT_STEP_SAFE only (no FINAL on step1)")
            else:
                unknown_submit = [
                    b for b in buttons_s1
                    if b.get("type") == "submit" and b.get("classification") == UNKNOWN
                ]
                if unknown_submit:
                    result["required_fixes"].append("dynamic_submit_unresolved")
                else:
                    result["required_fixes"].append("no_final_submit")

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
    assert result["real_submission_count"] == submission_count_at_start, (
        "fill-no-submit must not increment real_submission_count"
    )

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
