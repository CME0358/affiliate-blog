"""
fill_compat.py — visible/enabled fill contract + honeypot exclusion.
"""

from __future__ import annotations

from typing import Any

VISIBLE_EDITABLE = "VISIBLE_EDITABLE"
VISIBLE_READONLY = "VISIBLE_READONLY"
HIDDEN_SYSTEM = "HIDDEN_SYSTEM"
HIDDEN_HONEYPOT = "HIDDEN_HONEYPOT"
DISABLED = "DISABLED"
UNKNOWN = "UNKNOWN"

_CLASSIFY_FIELD_STATE_JS = r"""
(selector) => {
  if (!selector) return { state: 'UNKNOWN', editable: false };
  const el = document.querySelector(selector);
  if (!el) return { state: 'UNKNOWN', editable: false };
  const tag = el.tagName.toLowerCase();
  const type = (el.getAttribute('type') || '').toLowerCase();
  if (type === 'hidden') return { state: 'HIDDEN_SYSTEM', editable: false };
  const st = window.getComputedStyle(el);
  const idn = ((el.id || '') + ' ' + (el.name || '')).toLowerCase();
  const cls = (el.className || '').toLowerCase();
  const ac = (el.getAttribute('autocomplete') || '').toLowerCase();
  const ariaHidden = el.getAttribute('aria-hidden') === 'true';
  const tabIdx = el.getAttribute('tabindex');
  const offscreen = (() => {
    const r = el.getBoundingClientRect();
    return r.width < 2 && r.height < 2;
  })();
  const honeypotHint = ['honeypot', 'hp-field', 'bot-trap', 'spam-block'].some(
    (k) => idn.includes(k) || cls.includes(k)
  );
  const honeypotName = ['website', 'url', 'homepage'].some((k) => idn === k || idn.endsWith(' ' + k));
  if (honeypotHint || (honeypotName && (offscreen || st.display === 'none'))) {
    return { state: 'HIDDEN_HONEYPOT', editable: false };
  }
  if (el.disabled) return { state: 'DISABLED', editable: false };
  if (el.readOnly && tag !== 'select') return { state: 'VISIBLE_READONLY', editable: false };
  if (st.display === 'none' || st.visibility === 'hidden' || ariaHidden || offscreen) {
    return { state: 'HIDDEN_SYSTEM', editable: false };
  }
  if (ac === 'off' && offscreen) return { state: 'HIDDEN_HONEYPOT', editable: false };
  if (tabIdx === '-1' && offscreen) return { state: 'HIDDEN_HONEYPOT', editable: false };
  return { state: 'VISIBLE_EDITABLE', editable: true };
}
"""


async def classify_field_state(page, selector: str) -> dict[str, Any]:
    try:
        raw = await page.evaluate(_CLASSIFY_FIELD_STATE_JS, selector)
        return raw if isinstance(raw, dict) else {"state": UNKNOWN, "editable": False}
    except Exception:
        return {"state": UNKNOWN, "editable": False}


async def safe_fill(page, selector: str, value: str) -> tuple[bool, str]:
    """Fill only when field is visible, enabled, and user-editable."""
    if not selector or not value:
        return False, "empty_selector_or_value"
    try:
        from ari_pipeline.pf_rf_hardening import nf_pf_fill, nf_pf_mode_active, PfDefer, PfFastFail
        if nf_pf_mode_active():
            await nf_pf_fill(page, selector, value)
            return True, VISIBLE_EDITABLE
    except (PfDefer, PfFastFail):
        raise
    except ImportError:
        pass
    state = await classify_field_state(page, selector)
    if not state.get("editable"):
        return False, state.get("state") or UNKNOWN
    try:
        tag = await page.eval_on_selector(selector, "el => el.tagName.toLowerCase()")
    except Exception:
        return False, "element_not_found"
    if tag == "select":
        return False, "select_not_text_fill"
    try:
        await page.fill(selector, value)
        return True, VISIBLE_EDITABLE
    except Exception as exc:
        return False, str(exc)[:120]


async def safe_fill_optional(page, selector: str, value: str) -> tuple[bool, str]:
    """Like safe_fill but returns (False, reason) without raising on skip."""
    return await safe_fill(page, selector, value)
