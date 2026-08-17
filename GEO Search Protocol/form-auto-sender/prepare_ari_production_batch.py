#!/usr/bin/env python3
"""
prepare_ari_production_batch.py — 本番30件バッチの選定・検出・事前判定（送信なし）

Usage:
  python3 prepare_ari_production_batch.py [--detect-limit 60] [--target 30]
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))

from config import LP_URL_OVERRIDE, VAULT_ROOT, LOG_DIR
from form_detector import detect_form_only
from list_filter import apply_list_filter, get_config_exclusion_label
from log_manager import is_already_sent
from message_variant import (
    build_ari_message_compact,
    build_ari_message_v1,
    detect_message_field_maxlength,
    select_ari_message_variant,
)
from parser import parse_md_file
from form_field_resolver import resolve_form_fields
from form_finder import NAV_TIMEOUT, _goto_settled

OUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"
BATCH_MD = OUT_DIR / "ARI-Production-Batch-30.md"
PREP_CSV = LOG_DIR / "ari_production_prep_2026-08-10.csv"
PREP_REPORT = OUT_DIR / "ARI Production Batch Preparation.md"

SOURCE_FILES = [
    "40_Sales/商談メモ/リスト/2026-08-09_リフォーム・リノベーション_東京都台東区.md",
    "40_Sales/商談メモ/リスト/2026-08-09_外壁塗装・屋根工事_東京都台東区.md",
    "40_Sales/商談メモ/リスト/2026-08-09_弁護士事務所_東京都台東区.md",
    "40_Sales/商談メモ/リスト/2026-08-09_税理士・会計士_東京都台東区.md",
    "40_Sales/商談メモ/リスト/2026-08-09_ネイルサロン_東京都台東区.md",
    "40_Sales/商談メモ/リスト/2026-08-09_エステサロン_東京都台東区.md",
    "40_Sales/商談メモ/リスト/2026-08-06_リフォーム・リノベーション_東京都足立区.md",
    "40_Sales/商談メモ/リスト/2026-08-06_外壁塗装・屋根工事_東京都足立区.md",
    "40_Sales/商談メモ/リスト/2026-08-06_弁護士事務所_東京都足立区.md",
    "40_Sales/商談メモ/リスト/2026-08-06_税理士・会計士_東京都足立区.md",
    "40_Sales/商談メモ/リスト/2026-08-07_ハウスクリーニング・エアコン清掃_東京都足立区.md",
    "40_Sales/商談メモ/リスト/2026-08-07_引越し業者・単身引越し_東京都足立区.md",
    "40_Sales/商談メモ/リスト/2026-08-07_遺品整理・相続手続き代行_東京都足立区.md",
    "40_Sales/商談メモ/リスト/2026-08-07_プログラミングスクール_東京都足立区.md",
]

NOT_SUITABLE_NAMES = frozenset({
    "上野御徒町内科クリニック",
    "東京ビジネスクリニック エキュート上野",
    "協和医院",
    "あさくさ田原町内科クリニック",
    "御徒町おひさま内科",
    "Hard Rock Cafe Uyeno-Eki Tokyo",
    "HALIMA KEBAB BIRYANI",
    "T'sたんたん エキュート上野店",
    "Cafe&Rotisserie LA COCORICO 上野本店",
    "牛の達人 浅草店",
    "つばめグリル アトレ上野店",
    "千賀デンタルクリニック 上野マルイ医院",
    "マルイ錦糸町シティデンタルクリニック",
    "浅草橋クリアデンタルオフィス",
    "エクシアデンタルクリニック墨田",
    "エクシアホワイトニング東上野店",
    "RINX（リンクス）東京上野店",
    "株式会社レイリーチ",
    "MEN'S TBC 上野店",
    "一心",
    "東京豚バザール",
})

EXECUTABLE_FORM_TYPES = frozenset({
    "FORM_FOUND",
    "MULTI_STEP",
})

SKIP_FORM_TYPES = frozenset({
    "CAPTCHA",  # 2captcha 無効のため本番自動送信対象外
    "EXTERNAL_FORM",
    "CONTACT_PAGE_ONLY",
    "BLOCKED",
    "NO_FORM",
    "ERROR",
})


def _domain(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def _load_sent_domains() -> set[str]:
    domains: set[str] = set()
    idx = LOG_DIR / ".sent_index.csv"
    if not idx.exists():
        return domains
    import csv as csvm
    with idx.open(encoding="utf-8") as f:
        for row in csvm.DictReader(f):
            d = _domain(row.get("website_url", ""))
            if d:
                domains.add(d)
    return domains


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", (name or ""))


def load_candidate_pool() -> list[dict]:
    pool: list[dict] = []
    seen_names: set[str] = set()
    seen_domains: set[str] = set()
    sent_domains = _load_sent_domains()

    for rel in SOURCE_FILES:
        path = VAULT_ROOT / rel
        if not path.exists():
            continue
        for c in parse_md_file(str(path)):
            name = c.get("company_name", "").strip()
            url = (c.get("website_url") or "").strip()
            if not name or not url:
                continue
            norm = _normalize_name(name)
            dom = _domain(url)
            if norm in seen_names or (dom and dom in seen_domains):
                continue
            if any(ns in name or name in ns for ns in NOT_SUITABLE_NAMES):
                continue
            if is_already_sent(name, url):
                continue
            if dom and dom in sent_domains:
                continue
            if get_config_exclusion_label(c):
                continue
            seen_names.add(norm)
            if dom:
                seen_domains.add(dom)
            pool.append(c)

    pool = apply_list_filter(pool, source_label="ari_production_prep")
    return pool


PRIORITY_NAMES = (
    "株式会社坊",
    "山田工務店",
    "YUKUIDO",
    "ゆくい堂",
    "kurachiffon",
    "株式会社ブラスト",
    "星和リフォーム",
    "ケイズインテリア",
    "㈱ネクスト",
    "リノベ不動産",
    "税理士",
    "弁護士",
)


def _score_company(c: dict) -> tuple[int, int]:
    """Higher is better."""
    name = c.get("company_name", "")
    industry = c.get("industry_name", "")
    priority = 0
    if any(p in name for p in PRIORITY_NAMES):
        priority = 110
    elif "リフォーム" in industry:
        priority = 100
    elif "外壁塗装" in industry:
        priority = 90
    elif "弁護士" in industry or "税理士" in industry:
        priority = 85
    elif "ハウスクリーニング" in industry or "引越し" in industry or "遺品整理" in industry:
        priority = 80
    elif "ネイル" in industry or "エステ" in industry:
        priority = 70
    elif "プログラミング" in industry:
        priority = 65
    reviews = int(c.get("review_count") or 0)
    return priority, reviews


async def probe_maxlength_and_variant(form_url: str, lp_url: str) -> dict:
    out = {
        "detected_maxlength": None,
        "message_variant": "ARI_MESSAGE_V1",
        "message_length": len(build_ari_message_v1(lp_url)),
        "fallback_reason": "",
        "prep_skip_reason": "",
    }
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        out["prep_skip_reason"] = "playwright_not_installed"
        return out

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(locale="ja-JP")
        try:
            if not await _goto_settled(page, form_url, goto_timeout=NAV_TIMEOUT):
                return out
            html = await page.content()
            fields, _ = await resolve_form_fields(page, html, form_url)
            if not fields:
                return out
            ml = await detect_message_field_maxlength(page, fields)
            sel = select_ari_message_variant(lp_url, ml)
            out["detected_maxlength"] = ml
            out["message_variant"] = sel.variant
            out["message_length"] = sel.message_length
            out["fallback_reason"] = sel.fallback_reason or ""
            if sel.skipped:
                out["prep_skip_reason"] = sel.skip_reason or "compact_message_exceeds_maxlength"
        finally:
            await browser.close()
    return out


async def run_detection_pipeline(pool: list[dict], detect_limit: int, target: int) -> list[dict]:
    ranked = sorted(pool, key=_score_company, reverse=True)
    results: list[dict] = []
    lp_url = LP_URL_OVERRIDE

    for i, company in enumerate(ranked[:detect_limit], 1):
        name = company["company_name"]
        print(f"[{i}/{min(detect_limit, len(ranked))}] detect: {name}")
        det = await detect_form_only(company)
        ft = det.get("form_type", "ERROR")
        row = {
            **company,
            "form_type": ft,
            "form_url_detected": det.get("form_url") or "",
            "confidence": det.get("confidence", "LOW"),
            "captcha": det.get("captcha", False),
            "field_map": det.get("field_map", {}),
            "failure_reason": det.get("failure_reason", ""),
            "domain": _domain(company.get("website_url", "")),
            "executable": False,
            "prep_status": "REJECTED",
        }

        fm = row["field_map"]
        has_core = fm.get("email") == "FOUND" and fm.get("message") == "FOUND"

        if ft in EXECUTABLE_FORM_TYPES and has_core and not det.get("captcha"):
            row["executable"] = True
            row["prep_status"] = "CANDIDATE"
            if row["form_url_detected"]:
                company["form_url"] = row["form_url_detected"]
                probe = await probe_maxlength_and_variant(row["form_url_detected"], lp_url)
                row.update(probe)
                if probe.get("prep_skip_reason"):
                    row["executable"] = False
                    row["prep_status"] = "SKIP_MAXLENGTH"
        elif ft == "CAPTCHA":
            row["prep_status"] = "SKIP_CAPTCHA"
        elif ft in SKIP_FORM_TYPES:
            row["prep_status"] = f"SKIP_{ft}"

        results.append(row)

        selected = sum(1 for r in results if r.get("executable"))
        if selected >= target:
            break

    return results


def write_batch_md(selected: list[dict]) -> None:
    lines = [
        "# ARI Production Batch 30",
        "",
        "- 作成日: 2026-08-10",
        "- Tier: 業種2 / エリア1",
        f"- 件数: {len(selected)}（本番送信対象・15:00 JST）",
        "- Batch 1: 1–10 / Batch 2: 11–30",
        "",
        "## 選定サマリー",
        "",
        "| # | Company | Domain | Industry | Form URL | message_variant | maxlength |",
        "| ---: | --- | --- | --- | --- | --- | ---: |",
    ]
    for i, r in enumerate(selected, 1):
        ml = r.get("detected_maxlength")
        ml_s = str(ml) if ml is not None else "—"
        lines.append(
            f"| {i} | {r['company_name']} | {r.get('domain','')} | {r.get('industry_name','')} "
            f"| {r.get('form_url_detected','')} | {r.get('message_variant','')} | {ml_s} |"
        )
    lines.append("")
    lines.append("## 企業一覧")
    lines.append("")

    for i, r in enumerate(selected, 1):
        rc = r.get("review_count", 0)
        rating = r.get("rating", 0)
        lines.append(
            f"- **{r['company_name']}**（★{rating} / {rc}件 / Webあり）"
        )
        lines.append(f"  - 業種: {r.get('industry_name', '')}")
        if r.get("address"):
            lines.append(f"  - 住所: {r['address']}")
        lines.append(f"  - Web: {r.get('website_url', '')}")
        if r.get("phone"):
            lines.append(f"  - 電話: {r['phone']}")
        if r.get("place_id"):
            lines.append(f"  - placeId: {r['place_id']}")
        if r.get("form_url_detected"):
            lines.append(f"  - フォームURL: {r['form_url_detected']}")
        lines.append(f"  - message_variant: {r.get('message_variant', '')}")
        if r.get("detected_maxlength") is not None:
            lines.append(f"  - detected_maxlength: {r['detected_maxlength']}")
        lines.append(f"  - 選定理由: production_prep / batch_{1 if i <= 10 else 2}")
        lines.append("")

    BATCH_MD.parent.mkdir(parents=True, exist_ok=True)
    BATCH_MD.write_text("\n".join(lines), encoding="utf-8")


def write_prep_csv(all_results: list[dict]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "company_name", "domain", "industry_name", "website_url", "form_url_detected",
        "form_type", "confidence", "executable", "prep_status",
        "message_variant", "message_length", "detected_maxlength", "fallback_reason", "prep_skip_reason",
    ]
    with PREP_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in all_results:
            w.writerow(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detect-limit", type=int, default=55)
    ap.add_argument("--target", type=int, default=30)
    args = ap.parse_args()

    print("=== ARI Production Batch Preparation (NO SUBMIT) ===")
    pool = load_candidate_pool()
    print(f"Candidate pool after filters: {len(pool)}")

    results = asyncio.run(run_detection_pipeline(pool, args.detect_limit, args.target))
    write_prep_csv(results)

    selected = [r for r in results if r.get("executable")][: args.target]
    print(f"\nSelected executable: {len(selected)} / target {args.target}")

    if len(selected) < args.target:
        print(f"⚠️  WARNING: only {len(selected)} executable forms found", file=sys.stderr)

    write_batch_md(selected)

    v1 = len([r for r in selected if r.get("message_variant") == "ARI_MESSAGE_V1"])
    compact = len([r for r in selected if r.get("message_variant") == "ARI_MESSAGE_COMPACT"])

    report = f"""# ARI Production Batch Preparation

- **準備日時**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S JST")}
- **実送信**: 0
- **automation paused**: true（15:00 直前に resume 予定）
- **実行予定**: 2026-08-10 15:00 JST

## Selection

| 指標 | 値 |
| --- | ---: |
| Pool | {len(pool)} |
| Detected | {len(results)} |
| Selected | {len(selected)} |
| V1 variant | {v1} |
| Compact variant | {compact} |

## Files

- Batch list: `{BATCH_MD.relative_to(VAULT_ROOT)}`
- Prep CSV: `{PREP_CSV.relative_to(_BASE)}`
- Run script: `scripts/run_ari_production_batch.py`
- Scheduler: `scripts/run_ari_production_1500.sh`

## 15:00 Command

```bash
cd "10_Projects/GEO Search Protocol/form-auto-sender"
./scripts/run_ari_production_1500.sh
```
"""
    PREP_REPORT.write_text(report, encoding="utf-8")
    print(f"Wrote {BATCH_MD}")
    print(f"Wrote {PREP_REPORT}")
    return 0 if len(selected) >= args.target else 1


if __name__ == "__main__":
    raise SystemExit(main())
