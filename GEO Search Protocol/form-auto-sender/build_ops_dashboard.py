#!/usr/bin/env python3
"""
Vault 70_outputs/運用ダッシュボード.html を form-auto-sender のログ・リストから再生成する。

指標の定義:
  - リスト獲得数: config.INPUT_DIR 配下の *.md を parser.parse_md_list で読んだ企業数（合算）
  - 本日送信試行数: 当日 logs/YYYY-MM-DD.md の ✅ + ⚠️ + ❌ セクション内の ### 件数の合計
  - 本日成功数: 当日 MD の ✅ 送信済みの ### 件数
  - 本日手動確認: 当日 MD の ⚠️ reCAPTCHA の ### 件数
  - 本日エラー（ログ）: 当日 MD の ❌ の ### 件数
  - error.csv 累計: DictReader で行数（複数行フィールド対応）
  - 累計成功送信: .sent_index.csv のデータ行数
  - 本日の暦日・生成時刻: 日本時間（Asia/Tokyo）基準

使い方:
  cd "$(dirname "$0")"
  python3 build_ops_dashboard.py

launchd で 1 時間ごとに実行する例は launchd/com.coaretail.ops-dashboard.plist を参照。
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

# form-auto-sender を cwd にして import
_BASE = Path(__file__).resolve().parent
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

from config import INPUT_DIR, LOG_DIR, LOG_ERROR, VAULT_ROOT  # noqa: E402
from automation_registry import AUTO_CATEGORIES, AUTOMATION_JOBS  # noqa: E402
from automation_state import build_runtime_snapshot  # noqa: E402
from log_manager import get_stats  # noqa: E402
from fitness_dashboard_metrics import build_fitness_section_html  # noqa: E402
from ari_insights_dashboard_metrics import build_ari_section_html  # noqa: E402
from parser import parse_md_list  # noqa: E402

_SENT_INDEX = LOG_DIR / ".sent_index.csv"
TEMPLATE = _BASE / "templates" / "ops_dashboard.html"
EXPO_SECTION = _BASE / "templates" / "ops_dashboard_expo_section.html"
OUTPUT_HTML = VAULT_ROOT / "70_outputs" / "運用ダッシュボード.html"
_VAULT_TZ = ZoneInfo("Asia/Tokyo")
_METRICS_BEGIN = "<!-- OPS_DASHBOARD_METRICS_BEGIN -->"
_METRICS_END = "<!-- OPS_DASHBOARD_METRICS_END -->"
_EXPO_BEGIN = "<!-- OPS_DASHBOARD_EXPO_BEGIN -->"
_EXPO_END = "<!-- OPS_DASHBOARD_EXPO_END -->"
_FITNESS_BEGIN = "<!-- OPS_DASHBOARD_FITNESS_BEGIN -->"
_FITNESS_END = "<!-- OPS_DASHBOARD_FITNESS_END -->"
_ARI_BEGIN = "<!-- OPS_DASHBOARD_ARI_BEGIN -->"
_ARI_END = "<!-- OPS_DASHBOARD_ARI_END -->"
_DENTAL_BEGIN = "<!-- OPS_DASHBOARD_DENTAL_BEGIN -->"
_DENTAL_END = "<!-- OPS_DASHBOARD_DENTAL_END -->"
_FOOTER_TS_RE = re.compile(r"(数値の最終生成:\s*<strong>)[^<]*(</strong>)")


def _reason_key(reason: str) -> str:
    r = (reason or "").strip()
    if not r:
        return "(空)"
    first = r.split("\n")[0].strip()
    return first[:120] if len(first) > 120 else first


def count_csv_dict_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return 0
        return sum(1 for _ in reader)


def error_csv_top_reasons(path: Path, n: int = 2) -> list[tuple[str, int]]:
    if not path.exists():
        return []
    c: Counter[str] = Counter()
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            c[_reason_key(row.get("reason", ""))] += 1
    return c.most_common(n)


def count_list_companies() -> int:
    if not INPUT_DIR.exists():
        return 0
    try:
        return len(parse_md_list(str(INPUT_DIR)))
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] リスト集計スキップ: {e}", file=sys.stderr)
        return 0


def build_automation_runtime_json() -> str:
    return json.dumps(build_runtime_snapshot(), ensure_ascii=False)


def build_automation_items_json() -> str:
    items = []
    for job in AUTOMATION_JOBS:
        items.append(
            {
                "id": job.id,
                "category": job.category,
                "name": job.name,
                "launchd": job.launchd,
                "schedule": job.schedule,
                "detail": job.detail,
                "path": job.path,
                "defaultOn": job.default_on,
                "status": job.status,
                "alert": job.alert,
            }
        )
    return json.dumps(items, ensure_ascii=False)


def build_automation_categories_json() -> str:
    return json.dumps(AUTO_CATEGORIES, ensure_ascii=False)


def escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_metrics_inner(
    *,
    today: date,
    generated: datetime,
    list_count: int,
    stats: dict,
    err_csv_total: int,
    sent_total: int,
    top2: list[tuple[str, int]],
) -> str:
    sent, pending, err_md = stats["sent"], stats["pending"], stats["error"]
    attempts = sent + pending + err_md

    def kpi(label: str, value: str | int, note: str = "") -> str:
        note_html = f'<div class="note">{note}</div>' if note else ""
        return (
            f'<div class="kpi"><div class="label">{escape_html(label)}</div>'
            f'<div class="value">{escape_html(str(value))}</div>{note_html}</div>'
        )

    rows = [
        kpi("リスト獲得数", list_count, "40_Sales/商談メモ/リスト の MD からパース"),
        kpi("本日送信試行数", attempts, "当日ログ内: 成功+手動確認+エラー"),
        kpi("本日成功数", sent, "logs/{0}.md の ✅ 送信済み".format(today.isoformat())),
        kpi("本日手動確認", pending, "reCAPTCHA 等・要人手"),
        kpi("本日エラー（ログ）", err_md, "当日 MD の ❌ セクション"),
        kpi("error.csv 累計", err_csv_total, "送信パイプラインで追記された失敗の累積"),
        kpi("累計成功送信", sent_total, ".sent_index.csv のデータ行数"),
    ]
    if err_csv_total == 0:
        rows.append(kpi("最多理由（累計）", "—", "error.csv に行がありません"))
        rows.append(kpi("次点理由（累計）", "—", "—"))
    else:
        r1_label, r1_n = top2[0]
        rows.append(kpi("最多理由（累計）", r1_n, f"<code>{escape_html(r1_label)}</code>"))
        if len(top2) > 1:
            r2_label, r2_n = top2[1]
            rows.append(kpi("次点理由（累計）", r2_n, f"<code>{escape_html(r2_label)}</code>"))
        else:
            rows.append(kpi("次点理由（累計）", "—", "理由は1種類のみ"))
    inner = '<div class="kpis">\n' + "\n".join(rows) + "\n</div>"
    sub = (
        f"生成: <strong>{generated.strftime('%Y-%m-%d %H:%M:%S')}</strong> · "
        f"本日ログ <code>logs/{today.isoformat()}.md</code> · "
        f"リスト <code>40_Sales/商談メモ/リスト</code>"
    )
    return (
        f'<p class="sub" style="margin:0 0 12px">{sub}</p>\n'
        f"{inner}\n"
        f'<p style="margin-top:14px;color:var(--muted);font-size:0.9rem">\n'
        f'ログ生データ：<span class="mono">10_Projects/GEO Search Protocol/form-auto-sender/logs/</span>\n'
        f" · <code>build_ops_dashboard.py</code> で更新（launchd 1時間ごと / form-auto-sender 日次実行後）\n"
        f"</p>"
    )


def load_expo_section_html() -> str:
    if not EXPO_SECTION.exists():
        print(f"[WARN] 展示会セクション未找到: {EXPO_SECTION}", file=sys.stderr)
        return ""
    return EXPO_SECTION.read_text(encoding="utf-8").strip()


def _patch_fitness_in_place(html: str, fitness_html: str) -> str:
    if not fitness_html:
        return html
    if _FITNESS_BEGIN in html and _FITNESS_END in html:
        start = html.index(_FITNESS_BEGIN) + len(_FITNESS_BEGIN)
        end = html.index(_FITNESS_END, start)
        return html[:start] + "\n" + fitness_html + "\n" + html[end:]
    if _DENTAL_BEGIN in html and _DENTAL_END in html:
        start = html.index(_DENTAL_BEGIN) + len(_DENTAL_BEGIN)
        end = html.index(_DENTAL_END, start)
        return html[:start] + "\n" + fitness_html + "\n" + html[end:]
    marker = "<!-- OPS_DASHBOARD_EXPO_BEGIN -->"
    if marker in html and 'id="fitness-crawler"' not in html:
        return html.replace(marker, fitness_html + "\n\n" + marker, 1)
    return html


def _patch_ari_in_place(html: str, ari_html: str) -> str:
    if not ari_html:
        return html
    if _ARI_BEGIN in html and _ARI_END in html:
        start = html.index(_ARI_BEGIN) + len(_ARI_BEGIN)
        end = html.index(_ARI_END, start)
        return html[:start] + "\n" + ari_html + "\n" + html[end:]
    marker = '    <div class="tab-content">'
    if marker in html and 'id="ari-daily"' not in html:
        return html.replace(
            marker,
            marker + "\n<!-- OPS_DASHBOARD_ARI_BEGIN -->\n" + ari_html + "\n<!-- OPS_DASHBOARD_ARI_END -->",
            1,
        )
    return html


def _patch_expo_in_place(html: str, expo_html: str) -> str:
    if not expo_html:
        return html
    if _EXPO_BEGIN in html and _EXPO_END in html:
        start = html.index(_EXPO_BEGIN) + len(_EXPO_BEGIN)
        end = html.index(_EXPO_END, start)
        return html[:start] + "\n" + expo_html + "\n" + html[end:]
    marker = '    <footer>'
    if marker in html and 'id="expo-match"' not in html:
        return html.replace(marker, expo_html + "\n\n" + marker, 1)
    return html


def _patch_metrics_in_place(html: str, metrics_html: str, ts: str) -> str | None:
    """既存 HTML の指標ブロックだけ差し替え。マーカーが無ければ None。"""
    if _METRICS_BEGIN not in html or _METRICS_END not in html:
        return None
    start = html.index(_METRICS_BEGIN) + len(_METRICS_BEGIN)
    end = html.index(_METRICS_END, start)
    out = html[:start] + "\n" + metrics_html + "\n" + html[end:]
    return _FOOTER_TS_RE.sub(rf"\g<1>{ts}\g<2>", out, count=1)


def _render_from_template(
    metrics_html: str,
    ts: str,
    runtime_json: str,
    items_json: str,
    cats_json: str,
    expo_html: str,
    fitness_html: str,
    ari_html: str,
) -> str:
    if not TEMPLATE.exists():
        print(f"[ERROR] テンプレートが見つかりません: {TEMPLATE}", file=sys.stderr)
        sys.exit(1)
    text = TEMPLATE.read_text(encoding="utf-8")
    if "__METRICS_BLOCK__" not in text:
        print("[ERROR] テンプレートに __METRICS_BLOCK__ がありません", file=sys.stderr)
        sys.exit(1)
    out = text.replace("__METRICS_BLOCK__", metrics_html, 1)
    out = out.replace("__EXPO_SECTION__", expo_html, 1)
    out = out.replace("__FITNESS_SECTION__", fitness_html, 1)
    out = out.replace("__ARI_SECTION__", ari_html, 1)
    out = out.replace("__FOOTER_UPDATED__", ts, 1)
    out = out.replace("__AUTOMATION_RUNTIME_JSON__", runtime_json, 1)
    out = out.replace("__AUTOMATION_ITEMS_JSON__", items_json, 1)
    return out.replace("__AUTOMATION_CATEGORIES_JSON__", cats_json, 1)


def _patch_automation_in_html(html: str, runtime_json: str, items_json: str, cats_json: str) -> str:
    html = _patch_runtime_in_html(html, runtime_json)
    for marker, val in (
        ("var AUTOMATION_ITEMS = ", items_json),
        ("var AUTO_CATEGORIES = ", cats_json),
    ):
        start = html.find(marker)
        if start < 0:
            continue
        val_start = start + len(marker)
        end = html.find(";", val_start)
        if end >= 0:
            html = html[:val_start] + val + html[end:]
    return html


def _patch_runtime_in_html(html: str, runtime_json: str) -> str:
    marker = "var AUTOMATION_RUNTIME = "
    start = html.find(marker)
    if start < 0:
        return html
    val_start = start + len(marker)
    end = html.find(";", val_start)
    if end < 0:
        return html
    return html[:val_start] + runtime_json + html[end:]


def main() -> None:
    now = datetime.now(_VAULT_TZ)
    today = now.date()
    generated = now
    ts = generated.strftime("%Y-%m-%d %H:%M:%S")
    stats = get_stats()
    list_count = count_list_companies()
    err_csv_total = count_csv_dict_rows(LOG_ERROR)
    sent_total = count_csv_dict_rows(_SENT_INDEX)
    top2 = error_csv_top_reasons(LOG_ERROR, 2)
    runtime_json = build_automation_runtime_json()
    items_json = build_automation_items_json()
    cats_json = build_automation_categories_json()

    metrics_html = build_metrics_inner(
        today=today,
        generated=generated,
        list_count=list_count,
        stats=stats,
        err_csv_total=err_csv_total,
        sent_total=sent_total,
        top2=top2,
    )
    expo_html = load_expo_section_html()
    fitness_html = build_fitness_section_html(VAULT_ROOT, today, ts)
    ari_html = build_ari_section_html(VAULT_ROOT, today, generated)

    if OUTPUT_HTML.exists():
        existing = OUTPUT_HTML.read_text(encoding="utf-8")
        has_automation_markers = (
            "var AUTOMATION_RUNTIME = " in existing
            and "var AUTOMATION_ITEMS = " in existing
            and "function automationCmd" in existing
            and 'localStorage.getItem("automation-' not in existing
        )
        needs_expo_restore = bool(expo_html) and 'id="expo-match"' not in existing
        needs_fitness_restore = 'id="fitness-crawler"' not in existing
        needs_ari_restore = 'id="ari-daily"' not in existing or "renderAriDaily" not in existing
        patched = _patch_metrics_in_place(existing, metrics_html, ts)
        if (
            patched is not None
            and has_automation_markers
            and not needs_expo_restore
            and not needs_fitness_restore
            and not needs_ari_restore
        ):
            patched = _patch_automation_in_html(patched, runtime_json, items_json, cats_json)
            patched = _patch_fitness_in_place(patched, fitness_html)
            patched = _patch_ari_in_place(patched, ari_html)
            patched = _patch_expo_in_place(patched, expo_html)
            OUTPUT_HTML.write_text(patched, encoding="utf-8")
            print(f"OK (patch): {OUTPUT_HTML}")
            _print_summary(list_count, stats, err_csv_total, sent_total)
            return
        if needs_expo_restore or needs_fitness_restore or needs_ari_restore:
            print("[INFO] セクション欠落のためテンプレートから全体再生成", file=sys.stderr)

    out = _render_from_template(
        metrics_html, ts, runtime_json, items_json, cats_json, expo_html, fitness_html, ari_html
    )
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(out, encoding="utf-8")
    print(f"OK (full): {OUTPUT_HTML}")
    _print_summary(list_count, stats, err_csv_total, sent_total)


def _print_summary(
    list_count: int, stats: dict, err_csv_total: int, sent_total: int
) -> None:
    print(
        f"  list={list_count} attempts_today={stats['sent']+stats['pending']+stats['error']} "
        f"sent={stats['sent']} pending={stats['pending']} err_md={stats['error']} "
        f"err_csv={err_csv_total} sent_total={sent_total}"
    )


if __name__ == "__main__":
    main()
