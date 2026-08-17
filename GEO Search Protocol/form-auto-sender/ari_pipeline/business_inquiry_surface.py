"""
business_inquiry_surface.py — Reject patient/reservation-only contact surfaces for R2.
"""

from __future__ import annotations

import re
from typing import Any

# URL / path signals for non-business inquiry surfaces
_PATIENT_FORM_URL_PATTERNS: tuple[str, ...] = (
    "/reserve", "/reservation", "/booking", "/book/", "/yoyaku", "/予約",
    "/appointment", "/schedule", "/shoshin", "/初診", "/saishin", "/再診",
    "/counseling-reserve", "/consultation-reserve", "/patient", "/member-only",
    "/members-only", "/first-visit", "/visit-reserve",
)

# Page / form title markers (patient-facing)
_PATIENT_SURFACE_MARKERS: tuple[str, ...] = (
    "初診予約", "再診予約", "来院予約", "診察予約", "治療予約", "施術予約",
    "カウンセリング予約", "無料カウンセリング予約", "体験予約", "予約フォーム",
    "初診の方", "再診の方", "患者様専用", "会員専用", "診察券", "症状について",
    "問診票", "医療問診", "初診受付", "WEB予約", "オンライン予約",
    "appointment booking", "book an appointment", "patient form",
)

# Business-compatible surface markers (positive signal when present)
_BUSINESS_SURFACE_MARKERS: tuple[str, ...] = (
    "お問い合わせ", "問い合わせ", "問合せ", "contact", "inquiry",
    "法人", "取材", "提携", "営業", "ご依頼", "その他",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _contains_any(blob: str, patterns: tuple[str, ...]) -> bool:
    low = blob.lower()
    return any(p.lower() in low for p in patterns)


def assess_business_inquiry_surface(
    *,
    form_url: str = "",
    page_title: str = "",
    form_heading: str = "",
    h1_text: str = "",
    detection: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """
    Returns (acceptable, reason).
    acceptable=True when surface appears business/general inquiry compatible.
    """
    det = detection or {}
    url = form_url or det.get("form_url") or ""
    blob = _norm(" ".join([
        url, page_title, form_heading, h1_text,
        det.get("page_title") or "",
        det.get("form_heading") or "",
        det.get("failure_reason") or "",
    ]))

    if _contains_any(url, _PATIENT_FORM_URL_PATTERNS):
        return False, "patient_reservation_url"

    if _contains_any(blob, _PATIENT_SURFACE_MARKERS):
        # Allow if strong business marker coexists in same blob
        if not _contains_any(blob, _BUSINESS_SURFACE_MARKERS):
            return False, "patient_reservation_surface"

    return True, ""


def assess_from_lightweight_record(record: dict) -> tuple[bool, str]:
    det = record.get("detection") or {}
    return assess_business_inquiry_surface(
        form_url=record.get("form_url") or det.get("form_url") or "",
        page_title=det.get("page_title") or "",
        form_heading=det.get("form_heading") or "",
        h1_text=det.get("h1_text") or "",
        detection=det,
    )
