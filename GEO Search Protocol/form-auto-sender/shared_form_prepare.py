"""
shared_form_prepare.py — Single source of truth for form preparation.

Preflight (fill_form_no_submit) and production (send_form) MUST use
shared_prepare_form() so field mapping, choices, consent, and validation
are identical before FINAL_SUBMIT.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from config import (
    SENDER_COMPANY,
    SENDER_EMAIL,
    SENDER_NAME,
    SENDER_PHONE,
)
from consent_detector import (
    CONSENT_DETECT_AND_FILL_JS,
    consent_fill_status,
)
from fill_compat import safe_fill
from form_field_resolver import (
    classify_form_analysis_failure,
    extract_partial_fields_from_dom,
    resolve_form_fields,
)
from message_variant import (
    MIN_MESSAGE_CAPACITY,
    SKIP_V2_EXCEEDS_MAX,
    VARIANT_V2,
    MessageSelection,
    detect_message_field_maxlength,
    format_selection_log_line,
    resolve_ari_message_for_form,
    selection_as_dict,
)
from inquiry_purpose_semantics import REASON_AMBIGUOUS, REASON_NO_COMPATIBLE
from required_choice_resolver import apply_rational_required_choices
from semantic_policy import (
    SEMANTIC_REFRESH_REQUIRED,
    current_semantic_policy_provenance,
    is_semantic_policy_compatible,
)

RUNTIME_DIVERGENCE = "RUNTIME_DIVERGENCE"
ARI_SUBJECT = "Agent Readiness Index についてのご連絡"

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

from form_sender import (
    _fill_address_block,
    _fill_message_field,
    _fill_postal_code,
    _fill_prefecture,
    _reset_gender_age_fields,
)


def _field_status_map(
    fields: dict,
    filled: dict[str, str],
    signals: dict[str, str],
) -> dict[str, str]:
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
    out["consent"] = filled.get("consent", signals.get("consent", "MISSING"))
    return out


@dataclass
class FormPrepareResult:
    ok: bool
    reason: str = ""
    blocked: bool = False
    fields: dict[str, Any] = field(default_factory=dict)
    field_source: str = ""
    selection: Any = None
    message: str = ""
    filled: dict[str, str] = field(default_factory=dict)
    choice_log: dict[str, Any] = field(default_factory=dict)
    field_map: dict[str, str] = field(default_factory=dict)
    contact_form_scope: str | None = None
    mapping_hash: str = ""
    snapshot: dict[str, Any] = field(default_factory=dict)
    cookie_banner_dismissed: bool = False
    cookie_overlay: bool = False
    buttons: list[dict] = field(default_factory=list)
    final_submit_identified: bool = False
    final_submit_label: str | None = None
    canonical_submit_target: dict[str, Any] = field(default_factory=dict)
    message_validation: dict[str, Any] = field(default_factory=dict)
    partial_fields: dict[str, Any] = field(default_factory=dict)
    required_field_coverage: dict[str, Any] = field(default_factory=dict)


def _normalize_selector(val: str | None) -> str:
    return (val or "").strip()


_HONEYPOT_FIELD_FRAGMENTS = (
    "spam", "honeypot", "turnstile", "recaptcha", "quiz", "image_auth", "image-auth",
)

# ─── Canonical Semantic Evidence (schema v2) ────────────────────────────────

SEMANTIC_EVIDENCE_SCHEMA_VERSION = 2
SEMANTIC_EVIDENCE_SCHEMA_VERSION_V1 = 1

# Keys included in semantic hash (stable across v2; matches legacy mapping hash payload).
SEMANTIC_HASH_KEYS = (
    "contact_form_scope",
    "fields",
    "field_map",
    "choices_applied",
    "choices_post_fill",
    "message_variant",
    "message_length",
    "consent",
)

FIELD_MAP_KEYS = (
    "company", "name", "email", "phone", "subject", "message", "consent",
)


def _normalize_choice_list(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Stable ordering for required-choice decisions in canonical serialization."""
    normalized: list[dict[str, Any]] = []
    for item in items or []:
        normalized.append({
            "category": item.get("category"),
            "name": item.get("name"),
            "value": item.get("value"),
            "label": (item.get("label") or "")[:80] if item.get("label") is not None else item.get("label"),
        })
    return sorted(
        normalized,
        key=lambda c: (
            str(c.get("category") or ""),
            str(c.get("name") or ""),
            str(c.get("value") or ""),
            str(c.get("label") or ""),
        ),
    )


def _normalize_fields_dict(fields: dict[str, Any]) -> dict[str, str]:
    return {
        k: _normalize_selector(v)
        for k, v in sorted(fields.items())
        if (k.endswith("_field") or k in ("submit_button", "contact_form_scope", "furigana_format"))
        and not any(h in k.lower() or h in _normalize_selector(v).lower() for h in _HONEYPOT_FIELD_FRAGMENTS)
    }


def build_canonical_prepared_snapshot(
    *,
    form_url: str = "",
    fields: dict[str, Any],
    filled: dict[str, str],
    choice_log: dict[str, Any],
    field_map: dict[str, str],
    selection: Any = None,
    contact_form_scope: str | None = None,
    submit_target: str | None = None,
) -> dict[str, Any]:
    """
    Single canonical semantic snapshot builder for FULL_PREFLIGHT, refresh, and production.
    """
    sel_dict = selection if isinstance(selection, dict) else (
        selection_as_dict(selection) if selection is not None else {}
    )
    post_fill = choice_log.get("post_fill") or {}
    submit_button = submit_target or _normalize_selector(fields.get("submit_button"))

    return {
        "semantic_evidence_schema_version": SEMANTIC_EVIDENCE_SCHEMA_VERSION,
        "form_url": (form_url or "").strip(),
        "contact_form_scope": contact_form_scope or "",
        "submit_target": submit_button,
        "fields": _normalize_fields_dict(fields),
        "field_map": {k: field_map.get(k, "MISSING") for k in FIELD_MAP_KEYS},
        "choices_applied": _normalize_choice_list(choice_log.get("applied")),
        "choices_post_fill": _normalize_choice_list(post_fill.get("applied")),
        "message_variant": sel_dict.get("variant", ""),
        "message_length": sel_dict.get("message_length", 0),
        "consent": field_map.get("consent", filled.get("consent", "MISSING")),
    }


def extract_semantic_hash_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Semantic payload used for deterministic hash (excludes schema metadata)."""
    return {
        "contact_form_scope": snapshot.get("contact_form_scope") or "",
        "fields": _normalize_fields_dict(snapshot.get("fields") or {}),
        "field_map": {k: (snapshot.get("field_map") or {}).get(k, "MISSING") for k in FIELD_MAP_KEYS},
        "choices_applied": _normalize_choice_list(snapshot.get("choices_applied")),
        "choices_post_fill": _normalize_choice_list(snapshot.get("choices_post_fill")),
        "message_variant": snapshot.get("message_variant") or "",
        "message_length": snapshot.get("message_length") or 0,
        "consent": snapshot.get("consent", "MISSING"),
    }


def serialize_canonical_snapshot(snapshot: dict[str, Any]) -> str:
    """Deterministic JSON serialization for semantic hash input."""
    payload = extract_semantic_hash_payload(snapshot)
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)


def compute_semantic_hash(snapshot: dict[str, Any]) -> str:
    canonical = serialize_canonical_snapshot(snapshot)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def build_semantic_evidence_record(
    *,
    canonical_snapshot: dict[str, Any],
    source: str = "shared_prepare_form",
    refreshed_at: str | None = None,
    historical_schema_version: int | None = None,
) -> dict[str, Any]:
    """Versioned persisted evidence record for export/refresh."""
    semantic_hash = compute_semantic_hash(canonical_snapshot)
    record = {
        "semantic_evidence_schema_version": SEMANTIC_EVIDENCE_SCHEMA_VERSION,
        "semantic_hash": semantic_hash,
        "canonical_snapshot": canonical_snapshot,
        "source": source,
        **current_semantic_policy_provenance(),
    }
    if refreshed_at:
        record["refreshed_at"] = refreshed_at
    if historical_schema_version is not None:
        record["historical_schema_version"] = historical_schema_version
    return record


def evidence_schema_version(evidence: dict[str, Any] | None) -> int:
    if not evidence:
        return SEMANTIC_EVIDENCE_SCHEMA_VERSION_V1
    if evidence.get("semantic_evidence_schema_version") == SEMANTIC_EVIDENCE_SCHEMA_VERSION:
        return SEMANTIC_EVIDENCE_SCHEMA_VERSION
    if evidence.get("semantic_evidence") and (
        evidence.get("semantic_evidence") or {}
    ).get("semantic_evidence_schema_version") == SEMANTIC_EVIDENCE_SCHEMA_VERSION:
        return SEMANTIC_EVIDENCE_SCHEMA_VERSION
    fn = evidence.get("fill_no_submit") if isinstance(evidence.get("fill_no_submit"), dict) else {}
    if (fn.get("semantic_evidence") or {}).get("semantic_evidence_schema_version") == SEMANTIC_EVIDENCE_SCHEMA_VERSION:
        return SEMANTIC_EVIDENCE_SCHEMA_VERSION
    return SEMANTIC_EVIDENCE_SCHEMA_VERSION_V1


def is_evidence_compatible(evidence: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """Production may compare only against compatible v2 canonical evidence."""
    reasons: list[str] = []
    if not evidence:
        reasons.append("missing_evidence")
        return False, reasons

    version = evidence.get("semantic_evidence_schema_version")
    if version is None:
        version = evidence_schema_version(evidence)
    if version != SEMANTIC_EVIDENCE_SCHEMA_VERSION:
        reasons.append(f"schema_version_mismatch:{version}!={SEMANTIC_EVIDENCE_SCHEMA_VERSION}")
        return False, reasons

    policy_ok, policy_reasons = is_semantic_policy_compatible(evidence)
    if not policy_ok:
        return False, policy_reasons

    snap = evidence.get("canonical_snapshot") or evidence
    fields = snap.get("fields") or evidence.get("fields") or {}
    if not fields:
        reasons.append("missing_canonical_fields")
        return False, reasons

    stored_hash = evidence.get("semantic_hash") or evidence.get("mapping_hash")
    if stored_hash:
        computed = compute_semantic_hash(snap if snap.get("fields") else evidence)
        if stored_hash != computed:
            reasons.append(f"semantic_hash_mismatch:{stored_hash}!={computed}")
            return False, reasons

    return True, []


def is_evidence_schema_and_hash_compatible(evidence: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """Schema/hash compatibility without semantic policy gate (internal use)."""
    reasons: list[str] = []
    if not evidence:
        reasons.append("missing_evidence")
        return False, reasons

    version = evidence.get("semantic_evidence_schema_version")
    if version is None:
        version = evidence_schema_version(evidence)
    if version != SEMANTIC_EVIDENCE_SCHEMA_VERSION:
        reasons.append(f"schema_version_mismatch:{version}!={SEMANTIC_EVIDENCE_SCHEMA_VERSION}")
        return False, reasons

    snap = evidence.get("canonical_snapshot") or evidence
    fields = snap.get("fields") or evidence.get("fields") or {}
    if not fields:
        reasons.append("missing_canonical_fields")
        return False, reasons

    stored_hash = evidence.get("semantic_hash") or evidence.get("mapping_hash")
    if stored_hash:
        computed = compute_semantic_hash(snap if snap.get("fields") else evidence)
        if stored_hash != computed:
            reasons.append(f"semantic_hash_mismatch:{stored_hash}!={computed}")
            return False, reasons

    return True, []


def build_mapping_snapshot(
    *,
    fields: dict[str, Any],
    filled: dict[str, str],
    choice_log: dict[str, Any],
    field_map: dict[str, str],
    selection: Any = None,
    contact_form_scope: str | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper — delegates to build_canonical_prepared_snapshot."""
    snap = build_canonical_prepared_snapshot(
        fields=fields,
        filled=filled,
        choice_log=choice_log,
        field_map=field_map,
        selection=selection,
        contact_form_scope=contact_form_scope,
        submit_target=fields.get("submit_button"),
    )
    # Legacy callers expect hash-payload keys only (no schema wrapper fields in snapshot dict).
    return extract_semantic_hash_payload(snap)


def compute_mapping_hash(snapshot: dict[str, Any]) -> str:
    return compute_semantic_hash(snapshot)


def compare_runtime_snapshots(
    preflight: dict[str, Any],
    production: dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Returns (diverged, reasons).
    Major differences block production send with RUNTIME_DIVERGENCE.
    """
    reasons: list[str] = []
    if not preflight or not production:
        return False, reasons

    pre_hash = preflight.get("mapping_hash") or compute_mapping_hash(preflight)
    prod_hash = production.get("mapping_hash") or compute_mapping_hash(production)
    if pre_hash != prod_hash:
        reasons.append(f"mapping_hash:{pre_hash}!={prod_hash}")

    for key in ("company", "name", "email", "message", "consent"):
        pre_fm = (preflight.get("field_map") or {}).get(key)
        prod_fm = (production.get("field_map") or {}).get(key)
        if pre_fm in ("FILLED", "FOUND") and prod_fm in ("MISSING", "AMBIGUOUS", None):
            reasons.append(f"field_regression:{key}:{pre_fm}->{prod_fm}")

    pre_scope = preflight.get("contact_form_scope") or (preflight.get("snapshot") or {}).get("contact_form_scope")
    prod_scope = production.get("contact_form_scope") or (production.get("snapshot") or {}).get("contact_form_scope")
    if pre_scope and prod_scope and pre_scope != prod_scope:
        reasons.append(f"scope_divergence:{pre_scope}!={prod_scope}")

    return bool(reasons), reasons


async def _fill_standard_fields(
    page,
    fields: dict,
    message: str,
    *,
    subject_text: str | None = None,
) -> dict[str, str]:
    """Hardened fill — safe_fill + consent. Single source of truth."""
    filled: dict[str, str] = {}
    subject_value = subject_text if subject_text is not None else ARI_SUBJECT

    if fields.get("company_field"):
        ok, reason = await safe_fill(page, fields["company_field"], SENDER_COMPANY)
        filled["company"] = "FILLED" if ok else f"SKIPPED:{reason}"

    if fields.get("name_field"):
        ok, reason = await safe_fill(page, fields["name_field"], SENDER_NAME)
        filled["name"] = "FILLED" if ok else f"SKIPPED:{reason}"

    if fields.get("furigana_name_field"):
        furigana_value = (
            "ささきたけし"
            if fields.get("furigana_format") == "hiragana"
            else "ササキタケシ"
        )
        ok, reason = await safe_fill(page, fields["furigana_name_field"], furigana_value)
        filled["furigana"] = "FILLED" if ok else f"SKIPPED:{reason}"

    if fields.get("email_field"):
        ok, reason = await safe_fill(page, fields["email_field"], SENDER_EMAIL)
        filled["email"] = "FILLED" if ok else f"SKIPPED:{reason}"

    # Some contact forms require the sender email to be entered twice.
    # Keep the confirmation field separate from the canonical email field
    # so resolver scoring cannot accidentally select it as the primary field.
    if fields.get("email_confirmation_field"):
        ok, reason = await safe_fill(
            page,
            fields["email_confirmation_field"],
            SENDER_EMAIL,
        )
        filled["email_confirmation"] = (
            "FILLED" if ok else f"SKIPPED:{reason}"
        )

    if fields.get("phone_field"):
        ok, reason = await safe_fill(page, fields["phone_field"], SENDER_PHONE)
        filled["phone"] = "FILLED" if ok else f"SKIPPED:{reason}"

    await _fill_postal_code(page, fields.get("postal_code_field") or "")
    await _fill_prefecture(page, fields)
    await _fill_address_block(page, fields)
    await _reset_gender_age_fields(page, fields)

    msg_ok, _ = await _fill_message_field(page, fields, message)
    filled["message"] = "FILLED" if msg_ok else "MISSING"

    await _reset_gender_age_fields(page, fields)

    try:
        sub_sel = await page.evaluate(_FIND_SUBJECT_JS)
        if sub_sel:
            ok, _ = await safe_fill(page, sub_sel, subject_value)
            if ok:
                filled["subject"] = "FILLED"
        elif fields.get("subject_field"):
            ok, _ = await safe_fill(page, fields["subject_field"], subject_value)
            if ok:
                filled["subject"] = "FILLED"
    except Exception:
        pass

    try:
        consent_result = await page.evaluate(CONSENT_DETECT_AND_FILL_JS)
        filled["consent"] = consent_fill_status(consent_result)
        if consent_result:
            filled["consent_meta"] = consent_result
    except Exception:
        pass

    return filled


async def verify_required_text_coverage(
    page,
    fields: dict[str, Any],
    *,
    contact_scope: str | None = None,
) -> dict[str, Any]:
    """Fail-closed inventory of visible required text-like controls after fill."""
    mapped = sorted({
        str(value).strip()
        for key, value in (fields or {}).items()
        if key.endswith("_field") and isinstance(value, str) and value.strip()
    })
    try:
        controls = await page.evaluate(
            """({scope, mapped}) => {
              const root = scope ? document.querySelector(scope) : document;
              if (!root) return [{reason: 'required_scope_missing'}];
              const mappedSet = new Set(mapped);
              const esc = (s) => (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
              const selectorFor = (el) => el.id ? `#${esc(el.id)}` :
                (el.name ? `${el.tagName.toLowerCase()}[name="${String(el.name).replace(/"/g, '\\"')}"]` : '');
              const visible = (el) => {
                const st = getComputedStyle(el), r = el.getBoundingClientRect();
                return st.display !== 'none' && st.visibility !== 'hidden' && r.width > 0 && r.height > 0;
              };
              return Array.from(root.querySelectorAll('input, textarea')).filter((el) => {
                const type = (el.type || '').toLowerCase();
                const textLike = el.tagName === 'TEXTAREA' || ['', 'text', 'email', 'tel', 'url', 'search', 'number'].includes(type);
                const required = el.required || el.getAttribute('aria-required') === 'true' || /(?:^|\\s)wpcf7-validates-as-required(?:\\s|$)/.test(el.className || '');
                return textLike && required && visible(el) && !el.disabled;
              }).map((el) => {
                const selector = selectorFor(el);
                return {selector, name: el.name || '', type: el.type || el.tagName.toLowerCase(),
                  mapped: !!selector && mappedSet.has(selector), filled: String(el.value || '').trim().length > 0};
              });
            }""",
            {"scope": contact_scope or "", "mapped": mapped},
        )
    except Exception as exc:
        return {"ok": False, "reason": "required_text_coverage_error", "error": type(exc).__name__, "controls": []}
    if not isinstance(controls, list):
        return {"ok": False, "reason": "required_text_coverage_invalid", "controls": []}
    unmapped = [c for c in controls if not c.get("mapped")]
    unfilled = [c for c in controls if c.get("mapped") and not c.get("filled")]
    reason = ""
    if unmapped:
        reason = "required_text_field_unmapped"
    elif unfilled:
        reason = "required_text_field_unfilled"
    return {"ok": not reason, "reason": reason, "controls": controls, "unmapped": unmapped, "unfilled": unfilled}


async def _prepare_dynamic_form_fields(page, contact_scope: str | None = None) -> dict:
    try:
        return await apply_rational_required_choices(page, scope_selector=contact_scope)
    except Exception:
        return {"applied": [], "skipped": [], "unsuitable": []}


async def _dismiss_cookie_if_needed(page) -> tuple[bool, bool]:
    from cookie_banner import cookie_overlay_likely, dismiss_cookie_banner

    html = await page.content()
    overlay = cookie_overlay_likely(html)
    dismissed = await dismiss_cookie_banner(page)
    return overlay, dismissed


async def shared_prepare_form(
    page,
    form_url: str,
    message: str,
    lp_url: str,
    *,
    allow_validation_fallback: bool = True,
    html: str | None = None,
    fixed_message_variant: str | None = None,
    fixed_subject: str | None = None,
) -> FormPrepareResult:
    """
    SHARED_PREPARE_FORM pipeline — used by preflight and production.

    Does NOT click FINAL_SUBMIT. Caller handles multistep navigation (preflight)
    or submit (production).
    """
    from form_fill_no_submit import (
        _audit_buttons,
        _fill_corporate_company_if_needed,
        _wait_fill_settle,
        detect_unsuitable_form_fields,
        pick_final_submit_button,
        validate_ari_message,
    )

    result = FormPrepareResult(ok=False)

    if html is None:
        html = await page.content()

    overlay, dismissed = await _dismiss_cookie_if_needed(page)
    result.cookie_overlay = overlay
    result.cookie_banner_dismissed = dismissed

    unsuitable = await detect_unsuitable_form_fields(page)
    if unsuitable:
        result.blocked = True
        result.reason = "form_not_suitable"
        return result

    fields, field_source = await resolve_form_fields(page, html, form_url)
    result.field_source = field_source
    result.fields = fields or {}

    if not fields:
        # Resolver recovery:
        # Some sites expose the actual inquiry form behind a contact/reserve
        # link rather than directly at the supplied URL. Reuse the existing
        # form_finder discovery rules on the current live page/session.
        try:
            from form_finder import recover_form_url_on_live_page

            recovered_form_url = await recover_form_url_on_live_page(
                page,
                form_url,
            )
        except Exception:
            recovered_form_url = None

        if recovered_form_url and recovered_form_url != form_url:
            try:
                recovered_html = await page.content()

                recovered_fields, recovered_source = await resolve_form_fields(
                    page,
                    recovered_html,
                    recovered_form_url,
                    skip_cache=True,
                )

                if recovered_fields:
                    form_url = recovered_form_url
                    html = recovered_html
                    fields = recovered_fields
                    field_source = f"recovery:{recovered_source}"

                    result.field_source = field_source
                    result.fields = fields
            except Exception:
                fields = None

    if not fields:
        partial = await extract_partial_fields_from_dom(page)
        result.partial_fields = partial
        try:
            iframe_hit = await page.evaluate(
                "() => Array.from(document.querySelectorAll('iframe')).some("
                "f => /form|contact|mail|inquiry/i.test(f.src||''))"
            )
        except Exception:
            iframe_hit = False
        result.reason = classify_form_analysis_failure(partial, iframe_detected=bool(iframe_hit))
        result.blocked = True
        return result

    if fixed_message_variant == VARIANT_V2:
        maxlength = await detect_message_field_maxlength(page, fields)
        if maxlength is not None and maxlength < MIN_MESSAGE_CAPACITY:
            selection = MessageSelection(
                variant=VARIANT_V2,
                message="",
                message_length=0,
                detected_maxlength=maxlength,
                fallback_reason=None,
                skip_reason="insufficient_message_capacity",
                skipped=True,
            )
        elif maxlength is not None and len(message) > maxlength:
            selection = MessageSelection(
                variant=VARIANT_V2,
                message="",
                message_length=len(message),
                detected_maxlength=maxlength,
                fallback_reason=None,
                skip_reason=SKIP_V2_EXCEEDS_MAX,
                skipped=True,
            )
        else:
            selection = MessageSelection(
                variant=VARIANT_V2,
                message=message,
                message_length=len(message),
                detected_maxlength=maxlength,
                fallback_reason=None,
                skip_reason=None,
                skipped=False,
            )
    else:
        selection = await resolve_ari_message_for_form(
            page, fields, lp_url, allow_validation_fallback=allow_validation_fallback,
        )
    result.selection = selection
    print(f"  📝 {format_selection_log_line(selection)}")

    if selection.skipped:
        result.blocked = True
        result.reason = selection.skip_reason or "compact_message_exceeds_maxlength"
        return result

    if fixed_message_variant == VARIANT_V2:
        result.message = message
    else:
        message = selection.message
        result.message = message
    result.message_validation = validate_ari_message(message)

    contact_scope = fields.get("contact_form_scope")
    result.contact_form_scope = contact_scope

    choice_log = await _prepare_dynamic_form_fields(page, contact_scope)
    result.choice_log = choice_log
    if choice_log.get("unsuitable"):
        result.blocked = True
        reasons = [u.get("reason") for u in choice_log.get("unsuitable") or [] if u.get("reason")]
        if REASON_AMBIGUOUS in reasons:
            result.reason = REASON_AMBIGUOUS
        elif REASON_NO_COMPATIBLE in reasons:
            result.reason = REASON_NO_COMPATIBLE
        else:
            result.reason = "unsuitable_required_choices"
        return result

    await _fill_corporate_company_if_needed(page, choice_log, fields)
    filled = await _fill_standard_fields(
        page,
        fields,
        message,
        subject_text=fixed_subject,
    )
    await _wait_fill_settle(page)

    post_fill = await _prepare_dynamic_form_fields(page, contact_scope)
    choice_log["post_fill"] = post_fill
    if post_fill.get("unsuitable"):
        result.blocked = True
        reasons = [u.get("reason") for u in post_fill.get("unsuitable") or [] if u.get("reason")]
        if REASON_AMBIGUOUS in reasons:
            result.reason = REASON_AMBIGUOUS
        elif REASON_NO_COMPATIBLE in reasons:
            result.reason = REASON_NO_COMPATIBLE
        else:
            result.reason = "unsuitable_required_choices"
        return result
    await _fill_corporate_company_if_needed(page, choice_log, fields)

    result.filled = filled

    required_coverage = await verify_required_text_coverage(
        page, fields, contact_scope=contact_scope,
    )
    result.required_field_coverage = required_coverage
    if not required_coverage.get("ok"):
        result.blocked = True
        result.reason = required_coverage.get("reason") or "required_text_field_unresolved"
        return result

    hl = html.lower()
    signals = {"subject": "MISSING", "consent": "MISSING"}
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
    elif filled.get("consent") == "NOT_REQUIRED":
        signals["consent"] = "NOT_REQUIRED"
    elif re.search(r"type\s*=\s*['\"]checkbox['\"]", hl) and (
        "同意" in html or "privacy" in hl or "個人情報" in html or "wpcf7-acceptance" in hl
    ):
        signals["consent"] = "FOUND"

    result.field_map = _field_status_map(fields, filled, signals)

    buttons = await _audit_buttons(page, contact_scope)
    result.buttons = buttons

    from canonical_submit_target import (
        derive_final_submit_identified,
        resolve_canonical_submit_target,
    )

    submit_sel = _normalize_selector(fields.get("submit_button"))
    if submit_sel:
        valid, submit_record, _fail = await resolve_canonical_submit_target(
            page,
            contact_form_scope=contact_scope,
            submit_selector=submit_sel,
        )
        result.canonical_submit_target = submit_record
        resolved_sel = (submit_record.get("submit_selector") or submit_sel).strip()
        if valid and resolved_sel and resolved_sel != submit_sel:
            fields["submit_button"] = resolved_sel
            submit_sel = resolved_sel
        result.final_submit_identified = derive_final_submit_identified(
            submit_selector=submit_sel,
            submit_target_record=submit_record if valid else None,
        )
        if result.final_submit_identified:
            result.final_submit_label = submit_record.get("label") or None
    else:
        final_btn, _ = pick_final_submit_button(buttons)
        if final_btn and final_btn.get("selector"):
            fields["submit_button"] = final_btn["selector"]
            valid, submit_record, _fail = await resolve_canonical_submit_target(
                page,
                contact_form_scope=contact_scope,
                submit_selector=final_btn["selector"],
            )
            result.canonical_submit_target = submit_record
            result.final_submit_identified = derive_final_submit_identified(
                submit_selector=final_btn["selector"],
                submit_target_record=submit_record if valid else None,
            )
            result.final_submit_label = submit_record.get("label") or final_btn.get("label")
        elif final_btn:
            result.final_submit_identified = True
            result.final_submit_label = final_btn.get("label")

    snapshot = build_mapping_snapshot(
        fields=fields,
        filled=filled,
        choice_log=choice_log,
        field_map=result.field_map,
        selection=selection,
        contact_form_scope=contact_scope,
    )
    result.snapshot = snapshot
    result.mapping_hash = compute_semantic_hash(snapshot)
    result.ok = True
    return result


# ─── Single-Snapshot Production Contract ─────────────────────────────────────

# Property classifications (generic, documented)
SEMANTIC_STABLE = "SEMANTIC_STABLE"          # field_map, scope, selectors, message variant
RUNTIME_VOLATILE = "RUNTIME_VOLATILE"        # dynamic choice resolution timing (same session)
SAFETY_CRITICAL_DYNAMIC = "SAFETY_CRITICAL_DYNAMIC"  # CAPTCHA, form identity, submit target

SEMANTIC_STABLE_KEYS = frozenset({
    "contact_form_scope", "fields", "field_map",
    "message_variant", "message_length", "consent",
})
SAFETY_CRITICAL_KEYS = frozenset({
    "form_url", "submit_button", "captcha_present", "page_alive",
})


@dataclass
class PreparedFormSnapshot:
    """
    Immutable prepared state bound to a live page/session.
    SINGLE-SNAPSHOT CONTRACT: prepare once → authorize → submit same state.
    """
    prep: FormPrepareResult
    form_url: str
    page_url: str = ""
    page: Any = None
    browser: Any = None
    context: Any = None
    authorized: bool = False
    submitted: bool = False
    authorization_hash: str = ""
    invariant_baseline: dict[str, Any] = field(default_factory=dict)

    @property
    def mapping_hash(self) -> str:
        return self.prep.mapping_hash

    @property
    def snapshot(self) -> dict[str, Any]:
        return self.prep.snapshot

    @property
    def field_map(self) -> dict[str, str]:
        return self.prep.field_map

    def to_runtime_snap(self) -> dict[str, Any]:
        return {
            "mapping_hash": self.prep.mapping_hash,
            "field_map": self.prep.field_map,
            "contact_form_scope": self.prep.contact_form_scope,
            "snapshot": self.prep.snapshot,
        }


async def prepare_once(
    page,
    form_url: str,
    message: str,
    lp_url: str,
    *,
    allow_validation_fallback: bool = False,
    html: str | None = None,
    fixed_message_variant: str | None = None,
    fixed_subject: str | None = None,
) -> PreparedFormSnapshot:
    """Single prepare — returns immutable PreparedFormSnapshot + live page."""
    prep = await shared_prepare_form(
        page, form_url, message, lp_url,
        allow_validation_fallback=allow_validation_fallback,
        html=html,
        fixed_message_variant=fixed_message_variant,
        fixed_subject=fixed_subject,
    )
    page_url = ""
    try:
        page_url = page.url
    except Exception:
        pass

    submit_sel = (prep.fields or {}).get("submit_button", "")
    baseline = {
        "form_url": form_url,
        "page_url": page_url,
        "contact_form_scope": prep.contact_form_scope or "",
        "field_map": dict(prep.field_map or {}),
        "mapping_hash": prep.mapping_hash,
        "fields_fingerprint": _fields_fingerprint(prep.fields or {}),
        "submit_button": submit_sel,
        "final_submit_identified": prep.final_submit_identified,
        "canonical_submit_target": dict(prep.canonical_submit_target or {}),
    }

    return PreparedFormSnapshot(
        prep=prep,
        form_url=form_url,
        page_url=page_url,
        page=page,
        invariant_baseline=baseline,
    )


def _fields_fingerprint(fields: dict[str, Any]) -> str:
    keys = sorted(k for k in fields if k.endswith("_field") or k in ("submit_button", "contact_form_scope"))
    parts = [f"{k}={_normalize_selector(fields.get(k))}" for k in keys]
    canonical = json.dumps(parts, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def build_preflight_semantic_evidence(preflight_row: dict[str, Any]) -> dict[str, Any]:
    """
    Load canonical semantic evidence for production equivalence.
    Prefers persisted v2 semantic_evidence; never silently upgrades v1 incomplete exports.
    """
    fn = preflight_row.get("fill_no_submit") or {}
    sem_record = fn.get("semantic_evidence") or preflight_row.get("semantic_evidence") or {}

    if sem_record.get("semantic_evidence_schema_version") == SEMANTIC_EVIDENCE_SCHEMA_VERSION:
        snap = sem_record.get("canonical_snapshot") or {}
        payload = extract_semantic_hash_payload(snap)
        return {
            **payload,
            "semantic_evidence_schema_version": SEMANTIC_EVIDENCE_SCHEMA_VERSION,
            "semantic_hash": sem_record.get("semantic_hash") or compute_semantic_hash(snap),
            "mapping_hash": sem_record.get("semantic_hash") or compute_semantic_hash(snap),
            "form_url": snap.get("form_url") or fn.get("form_url") or preflight_row.get("form_url") or "",
            "submit_target": snap.get("submit_target") or "",
            "canonical_snapshot": snap,
            "semantic_policy_version": sem_record.get("semantic_policy_version"),
            "semantic_policy_fingerprint": sem_record.get("semantic_policy_fingerprint"),
        }

    evidence = preflight_row.get("preflight_evidence") or {}
    snap = fn.get("prepare_snapshot") or {}
    field_map = fn.get("field_map") or evidence.get("field_map") or snap.get("field_map") or {}
    contact_scope = fn.get("contact_form_scope") or evidence.get("contact_form_scope") or snap.get("contact_form_scope") or ""
    sel = fn.get("message_selection") or {}
    message_variant = sel.get("variant") or evidence.get("message_variant") or snap.get("message_variant") or ""
    message_length = sel.get("message_length") or snap.get("message_length") or 0

    choices_applied = snap.get("choices_applied") or []
    choices_post_fill = snap.get("choices_post_fill") or []
    rc = fn.get("required_choices") or {}
    if not choices_applied and rc.get("applied"):
        choices_applied = _normalize_choice_list(rc["applied"])
    if not choices_post_fill and rc.get("post_fill", {}).get("applied"):
        choices_post_fill = _normalize_choice_list(rc["post_fill"]["applied"])

    fields = snap.get("fields") or {}
    consent = field_map.get("consent", snap.get("consent", "MISSING"))

    semantic = {
        "semantic_evidence_schema_version": SEMANTIC_EVIDENCE_SCHEMA_VERSION_V1,
        "contact_form_scope": contact_scope,
        "fields": fields,
        "field_map": {k: field_map.get(k, "MISSING") for k in FIELD_MAP_KEYS},
        "choices_applied": choices_applied,
        "choices_post_fill": choices_post_fill,
        "message_variant": message_variant,
        "message_length": message_length,
        "consent": consent,
    }
    stored_hash = fn.get("preflight_mapping_hash") or fn.get("mapping_hash") or evidence.get("mapping_hash")
    semantic["mapping_hash"] = stored_hash or compute_semantic_hash(semantic)
    semantic["semantic_hash"] = semantic["mapping_hash"]
    return semantic


def authorize_snapshot(
    prepared: PreparedFormSnapshot,
    preflight_evidence: dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Compare fresh production snapshot to compatible FULL_PREFLIGHT / refresh semantic evidence.
    Fail-closed equivalence gate — requires v2 canonical evidence for direct comparison.
    """
    if not prepared.prep.ok or prepared.prep.blocked:
        return False, [f"prepare_blocked:{prepared.prep.reason}"]

    compatible, compat_reasons = is_evidence_compatible(preflight_evidence)
    if not compatible:
        return False, compat_reasons

    fresh = prepared.to_runtime_snap()
    fresh["snapshot"] = prepared.prep.snapshot
    fresh["mapping_hash"] = prepared.prep.mapping_hash
    fresh["semantic_hash"] = prepared.prep.mapping_hash

    pre = dict(preflight_evidence or {})
    pre_hash = pre.get("semantic_hash") or pre.get("mapping_hash")
    if not pre_hash:
        snap = pre.get("canonical_snapshot") or pre
        pre_hash = compute_semantic_hash(snap)
    pre["mapping_hash"] = pre_hash
    pre["semantic_hash"] = pre_hash

    diverged, reasons = compare_runtime_snapshots(pre, fresh)
    if diverged:
        return False, reasons
    return True, []


def mark_snapshot_authorized(prepared: PreparedFormSnapshot) -> PreparedFormSnapshot:
    """Record authorization on snapshot — required before submit."""
    prepared.authorized = True
    prepared.authorization_hash = prepared.prep.mapping_hash
    return prepared


_CAPTCHA_DETECT_JS = r"""
() => {
  const patterns = ['recaptcha', 'hcaptcha', 'turnstile', 'captcha', 'g-recaptcha', 'cf-turnstile'];
  const html = document.documentElement.innerHTML.toLowerCase();
  return patterns.some(p => html.includes(p));
}
"""

_FIELDS_EXIST_JS = r"""
(selectors) => {
  const missing = [];
  for (const [key, sel] of Object.entries(selectors || {})) {
    if (!sel || typeof sel !== 'string') continue;
    if (!key.endsWith('_field') && key !== 'submit_button') continue;
    try {
      const el = document.querySelector(sel);
      if (!el) missing.push(key);
    } catch (e) {
      missing.push(key);
    }
  }
  return missing;
}
"""

_RESTORE_CONTACT_SCOPE_JS = r"""
(args) => {
  const scope = (args.scope || '').trim();
  const submitSel = (args.submit_selector || '').trim();
  if (scope && document.querySelector(scope)) return scope;
  let el = null;
  if (submitSel) {
    try { el = document.querySelector(submitSel); } catch (e) {}
    if (!el && submitSel.includes(' ')) {
      const tail = submitSel.split(' ').slice(-1)[0];
      try { el = document.querySelector(tail); } catch (e) {}
    }
  }
  const form = el ? el.closest('form') : null;
  if (!form) return scope;
  form.setAttribute('data-ari-form-scope', 'contact');
  if (form.id) {
    const esc = (typeof CSS !== 'undefined' && CSS.escape)
      ? CSS.escape(form.id)
      : form.id.replace(/([!"#$%&'()*+,.\/:;<=>?@[\\\]^`{|}~])/g, '\\$1');
    return 'form#' + esc;
  }
  return 'form[data-ari-form-scope="contact"]';
}
"""


async def _restore_contact_form_scope(page, contact_form_scope: str, submit_selector: str) -> str:
    """Re-apply prepare-time contact scope marker if dynamic DOM dropped it."""
    scope = (contact_form_scope or "").strip()
    if not scope or not page:
        return scope
    try:
        restored = await page.evaluate(
            _RESTORE_CONTACT_SCOPE_JS,
            {"scope": scope, "submit_selector": submit_selector or ""},
        )
        return (restored or scope).strip() or scope
    except Exception:
        return scope


async def validate_snapshot_invariants(
    prepared: PreparedFormSnapshot,
    *,
    check_captcha: bool = True,
) -> tuple[bool, list[str]]:
    """
    Lightweight stale-state invariant check before FINAL_SUBMIT.
    Returns (valid, reasons). Violations → RUNTIME_DIVERGENCE, DO NOT SUBMIT.
    """
    reasons: list[str] = []

    if prepared.submitted:
        reasons.append("duplicate_submit:already_submitted")
        return False, reasons

    if not prepared.authorized:
        reasons.append("not_authorized:snapshot_not_authorized")
        return False, reasons

    if not prepared.page:
        reasons.append("page_alive:page_missing")
        return False, reasons

    try:
        if prepared.page.is_closed():
            reasons.append("page_alive:page_closed")
            return False, reasons
    except Exception:
        reasons.append("page_alive:page_unreachable")
        return False, reasons

    baseline = prepared.invariant_baseline or {}
    current_url = ""
    try:
        current_url = prepared.page.url
    except Exception:
        reasons.append("navigation:page_url_unreachable")
        return False, reasons

    base_url = baseline.get("page_url") or baseline.get("form_url") or prepared.form_url
    if base_url and current_url:
        from urllib.parse import urlparse
        base_path = urlparse(base_url).path.rstrip("/")
        cur_path = urlparse(current_url).path.rstrip("/")
        if base_path and cur_path and base_path != cur_path:
            reasons.append(f"navigation:{base_path}!={cur_path}")

    if prepared.prep.contact_form_scope != baseline.get("contact_form_scope"):
        reasons.append(
            f"form_identity:{baseline.get('contact_form_scope')}!={prepared.prep.contact_form_scope}"
        )

    cur_fp = _fields_fingerprint(prepared.prep.fields or {})
    if baseline.get("fields_fingerprint") and cur_fp != baseline["fields_fingerprint"]:
        reasons.append(f"field_map_mutation:{baseline['fields_fingerprint']}!={cur_fp}")

    cur_fm = prepared.prep.field_map or {}
    base_fm = baseline.get("field_map") or {}
    for key in ("company", "name", "email", "message", "consent"):
        if base_fm.get(key) in ("FILLED", "FOUND") and cur_fm.get(key) in ("MISSING", "AMBIGUOUS", None):
            reasons.append(f"field_regression:{key}:{base_fm.get(key)}->{cur_fm.get(key)}")

    submit_sel = (prepared.prep.fields or {}).get("submit_button") or baseline.get("submit_button")
    if baseline.get("submit_button") and submit_sel != baseline["submit_button"]:
        reasons.append(f"submit_target:{baseline['submit_button']}!={submit_sel}")

    from canonical_submit_target import validate_authorized_submit_target

    baseline_submit = baseline.get("canonical_submit_target") or prepared.prep.canonical_submit_target or {}
    restored_scope = await _restore_contact_form_scope(
        prepared.page,
        prepared.prep.contact_form_scope or "",
        submit_sel or "",
    )
    if restored_scope and restored_scope != prepared.prep.contact_form_scope:
        prepared.prep.contact_form_scope = restored_scope
    target_ok, target_reasons, live_record = await validate_authorized_submit_target(
        prepared.page,
        contact_form_scope=restored_scope,
        submit_selector=submit_sel,
        baseline_record=baseline_submit if baseline_submit.get("submit_selector") else None,
    )
    if not target_ok:
        reasons.extend(target_reasons)
    else:
        prepared.prep.final_submit_identified = True
        prepared.prep.canonical_submit_target = live_record
        if live_record.get("label"):
            prepared.prep.final_submit_label = live_record.get("label")

    if prepared.page and prepared.prep.fields:
        field_selectors = {
            k: v for k, v in prepared.prep.fields.items()
            if (k.endswith("_field") or k == "submit_button") and v
        }
        try:
            missing = await prepared.page.evaluate(_FIELDS_EXIST_JS, field_selectors)
            if missing:
                reasons.append(f"fields_missing:{','.join(missing[:5])}")
        except Exception:
            reasons.append("fields_exist:check_failed")

    if check_captcha and prepared.page:
        try:
            captcha = await prepared.page.evaluate(_CAPTCHA_DETECT_JS)
            if captcha:
                reasons.append("captcha:appeared_after_prepare")
        except Exception:
            pass

    if prepared.prep.mapping_hash != prepared.authorization_hash:
        reasons.append(
            f"mapping_hash_mutation:{prepared.authorization_hash}!={prepared.prep.mapping_hash}"
        )

    return not bool(reasons), reasons
