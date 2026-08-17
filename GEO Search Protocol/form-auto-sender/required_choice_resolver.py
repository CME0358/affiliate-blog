"""
required_choice_resolver.py — rational required radio/checkbox/select selection.
"""

from __future__ import annotations

from inquiry_purpose_semantics import (
    REASON_AMBIGUOUS,
    REASON_NO_COMPATIBLE,
    is_inquiry_purpose_group,
    resolve_inquiry_purpose_choice,
)

INQUIRY_CATEGORY = "INQUIRY_CATEGORY"
CUSTOMER_TYPE = "CUSTOMER_TYPE"
SERVICE_TYPE = "SERVICE_TYPE"
PREFECTURE = "PREFECTURE"
CONTACT_METHOD = "CONTACT_METHOD"
CONSENT = "CONSENT"
UNSUITABLE_REQUIRED_CHOICE = "UNSUITABLE_REQUIRED_CHOICE"
UNKNOWN = "UNKNOWN"

_INQUIRY_PREFS = (
    "その他のお問い合わせ", "一般のお問い合わせ", "一般お問い合わせ", "お問い合わせ",
    "ご相談", "その他ご相談", "その他", "other",
)
_CUSTOMER_PREFS = ("法人", "企業", "事業者", "company", "corporate")
_SERVICE_OTHER = ("その他", "other", "その他の", "特に決まっていない", "未定")
_UNSUITABLE_KWS = (
    "予算", "施工", "リフォーム箇所", "現場調査希望", "見積", "工事",
    "キッチン", "浴室", "トイレ", "外壁", "屋根", "塗装",
)

_ANALYZE_REQUIRED_CHOICES_JS = r"""
(scope) => {
  function norm(s) { return (s || '').replace(/\s+/g, ' ').trim(); }
  function ctx(el) {
    const parts = [];
    const row = el.closest('tr, li, dl, fieldset, div, label') || el.parentElement;
    if (row) {
      const th = row.querySelector('th, dt, legend, label, h2, h3, h4, p');
      if (th) parts.push(th.textContent || '');
    }
    parts.push(el.name || '', el.id || '', el.className || '');
    if (el.labels) Array.from(el.labels).forEach(lb => parts.push(lb.textContent || ''));
    return norm(parts.join(' '));
  }
  const root = scope ? document.querySelector(scope) : document;
  if (!root) return [];
  const groups = [];
  function isRequired(el, contextText) {
    return !!(el.required || el.getAttribute('aria-required') === 'true'
      || (contextText || '').includes('必須'));
  }
  const radioNames = new Set();
  root.querySelectorAll('input[type="radio"]').forEach(el => {
    if (el.name) radioNames.add(el.name);
  });
  for (const name of radioNames) {
    const opts = Array.from(root.querySelectorAll('input[type="radio"][name="' + name.replace(/"/g, '\\"') + '"]'));
    if (!opts.length) continue;
    groups.push({
      kind: 'radio',
      name,
      context: ctx(opts[0]),
      required: isRequired(opts[0], ctx(opts[0])),
      options: opts.map(o => ({
        value: o.value || '',
        id: o.id || '',
        label: norm((o.labels && o.labels[0] ? o.labels[0].textContent : '') + ' ' + (o.parentElement ? o.parentElement.textContent : '')).slice(0, 120),
        checked: o.checked,
      })),
    });
  }
  root.querySelectorAll('select').forEach(el => {
    if ((el.type || '').toLowerCase() === 'hidden') return;
    const opts = Array.from(el.options).map(o => ({ value: o.value, label: norm(o.textContent || '') }));
    groups.push({
      kind: 'select',
      name: el.name || el.id || '',
      context: ctx(el),
      required: isRequired(el, ctx(el)),
      options: opts,
    });
  });
  const cbNames = new Set();
  root.querySelectorAll('input[type="checkbox"]').forEach(el => {
    if (!el.name || (el.name || '').includes('accept') || (el.name || '').includes('agree')) return;
    cbNames.add(el.name);
  });
  for (const name of cbNames) {
    const opts = Array.from(root.querySelectorAll('input[type="checkbox"][name="' + name.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"]'));
    if (!opts.length) continue;
    groups.push({
      kind: 'checkbox',
      name,
      context: ctx(opts[0]),
      required: opts.some(o => isRequired(o, ctx(o))),
      options: opts.map(o => ({
        value: o.value || '',
        id: o.id || '',
        label: norm((o.labels && o.labels[0] ? o.labels[0].textContent : '') + ' ' + (o.parentElement ? o.parentElement.textContent : '')).slice(0, 120),
        checked: o.checked,
      })),
    });
  }
  return groups;
}
"""

_APPLY_RADIO_JS = r"""
(args) => {
  const { name, value, id } = args;
  let el = null;
  if (id) el = document.getElementById(id);
  if (!el && name && value !== undefined) {
    el = document.querySelector('input[type="radio"][name="' + name.replace(/"/g, '\\"') + '"][value="' + String(value).replace(/"/g, '\\"') + '"]');
  }
  if (!el && id) el = document.getElementById(id);
  if (el && !el.checked) {
    el.click();
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }
  return !!(el && el.checked);
}
"""

_APPLY_CHECKBOX_JS = r"""
(args) => {
  const { name, value, id } = args;
  let el = null;
  if (id) el = document.getElementById(id);
  if (!el && name) {
    const sel = value
      ? 'input[type="checkbox"][name="' + name.replace(/"/g, '\\"') + '"][value="' + String(value).replace(/"/g, '\\"') + '"]'
      : 'input[type="checkbox"][name="' + name.replace(/"/g, '\\"') + '"]';
    el = document.querySelector(sel);
  }
  if (el && !el.checked) { el.click(); return true; }
  return !!(el && el.checked);
}
"""

_APPLY_SELECT_JS = r"""
(args) => {
  const { name, value, label } = args;
  let el = document.querySelector('select[name="' + name.replace(/"/g, '\\"') + '"]') || document.getElementById(name);
  if (!el) return false;
  if (value) { el.value = value; el.dispatchEvent(new Event('change', { bubbles: true })); return true; }
  if (label) {
    for (const o of el.options) {
      if ((o.textContent || '').includes(label)) {
        el.value = o.value;
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }
    }
  }
  return false;
}
"""


def classify_choice_group(group: dict[str, Any]) -> str:
    ctx = (group.get("context") or "").lower()
    name = (group.get("name") or "").lower()
    blob = f"{ctx} {name}"
    if any(k in blob for k in ("同意", "consent", "privacy", "個人情報", "accept", "agree")):
        return CONSENT
    if any(k in blob for k in ("都道府県", "prefecture", "pref", "todofuken", "form_area")):
        return PREFECTURE
    if any(k in blob for k in ("連絡方法", "contact method", "ご連絡", "診断", "inspection", "現場調査")):
        return CONTACT_METHOD
    if any(k in blob for k in ("法人", "個人", "customer", "type_s", "type")):
        return CUSTOMER_TYPE
    if any(k in blob for k in ("お問い合わせ種類", "mailtonum", "category", "問い合わせ種類", "inquiry")):
        return INQUIRY_CATEGORY
    if any(k in blob for k in ("お問い合わせ項目", "お問い合わせ内容", "問い合わせ項目", "ご用件", "用件")):
        return INQUIRY_CATEGORY
    if any(k in blob for k in _UNSUITABLE_KWS):
        return SERVICE_TYPE
    if group.get("kind") == "checkbox" and any(k in blob for k in ("施工", "リフォーム", "form_reform", "部位", "checkbox")):
        return SERVICE_TYPE
    return UNKNOWN


def _pick_option(options: list[dict], prefs: tuple[str, ...]) -> dict | None:
    for pref in prefs:
        for opt in options:
            lbl = (opt.get("label") or "").lower()
            if pref.lower() in lbl:
                return opt
    return None


def resolve_rational_choice(group: dict[str, Any]) -> tuple[dict | None, str, str]:
    """
    Returns (option_to_select, category, status).
    status: selected | skip | unsuitable
    """
    cat = classify_choice_group(group)
    opts = group.get("options") or []
    if not opts:
        return None, cat, "skip"

    if cat == CONSENT:
        return None, cat, "skip"  # handled by consent_detector

    if cat == PREFECTURE:
        opt = _pick_option(opts, ("足立", "東京都", "東京23区", "東京", "その他"))
        if opt:
            return opt, cat, "selected"
        return None, cat, "skip"

    if cat == INQUIRY_CATEGORY or is_inquiry_purpose_group(group, category=cat):
        opt, ip_status, ip_reason = resolve_inquiry_purpose_choice(group)
        if ip_status == "selected" and opt:
            return opt, INQUIRY_CATEGORY, "selected"
        if ip_status == "unsuitable" or (group.get("required") and ip_status != "selected"):
            return None, UNSUITABLE_REQUIRED_CHOICE, "unsuitable"
        return None, cat, "skip"

    if cat == CUSTOMER_TYPE:
        opt = _pick_option(opts, _CUSTOMER_PREFS)
        if opt:
            return opt, cat, "selected"
        return None, cat, "skip"

    if cat == CONTACT_METHOD:
        opt = _pick_option(opts, ("メール", "オンライン", "zoom", "email", "e-mail", "mail"))
        if opt:
            return opt, cat, "selected"
        return None, cat, "skip"

    if cat == SERVICE_TYPE:
        if len(opts) == 1:
            lbl = (opts[0].get("label") or "").lower()
            if any(p.lower() in lbl for p in _SERVICE_OTHER):
                return opts[0], cat, "selected"
            if not group.get("required"):
                return None, cat, "skip"
            return None, UNSUITABLE_REQUIRED_CHOICE, "unsuitable"
        if not group.get("required"):
            return None, cat, "skip"
        opt = _pick_option(opts, _SERVICE_OTHER)
        if opt:
            return opt, cat, "selected"
        return None, UNSUITABLE_REQUIRED_CHOICE, "unsuitable"

    if cat == UNKNOWN and group.get("required"):
        if is_inquiry_purpose_group(group, category=cat):
            opt, ip_status, _ip_reason = resolve_inquiry_purpose_choice(group)
            if ip_status == "selected" and opt:
                return opt, INQUIRY_CATEGORY, "selected"
            return None, UNSUITABLE_REQUIRED_CHOICE, "unsuitable"
        opt = _pick_option(opts, _CUSTOMER_PREFS + _SERVICE_OTHER)
        if opt:
            return opt, cat, "selected"

    return None, cat, "skip"


async def apply_rational_required_choices(page, *, scope_selector: str | None = None) -> dict[str, Any]:
    """Apply rational selections. Returns log dict."""
    result: dict[str, Any] = {
        "applied": [],
        "skipped": [],
        "unsuitable": [],
    }
    try:
        groups = await page.evaluate(_ANALYZE_REQUIRED_CHOICES_JS, scope_selector)
    except Exception:
        return result
    if not isinstance(groups, list):
        return result

    for group in groups:
        cat = classify_choice_group(group)
        if cat == INQUIRY_CATEGORY or is_inquiry_purpose_group(group, category=cat):
            opt, ip_status, ip_reason = resolve_inquiry_purpose_choice(group)
            entry = {
                "category": INQUIRY_CATEGORY,
                "name": group.get("name"),
                "context": (group.get("context") or "")[:80],
            }
            if ip_status == "selected" and opt:
                pass  # fall through to apply below
            elif ip_status == "unsuitable" or (group.get("required") and ip_status != "selected"):
                entry["reason"] = ip_reason or REASON_NO_COMPATIBLE
                result["unsuitable"].append(entry)
                continue
            else:
                result["skipped"].append(entry)
                continue
            # apply selected inquiry-purpose option
            kind = group.get("kind")
            args = {"name": group.get("name"), "value": opt.get("value"), "id": opt.get("id")}
            try:
                if kind == "radio":
                    ok = await page.evaluate(_APPLY_RADIO_JS, args)
                elif kind == "checkbox":
                    ok = await page.evaluate(_APPLY_CHECKBOX_JS, args)
                elif kind == "select":
                    ok = await page.evaluate(_APPLY_SELECT_JS, {**args, "label": opt.get("label")})
                else:
                    ok = False
                if ok:
                    entry["label"] = opt.get("label")
                    result["applied"].append(entry)
                else:
                    result["skipped"].append(entry)
            except Exception:
                result["skipped"].append(entry)
            continue

        opt, cat, status = resolve_rational_choice(group)
        entry = {"category": cat, "name": group.get("name"), "context": (group.get("context") or "")[:80]}
        if status == "unsuitable":
            if cat == UNSUITABLE_REQUIRED_CHOICE and is_inquiry_purpose_group(group, category=classify_choice_group(group)):
                _, _, ip_reason = resolve_inquiry_purpose_choice(group)
                entry["reason"] = ip_reason or REASON_NO_COMPATIBLE
            result["unsuitable"].append(entry)
            continue
        if status != "selected" or not opt:
            result["skipped"].append(entry)
            continue
        kind = group.get("kind")
        args = {"name": group.get("name"), "value": opt.get("value"), "id": opt.get("id")}
        try:
            if kind == "radio":
                ok = await page.evaluate(_APPLY_RADIO_JS, args)
            elif kind == "checkbox":
                ok = await page.evaluate(_APPLY_CHECKBOX_JS, args)
            elif kind == "select":
                ok = await page.evaluate(_APPLY_SELECT_JS, {**args, "label": opt.get("label")})
            else:
                ok = False
            if ok:
                entry["label"] = opt.get("label")
                result["applied"].append(entry)
        except Exception:
            result["skipped"].append(entry)
    return result
