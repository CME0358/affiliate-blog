"""
observations/video_segment.py — Deterministic industry → preview video segment.

Separate from commercial_fit scoring. Ambiguous / unknown → membership (generic merged).
"""

from __future__ import annotations

VIDEO_SEGMENTS = ("dental", "clinic", "tax", "membership", "estate")

_DENTAL = (
    "歯科",
    "歯科医院",
    "歯科クリニック",
    "矯正歯科",
    "審美歯科",
    "インプラント",
)
_CLINIC = (
    "美容クリニック",
    "美容皮膚科",
    "美容外科",
    "医療脱毛",
    "AGA",
    "自由診療",
)
_TAX = (
    "税理士",
    "会計事務所",
    "会計士",
)
_ESTATE = (
    "不動産",
)
_MEMBERSHIP = (
    "パーソナルジム",
    "フィットネス",
    "ピラティス",
    "ヨガ",
    "スクール",
    "会員制",
)


def normalize_video_segment(segment: str | None) -> str:
    """Backward compat: legacy generic → membership."""
    value = (segment or "").strip() or "membership"
    if value == "generic":
        return "membership"
    if value in VIDEO_SEGMENTS:
        return value
    return "membership"


def classify_video_segment(industry: str | None) -> str:
    """Map candidate industry string to preview video segment. Default: membership."""
    text = (industry or "").strip()
    if not text:
        return "membership"

    for keyword in _DENTAL:
        if keyword in text:
            return "dental"
    for keyword in _CLINIC:
        if keyword in text:
            return "clinic"
    for keyword in _TAX:
        if keyword in text:
            return "tax"
    for keyword in _ESTATE:
        if keyword in text:
            return "estate"
    for keyword in _MEMBERSHIP:
        if keyword in text:
            return "membership"
    return "membership"


PREVIEW_VIDEO_SEGMENT_TO_SCENE_ID: dict[str, str] = {
    "membership": "01",
    "estate": "02",
    "tax": "03",
    "dental": "04",
    "clinic": "05",
}

PREVIEW_SCENE_FILES: dict[str, str] = {
    "01": "scene-01-ai-search.mp4",
    "02": "scene-02-compare.mov",
    "03": "scene-03-recommend.mov",
    "04": "scene-04-booking.mov",
    "05": "scene-05-action.mov",
}


def resolve_preview_video_asset(segment: str | None) -> str:
    """Resolve persisted video_segment to preview page asset filename."""
    seg = normalize_video_segment(segment)
    scene_id = PREVIEW_VIDEO_SEGMENT_TO_SCENE_ID[seg]
    return PREVIEW_SCENE_FILES[scene_id]


def _industry_matches(industry: str, keywords: tuple[str, ...]) -> bool:
    text = (industry or "").strip()
    return any(k in text for k in keywords)


def validate_p1_video_segment(industry_name: str | None, video_segment: str | None) -> tuple[str, str]:
    """
    P1 commercial-fit preview validation.
    Returns (validation_status, reason) where status is PASS or REVIEW.
    """
    seg = normalize_video_segment(video_segment)
    industry = (industry_name or "").strip()

    if seg in ("membership", "estate", "tax"):
        return "REVIEW", f"VIDEO_SEGMENT_MISMATCH: P1 candidate mapped to {seg}"

    if _industry_matches(industry, _DENTAL):
        if seg != "dental":
            return "REVIEW", f"VIDEO_SEGMENT_MISMATCH: dental P1 expected dental, got {seg}"
        return "PASS", ""

    if _industry_matches(industry, _CLINIC):
        if seg != "clinic":
            return "REVIEW", f"VIDEO_SEGMENT_MISMATCH: cosmetic clinic P1 expected clinic, got {seg}"
        return "PASS", ""

    if seg not in ("dental", "clinic"):
        return (
            "REVIEW",
            f"VIDEO_SEGMENT_MISMATCH: P1 medical expected dental/clinic, got {seg}",
        )
    return "PASS", ""
