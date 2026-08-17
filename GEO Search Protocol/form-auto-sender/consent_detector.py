"""
consent_detector.py — Generic consent / acceptance checkbox detection (CF7 + HTML forms)

Site-specific selectors prohibited. Uses plugin-generic markers and text context.
"""

from __future__ import annotations

CONSENT_DETECT_AND_FILL_JS = r"""
() => {
  const tick = (cb) => {
    if (!cb || cb.disabled) return false;
    cb.checked = true;
    cb.dispatchEvent(new Event('input', { bubbles: true }));
    cb.dispatchEvent(new Event('change', { bubbles: true }));
    cb.dispatchEvent(new Event('click', { bubbles: true }));
    return cb.checked === true;
  };
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const isConsentContext = (text) => {
    const t = norm(text).toLowerCase();
    return (
      t.includes('同意') || t.includes('privacy') || t.includes('個人情報') ||
      t.includes('プライバシー') || t.includes('同意する') ||
      t.includes('acceptance') || t.includes('利用規約') ||
      t.includes('個人情報の取り扱い') || t.includes('policy')
    );
  };

  const candidates = [];

  for (const wrap of document.querySelectorAll('.wpcf7-acceptance')) {
    const cb = wrap.querySelector('input[type="checkbox"]');
    if (cb) candidates.push({ el: cb, source: 'wpcf7-acceptance' });
  }

  for (const el of document.querySelectorAll('input[type="checkbox"]')) {
    const wrap = el.closest('.wpcf7-form-control-wrap, .wpcf7-list-item, label, p, div, span') || el.parentElement;
    const ctx = norm(
      (el.name || '') + ' ' + (el.id || '') + ' ' +
      (el.getAttribute('class') || '') + ' ' +
      (wrap?.innerText || '') + ' ' +
      (el.closest('form')?.innerText || '').slice(0, 800)
    );
    const ariaReq = el.getAttribute('aria-required') === 'true';
    const req = el.required || ariaReq;
    if (isConsentContext(ctx) || el.closest('.wpcf7-acceptance')) {
      candidates.push({ el, source: 'checkbox-consent-context' });
    } else if (req && isConsentContext(el.closest('form')?.innerText || '')) {
      candidates.push({ el, source: 'checkbox-required-in-form' });
    }
  }

  for (const node of document.querySelectorAll('label, p, div, span')) {
    const t = norm(node.innerText || '');
    if (!t.includes('同意')) continue;
    const cb = node.querySelector('input[type="checkbox"]')
      || node.parentElement?.querySelector('input[type="checkbox"]');
    if (cb) candidates.push({ el: cb, source: 'label-proximity' });
  }

  const seen = new Set();
  const unique = [];
  for (const c of candidates) {
    if (seen.has(c.el)) continue;
    seen.add(c.el);
    unique.push(c);
  }

  if (unique.length === 0) {
    return { present: false, filled: false, source: null, selector: null, count: 0 };
  }

  let filledAny = false;
  let firstSource = null;
  let firstSelector = null;
  for (const c of unique) {
    if (tick(c.el)) {
      filledAny = true;
      if (!firstSource) {
        firstSource = c.source;
        const el = c.el;
        firstSelector = el.name ? `[name="${el.name}"]` : (el.id ? `#${el.id}` : 'checked');
      }
    }
  }

  return {
    present: true,
    filled: filledAny,
    source: firstSource,
    selector: firstSelector,
    count: unique.length,
  };
}
"""

# Legacy callers expect selector string or null
FIND_CONSENT_JS = (
    "() => { const r = (" + CONSENT_DETECT_AND_FILL_JS + ")(); "
    "return r.filled ? (r.selector || 'checked') : null; }"
)


def consent_fill_status(result: dict | None) -> str:
    """Map JS result → FILLED | MISSING | NOT_REQUIRED."""
    if not result:
        return "NOT_REQUIRED"
    if not result.get("present"):
        return "NOT_REQUIRED"
    return "FILLED" if result.get("filled") else "MISSING"
