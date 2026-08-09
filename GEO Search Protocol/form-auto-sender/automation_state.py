"""automation_state.json の読み書き（.env 不要・他スクリプトから import 可）。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from automation_registry import AUTOMATION_JOBS, CHANNEL_JOB_BY_KEY, JOBS_BY_ID

_BASE = Path(__file__).resolve().parent
AUTOMATION_STATE_PATH = _BASE / "automation_state.json"
_TZ = ZoneInfo("Asia/Tokyo")


def _load_raw() -> dict:
    if not AUTOMATION_STATE_PATH.exists():
        return {}
    try:
        data = json.loads(AUTOMATION_STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_raw(state: dict) -> None:
    AUTOMATION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTOMATION_STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def is_paused(job_id: str) -> bool:
    entry = _load_raw().get(job_id)
    if isinstance(entry, dict) and "paused" in entry:
        return bool(entry["paused"])
    job = JOBS_BY_ID.get(job_id)
    if job:
        return not job.default_on
    return False


def is_channel_paused(channel_key: str) -> bool:
    job_id = CHANNEL_JOB_BY_KEY.get(channel_key)
    if not job_id:
        return False
    if is_paused("qol-buffer-daily"):
        return True
    return is_paused(job_id)


def set_paused(job_id: str, paused: bool, *, by: str) -> None:
    if job_id not in JOBS_BY_ID:
        raise ValueError(f"未知のジョブ ID: {job_id}")
    job = JOBS_BY_ID[job_id]
    state = _load_raw()
    state[job_id] = {
        "paused": paused,
        "launchd": job.launchd,
        "updated_at": datetime.now(_TZ).isoformat(timespec="seconds"),
        "updated_by": by,
    }
    _save_raw(state)


def sync_defaults(*, by: str = "automation_control.py sync-defaults") -> list[str]:
    """default_on=False のジョブを停止状態に揃える（default ON の明示停止は維持）。"""
    state = _load_raw()
    changed: list[str] = []
    for job in AUTOMATION_JOBS:
        if job.default_on:
            continue
        entry = state.get(job.id)
        current = (
            bool(entry["paused"])
            if isinstance(entry, dict) and "paused" in entry
            else True
        )
        if not current:
            state[job.id] = {
                "paused": True,
                "launchd": job.launchd,
                "updated_at": datetime.now(_TZ).isoformat(timespec="seconds"),
                "updated_by": by,
            }
            changed.append(job.id)
    _save_raw(state)
    return changed


def build_runtime_snapshot() -> dict[str, dict]:
    fas_dir = str(_BASE)
    out: dict[str, dict] = {}
    for job in AUTOMATION_JOBS:
        entry = _load_raw().get(job.id, {})
        paused = is_paused(job.id)
        out[job.id] = {
            "paused": paused,
            "controlDir": fas_dir,
            "updatedAt": entry.get("updated_at") if isinstance(entry, dict) else None,
            "defaultOn": job.default_on,
        }
    return out
