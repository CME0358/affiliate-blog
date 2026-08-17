"""
ari_pipeline/dashboard.py — End-of-day dashboard (single Markdown + JSON).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from config import VAULT_ROOT
from automation_state import is_paused
from ari_pipeline.forensic_queue import build_forensic_queue
from ari_pipeline.kpi_aggregator import aggregate_daily_kpi
from ari_pipeline.limits import load_limits, tomorrow_scale_config
from ari_pipeline.status_integrity import count_official_confirmed_sent

OUTPUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"


def build_dashboard(for_date: str = "2026-08-11", pool_date: str = "2026-08-12") -> dict:
    kpi = aggregate_daily_kpi(for_date)
    forensic = build_forensic_queue()
    limits = load_limits(pool_date)
    scale = tomorrow_scale_config(pool_date)

    pool_path = OUTPUT_DIR / f"ARI-Candidate-Pool-{pool_date}-500.json"
    pool_size = 0
    if pool_path.exists():
        pool_size = json.loads(pool_path.read_text(encoding="utf-8")).get("stats", {}).get("pool_size", 0)

    cp_path = VAULT_ROOT / "10_Projects/GEO Search Protocol/form-auto-sender/logs/ari_checkpoints"
    checkpoint_count = len(list(cp_path.glob("orchestrator_*.json"))) if cp_path.exists() else 0

    return {
        "generated_at": datetime.now().isoformat(),
        "for_date": for_date,
        "today": {
            "candidates_processed": kpi["batch_log_rows"],
            "confirmed_sent": kpi["production"]["confirmed_sent"],
            "official_confirmed_total": count_official_confirmed_sent(),
            "replies": 0,
            "purchases": 0,
            "revenue": 0,
        },
        "technical": kpi["quality"],
        "production": kpi["production"],
        "tomorrow_ready": {
            "candidate_pool_size": pool_size,
            "lightweight_queue": pool_size,
            "preflight_queue_cap": limits.full_preflight_limit,
            "auto_ready_cap": limits.auto_ready_limit,
            "production_limit": limits.production_limit,
            "forensic_queue_count": forensic["count"],
            "orchestrator_checkpoints": checkpoint_count,
        },
        "end_of_day_state": {
            "automation_paused": is_paused("form-auto-sender"),
            "production_stopped": limits.production_limit == 0,
            "automatic_retry_disabled": True,
            "additional_sends_tonight": 0,
        },
        "tomorrow_scale": scale,
    }


def write_dashboard(for_date: str = "2026-08-11", pool_date: str = "2026-08-12") -> tuple[Path, Path]:
    dash = build_dashboard(for_date, pool_date)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / f"ari_eod_dashboard_{for_date}.json"
    md_path = OUTPUT_DIR / f"ARI End-of-Day Dashboard {for_date}.md"
    json_path.write_text(json.dumps(dash, ensure_ascii=False, indent=2), encoding="utf-8")

    t = dash["today"]
    tr = dash["tomorrow_ready"]
    eod = dash["end_of_day_state"]
    lines = [
        f"# ARI End-of-Day Dashboard {for_date}",
        "",
        "## Today",
        "",
        f"- Candidates processed (batch logs): {t['candidates_processed']}",
        f"- Confirmed Sent (today batches): {t['confirmed_sent']}",
        f"- Official CONFIRMED_SENT total: {t['official_confirmed_total']}",
        f"- Replies: {t['replies']}",
        f"- Purchases: {t['purchases']}",
        "",
        "## Technical",
        "",
        f"- false SENT: {dash['technical'].get('false_sent_count', 0)}",
        f"- UNKNOWN rate: {dash['technical'].get('unknown_rate', 0)}%",
        f"- RUNTIME_DIVERGENCE (batch): {dash['production'].get('runtime_divergence', 0)}",
        "",
        "## Tomorrow Ready",
        "",
        f"- Candidate pool: {tr['candidate_pool_size']}",
        f"- Lightweight queue: {tr['lightweight_queue']}",
        f"- Preflight cap: {tr['preflight_queue_cap']}",
        f"- AUTO_READY cap: {tr['auto_ready_cap']}",
        f"- Production limit: {tr['production_limit']}",
        f"- Forensic queue: {tr['forensic_queue_count']}",
        "",
        "## End-of-Day State",
        "",
        f"- automation paused: {eod['automation_paused']}",
        f"- production stopped: {eod['production_stopped']}",
        f"- retry disabled: {eod['automatic_retry_disabled']}",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path
