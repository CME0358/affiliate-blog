"""運用ダッシュボード用 — パーソナルジム / フィットネスクローラー / ARI 指標。"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

TOKYO_23_WARDS: tuple[str, ...] = (
    "千代田区",
    "中央区",
    "港区",
    "新宿区",
    "文京区",
    "台東区",
    "墨田区",
    "江東区",
    "品川区",
    "目黒区",
    "大田区",
    "世田谷区",
    "渋谷区",
    "中野区",
    "杉並区",
    "豊島区",
    "北区",
    "荒川区",
    "板橋区",
    "練馬区",
    "足立区",
    "葛飾区",
    "江戸川区",
)

FITNESS_INDUSTRIES: tuple[str, ...] = (
    "パーソナルジム",
    "フィットネスクラブ",
    "ヨガスタジオ・ピラティス",
)

ARI_ITEMS: tuple[tuple[str, str], ...] = (
    ("FAQ", "よくある質問ページ・FAQPage スキーマ"),
    ("Schema.org", "構造化データ（JSON-LD）"),
    ("ReservationAction", "予約アクションのスキーマ"),
    ("LocalBusiness", "SportsActivityLocation / LocalBusiness 等"),
    ("SNSリンク", "Instagram / X / LINE 等"),
    ("GoogleMap埋め込み", "地図 iframe 埋め込み"),
    ("予約ボタン", "Web予約・体験予約CTA"),
)


@dataclass
class FitnessDashboardStats:
    start_date: str
    completed_count: int
    today_ward: str
    today_status: str
    total_facilities: int
    facilities_with_url: int
    reservation_detected: int
    ari_avg: float
    ari_count: int
    schedule_end: str
    last_run_ward: str
    last_run_at: str
    data_source: str


def crawler_root(vault_root: Path) -> Path:
    return vault_root / "40_Sales/営業自動化ツール/reservation_crawler"


def load_state(vault_root: Path) -> dict[str, Any]:
    path = crawler_root(vault_root) / "data/fitness_ward_schedule_state.json"
    if not path.exists():
        return {
            "start_date": "2026-07-10",
            "completed": {},
            "runs": [],
            "data_source": "https://fitsearch.jp/",
        }
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def ward_for_day_index(day_index: int) -> str | None:
    if 0 <= day_index < len(TOKYO_23_WARDS):
        return TOKYO_23_WARDS[day_index]
    return None


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _safe_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def collect_stats(vault_root: Path, today: date) -> FitnessDashboardStats:
    state = load_state(vault_root)
    start = date.fromisoformat(state.get("start_date", "2026-07-10"))
    completed: dict[str, str] = state.get("completed", {}) or {}
    runs: list[dict[str, str]] = state.get("runs", []) or []
    data_source = state.get("data_source", "https://fitsearch.jp/")

    day_index = (today - start).days
    today_ward = ward_for_day_index(day_index) or "—"
    completed_wards = set(completed.values())
    completed_count = len(completed_wards)

    if today_ward in completed_wards:
        today_status = "完了"
    elif day_index < 0:
        today_status = "開始前"
    elif day_index >= len(TOKYO_23_WARDS):
        today_status = "スケジュール終了"
    else:
        today_status = "18:00 予定"

    master = crawler_root(vault_root) / "data/fitness_master"
    list_rows = _read_csv_rows(master / "business_list_all.csv")
    reservation_rows = _read_csv_rows(master / "reservation_results_all.csv")
    ari_rows = _read_csv_rows(master / "agent_readiness_index_all.csv")

    url_col = "HP URL" if list_rows and "HP URL" in list_rows[0] else "url"
    total_facilities = len(list_rows)
    facilities_with_url = sum(1 for r in list_rows if (r.get(url_col) or "").strip())

    reservation_detected = sum(
        1 for r in reservation_rows if (r.get("reservation_system") or "").strip()
    )

    scores = [_safe_float(r.get("total_score", "")) for r in ari_rows if r.get("total_score")]
    ari_avg = sum(scores) / len(scores) if scores else 0.0

    last_run_ward = ""
    last_run_at = ""
    if runs:
        last = runs[-1]
        last_run_ward = last.get("ward", "")
        last_run_at = last.get("finished_at", "")

    schedule_end = (start + timedelta(days=len(TOKYO_23_WARDS) - 1)).isoformat()

    return FitnessDashboardStats(
        start_date=start.isoformat(),
        completed_count=completed_count,
        today_ward=today_ward,
        today_status=today_status,
        total_facilities=total_facilities,
        facilities_with_url=facilities_with_url,
        reservation_detected=reservation_detected,
        ari_avg=ari_avg,
        ari_count=len(scores),
        schedule_end=schedule_end,
        last_run_ward=last_run_ward,
        last_run_at=last_run_at,
        data_source=data_source,
    )


def escape_html(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_fitness_section_html(vault_root: Path, today: date, generated_ts: str) -> str:
    stats = collect_stats(vault_root, today)
    state = load_state(vault_root)
    start = date.fromisoformat(state.get("start_date", stats.start_date))
    completed: dict[str, str] = state.get("completed", {}) or {}
    industries_label = " / ".join(FITNESS_INDUSTRIES)

    def kpi(label: str, value: str | int, note: str = "") -> str:
        note_html = f'<div class="note">{escape_html(note)}</div>' if note else ""
        return (
            f'<div class="kpi"><div class="label">{escape_html(label)}</div>'
            f'<div class="value">{escape_html(str(value))}</div>{note_html}</div>'
        )

    kpis = "\n".join(
        [
            kpi("完了区数", f"{stats.completed_count}/23", f"{stats.start_date}〜{stats.schedule_end}"),
            kpi("本日の区", stats.today_ward, stats.today_status),
            kpi("累計施設", stats.total_facilities, f"HP URLあり {stats.facilities_with_url}"),
            kpi("ARI 平均", f"{stats.ari_avg:.1f}", f"{stats.ari_count}件・100点満点"),
            kpi("予約システム検出", stats.reservation_detected, "hacomono / RESERVA 等"),
            kpi(
                "次回実行",
                "18:00",
                "launchd · com.coaretail.reservation.daily_ward",
            ),
        ]
    )

    schedule_rows: list[str] = []
    for i, ward in enumerate(TOKYO_23_WARDS):
        run_date = (start + timedelta(days=i)).isoformat()
        if ward in completed.values():
            status = '<span class="badge badge--ok">完了</span>'
        elif run_date == today.isoformat():
            status = '<span class="badge badge--hi">本日</span>'
        elif date.fromisoformat(run_date) < today:
            status = '<span class="badge badge--mid">未実行</span>'
        else:
            status = '<span class="badge badge--low">予定</span>'
        schedule_rows.append(
            f"<tr><td>{escape_html(run_date)}</td>"
            f"<td>{escape_html(ward)}</td><td>{status}</td></tr>"
        )

    ari_rows = "".join(
        f"<tr><td>{escape_html(name)}</td><td>各20点</td><td>{escape_html(desc)}</td></tr>"
        for name, desc in ARI_ITEMS
    )

    last_run_note = ""
    if stats.last_run_ward:
        last_run_note = (
            f"直近完了: <strong>{escape_html(stats.last_run_ward)}</strong>"
            f"（{escape_html(stats.last_run_at)}）"
        )

    crawler_rel = "40_Sales/営業自動化ツール/reservation_crawler"

    return f"""<div id="fitness-crawler" class="kanban-card kanban-card--wide kanban-card--scroll">
      <h3>パーソナルジムクローラー · Agent Readiness Index</h3>
      <span class="section-tag" style="display:inline-block;margin-bottom:12px">23区 · 1日1区 · 18:00</span>
      <p class="expo-note">
        <strong>対象業種:</strong> {escape_html(industries_label)}。
        <strong>データソース:</strong> <a href="{escape_html(stats.data_source)}" target="_blank" rel="noopener">FIT Search</a>（fitsearch.jp）· Google Maps 不使用。
        毎日18:00に1区ずつフル診断（リスト取得 → 予約判定 → ARI診断）。
        生成: <strong>{escape_html(generated_ts)}</strong>
        · 開始 <strong>{escape_html(stats.start_date)}</strong>
        · 終了予定 <strong>{escape_html(stats.schedule_end)}</strong>
        {f" · {last_run_note}" if last_run_note else ""}
      </p>
      <div class="kpis" style="margin-bottom:20px">
{kpis}
      </div>
      <div class="card" style="margin-bottom:16px">
        <table>
          <thead>
            <tr><th>日付</th><th>区</th><th>状態</th></tr>
          </thead>
          <tbody>
{"".join(schedule_rows)}
          </tbody>
        </table>
      </div>
      <div class="sub-table">
        <h3>Agent Readiness Index 評価項目（100点満点）</h3>
        <div class="card" style="margin-bottom:16px">
          <table>
            <thead>
              <tr><th>項目</th><th>配点</th><th>判定内容</th></tr>
            </thead>
            <tbody>
{ari_rows}
            </tbody>
          </table>
        </div>
      </div>
      <div class="card">
        <table>
          <thead>
            <tr><th>ツール / 出力</th><th>パス</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>日次スケジューラ</td>
              <td><code>{escape_html(crawler_rel)}/daily_fitness_ward_diagnosis.py</code></td>
            </tr>
            <tr>
              <td>リスト取得（FIT Search）</td>
              <td><code>{escape_html(crawler_rel)}/fitsearch_client.py</code></td>
            </tr>
            <tr>
              <td>予約システム判定</td>
              <td><code>{escape_html(crawler_rel)}/detect_reservation_system.py</code></td>
            </tr>
            <tr>
              <td>ARI 診断</td>
              <td><code>{escape_html(crawler_rel)}/agent_readiness_index.py</code></td>
            </tr>
            <tr>
              <td>区別出力</td>
              <td><code>{escape_html(crawler_rel)}/output/fitness/YYYY-MM-DD_区名/</code></td>
            </tr>
            <tr>
              <td>全区統合 CSV</td>
              <td><code>{escape_html(crawler_rel)}/data/fitness_master/</code></td>
            </tr>
            <tr>
              <td>進捗 state</td>
              <td><code>{escape_html(crawler_rel)}/data/fitness_ward_schedule_state.json</code></td>
            </tr>
            <tr>
              <td>実行ログ</td>
              <td><code>{escape_html(crawler_rel)}/data/daily_fitness_ward.log</code></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="path-row" style="margin-top:16px">
        <code id="p-reservation-crawler"></code>
        <button type="button" class="copy" data-copy-target="p-reservation-crawler">コピー</button>
      </div>
      <div class="path-row" style="margin-top:8px">
        <code id="p-ari-master"></code>
        <button type="button" class="copy" data-copy-target="p-ari-master">コピー</button>
      </div>
    </div>"""
