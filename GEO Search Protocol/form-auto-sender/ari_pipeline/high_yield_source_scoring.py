"""
high_yield_source_scoring.py — READY probability scoring BEFORE expensive PF/RF.

Builds HIGH_YIELD_SOURCE_SIGNATURES from historical CONFIRMED_SENT + READY artifacts
and cheap pre-PF signals (URL, FAST_HTTP, LW detection).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ari_pipeline.proven_pattern_library import (
    infer_framework_from_signals,
    load_pattern_library,
)
from ari_pipeline.r2_lane_c_filter import lane_c_industry_tier, lane_c_url_pattern_score
from ari_pipeline.r2_industry_filter import classify_r2_industry, is_remodel_industry

READY_PRIORITY_A = "READY_PRIORITY_A"
READY_PRIORITY_B = "READY_PRIORITY_B"
SLOW_PATH = "SLOW_PATH"

# Discriminating weights from historical CONFIRMED_SENT audit (816 domains)
_FRAMEWORK_READY_WEIGHT = {
    "contact_form_7": 95,
    "mw_wp_form": 90,
    "formmail": 85,
    "generic_contact_path": 80,
    "generic_html_form": 75,
    "jimdo": 60,
    "google_forms": 20,
}

_NEGATIVE_FAST_OUTCOMES = frozenset({
    "CAPTCHA", "RESERVATION", "UNREACHABLE", "NO_HTML", "SLOW_PATH",
})


@dataclass
class HighYieldScore:
    domain: str
    score: int
    tier: str
    signals: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def _known_contact_url(candidate: dict) -> bool:
    web = (candidate.get("website_url") or "").strip().rstrip("/")
    lw = (candidate.get("lw_entry_url") or "").strip().rstrip("/")
    if lw and web and lw != web:
        return True
    return lane_c_url_pattern_score(lw or web) >= 70


def _fast_http_meta(candidate: dict, cp: dict | None = None) -> dict[str, Any]:
    dom = (candidate.get("domain") or "").lower()
    if cp and dom:
        return (cp.get("fast_http_results") or {}).get(dom) or {}
    return candidate.get("fast_http") or {}


def _lw_detection_meta(candidate: dict) -> dict[str, Any]:
    det = candidate.get("detection") or {}
    if det:
        return det
    return candidate.get("lightweight_evidence") or {}


def build_high_yield_signatures() -> dict[str, Any]:
    """Derived signature catalog from historical success + READY artifacts."""
    library = load_pattern_library()
    patterns = library.get("patterns") or []
    fast_eligible = [p for p in patterns if p.get("fast_path_eligible")]
    top_fw = Counter(p.get("framework") for p in fast_eligible).most_common(10)
    return {
        "known_contact_url": {"weight": 120, "description": "lw_entry_url is explicit contact path"},
        "generic_contact_path": {"weight": 120, "url_markers": ["/contact", "/inquiry", "/otoiawase", "/form"]},
        "generic_html_form": {"weight": 75, "description": "Historical dominant success structure"},
        "cf7_markers": {"weight": 90, "markers": ["wpcf7", "contact-form-7"]},
        "mwform_markers": {"weight": 85, "markers": ["mwform", "mw_wp_form"]},
        "standard_name_email_message": {"weight": 60, "requires": ["has_form", "has_textarea", "has_email_input"]},
        "no_reservation_signals": {"weight": 50, "negative_url": ["/reserve", "/booking", "/yoyaku"]},
        "no_captcha_signals": {"weight": 40, "fast_outcome_block": list(_NEGATIVE_FAST_OUTCOMES)},
        "no_inquiry_purpose_field": {"weight": 30, "description": "No required business-specific choice pre-PF"},
        "industry_tier_1": {"weight": 40, "examples": ["不動産", "引越", "人材派遣"]},
        "industry_tier_2": {"weight": 20, "examples": ["税理", "司法書士", "清掃"]},
        "historical_framework_weights": dict(_FRAMEWORK_READY_WEIGHT),
        "proven_pattern_count": len(fast_eligible),
        "top_proven_frameworks": dict(top_fw),
    }


def score_source_candidate(
    candidate: dict,
    *,
    cp: dict | None = None,
    signatures: dict[str, Any] | None = None,
) -> HighYieldScore:
    """Score a source row using only pre-PF/RF attributes."""
    signatures = signatures or build_high_yield_signatures()
    dom = (candidate.get("domain") or "").lower()
    score = 0
    reasons: list[str] = []
    signals: dict[str, Any] = {}

    industry = candidate.get("industry_name") or ""
    name = candidate.get("company_name") or ""
    url = candidate.get("lw_entry_url") or candidate.get("website_url") or ""
    url_score = lane_c_url_pattern_score(url)
    fast = _fast_http_meta(candidate, cp)
    fast_out = fast.get("outcome") or ""
    fast_signals = fast.get("signals") or {}
    det = _lw_detection_meta(candidate)

    # Hard deprioritize / SLOW_PATH triggers
    if is_remodel_industry(industry):
        score -= 80
        reasons.append("remodel_industry")
    if classify_r2_industry(industry):
        score -= 60
        reasons.append("dental_esthetic_medical")
    if fast_out in ("CAPTCHA",):
        score -= 200
        reasons.append("fast_captcha")
    if fast_out in ("RESERVATION",):
        score -= 150
        reasons.append("fast_reservation")
    if fast_out in ("UNREACHABLE", "NO_HTML"):
        score -= 100
        reasons.append(f"fast_{fast_out.lower()}")

    # Positive signatures
    if _known_contact_url(candidate):
        score += 120
        reasons.append("known_contact_url")
        signals["known_contact_url"] = True

    if url_score >= 120:
        score += 120
        reasons.append("generic_contact_path")
    elif url_score >= 70:
        score += 70
        reasons.append("contact_url_partial")

    fw = infer_framework_from_signals(form_url=url, submit_pattern=det.get("submit_label") or "")
    fw_weight = _FRAMEWORK_READY_WEIGHT.get(fw, 40)
    score += fw_weight
    signals["inferred_framework"] = fw
    if fw in ("contact_form_7", "mw_wp_form", "formmail"):
        reasons.append(f"framework_{fw}")

    if fast_signals.get("has_framework") or any(
        m in (fast.get("reason") or "").lower() for m in ("wpcf7", "mwform")
    ):
        score += 80
        reasons.append("fast_framework_marker")

    if fast_signals.get("has_form"):
        score += 40
    if fast_signals.get("has_textarea"):
        score += 30
    if fast_signals.get("has_email_input"):
        score += 30
    if fast_signals.get("has_form") and fast_signals.get("has_textarea"):
        reasons.append("standard_html_form_fields")

    tier_ind = lane_c_industry_tier(industry, name)
    if tier_ind == 1:
        score += 40
        reasons.append("industry_tier_1")
    elif tier_ind == 2:
        score += 20
        reasons.append("industry_tier_2")
    elif tier_ind is None and not is_remodel_industry(industry):
        score -= 30
        reasons.append("industry_excluded_or_low")

    if det.get("captcha"):
        score -= 100
        reasons.append("lw_captcha")
    if (det.get("form_type") or "") in ("MULTI_STEP", "LOGIN_REQUIRED", "EXTERNAL_FORM"):
        score -= 50
        reasons.append(f"lw_form_type_{det.get('form_type')}")

    if candidate.get("lightweight_outcome") == "PREFLIGHT_CANDIDATE":
        score += 25
        reasons.append("lw_preflight_candidate")

    # Tier assignment
    negative = any(r.startswith(("fast_captcha", "fast_reservation", "fast_unreachable", "dental", "remodel")) for r in reasons)
    if negative or score < 80:
        tier = SLOW_PATH
    elif score >= 220 and tier_ind in (1, 2) and url_score >= 70:
        tier = READY_PRIORITY_A
    elif score >= 140:
        tier = READY_PRIORITY_B
    else:
        tier = SLOW_PATH

    return HighYieldScore(domain=dom, score=score, tier=tier, signals=signals, reasons=reasons)


def annotate_source_pool(pool: list[dict], *, cp: dict | None = None) -> list[dict]:
    """Add ready_yield_score / ready_priority_tier to each candidate."""
    sigs = build_high_yield_signatures()
    out: list[dict] = []
    for c in pool:
        hs = score_source_candidate(c, cp=cp, signatures=sigs)
        row = {
            **c,
            "ready_yield_score": hs.score,
            "ready_priority_tier": hs.tier,
            "ready_yield_signals": hs.signals,
            "ready_yield_reasons": hs.reasons[:8],
        }
        out.append(row)
    return out


def sort_by_ready_priority(pool: list[dict]) -> list[dict]:
    tier_order = {READY_PRIORITY_A: 0, READY_PRIORITY_B: 1, SLOW_PATH: 2}
    return sorted(
        pool,
        key=lambda r: (
            tier_order.get(r.get("ready_priority_tier"), 9),
            -int(r.get("ready_yield_score") or 0),
            -int(r.get("url_pattern_score") or 0),
            r.get("industry_tier", 99),
        ),
    )


def select_priority_pool(
    pool: list[dict],
    tier: str,
    *,
    limit: int | None = None,
    exclude_domains: set[str] | None = None,
) -> list[dict]:
    excluded = exclude_domains or set()
    rows = [
        c for c in pool
        if c.get("ready_priority_tier") == tier
        and (c.get("domain") or "").lower() not in excluded
    ]
    rows = sort_by_ready_priority(rows)
    if limit:
        rows = rows[:limit]
    return rows


def tier_counts(pool: list[dict]) -> dict[str, int]:
    return dict(Counter(c.get("ready_priority_tier") for c in pool))
