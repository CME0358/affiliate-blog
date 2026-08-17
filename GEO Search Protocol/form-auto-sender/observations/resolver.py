"""
observations/resolver.py — Deterministic Observation Code → approved copy mapping.

No LLM generation. All outbound/preview text comes from catalog.json.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).resolve().parent / "catalog.json"

# Report FormPage industry options (must match agent-readiness-report.jsx)
FORM_INDUSTRY_OPTIONS = (
    "小売・EC",
    "飲食・フード",
    "美容・ヘルスケア",
    "不動産",
    "教育・スクール",
    "医療・歯科",
    "宿泊・ホテル",
    "フィットネス",
    "その他",
)

INDUSTRY_TO_FORM: dict[str, str] = {
    "美容クリニック": "美容・ヘルスケア",
    "エステサロン": "美容・ヘルスケア",
    "ホワイトニング・審美歯科": "美容・ヘルスケア",
    "歯科": "医療・歯科",
    "歯科クリニック": "医療・歯科",
    "歯科・歯医者": "医療・歯科",
    "パーソナルジム": "フィットネス",
    "フィットネスクラブ": "フィットネス",
    "ヨガスタジオ・ピラティス": "フィットネス",
    "飲食店": "飲食・フード",
    "不動産会社": "不動産",
    "不動産売却・査定": "不動産",
    "学習塾・個別指導塾": "教育・スクール",
    "プログラミングスクール": "教育・スクール",
    "予備校・大学受験対策": "教育・スクール",
    "結婚式場・葬儀社": "宿泊・ホテル",
    "小売・EC": "小売・EC",
}


def map_industry_to_form(industry_name: str) -> str:
    name = (industry_name or "").strip()
    if name in FORM_INDUSTRY_OPTIONS:
        return name
    if name in INDUSTRY_TO_FORM:
        return INDUSTRY_TO_FORM[name]
    for key, mapped in INDUSTRY_TO_FORM.items():
        if key in name or name in key:
            return mapped
    return "その他"


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    with CATALOG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)


def normalize_crawler_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize CSV column names to resolver field keys (reservation crawler path)."""
    faq = _as_int(row.get("faq") or row.get("FAQ"))
    schema_org = _as_int(row.get("schema_org") or row.get("Schema.org"))
    reservation_button = _as_int(row.get("reservation_button") or row.get("予約ボタン"))
    local_business = _as_int(row.get("local_business") or row.get("LocalBusiness"))
    reservation_url = (row.get("reservation_url") or "").strip()
    return {
        "evidence_source": row.get("evidence_source") or "reservation_crawler",
        "site_reachable": _as_bool(row.get("site_reachable", True)),
        "faq": faq,
        "schema_org": schema_org,
        "reservation_action": _as_int(row.get("reservation_action") or row.get("ReservationAction")),
        "local_business": local_business,
        "sns_link": _as_int(row.get("sns_link") or row.get("SNSリンク")),
        "google_map_embed": _as_int(row.get("google_map_embed") or row.get("GoogleMap埋め込み")),
        "reservation_button": reservation_button,
        "has_reservation_url": bool(reservation_url),
        "reservation_url": reservation_url,
        "has_llms_txt": _as_bool(row.get("has_llms_txt", False)),
        "has_robots_txt": _as_bool(row.get("has_robots_txt", False)),
        "run_date": (row.get("run_date") or "").strip(),
        "clinic_name": (row.get("clinic_name") or row.get("店舗名") or "").strip(),
        "url": (row.get("url") or row.get("HP URL") or "").strip(),
    }


def normalize_generic_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize generic scan evidence row for resolver."""
    return {
        "evidence_source": "generic_scan",
        "site_reachable": _as_bool(row.get("site_reachable", False)),
        "action_path_scanned": _as_bool(row.get("action_path_scanned", False)),
        "action_path_present": _as_bool(row.get("action_path_present", False)),
        "faq_scanned": _as_bool(row.get("faq_scanned", False)),
        "faq_present": _as_bool(row.get("faq_present", False)),
        "schema_scanned": _as_bool(row.get("schema_scanned", False)),
        "schema_present": _as_bool(row.get("schema_present", False)),
        "service_info_scanned": _as_bool(row.get("service_info_scanned", False)),
        "service_info_ok": _as_bool(row.get("service_info_ok", False)),
        "service_info_weak": _as_bool(row.get("service_info_weak", False)),
        "llms_txt_scanned": _as_bool(row.get("llms_txt_scanned", False)),
        "has_llms_txt": _as_bool(row.get("has_llms_txt", False)),
        "scanned_at": (row.get("scanned_at") or "").strip(),
        "url": (row.get("url") or row.get("website_url") or "").strip(),
    }


def normalize_evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    if (row.get("evidence_source") or "") == "generic_scan":
        return normalize_generic_row(row)
    return normalize_crawler_row(row)


def _catalog_observations_for_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    catalog = load_catalog()
    src = (row.get("evidence_source") or "reservation_crawler")
    out: list[dict[str, Any]] = []
    for obs in catalog.get("observations", []):
        obs_src = obs.get("evidence_source")
        if src == "generic_scan":
            if obs_src not in (None, "generic_scan"):
                continue
            if obs_src is None and obs.get("code") != "OBS_SITE_UNREACHABLE":
                continue
        else:
            if obs_src == "generic_scan":
                continue
        out.append(obs)
    return out


def _eval_condition(evidence: dict[str, Any], data: dict[str, Any]) -> bool:
    if "any_of" in evidence:
        return any(_eval_condition(item, data) for item in evidence["any_of"])
    if "all_of" in evidence:
        return all(_eval_condition(item, data) for item in evidence["all_of"])

    field = evidence.get("field")
    if not field:
        return False
    actual = data.get(field)
    op = evidence.get("operator", "==")

    if op == "==":
        expected = evidence.get("value", evidence.get("threshold"))
        if isinstance(expected, bool):
            return _as_bool(actual) == expected
        return _as_int(actual) == _as_int(expected)
    if op == ">=":
        return _as_int(actual) >= _as_int(evidence.get("threshold", 0))
    if op == ">":
        return _as_int(actual) > _as_int(evidence.get("threshold", 0))
    if op == "<":
        return _as_int(actual) < _as_int(evidence.get("threshold", 0))
    if op == "between":
        val = _as_int(actual)
        return _as_int(evidence.get("min", 0)) <= val <= _as_int(evidence.get("max", 0))
    return False


def resolve_observations(data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Return all matching observation definitions (ordered by display_priority).
    Excludes OBS_SITE_UNREACHABLE from consumer-facing lists via filter at call site.
    """
    normalized = normalize_evidence_row(data)
    matched: list[dict[str, Any]] = []

    for obs in _catalog_observations_for_row(normalized):
        evidence = obs.get("source_evidence") or {}
        if _eval_condition(evidence, normalized):
            matched.append({
                "code": obs["code"],
                "approved_copy": obs.get("approved_copy", ""),
                "qualification": obs.get("qualification", ""),
                "severity": obs.get("severity", "medium"),
                "display_priority": obs.get("display_priority", 100),
                "check_item_id": obs.get("check_item_id"),
                "check_status": obs.get("check_status"),
            })

    matched.sort(key=lambda x: x["display_priority"])
    return matched


def select_message_observations(data: dict[str, Any], *, max_count: int | None = None) -> list[dict[str, Any]]:
    catalog = load_catalog()
    limit = max_count if max_count is not None else int(catalog.get("max_observations_per_message", 2))
    all_obs = resolve_observations(data)
    filtered = [
        o for o in all_obs
        if o["code"] != "OBS_SITE_UNREACHABLE" and o.get("approved_copy")
    ]
    # Prefer warn/medium over info/pass for message urgency; still deterministic via priority sort
    return filtered[:limit]


def build_check_summary(data: dict[str, Any]) -> dict[str, Any]:
    catalog = load_catalog()
    normalized = normalize_evidence_row(data)
    if not normalized.get("site_reachable", True):
        return {
            "checked_count": 0,
            "total_teaser": int(catalog.get("preview_teaser_total", 23)),
            "check_items": [],
            "blocked": True,
        }

    item_defs = {item["id"]: item for item in catalog.get("check_items", [])}
    statuses: dict[str, str] = {item_id: "unknown" for item_id in item_defs}

    for obs in resolve_observations(data):
        item_id = obs.get("check_item_id")
        status = obs.get("check_status")
        if not item_id or item_id not in statuses or not status:
            continue
        # pass beats warn; warn beats unknown
        rank = {"unknown": 0, "warn": 1, "pass": 2}
        if rank.get(status, 0) >= rank.get(statuses[item_id], 0):
            statuses[item_id] = status

    check_items = [
        {
            "id": item_id,
            "label": item_defs[item_id]["label"],
            "status": statuses[item_id],
        }
        for item_id in item_defs
    ]
    checked_count = sum(1 for item in check_items if item["status"] in ("pass", "warn"))

    return {
        "checked_count": checked_count,
        "total_teaser": int(catalog.get("preview_teaser_total", 23)),
        "check_items": check_items,
        "blocked": False,
    }


def build_preview_payload(
    *,
    company_name: str,
    url: str,
    industry_name: str,
    crawler_data: dict[str, Any],
    candidate_id: str = "",
) -> dict[str, Any]:
    """Public-safe preview payload (no raw scores)."""
    normalized = normalize_evidence_row(crawler_data)
    summary = build_check_summary(crawler_data)
    observations = select_message_observations(crawler_data)

    crawled_at = normalized.get("run_date") or normalized.get("scanned_at") or None

    return {
        "company_name": company_name,
        "url": url,
        "industry": map_industry_to_form(industry_name),
        "industry_source": industry_name,
        "candidate_id": candidate_id,
        "crawled_at": crawled_at or normalized.get("run_date") or None,
        "observations": [
            {
                "code": o["code"],
                "copy": o["approved_copy"],
                "qualification": o["qualification"],
            }
            for o in observations
        ],
        "check_summary": {
            "checked_count": summary["checked_count"],
            "total_teaser": summary["total_teaser"],
            "check_items": summary["check_items"],
        },
        "blocked": summary.get("blocked", False),
    }
