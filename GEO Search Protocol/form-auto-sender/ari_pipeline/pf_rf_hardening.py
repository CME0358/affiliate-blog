"""
pf_rf_hardening.py — PF/RF FAST-FAIL + priority pipeline (ZERO SEND).

Throughput only. Does not change READY qualification semantics.
Active only when Night Factory PF budget context is entered.
The running worker that imported older modules is unaffected until next lifecycle.
"""

from __future__ import annotations

import math
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Sequence

# --- budgets (Night Factory PF only; production fill path unchanged) ---

PF_FIELD_FILL_TIMEOUT_MS = 4000
PF_CANDIDATE_WALL_SEC = 22.0
PF_HIGH_WEIGHT = 4
PF_NORMAL_WEIGHT = 1
IN_PROGRESS_STALE_SEC = 180.0

PF_PRIORITY_HIGH = "PF_PRIORITY_HIGH"
PF_PRIORITY_NORMAL = "PF_PRIORITY_NORMAL"
PF_PRIORITY_DEFER = "PF_PRIORITY_DEFER"

OUTCOME_PF_DEFERRED = "PF_DEFERRED"
OUTCOME_PF_FAST_FAIL = "PF_FAST_FAIL"

STATUS_PF_PENDING = "PF_PENDING"
STATUS_PF_IN_PROGRESS = "PF_IN_PROGRESS"
STATUS_PF_DEFERRED = "PF_DEFERRED"
STATUS_PF_COMPLETE = "PF_COMPLETE"
STATUS_RF_PENDING = "RF_PENDING"
STATUS_RF_IN_PROGRESS = "RF_IN_PROGRESS"
STATUS_RF_COMPLETE = "RF_COMPLETE"
STATUS_READY = "READY"

_nf_pf_mode: ContextVar[bool] = ContextVar("nf_pf_mode", default=False)
_nf_pf_deadline: ContextVar[float | None] = ContextVar("nf_pf_deadline", default=None)

_cp_write_lock = threading.Lock()
_in_flight_domains: set[str] = set()
_in_flight_lock = threading.Lock()


def nf_pf_mode_active() -> bool:
    return bool(_nf_pf_mode.get())


def pf_deadline_exceeded() -> bool:
    dl = _nf_pf_deadline.get()
    return dl is not None and time.monotonic() >= dl


@contextmanager
def enter_nf_pf_budget(*, wall_sec: float = PF_CANDIDATE_WALL_SEC):
    tok_m = _nf_pf_mode.set(True)
    tok_d = _nf_pf_deadline.set(time.monotonic() + wall_sec)
    try:
        yield
    finally:
        _nf_pf_mode.reset(tok_m)
        _nf_pf_deadline.reset(tok_d)


def checkpoint_write_lock() -> threading.Lock:
    return _cp_write_lock


# --- locator resolution (no Playwright required) ---

@dataclass(frozen=True)
class ElementProbe:
    visible: bool
    enabled: bool
    editable: bool
    in_form_scope: bool = True
    semantic_id: str = ""


@dataclass
class LocatorProbe:
    selector: str
    elements: list[ElementProbe] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.elements)


QUALIFIED = "qualified"
FAST_FAIL_NOT_INTERACTABLE = "required_field_not_interactable"
DEFER_AMBIGUOUS = "ambiguous_field_locator"
DEFER_TIME_BUDGET = "pf_time_budget_exceeded"
DEFER_DYNAMIC = "dynamic_form_unresolved"
FAST_FAIL_MISSING_EMAIL = "missing_email"
FAST_FAIL_MISSING_NAME = "missing_name"
FAST_FAIL_NO_FINAL_SUBMIT = "no_final_submit"
FAST_FAIL_CAPTCHA = "captcha"
DEFER_PURPOSE_AMBIGUOUS = "inquiry_purpose_ambiguous"


def qualified_indices(probe: LocatorProbe) -> list[int]:
    out: list[int] = []
    for i, el in enumerate(probe.elements):
        if el.visible and el.enabled and el.editable and el.in_form_scope:
            out.append(i)
    return out


def resolve_locator_action(probe: LocatorProbe) -> tuple[str, int | None, str]:
    """
    Returns (action, index, reason).
    action: fill | fast_fail | defer
    Never use an invisible first match.
    """
    if probe.count == 0:
        return "fast_fail", None, FAST_FAIL_NOT_INTERACTABLE
    q = qualified_indices(probe)
    if len(q) == 1:
        return "fill", q[0], QUALIFIED
    if len(q) == 0:
        return "fast_fail", None, FAST_FAIL_NOT_INTERACTABLE
    ids = {probe.elements[i].semantic_id for i in q if probe.elements[i].semantic_id}
    if len(q) > 1 and (len(ids) > 1 or not ids):
        return "defer", None, DEFER_AMBIGUOUS
    return "fill", q[0], QUALIFIED


async def probe_locator(page, selector: str, *, form_scope: str | None = None) -> LocatorProbe:
    loc = page.locator(selector)
    try:
        n = await loc.count()
    except Exception:
        return LocatorProbe(selector=selector, elements=[])
    elements: list[ElementProbe] = []
    for i in range(n):
        el = loc.nth(i)
        try:
            visible = await el.is_visible()
        except Exception:
            visible = False
        try:
            enabled = await el.is_enabled()
        except Exception:
            enabled = False
        try:
            editable = await el.is_editable()
        except Exception:
            editable = visible and enabled
        in_scope = True
        if form_scope:
            try:
                handle = await el.element_handle()
                in_scope = bool(handle) and True
            except Exception:
                in_scope = True
        name = ""
        try:
            name = (await el.get_attribute("name")) or (await el.get_attribute("id")) or ""
        except Exception:
            name = ""
        elements.append(
            ElementProbe(
                visible=bool(visible),
                enabled=bool(enabled),
                editable=bool(editable),
                in_form_scope=in_scope,
                semantic_id=str(name),
            )
        )
    return LocatorProbe(selector=selector, elements=elements)


async def nf_pf_fill(page, selector: str, value: str) -> None:
    """Bounded fill for Night Factory PF only. Raises FastFail/Defer exceptions."""
    if pf_deadline_exceeded():
        raise PfDefer(DEFER_TIME_BUDGET)
    probe = await probe_locator(page, selector)
    action, idx, reason = resolve_locator_action(probe)
    if action == "fast_fail":
        raise PfFastFail(reason)
    if action == "defer":
        raise PfDefer(reason)
    loc = page.locator(selector).nth(idx or 0)
    await loc.fill(value, timeout=PF_FIELD_FILL_TIMEOUT_MS)


class PfFastFail(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class PfDefer(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# --- priority classifier (generic; no site-specific hardcodes) ---

_HIGH_OUTCOMES = frozenset({"AUTO_READY_CANDIDATE", "CONFIRMATION_READY", "AUTO_READY"})
_BLOCK_REASONS = frozenset({
    "dynamic_form_unresolved",
    "dynamic_submit_unresolved",
    "captcha_detected",
    "captcha",
    "missing_email",
    "missing_name",
    "no_final_submit",
    "email_field_not_found",
    "submit_field_not_found",
})


def _field_map(rec: dict[str, Any]) -> dict[str, Any]:
    det = rec.get("detection") or {}
    fn = rec.get("fill_no_submit") or {}
    return det.get("field_map") or fn.get("field_map") or rec.get("field_map") or {}


def _missing(fm: dict[str, Any], key: str) -> bool:
    v = fm.get(key)
    if v is None:
        return True
    if isinstance(v, str) and v.upper() in ("MISSING", "", "NONE"):
        return True
    return False


def classify_pf_priority(rec: dict[str, Any]) -> tuple[str, str]:
    """
    Returns (priority, reason).
    DEFER is not rejection — candidate stays available for slow-path.
    """
    reason = (
        (rec.get("lightweight_reason") or rec.get("skip_reason") or rec.get("failure_reason") or "")
        + " "
        + str((rec.get("detection") or {}).get("failure_reason") or "")
        + " "
        + str((rec.get("fill_no_submit") or {}).get("reason") or "")
    ).lower()

    if rec.get("captcha") or rec.get("captcha_detected") or (rec.get("detection") or {}).get("captcha"):
        return PF_PRIORITY_DEFER, FAST_FAIL_CAPTCHA
    if "captcha" in reason or "recaptcha" in reason:
        return PF_PRIORITY_DEFER, FAST_FAIL_CAPTCHA
    if "dynamic_form" in reason or "dynamic_submit" in reason:
        return PF_PRIORITY_DEFER, DEFER_DYNAMIC
    if "inquiry_purpose_ambiguous" in reason or "reason_ambiguous" in reason or "ambiguous" in reason and "purpose" in reason:
        return PF_PRIORITY_DEFER, DEFER_PURPOSE_AMBIGUOUS

    fm = _field_map(rec)
    if fm:
        if _missing(fm, "email"):
            return PF_PRIORITY_DEFER, FAST_FAIL_MISSING_EMAIL
        if _missing(fm, "name"):
            return PF_PRIORITY_DEFER, FAST_FAIL_MISSING_NAME

    if rec.get("final_submit_identified") is False or rec.get("lightweight_reason") == "no_final_submit":
        if "no_final_submit" in reason or rec.get("final_submit_identified") is False:
            det = rec.get("detection") or {}
            if det.get("submit_label") in (None, "", "MISSING") and rec.get("final_submit_identified") is False:
                return PF_PRIORITY_DEFER, FAST_FAIL_NO_FINAL_SUBMIT

    outcome = rec.get("preflight_outcome") or rec.get("lightweight_outcome") or ""
    if outcome in _HIGH_OUTCOMES:
        return PF_PRIORITY_HIGH, "auto_or_confirmation_ready"

    high_signals = 0
    if rec.get("final_submit_identified") or (rec.get("detection") or {}).get("submit_label"):
        high_signals += 1
    if fm and not _missing(fm, "email") and not _missing(fm, "name"):
        high_signals += 1
    if rec.get("canonical_submit_target") or (rec.get("detection") or {}).get("form_type") in (
        "generic_contact", "contact", "inquiry",
    ):
        high_signals += 1
    if rec.get("ready_priority_tier") == "READY_PRIORITY_A":
        high_signals += 1
    if high_signals >= 3:
        return PF_PRIORITY_HIGH, "complete_canonical_evidence"
    return PF_PRIORITY_NORMAL, "default"


def structural_blocker_reason(rec: dict[str, Any]) -> str | None:
    pri, reason = classify_pf_priority(rec)
    if pri != PF_PRIORITY_DEFER:
        return None
    return reason


def should_skip_browser_pf(rec: dict[str, Any]) -> bool:
    """Deterministic structural blockers — do not spend Playwright time."""
    return structural_blocker_reason(rec) in {
        FAST_FAIL_CAPTCHA,
        FAST_FAIL_MISSING_EMAIL,
        FAST_FAIL_MISSING_NAME,
        FAST_FAIL_NO_FINAL_SUBMIT,
        DEFER_DYNAMIC,
        DEFER_PURPOSE_AMBIGUOUS,
    }


def rf_should_accept(pf_row: dict[str, Any]) -> bool:
    """RF only receives candidates that actually need semantic refresh."""
    outcome = pf_row.get("preflight_outcome") or ""
    if outcome in (OUTCOME_PF_DEFERRED, OUTCOME_PF_FAST_FAIL, "CAPTCHA_MANUAL", "FORM_NOT_SUITABLE", "UNKNOWN", "INTERNAL_ERROR"):
        return False
    if pf_row.get("pipeline_status") in (STATUS_PF_DEFERRED,):
        return False
    if pf_row.get("captcha_detected") or (pf_row.get("fill_no_submit") or {}).get("captcha_detected"):
        return False
    skip = (pf_row.get("skip_reason") or "").lower()
    if skip in _BLOCK_REASONS or skip in {
        FAST_FAIL_CAPTCHA, FAST_FAIL_MISSING_EMAIL, FAST_FAIL_MISSING_NAME,
        FAST_FAIL_NO_FINAL_SUBMIT, DEFER_DYNAMIC, DEFER_PURPOSE_AMBIGUOUS,
        DEFER_TIME_BUDGET, FAST_FAIL_NOT_INTERACTABLE, DEFER_AMBIGUOUS,
    }:
        return False
    cls = pf_row.get("preflight_classification") or ""
    if cls in ("FORM_NOT_SUITABLE", "MANUAL_INTERVENTION_REQUIRED"):
        return False
    return True


def rf_sort_key(row: dict[str, Any]) -> tuple:
    outcome = row.get("preflight_outcome") or ""
    if outcome in ("CONFIRMATION_READY", "AUTO_READY_CANDIDATE"):
        rank = 0
    elif row.get("preflight_classification") == "AUTO_READY":
        rank = 0
    else:
        rank = 1
    return (rank, -(int(row.get("ready_yield_score") or 0)))


def schedule_weighted(
    high: Sequence[dict],
    normal: Sequence[dict],
    *,
    take: int,
    high_weight: int = PF_HIGH_WEIGHT,
    normal_weight: int = PF_NORMAL_WEIGHT,
) -> list[dict]:
    """HIGH:NORMAL = 4:1 without permanently starving NORMAL."""
    out: list[dict] = []
    hi = list(high)
    no = list(normal)
    cycle = max(1, high_weight + normal_weight)
    while len(out) < take and (hi or no):
        slot = len(out) % cycle
        if slot < high_weight and hi:
            out.append(hi.pop(0))
        elif no:
            out.append(no.pop(0))
        elif hi:
            out.append(hi.pop(0))
        else:
            break
    return out[:take]


def partition_by_priority(cands: Iterable[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    high: list[dict] = []
    normal: list[dict] = []
    deferred: list[dict] = []
    for c in cands:
        pri, _ = classify_pf_priority(c)
        if pri == PF_PRIORITY_HIGH:
            high.append(c)
        elif pri == PF_PRIORITY_DEFER:
            deferred.append(c)
        else:
            normal.append(c)
    return high, normal, deferred


def make_deferred_row(rec: dict[str, Any], reason: str) -> dict[str, Any]:
    dom = (rec.get("domain") or "").lower()
    return {
        **{k: rec.get(k) for k in (
            "domain", "company_name", "website_url", "form_url",
            "industry_name", "area_name", "candidate_id",
        ) if rec.get(k) is not None},
        "domain": dom,
        "preflight_outcome": OUTCOME_PF_DEFERRED,
        "preflight_classification": "NOT_READY",
        "skip_reason": reason,
        "pipeline_status": STATUS_PF_DEFERRED,
        "deferred": True,
        "defer_is_not_rejection": True,
        "elapsed_seconds": 0.0,
        "completed_at": datetime.now().isoformat(),
        "hardening": True,
    }


# --- in-flight / idempotency ---

def claim_domain(domain: str) -> bool:
    d = (domain or "").lower()
    if not d:
        return False
    with _in_flight_lock:
        if d in _in_flight_domains:
            return False
        _in_flight_domains.add(d)
        return True


def release_domain(domain: str) -> None:
    d = (domain or "").lower()
    with _in_flight_lock:
        _in_flight_domains.discard(d)


def recover_stale_in_progress(cp: dict, *, now: float | None = None, stale_sec: float = IN_PROGRESS_STALE_SEC) -> list[str]:
    """IN_PROGRESS older than stale_sec becomes PENDING again. Does not erase evidence."""
    now = now if now is not None else time.time()
    recovered: list[str] = []
    states = cp.setdefault("pipeline_domain_status", {})
    for dom, row in list(states.items()):
        if not isinstance(row, dict):
            continue
        st = row.get("status")
        started = row.get("started_ts")
        if st in (STATUS_PF_IN_PROGRESS, STATUS_RF_IN_PROGRESS) and isinstance(started, (int, float)):
            if now - started >= stale_sec:
                row["status"] = STATUS_PF_PENDING if st == STATUS_PF_IN_PROGRESS else STATUS_RF_PENDING
                row["recovered_from_in_progress"] = True
                recovered.append(dom)
    return recovered


def mark_status(cp: dict, domain: str, status: str) -> None:
    states = cp.setdefault("pipeline_domain_status", {})
    prev = states.get(domain) or {}
    states[domain] = {
        **prev,
        "status": status,
        "updated_at": datetime.now().isoformat(),
        "started_ts": time.time() if status.endswith("IN_PROGRESS") else prev.get("started_ts"),
    }


def ready_insert_atomic(inv: dict, rec: dict, bucket: str) -> bool:
    """Insert READY once. Returns False if domain already present."""
    dom = (rec.get("domain") or "").lower()
    if not dom:
        return False
    existing = set(inv.get("domains_primary") or []) | set(inv.get("domains_remodel") or [])
    if dom in existing:
        return False
    if bucket == "remodel":
        inv.setdefault("ready_remodel_reserve", []).append(rec)
        inv.setdefault("domains_remodel", []).append(dom)
    else:
        inv.setdefault("ready_primary", []).append(rec)
        inv.setdefault("domains_primary", []).append(dom)
    return True


# --- metrics ---

def _parse_iso(ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts).timestamp()
    except (TypeError, ValueError):
        return None


def _percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    if len(ys) == 1:
        return ys[0]
    k = (len(ys) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return ys[int(k)]
    return ys[f] + (ys[c] - ys[f]) * (k - f)


def _elapsed_list(rows: Iterable[dict]) -> list[float]:
    out: list[float] = []
    for r in rows:
        v = r.get("elapsed_seconds")
        if isinstance(v, (int, float)) and v >= 0:
            out.append(float(v))
    return out


def compute_rolling_throughput(cp: dict, *, now_ts: float | None = None) -> dict[str, Any]:
    """
    Rolling last-hour rates from checkpoint evidence timestamps.
    Does not reset historical counters.
    """
    now_ts = now_ts if now_ts is not None else time.time()
    hour_ago = now_ts - 3600.0

    pf_rows = list((cp.get("preflight_results") or {}).values())
    rf_rows = list((cp.get("refresh_results") or {}).values())
    deferred = list((cp.get("pf_deferred") or {}).values())

    def last_hour(rows: list[dict]) -> int:
        n = 0
        for r in rows:
            ts = _parse_iso(r.get("completed_at"))
            if ts is not None and ts >= hour_ago:
                n += 1
        return n

    pf_all = pf_rows + deferred
    pf_lh = last_hour(pf_all)
    rf_lh = last_hour(rf_rows)

    pf_secs = _elapsed_list(pf_all)
    rf_secs = _elapsed_list(rf_rows)

    states = cp.get("pipeline_domain_status") or {}
    pf_high_pending = sum(1 for v in states.values() if isinstance(v, dict) and v.get("priority") == PF_PRIORITY_HIGH and v.get("status") == STATUS_PF_PENDING)
    pf_normal_pending = sum(1 for v in states.values() if isinstance(v, dict) and v.get("priority") == PF_PRIORITY_NORMAL and v.get("status") == STATUS_PF_PENDING)

    counters = cp.get("hardening_counters") or {}

    return {
        "pf_last_hour": pf_lh,
        "pf_per_hour": float(pf_lh),
        "rf_last_hour": rf_lh,
        "rf_per_hour": float(rf_lh),
        "ready_last_hour": 0,
        "READY_per_hour": 0.0,
        "pf_high_pending": pf_high_pending,
        "pf_normal_pending": pf_normal_pending,
        "pf_deferred": len(deferred),
        "rf_pending": sum(1 for v in states.values() if isinstance(v, dict) and v.get("status") == STATUS_RF_PENDING),
        "avg_pf_seconds": round(sum(pf_secs) / len(pf_secs), 2) if pf_secs else 0.0,
        "p50_pf_seconds": round(_percentile(pf_secs, 0.50), 2),
        "p95_pf_seconds": round(_percentile(pf_secs, 0.95), 2),
        "avg_rf_seconds": round(sum(rf_secs) / len(rf_secs), 2) if rf_secs else 0.0,
        "p50_rf_seconds": round(_percentile(rf_secs, 0.50), 2),
        "p95_rf_seconds": round(_percentile(rf_secs, 0.95), 2),
        "pf_fast_fail_count": int(counters.get("pf_fast_fail_count") or 0),
        "pf_timeout_defer_count": int(counters.get("pf_timeout_defer_count") or 0),
        "dynamic_form_defer_count": int(counters.get("dynamic_form_defer_count") or 0),
        "invisible_field_defer_count": int(counters.get("invisible_field_defer_count") or 0),
        "READY_yield_from_pf": int(counters.get("READY_yield_from_pf") or 0),
        "READY_yield_from_rf": int(counters.get("READY_yield_from_rf") or 0),
        "metric_source": "checkpoint_completed_at_rolling_1h",
    }


def attach_ready_rate(metrics: dict[str, Any], state: dict) -> dict[str, Any]:
    samples = (state.get("stats") or {}).get("ready_timestamps") or []
    if len(samples) >= 2:
        now = time.time()
        hour_ago = now - 3600
        window = []
        for s in samples:
            ts = _parse_iso(s.get("ts"))
            if ts is not None and ts >= hour_ago:
                window.append(s)
        if len(window) >= 2:
            delta = int(window[-1].get("ready_total") or 0) - int(window[0].get("ready_total") or 0)
            # READY total can drop when consumed; count only positive manufacturing
            added = (state.get("stats") or {}).get("ready_added_last_hour") or []
            if isinstance(added, list) and added:
                metrics["ready_last_hour"] = len(added)
                metrics["READY_per_hour"] = float(len(added))
            else:
                metrics["ready_last_hour"] = max(0, delta)
                metrics["READY_per_hour"] = float(max(0, delta))
    return metrics


def bump_counter(cp: dict, key: str, n: int = 1) -> None:
    ctr = cp.setdefault("hardening_counters", {})
    ctr[key] = int(ctr.get(key) or 0) + n


def increment_defer_counters(cp: dict, reason: str) -> None:
    if reason == DEFER_TIME_BUDGET:
        bump_counter(cp, "pf_timeout_defer_count")
    elif reason == DEFER_DYNAMIC:
        bump_counter(cp, "dynamic_form_defer_count")
    elif reason in (FAST_FAIL_NOT_INTERACTABLE, DEFER_AMBIGUOUS):
        bump_counter(cp, "invisible_field_defer_count")
    if reason in (FAST_FAIL_NOT_INTERACTABLE, FAST_FAIL_MISSING_EMAIL, FAST_FAIL_MISSING_NAME, FAST_FAIL_NO_FINAL_SUBMIT, FAST_FAIL_CAPTCHA):
        bump_counter(cp, "pf_fast_fail_count")


def old_vs_new_pf_seconds(reason: str | None, old_elapsed: float | None) -> tuple[float, float]:
    """Estimate NEW wall time from structural reason vs recorded OLD elapsed."""
    old = float(old_elapsed or 0)
    if reason in {
        FAST_FAIL_CAPTCHA, FAST_FAIL_MISSING_EMAIL, FAST_FAIL_MISSING_NAME,
        FAST_FAIL_NO_FINAL_SUBMIT, DEFER_DYNAMIC, DEFER_PURPOSE_AMBIGUOUS,
        FAST_FAIL_NOT_INTERACTABLE, DEFER_AMBIGUOUS,
    }:
        return old, 0.15
    if reason == DEFER_TIME_BUDGET:
        return old, min(old, PF_CANDIDATE_WALL_SEC)
    return old, old
