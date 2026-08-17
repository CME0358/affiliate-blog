"""Preflight classification for ARI expansion batches."""

from __future__ import annotations

from inquiry_purpose_semantics import REASON_AMBIGUOUS, REASON_NO_COMPATIBLE
from submission_state import FORM_NOT_SUITABLE, MANUAL_INTERVENTION_REQUIRED

AUTO_READY = "AUTO_READY"
NOT_READY = "NOT_READY"

_ESTIMATE_URL_FRAGMENTS = ("/estimate/", "/mitsumori/", "見積")
_BUSINESS_VALIDATION_KWS = (
    "建物種別",
    "施工内容",
    "施工",
    "予算",
    "見積",
    "工事内容",
    "リフォーム箇所",
    "現場調査",
    "お住いのエリア",
    "メールアドレス(確認用)",
    "ご住所",
    "住所必須",
)


def _validation_error_text(fn: dict) -> str:
    vf = fn.get("validation_feedback") or {}
    errors = vf.get("errors") or []
    return " ".join(str(e) for e in errors)


def infer_business_unsuitable(fn: dict, form_url: str = "") -> tuple[bool, str]:
    """
    営業問い合わせとして合理的に埋められない業務固有フォームを検出。
    サイト固有ハードコードなし — URL / validation DOM / choice unsuitable のみ。
    """
    url_l = (form_url or fn.get("form_url") or "").lower()
    if any(f in url_l for f in _ESTIMATE_URL_FRAGMENTS):
        return True, "estimate_only"

    rc = fn.get("required_choices") or {}
    if rc.get("unsuitable"):
        return True, "service_specific_required"

    err = _validation_error_text(fn)
    if not err:
        return False, ""

    hits = [kw for kw in _BUSINESS_VALIDATION_KWS if kw in err]
    if len(hits) >= 2:
        if any(k in err for k in ("見積", "施工", "建物種別", "リフォーム")):
            return True, "service_specific_required"
        return True, "estimate_only"

    if any(k in err for k in ("ご住所", "お住いのエリア", "住所必須", "現住所")):
        if fn.get("multistep_state") == "VALIDATION_FAILED" and len(hits) >= 1:
            return True, "address_required"
        if "ご住所" in err and "建物" in err:
            return True, "address_required"

    if any(k in err for k in ("建物種別", "施工内容必須", "施工内容")):
        return True, "service_specific_required"

    return False, ""


def bucket_not_ready_reason(skip_reason: str, fn: dict) -> str:
    """NOT_READY / reject reason を failure pattern へ正規化。"""
    sr = (skip_reason or "").lower()
    er = (fn.get("reason") or "").lower()

    unsuitable, tag = infer_business_unsuitable(fn)
    if unsuitable and tag:
        return tag

    if fn.get("multistep_state") == "VALIDATION_FAILED":
        return "validation_required"

    if sr in ("no_final_submit",) or "no_final_submit" in sr:
        return "no_final_submit"
    if sr in ("timeout",) or er == "timeout":
        return "timeout"
    if "dynamic" in sr or er in ("dynamic_form_unresolved", "dynamic_submit_unresolved"):
        return "dynamic_unresolved"
    if er in ("external_iframe", "unsupported_custom_form", "submit_field_not_found"):
        return "unsupported"
    if sr.startswith("missing_") or "missing_" in sr:
        return "validation_required"
    if sr.startswith("business_required") or sr.startswith("unsuitable_required"):
        return "service_specific_required"
    if sr.startswith("dom_unsuitable"):
        return "unsupported"
    return "other"


def _required_field_profile(field_map: dict) -> dict[str, str]:
    keys = (
        "company", "name", "email", "phone", "message", "subject", "consent",
    )
    return {k: field_map.get(k, "MISSING") for k in keys}


def classify_preflight(pf: dict) -> tuple[str, str, dict]:
    """
    Returns (classification, skip_reason, required_field_profile).
    """
    fn = pf.get("fill_no_submit") or {}
    fm = fn.get("field_map") or {}
    profile = _required_field_profile(fm)

    if pf.get("duplicate_lock"):
        return NOT_READY, "duplicate_lock", profile

    if fn.get("form_not_suitable") or fn.get("reason") == "form_not_suitable":
        fields = fn.get("unsuitable_fields") or []
        detail = fields[0].get("name", "unsuitable") if fields else "dom_unsuitable"
        return FORM_NOT_SUITABLE, f"dom_unsuitable:{detail}", profile

    if fn.get("reason") in (REASON_NO_COMPATIBLE, REASON_AMBIGUOUS):
        return FORM_NOT_SUITABLE, fn.get("reason"), profile

    if fn.get("reason") == "unsuitable_required_choices":
        rc = fn.get("required_choices") or {}
        uns = rc.get("unsuitable") or []
        detail = uns[0].get("name", "required_choice") if uns else "required_choice"
        return FORM_NOT_SUITABLE, f"unsuitable_required:{detail}", profile

    unsuitable_labels = fn.get("unsuitable_required_labels") or []
    if unsuitable_labels:
        return FORM_NOT_SUITABLE, f"business_required:{unsuitable_labels[0][:40]}", profile

    reason = (fn.get("reason") or "").lower()
    if fn.get("captcha_detected") or "captcha" in reason or "recaptcha" in reason:
        return MANUAL_INTERVENTION_REQUIRED, "captcha_or_human_verification", profile

    if fn.get("status") == "error":
        er = fn.get("reason") or "error"
        if er in (
            "insufficient_message_capacity",
            "message_field_not_found",
            "email_field_not_found",
            "submit_field_not_found",
            "external_iframe",
            "dynamic_form_unresolved",
            "unsupported_custom_form",
        ):
            if er == "insufficient_message_capacity":
                return FORM_NOT_SUITABLE, er, profile
            return NOT_READY, er, profile
        return NOT_READY, er, profile

    if fn.get("status") == "skipped":
        sr = fn.get("reason") or "skipped"
        if sr in ("insufficient_message_capacity", "compact_message_exceeds_maxlength"):
            return FORM_NOT_SUITABLE, sr, profile
        return NOT_READY, sr, profile

    if fn.get("blocked"):
        br = fn.get("reason") or "blocked"
        if "captcha" in str(br).lower():
            return MANUAL_INTERVENTION_REQUIRED, br, profile
        return NOT_READY, br, profile

    if not fn.get("final_submit_identified"):
        fixes = fn.get("required_fixes") or []
        form_url = pf.get("form_url") or fn.get("form_url") or ""
        unsuitable, tag = infer_business_unsuitable(fn, form_url)
        if unsuitable:
            return FORM_NOT_SUITABLE, tag, profile
        for fx in fixes:
            if "no_final_submit" in fx or "dynamic_submit" in fx:
                return NOT_READY, "no_final_submit", profile
            if "MULTI_STEP" in fx:
                return NOT_READY, "multi_step_unresolved", profile
        if fn.get("multistep_state") == "VALIDATION_FAILED":
            return NOT_READY, "validation_required", profile
        return NOT_READY, "no_final_submit", profile

    mv = fn.get("message_validation") or {}
    if not mv.get("pass"):
        return NOT_READY, "message_validation_fail", profile

    for k in ("name", "email", "message"):
        if fm.get(k) in ("MISSING", "AMBIGUOUS"):
            return NOT_READY, f"missing_{k}", profile

    sel = fn.get("message_selection") or {}
    if sel.get("skipped"):
        return NOT_READY, sel.get("skip_reason") or "maxlength", profile

    return AUTO_READY, "", profile
