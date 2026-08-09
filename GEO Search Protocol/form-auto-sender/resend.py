#!/usr/bin/env python3
"""
resend.py — sent.csv の全件に改善版文面で再送信する（main.py / retry_errors.py とは独立）

実行例:
    python resend.py --dry-run   # 対象件数のみ確認
    python resend.py             # 本番再送

仕様:
    - logs/sent.csv の全行を対象（RESEND_INTERVAL_DAYS は無視）
    - form_url が記録されていればそれを使用、なければ form_finder で探索
    - 結果は logs/resend_YYYY-MM-DD.csv に記録（sent.csv は更新しない）
    - 送信成功時のみ random.uniform(2, 4) 秒待機
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import random
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config import LOG_DIR, LOG_SENT, SEND_INTERVAL_MAX, SEND_INTERVAL_MIN
from form_finder import find_form_url
from form_sender import send_form
from message_builder import build_message
from url_builder import build_lp_url
from log_manager import is_permanently_skipped, vault_today
from company_infer import enrich_company_metadata

_RESEND_HEADERS = [
    "date",
    "company_name",
    "industry_name",
    "area_name",
    "form_url",
    "lp_url",
    "status",
]


def _resend_log_path() -> Path:
    return LOG_DIR / f"resend_{vault_today().isoformat()}.csv"


def _ensure_resend_log(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=_RESEND_HEADERS).writeheader()


def append_resend_log(
    path: Path,
    *,
    company_name: str,
    industry_name: str,
    area_name: str,
    form_url: str,
    lp_url: str,
    status: str,
) -> None:
    _ensure_resend_log(path)
    with path.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=_RESEND_HEADERS).writerow(
            {
                "date": vault_today().isoformat(),
                "company_name": company_name,
                "industry_name": industry_name,
                "area_name": area_name,
                "form_url": form_url,
                "lp_url": lp_url,
                "status": status,
            }
        )


def load_resend_already_sent(log_path: Path) -> set[str]:
    """当日 resend ログで status=sent の会社名（再送スキップ用）。"""
    if not log_path.exists():
        return set()
    done: set[str] = set()
    with log_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return done
        for row in reader:
            if (row.get("status") or "").strip() == "sent":
                name = (row.get("company_name") or "").strip()
                if name:
                    done.add(name)
    return done


def load_sent_rows(*, empty_industry_only: bool = False) -> list[dict]:
    """sent.csv のデータ行を返す。empty_industry_only 時は業種未記録行のみ。"""
    if not LOG_SENT.exists():
        return []

    rows: list[dict] = []
    with LOG_SENT.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        for row in reader:
            name = (row.get("company_name") or "").strip()
            if not name:
                continue
            if empty_industry_only and (row.get("industry_name") or "").strip():
                continue
            rows.append(row)
    return rows


def row_to_company(row: dict) -> dict:
    return {
        "company_name": (row.get("company_name") or "").strip(),
        "industry_name": (row.get("industry_name") or "").strip(),
        "area_name": (row.get("area_name") or "").strip(),
        "website_url": (row.get("website_url") or "").strip() or None,
        "form_url": (row.get("form_url") or "").strip(),
        "lp_url": (row.get("lp_url") or "").strip(),
        "phone": None,
        "address": None,
        "place_id": (row.get("place_id") or "").strip() or None,
        "rating": 0.0,
        "review_count": 0,
        "date": (row.get("date") or "").strip(),
    }


async def process_one(
    company: dict,
    log_path: Path,
    already_sent: set[str] | None = None,
) -> str:
    """
    1件再送。戻り値: sent | error | skipped
    """
    enrich_company_metadata(company)
    name = company["company_name"]
    industry_name = company["industry_name"]
    area_name = company["area_name"]

    if already_sent and name in already_sent:
        return "skipped"

    in_perm, perm_reason = is_permanently_skipped(company)
    if in_perm:
        append_resend_log(
            log_path,
            company_name=name,
            industry_name=industry_name,
            area_name=area_name,
            form_url="",
            lp_url="",
            status=f"skipped:permanent({perm_reason})",
        )
        return "skipped"

    website = (company.get("website_url") or "").strip()
    if not website:
        append_resend_log(
            log_path,
            company_name=name,
            industry_name=industry_name,
            area_name=area_name,
            form_url="",
            lp_url="",
            status="skipped",
        )
        return "skipped"

    lp_url = build_lp_url(industry_name, area_name)
    message = build_message(industry_name, name, lp_url, area_name=area_name)

    form_url = (company.get("form_url") or "").strip()
    if form_url:
        company["form_url"] = form_url
        form_result = {"status": "found", "form_url": form_url, "reason": ""}
    else:
        form_result = await find_form_url(website, company_name=name)

    if form_result["status"] == "pending":
        append_resend_log(
            log_path,
            company_name=name,
            industry_name=industry_name,
            area_name=area_name,
            form_url=form_result.get("form_url", ""),
            lp_url=lp_url,
            status="pending",
        )
        return "error"

    if form_result["status"] != "found":
        append_resend_log(
            log_path,
            company_name=name,
            industry_name=industry_name,
            area_name=area_name,
            form_url="",
            lp_url=lp_url,
            status=f"error:{form_result.get('reason', 'form_not_found')}",
        )
        return "error"

    company["form_url"] = form_result["form_url"]
    fu = company.get("form_url")
    if not fu or not str(fu).strip():
        append_resend_log(
            log_path,
            company_name=name,
            industry_name=industry_name,
            area_name=area_name,
            form_url="",
            lp_url=lp_url,
            status="error:form_url_is_none",
        )
        return "error"

    result = await send_form(company, message, lp_url)
    status = result.get("status", "error")
    reason = result.get("reason", "")

    if status == "sent":
        log_status = "sent"
    elif status == "pending":
        log_status = f"pending:{reason}" if reason else "pending"
    else:
        log_status = f"error:{reason}" if reason else "error"

    append_resend_log(
        log_path,
        company_name=name,
        industry_name=industry_name,
        area_name=area_name,
        form_url=company["form_url"],
        lp_url=lp_url,
        status=log_status,
    )

    if status == "sent":
        await asyncio.sleep(random.uniform(SEND_INTERVAL_MIN, SEND_INTERVAL_MAX))
        return "sent"

    return "error"


DEFAULT_RESEND_LIMIT = 50


async def run_resend(
    dry_run: bool = False,
    empty_industry_only: bool = False,
    resume: bool = True,
    limit: int = DEFAULT_RESEND_LIMIT,
) -> tuple[dict[str, int], str]:
    rows = load_sent_rows(empty_industry_only=empty_industry_only)
    companies = [row_to_company(r) for r in rows]
    if limit > 0:
        companies = companies[:limit]
    log_path = _resend_log_path()
    already_sent: set[str] = load_resend_already_sent(log_path) if resume else set()
    total = len(companies)
    target_label = (
        "業種未記録のみ"
        if empty_industry_only
        else "全件"
    )

    print(f"\n{'='*60}")
    print(f"  再送スクリプト {'[DRY-RUN]' if dry_run else '[本番]'}")
    print(f"  対象: logs/sent.csv {target_label} {total} 件（RESEND_INTERVAL_DAYS 無視）")
    print(f"  業種・エリア未記録行は会社名から補完")
    if resume and already_sent:
        print(f"  再送ログ sent 済みスキップ: {len(already_sent)} 件")
    from config import LP_URL_OVERRIDE
    if (LP_URL_OVERRIDE or "").strip():
        print(f"  LP URL 固定: {(LP_URL_OVERRIDE or '').strip()}")
    print(f"{'='*60}\n")

    if dry_run:
        with_form = sum(1 for c in companies if (c.get("form_url") or "").strip())
        with_site = sum(1 for c in companies if (c.get("website_url") or "").strip())
        todo = sum(1 for c in companies if c["company_name"] not in already_sent)
        print(f"  website_url あり: {with_site} 件")
        print(f"  form_url 記録済み: {with_form} 件")
        print(f"  form_url 未記録（探索が必要）: {with_site - with_form} 件")
        print(f"  今回の送信対象（sent済み除く）: {todo} 件")
        print(f"\n  DRY-RUN: 送信は行いません。対象 {total} 件\n")
        summary = f"再送完了: 送信0件 / エラー0件 / スキップ0件（DRY-RUN 対象{total}件）"
        return {"sent": 0, "error": 0, "skipped": 0, "dry_run": total}, summary

    _ensure_resend_log(log_path)
    print(f"  ログ出力先: {log_path}\n")

    counts: dict[str, int] = {"sent": 0, "error": 0, "skipped": 0}
    initial_resend_done = set(already_sent)

    for idx, company in enumerate(companies, start=1):
        name = company["company_name"]
        t0 = time.perf_counter()
        try:
            outcome = await process_one(company, log_path, already_sent=already_sent)
        except Exception as e:
            elapsed = time.perf_counter() - t0
            append_resend_log(
                log_path,
                company_name=name,
                industry_name=company.get("industry_name", ""),
                area_name=company.get("area_name", ""),
                form_url=company.get("form_url", ""),
                lp_url=build_lp_url(company.get("industry_name", ""), company.get("area_name", "")),
                status=f"error:{e!r}",
            )
            counts["error"] += 1
            print(f"[{idx:02d}/{total:02d}] {name} - ERROR: {e!r} ({elapsed:.1f}秒)")
            continue

        elapsed = time.perf_counter() - t0
        if outcome == "skipped" and name in initial_resend_done:
            label = "SKIP（再送済み）"
        elif outcome == "skipped":
            label = "SKIP"
        else:
            label = {"sent": "SENT", "error": "ERROR"}.get(outcome, outcome.upper())
        print(f"[{idx:02d}/{total:02d}] {name} - {label} ({elapsed:.1f}秒)")

        if outcome == "sent":
            counts["sent"] += 1
            already_sent.add(name)
        elif outcome == "skipped":
            counts["skipped"] += 1
        else:
            counts["error"] += 1

    summary = (
        f"再送完了: 送信{counts['sent']}件 / "
        f"エラー{counts['error']}件 / "
        f"スキップ{counts['skipped']}件"
    )
    return counts, summary


def main() -> None:
    ap = argparse.ArgumentParser(
        description="sent.csv 全件に改善版文面で再送信（main.py 独立）",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="送信せず対象件数のみ表示",
    )
    ap.add_argument(
        "--empty-industry-only",
        action="store_true",
        help="sent.csv の industry_name が空の行のみ再送（既定: 全件）",
    )
    ap.add_argument(
        "--no-resume",
        action="store_true",
        help="当日 resend ログの sent 済みも再送する（既定: sent 済みはスキップ）",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_RESEND_LIMIT,
        help=f"最大送信件数（既定: {DEFAULT_RESEND_LIMIT}。0=無制限は不可）",
    )
    ap.add_argument(
        "--yes",
        action="store_true",
        help="本番実行前の確認プロンプトをスキップ",
    )
    args = ap.parse_args()

    if args.limit < 1:
        print("エラー: --limit は 1 以上を指定してください（無制限再送は禁止）")
        sys.exit(1)

    if not args.dry_run and not args.yes:
        answer = input(
            f"本番再送を最大 {args.limit} 件実行します。続行しますか? [y/N] "
        ).strip().lower()
        if answer not in ("y", "yes"):
            print("中止しました。")
            sys.exit(0)

    _, summary = asyncio.run(
        run_resend(
            dry_run=args.dry_run,
            empty_industry_only=args.empty_industry_only,
            resume=not args.no_resume,
            limit=args.limit,
        )
    )
    print(summary)


if __name__ == "__main__":
    main()
