"""Shared candidate exclusion sets for ARI expansion / preselection."""

from __future__ import annotations

import csv
import json
import re
from urllib.parse import urlparse

from config import LOG_MANUALLY_EXCLUDED, LOG_SENT, VAULT_ROOT
from log_manager import LOG_SENT_STATUS_CORRECTIONS
from list_filter import classify_skip, get_config_exclusion_label
from parser import parse_md_file
from prepare_ari_production_batch import NOT_SUITABLE_NAMES
from submission_state import FORM_NOT_SUITABLE, MANUAL_INTERVENTION_REQUIRED

LIST_ROOT = VAULT_ROOT / "40_Sales" / "商談メモ" / "リスト"
BATCH30_LIST = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Production-Batch-30.md"
BATCH3_LIST = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-Expansion-Batch-3.md"

PREFLIGHT_JSON_GLOBS = (
    "70_outputs/5-Day-Sales-Sprint/ari_expansion_batch2_*.json",
    "70_outputs/5-Day-Sales-Sprint/ari_expansion_batch3_*.json",
    "70_outputs/5-Day-Sales-Sprint/ari_unknown_site_expansion*.json",
    "70_outputs/5-Day-Sales-Sprint/ari_compat_forensic_*.json",
)


def domain(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", (name or ""))


def _load_manually_excluded() -> tuple[set[str], set[str]]:
    names: set[str] = set()
    domains: set[str] = set()
    if not LOG_MANUALLY_EXCLUDED.exists():
        return names, domains
    with LOG_MANUALLY_EXCLUDED.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            n = normalize_name(row.get("company_name", ""))
            d = domain(row.get("website_url", ""))
            if n:
                names.add(n)
            if d:
                domains.add(d)
    return names, domains


def _load_definitive_skip_sets() -> tuple[set[str], set[str]]:
    names: set[str] = set()
    domains: set[str] = set()
    definitive = {FORM_NOT_SUITABLE, MANUAL_INTERVENTION_REQUIRED}
    for pattern in PREFLIGHT_JSON_GLOBS:
        for path in sorted(VAULT_ROOT.glob(pattern)):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for pf in data.get("preflights") or []:
                cls = pf.get("preflight_classification") or pf.get("classification")
                if cls in definitive:
                    names.add(normalize_name(pf.get("company_name", "")))
                    domains.add(pf.get("domain") or domain(pf.get("website_url", "")))
            for prod in data.get("production") or []:
                st = prod.get("submission_state") or prod.get("effective_status")
                if st in definitive:
                    names.add(normalize_name(prod.get("company_name", "")))
                    domains.add(prod.get("domain") or domain(prod.get("website_url", "")))
    names.discard("")
    domains.discard("")
    return names, domains


def _companies_from_locked_lists() -> list[dict]:
    out: list[dict] = []
    for path in (BATCH30_LIST, BATCH3_LIST):
        if path.exists():
            out.extend(parse_md_file(str(path)))
    return out


def _load_confirmed_sent_sets() -> tuple[set[str], set[str]]:
    """sent.csv + corrections を1回読み込み duplicate lock 用セット。"""
    from submission_state import should_block_duplicate_send

    names: set[str] = set()
    domains: set[str] = set()
    status_by_key: dict[str, str] = {}

    if LOG_SENT.exists():
        with LOG_SENT.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                n = normalize_name(row.get("company_name", ""))
                d = domain(row.get("website_url", ""))
                st = row.get("status") or "sent"
                if n:
                    status_by_key[f"n:{n}"] = st
                if d:
                    status_by_key[f"d:{d}"] = st

    if LOG_SENT_STATUS_CORRECTIONS.exists():
        with LOG_SENT_STATUS_CORRECTIONS.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                n = normalize_name(row.get("company_name", ""))
                d = domain(row.get("website_url", ""))
                st = row.get("corrected_status") or ""
                if n:
                    status_by_key[f"n:{n}"] = st
                if d:
                    status_by_key[f"d:{d}"] = st

    for key, st in status_by_key.items():
        if should_block_duplicate_send(st):
            if key.startswith("n:"):
                names.add(key[2:])
            else:
                domains.add(key[2:])
    return names, domains


def build_exclusion_sets() -> dict:
    locked = _companies_from_locked_lists()
    excluded_names = {normalize_name(c.get("company_name", "")) for c in locked}
    excluded_domains = {domain(c.get("website_url", "")) for c in locked if c.get("website_url")}
    excluded_places = {c.get("place_id") for c in locked if c.get("place_id")}
    manual_names, manual_domains = _load_manually_excluded()
    skip_names, skip_domains = _load_definitive_skip_sets()
    confirmed_names, confirmed_domains = _load_confirmed_sent_sets()
    permanent_rows = _load_permanent_skip_rows_cached()
    return {
        "locked_names": excluded_names - {""},
        "locked_domains": excluded_domains - {""},
        "locked_places": excluded_places - {None, ""},
        "manual_names": manual_names,
        "manual_domains": manual_domains,
        "skip_names": skip_names,
        "skip_domains": skip_domains,
        "confirmed_names": confirmed_names,
        "confirmed_domains": confirmed_domains,
        "permanent_rows": permanent_rows,
    }


def _load_permanent_skip_rows_cached() -> list[dict]:
    from config import LOG_PERMANENT_SKIP
    if not LOG_PERMANENT_SKIP.exists():
        return []
    import csv as csvm
    with LOG_PERMANENT_SKIP.open(encoding="utf-8") as f:
        return list(csvm.DictReader(f))


def _is_permanently_skipped_fast(company: dict, rows: list[dict]) -> tuple[bool, str]:
    from exclude_places import is_excluded_place

    excluded, reason = is_excluded_place(company)
    if excluded:
        return True, reason
    name = (company.get("company_name") or "").strip()
    url = (company.get("website_url") or "").strip()
    place_id = (company.get("place_id") or "").strip()
    nu = url.rstrip("/").lower()
    for row in rows:
        reason = row.get("reason", "timeout_repeated")
        row_name = (row.get("company_name") or "").strip()
        row_url = (row.get("website_url") or "").strip().rstrip("/").lower()
        if row_name and name and (name == row_name or name in row_name or row_name in name):
            return True, reason
        if nu and row_url and (nu == row_url or nu in row_url or row_url in nu):
            return True, reason
        if place_id and place_id == (row.get("place_id") or "").strip():
            return True, reason
    return False, ""


def load_full_candidate_pool() -> list[dict]:
    pool: list[dict] = []
    for md_file in sorted(LIST_ROOT.rglob("*.md")):
        if "別チャネル" in md_file.parts:
            continue
        if md_file.name.startswith("ARI-"):
            continue
        try:
            pool.extend(parse_md_file(str(md_file)))
        except (ValueError, FileNotFoundError):
            continue
    return pool


def exclusion_reason(company: dict, ex: dict) -> str | None:
    name = (company.get("company_name") or "").strip()
    url = (company.get("website_url") or "").strip()
    norm = normalize_name(name)
    dom = domain(url)
    pid = (company.get("place_id") or "").strip()

    if not name or not url:
        return "missing_name_or_url"
    if norm in ex["locked_names"] or (dom and dom in ex["locked_domains"]):
        return "locked_batch_1_55"
    if pid and pid in ex["locked_places"]:
        return "locked_place_id"
    if norm in ex["manual_names"] or (dom and dom in ex["manual_domains"]):
        return "manually_excluded"
    if norm in ex["skip_names"] or (dom and dom in ex["skip_domains"]):
        return "definitive_skip_classification"
    if any(ns in name or name in ns for ns in NOT_SUITABLE_NAMES):
        return "not_suitable_name"
    if norm in ex.get("confirmed_names", set()) or (dom and dom in ex.get("confirmed_domains", set())):
        return "confirmed_sent"
    skipped, reason = _is_permanently_skipped_fast(company, ex.get("permanent_rows") or [])
    if skipped:
        return f"permanent_skip:{reason}"
    if get_config_exclusion_label(company):
        return get_config_exclusion_label(company)
    hit = classify_skip(company)
    if hit:
        return hit[0]
    return None
