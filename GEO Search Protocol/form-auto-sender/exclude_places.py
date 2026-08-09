"""
exclude_places.py — Vault 共通除外（config/exclude_places.json）

daily_collect と form-auto-sender の両方から参照する。
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from config import VAULT_ROOT

EXCLUDE_PLACES_PATH = (
    VAULT_ROOT / "40_Sales" / "営業自動化ツール" / "config" / "exclude_places.json"
)


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/").lower()


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _name_matches(company_name: str, rule: dict) -> bool:
    name = (company_name or "").strip()
    if not name:
        return False
    full = (rule.get("company_name") or "").strip()
    if full and (name == full or full in name or name in full):
        return True
    for frag in rule.get("name_contains") or []:
        frag = str(frag).strip()
        if frag and frag in name:
            return True
    return False


def load_exclude_places() -> list[dict]:
    if not EXCLUDE_PLACES_PATH.exists():
        return []
    raw = json.loads(EXCLUDE_PLACES_PATH.read_text(encoding="utf-8"))
    return list(raw.get("places") or [])


def is_excluded_place(company: dict) -> tuple[bool, str]:
    """
    共通除外に該当すれば (True, reason)。
    company: company_name / website_url / place_id または name / website（daily_collect 互換）
    """
    name = (company.get("company_name") or company.get("name") or "").strip()
    url = _normalize_url(company.get("website_url") or company.get("website") or "")
    host = _host_of(url)
    place_id = (company.get("place_id") or company.get("id") or "").strip()

    for rule in load_exclude_places():
        reason = rule.get("reason") or "user_excluded"
        rule_url = _normalize_url(rule.get("website_url") or "")
        rule_host = _host_of(rule.get("website_url") or "")
        if rule_url and url and (url == rule_url or rule_url in url or url in rule_url):
            return True, reason
        if rule_host and host and (host == rule_host or rule_host in host):
            return True, reason
        if place_id and place_id == (rule.get("place_id") or "").strip():
            return True, reason
        if _name_matches(name, rule):
            return True, reason
    return False, ""
