"""
multistep_state.py — multi-step form state detection and validation feedback.
"""

from __future__ import annotations

from typing import Any

FORM_ENTRY = "FORM_ENTRY"
VALIDATION_FAILED = "VALIDATION_FAILED"
CONFIRMATION = "CONFIRMATION"
FINAL_SUBMIT_READY = "FINAL_SUBMIT_READY"

_DETECT_STATE_JS = r"""
() => {
  const html = document.body ? document.body.innerText : '';
  const hl = html.toLowerCase();
  const confirmSignals = ['入力内容の確認', '入力内容確認', '確認画面', '送信内容の確認', '内容をご確認'];
  const validationSignals = ['必須項目', '選択してください', '入力してください', 'ご確認ください', 'エラー'];
  const hasConfirm = confirmSignals.some(s => html.includes(s));
  const hasValidation = validationSignals.some(s => html.includes(s))
    || document.querySelector('[aria-invalid="true"], .error, .errPosRight:not(:empty), .validation-error, .form-error');
  const finalBtn = Array.from(document.querySelectorAll('button, input[type="submit"]')).find(el => {
    const t = ((el.value || '') + ' ' + (el.textContent || '')).replace(/\s+/g, ' ');
    return (t.includes('送信') && !t.includes('確認画面') && !t.includes('内容の確認'))
      || t.trim() === '送信' || t.includes('送信する');
  });
  const backBtn = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"]')).find(el => {
    const t = ((el.value || '') + ' ' + (el.textContent || '')).toLowerCase();
    return t.includes('戻る') || t.includes('修正');
  });
  if (finalBtn && (hasConfirm || backBtn)) return 'FINAL_SUBMIT_READY';
  if (hasConfirm) return 'CONFIRMATION';
  if (hasValidation) return 'VALIDATION_FAILED';
  return 'FORM_ENTRY';
}
"""

_PARSE_VALIDATION_JS = r"""
() => {
  const errors = [];
  document.querySelectorAll('[aria-invalid="true"], .error, .validation-error, .form-error, .errMsg, .error-message').forEach(el => {
    const txt = (el.textContent || '').replace(/\s+/g, ' ').trim();
    if (txt && txt.length < 200) errors.push(txt);
  });
  document.querySelectorAll('label, th, dt, .required').forEach(el => {
    const txt = (el.textContent || '').replace(/\s+/g, ' ').trim();
    if (txt.includes('必須') && txt.length < 100) errors.push(txt);
  });
  return [...new Set(errors)].slice(0, 15);
}
"""


def detect_multistep_state(html: str, *, page_state: str | None = None) -> str:
    if page_state:
        return page_state
    hl = html.lower()
    if any(k in html for k in ("入力内容の確認", "確認画面", "送信内容の確認")):
        if any(k in html for k in ("送信する", "送　信", "この内容で送信")):
            return FINAL_SUBMIT_READY
        return CONFIRMATION
    if any(k in html for k in ("必須項目", "選択してください", "入力してください")):
        return VALIDATION_FAILED
    if "aria-invalid" in hl or "validation-error" in hl:
        return VALIDATION_FAILED
    return FORM_ENTRY


async def detect_multistep_state_dom(page) -> str:
    from mw_wp_form_state import MW_COMPLETE, MW_CONFIRMATION, probe_mw_wp_form_state_dom
    mw = await probe_mw_wp_form_state_dom(page)
    if mw.get("state") == MW_CONFIRMATION:
        return FINAL_SUBMIT_READY
    if mw.get("state") == MW_COMPLETE:
        return CONFIRMATION
    try:
        state = await page.evaluate(_DETECT_STATE_JS)
        return state if state in (FORM_ENTRY, VALIDATION_FAILED, CONFIRMATION, FINAL_SUBMIT_READY) else FORM_ENTRY
    except Exception:
        return FORM_ENTRY


async def parse_validation_errors(page) -> list[str]:
    try:
        raw = await page.evaluate(_PARSE_VALIDATION_JS)
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


async def run_validation_feedback_once(page, choice_log: dict[str, Any]) -> dict[str, Any]:
    """
    One retry: re-apply rational choices if validation failed.
    Does not click final submit.
    """
    state = await detect_multistep_state_dom(page)
    errors = await parse_validation_errors(page)
    if state != VALIDATION_FAILED and not errors:
        return {"state": state, "errors": errors, "retried": False}

    from required_choice_resolver import apply_rational_required_choices

    retry_log = await apply_rational_required_choices(page)
    choice_log["validation_retry"] = retry_log
    return {
        "state": await detect_multistep_state_dom(page),
        "errors": errors,
        "retried": True,
    }
