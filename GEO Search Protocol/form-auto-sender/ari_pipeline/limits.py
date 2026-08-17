"""
ari_pipeline/limits.py — 500 candidates/day operating guard.

500/day = candidate processing capacity (NOT 500 attempted sends).
production_limit=0 tonight and until explicitly raised.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from config import LOG_DIR, VAULT_ROOT

LIMITS_PATH = LOG_DIR / "ari_daily_limits.json"
DEFAULT_POOL_DATE = "2026-08-12"


@dataclass
class AriDailyLimits:
    date: str = DEFAULT_POOL_DATE
    daily_candidate_limit: int = 500
    lightweight_limit: int = 500
    full_preflight_limit: int = 100
    auto_ready_limit: int = 50
    production_limit: int = 0
    production_enabled: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AriDailyLimits":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: Path | None = None) -> Path:
        p = path or LIMITS_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return p


def load_limits(date: str | None = None) -> AriDailyLimits:
    if LIMITS_PATH.exists():
        data = json.loads(LIMITS_PATH.read_text(encoding="utf-8"))
        lim = AriDailyLimits.from_dict(data)
        if date:
            lim.date = date
        return lim
    lim = AriDailyLimits(date=date or DEFAULT_POOL_DATE)
    if os.environ.get("ARI_PRODUCTION_LIMIT"):
        lim.production_limit = int(os.environ["ARI_PRODUCTION_LIMIT"])
    return lim


def tomorrow_scale_config(date: str = DEFAULT_POOL_DATE) -> dict:
    """Phase 6 — staged expansion defaults for tomorrow."""
    lim = load_limits(date)
    return {
        "date": date,
        "morning": {
            "action": "lightweight_detect",
            "pool_size": lim.daily_candidate_limit,
            "cap": lim.lightweight_limit,
        },
        "mid_stage": {
            "action": "full_preflight",
            "input_stage": "PREFLIGHT_CANDIDATE",
            "cap": lim.full_preflight_limit,
        },
        "production": {
            "action": "supervised_batch",
            "input_stage": "AUTO_READY",
            "cap": lim.production_limit,
            "gate": "result_gate_between_batches",
            "note": "Never send all 500 unconditionally",
        },
        "limits": lim.to_dict(),
    }
