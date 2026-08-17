"""
ari_pipeline/kpi_aggregator.py — Daily KPI from distributed batch logs.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from config import LOG_DIR, VAULT_ROOT
from ari_pipeline.status_integrity import count_official_confirmed_sent, count_raw_sent_rows

OUTPUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"

# Log sources for a given date (glob patterns resolved at runtime)
_BATCH_LOG_GLOBS = (
    "ari_*_2026-*.csv",
    "ari_*_batch*.csv",
)


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _bool(val) -> bool:
    return str(val or "").lower() in ("true", "1", "yes")


def _collect_batch_logs(for_date: str) -> list[dict]:
    rows: list[dict] = []
    for p in sorted(LOG_DIR.glob("ari_*.csv")):
        if for_date.replace("-", "") not in p.name and for_date not in p.name:
            continue
        rows.extend(_read_csv(p))
    return rows


def _load_json_globs(for_date: str) -> list[dict]:
    out: list[dict] = []
    for p in OUTPUT_DIR.glob(f"ari_*{for_date}*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                out.append(data)
        except Exception:
            pass
    return out


def aggregate_daily_kpi(for_date: str = "2026-08-11") -> dict:
    batch_rows = _collect_batch_logs(for_date)
    json_reports = _load_json_globs(for_date)

    # Production metrics from batch CSV rows
    attempted = sum(1 for r in batch_rows if _bool(r.get("attempted")))
    final_submit = sum(1 for r in batch_rows if _bool(r.get("final_submit_clicked")))
    confirmed = sum(1 for r in batch_rows if r.get("submission_state") == "CONFIRMED_SENT")
    confirmation_reached = sum(1 for r in batch_rows if r.get("submission_state") == "CONFIRMATION_REACHED")
    failed = sum(1 for r in batch_rows if r.get("submission_state") == "FAILED" and _bool(r.get("attempted")))
    unknown = sum(1 for r in batch_rows if r.get("submission_state") == "UNKNOWN" and _bool(r.get("attempted")))
    manual = sum(1 for r in batch_rows if r.get("submission_state") == "MANUAL_INTERVENTION_REQUIRED")
    skipped = sum(1 for r in batch_rows if r.get("submission_state") == "SKIPPED" or not _bool(r.get("attempted")))
    runtime_div = sum(
        1 for r in batch_rows
        if (r.get("pre_send_skip_reason") or r.get("reason") or "") == "RUNTIME_DIVERGENCE"
    )
    false_sent = sum(
        1 for r in batch_rows
        if r.get("status") == "sent" and r.get("submission_state") != "CONFIRMED_SENT"
    )

    msg_v1 = sum(1 for r in batch_rows if "V1" in (r.get("message_variant") or ""))
    msg_compact = sum(1 for r in batch_rows if "COMPACT" in (r.get("message_variant") or ""))
    maxlength_skip = sum(1 for r in batch_rows if "maxlength" in (r.get("pre_send_skip_reason") or "").lower())

    captcha = sum(1 for r in batch_rows if "captcha" in (r.get("pre_send_skip_reason") or "").lower())
    form_unsuitable = sum(1 for r in batch_rows if "form_not_suitable" in (r.get("pre_send_skip_reason") or "").lower())

    # Preflight / funnel from JSON reports
    preflight_candidate = 0
    auto_ready = 0
    full_preflight = 0
    lightweight = 0
    for rep in json_reports:
        if "preflight_results" in rep:
            full_preflight += len(rep.get("preflight_results") or [])
            for pr in rep.get("preflight_results") or []:
                if pr.get("classification") == "AUTO_READY":
                    auto_ready += 1
        if "batch_a_dry" in rep:
            full_preflight += len(rep.get("batch_a_dry") or [])
            auto_ready += sum(1 for x in rep.get("batch_a_dry") or [] if x.get("preflight_classification") == "AUTO_READY")
        tr = rep.get("tonight_batch_b") or rep.get("total") or {}
        if tr:
            confirmed = max(confirmed, tr.get("confirmed_sent", confirmed))

    pool_path = OUTPUT_DIR / "ARI-Candidate-Pool-2026-08-12-500.json"
    source_candidates = 0
    if pool_path.exists():
        pool = json.loads(pool_path.read_text(encoding="utf-8"))
        source_candidates = pool.get("stats", {}).get("source_total", 0)

    official_confirmed_total = count_official_confirmed_sent()
    raw_sent_rows = count_raw_sent_rows()

    quality = {
        "confirmed_sent_rate": round(confirmed / attempted * 100, 1) if attempted else 0.0,
        "auto_ready_rate": round(auto_ready / full_preflight * 100, 1) if full_preflight else 0.0,
        "captcha_rate": round(captcha / max(len(batch_rows), 1) * 100, 1),
        "form_not_suitable_rate": round(form_unsuitable / max(len(batch_rows), 1) * 100, 1),
        "unknown_rate": round(unknown / attempted * 100, 1) if attempted else 0.0,
        "failed_rate": round(failed / attempted * 100, 1) if attempted else 0.0,
        "false_sent_count": false_sent,
        "duplicate_anomaly_count": runtime_div,
    }

    return {
        "date": for_date,
        "generated_at": datetime.now().isoformat(),
        "candidate_funnel": {
            "source_candidates": source_candidates,
            "lightweight_scanned": lightweight,
            "likely_auto_ready": 0,
            "preflight_candidate": preflight_candidate,
            "full_preflight": full_preflight,
            "auto_ready": auto_ready,
        },
        "production": {
            "attempted": attempted,
            "final_submit_clicked": final_submit,
            "confirmed_sent": confirmed,
            "confirmation_reached": confirmation_reached,
            "failed": failed,
            "unknown": unknown,
            "manual_intervention": manual,
            "skipped": skipped,
            "runtime_divergence": runtime_div,
        },
        "quality": quality,
        "message": {
            "ARI_MESSAGE_V1": msg_v1,
            "ARI_MESSAGE_COMPACT": msg_compact,
            "maxlength_skips": maxlength_skip,
        },
        "official_kpi": {
            "confirmed_sent_today_batch_logs": confirmed,
            "official_confirmed_sent_total_deduped": official_confirmed_total,
            "raw_sent_csv_rows": raw_sent_rows,
            "note": "Use official_confirmed_sent_total_deduped — NOT raw_sent_csv_rows",
        },
        "form_type_breakdown": {},
        "batch_log_rows": len(batch_rows),
    }


def write_daily_kpi(for_date: str = "2026-08-11") -> tuple[Path, Path]:
    kpi = aggregate_daily_kpi(for_date)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / f"ari_daily_kpi_{for_date}.json"
    md_path = OUTPUT_DIR / f"ARI Daily KPI {for_date}.md"
    json_path.write_text(json.dumps(kpi, ensure_ascii=False, indent=2), encoding="utf-8")

    pf = kpi["production"]
    q = kpi["quality"]
    lines = [
        f"# ARI Daily KPI {for_date}",
        "",
        f"Generated: {kpi['generated_at']}",
        "",
        "## Official KPI",
        "",
        f"- **CONFIRMED_SENT (deduped total):** {kpi['official_kpi']['official_confirmed_sent_total_deduped']}",
        f"- Raw sent.csv rows: {kpi['official_kpi']['raw_sent_csv_rows']} (NOT official KPI)",
        "",
        "## Production",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Attempted | {pf['attempted']} |",
        f"| Confirmed Sent | {pf['confirmed_sent']} |",
        f"| Confirmation Reached | {pf['confirmation_reached']} |",
        f"| Failed | {pf['failed']} |",
        f"| Unknown | {pf['unknown']} |",
        f"| Skipped | {pf['skipped']} |",
        f"| Runtime Divergence | {pf['runtime_divergence']} |",
        "",
        "## Quality",
        "",
        f"- Confirmed/Attempted: {q['confirmed_sent_rate']}%",
        f"- UNKNOWN rate: {q['unknown_rate']}%",
        f"- false SENT: {q['false_sent_count']}",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path
