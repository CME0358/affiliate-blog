"""
night_factory.py — Overnight READY inventory manufacturing (ZERO SEND).

Coordinated pipeline: SOURCE → LW → PF → RF → READY inventory.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from copy import deepcopy
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from ari_pipeline.business_inquiry_surface import assess_business_inquiry_surface
from ari_pipeline.candidate_pool import _candidate_id
from ari_pipeline.orchestrator import Stage, load_checkpoint
from ari_pipeline.production_queue_eligibility import assess_production_queue_eligibility
from ari_pipeline.proven_pattern_library import classify_candidate, load_pattern_library
from ari_pipeline.queue_evidence_contract import (
    build_queue_authorization,
    terminal_consumer_eligible_offline,
)
from ari_pipeline.r2_industry_filter import (
    classify_r2_industry,
    industry_name_excluded_by_keywords,
    is_remodel_industry,
)
from ari_pipeline.high_yield_source_scoring import (
    READY_PRIORITY_A,
    READY_PRIORITY_B,
    SLOW_PATH,
    annotate_source_pool,
    sort_by_ready_priority,
    tier_counts,
)
from ari_pipeline.r2_lane_c_filter import infer_contact_url, lane_c_url_pattern_score
from ari_pipeline.sent_domain_index import get_sent_domain_index, normalize_domain
from ari_pipeline.status_integrity import count_official_confirmed_sent
from config import INPUT_DIR, LOG_DIR, VAULT_ROOT
from parser import parse_md_list
from semantic_policy import current_semantic_policy_provenance
from shared_form_prepare import is_evidence_schema_and_hash_compatible

FACTORY_DATE = os.environ.get("ARI_NIGHT_FACTORY_DATE", "2026-08-14")
RUN_ID = f"night_factory_{FACTORY_DATE.replace('-', '')}"
OUTPUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"

READY_JSON = OUTPUT_DIR / f"ARI-Night-Factory-READY-{FACTORY_DATE}.json"
STATE_JSON = OUTPUT_DIR / f"ARI-Night-Factory-State-{FACTORY_DATE}.json"
MORNING_INVENTORY_JSON = OUTPUT_DIR / f"ARI-Production-Ready-Inventory-{FACTORY_DATE}.json"
CHECKPOINT_JSON = LOG_DIR / f"ari_checkpoints/{RUN_ID}.json"
PID_FILE = LOG_DIR / "ari_night_factory.pid"
LOG_FILE = LOG_DIR / f"ari_night_factory_{FACTORY_DATE}.log"

# Reuse paths from prior lanes
LANE_CHECKPOINTS = (
    ("lane_a", "r2_lw_2026-08-13"),
    ("lane_b", "r2_lane_b_lw_2026-08-13"),
    ("lane_c", "r2_lane_c_lw_2026-08-13"),
)
SUPPLY_CP = LOG_DIR / "ari_checkpoints/r2_supply_2026-08-13.json"

REFRESH_ARTIFACTS = (
    OUTPUT_DIR / "ARI-Fast-Queue-Semantic-Refresh-2026-08-13.json",
    OUTPUT_DIR / "ARI-Semantic-Policy-Refresh-2026-08-13.json",
    OUTPUT_DIR / "ARI-AUTO-READY-Semantic-Refresh-2026-08-12.json",
)

PREFLIGHT_ARTIFACTS = (
    LOG_DIR / "ari_checkpoints/full_preflight_2026-08-12.json",
    OUTPUT_DIR / "ARI-Full-Preflight-2026-08-12.json",
    OUTPUT_DIR / "ARI-R2-Full-Preflight-2026-08-13.json",
    SUPPLY_CP,
)

CONSUMED_RESULTS = (
    OUTPUT_DIR / "ARI-Fast-Production-Results-2026-08-13-R1-fixed.json",
    OUTPUT_DIR / "ARI-Fast-Production-Results-2026-08-13.json",
)

PERMANENT_LW_OUTCOMES = frozenset({
    "CAPTCHA_MANUAL", "FORM_NOT_SUITABLE", "OTHER_SKIPPED",
})

DEFAULT_CONFIG = {
    "target_ready": 500,
    "buffer": 50,
    "lw_batch_size": 50,
    "pipeline_chunk_size": 200,
    "pf_batch_size": 12,
    "rf_batch_size": 12,
    "fast_http_workers": 12,
    "lw_workers": 2,
    "pf_workers": 2,
    "rf_workers": 2,
    "checkpoint_interval_sec": 300,
    "summary_interval_sec": 900,
}

CHECKPOINT_SCHEMA_VERSION = 2
SOURCE_POOL_JSON = OUTPUT_DIR / f"ARI-Night-Factory-Source-Pool-{FACTORY_DATE}.json"


class DomainStage(str, Enum):
    SOURCE_ONLY = "SOURCE_ONLY"
    LIGHTWEIGHT_COMPLETE = "LIGHTWEIGHT_COMPLETE"
    PREFLIGHT_CANDIDATE = "PREFLIGHT_CANDIDATE"
    PREFLIGHT_COMPLETE = "PREFLIGHT_COMPLETE"
    SEMANTIC_REFRESH_REQUIRED = "SEMANTIC_REFRESH_REQUIRED"
    CURRENT_POLICY_READY = "CURRENT_POLICY_READY"
    PERMANENT_EXCLUSION = "PERMANENT_EXCLUSION"


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_factory_state() -> dict[str, Any]:
    if STATE_JSON.exists():
        return json.loads(STATE_JSON.read_text(encoding="utf-8"))
    return {
        "factory_date": FACTORY_DATE,
        "run_id": RUN_ID,
        "started_at": None,
        "config": dict(DEFAULT_CONFIG),
        "stats": {
            "source_eligible": 0,
            "lw_processed": 0,
            "pf_processed": 0,
            "rf_processed": 0,
            "ready_primary": 0,
            "ready_remodel_reserve": 0,
            "ready_total": 0,
            "ready_added_last_hour": [],
        },
        "priority_weights": {},
        "last_summary_at": None,
        "last_error": None,
        "hard_stop": None,
    }


def save_factory_state(state: dict[str, Any]) -> None:
    state["updated_at"] = datetime.now().isoformat()
    _atomic_write(STATE_JSON, state)


def load_ready_inventory() -> dict[str, Any]:
    if READY_JSON.exists():
        return json.loads(READY_JSON.read_text(encoding="utf-8"))
    return {
        "factory_date": FACTORY_DATE,
        "generated_at": datetime.now().isoformat(),
        "policy_fingerprint": current_semantic_policy_provenance().get("semantic_policy_fingerprint"),
        "ready_primary": [],
        "ready_remodel_reserve": [],
        "domains_primary": [],
        "domains_remodel": [],
        "stats": {"ready_primary": 0, "ready_remodel_reserve": 0, "ready_total": 0},
    }


def save_ready_inventory(inv: dict[str, Any]) -> None:
    inv["updated_at"] = datetime.now().isoformat()
    inv["stats"] = {
        "ready_primary": len(inv.get("ready_primary") or []),
        "ready_remodel_reserve": len(inv.get("ready_remodel_reserve") or []),
        "ready_total": len(inv.get("ready_primary") or []) + len(inv.get("ready_remodel_reserve") or []),
    }
    _atomic_write(READY_JSON, inv)


def load_factory_checkpoint() -> dict[str, Any]:
    if CHECKPOINT_JSON.exists():
        cp = json.loads(CHECKPOINT_JSON.read_text(encoding="utf-8"))
        cp.setdefault("preflight_results", {})
        cp.setdefault("refresh_results", {})
        cp.setdefault("domain_stages", {})
        cp.setdefault("exclusions", {})
        return migrate_checkpoint(cp)
    return migrate_checkpoint({
        "run_id": RUN_ID,
        "factory_date": FACTORY_DATE,
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "preflight_results": {},
        "refresh_results": {},
        "domain_stages": {},
        "exclusions": {},
        "source_initialized": False,
        "source_population_identity": "",
        "source_eligible_count": 0,
        "source_cursor": 0,
        "processed_domain_identities": [],
        "ready_domain_identities": {"primary": [], "remodel": []},
    })


def migrate_checkpoint(cp: dict[str, Any]) -> dict[str, Any]:
    """Upgrade legacy checkpoints; never treat missing source fields as exhausted inventory."""
    cp.setdefault("schema_version", 1)
    cp.setdefault("source_initialized", bool(cp.get("source_pool_built")))
    cp.setdefault("source_population_identity", "")
    cp.setdefault("source_eligible_count", 0)
    cp.setdefault("source_cursor", 0)
    cp.setdefault("processed_domain_identities", [])
    cp.setdefault("ready_domain_identities", {"primary": [], "remodel": []})
    cp.setdefault("semantic_policy_fingerprint", "")
    cp.setdefault("target", DEFAULT_CONFIG["target_ready"])
    cp.setdefault("buffer", DEFAULT_CONFIG["buffer"])
    cp.setdefault("stop_target", stop_target(DEFAULT_CONFIG))

    if cp["schema_version"] < CHECKPOINT_SCHEMA_VERSION:
        # v1 had PF/RF evidence but no source metadata — force rebuild on next init
        if cp.get("source_eligible_count", 0) == 0 and not cp.get("source_initialized"):
            cp["source_initialized"] = False
        cp["schema_version"] = CHECKPOINT_SCHEMA_VERSION
    return cp


def source_population_identity() -> str:
    import hashlib

    md_path = Path(INPUT_DIR)
    mtime = int(md_path.stat().st_mtime) if md_path.exists() else 0
    confirmed = count_official_confirmed_sent()
    attempted = len(load_attempted_domains())
    raw = f"{FACTORY_DATE}:{mtime}:{confirmed}:{attempted}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def initialize_source_inventory(
    state: dict[str, Any],
    cp: dict[str, Any],
    *,
    force_rebuild: bool = False,
) -> tuple[list[dict], dict[str, dict], dict[str, Any]]:
    """
    Build or rebuild eligible source pool from canonical local data.
    Preserves PF/RF/READY evidence; persists source metadata to checkpoint + state.
    """
    identity = source_population_identity()
    prov = current_semantic_policy_provenance()
    fp = prov.get("semantic_policy_fingerprint", "")
    config = state.get("config") or DEFAULT_CONFIG
    inv = load_ready_inventory()

    needs_rebuild = (
        force_rebuild
        or not cp.get("source_initialized")
        or cp.get("source_eligible_count", 0) == 0
        or cp.get("source_population_identity") != identity
        or cp.get("schema_version", 0) < CHECKPOINT_SCHEMA_VERSION
    )

    source = build_source_pool()
    pool_by_dom = {c["domain"]: c for c in source}

    cp["schema_version"] = CHECKPOINT_SCHEMA_VERSION
    cp["source_initialized"] = True
    cp["source_population_identity"] = identity
    cp["source_eligible_count"] = len(source)
    cp["semantic_policy_fingerprint"] = fp
    cp["target"] = int(config.get("target_ready", 500))
    cp["buffer"] = int(config.get("buffer", 50))
    cp["stop_target"] = stop_target(config)
    cp["ready_domain_identities"] = {
        "primary": list(inv.get("domains_primary") or []),
        "remodel": list(inv.get("domains_remodel") or []),
    }
    cp["source_rebuilt_at"] = datetime.now().isoformat()
    if needs_rebuild:
        cp["source_cursor"] = int(cp.get("source_cursor") or 0)

    state.setdefault("stats", {})
    state["stats"]["source_eligible"] = len(source)
    state["source_initialized"] = True
    state["source_population_identity"] = identity
    save_factory_state(state)
    save_factory_checkpoint(cp)

    # Lightweight sidecar for resume/debug (domain list only, not full PF evidence)
    _atomic_write(SOURCE_POOL_JSON, {
        "factory_date": FACTORY_DATE,
        "source_population_identity": identity,
        "source_eligible_count": len(source),
        "domains": [c["domain"] for c in source[:500]],  # sample head for audit
        "note": "Full pool rebuilt from canonical INPUT on each init; see source_eligible_count",
    })

    return source, pool_by_dom, cp


def effective_source_eligible(state: dict[str, Any], cp: dict[str, Any]) -> int:
    """Best available source_eligible for status (state → checkpoint → rebuild probe)."""
    n = int(state.get("stats", {}).get("source_eligible") or 0)
    if n > 0:
        return n
    n = int(cp.get("source_eligible_count") or 0)
    if n > 0:
        return n
    if state.get("source_initialized") or cp.get("source_initialized"):
        return int(cp.get("source_eligible_count") or 0)
    return 0


def save_factory_checkpoint(cp: dict[str, Any]) -> None:
    cp["updated_at"] = datetime.now().isoformat()
    _atomic_write(CHECKPOINT_JSON, cp)


def load_attempted_domains() -> set[str]:
    attempted: set[str] = set()
    paths = list(CONSUMED_RESULTS)
    if OUTPUT_DIR.exists():
        paths.extend(sorted(OUTPUT_DIR.glob("ARI-Fast-Production-Results-*.json")))
    seen_files: set[Path] = set()
    for path in paths:
        if path in seen_files or not path.exists():
            continue
        seen_files.add(path)
        try:
            rows = json.loads(path.read_text()).get("results") or []
        except (json.JSONDecodeError, OSError):
            continue
        for r in rows:
            if r.get("attempted") or r.get("final_submit_attempted") or r.get("final_submit_clicked"):
                dom = r.get("domain")
                if dom:
                    attempted.add(dom.lower())
    return attempted


def refresh_production_exclusions(inv: dict | None = None, cp: dict | None = None) -> dict[str, Any]:
    """
    Mark newly sent/attempted domains ineligible for future READY without deleting evidence.
    """
    from ari_pipeline.sent_domain_index import get_sent_domain_index

    get_sent_domain_index.cache_clear()
    idx = get_sent_domain_index()
    attempted = load_attempted_domains()
    consumed = set(idx.confirmed_domains) | attempted
    inv = inv if inv is not None else load_ready_inventory()
    marked = 0
    for bucket in ("ready_primary", "ready_remodel_reserve"):
        for rec in inv.get(bucket) or []:
            dom = (rec.get("domain") or "").lower()
            if not dom or rec.get("consumed_by_production"):
                continue
            if idx.is_confirmed_sent_domain(dom) or idx.should_no_resend(dom) or dom in attempted:
                rec["consumed_by_production"] = True
                rec["inventory_eligibility"] = "excluded_after_production"
                rec["consumed_at"] = datetime.now().isoformat()
                marked += 1
    if marked:
        save_ready_inventory(inv)
    if cp is not None:
        exclusions = cp.setdefault("exclusions", {})
        for dom in consumed:
            exclusions.setdefault(dom, "PRODUCTION_CONSUMED")
    return {
        "marked": marked,
        "attempted": len(attempted),
        "confirmed": len(idx.confirmed_domains),
        "effective_confirmed_sent": idx.effective_confirmed_sent,
    }


def priority_score(row: dict) -> int:
    url = row.get("website_url") or ""
    score = lane_c_url_pattern_score(url)
    industry = row.get("industry_name") or ""
    if is_remodel_industry(industry):
        score -= 50
    elif classify_r2_industry(industry):
        score -= 30
    tier = row.get("industry_tier")
    if tier == 1:
        score += 40
    elif tier == 2:
        score += 20
    score += min(int(row.get("review_count") or 0) // 50, 10)
    return score


def _industry_tier(industry: str, name: str = "") -> int:
    blob = f"{industry} {name}"
    t1 = ("不動産", "引越", "人材派遣", "派遣", "staffing", "moving")
    t2 = ("清掃", "物流", "税理", "司法書士", "行政書士", "コンサル", "警備")
    if any(k in blob for k in t1):
        return 1
    if any(k in blob for k in t2):
        return 2
    return 3


def build_source_pool() -> list[dict]:
    get_sent_domain_index.cache_clear()
    idx = get_sent_domain_index()
    attempted = load_attempted_domains()
    companies = parse_md_list(str(INPUT_DIR))
    seen: set[str] = set()
    pool: list[dict] = []

    for c in companies:
        dom = normalize_domain(c.get("website_url", ""))
        if not dom or dom in seen:
            continue
        seen.add(dom)
        industry = c.get("industry_name", "")
        name = c.get("company_name", "")

        if idx.is_confirmed_sent_domain(dom) or idx.should_no_resend(dom) or dom in attempted:
            continue
        if industry_name_excluded_by_keywords(industry, name):
            continue

        url_score = lane_c_url_pattern_score(c.get("website_url", ""))
        if url_score < -100:
            continue

        lw_url = c.get("website_url") if url_score >= 70 else infer_contact_url(c.get("website_url", ""))
        pool.append({
            "candidate_id": _candidate_id(c),
            "company_name": name,
            "domain": dom,
            "website_url": c.get("website_url", ""),
            "lw_entry_url": lw_url,
            "industry_name": industry,
            "area_name": c.get("area_name", ""),
            "place_id": c.get("place_id", ""),
            "rating": c.get("rating"),
            "review_count": c.get("review_count"),
            "industry_tier": _industry_tier(industry, name),
            "is_remodel": is_remodel_industry(industry),
            "url_pattern_score": url_score,
            "pool_date": FACTORY_DATE,
        })

    pool.sort(key=lambda r: (-priority_score(r), r.get("industry_tier", 99), r.get("company_name", "")))
    pool = annotate_source_pool(pool)
    pool = sort_by_ready_priority(pool)
    return pool


def ingest_existing_evidence(cp: dict, pool_by_dom: dict[str, dict]) -> dict[str, Any]:
    """Merge Lane A/B/C + artifacts into domain_stages and pf/rf maps."""
    stats = Counter()
    domain_stages: dict[str, str] = dict(cp.get("domain_stages") or {})
    pf: dict[str, dict] = dict(cp.get("preflight_results") or {})
    rf: dict[str, dict] = dict(cp.get("refresh_results") or {})

    for lane, run_id in LANE_CHECKPOINTS:
        st = load_checkpoint(run_id) or {}
        for c in st.get("candidates") or []:
            dom = (c.get("domain") or "").lower()
            if not dom:
                continue
            out = c.get("lightweight_outcome") or ""
            if c.get("status") == "completed":
                if out == "PREFLIGHT_CANDIDATE":
                    domain_stages[dom] = DomainStage.PREFLIGHT_CANDIDATE.value
                elif out in PERMANENT_LW_OUTCOMES or out in ("UNREACHABLE_ERROR", "NO_FORM_FOUND"):
                    domain_stages[dom] = DomainStage.PERMANENT_EXCLUSION.value
                    cp.setdefault("exclusions", {})[dom] = out
                else:
                    domain_stages[dom] = DomainStage.LIGHTWEIGHT_COMPLETE.value
                stats[f"lane_{lane}_lw"] += 1

    if SUPPLY_CP.exists():
        sc = json.loads(SUPPLY_CP.read_text())
        for dom, row in (sc.get("preflight_results") or {}).items():
            pf[dom] = row
            domain_stages[dom.lower()] = DomainStage.PREFLIGHT_COMPLETE.value
        for dom, row in (sc.get("refresh_results") or {}).items():
            rf[dom] = row
            if row.get("refresh_outcome") == "REFRESH_READY":
                domain_stages[dom.lower()] = DomainStage.SEMANTIC_REFRESH_REQUIRED.value

    prov = current_semantic_policy_provenance()
    fp = prov.get("semantic_policy_fingerprint", "")
    for path in REFRESH_ARTIFACTS:
        if not path.exists():
            continue
        for r in json.loads(path.read_text()).get("results") or []:
            dom = (r.get("domain") or "").lower()
            if not dom or r.get("refresh_outcome") != "REFRESH_READY":
                continue
            sem = r.get("semantic_evidence_v2") or {}
            ok, _ = is_evidence_schema_and_hash_compatible(sem)
            if not ok:
                continue
            if sem.get("semantic_policy_fingerprint") and fp and sem["semantic_policy_fingerprint"] != fp:
                continue
            rf[dom] = r
            domain_stages[dom] = DomainStage.SEMANTIC_REFRESH_REQUIRED.value
            stats["artifact_refresh"] += 1

    for path in PREFLIGHT_ARTIFACTS:
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        rows = data.get("preflight_results") or data.get("results") or data.get("records") or []
        if isinstance(rows, dict):
            rows = list(rows.values())
        for r in rows:
            if not isinstance(r, dict):
                continue
            dom = (r.get("domain") or "").lower()
            if dom:
                pf.setdefault(dom, r)

    cp["preflight_results"] = pf
    cp["refresh_results"] = rf
    cp["domain_stages"] = domain_stages
    return {"ingested": dict(stats), "pf_total": len(pf), "rf_total": len(rf)}


def _purpose_compatible(rr: dict | None) -> bool:
    return (rr or {}).get("purpose_audit", "COMPATIBLE") in ("COMPATIBLE", "NOT_APPLICABLE", "")


def evaluate_ready(
    dom: str,
    src: dict,
    pf: dict,
    rf: dict,
    *,
    excluded: set[str],
    attempted: set[str],
) -> tuple[bool, str, dict | None, str]:
    """Returns (is_ready, bucket primary|remodel|none, record, reason)."""
    if dom in excluded or dom in attempted:
        return False, "none", None, "excluded"
    rr = rf.get(dom)
    if not rr or rr.get("refresh_outcome") != "REFRESH_READY":
        return False, "none", None, "not_refresh_ready"
    if not _purpose_compatible(rr):
        return False, "none", None, "purpose_incompatible"

    pf_row = pf.get(dom, {})
    fn = pf_row.get("fill_no_submit") or {}
    if fn.get("captcha_detected"):
        return False, "none", None, "captcha"

    surface_ok, sr = assess_business_inquiry_surface(
        form_url=pf_row.get("form_url") or src.get("website_url", ""),
        form_heading=fn.get("form_heading") or "",
    )
    if not surface_ok and not src.get("is_remodel"):
        return False, "none", None, f"surface_{sr}"

    get_sent_domain_index.cache_clear()
    idx = get_sent_domain_index()
    library = load_pattern_library()
    merged = {**pf_row, **src}
    eligible, reason, detail = assess_production_queue_eligibility(
        merged, refresh_row=rr, sent_index=idx, library=library, excluded_domains=frozenset(excluded | attempted),
    )
    if not eligible:
        return False, "none", None, reason

    bucket = "remodel" if src.get("is_remodel") else "primary"
    auth = build_queue_authorization(
        {"queue_revision": "NIGHT-FACTORY", "candidate_id": src.get("candidate_id"), "domain": dom, "production_eligibility": "production_ready"},
        rr,
    )
    snap = (rr.get("semantic_evidence_v2") or {}).get("canonical_snapshot") or {}
    purpose_label = ""
    for ch in snap.get("choices_applied") or []:
        if ch.get("category") in ("INQUIRY_CATEGORY", "UNKNOWN", None):
            purpose_label = ch.get("label") or ch.get("value") or ""
            break

    rec = {
        "candidate_id": src.get("candidate_id"),
        "company_name": src.get("company_name") or pf_row.get("company_name", ""),
        "domain": dom,
        "website_url": src.get("website_url") or pf_row.get("website_url", ""),
        "form_url": pf_row.get("form_url") or "",
        "industry_name": src.get("industry_name") or "",
        "area_name": src.get("area_name") or "",
        "place_id": src.get("place_id") or "",
        "supply_lane": "NIGHT_FACTORY",
        "inventory_bucket": bucket,
        "classification": "PROVEN_FAST_PATH",
        "matched_pattern_id": detail.get("matched_pattern_id"),
        "pattern_tier": detail.get("pattern_tier"),
        "refresh_outcome": rr.get("refresh_outcome"),
        "inquiry_purpose_audit": rr.get("purpose_audit") or "COMPATIBLE",
        "selected_inquiry_purpose": purpose_label,
        "semantic_hash": auth.get("authorized_semantic_hash"),
        "production_eligibility": "production_ready",
        "queue_authorization": auth,
        "evidence_source": rr.get("_source", "night_factory"),
    }

    ok_term, term_reason = terminal_consumer_eligible_offline(
        rec, refresh_row=rr, preflight_row=pf_row,
        classify_fn=classify_candidate, excluded_domains=excluded | attempted, library=library,
    )
    if not ok_term:
        return False, "none", None, term_reason

    return True, bucket, rec, ""


def recalculate_ready_inventory(
    pool_by_dom: dict[str, dict],
    cp: dict,
    inv: dict | None = None,
) -> dict[str, Any]:
    inv = inv or load_ready_inventory()
    excluded = set((inv.get("domains_primary") or []) + (inv.get("domains_remodel") or []))
    attempted = load_attempted_domains()
    pf = cp.get("preflight_results") or {}
    rf = cp.get("refresh_results") or {}

    primary: list[dict] = list(inv.get("ready_primary") or [])
    remodel: list[dict] = list(inv.get("ready_remodel_reserve") or [])
    primary_doms = {r["domain"] for r in primary}
    remodel_doms = {r["domain"] for r in remodel}

    for dom, src in pool_by_dom.items():
        if dom in primary_doms or dom in remodel_doms:
            continue
        ok, bucket, rec, _ = evaluate_ready(dom, src, pf, rf, excluded=excluded, attempted=attempted)
        if not ok or not rec:
            continue
        if bucket == "remodel":
            remodel.append(rec)
            remodel_doms.add(dom)
        else:
            primary.append(rec)
            primary_doms.add(dom)

    inv["ready_primary"] = primary
    inv["ready_remodel_reserve"] = remodel
    inv["domains_primary"] = sorted(primary_doms)
    inv["domains_remodel"] = sorted(remodel_doms)
    save_ready_inventory(inv)
    return inv


def build_morning_inventory(inv: dict, *, target: int, cp: dict | None = None) -> dict[str, Any]:
    """Atomic update production-ready inventory segments (ZERO SEND)."""
    from semantic_policy import current_semantic_policy_provenance

    primary = list(inv.get("ready_primary") or [])
    remodel = list(inv.get("ready_remodel_reserve") or [])
    prov = current_semantic_policy_provenance()

    def _seg(start: int, size: int) -> list[dict]:
        chunk = primary[start:start + size]
        out = []
        for rec in chunk:
            out.append({
                "domain": rec.get("domain"),
                "company": rec.get("company_name"),
                "form_url": rec.get("form_url"),
                "source_lineage": rec.get("supply_lane") or rec.get("evidence_source") or "NIGHT_FACTORY",
                "semantic_hash": rec.get("semantic_hash"),
                "policy_fingerprint": prov.get("semantic_policy_fingerprint"),
                "inquiry_purpose_result": rec.get("inquiry_purpose_audit"),
                "selected_inquiry_purpose": rec.get("selected_inquiry_purpose"),
                "submit_target": (rec.get("queue_authorization") or {}).get("authorized_submit_target"),
                "ready_classification": rec.get("classification"),
                "matched_pattern_id": rec.get("matched_pattern_id"),
                "inventory_bucket": rec.get("inventory_bucket"),
            })
        return out

    segments = {
        "P01": _seg(0, 100),
        "P02": _seg(100, 100),
        "P03": _seg(200, 100),
        "P04": _seg(300, 100),
        "P05": _seg(400, 100),
    }
    payload = {
        "generated_at": datetime.now().isoformat(),
        "factory_date": FACTORY_DATE,
        "target_ready": target,
        "policy_fingerprint": prov.get("semantic_policy_fingerprint"),
        "ready_primary_count": len(primary),
        "ready_remodel_count": len(remodel),
        "ready_total": len(primary) + len(remodel),
        "segments": {
            k: {"count": len(v), "candidates": v, "domains": [c["domain"] for c in v if c.get("domain")]}
            for k, v in segments.items()
        },
        "ready_remodel_reserve": [r.get("domain") for r in remodel],
        "note": "Production-ready inventory — ZERO SEND / no FINAL_SUBMIT",
    }
    if cp:
        payload["checkpoint_stats"] = {
            "pf_processed": len(cp.get("preflight_results") or {}),
            "rf_processed": len(cp.get("refresh_results") or {}),
            "fast_http_processed": len(cp.get("fast_http_results") or {}),
        }
    _atomic_write(MORNING_INVENTORY_JSON, payload)
    return payload


def stop_target(config: dict) -> int:
    return int(config.get("target_ready", 500)) + int(config.get("buffer", 50))
