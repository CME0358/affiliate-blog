"""
production_ownership.py — Process-scoped production ownership for Night Factory coexistence.

Night Factory must not own or invoke production. Global production_limit > 0 is allowed
only when an authorized Terminal production owner is alive and distinct.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from config import LOG_DIR, VAULT_ROOT

OWNERSHIP_JSON = LOG_DIR / "ari_production_ownership.json"
OWNER_TERMINAL = "TERMINAL_PRODUCTION"

AUTHORIZED_COMMAND_MARKERS = (
    "run_ari_terminal_production.py",
    "run_ari_terminal_production.sh",
)

OUTPUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"


def get_process_command(pid: int) -> str:
    try:
        return subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "command="],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError, OSError):
        return ""


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def command_is_authorized_terminal(command: str) -> bool:
    cmd = command or ""
    lower = cmd.lower()
    if any(m in cmd for m in AUTHORIZED_COMMAND_MARKERS):
        if "run_ari_night_factory" in lower:
            return False
        return True
    return False


def load_ownership() -> dict[str, Any] | None:
    if not OWNERSHIP_JSON.exists():
        return None
    try:
        data = json.loads(OWNERSHIP_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def save_ownership(payload: dict[str, Any]) -> None:
    OWNERSHIP_JSON.parent.mkdir(parents=True, exist_ok=True)
    OWNERSHIP_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_ownership(*, pid: int | None = None) -> None:
    current = load_ownership()
    if not current:
        OWNERSHIP_JSON.unlink(missing_ok=True)
        return
    if pid is not None and int(current.get("production_pid") or 0) != int(pid):
        return
    OWNERSHIP_JSON.unlink(missing_ok=True)


def claim_terminal_ownership(
    *,
    pid: int,
    batch_id: str,
    production_limit: int,
) -> dict[str, Any]:
    payload = {
        "production_owner": OWNER_TERMINAL,
        "production_batch_id": batch_id,
        "production_pid": int(pid),
        "production_limit": int(production_limit),
        "claimed_at": datetime.now().isoformat(),
        "command": get_process_command(pid),
    }
    save_ownership(payload)
    return payload


def verify_authorized_terminal_owner(
    *,
    night_factory_pid: int | None = None,
    expected_limit: int | None = None,
) -> dict[str, Any]:
    """
    Returns {valid: bool, reason: str, ownership: dict|None}.
    valid=True only for a live external Terminal production owner.
    """
    rec = load_ownership()
    if not rec:
        return {"valid": False, "reason": "no_owner", "ownership": None}

    owner = rec.get("production_owner")
    pid = int(rec.get("production_pid") or 0)
    if owner != OWNER_TERMINAL:
        return {"valid": False, "reason": f"invalid_owner:{owner}", "ownership": rec}
    if pid <= 0:
        return {"valid": False, "reason": "missing_production_pid", "ownership": rec}
    if night_factory_pid and pid == int(night_factory_pid):
        return {"valid": False, "reason": "owner_pid_equals_night_factory", "ownership": rec}
    if not process_alive(pid):
        return {"valid": False, "reason": "owner_pid_dead", "ownership": rec}

    live_cmd = get_process_command(pid)
    recorded = rec.get("command") or ""
    if not command_is_authorized_terminal(live_cmd):
        # Reused PID: alive process is not the authorized runner
        return {
            "valid": False,
            "reason": "owner_pid_reused_or_unauthorized_command",
            "ownership": rec,
            "live_command": live_cmd,
            "recorded_command": recorded,
        }
    if expected_limit is not None and int(rec.get("production_limit") or 0) not in (0, int(expected_limit)):
        # Limit may be updated by the owner; mismatch alone is not fatal if command is valid
        pass
    return {"valid": True, "reason": "authorized_terminal_owner", "ownership": rec, "live_command": live_cmd}


def load_attempted_domains_from_results(*, date: str | None = None) -> set[str]:
    attempted: set[str] = set()
    if not OUTPUT_DIR.exists():
        return attempted
    pattern = f"ARI-Fast-Production-Results-{date}*.json" if date else "ARI-Fast-Production-Results-*.json"
    for path in OUTPUT_DIR.glob(pattern):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for r in data.get("results") or []:
            if r.get("attempted") or r.get("final_submit_clicked") or r.get("final_submit_attempted"):
                dom = (r.get("domain") or "").lower()
                if dom:
                    attempted.add(dom)
    return attempted


def sent_csv_line_count(path: Path | None = None) -> int:
    p = path or (LOG_DIR / "sent.csv")
    if not p.exists():
        return 0
    return sum(1 for _ in open(p, encoding="utf-8", errors="replace"))


def classify_sent_csv_delta(
    *,
    baseline: int,
    current: int,
    owner_valid: bool,
    production_date: str | None = None,
) -> dict[str, Any]:
    if current <= baseline:
        return {"kind": "NONE", "delta": 0}
    delta = current - baseline
    if owner_valid:
        return {"kind": "AUTHORIZED_EXTERNAL_SENT_DELTA", "delta": delta}
    today = production_date or datetime.now().strftime("%Y-%m-%d")
    attempted = load_attempted_domains_from_results(date=today)
    if attempted:
        return {"kind": "AUTHORIZED_EXTERNAL_SENT_DELTA", "delta": delta, "owner_released": True}
    return {"kind": "UNAUTHORIZED_MUTATION", "delta": delta}
