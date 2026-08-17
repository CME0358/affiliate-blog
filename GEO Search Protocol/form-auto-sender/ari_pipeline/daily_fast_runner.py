"""
ari_pipeline/daily_fast_runner.py — Daily Fast Path production orchestration (300 attempts/day).

Candidate-level safe skip; system-level hard stop only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from config import LOG_DIR, VAULT_ROOT
from shared_form_prepare import RUNTIME_DIVERGENCE
from submission_state import CONFIRMED_SENT, FAILED, UNKNOWN

OUTPUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"
DAILY_STATE_JSON = LOG_DIR / "ari_terminal_daily_fast_state.json"
DAILY_PID_FILE = LOG_DIR / "ari_terminal_daily_fast.pid"
DAILY_LOG_PREFIX = LOG_DIR / "ari_terminal_daily_fast"


def daily_state_path(revision: str = "") -> Path:
    if revision:
        safe = revision.replace("/", "-")
        return LOG_DIR / f"ari_terminal_daily_fast_state_{safe}.json"
    return DAILY_STATE_JSON


def daily_results_path(date: str, revision: str = "") -> Path:
    rev = f"-{revision}" if revision else ""
    return OUTPUT_DIR / f"ARI-Fast-Production-Results-{date}{rev}.json"

# Rolling window for aggregate quality protection
ROLLING_WINDOW_SIZE = 30
ROLLING_MIN_ATTEMPTS = 20
ROLLING_FAILED_UNKNOWN_THRESHOLD = 0.85  # 85% failed+unknown in window → pause


@dataclass
class DailyCounters:
    candidates_processed: int = 0
    candidates_skipped: int = 0
    final_submit_attempts: int = 0
    confirmed_sent: int = 0
    unknown: int = 0
    failed: int = 0
    navigation_errors: int = 0
    candidate_divergence: int = 0
    captcha_manual: int = 0
    form_not_suitable: int = 0
    slow_path_review: int = 0
    false_sent: int = 0
    duplicate_send: int = 0
    safety_violations: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "candidates_processed": self.candidates_processed,
            "candidates_skipped": self.candidates_skipped,
            "final_submit_attempts": self.final_submit_attempts,
            "confirmed_sent": self.confirmed_sent,
            "unknown": self.unknown,
            "failed": self.failed,
            "navigation_errors": self.navigation_errors,
            "candidate_divergence": self.candidate_divergence,
            "captcha_manual": self.captcha_manual,
            "form_not_suitable": self.form_not_suitable,
            "slow_path_review": self.slow_path_review,
            "false_sent": self.false_sent,
            "duplicate_send": self.duplicate_send,
            "safety_violations": self.safety_violations,
        }


def daily_queue_path(date: str, revision: str = "") -> Path:
    rev = f"-{revision}" if revision else ""
    return OUTPUT_DIR / f"ARI-Fast-Production-Queue-{date}{rev}.json"


def load_daily_queue(date: str, revision: str = "") -> dict[str, Any]:
    path = daily_queue_path(date, revision=revision)
    if not path.exists():
        raise FileNotFoundError(f"Daily queue missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_daily_state(state: dict[str, Any], *, revision: str = "") -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now().isoformat()
    path = daily_state_path(revision)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def read_daily_state(*, revision: str = "") -> dict[str, Any]:
    path = daily_state_path(revision)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _is_navigation_error(row: dict) -> bool:
    blob = " ".join([
        row.get("reason") or "",
        row.get("skip_reason") or "",
        row.get("pre_send_skip_reason") or "",
    ]).lower()
    return row.get("submission_state") == "error" and (
        "navigating" in blob or "unable to retrieve content" in blob
    )


def update_counters_from_result(counters: DailyCounters, result: dict, *, skip_classification: str = "") -> None:
    counters.candidates_processed += 1
    if skip_classification or result.get("status") == "skipped" or not result.get("attempted"):
        counters.candidates_skipped += 1
        sc = skip_classification or result.get("pre_send_skip_reason") or result.get("classification") or ""
        if "captcha" in sc.lower():
            counters.captcha_manual += 1
        elif "form_not_suitable" in sc.lower() or sc == "FORM_NOT_SUITABLE":
            counters.form_not_suitable += 1
        elif sc == "SLOW_PATH_REVIEW" or "slow_path" in sc.lower():
            counters.slow_path_review += 1
        elif result.get("submission_state") == RUNTIME_DIVERGENCE or sc == RUNTIME_DIVERGENCE:
            counters.candidate_divergence += 1
        return

    if result.get("attempted"):
        counters.final_submit_attempts += 1

    state = result.get("submission_state") or result.get("status") or ""
    if state == CONFIRMED_SENT:
        counters.confirmed_sent += 1
    elif state == UNKNOWN:
        counters.unknown += 1
    elif state == FAILED:
        counters.failed += 1
    elif state == RUNTIME_DIVERGENCE:
        counters.candidate_divergence += 1
    elif _is_navigation_error(result):
        counters.navigation_errors += 1

    if result.get("status") == "sent" and state != CONFIRMED_SENT:
        counters.false_sent += 1
    if "duplicate" in (result.get("reason") or "").lower() and result.get("attempted"):
        counters.duplicate_send += 1


def should_system_hard_stop(
    counters: DailyCounters,
    recent_attempts: list[dict],
) -> tuple[bool, str, str]:
    """
    System-level hard stop only. Returns (stop, reason, stop_class).
    stop_class is always HARD_STOP when True.
    """
    if counters.false_sent >= 1:
        return True, "false_sent", "HARD_STOP"
    if counters.duplicate_send >= 1:
        return True, "duplicate_send", "HARD_STOP"
    if counters.safety_violations >= 1:
        return True, "safety_violation", "HARD_STOP"

    for row in recent_attempts:
        notes = (row.get("notes") or "").lower()
        if row.get("attempted") and "captcha" in notes and "bypass" in notes:
            return True, "captcha_bypass", "HARD_STOP"

    attempted_recent = [r for r in recent_attempts if r.get("attempted")]
    if len(attempted_recent) >= ROLLING_MIN_ATTEMPTS:
        window = attempted_recent[-ROLLING_WINDOW_SIZE:]
        bad = sum(
            1 for r in window
            if (r.get("submission_state") in (UNKNOWN, FAILED, "error"))
            or r.get("submission_state") == RUNTIME_DIVERGENCE
        )
        rate = bad / len(window)
        if rate >= ROLLING_FAILED_UNKNOWN_THRESHOLD:
            return True, f"rolling_failure_rate_{rate:.2f}", "HARD_STOP"

    return False, "", ""


def candidate_skip_outcome(domain: str, classification: str, reason: str, *, batch_id: str, lock_index: int | None = None) -> dict:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S JST")
    return {
        "timestamp": ts,
        "batch": batch_id,
        "lock_index": lock_index,
        "domain": domain,
        "classification": classification,
        "pre_send_skip_reason": reason,
        "submission_state": "SKIPPED",
        "attempted": False,
        "final_submit_clicked": False,
        "status": "skipped",
        "reason": reason,
    }


def daily_target_reached(counters: DailyCounters, target_attempts: int) -> bool:
    return counters.final_submit_attempts >= target_attempts


def init_daily_state(
    *,
    date: str,
    target_attempts: int,
    queue_path: Path,
    effective_confirmed_baseline: int,
) -> dict[str, Any]:
    return {
        "mode": "daily_fast",
        "date": date,
        "status": "idle",
        "target_attempts": target_attempts,
        "queue_path": str(queue_path),
        "processed_domains": [],
        "attempted_domains": [],
        "counters": DailyCounters().to_dict(),
        "effective_confirmed_baseline": effective_confirmed_baseline,
        "hard_stop": False,
        "hard_stop_reason": "",
        "started_at": None,
    }
