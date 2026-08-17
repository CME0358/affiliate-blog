#!/usr/bin/env python3
"""
run_controlled_pilot_generic.py — Generic scan + 100-contact pilot cohort (ZERO SEND).

Usage:
  python3 run_controlled_pilot_generic.py --pre-scan-only
  python3 run_controlled_pilot_generic.py --full
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_BASE = Path(__file__).resolve().parent
VAULT_ROOT = _BASE.parents[2]
OUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"
LOG_DIR = _BASE / "logs"
SCAN_LIMIT = 120
CANARY_SIZE = 10
COHORT_SIZE = 100
PILOT_NS = "controlled_pilot_v1"
PRODUCTION_DOMAIN = "readiness.coaretail.com"

sys.path.insert(0, str(_BASE))

_env = _BASE / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8-sig").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)

import types

if "dotenv" not in sys.modules:
    _dotenv = types.ModuleType("dotenv")
    _dotenv.load_dotenv = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    sys.modules["dotenv"] = _dotenv

os.environ.setdefault("LP_URL_OVERRIDE", "https://readiness.coaretail.com/report/")
os.environ.setdefault("PREVIEW_STORE_BACKEND", "upstash")
os.environ.setdefault("GENERIC_SCAN_STORE_BACKEND", "upstash")

from message_builder import build_preview_record
from observations.generic_scanner import has_safe_observation, is_scan_success, scan_domain
from observations.generic_scan_store import save_generic_scan
from observations.preview_snapshot_store import PreviewStoreError, load_snapshot
from observations.resolver import select_message_observations
from shared_form_prepare import SEMANTIC_EVIDENCE_SCHEMA_VERSION

_spec = importlib.util.spec_from_file_location("ab_tracking", _BASE / "ari_pipeline/ab_tracking.py")
_ab = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_ab)
encode_ab_notes = _ab.encode_ab_notes

READY_JSON = OUT_DIR / "ARI-Night-Factory-READY-2026-08-14.json"
INVENTORY_JSON = OUT_DIR / "ARI-Production-Ready-Inventory-2026-08-14.json"

PRE_SCAN_DOMAINS = [
    "hiiragi-law-office.jp",
    "graz-inc.jp",
    "44juku.com",
    "yokos-gym.jp",
    "welina-marriage.com",
    "yorozu-auto.com",
    "oide-acc.org",
    "iseya-nursery.co.jp",
]


def _domain(url: str) -> str:
    try:
        h = urlparse((url or "").strip()).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def load_unconsumed_ready(limit: int | None = None) -> list[dict[str, Any]]:
    ready = json.loads(READY_JSON.read_text(encoding="utf-8"))
    rows = [r for r in ready.get("ready_primary", []) if not r.get("consumed_by_production")]
    if limit is not None:
        return rows[:limit]
    return rows


def _company_from_ready(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": rec.get("candidate_id") or "",
        "company_name": rec.get("company_name") or "",
        "website_url": rec.get("website_url") or "",
        "industry_name": rec.get("industry_name") or "",
        "area_name": rec.get("area_name") or "",
        "domain": (rec.get("domain") or _domain(rec.get("website_url") or "")).lower(),
    }


def verify_production_preview(token: str) -> tuple[bool, str]:
    if not token:
        return False, "missing_token"
    for label, path in (("api", f"/api/preview/{token}"), ("page", f"/report/p/{token}")):
        url = f"https://{PRODUCTION_DOMAIN}{path}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ARI-Pilot-Generic/1.0"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                if resp.status != 200:
                    return False, f"{label}_http_{resp.status}"
        except urllib.error.HTTPError as e:
            return False, f"{label}_http_{e.code}"
        except Exception as e:
            return False, f"{label}_error:{e}"
    return True, ""


def run_pre_scan() -> dict[str, Any]:
    ready_by_dom = {r["domain"]: r for r in json.loads(READY_JSON.read_text())["ready_primary"]}
    results = []
    for dom in PRE_SCAN_DOMAINS:
        rec = ready_by_dom.get(dom)
        if not rec:
            results.append({"domain": dom, "error": "not_in_ready"})
            continue
        company = _company_from_ready(rec)
        row = scan_domain(
            website_url=company["website_url"],
            domain=company["domain"],
            industry_name=company["industry_name"],
        )
        obs = select_message_observations(row)
        booking_codes = [o["code"] for o in obs if "BOOKING" in o["code"]]
        results.append({
            "domain": dom,
            "industry": company["industry_name"],
            "reachable": is_scan_success(row),
            "obs_eligible": has_safe_observation(row),
            "observation_codes": [o["code"] for o in obs],
            "booking_semantics_leak": booking_codes,
            "not_found_copy_ok": all(
                "見つけられませんでした" in (o.get("approved_copy") or "")
                or "確認できませんでした" in (o.get("approved_copy") or "")
                or "確認しました" in (o.get("approved_copy") or "")
                or "可能性があります" in (o.get("approved_copy") or "")
                for o in obs
            ),
        })

    reachable = sum(1 for r in results if r.get("reachable"))
    obs_eligible = sum(1 for r in results if r.get("obs_eligible"))
    leaks = sum(1 for r in results if r.get("booking_semantics_leak"))
    passed = reachable >= 5 and obs_eligible >= 5 and leaks == 0
    return {
        "passed": passed,
        "sample_scanned": len(PRE_SCAN_DOMAINS),
        "reachable": reachable,
        "obs_eligible": obs_eligible,
        "booking_leaks": leaks,
        "results": results,
    }


def run_controlled_scan_and_cohort(*, persist: bool) -> dict[str, Any]:
    targets = load_unconsumed_ready(SCAN_LIMIT)
    stats = Counter()
    obs_code_counter: Counter = Counter()
    cohort_rows: list[dict[str, Any]] = []
    allocation_ts = datetime.now(timezone.utc).isoformat()

    for rec in targets:
        company = _company_from_ready(rec)
        dom = company["domain"]
        base = {
            "domain": dom,
            "company_name": company["company_name"],
            "candidate_id": company["candidate_id"],
            "industry_name": company["industry_name"],
            "prep_status": "EXCLUDED",
            "exclude_reason": "",
            "cohort_role": "",
            "cohort_rank": "",
            "preview_token": "",
            "preview_url": "",
            "message_variant": "",
            "observation_codes": "",
        }
        stats["scanned"] += 1

        row = scan_domain(
            website_url=company["website_url"],
            domain=dom,
            industry_name=company["industry_name"],
        )
        if persist:
            save_generic_scan(row)

        if not is_scan_success(row):
            base["exclude_reason"] = row.get("scan_error") or "site_unreachable"
            stats["unreachable"] += 1
            cohort_rows.append(base)
            continue
        stats["reachable"] += 1

        if not has_safe_observation(row):
            base["exclude_reason"] = "no_safe_observation"
            stats["no_observation"] += 1
            cohort_rows.append(base)
            continue
        stats["observation_eligible"] += 1
        for o in select_message_observations(row):
            obs_code_counter[o["code"]] += 1

        try:
            preview = build_preview_record(
                company,
                ab_arm="C",
                dry_run_snapshot=not persist,
                crawler_data=row,
            )
        except Exception as e:
            base["exclude_reason"] = f"preview_generation_failure:{e}"
            stats["preview_failures"] += 1
            cohort_rows.append(base)
            continue

        if preview.get("fallback") or preview.get("message_version") != "ARI_MESSAGE_V2":
            base["exclude_reason"] = preview.get("fallback_reason") or "v1_fallback"
            stats["v1_fallback"] += 1
            cohort_rows.append(base)
            continue

        token = preview.get("preview_token") or ""
        if persist:
            if not load_snapshot(token):
                base["exclude_reason"] = "snapshot_persist_failure"
                stats["persist_failures"] += 1
                cohort_rows.append(base)
                continue
            ok, reason = verify_production_preview(token)
            if not ok:
                base["exclude_reason"] = f"production_preview_failed:{reason}"
                stats["preview_api_failures"] += 1
                cohort_rows.append(base)
                continue
            stats["preview_api_verified"] += 1
        stats["snapshot_persisted"] += 1 if persist else 0

        obs_codes = "|".join((o.get("code") or "") for o in (preview.get("observations") or []))
        obs_copies = " | ".join(
            (o.get("approved_copy") or "") for o in (preview.get("observations") or [])
        )
        base.update({
            "prep_status": "SEND_ELIGIBLE",
            "exclude_reason": "",
            "message_variant": "ARI_MESSAGE_V2",
            "preview_token": token,
            "preview_url": preview.get("preview_url") or "",
            "observation_codes": obs_codes,
            "observation_copy": obs_copies,
            "rendered_message": preview.get("rendered_message") or "",
            "notes": encode_ab_notes(
                ab_arm="C",
                message_version="ARI_MESSAGE_V2",
                preview_token=token,
                preview_created_at=(load_snapshot(token) or {}).get("created_at", "") if persist else "",
                extra={"pilot_namespace": PILOT_NS, "evidence_source": "generic_scan", "confirmed_sent": False},
            ),
        })
        stats["send_eligible"] += 1
        cohort_rows.append(base)

    eligible = [r for r in cohort_rows if r["prep_status"] == "SEND_ELIGIBLE"]
    for i, row in enumerate(eligible[:COHORT_SIZE]):
        row["cohort_rank"] = str(i + 1)
        row["cohort_role"] = "CANARY" if i < CANARY_SIZE else "RESERVE"
        row["cohort_allocation_timestamp"] = allocation_ts

    canary = eligible[:CANARY_SIZE]
    reserve = eligible[CANARY_SIZE:COHORT_SIZE]

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    csv_path = LOG_DIR / f"controlled_pilot_cohort_generic_{date}.csv"
    json_path = OUT_DIR / f"Controlled-Pilot-Cohort-Generic-{date}.json"
    review_path = OUT_DIR / f"Canary-10-Message-Review-{date}.md"

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fields = list(cohort_rows[0].keys()) if cohort_rows else []
    if fields:
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(cohort_rows)

    artifact = {
        "generated_at": allocation_ts,
        "pilot_namespace": PILOT_NS,
        "scan_limit": SCAN_LIMIT,
        "source_read_only": {
            "ready": str(READY_JSON),
            "inventory": str(INVENTORY_JSON),
        },
        "stats": dict(stats),
        "observation_distribution": dict(obs_code_counter),
        "send_eligible": len(eligible),
        "canary_fixed": len(canary),
        "reserve_fixed": len(reserve),
        "pilot_100_ready": len(eligible) >= COHORT_SIZE,
        "canary_ready": len(canary) >= CANARY_SIZE,
        "csv_path": str(csv_path),
        "safety": {"real_sends": 0, "final_submit": 0, "production_send": 0},
    }
    json_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    review_lines = [
        "# Canary 10 — Message Review (Generic Preview)",
        "",
        f"- Generated: {allocation_ts}",
        f"- Pilot namespace: `{PILOT_NS}`",
        "- **NO SEND EXECUTED**",
        "",
    ]
    for i, row in enumerate(canary, 1):
        review_lines.extend([
            f"## {i}. {row['company_name']}",
            "",
            f"- domain: `{row['domain']}`",
            f"- industry: {row.get('industry_name', '')}",
            f"- observations: `{row.get('observation_codes', '')}`",
            f"- approved copy: {row.get('observation_copy', '')}",
            f"- preview URL: {row.get('preview_url', '')}",
            "",
            "### Rendered ARI_MESSAGE_V2",
            "",
            "```text",
            row.get("rendered_message") or "",
            "```",
            "",
        ])

    review_path.write_text("\n".join(review_lines), encoding="utf-8")

    return {
        **artifact,
        "review_path": str(review_path),
        "gate": (
            "READY FOR HUMAN REVIEW OF CANARY 10"
            if len(eligible) >= COHORT_SIZE
            else "INSUFFICIENT ELIGIBLE AFTER 120 SCAN"
        ),
        "additional_scan_estimate": max(0, int((COHORT_SIZE - len(eligible)) * 1.15)) if len(eligible) < COHORT_SIZE else 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre-scan-only", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="Scan without Upstash persist")
    args = ap.parse_args()

    pre = run_pre_scan()
    print(json.dumps({"phase": "pre_scan", **pre}, ensure_ascii=False, indent=2))
    if not pre["passed"]:
        print("PRE-SCAN FAILED — aborting 120 scan", file=sys.stderr)
        return 1

    if args.pre_scan_only:
        return 0

    if not args.full:
        print("Pre-scan PASS. Re-run with --full to execute 120 scan.", file=sys.stderr)
        return 0

    result = run_controlled_scan_and_cohort(persist=not args.dry_run)
    print(json.dumps({"phase": "controlled_scan", **result}, ensure_ascii=False, indent=2))
    return 0 if result.get("pilot_100_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
