"""
r2_streaming_queue.py — Immutable micro-batch queue sealing for R2 streaming supply.

Seals R2-A, R2-B, … (20–30 production-ready candidates) without waiting for full pool.
ZERO SEND — preparation only.
"""

from __future__ import annotations

import json
import string
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from ari_pipeline.daily_fast_runner import daily_queue_path, init_daily_state, write_daily_state
from ari_pipeline.production_queue_eligibility import assess_production_queue_eligibility
from ari_pipeline.proven_pattern_library import classify_candidate, load_pattern_library
from ari_pipeline.queue_evidence_contract import (
    build_queue_authorization,
    terminal_consumer_eligible_offline,
)
from ari_pipeline.sent_domain_index import get_sent_domain_index
from ari_pipeline.status_integrity import count_official_confirmed_sent
from config import LOG_DIR, VAULT_ROOT

QUEUE_DATE = "2026-08-13"
STREAMING_STATE_PATH = LOG_DIR / "ari_checkpoints/r2_streaming_2026-08-13.json"
SUPPLY_CHECKPOINT = LOG_DIR / "ari_checkpoints/r2_supply_2026-08-13.json"
POOL_JSON = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-R2-Candidate-Pool-2026-08-13.json"
LANE_B_POOL = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-R2-LaneB-Pool-2026-08-13.json"
LANE_C_POOL = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint/ARI-R2-LaneC-Pool-2026-08-13.json"
LW_RUN_ID = "r2_lw_2026-08-13"
LANE_C_LW_RUN_ID = "r2_lane_c_lw_2026-08-13"
LANE_B_LW_RUN_ID = "r2_lane_b_lw_2026-08-13"


def _merged_pool_candidates(cp: dict) -> list[dict]:
    pool = cp.get("pool") or {}
    cands = list(pool.get("candidates") or [])
    if not cands and POOL_JSON.exists():
        cands = json.loads(POOL_JSON.read_text(encoding="utf-8")).get("candidates") or []
    if LANE_B_POOL.exists():
        lb = json.loads(LANE_B_POOL.read_text(encoding="utf-8"))
        cands = cands + (lb.get("candidates") or [])
    if LANE_C_POOL.exists():
        lc = json.loads(LANE_C_POOL.read_text(encoding="utf-8"))
        cands = cands + (lc.get("candidates") or [])
    return cands

MICRO_BATCH_PREFERRED = 25
MICRO_BATCH_MIN = 20
MICRO_BATCH_MAX = 30
MICRO_BATCH_DEADLINE_MIN = 10
R2_YIELD_ATTEMPT = 35 / 42

R1_FIXED_ATTEMPTS = 35
DAILY_TARGET_ATTEMPTS = 300
REMAINING_ATTEMPTS_BASELINE = DAILY_TARGET_ATTEMPTS - R1_FIXED_ATTEMPTS

YIELD_CHECKPOINTS = (100, 200, 500)


def _next_revision_letter(sealed: list[str]) -> str:
    used = {r for r in sealed if r.startswith("R2-")}
    for ch in string.ascii_uppercase:
        rev = f"R2-{ch}"
        if rev not in used:
            return rev
    raise RuntimeError("R2 revision letters exhausted")


def load_streaming_state() -> dict[str, Any]:
    if STREAMING_STATE_PATH.exists():
        return json.loads(STREAMING_STATE_PATH.read_text(encoding="utf-8"))
    return {
        "queue_date": QUEUE_DATE,
        "sealed_revisions": [],
        "sealed_domains": [],
        "sealed_candidate_ids": [],
        "yield_checkpoints": {},
        "attempt_accounting": {
            "r1_fixed_attempts": R1_FIXED_ATTEMPTS,
            "daily_target": DAILY_TARGET_ATTEMPTS,
            "remaining_after_r1": REMAINING_ATTEMPTS_BASELINE,
            "r2_estimated_attempts": 0,
        },
        "lane_a_ready_total": 0,
        "lane_b_ready_total": 0,
    }


def save_streaming_state(state: dict[str, Any]) -> None:
    STREAMING_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now().isoformat()
    STREAMING_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_supply_checkpoint() -> dict[str, Any]:
    if SUPPLY_CHECKPOINT.exists():
        return json.loads(SUPPLY_CHECKPOINT.read_text(encoding="utf-8"))
    return {"preflight_results": {}, "refresh_results": {}, "pool": None}


def save_supply_checkpoint(cp: dict[str, Any]) -> None:
    SUPPLY_CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    cp["updated_at"] = datetime.now().isoformat()
    SUPPLY_CHECKPOINT.write_text(json.dumps(cp, ensure_ascii=False, indent=2), encoding="utf-8")


def _purpose_compatible(rr: dict | None) -> bool:
    if not rr:
        return False
    return (rr.get("purpose_audit") or "") in ("COMPATIBLE", "NOT_APPLICABLE", "")


def collect_production_ready(
    pool_candidates: list[dict],
    preflight_by: dict[str, dict],
    refresh_results: list[dict],
    *,
    exclude_domains: set[str],
    lane: str = "A",
) -> tuple[list[dict], list[dict]]:
    get_sent_domain_index.cache_clear()
    idx = get_sent_domain_index()
    refresh_by = {r["domain"]: r for r in refresh_results if r.get("domain")}
    library = load_pattern_library()
    source_by = {c["domain"]: c for c in pool_candidates if c.get("domain")}

    ready: list[dict] = []
    rejected: list[dict] = []

    for dom, src in source_by.items():
        if dom in exclude_domains:
            continue
        pf = preflight_by.get(dom, {})
        rr = refresh_by.get(dom)
        if not rr or rr.get("refresh_outcome") != "REFRESH_READY":
            continue
        if not _purpose_compatible(rr):
            rejected.append({"domain": dom, "reason": f"purpose_{rr.get('purpose_audit')}", "lane": lane})
            continue

        merged = {**pf, **src}
        eligible, reason, detail = assess_production_queue_eligibility(
            merged, refresh_row=rr, sent_index=idx, library=library,
        )
        if not eligible:
            rejected.append({"domain": dom, "reason": reason, "detail": detail, "lane": lane})
            continue

        snap = (rr.get("semantic_evidence_v2") or {}).get("canonical_snapshot") or {}
        purpose_label = ""
        for ch in snap.get("choices_applied") or []:
            if ch.get("category") in ("INQUIRY_CATEGORY", "UNKNOWN", None):
                purpose_label = ch.get("label") or ch.get("value") or ""
                break

        ready.append({
            "candidate_id": src.get("candidate_id"),
            "company_name": src.get("company_name") or pf.get("company_name", ""),
            "domain": dom,
            "website_url": src.get("website_url") or pf.get("website_url", ""),
            "form_url": pf.get("form_url") or src.get("form_url", ""),
            "industry_name": src.get("industry_name") or pf.get("industry_name", ""),
            "area_name": src.get("area_name") or pf.get("area_name", ""),
            "place_id": src.get("place_id") or pf.get("place_id", ""),
            "r2_industry_bucket": src.get("r2_industry_bucket") or src.get("lane_b_bucket") or src.get("lane_c_bucket", ""),
            "supply_lane": lane,
            "classification": "PROVEN_FAST_PATH",
            "matched_pattern_id": detail.get("matched_pattern_id"),
            "pattern_tier": detail.get("pattern_tier"),
            "refresh_outcome": rr.get("refresh_outcome"),
            "inquiry_purpose_audit": rr.get("purpose_audit") or "",
            "selected_inquiry_purpose": purpose_label,
            "canonical_submit_target": snap.get("submit_target"),
            "_preflight_row": pf,
            "_refresh_row": rr,
        })

    return ready, rejected


def validate_producer_consumer_parity(
    queue_candidates: list[dict],
    preflight_by: dict[str, dict],
    refresh_by: dict[str, dict],
) -> dict[str, Any]:
    get_sent_domain_index.cache_clear()
    idx = get_sent_domain_index()
    excluded = set(idx.confirmed_domains)
    library = load_pattern_library()

    sample_size = max(5, int(len(queue_candidates) * 0.2 + 0.999))
    sample = queue_candidates[:sample_size]

    mismatches: list[dict] = []
    for rec in sample:
        dom = rec.get("domain", "")
        pf = preflight_by.get(dom) or rec.get("_preflight_row") or {}
        rr = refresh_by.get(dom) or rec.get("_refresh_row") or {}
        auth = rec.get("queue_authorization") or build_queue_authorization(
            {"queue_revision": rec.get("queue_revision", ""), "candidate_id": rec.get("candidate_id"),
             "domain": dom, "production_eligibility": "production_ready"},
            rr,
        )
        qrec = {**rec, "queue_authorization": auth, "production_eligibility": "production_ready"}

        ok_prod, prod_reason, _ = assess_production_queue_eligibility(
            {**pf, **qrec}, refresh_row=rr, sent_index=idx, library=library,
        )
        ok_term, term_reason = terminal_consumer_eligible_offline(
            qrec, refresh_row=rr, preflight_row=pf,
            classify_fn=classify_candidate, excluded_domains=excluded, library=library,
        )
        if not (ok_prod and ok_term):
            mismatches.append({
                "domain": dom,
                "producer_ok": ok_prod,
                "producer_reason": prod_reason,
                "terminal_ok": ok_term,
                "terminal_reason": term_reason,
            })

    purpose_ok = all(
        (c.get("inquiry_purpose_audit") or "") in ("COMPATIBLE", "NOT_APPLICABLE", "")
        for c in queue_candidates
    )
    return {
        "sample_size": len(sample),
        "queue_size": len(queue_candidates),
        "parity_pass": len(mismatches) == 0,
        "producer_terminal_ready_rate": 1.0 if not mismatches else (len(sample) - len(mismatches)) / max(len(sample), 1),
        "correct_purpose_rate": 1.0 if purpose_ok else 0.0,
        "mismatches": mismatches,
    }


def _finalize_sealed_records(batch: list[dict], revision: str) -> list[dict]:
    sealed: list[dict] = []
    for i, row in enumerate(batch, start=1):
        rr = row["_refresh_row"]
        rec = {k: v for k, v in row.items() if not k.startswith("_")}
        rec["queue_index"] = i
        rec["queue_date"] = QUEUE_DATE
        rec["queue_revision"] = revision
        rec["production_eligibility"] = "production_ready"
        auth = build_queue_authorization(
            {
                "queue_revision": revision,
                "candidate_id": rec.get("candidate_id"),
                "domain": rec.get("domain"),
                "production_eligibility": "production_ready",
            },
            rr,
        )
        rec["queue_authorization"] = auth
        rec["semantic_hash"] = auth.get("authorized_semantic_hash")
        sealed.append(rec)
    return sealed


def seal_micro_batch(
    ready_candidates: list[dict],
    *,
    revision: str,
    lane: str = "A",
    batch_size: int = MICRO_BATCH_PREFERRED,
    deadline_mode: bool = False,
) -> dict[str, Any] | None:
    min_size = MICRO_BATCH_DEADLINE_MIN if deadline_mode else MICRO_BATCH_MIN
    if len(ready_candidates) < min_size:
        return None

    if deadline_mode:
        take = min(MICRO_BATCH_MAX, len(ready_candidates))
    else:
        take = min(batch_size, MICRO_BATCH_MAX, len(ready_candidates))
        if len(ready_candidates) >= MICRO_BATCH_MIN:
            take = max(take, min(MICRO_BATCH_MIN, len(ready_candidates)))

    batch = ready_candidates[:take]
    pf_by = {r["domain"]: r["_preflight_row"] for r in batch}
    rf_by = {r["domain"]: r["_refresh_row"] for r in batch}

    sealed = _finalize_sealed_records(batch, revision)
    get_sent_domain_index.cache_clear()
    idx = get_sent_domain_index()

    dup = len(sealed) != len({c["domain"] for c in sealed})
    confirmed_contam = [c for c in sealed if idx.is_confirmed_sent_domain(c["domain"])]
    if dup or confirmed_contam:
        raise RuntimeError(f"Contamination blocked seal {revision}: dup={dup} confirmed={len(confirmed_contam)}")

    parity = validate_producer_consumer_parity(sealed, pf_by, rf_by)
    if not parity["parity_pass"]:
        raise RuntimeError(f"Producer/consumer parity failed for {revision}: {parity['mismatches'][:3]}")

    dental = sum(1 for c in sealed if c.get("r2_industry_bucket") == "dental")
    esthetic = sum(1 for c in sealed if c.get("r2_industry_bucket") == "esthetic")
    fallback = sum(1 for c in sealed if c.get("supply_lane") == "B")

    payload = {
        "generated_at": datetime.now().isoformat(),
        "queue_date": QUEUE_DATE,
        "queue_revision": revision,
        "immutable": True,
        "sealed": True,
        "supply_lane": lane,
        "source_pool": str(POOL_JSON),
        "target_attempts": DAILY_TARGET_ATTEMPTS,
        "pool_size": len(sealed),
        "proven_fast_path_count": len(sealed),
        "selection_policy": "R2_STREAMING_MICRO_BATCH",
        "industry_breakdown": {
            "dental": dental,
            "esthetic": esthetic,
            "fallback_lane_b": fallback,
        },
        "contamination": {
            "duplicate_domains": dup,
            "attempted_contamination": 0,
            "confirmed_sent_contamination": len(confirmed_contam),
        },
        "parity_validation": parity,
        "estimated_final_submit_attempts": int(len(sealed) * R2_YIELD_ATTEMPT),
        "candidates": sealed,
    }

    path = daily_queue_path(QUEUE_DATE, revision=revision)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"Immutable queue already exists: {path}")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    init_revision_terminal_state(revision, queue_path=path)
    return payload


def init_revision_terminal_state(revision: str, *, queue_path: Path) -> None:
    effective = count_official_confirmed_sent()
    write_daily_state({
        **init_daily_state(
            date=QUEUE_DATE,
            target_attempts=DAILY_TARGET_ATTEMPTS,
            queue_path=queue_path,
            effective_confirmed_baseline=effective,
        ),
        "queue_revision": revision,
        "status": "idle",
        "started_at": None,
        "streaming_micro_batch": True,
    }, revision=revision)


def terminal_command(revision: str) -> str:
    return (
        "export ARI_TERMINAL_PRODUCTION_CONFIRM=1\n"
        f"./run_ari_terminal_production.sh \\\n"
        f"  --daily-fast 300 \\\n"
        f"  --queue-date {QUEUE_DATE} \\\n"
        f"  --queue-revision {revision}"
    )


def compute_yield_metrics(lw_state: dict, cp: dict) -> dict[str, Any]:
    from collections import Counter

    cands = lw_state.get("candidates") or []
    done = [c for c in cands if c.get("status") == "completed"]
    outcomes = Counter(c.get("lightweight_outcome") for c in done)
    pf = cp.get("preflight_results") or {}
    rf = cp.get("refresh_results") or {}
    rf_list = list(rf.values()) if isinstance(rf, dict) else rf
    rf_out = Counter(r.get("refresh_outcome") for r in rf_list)

    n = len(done)
    reachable = 1.0 - (outcomes.get("UNREACHABLE_ERROR", 0) / max(n, 1))
    contact_form = outcomes.get("PREFLIGHT_CANDIDATE", 0) / max(n, 1)
    preflight_rate = len(pf) / max(outcomes.get("PREFLIGHT_CANDIDATE", 0), 1)
    refresh_ready_rate = rf_out.get("REFRESH_READY", 0) / max(len(rf_list), 1)

    return {
        "processed": n,
        "reachable_rate": round(reachable, 4),
        "contact_form_rate": round(contact_form, 4),
        "preflight_candidate_rate": round(contact_form, 4),
        "preflight_processed_rate": round(preflight_rate, 4),
        "refresh_ready_rate": round(refresh_ready_rate, 4),
        "lightweight_outcomes": dict(outcomes),
        "refresh_outcomes": dict(rf_out),
    }


def maybe_record_yield_checkpoint(streaming: dict, lw_state: dict, cp: dict) -> dict | None:
    metrics = compute_yield_metrics(lw_state, cp)
    n = metrics["processed"]
    recorded = streaming.setdefault("yield_checkpoints", {})
    for threshold in YIELD_CHECKPOINTS:
        if n >= threshold and str(threshold) not in recorded:
            recorded[str(threshold)] = {**metrics, "recorded_at": datetime.now().isoformat()}
            return metrics
    return None


def estimate_time_to_next_batch(ready_count: int, metrics: dict) -> str:
    if ready_count >= MICRO_BATCH_MIN:
        return "ready_now"
    processed = metrics.get("processed") or 0
    if processed < 10:
        return "insufficient_data"
    # production-ready rate ≈ contact * preflight * refresh chain
    chain = (
        metrics.get("contact_form_rate", 0)
        * metrics.get("preflight_processed_rate", 0)
        * metrics.get("refresh_ready_rate", 0)
    )
    if chain <= 0:
        return "lane_b_recommended"
    need = MICRO_BATCH_MIN - ready_count
    per_100 = chain * 100
    if per_100 <= 0:
        return "lane_b_recommended"
    hours = (need / per_100) * (100 / max(processed / max(datetime.now().hour, 1), 1))
    return f"~{max(1, int(hours))}h_at_current_yield"


def try_seal_next_batch(
    *,
    deadline_mode: bool = False,
) -> dict[str, Any] | None:
    """Attempt to seal next micro-batch from supply checkpoint inventory."""
    streaming = load_streaming_state()
    cp = load_supply_checkpoint()
    cands = _merged_pool_candidates(cp)

    pf = cp.get("preflight_results") or {}
    rf = cp.get("refresh_results") or {}
    rf_list = list(rf.values()) if isinstance(rf, dict) else list(rf or [])

    exclude = set(streaming.get("sealed_domains") or [])
    ready, _ = collect_production_ready(cands, pf, rf_list, exclude_domains=exclude, lane="A")

    revision = _next_revision_letter(streaming.get("sealed_revisions") or [])
    supply_lane = "C" if sum(1 for r in ready if r.get("supply_lane") == "C") >= len(ready) // 2 else "A"
    payload = seal_micro_batch(
        ready, revision=revision, lane=supply_lane, deadline_mode=deadline_mode,
    )
    if not payload:
        return None

    streaming["sealed_revisions"].append(revision)
    streaming["sealed_domains"].extend(c["domain"] for c in payload["candidates"])
    streaming["sealed_candidate_ids"].extend(c.get("candidate_id") for c in payload["candidates"])
    streaming["lane_a_ready_total"] = streaming.get("lane_a_ready_total", 0) + payload["pool_size"]
    if payload.get("supply_lane") == "C" or any(c.get("supply_lane") == "C" for c in payload.get("candidates") or []):
        streaming["lane_c_ready_total"] = streaming.get("lane_c_ready_total", 0) + payload["pool_size"]
    acct = streaming.setdefault("attempt_accounting", {})
    acct["r2_estimated_attempts"] = acct.get("r2_estimated_attempts", 0) + payload["estimated_final_submit_attempts"]
    save_streaming_state(streaming)
    return payload
