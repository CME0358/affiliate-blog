"""
canonical_submit_target.py — Single resolver for authorized FINAL_SUBMIT targets.

Unifies field-resolver submit_button, canonical snapshot submit_target,
production authorization, stale-state validation, and click execution.
"""

from __future__ import annotations

from typing import Any

from multistep_state import FORM_ENTRY, detect_multistep_state_dom
from submit_target_semantics import (
    RESOLUTION_AMBIGUOUS,
    candidate_label,
    resolve_submit_from_candidates,
)

SUBMIT_TARGET_VALID = "VALID"
SUBMIT_TARGET_MISSING = "submit_missing"
SUBMIT_TARGET_OUTSIDE_FORM = "submit_outside_form"
SUBMIT_TARGET_HIDDEN = "submit_hidden"
SUBMIT_TARGET_DISABLED = "submit_disabled"
SUBMIT_TARGET_AMBIGUOUS = "submit_ambiguous"
SUBMIT_TARGET_SCOPE_MISSING = "form_scope_missing"
SUBMIT_TARGET_SELECTOR_INVALID = "selector_invalid"
SUBMIT_TARGET_NEXT_STEP = "next_step_not_final"

_DISCOVER_SUBMIT_CANDIDATES_JS = r"""
(args) => {
  const scope = (args.contact_form_scope || '').trim();
  const hint = (args.submit_selector || '').trim();
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const visible = (el) => {
    if (!el || !(el instanceof Element)) return false;
    const st = window.getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const root = scope ? document.querySelector(scope) : null;
  if (scope && !root) {
    return { ok: false, reason: 'form_scope_missing', candidates: [] };
  }
  const formRoot = root || document.body;
  const sel = 'button, input[type="submit"], input[type="button"], input[type="image"], input[type="reset"]';
  const items = [];
  for (const el of formRoot.querySelectorAll(sel)) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    const name = el.getAttribute('name') || '';
    const id = el.id || '';
    const cls = (el.getAttribute('class') || '').trim();
    const value = (el.value || '').slice(0, 120);
    const ariaLabel = el.getAttribute('aria-label') || '';
    const text = norm((el.innerText || '') + ' ' + (el.textContent || '')).slice(0, 120);
    const form = el.closest('form');
    items.push({
      tag,
      type,
      name,
      id,
      className: cls.slice(0, 200),
      value,
      ariaLabel,
      text,
      label: norm(text + ' ' + value + ' ' + ariaLabel + ' ' + name + ' ' + cls).slice(0, 120),
      visible: visible(el),
      enabled: !el.disabled && !el.hasAttribute('aria-disabled'),
      inSelectedForm: root ? root.contains(el) : true,
      formId: form ? (form.id || '') : '',
      formAction: form ? (form.getAttribute('action') || '') : '',
      domOrder: items.length,
    });
  }

  let hintMatches = items;
  if (hint) {
    const local = hint.includes(' ') ? hint.split(' ').slice(-1)[0] : hint;
    try {
      hintMatches = items.filter((item) => {
        for (const el of formRoot.querySelectorAll(local)) {
          const tag = el.tagName.toLowerCase();
          const type = (el.getAttribute('type') || '').toLowerCase();
          const name = el.getAttribute('name') || '';
          const id = el.id || '';
          const cls = (el.getAttribute('class') || '').trim();
          const value = (el.value || '').slice(0, 120);
          if (
            tag === item.tag && type === item.type && name === item.name
            && id === item.id && cls === item.className && value === item.value
          ) {
            return true;
          }
        }
        return false;
      });
      if (!hintMatches.length) hintMatches = items;
    } catch (e) {
      hintMatches = items;
    }
  }

  return { ok: true, reason: 'ok', candidates: items, hint_candidates: hintMatches };
}
"""

_VALIDATE_RESOLVED_SUBMIT_JS = r"""
(args) => {
  const scope = (args.contact_form_scope || '').trim();
  const selector = (args.submit_selector || '').trim();
  if (!selector) {
    return { valid: false, reason: 'submit_missing', matches: 0 };
  }
  const root = scope ? document.querySelector(scope) : null;
  if (scope && !root) {
    return { valid: false, reason: 'form_scope_missing', matches: 0 };
  }
  let el = null;
  try {
    el = document.querySelector(selector);
  } catch (e) {
    return { valid: false, reason: 'selector_invalid', matches: 0 };
  }
  if (!el) {
    return { valid: false, reason: 'submit_missing', matches: 0 };
  }
  if (root && !root.contains(el)) {
    return { valid: false, reason: 'submit_outside_form', matches: 0 };
  }
  const localSel = selector.includes(' ') ? selector.split(' ').slice(-1)[0] : selector;
  const formRoot = root || el.closest('form') || document.body;
  let matches = 0;
  try {
    matches = formRoot.querySelectorAll(localSel).length;
  } catch (e) {
    matches = 1;
  }
  const style = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  const visible = style.display !== 'none'
    && style.visibility !== 'hidden'
    && style.opacity !== '0'
    && rect.width > 0
    && rect.height > 0;
  const enabled = !el.disabled && !el.hasAttribute('aria-disabled');
  const label = (
    (el.innerText || '') + ' ' + (el.textContent || '') + ' ' + (el.value || '')
  ).replace(/\s+/g, ' ').trim().slice(0, 120);
  const tag = (el.tagName || '').toLowerCase();
  const type = (el.getAttribute('type') || '').toLowerCase();
  const elementType = type ? tag + ':' + type : tag;
  if (!visible) {
    return {
      valid: false, reason: 'submit_hidden', matches, visible: false, enabled,
      element_type: elementType, label, selector, contact_form_scope: scope,
    };
  }
  if (!enabled) {
    return {
      valid: false, reason: 'submit_disabled', matches, visible: true, enabled: false,
      element_type: elementType, label, selector, contact_form_scope: scope,
    };
  }
  if (matches > 1) {
    return {
      valid: false, reason: 'submit_ambiguous', matches, visible: true, enabled: true,
      element_type: elementType, label, selector, contact_form_scope: scope,
    };
  }
  return {
    valid: true,
    reason: 'valid',
    matches: 1,
    visible: true,
    enabled: true,
    element_type: elementType,
    label,
    selector,
    contact_form_scope: scope,
    final_submit_eligible: true,
    resolution_policy: args.resolution_policy || '',
  };
}
"""


def build_submit_target_record(
    *,
    submit_selector: str,
    contact_form_scope: str,
    live_state: dict[str, Any],
) -> dict[str, Any]:
    """Canonical submit-target representation (metadata; not in semantic hash)."""
    return {
        "submit_selector": (submit_selector or "").strip(),
        "contact_form_scope": (contact_form_scope or "").strip(),
        "element_type": live_state.get("element_type", ""),
        "label": live_state.get("label", ""),
        "visible": bool(live_state.get("visible")),
        "enabled": bool(live_state.get("enabled")),
        "matches_in_scope": int(live_state.get("matches") or 0),
        "final_submit_eligible": bool(live_state.get("final_submit_eligible")),
        "validation_reason": live_state.get("reason", ""),
        "resolution_policy": live_state.get("resolution_policy", ""),
        "selector_hint": live_state.get("selector_hint", ""),
        "semantic_class": live_state.get("semantic_class", ""),
        "multistep_state": live_state.get("multistep_state", ""),
    }


async def _discover_submit_candidates(
    page,
    *,
    contact_form_scope: str,
    submit_selector: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        raw = await page.evaluate(
            _DISCOVER_SUBMIT_CANDIDATES_JS,
            {"contact_form_scope": contact_form_scope, "submit_selector": submit_selector},
        )
    except Exception as exc:
        return [], [f"submit_target:discovery_failed:{exc}"]
    if not isinstance(raw, dict):
        return [], ["submit_target:discovery_invalid_response"]
    if not raw.get("ok"):
        reason = raw.get("reason") or SUBMIT_TARGET_SCOPE_MISSING
        return [], [f"submit_target:{reason}"]
    candidates = raw.get("hint_candidates") or raw.get("candidates") or []
    if not isinstance(candidates, list):
        return [], ["submit_target:discovery_invalid_candidates"]
    return candidates, []


async def resolve_canonical_submit_target(
    page,
    *,
    contact_form_scope: str | None,
    submit_selector: str | None,
) -> tuple[bool, dict[str, Any], list[str]]:
    """
    Validate and, if needed, semantically disambiguate the authorized submit target.
    Returns (valid, submit_target_record, failure_reasons).
    """
    reasons: list[str] = []
    selector = (submit_selector or "").strip()
    scope = (contact_form_scope or "").strip()

    if not selector:
        reasons.append(f"submit_target:{SUBMIT_TARGET_MISSING}")
        return False, {}, reasons

    candidates, discover_reasons = await _discover_submit_candidates(
        page,
        contact_form_scope=scope,
        submit_selector=selector,
    )
    if discover_reasons:
        return False, {}, discover_reasons

    multistep_state = FORM_ENTRY
    page_url = ""
    try:
        page_url = page.url or ""
        multistep_state = await detect_multistep_state_dom(page)
    except Exception:
        pass

    resolution = resolve_submit_from_candidates(
        candidates,
        contact_form_scope=scope,
        submit_selector_hint=selector,
        page_url=page_url,
        multistep_state=multistep_state,
    )
    resolved_selector = (resolution.get("selector") or selector).strip()
    if not resolution.get("valid"):
        reason = resolution.get("reason") or SUBMIT_TARGET_AMBIGUOUS
        record = build_submit_target_record(
            submit_selector=selector,
            contact_form_scope=scope,
            live_state={
                "reason": reason,
                "matches": resolution.get("matches") or 0,
                "resolution_policy": resolution.get("policy") or RESOLUTION_AMBIGUOUS,
                "selector_hint": selector,
            },
        )
        reasons.append(f"submit_target:{reason}")
        return False, record, reasons

    try:
        live = await page.evaluate(
            _VALIDATE_RESOLVED_SUBMIT_JS,
            {
                "contact_form_scope": scope,
                "submit_selector": resolved_selector,
                "resolution_policy": resolution.get("policy") or "",
            },
        )
    except Exception as exc:
        reasons.append(f"submit_target:validation_failed:{exc}")
        return False, {}, reasons

    if not isinstance(live, dict):
        reasons.append("submit_target:validation_invalid_response")
        return False, {}, reasons

    live["selector_hint"] = selector
    live["resolution_policy"] = resolution.get("policy") or ""
    record = build_submit_target_record(
        submit_selector=resolved_selector,
        contact_form_scope=scope,
        live_state=live,
    )

    if not live.get("valid"):
        reason = live.get("reason") or SUBMIT_TARGET_MISSING
        reasons.append(f"submit_target:{reason}")
        return False, record, reasons

    chosen = resolution.get("candidate") or {}
    semantic_class = chosen.get("semantic_class") or ""
    live["semantic_class"] = semantic_class
    live["multistep_state"] = multistep_state
    if semantic_class == "NEXT_STEP_SAFE":
        live["final_submit_eligible"] = False
        live["reason"] = SUBMIT_TARGET_NEXT_STEP
        record = build_submit_target_record(
            submit_selector=resolved_selector,
            contact_form_scope=scope,
            live_state=live,
        )
        reasons.append(f"submit_target:{SUBMIT_TARGET_NEXT_STEP}")
        return False, record, reasons
    record["semantic_class"] = semantic_class
    record["multistep_state"] = multistep_state
    if not record.get("label") and chosen:
        record["label"] = candidate_label(chosen)

    return True, record, []


def derive_final_submit_identified(
    *,
    submit_selector: str | None,
    submit_target_record: dict[str, Any] | None,
) -> bool:
    """Derive runtime final_submit_identified from canonical live evidence."""
    if not (submit_selector or "").strip():
        return False
    record = submit_target_record or {}
    return bool(record.get("final_submit_eligible") and record.get("visible") and record.get("enabled"))


async def validate_authorized_submit_target(
    page,
    *,
    contact_form_scope: str | None,
    submit_selector: str | None,
    baseline_record: dict[str, Any] | None = None,
) -> tuple[bool, list[str], dict[str, Any]]:
    """
    Re-validate authorized canonical submit target immediately before FINAL_SUBMIT.
    Uses semantic disambiguation when the stored selector is broad or ambiguous.
    """
    valid, record, reasons = await resolve_canonical_submit_target(
        page,
        contact_form_scope=contact_form_scope,
        submit_selector=submit_selector,
    )
    if not valid:
        return False, reasons, record

    if baseline_record:
        base_scope = (baseline_record.get("contact_form_scope") or "").strip()
        if base_scope and base_scope != (contact_form_scope or "").strip():
            reasons.append(f"form_identity:{base_scope}!={contact_form_scope}")
            return False, reasons, record

    return True, [], record
