"""
cookie_banner.py — Generic cookie / consent overlay dismissal (not site-specific).

Jimdo and similar CMS pages block form submit clicks until the cookie banner
is accepted. Dismiss before submit detection / click.
"""

from __future__ import annotations

import asyncio
import re

# Platform-agnostic accept / save patterns (IDs/classes/text, not URLs)
_COOKIE_DISMISS_SELECTORS: tuple[str, ...] = (
    "#cookie-settings-all",
    "#cookie-settings-save",
    "[id*='cookie-settings-all']",
    "[id*='cookie-settings-save']",
    "[id*='cookie-settings'] button.btn",
    "[class*='cookie-settings'] button",
    "[class*='cookie-banner'] button[class*='accept']",
    "[class*='cookie-consent'] button[class*='accept']",
    "button:has-text('すべて同意')",
    "button:has-text('同意して閉じる')",
    "button:has-text('同意する')",
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
)

_DISMISS_JS = r"""
() => {
  const visible = (el) => {
    if (!el || !(el instanceof Element)) return false;
    const st = window.getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') return false;
    const r = el.getBoundingClientRect();
    return r.width >= 2 && r.height >= 2;
  };
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const acceptText = (t) => (
    t.includes('すべて同意') || t.includes('同意して') || t === '同意する' ||
    t.includes('accept all') || t.includes('allow all')
  );
  const roots = document.querySelectorAll(
    '[id*="cookie" i], [class*="cookie" i], [id*="Cookie"], [class*="Cookie"]'
  );
  for (const root of roots) {
    if (root.closest('form')) continue;
    for (const btn of root.querySelectorAll('button, [role="button"], input[type="button"]')) {
      if (!visible(btn)) continue;
      const t = norm((btn.innerText || '') + ' ' + (btn.textContent || '') + ' ' + (btn.value || ''));
      const id = norm(btn.id || '');
      if (acceptText(t) || id.includes('cookie-settings-all') || id.includes('cookie-settings-save')) {
        btn.click();
        return { clicked: true, id: btn.id || null, text: t.slice(0, 80) };
      }
    }
  }
  return { clicked: false };
}
"""


async def dismiss_cookie_banner(page, *, settle_ms: int = 600) -> bool:
    """
    Accept cookie banner if present. Returns True if a dismiss control was clicked.
    Safe to call when no banner exists.
    """
    clicked = False
    for sel in _COOKIE_DISMISS_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            if not await loc.is_visible():
                continue
            await loc.click(timeout=3_000)
            clicked = True
            break
        except Exception:
            continue
    if not clicked:
        try:
            result = await page.evaluate(_DISMISS_JS)
            clicked = bool(result and result.get("clicked"))
        except Exception:
            pass
    if clicked and settle_ms > 0:
        await asyncio.sleep(settle_ms / 1000)
    return clicked


def cookie_overlay_likely(html: str) -> bool:
    """Heuristic for pages that may block clicks behind cookie UI."""
    h = (html or "").lower()
    return bool(
        re.search(r"cookie[-_]?settings|cookie[-_]?banner|cookie[-_]?consent", h)
    )
