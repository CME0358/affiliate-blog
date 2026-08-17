"""Generic, side-effect-free MW WP Form state/evidence detection."""
from __future__ import annotations

import re
import inspect
from typing import Any

MW_INITIAL = "INITIAL_FORM"
MW_CONFIRMATION = "CONFIRMATION_REACHED"
MW_COMPLETE = "CONFIRMED_SENT"
MW_UNKNOWN = "UNKNOWN_STATE"


def detect_mw_wp_form_state(html: str) -> str:
    value = (html or "").lower()
    if "mw_wp_form_complete" in value:
        return MW_COMPLETE
    if "mw_wp_form_confirm" in value:
        return MW_CONFIRMATION
    if "mw_wp_form_input" in value:
        return MW_INITIAL
    return MW_UNKNOWN


async def probe_mw_wp_form_state_dom(page) -> dict[str, Any]:
    """Probe only the MW root without consuming the generic evaluate contract.

    ``multistep_state`` historically performs one ``page.evaluate`` per state
    read.  Keep this plugin probe on Playwright's locator channel so non-MW
    pages and existing evaluate-based fixtures retain that exact contract.
    """
    try:
        roots = page.locator(".mw_wp_form")
        if inspect.isawaitable(roots):
            roots.close()
            return {
                "state": MW_UNKNOWN,
                "plugin_present": False,
                "error": "invalid_async_locator_contract",
            }
        count = await roots.count()
        if count != 1:
            return {
                "state": MW_UNKNOWN,
                "plugin_present": count > 0,
                "root_count": count,
            }
        root_class = await roots.first.get_attribute("class") or ""
    except Exception as exc:
        return {
            "state": MW_UNKNOWN,
            "plugin_present": False,
            "error": f"{type(exc).__name__}:{exc}",
        }

    return {
        "state": detect_mw_wp_form_state(f'<div class="{root_class}">'),
        "plugin_present": True,
        "root_count": 1,
        "root_class": root_class,
    }


async def detect_mw_wp_form_state_dom(page) -> dict[str, Any]:
    try:
        raw = await page.evaluate("""() => {
          const root = document.querySelector('.mw_wp_form');
          const form = root?.querySelector('form') || root?.closest('form') || document.querySelector('form');
          const cls = root?.className || '';
          let state = 'UNKNOWN_STATE';
          if (cls.includes('mw_wp_form_complete')) state = 'CONFIRMED_SENT';
          else if (cls.includes('mw_wp_form_confirm')) state = 'CONFIRMATION_REACHED';
          else if (cls.includes('mw_wp_form_input')) state = 'INITIAL_FORM';
          const id = form?.querySelector('[name="mw-wp-form-form-id"]')?.value || '';
          const token = form?.querySelector('[name="mw_wp_form_token"]');
          const buttons = [...(form || root || document).querySelectorAll('button,input[type="submit"],input[type="button"]')].map((e, i) => ({
            order:i, tag:e.tagName.toLowerCase(), type:(e.type||'').toLowerCase(), name:e.name||'',
            value:e.value||'', text:(e.innerText||'').trim(), visible:!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length), disabled:!!e.disabled
          }));
          return {state, plugin_present:!!root, root_class:cls, form_id:id,
            token_field_present:!!token, token_value_present:!!(token && token.value),
            form_action:form?.action||'', form_method:(form?.method||'').toLowerCase(), buttons,
            asset_hints:[...document.querySelectorAll('script[src],link[href]')].map(e=>e.src||e.href||'').filter(x=>x.includes('mw-wp-form')).slice(0,10)};
        }""")
    except Exception as exc:
        return {"state": MW_UNKNOWN, "plugin_present": False, "error": f"{type(exc).__name__}:{exc}"}
    return raw if isinstance(raw, dict) else {"state": MW_UNKNOWN, "plugin_present": False, "error": "invalid_dom_result"}


def cookie_hints(cookies: list[dict[str, Any]]) -> list[str]:
    return sorted({str(c.get("name") or "") for c in cookies if re.search(r"mw[-_]wp[-_]form", str(c.get("name") or ""), re.I)})
