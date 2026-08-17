"""
ari_pipeline/forensic_queue.py — Manual review queue (NOT auto-retry).
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from config import LOG_DIR, VAULT_ROOT
from log_manager import get_effective_sent_status
from submission_state import normalize_effective_status

OUTPUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"
FORENSIC_JSON = OUTPUT_DIR / "ari_forensic_review_queue.json"
FORENSIC_CSV = LOG_DIR / "ari_forensic_review_queue.csv"

KNOWN_CASES = [
    {
        "company_name": "株式会社第一住設 東京営業所",
        "domain": "daiichi-jyusetu.co.jp",
        "issue": "RUNTIME_DIVERGENCE",
        "notes": "preflight vs production mapping hash mismatch",
        "batch": "EOD Batch B 2026-08-11",
    },
    {
        "company_name": "㈱ミゾイホーム",
        "domain": "mizoihome.com",
        "issue": "CONFIRMATION_REACHED",
        "notes": "final submit clicked; no completion evidence",
        "batch": "EOD Batch B 2026-08-11",
    },
    {
        "company_name": "建築のスマイルサービス",
        "domain": "smile0033.com",
        "issue": "UNKNOWN",
        "notes": "final submit clicked; same-URL no completion evidence",
        "batch": "EOD Batch B 2026-08-11",
    },
    {
        "company_name": "高部孝之税理士事務所",
        "domain": "",
        "issue": "UNKNOWN",
        "notes": "Jimdo / UNKNOWN — manual review",
        "batch": "prior_batch",
    },
]

BATCH_A_FORENSIC = [
    {"company_name": "㈱丸巧(まるこう)", "domain": "maru-kou.jp", "issue": "FAILED", "notes": "CF7 validation_failed"},
    {"company_name": "アオイリフォーム足立店 ㈱工房彩美", "domain": "aoi-reform.com", "issue": "FAILED", "notes": "CF7 validation_failed"},
    {"company_name": "㈱大和工務店", "domain": "yamato-2013.co.jp", "issue": "UNKNOWN", "notes": "final_click_no_completion_evidence"},
    {"company_name": "㈲毛利工務店（一級建築士事務所）", "domain": "space-m.net", "issue": "UNKNOWN", "notes": "final_click_no_completion_evidence"},
]


def build_forensic_queue() -> dict:
    items: list[dict] = []
    seen: set[str] = set()

    def _add(entry: dict) -> None:
        key = entry.get("domain") or entry.get("company_name", "")
        if key in seen:
            return
        seen.add(key)
        eff = ""
        if entry.get("domain"):
            eff = normalize_effective_status(
                get_effective_sent_status(entry.get("company_name", ""), f"https://{entry['domain']}/")
            )
        items.append({
            **entry,
            "queue_type": "FORENSIC_REVIEW",
            "auto_retry": False,
            "requires_manual_decision": True,
            "effective_status": eff or "not_sent",
            "queued_at": datetime.now().isoformat(),
        })

    for k in KNOWN_CASES + BATCH_A_FORENSIC:
        _add(k)

    # Scan batch logs for UNKNOWN / CONFIRMATION_REACHED / RUNTIME_DIVERGENCE
    for p in LOG_DIR.glob("ari_*.csv"):
        with p.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                st = row.get("submission_state") or row.get("pre_send_skip_reason") or ""
                if st in ("UNKNOWN", "CONFIRMATION_REACHED", "RUNTIME_DIVERGENCE", "SKIPPED") and "RUNTIME" in (row.get("pre_send_skip_reason") or ""):
                    issue = row.get("pre_send_skip_reason") or st
                elif st in ("UNKNOWN", "CONFIRMATION_REACHED"):
                    issue = st
                else:
                    continue
                _add({
                    "company_name": row.get("company", ""),
                    "domain": row.get("domain", ""),
                    "issue": issue,
                    "notes": row.get("notes") or row.get("pre_send_skip_reason") or "",
                    "batch": row.get("batch", ""),
                    "source_log": p.name,
                })

    return {
        "generated_at": datetime.now().isoformat(),
        "count": len(items),
        "policy": "NO automatic retry from forensic queue",
        "items": items,
    }


def write_forensic_queue() -> tuple[Path, Path]:
    data = build_forensic_queue()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    FORENSIC_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    headers = ["company_name", "domain", "issue", "effective_status", "notes", "batch", "auto_retry"]
    with FORENSIC_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        for item in data["items"]:
            w.writerow({**item, "auto_retry": False})

    return FORENSIC_JSON, FORENSIC_CSV
