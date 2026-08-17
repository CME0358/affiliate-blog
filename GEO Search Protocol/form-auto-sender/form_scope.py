"""
form_scope.py — contact form vs search/newsletter form discrimination.
"""

from __future__ import annotations

from typing import Any

PICK_CONTACT_FORM_JS = r"""
() => {
  function matchAny(text, kws) {
    return kws.some((k) => (text || '').includes(k));
  }
  function norm(s) { return (s || '').replace(/\s+/g, ' ').trim().toLowerCase(); }
  function cssEscape(s) {
    if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(s);
    return String(s).replace(/([!"#$%&'()*+,.\/:;<=>?@[\\\]^`{|}~])/g, '\\$1');
  }
  function formSelector(f) {
    f.setAttribute('data-ari-form-scope', 'contact');
    if (f.id) return 'form#' + cssEscape(f.id);
    return 'form[data-ari-form-scope="contact"]';
  }
  function isSearchForm(f) {
    const fc = norm((f.className || '') + ' ' + (f.id || '') + ' ' + (f.getAttribute('action') || ''));
    if (matchAny(fc, ['searchform', 'search-form', 'keni_search', 'hidden-search', 'site-search'])) return true;
    if (fc.includes('?s=') || fc.includes('&s=')) return true;
    const inputs = f.querySelectorAll('input, textarea, select');
    const hasSearchInput = Array.from(inputs).some((el) => {
      const n = norm(el.name || '');
      const t = norm(el.type || '');
      return n === 's' || t === 'search' || norm(el.placeholder || '').includes('検索');
    });
    const hasTextarea = f.querySelector('textarea');
    const hasEmail = f.querySelector('input[type="email"]') || Array.from(inputs).some((el) => matchAny(norm(el.name || ''), ['mail', 'email', 'メール']));
    if (hasSearchInput && !hasTextarea && !hasEmail && inputs.length <= 3) return true;
    return false;
  }
  function scoreContactForm(f) {
    if (isSearchForm(f)) return -999;
    let s = 0;
    const fc = norm((f.className || '') + ' ' + (f.id || '') + ' ' + (f.getAttribute('action') || ''));
    if (matchAny(fc, ['contact', 'inquiry', '問い合わせ', 'mail', 'estimate', 'wpcf7', 'mwform', 'sfm-form'])) s += 35;
    s += f.querySelectorAll('textarea').length * 18;
    s += f.querySelectorAll('input[type="email"]').length * 14;
    s += f.querySelectorAll('input[name*="your-"], textarea[name*="your-"]').length * 10;
    if (f.querySelector('textarea') && (f.querySelector('input[type="email"]') || f.querySelector('input[name*="mail"], input[name*="メール"]'))) s += 25;
    s += Math.min(f.querySelectorAll('input, textarea, select').length, 25);
    if (matchAny(fc, ['search', 'login', 'newsletter', 'subscribe'])) s -= 80;
    return s;
  }

  const forms = Array.from(document.querySelectorAll('form'));
  let best = null;
  let bestScore = -999;
  for (const f of forms) {
    const sc = scoreContactForm(f);
    if (sc > bestScore) { bestScore = sc; best = f; }
  }
  if (!best || bestScore < 0) return null;
  return {
    selector: formSelector(best),
    id: best.id || null,
    action: best.getAttribute('action') || '',
    method: (best.getAttribute('method') || 'get').toLowerCase(),
    score: bestScore,
    fieldCount: best.querySelectorAll('input, textarea, select').length,
    hasTextarea: !!best.querySelector('textarea'),
    hasEmail: !!best.querySelector('input[type="email"]'),
  };
}
"""


def is_search_form_meta(meta: dict[str, Any]) -> bool:
    action = (meta.get("action") or "").lower()
    fid = (meta.get("id") or "").lower()
    if any(k in action for k in ("?s=", "&s=", "search")):
        return True
    if any(k in fid for k in ("search", "keni_search")):
        return True
    return False


async def pick_contact_form(page) -> dict[str, Any] | None:
    try:
        raw = await page.evaluate(PICK_CONTACT_FORM_JS)
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None
