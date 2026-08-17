"""
cf7_feedback.py — Contact Form 7 REST feedback response contract

Endpoint pattern:
  /wp-json/contact-form-7/v1/contact-forms/{id}/feedback

Never auto-infer success from POST alone — parse response body status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# CF7 REST API status values (plugin canonical)
CF7_MAIL_SENT = "mail_sent"
CF7_VALIDATION_FAILED = "validation_failed"
CF7_MAIL_FAILED = "mail_failed"
CF7_SPAM = "spam"
CF7_ABORTED = "aborted"

CF7_FAILURE_STATUSES = frozenset({
    CF7_MAIL_FAILED,
    CF7_SPAM,
    CF7_ABORTED,
})

CF7_FEEDBACK_URL_FRAGMENT = "contact-form-7/v1/contact-forms"
CF7_FEEDBACK_PATH_SUFFIX = "/feedback"

# Fields that cannot be filled for cold outreach (honeypot / quiz / image CAPTCHA)
_CF7_UNSUITABLE_FIELD_FRAGMENTS = (
    "spam-block",
    "honeypot",
    "image_auth",
    "image-auth",
    "quiz",
    "captcha",
    "turnstile",
    "recaptcha",
)
_CF7_UNSUITABLE_MESSAGE_FRAGMENTS = (
    "image_auth",
    "スパム",
    "robot",
)
_CF7_STANDARD_FIELD_HINTS = {
    "your-name": "name",
    "name": "name",
    "your-email": "email",
    "email": "email",
    "your-phone": "phone",
    "tel": "phone",
    "phone": "phone",
    "your-message": "message",
    "message": "message",
    "your-subject": "subject",
    "subject": "subject",
    "your-company": "company",
    "company": "company",
    "acceptance": "consent",
    "consent": "consent",
}


@dataclass
class Cf7FeedbackResult:
    status: str = ""
    message: str = ""
    invalid_fields: list[dict[str, Any]] = field(default_factory=list)
    contact_form_id: str = ""
    posted_data_hash: str = ""
    into: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    parsed_ok: bool = False
    parse_error: str = ""


def is_cf7_feedback_url(url: str) -> bool:
    u = (url or "").lower()
    return CF7_FEEDBACK_URL_FRAGMENT in u and CF7_FEEDBACK_PATH_SUFFIX in u


def parse_cf7_feedback_body(body: Any) -> Cf7FeedbackResult:
    """Parse CF7 feedback JSON body into structured result."""
    if body is None:
        return Cf7FeedbackResult(parse_error="empty_body")
    if isinstance(body, str):
        import json
        try:
            body = json.loads(body)
        except Exception as exc:
            return Cf7FeedbackResult(parse_error=f"json_error:{exc}")
    if not isinstance(body, dict):
        return Cf7FeedbackResult(parse_error="not_object")

    status = str(body.get("status") or "").strip()
    invalid = body.get("invalid_fields")
    if invalid is None:
        invalid_list: list[dict] = []
    elif isinstance(invalid, list):
        invalid_list = [x for x in invalid if isinstance(x, dict)]
    else:
        invalid_list = []

    return Cf7FeedbackResult(
        status=status,
        message=str(body.get("message") or ""),
        invalid_fields=invalid_list,
        contact_form_id=str(body.get("contact_form_id") or ""),
        posted_data_hash=str(body.get("posted_data_hash") or ""),
        into=str(body.get("into") or ""),
        raw=body,
        parsed_ok=bool(status),
    )


def _map_cf7_field_name(field_name: str) -> str:
    name = (field_name or "").lower()
    for hint, logical in _CF7_STANDARD_FIELD_HINTS.items():
        if hint in name:
            return logical
    return ""


def _is_unsuitable_cf7_field(field_name: str, message: str = "", idref: str = "") -> bool:
    blob = f"{field_name} {message} {idref}".lower()
    return any(f in blob for f in _CF7_UNSUITABLE_FIELD_FRAGMENTS + _CF7_UNSUITABLE_MESSAGE_FRAGMENTS)


def analyze_cf7_invalid_fields(invalid_fields: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Parse CF7 invalid_fields into resolver-friendly categories.
    Returns form_not_suitable when honeypot / image-auth / spam-block detected.
    """
    unsuitable: list[dict[str, str]] = []
    missing_standard: list[dict[str, str]] = []
    other: list[dict[str, str]] = []
    for inv in invalid_fields or []:
        if not isinstance(inv, dict):
            continue
        field = str(inv.get("field") or "")
        message = str(inv.get("message") or "")
        idref = str(inv.get("idref") or "")
        entry = {"field": field, "message": message, "idref": idref}
        if _is_unsuitable_cf7_field(field, message, idref):
            unsuitable.append(entry)
            continue
        logical = _map_cf7_field_name(field)
        if logical:
            missing_standard.append({**entry, "logical": logical})
        else:
            other.append(entry)
    return {
        "form_not_suitable": bool(unsuitable),
        "unsuitable_fields": unsuitable,
        "missing_standard_fields": missing_standard,
        "other_fields": other,
    }


def cf7_result_to_dict(result: Cf7FeedbackResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "message": result.message,
        "invalid_fields": result.invalid_fields,
        "contact_form_id": result.contact_form_id,
        "posted_data_hash": result.posted_data_hash,
        "into": result.into,
        "parsed_ok": result.parsed_ok,
        "parse_error": result.parse_error,
        "invalid_analysis": analyze_cf7_invalid_fields(result.invalid_fields),
    }


def attach_cf7_feedback_capture(page) -> list[dict]:
    """Register async response listener; returns list appended on CF7 feedback JSON."""
    captured: list[dict] = []

    async def _on_response(response) -> None:
        if not is_cf7_feedback_url(response.url):
            return
        try:
            if response.ok:
                captured.append(await response.json())
        except Exception:
            pass

    page.on("response", _on_response)
    return captured


def classify_cf7_feedback(result: Cf7FeedbackResult) -> tuple[str | None, str]:
    """
    Map CF7 feedback to (submission_state | None, reason).
    None state → fall through to DOM / other detectors.
    """
    if not result.parsed_ok:
        if result.parse_error:
            return None, "cf7_response_unparseable"
        return None, "cf7_response_missing_status"

    status = result.status
    analysis = analyze_cf7_invalid_fields(result.invalid_fields)

    if status == CF7_MAIL_SENT:
        if analysis["form_not_suitable"]:
            uf = analysis["unsuitable_fields"][0]["field"]
            return "FORM_NOT_SUITABLE", f"cf7_unsuitable_field:{uf}"
        if result.invalid_fields:
            return "FAILED", "validation_failed"
        return "CONFIRMED_SENT", "cf7_mail_sent"

    if status == CF7_VALIDATION_FAILED or result.invalid_fields:
        if analysis["form_not_suitable"]:
            uf = analysis["unsuitable_fields"][0]["field"]
            return "FORM_NOT_SUITABLE", f"cf7_unsuitable_field:{uf}"
        return "FAILED", "validation_failed"

    if status in CF7_FAILURE_STATUSES:
        return "FAILED", f"cf7_{status}"

    # Unknown CF7 status string — do not guess
    return None, f"cf7_status_unknown:{status}"
