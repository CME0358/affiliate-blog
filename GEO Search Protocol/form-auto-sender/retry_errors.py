#!/usr/bin/env python3
"""
retry_errors.py — error.csv の指定日付分のみを再処理する（main.py とは独立）

例:
    python retry_errors.py --date 2026-05-13

送信済み判定:
    logs/sent.csv（存在する場合）および logs/.sent_index.csv を参照し、
    記録済みの企業はスキップする（main が実際に書き込むのは .sent_index.csv）。
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import random
import sys
import time
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config import LOG_DIR, LOG_ERROR, LOG_SENT, SEND_INTERVAL_MAX, SEND_INTERVAL_MIN
from form_finder import find_form_url
from form_sender import send_form
from message_builder import build_message
from url_builder import build_lp_url
from list_filter import get_config_exclusion_label
from log_manager import (
    is_in_failure_cooldown,
    is_permanently_skipped,
    log_result,
    sync_permanent_skip,
)

_SENT_INDEX = LOG_DIR / ".sent_index.csv"


def _error_row_date(row: dict) -> str:
    """error.csv の日付列（logged_date または date）。"""
    return (row.get("logged_date") or row.get("date") or "").strip()


def load_error_rows_for_date(filter_date: str) -> list[dict]:
    """指定 ISO 日付の error.csv 行のみ返す（ヘッダー行は除外）。"""
    if not LOG_ERROR.exists():
        return []

    rows: list[dict] = []
    with LOG_ERROR.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        for row in reader:
            if _error_row_date(row) == filter_date:
                rows.append(row)
    return rows


def row_to_company(row: dict, fallback_date: str) -> dict | None:
    name = (row.get("company_name") or "").strip()
    if not name:
        return None
    return {
        "company_name": name,
        "industry_name": (row.get("industry_name") or "").strip(),
        "area_name": (row.get("area_name") or "").strip(),
        "website_url": (row.get("website_url") or "").strip() or None,
        "phone": (row.get("phone") or "").strip() or None,
        "address": (row.get("address") or "").strip() or None,
        "place_id": (row.get("place_id") or "").strip() or None,
        "rating": 0.0,
        "review_count": 0,
        "date": _error_row_date(row) or fallback_date,
    }


def _strip_url(u: str) -> str:
    return u.strip().rstrip("/")


def load_sent_records(paths: list[Path]) -> list[tuple[str, str]]:
    """各ファイルから (company_name, website_url) のリストを読む。"""
    out: list[tuple[str, str]] = []
    for path in paths:
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    continue
                for row in reader:
                    cn = (row.get("company_name") or "").strip()
                    wu = (row.get("website_url") or "").strip()
                    if cn:
                        out.append((cn, wu))
        except OSError:
            continue
    return out


def is_recorded_sent(company: dict, sent_records: list[tuple[str, str]]) -> bool:
    """
    sent.csv / .sent_index と同等の緩い一致で送信済みとみなす（日付による締め切りなし）。
    """
    name = company["company_name"]
    url = (company.get("website_url") or "").strip()
    nu = _strip_url(url) if url else ""

    for row_name, row_url in sent_records:
        if row_name == name:
            return True
        if nu and row_url:
            rv = _strip_url(row_url)
            if nu == rv or nu in rv or rv in nu:
                return True
    return False


class RetryLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = path.open("a", encoding="utf-8")

    def log(self, message: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {message}\n"
        self._fp.write(line)
        self._fp.flush()

    def close(self) -> None:
        self._fp.close()


def _emit_progress(
    idx: int,
    total: int,
    name: str,
    status: str,
    logger: RetryLogger,
) -> None:
    line = f"[{idx}/{total}] {name} - {status}"
    print(line, flush=True)
    logger.log(line)


async def process_one(
    company: dict,
    sent_records: list[tuple[str, str]],
    force_retry: bool = False,
) -> tuple[str, str]:
    """
    Returns (outcome, progress_suffix).
    outcome: 'sent' | 'error' | 'skipped' | 'pending'
    progress_suffix: SENT / ERROR: reason / SKIP: ... / PENDING: ...
    """
    name = company["company_name"]

    exclusion = get_config_exclusion_label(company)
    if exclusion:
        return "skipped", f"SKIP（{exclusion}）"

    if is_recorded_sent(company, sent_records):
        return "skipped", "SKIP（送信済み）"

    if not force_retry:
        in_perm, _perm_reason = is_permanently_skipped(company)
        if in_perm:
            return "skipped", "SKIP（永続除外）"

        in_cd, cd_msg = is_in_failure_cooldown(company)
        if in_cd:
            return "skipped", f"SKIP（失敗クールダウン）: {cd_msg}"

    form_result = await find_form_url(
        company["website_url"],
        company_name=name,
    )
    lp_url = build_lp_url(company["industry_name"], company["area_name"])
    message = build_message(
        company["industry_name"],
        company["company_name"],
        lp_url,
        area_name=company.get("area_name", ""),
    )

    if form_result["status"] == "pending":
        log_result(
            "pending",
            company,
            {
                "reason": form_result["reason"],
                "form_url": form_result.get("form_url", ""),
                "lp_url": lp_url,
                "message": message,
            },
        )
        return "pending", "PENDING（reCAPTCHA）"

    if form_result["status"] != "found":
        reason = form_result.get("reason") or "form_not_found"
        log_result(form_result["status"], company, {"detail": reason})
        return "error", f"ERROR: {reason}"

    company["form_url"] = form_result["form_url"]
    fu = company.get("form_url")
    if not fu or not str(fu).strip():
        log_result("error", company, {"detail": "form_url_is_none"})
        return "error", "ERROR: form_url_is_none"

    result = await send_form(company, message, lp_url)
    log_result(result["status"], company, {**result, "message": message})

    if result["status"] == "sent":
        await asyncio.sleep(random.uniform(SEND_INTERVAL_MIN, SEND_INTERVAL_MAX))
        return "sent", "SENT"

    if result["status"] == "pending":
        reason = result.get("reason") or "pending"
        return "pending", f"PENDING: {reason}"

    reason = result.get("reason") or "send_failed"
    return "error", f"ERROR: {reason}"


async def run_retry(
    filter_date: str,
    log_file: Path | None = None,
    force_retry: bool = False,
) -> tuple[dict[str, int], str]:
    sync_permanent_skip()
    print()

    sent_records = load_sent_records([LOG_SENT, _SENT_INDEX])
    rows = load_error_rows_for_date(filter_date)

    log_path = log_file or (LOG_DIR / f"retry_{filter_date}.log")
    logger = RetryLogger(log_path)
    logger.log(f"=== retry_errors start filter_date={filter_date} rows={len(rows)} log_file={log_path} ===")

    counts: dict[str, int] = {"sent": 0, "error": 0, "skipped": 0, "excluded": 0}

    if not rows:
        logger.log("対象行なし（error.csv に指定日のレコードがありません）")
        logger.close()
        empty_summary = (
            f"再実行完了: 送信{counts['sent']}件 / "
            f"エラー{counts['error']}件 / "
            f"スキップ{counts['skipped']}件（除外{counts['excluded']}件含む）"
        )
        return counts, empty_summary

    companies: list[dict] = []
    for row in rows:
        c = row_to_company(row, fallback_date=filter_date)
        if c:
            companies.append(c)

    total = len(companies)

    for idx, company in enumerate(companies, start=1):
        name = company["company_name"]
        _emit_progress(idx, total, name, "処理中...", logger)
        t0 = time.perf_counter()
        try:
            outcome, result_label = await process_one(
                company,
                sent_records,
                force_retry=force_retry,
            )
        except Exception as e:
            elapsed = time.perf_counter() - t0
            _emit_progress(idx, total, name, f"ERROR: {e!r} ({elapsed:.1f}秒)", logger)
            counts["error"] += 1
            continue

        elapsed = time.perf_counter() - t0
        _emit_progress(idx, total, name, f"{result_label} ({elapsed:.1f}秒)", logger)

        if outcome == "sent":
            counts["sent"] += 1
            sent_records.append(
                (company["company_name"], (company.get("website_url") or "").strip())
            )
        elif outcome == "skipped":
            counts["skipped"] += 1
            if "業種除外" in result_label or "エリア除外" in result_label:
                counts["excluded"] += 1
        else:
            counts["error"] += 1

    summary = (
        f"再実行完了: 送信{counts['sent']}件 / "
        f"エラー{counts['error']}件 / "
        f"スキップ{counts['skipped']}件（除外{counts['excluded']}件含む）"
    )
    logger.log(summary)
    logger.log("=== retry_errors end ===")
    logger.close()

    return counts, summary


def main() -> None:
    ap = argparse.ArgumentParser(
        description="error.csv の指定日付分のみを再処理する（main.py 独立）",
    )
    ap.add_argument(
        "--date",
        required=True,
        metavar="YYYY-MM-DD",
        help="error.csv の logged_date（または date）がこの日付の行だけ対象",
    )
    ap.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="ログ出力先を指定（既定: logs/retry_<フィルタ日付>.log）",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="失敗クールダウンを無視して再処理する",
    )
    args = ap.parse_args()

    filter_date = args.date.strip()
    try:
        date.fromisoformat(filter_date)
    except ValueError:
        print(f"無効な日付です: {filter_date}（YYYY-MM-DD で指定してください）", file=sys.stderr)
        sys.exit(1)

    log_path = args.log_file
    if log_path is None:
        log_path = LOG_DIR / f"retry_{filter_date}.log"

    _, summary = asyncio.run(run_retry(filter_date, log_file=log_path, force_retry=args.force))

    print(summary)


if __name__ == "__main__":
    main()
