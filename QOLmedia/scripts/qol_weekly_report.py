#!/usr/bin/env python3
"""QOLmedia 週次レポート（運用ログ集計 + 任意GA4 Data API）。"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
QOLMEDIA = SCRIPT_DIR.parent
RAKUTEN = QOLMEDIA / "rakuten-affiliate" / "rakuten-x-affiliate"
REPORTS_DIR = QOLMEDIA / "reports"
KPI_LOG = QOLMEDIA / "QOLmedia_週次KPIログ.md"
GA4_ENV = SCRIPT_DIR / "ga4.env"

MEASUREMENT_ID = "G-BS30YQY1N7"
LP_PATHS = {
    "sleep": "/sleep-guide.html",
    "haircare": "/hc-guide.html",
    "focus": "/",
    "fatigue": "/",
    "stress": "/",
}
GA4_EVENTS = ("cta_click", "primary_article_click", "modal_open", "page_view")


from ga4_lib import fetch_ga4_metrics, format_ga4_section, load_dotenv, resolve_ga4_config


def week_monday(d: date | None = None) -> date:
    d = d or date.today()
    return d - timedelta(days=d.weekday())


def report_window(mode: str, mon: date, today: date | None = None) -> tuple[date, date]:
    """集計期間。月曜Planは先週分（18:30パイプライン前に0件になるのを防ぐ）。"""
    today = today or date.today()
    if mode == "mon":
        return mon - timedelta(days=7), mon - timedelta(days=1)
    if mode == "fri":
        return mon, mon + timedelta(days=4)
    return mon, min(mon + timedelta(days=6), today)


def week_label(mon: date) -> str:
    sun = mon + timedelta(days=6)
    return f"{mon.isoformat()}〜{sun.isoformat()}"


def tail_text(path: Path, n: int = 80) -> str:
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-n:])


def read_qol_uploads(since: date, until: date | None = None) -> list[dict[str, str]]:
    path = RAKUTEN / "qol_x_upload_log.csv"
    if not path.is_file():
        return []
    out: list[dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            raw = (row.get("生成日") or "").strip()
            if not raw:
                continue
            try:
                d = date.fromisoformat(raw[:10])
            except ValueError:
                continue
            if d < since:
                continue
            if until is not None and d > until:
                continue
            out.append(row)
    return out


def read_rakuten_queue_since(since: date) -> list[dict[str, str]]:
    path = RAKUTEN / "draft" / "queue.csv"
    if not path.is_file():
        return []
    out: list[dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = (row.get("生成日") or "").strip()
            if not raw:
                continue
            try:
                d = date.fromisoformat(raw[:10])
            except ValueError:
                continue
            if d >= since:
                out.append(row)
    return out


def launchd_errors() -> list[str]:
    log = RAKUTEN / "logs" / "launchd-daily.log"
    text = tail_text(log, 120)
    errs: list[str] = []
    for line in text.splitlines():
        if any(
            x in line
            for x in ("Error", "Traceback", "403", "ERR", "failed", "gaierror")
        ):
            errs.append(line.strip())
    return errs[-15:]


def load_qol_state() -> dict:
    path = RAKUTEN / "qol_x_state.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def suggest_do(
    rakuten_rows: list[dict[str, str]],
    qol_rows: list[dict[str, str]],
    errors: list[str],
) -> str:
    err_join = " ".join(errors)
    if "403" in err_join:
        return "楽天: 楽天WSでアクセスキー確認 → generate_daily.py 単体テスト"
    uploaded_rakuten = sum(
        1 for r in rakuten_rows if (r.get("status") or "").strip() == "uploaded"
    )
    if uploaded_rakuten == 0:
        return "楽天: queue.csv / launchd-daily.log を確認し run_daily.sh 手動1回"
    qol_ok = sum(1 for r in qol_rows if (r.get("status") or "").strip() == "uploaded")
    if qol_ok < 7 * 5:  # 5日×7ch 未満の粗い目安
        return "QOL Buffer: upload_qol_x_buffer.py --dry-run で7ch確認"
    return "コンディション: X CSV 1本差替 or プロフィール導線の見直し"


def fetch_qol_ga4_metrics(since: date, until: date) -> dict[str, object] | None:
    cfg = resolve_ga4_config(GA4_ENV)
    if not cfg:
        return None
    prop, _ = cfg
    try:
        return fetch_ga4_metrics(
            property_id=prop,
            since=since,
            until=until,
            hostnames=["www.qolmedia.info"],
            events=GA4_EVENTS,
            lp_paths=LP_PATHS,
        )
    except ImportError:
        return {"error": "pip install google-analytics-data google-auth（scripts/setup_weekly.sh）"}
    except Exception as exc:
        return {"error": str(exc)[:200]}


def ga4_console_hint() -> str:
    return (
        f"測定ID: `{MEASUREMENT_ID}` · "
        "[GA4 レポート](https://analytics.google.com/) → エンゲージメント → イベント\n"
        "確認: `cta_click` / `primary_article_click` / `modal_open` · "
        "LP: pet-lp / sleep-guide / factoring-lp / hc-guide"
    )


def build_report(mode: str, mon: date, today: date | None = None) -> str:
    today = today or date.today()
    since, until = report_window(mode, mon, today)
    qol = read_qol_uploads(since, until)
    rakuten = read_rakuten_queue_since(since)
    errors = launchd_errors()
    state = load_qol_state()
    do = suggest_do(rakuten, qol, errors)

    qol_by_ch = Counter((r.get("channel") or "?") for r in qol)
    qol_ok = sum(1 for r in qol if (r.get("status") or "").strip() == "uploaded")
    rakuten_uploaded = sum(
        1 for r in rakuten if (r.get("status") or "").strip() == "uploaded"
    )
    rakuten_err = sum(1 for r in rakuten if (r.get("status") or "").strip() == "error")

    lines = [
        f"# QOLmedia 週次レポート（{mode}）",
        "",
        f"- **対象週**: {week_label(mon)}",
        f"- **集計期間**: {since.isoformat()}〜{until.isoformat()}",
        f"- **生成**: {datetime.now().strftime('%Y-%m-%d %H:%M')} JST",
        "",
        "## サマリー",
        "",
        f"- QOL Buffer 投入（7日）: **{qol_ok}** 件（チャネル内訳: {dict(qol_by_ch)}）",
        f"- 楽天 queue uploaded: **{rakuten_uploaded}** / error **{rakuten_err}**",
        f"- **今週の推奨Do**: {do}",
        "",
        "## 日次パイプライン（18:30）",
        "",
    ]
    if errors:
        lines.append("直近ログの警告・エラー:")
        lines.append("```")
        lines.extend(errors)
        lines.append("```")
    else:
        lines.append("- `launchd-daily.log` に直近の致命エラーなし（要目視）")
    lines.extend(
        [
            "",
            "## QOL x7（Buffer）",
            "",
            f"- ローテ index: `{json.dumps(state.get('indices', {}), ensure_ascii=False)}`",
            f"- last_run: `{state.get('last_run_date', '—')}`",
            "",
        ]
    )
    if qol:
        lines.append("| 生成日 | channel | 予定 | buffer_id | status |")
        lines.append("| --- | --- | --- | --- | --- |")
        for r in qol[-12:]:
            lines.append(
                f"| {r.get('生成日','')} | {r.get('channel','')} | "
                f"{r.get('投稿予定日時','')} | {r.get('buffer_post_id','')[:12]}… | "
                f"{r.get('status','')} |"
            )
    else:
        lines.append("- 今週の `qol_x_upload_log.csv` 行なし")
    lines.extend(["", "## 楽天", ""])
    if rakuten:
        lines.append(
            f"- 今週の queue 行: {len(rakuten)}（uploaded {rakuten_uploaded} / error {rakuten_err}）"
        )
    else:
        lines.append("- 今週の `draft/queue.csv` 行なし（API403等で未生成の可能性）")

    lines.extend(["", "## GA4", ""])
    ga4 = fetch_qol_ga4_metrics(since, until)
    lines.extend(
        format_ga4_section(
            ga4,
            measurement_id=MEASUREMENT_ID,
            console_hint=ga4_console_hint(),
            env_hint=(
                "`scripts/ga4.env` に `GA4_PROPERTY_ID` と "
                "`GOOGLE_APPLICATION_CREDENTIALS` を設定後 `scripts/setup_weekly.sh`"
            ),
        )
    )

    lines.extend(
        [
            "",
            "## 手動入力（月曜）",
            "",
            "[[QOLmedia_週次KPIログ]] に追記:",
            "- ペット: 購入総額 / 報酬（マネートラック）",
            "- HC / ファクタ / 睡眠: A8承認額",
            "",
            "## 関連",
            "",
            "- [[QOLmedia_週次改善ループ]]",
            "- [[QOLmedia_戦略_キャッシュ×単価]]",
            "",
        ]
    )
    return "\n".join(lines)


def append_kpi_skeleton(mon: date, do: str, qol_ok: int, rakuten_ok: int) -> bool:
    """月曜のみ: 週行が無ければテーブルに1行追加。戻り値=追加したか。"""
    if not KPI_LOG.is_file():
        return False
    week_tag = mon.isoformat()
    text = KPI_LOG.read_text(encoding="utf-8")
    if f"| **{week_tag}**" in text or f"| {week_tag} " in text:
        return False
    row = (
        f"| **{week_tag}** | ※MT入力 | ※A8 | ※A8 | ※A8 | "
        f"{rakuten_ok}件upload | — | 自動:QOL{qol_ok}件 | {do[:40]}… |"
    )
    marker = "## ログ\n\n"
    if marker not in text:
        return False
    head, rest = text.split(marker, 1)
    # ヘッダ行の直後に挿入
    parts = rest.split("\n", 3)
    if len(parts) < 3:
        return False
    # parts[0]=header line1, parts[1]=separator, parts[2]=first data row...
    new_rest = parts[0] + "\n" + parts[1] + "\n" + row + "\n" + "\n".join(parts[2:])
    KPI_LOG.write_text(head + marker + new_rest, encoding="utf-8")
    return True


def notify(title: str, message: str) -> None:
    safe_t = title.replace('"', '\\"')
    safe_m = message.replace('"', '\\"')[:200]
    subprocess.run(
        [
            "osascript",
            "-e",
            f'display notification "{safe_m}" with title "{safe_t}"',
        ],
        check=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="QOLmedia 週次レポート")
    parser.add_argument(
        "--mode",
        choices=("mon", "fri", "auto"),
        default="auto",
        help="mon=月曜Plan / fri=金曜Check / auto=曜日判定",
    )
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("--no-kpi", action="store_true", help="KPIログへの行追加をスキップ")
    args = parser.parse_args()

    load_dotenv(GA4_ENV)
    load_dotenv(SCRIPT_DIR / ".env")

    today = date.today()
    mon = week_monday(today)
    wd = today.weekday()
    if args.mode == "auto":
        mode = "mon" if wd == 0 else "fri" if wd == 4 else "adhoc"
    else:
        mode = args.mode

    report = build_report(mode, mon, today)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"weekly_{mon.isoformat()}_{mode}.md"
    out.write_text(report, encoding="utf-8")
    # 週の最新版
    latest = REPORTS_DIR / f"weekly_{mon.isoformat()}_latest.md"
    latest.write_text(report, encoding="utf-8")

    since, until = report_window(mode, mon, today)
    qol = read_qol_uploads(since, until)
    rakuten = read_rakuten_queue_since(mon)
    do = suggest_do(rakuten, qol, launchd_errors())
    qol_ok = sum(1 for r in qol if (r.get("status") or "").strip() == "uploaded")
    rakuten_ok = sum(1 for r in rakuten if (r.get("status") or "").strip() == "uploaded")

    kpi_added = False
    if mode == "mon" and not args.no_kpi:
        kpi_added = append_kpi_skeleton(mon, do, qol_ok, rakuten_ok)

    print(f"[qol_weekly] mode={mode} report={out}")
    if kpi_added:
        print(f"[qol_weekly] KPI log row added: {KPI_LOG}")

    if not args.no_notify and mode in ("mon", "fri"):
        notify(
            "QOLmedia 週次",
            f"{'月曜Plan' if mode == 'mon' else '金曜Check'} レポート生成済",
        )


if __name__ == "__main__":
    main()
