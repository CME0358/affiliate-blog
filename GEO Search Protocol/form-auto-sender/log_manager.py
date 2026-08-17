"""
log_manager.py  —  送信ログ管理モジュール

出力形式:
    logs/YYYY-MM-DD.md   — 人間が読む日次ログ（sent / pending / error をセクション分け）
    logs/.sent_index.csv — 重複チェック専用インデックス（内部管理）
"""

from __future__ import annotations

import csv
import hashlib
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from config import (
    BASE_DIR,
    FAILURE_COOLDOWN_DAYS,
    FAILURE_COOLDOWN_INDEX,
    INPUT_DIR,
    LOG_DIR,
    LOG_ERROR,
    LOG_PERMANENT_SKIP,
    LOG_SENT,
    RESEND_INTERVAL_DAYS,
)

_VAULT_TZ = ZoneInfo("Asia/Tokyo")


def vault_today() -> date:
    """ログ・ダッシュボードの「本日」。日本時間の暦日。"""
    return datetime.now(_VAULT_TZ).date()


# ─── パス定義 ─────────────────────────────────────────────────────────────────

def _daily_log(d: date | None = None) -> Path:
    d = d or vault_today()
    return LOG_DIR / f"{d.isoformat()}.md"

_SENT_INDEX = LOG_DIR / ".sent_index.csv"
_SENT_INDEX_HEADERS = ["date", "company_name", "website_url"]

_FAILURE_COOLDOWN_HEADERS = [
    "company_name",
    "place_id",
    "website_url",
    "reason_key",
    "reason_category",
    "last_failed_date",
    "cooldown_until",
]

# Immutable event history.  .failure_cooldown.csv remains a mutable operational
# index and must never be used as the sole historical record.
FAILURE_EVENT_LOG = LOG_DIR / "failure_events.csv"
_FAILURE_EVENT_HEADERS = [
    "event_id", "timestamp", "company", "domain", "website_url", "place_id",
    "event_class", "reason", "category", "source_execution", "attempted",
    "submit_clicked", "post_observed", "confirmed_sent", "cooldown_until",
    "evidence_reference", "correction_of",
]
FAILURE_STATUS_CORRECTIONS = LOG_DIR / "failure_status_corrections.csv"
_FAILURE_STATUS_CORRECTION_HEADERS = [
    "correction_id", "corrected_at", "company", "domain", "original_status",
    "corrected_status", "reason", "evidence_reference", "source_execution",
]

_ERROR_CSV_HEADERS = [
    "logged_date",
    "company_name",
    "industry_name",
    "area_name",
    "website_url",
    "phone",
    "address",
    "place_id",
    "reason",
]

_SENT_CSV_HEADERS = [
    "date",
    "company_name",
    "industry_name",
    "area_name",
    "website_url",
    "form_url",
    "lp_url",
    "place_id",
    "status",
]

_PERMANENT_SKIP_HEADERS = [
    "date_added",
    "company_name",
    "website_url",
    "place_id",
    "reason",
]

_TIMEOUT_REASON_KEYS = frozenset({
    "timeout",
    "form_find_timeout",
    "Page.goto: timeout",
})

_PERMANENT_SKIP_TIMEOUT_THRESHOLD = 3


# ─── 内部ユーティリティ ───────────────────────────────────────────────────────

def _ensure_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_sent_index() -> None:
    _ensure_dir()
    if not _SENT_INDEX.exists():
        with _SENT_INDEX.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(_SENT_INDEX_HEADERS)


def _normalize_website_url(url: str) -> str:
    return (url or "").strip().rstrip("/").lower()


def _ensure_sent_csv() -> None:
    _ensure_dir()
    if not LOG_SENT.exists():
        with LOG_SENT.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=_SENT_CSV_HEADERS).writeheader()
        return
    _migrate_sent_csv_if_needed()


def _migrate_sent_csv_if_needed() -> None:
    """旧フォーマット sent.csv を新ヘッダーへ移行する。"""
    with LOG_SENT.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        if fieldnames == _SENT_CSV_HEADERS:
            return
        raw_rows = list(reader)

    migrated: list[dict] = []
    for row in raw_rows:
        migrated.append({
            "date": (row.get("date") or row.get("logged_date") or "").strip(),
            "company_name": row.get("company_name", ""),
            "industry_name": row.get("industry_name", ""),
            "area_name": row.get("area_name", ""),
            "website_url": (row.get("website_url") or "").strip(),
            "form_url": (row.get("form_url") or "").strip(),
            "lp_url": (row.get("lp_url") or "").strip(),
            "place_id": (row.get("place_id") or "").strip(),
            "status": (row.get("status") or "sent").strip(),
        })
    _write_sent_csv_rows(migrated)


def _ensure_permanent_skip_csv() -> None:
    _ensure_dir()
    if not LOG_PERMANENT_SKIP.exists():
        with LOG_PERMANENT_SKIP.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(_PERMANENT_SKIP_HEADERS)


_SENT_STATUS_CORRECTION_HEADERS = [
    "corrected_at",
    "company_name",
    "website_url",
    "place_id",
    "original_status",
    "corrected_status",
    "reason",
    "evidence_type",
    "audit_ref",
    "batch_id",
]

LOG_SENT_STATUS_CORRECTIONS = LOG_DIR / "sent_status_corrections.csv"


def append_sent_csv_row(company: dict, extra: dict | None = None) -> None:
    """送信成功を logs/sent.csv に1行追記する。"""
    extra = extra or {}
    _ensure_sent_csv()
    row = {
        "date": vault_today().isoformat(),
        "company_name": company.get("company_name", ""),
        "industry_name": company.get("industry_name", ""),
        "area_name": company.get("area_name", ""),
        "website_url": (company.get("website_url") or "").strip(),
        "form_url": (extra.get("form_url") or company.get("form_url") or "").strip(),
        "lp_url": (extra.get("lp_url") or "").strip(),
        "place_id": (company.get("place_id") or "").strip(),
        "status": (extra.get("status") or "sent").strip(),
    }
    with LOG_SENT.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_SENT_CSV_HEADERS)
        writer.writerow(row)


def _ensure_sent_status_corrections_csv() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_SENT_STATUS_CORRECTIONS.exists():
        with LOG_SENT_STATUS_CORRECTIONS.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=_SENT_STATUS_CORRECTION_HEADERS).writeheader()


def append_sent_status_correction(
    company: dict,
    *,
    original_status: str,
    corrected_status: str,
    reason: str,
    evidence_type: str = "",
    audit_ref: str = "",
    batch_id: str = "ari_batch1_2026-08-11",
) -> None:
    """
    sent.csv の状態訂正 audit trail（追記のみ・既存行は削除しない）。
    """
    _ensure_sent_status_corrections_csv()
    row = {
        "corrected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S JST"),
        "company_name": company.get("company_name", ""),
        "website_url": (company.get("website_url") or "").strip(),
        "place_id": (company.get("place_id") or "").strip(),
        "original_status": original_status,
        "corrected_status": corrected_status,
        "reason": reason,
        "evidence_type": evidence_type,
        "audit_ref": audit_ref,
        "batch_id": batch_id,
    }
    with LOG_SENT_STATUS_CORRECTIONS.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=_SENT_STATUS_CORRECTION_HEADERS, extrasaction="ignore").writerow(row)


def get_effective_sent_status(company_name: str, website_url: str = "") -> str:
    """sent.csv 行 + 最新 correction を考慮した effective status（canonical）。"""
    from submission_state import NOT_SENT, normalize_effective_status

    base = NOT_SENT
    nu = _normalize_website_url(website_url)
    if LOG_SENT.exists():
        with LOG_SENT.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                row_url = _normalize_website_url(row.get("website_url", ""))
                match = (
                    row.get("company_name") == company_name
                    or (nu and row_url and (nu == row_url or nu in row_url or row_url in nu))
                    or (
                        website_url
                        and website_url.rstrip("/") in (row.get("website_url") or "")
                    )
                )
                if match:
                    base = row.get("status") or "sent"

    latest_correction: str | None = None
    latest_at = ""
    if LOG_SENT_STATUS_CORRECTIONS.exists():
        with LOG_SENT_STATUS_CORRECTIONS.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                row_url = _normalize_website_url(row.get("website_url", ""))
                if row.get("company_name") == company_name or (
                    nu and row_url and (nu == row_url or nu in row_url or row_url in nu)
                ):
                    at = row.get("corrected_at") or ""
                    if at >= latest_at:
                        latest_at = at
                        latest_correction = row.get("corrected_status")

    if latest_correction:
        return normalize_effective_status(latest_correction)
    return normalize_effective_status(base)


def get_effective_sent_row(company_name: str, website_url: str = "") -> dict | None:
    """sent.csv から該当行（effective status 付き）を返す。"""
    nu = _normalize_website_url(website_url)
    for row in _load_all_sent_csv_rows():
        row_url = _normalize_website_url(row.get("website_url", ""))
        if row.get("company_name") == company_name or (
            nu and row_url and (nu == row_url or nu in row_url or row_url in nu)
        ):
            enriched = dict(row)
            enriched["effective_status"] = get_effective_sent_status(
                company_name, website_url or row.get("website_url", "")
            )
            return enriched
    return None


def _load_permanent_skip_rows() -> list[dict]:
    _ensure_permanent_skip_csv()
    with LOG_PERMANENT_SKIP.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        return list(reader)


def _write_permanent_skip_rows(rows: list[dict]) -> None:
    _ensure_permanent_skip_csv()
    with LOG_PERMANENT_SKIP.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_PERMANENT_SKIP_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in _PERMANENT_SKIP_HEADERS})


def is_timeout_reason(reason: str) -> bool:
    key = normalize_reason_key(reason)
    if key in _TIMEOUT_REASON_KEYS:
        return True
    return key == "timeout" or key == "form_find_timeout"


def _company_name_matches(a: str, b: str) -> bool:
    """会社名の完全一致または包含（どちらかが空なら不一致）。"""
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return False
    return a == b or a in b or b in a


def is_permanently_skipped(company: dict) -> tuple[bool, str]:
    """永続除外リストに載っていれば (True, reason) を返す。"""
    from exclude_places import is_excluded_place

    excluded, reason = is_excluded_place(company)
    if excluded:
        return True, reason

    name = (company.get("company_name") or "").strip()
    url = _normalize_website_url(company.get("website_url") or "")
    place_id = (company.get("place_id") or "").strip()
    for row in _load_permanent_skip_rows():
        reason = row.get("reason", "timeout_repeated")
        row_name = (row.get("company_name") or "").strip()
        row_url = _normalize_website_url(row.get("website_url", ""))
        if row_name and name and _company_name_matches(name, row_name):
            return True, reason
        if url and row_url and (url == row_url or url in row_url or row_url in url):
            return True, reason
        if place_id and place_id == (row.get("place_id") or "").strip():
            return True, reason
    return False, ""


def add_permanent_skip(
    *,
    company_name: str = "",
    website_url: str = "",
    place_id: str = "",
    reason: str = "user_excluded",
) -> bool:
    """
    permanent_skip.csv に1件追加する。同一 URL または会社名が既にあれば追加しない。
    Returns: 新規追加したら True
    """
    company_name = (company_name or "").strip()
    website_url = (website_url or "").strip()
    place_id = (place_id or "").strip()
    if not company_name and not website_url and not place_id:
        return False

    rows = _load_permanent_skip_rows()
    nu = _normalize_website_url(website_url)
    for row in rows:
        if place_id and place_id == (row.get("place_id") or "").strip():
            return False
        if nu and _normalize_website_url(row.get("website_url", "")) == nu:
            return False
        if company_name and _company_name_matches(
            company_name, row.get("company_name", "")
        ):
            return False

    rows.append(
        {
            "date_added": vault_today().isoformat(),
            "company_name": company_name,
            "website_url": website_url,
            "place_id": place_id,
            "reason": reason,
        }
    )
    _write_permanent_skip_rows(rows)
    return True


def update_permanent_skip_from_errors() -> int:
    """
    error.csv を集計し、同一 website_url で timeout / form_find_timeout が
    3回以上の企業を permanent_skip.csv に追加する。
    Returns: 新規追加件数
    """
    if not LOG_ERROR.exists():
        return 0

    existing = _load_permanent_skip_rows()
    existing_urls = {
        _normalize_website_url(r.get("website_url", ""))
        for r in existing
        if _normalize_website_url(r.get("website_url", ""))
    }

    timeout_counts: dict[str, int] = {}
    latest_by_url: dict[str, dict] = {}

    with LOG_ERROR.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return 0
        for row in reader:
            reason = row.get("reason") or ""
            if not is_timeout_reason(reason):
                continue
            url = _normalize_website_url(row.get("website_url") or "")
            if not url:
                continue
            timeout_counts[url] = timeout_counts.get(url, 0) + 1
            latest_by_url[url] = row

    today = vault_today().isoformat()
    added = 0
    for url, count in timeout_counts.items():
        if count < _PERMANENT_SKIP_TIMEOUT_THRESHOLD:
            continue
        if url in existing_urls:
            continue
        src = latest_by_url[url]
        existing.append({
            "date_added": today,
            "company_name": src.get("company_name", ""),
            "website_url": (src.get("website_url") or "").strip(),
            "place_id": (src.get("place_id") or "").strip(),
            "reason": f"timeout_x{count}",
        })
        existing_urls.add(url)
        added += 1

    if added:
        _write_permanent_skip_rows(existing)
    return added


def sync_permanent_skip() -> tuple[int, int]:
    """
    error.csv を集計して永続除外リストを更新し、結果を表示する。
    Returns: (新規追加件数, 累計件数)
    """
    added = update_permanent_skip_from_errors()
    total = len(_load_permanent_skip_rows())
    print(f"永続除外に追加: {added}件（累計: {total}件）")
    return added, total


def show_permanent_skip() -> None:
    """永続除外リストをコンソールに表示する。"""
    rows = _load_permanent_skip_rows()
    print(f"永続除外リスト: {len(rows)} 件\n")
    if not rows:
        print("（登録なし）")
        return
    print(f"{'date_added':<12} {'company_name':<40} {'website_url'}")
    print("-" * 100)
    for row in rows:
        print(
            f"{row.get('date_added', ''):<12} "
            f"{row.get('company_name', '')[:40]:<40} "
            f"{row.get('website_url', '')}"
        )


def _parse_row_date(row: dict, date_keys: tuple[str, ...] = ("date", "logged_date")) -> date | None:
    for key in date_keys:
        raw = (row.get(key) or "").strip()
        if not raw:
            continue
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            continue
    return None


def _load_all_sent_csv_rows() -> list[dict]:
    """logs/sent.csv の全行を読み込む。"""
    if not LOG_SENT.exists():
        return []
    with LOG_SENT.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        return [dict(row) for row in reader]


def _write_sent_csv_rows(rows: list[dict]) -> None:
    _ensure_dir()
    with LOG_SENT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_SENT_CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({h: (row.get(h) or "") for h in _SENT_CSV_HEADERS})


def _sent_field_needs_fix(value: str | None) -> bool:
    s = (value or "").strip()
    return not s or s == "不明"


def _sent_row_needs_fix(row: dict) -> bool:
    return (
        _sent_field_needs_fix(row.get("industry_name"))
        or _sent_field_needs_fix(row.get("area_name"))
    )


def _sent_row_still_unknown(row: dict) -> bool:
    return (
        _sent_field_needs_fix(row.get("industry_name"))
        or _sent_field_needs_fix(row.get("area_name"))
    )


def _apply_industry_area(row: dict, industry: str, area: str) -> None:
    if _sent_field_needs_fix(row.get("industry_name")) and (industry or "").strip():
        row["industry_name"] = industry.strip()
    if _sent_field_needs_fix(row.get("area_name")) and (area or "").strip():
        row["area_name"] = area.strip()


def _build_place_id_index_from_md() -> dict[str, tuple[str, str]]:
    """
    input/*.md および INPUT_DIR 配下の MD をスキャンし、
    place_id → (industry_name, area_name) の索引を構築する。
    """
    from parser import parse_md_list

    place_index: dict[str, tuple[str, str]] = {}
    scan_dirs: list[Path] = []
    local_input = BASE_DIR / "input"
    if local_input.is_dir():
        scan_dirs.append(local_input)
    if INPUT_DIR.is_dir():
        scan_dirs.append(INPUT_DIR)

    for directory in scan_dirs:
        try:
            companies = parse_md_list(str(directory))
        except Exception:
            continue
        for company in companies:
            pid = (company.get("place_id") or "").strip()
            if not pid:
                continue
            place_index[pid] = (
                (company.get("industry_name") or "").strip(),
                (company.get("area_name") or "").strip(),
            )
    return place_index


def _build_error_url_index() -> dict[str, dict]:
    """website_url（正規化）→ error.csv 最新行。"""
    lookup: dict[str, dict] = {}
    if not LOG_ERROR.exists():
        return lookup
    with LOG_ERROR.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return lookup
        for row in reader:
            url_key = _normalize_website_url(row.get("website_url", ""))
            if url_key:
                lookup[url_key] = row
    return lookup


def fix_sent_csv() -> tuple[int, int, int]:
    """
    sent.csv の industry_name / area_name を MD・error.csv から補完して上書き保存する。

    Returns:
        (補完対象件数, 補完成功件数, 不明のまま件数)
    """
    rows = _load_all_sent_csv_rows()
    if not rows:
        print("logs/sent.csv が存在しないか、データ行がありません。")
        return 0, 0, 0

    targets = [row for row in rows if _sent_row_needs_fix(row)]
    if not targets:
        print(f"補完完了: 0件中 0件補完 / 0件不明のまま（全{len(rows)}件は補完済み）")
        return 0, 0, 0

    place_index = _build_place_id_index_from_md()
    error_by_url = _build_error_url_index()

    fixed = 0
    for row in targets:
        before_unknown = _sent_row_still_unknown(row)

        pid = (row.get("place_id") or "").strip()
        if pid and pid in place_index:
            industry, area = place_index[pid]
            _apply_industry_area(row, industry, area)

        if _sent_row_still_unknown(row):
            url_key = _normalize_website_url(row.get("website_url", ""))
            src = error_by_url.get(url_key)
            if src:
                _apply_industry_area(
                    row,
                    src.get("industry_name", ""),
                    src.get("area_name", ""),
                )

        if before_unknown and not _sent_row_still_unknown(row):
            fixed += 1

    _write_sent_csv_rows(rows)

    still_unknown = sum(1 for row in targets if _sent_row_still_unknown(row))
    print(
        f"補完完了: {len(targets)}件中 {fixed}件補完 / {still_unknown}件不明のまま"
    )
    return len(targets), fixed, still_unknown


def _load_csv_rows_in_period(path: Path, since: date, headers_ok: bool = True) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if headers_ok and not reader.fieldnames:
            return []
        for row in reader:
            d = _parse_row_date(row)
            if d is None or d < since:
                continue
            rows.append(row)
    return rows


def _company_lookup_from_error_csv() -> dict[str, dict]:
    """website_url / place_id / company_name から error.csv の最新行を引く。"""
    lookup: dict[str, dict] = {}
    if not LOG_ERROR.exists():
        return lookup
    with LOG_ERROR.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return lookup
        for row in reader:
            for key in (
                _normalize_website_url(row.get("website_url", "")),
                (row.get("place_id") or "").strip(),
                (row.get("company_name") or "").strip(),
            ):
                if key:
                    lookup[key] = row
    return lookup


def _load_sent_rows_for_report(since: date) -> list[dict]:
    """レポート用: sent.csv を優先し、無ければ .sent_index を error.csv で補完。"""
    rows = _load_csv_rows_in_period(LOG_SENT, since)
    if rows:
        return rows

    index_path = LOG_DIR / ".sent_index.csv"
    if not index_path.exists():
        return []

    lookup = _company_lookup_from_error_csv()
    out: list[dict] = []
    with index_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        for row in reader:
            d = _parse_row_date(row, ("date", "logged_date"))
            if d is None or d < since:
                continue
            url = (row.get("website_url") or "").strip()
            name = (row.get("company_name") or "").strip()
            src = (
                lookup.get(_normalize_website_url(url))
                or lookup.get(name)
                or {}
            )
            out.append({
                "logged_date": row.get("date", ""),
                "company_name": name,
                "industry_name": src.get("industry_name", ""),
                "area_name": src.get("area_name", ""),
                "website_url": url,
                "phone": src.get("phone", ""),
                "address": src.get("address", ""),
                "place_id": src.get("place_id", ""),
            })
    return out


def _aggregate_success_rates(rows: list[dict], group_key: str) -> list[tuple[str, int, int, float]]:
    stats: dict[str, dict[str, int]] = {}
    for row in rows:
        key = (row.get(group_key) or "").strip() or "（不明）"
        bucket = stats.setdefault(key, {"total": 0, "success": 0})
        bucket["total"] += 1
        if row.get("_outcome") == "success":
            bucket["success"] += 1

    result: list[tuple[str, int, int, float]] = []
    for key, bucket in stats.items():
        total = bucket["total"]
        success = bucket["success"]
        rate = (success / total * 100) if total else 0.0
        result.append((key, total, success, rate))
    result.sort(key=lambda x: (-x[1], x[0]))
    return result


def _format_rate_table(
    title: str,
    col_name: str,
    rows: list[tuple[str, int, int, float]],
) -> str:
    lines = [
        f"## {title}",
        "",
        f"| {col_name} | 処理数 | 成功 | 成功率 |",
        "|------|--------|------|--------|",
    ]
    if rows:
        for key, total, success, rate in rows:
            lines.append(f"| {key} | {total} | {success} | {rate:.1f}% |")
    else:
        lines.append("| （データなし） | 0 | 0 | 0.0% |")
    lines.append("")
    return "\n".join(lines)


def generate_report() -> str:
    """
    直近7日間の業種×エリア別成功率レポートを生成する。
    コンソール出力 + logs/report_YYYY-MM-DD.md に保存。
    """
    today = vault_today()
    since = today - timedelta(days=6)
    period_label = f"{since.isoformat()} 〜 {today.isoformat()}"

    outcome_rows: list[dict] = []

    for row in _load_sent_rows_for_report(since):
        enriched = dict(row)
        enriched["_outcome"] = "success"
        outcome_rows.append(enriched)

    for row in _load_csv_rows_in_period(LOG_ERROR, since):
        enriched = dict(row)
        enriched["_outcome"] = "error"
        outcome_rows.append(enriched)

    industry_table = _aggregate_success_rates(outcome_rows, "industry_name")
    area_table = _aggregate_success_rates(outcome_rows, "area_name")

    newly_added = update_permanent_skip_from_errors()
    total_skip = len(_load_permanent_skip_rows())

    report_parts = [
        f"# 送信成功率レポート {today.isoformat()}",
        "",
        f"集計期間: {period_label}（直近7日間）",
        f"データソース: logs/sent.csv + logs/error.csv",
        "",
        _format_rate_table("業種別 送信成功率（直近7日間）", "業種", industry_table),
        _format_rate_table("エリア別 送信成功率（直近7日間）", "エリア", area_table),
        "## 今日の永続除外追加件数",
        "",
        f"新規追加: {newly_added}件（累計: {total_skip}件）",
        "",
    ]
    report_text = "\n".join(report_parts)

    _ensure_dir()
    report_path = LOG_DIR / f"report_{today.isoformat()}.md"
    report_path.write_text(report_text, encoding="utf-8")

    print(report_text)
    print(f"レポート保存: {report_path}")
    return report_text


def _ensure_error_csv() -> None:
    _ensure_dir()
    if not LOG_ERROR.exists():
        with LOG_ERROR.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(_ERROR_CSV_HEADERS)


def normalize_reason_key(reason: str) -> str:
    """error.csv / クールダウン用に理由文字列を正規化する。"""
    r = (reason or "").strip()
    if not r:
        return "(empty)"
    first = r.split("\n")[0].strip()
    if first.startswith("Page.goto:"):
        if "ERR_CONNECTION_REFUSED" in first:
            return "Page.goto: ERR_CONNECTION_REFUSED"
        if "ERR_NAME_NOT_RESOLVED" in first:
            return "Page.goto: ERR_NAME_NOT_RESOLVED"
        if "timeout" in first.lower():
            return "Page.goto: timeout"
        return "Page.goto: (other)"
    return first[:200]


def reason_to_category(reason: str) -> str:
    """クールダウン日数カテゴリへマッピング。"""
    key = normalize_reason_key(reason)
    if key == "website_url_is_none":
        return "no_website"
    if key == "submit_button_not_found":
        return "submit_button"
    if key in ("no_contact_form_only_reservation",):
        return "reservation_only"
    if key == "no_form_external_booking":
        return "external_booking_only"
    if key == "pdf_or_file_download":
        return "pdf_or_file_download"
    if key == "no_form_chain_site":
        return "no_form_chain"
    if key == "recaptcha_detected":
        return "pending_recaptcha"
    if key in ("form_find_timeout",) or key == "timeout" or "timeout" in key.lower():
        return "timeout"
    if "ERR_CONNECTION" in key or "ERR_NAME_NOT_RESOLVED" in key:
        return "site_down"
    if "問い合わせ" in key or key.startswith("no_contact"):
        return "form_not_found"
    return "other"


def _company_match_key(company: dict) -> str:
    pid = (company.get("place_id") or "").strip()
    if pid:
        return f"pid:{pid}"
    name = (company.get("company_name") or "").strip()
    url = (company.get("website_url") or "").strip().rstrip("/")
    return f"name:{name}|url:{url}"


def _ensure_failure_cooldown_index() -> None:
    """Ensure mutable operational current-state cooldown index exists."""
    _ensure_dir()
    if not FAILURE_COOLDOWN_INDEX.exists():
        with FAILURE_COOLDOWN_INDEX.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(_FAILURE_COOLDOWN_HEADERS)


def _load_failure_cooldown_rows() -> dict[str, dict]:
    _ensure_failure_cooldown_index()
    out: dict[str, dict] = {}
    with FAILURE_COOLDOWN_INDEX.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return out
        for row in reader:
            key = _company_match_key({
                "place_id": row.get("place_id", ""),
                "company_name": row.get("company_name", ""),
                "website_url": row.get("website_url", ""),
            })
            if key:
                out[key] = row
    return out


def _write_failure_cooldown_rows(rows: dict[str, dict]) -> None:
    _ensure_failure_cooldown_index()
    with FAILURE_COOLDOWN_INDEX.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_FAILURE_COOLDOWN_HEADERS)
        writer.writeheader()
        for row in rows.values():
            writer.writerow({h: row.get(h, "") for h in _FAILURE_COOLDOWN_HEADERS})


def is_in_failure_cooldown(company: dict) -> tuple[bool, str]:
    """
    失敗クールダウン中なら (True, 説明) を返す。
    同一企業に active な cooldown_until があればスキップ（理由は問わない）。
    """
    rows = _load_failure_cooldown_rows()
    key = _company_match_key(company)
    row = rows.get(key)
    if not row:
        return False, ""
    try:
        until = date.fromisoformat((row.get("cooldown_until") or "").strip())
    except ValueError:
        return False, ""
    today = vault_today()
    if today <= until:
        rk = row.get("reason_key", "")
        return True, f"{rk} まで {until.isoformat()}（残り {(until - today).days + 1} 日）"
    return False, ""


def record_failure_cooldown(company: dict, reason: str) -> bool:
    """
    失敗を mutable operational current-state cooldown 索引に記録する。
    Immutable history is recorded separately in failure_events.csv.
    Returns:
        error.csv に追記してよいか（クールダウン開始時のみ True）
    """
    today = vault_today()
    reason_key = normalize_reason_key(reason)
    category = reason_to_category(reason)
    days = FAILURE_COOLDOWN_DAYS.get(category, FAILURE_COOLDOWN_DAYS["other"])
    until = today + timedelta(days=days)

    rows = _load_failure_cooldown_rows()
    key = _company_match_key(company)
    prev = rows.get(key)
    append_error = True
    if prev:
        try:
            prev_until = date.fromisoformat((prev.get("cooldown_until") or "").strip())
        except ValueError:
            prev_until = date.min
        if today <= prev_until:
            # クールダウン中の再失敗 → error.csv は水増ししない
            append_error = False
        rows[key] = {
            "company_name": company.get("company_name", ""),
            "place_id": company.get("place_id", "") or "",
            "website_url": (company.get("website_url") or "").strip(),
            "reason_key": reason_key,
            "reason_category": category,
            "last_failed_date": today.isoformat(),
            "cooldown_until": max(until, prev_until).isoformat(),
        }
    else:
        rows[key] = {
            "company_name": company.get("company_name", ""),
            "place_id": company.get("place_id", "") or "",
            "website_url": (company.get("website_url") or "").strip(),
            "reason_key": reason_key,
            "reason_category": category,
            "last_failed_date": today.isoformat(),
            "cooldown_until": until.isoformat(),
        }
    _write_failure_cooldown_rows(rows)
    return append_error


def _ensure_failure_event_log() -> None:
    _ensure_dir()
    if not FAILURE_EVENT_LOG.exists():
        with FAILURE_EVENT_LOG.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=_FAILURE_EVENT_HEADERS).writeheader()


def append_failure_event(
    company: dict,
    *,
    event_class: str,
    reason: str,
    source_execution: str,
    attempted: bool,
    submit_clicked: bool,
    post_observed: bool,
    confirmed_sent: bool = False,
    cooldown_until: str = "",
    evidence_reference: str = "",
    event_identity: str = "",
    correction_of: str = "",
    timestamp: str = "",
) -> tuple[bool, str]:
    """Append one immutable failure/safety event; dedupe by execution identity."""
    _ensure_failure_event_log()
    domain = (company.get("domain") or "").strip().lower()
    website_url = (company.get("website_url") or "").strip()
    if not domain and website_url:
        from urllib.parse import urlparse
        domain = (urlparse(website_url).hostname or "").lower().removeprefix("www.")
    identity = event_identity or "|".join((
        source_execution, domain, event_class, reason, evidence_reference,
    ))
    event_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    with FAILURE_EVENT_LOG.open("r", newline="", encoding="utf-8") as f:
        if any((row.get("event_id") or "") == event_id for row in csv.DictReader(f)):
            return False, event_id
    row = {
        "event_id": event_id,
        "timestamp": timestamp or datetime.now(_VAULT_TZ).isoformat(timespec="seconds"),
        "company": company.get("company_name", ""),
        "domain": domain,
        "website_url": website_url,
        "place_id": company.get("place_id", "") or "",
        "event_class": event_class,
        "reason": reason,
        "category": reason_to_category(reason),
        "source_execution": source_execution,
        "attempted": str(bool(attempted)).lower(),
        "submit_clicked": str(bool(submit_clicked)).lower(),
        "post_observed": str(bool(post_observed)).lower(),
        "confirmed_sent": str(bool(confirmed_sent)).lower(),
        "cooldown_until": cooldown_until,
        "evidence_reference": evidence_reference,
        "correction_of": correction_of,
    }
    with FAILURE_EVENT_LOG.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=_FAILURE_EVENT_HEADERS).writerow(row)
    return True, event_id


def load_failure_events(*, domain: str = "") -> list[dict]:
    _ensure_failure_event_log()
    with FAILURE_EVENT_LOG.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    normalized = domain.strip().lower().removeprefix("www.")
    return [r for r in rows if not normalized or (r.get("domain") or "") == normalized]


def append_failure_status_correction(
    company: dict,
    *,
    original_status: str,
    corrected_status: str,
    reason: str,
    evidence_reference: str,
    source_execution: str,
) -> tuple[bool, str]:
    """Append an authorized classification correction without rewriting history."""
    _ensure_dir()
    if not FAILURE_STATUS_CORRECTIONS.exists():
        with FAILURE_STATUS_CORRECTIONS.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=_FAILURE_STATUS_CORRECTION_HEADERS).writeheader()
    domain = (company.get("domain") or "").strip().lower().removeprefix("www.")
    identity = "|".join((domain, original_status, corrected_status, evidence_reference))
    correction_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    with FAILURE_STATUS_CORRECTIONS.open("r", newline="", encoding="utf-8") as f:
        if any((r.get("correction_id") or "") == correction_id for r in csv.DictReader(f)):
            return False, correction_id
    row = {
        "correction_id": correction_id,
        "corrected_at": datetime.now(_VAULT_TZ).isoformat(timespec="seconds"),
        "company": company.get("company_name", ""),
        "domain": domain,
        "original_status": original_status,
        "corrected_status": corrected_status,
        "reason": reason,
        "evidence_reference": evidence_reference,
        "source_execution": source_execution,
    }
    with FAILURE_STATUS_CORRECTIONS.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=_FAILURE_STATUS_CORRECTION_HEADERS).writerow(row)
    return True, correction_id


def get_effective_failure_status(domain: str, default: str = "") -> str:
    """Return latest append-only correction, otherwise latest ledger event class."""
    normalized = domain.strip().lower().removeprefix("www.")
    latest = default
    if FAILURE_STATUS_CORRECTIONS.exists():
        with FAILURE_STATUS_CORRECTIONS.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if (row.get("domain") or "") == normalized:
                    latest = row.get("corrected_status") or latest
    if latest != default:
        return latest
    events = load_failure_events(domain=normalized)
    return (events[-1].get("event_class") or default) if events else default


def seed_failure_cooldown_from_error_csv(csv_path: Path | None = None) -> int:
    """
    既存 error.csv からユニーク企業のクールダウン索引を一括生成する（P0 初回移行用）。
    error.csv には追記しない。戻り値は登録した企業数。
    """
    path = csv_path or LOG_ERROR
    if not path.exists():
        return 0

    latest: dict[str, tuple[dict, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("company_name") or "").strip()
            if not name:
                continue
            company = {
                "company_name": name,
                "place_id": (row.get("place_id") or "").strip(),
                "website_url": (row.get("website_url") or "").strip() or None,
            }
            reason = row.get("reason") or ""
            latest[_company_match_key(company)] = (company, reason)

    today = vault_today()
    rows = _load_failure_cooldown_rows()
    for company, reason in latest.values():
        reason_key = normalize_reason_key(reason)
        category = reason_to_category(reason)
        days = FAILURE_COOLDOWN_DAYS.get(category, FAILURE_COOLDOWN_DAYS["other"])
        until = today + timedelta(days=days)
        key = _company_match_key(company)
        rows[key] = {
            "company_name": company.get("company_name", ""),
            "place_id": company.get("place_id", "") or "",
            "website_url": (company.get("website_url") or "").strip(),
            "reason_key": reason_key,
            "reason_category": category,
            "last_failed_date": today.isoformat(),
            "cooldown_until": until.isoformat(),
        }
    _write_failure_cooldown_rows(rows)
    return len(latest)


def clear_failure_cooldown(company: dict) -> None:
    """送信成功時にクールダウンを解除する。"""
    rows = _load_failure_cooldown_rows()
    key = _company_match_key(company)
    if key in rows:
        del rows[key]
        _write_failure_cooldown_rows(rows)


def append_error_csv_row(company: dict, reason: str) -> None:
    """エラー・フォーム未取得を logs/error.csv に1行追記する（リトライ元データ用）。"""
    if not record_failure_cooldown(company, reason):
        return
    _ensure_error_csv()
    row = [
        vault_today().isoformat(),
        company.get("company_name", ""),
        company.get("industry_name", ""),
        company.get("area_name", ""),
        (company.get("website_url") or "").strip(),
        company.get("phone") or "",
        company.get("address") or "",
        company.get("place_id") or "",
        reason,
    ]
    with LOG_ERROR.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)


def load_companies_from_error_csv(csv_path: Path | None = None) -> list[dict]:
    """
    logs/error.csv を読み込み、main.process_company と互換な company dict のリストを返す。
    同一企業は最終行のみ（place_id / 社名+URL でユニーク）。
    """
    path = csv_path or LOG_ERROR
    if not path.exists():
        return []

    by_key: dict[str, dict] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        for row in reader:
            name = (row.get("company_name") or "").strip()
            if not name:
                continue
            company = {
                "company_name":  name,
                "industry_name": (row.get("industry_name") or "").strip(),
                "area_name":     (row.get("area_name") or "").strip(),
                "website_url":   (row.get("website_url") or "").strip() or None,
                "phone":         (row.get("phone") or "").strip() or None,
                "address":       (row.get("address") or "").strip() or None,
                "place_id":      (row.get("place_id") or "").strip() or None,
                "rating":        0.0,
                "review_count":  0,
                "date":          (row.get("logged_date") or vault_today().isoformat()),
            }
            by_key[_company_match_key(company)] = company
    return list(by_key.values())


def _append_sent_index(company_name: str, website_url: str) -> None:
    _ensure_sent_index()
    with _SENT_INDEX.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([vault_today().isoformat(), company_name, website_url or ""])


def _init_daily_log(path: Path) -> None:
    """その日のログファイルが存在しない場合、ヘッダーを作成する。"""
    if not path.exists():
        _ensure_dir()
        path.write_text(
            f"# 送信ログ {vault_today().isoformat()}\n\n"
            f"## ✅ 送信済み\n\n"
            f"## ⚠️ 手動確認（reCAPTCHA）\n\n"
            f"## ❌ エラー\n",
            encoding="utf-8",
        )


def _append_to_section(path: Path, section_header: str, block: str) -> None:
    """
    指定セクションヘッダーの直後にブロックを挿入する。
    セクションが見つからない場合はファイル末尾に追記する。
    """
    content = path.read_text(encoding="utf-8")
    marker = f"\n{section_header}\n"

    if marker in content:
        # セクションの直後（次のセクションの前）に挿入
        idx = content.index(marker) + len(marker)
        content = content[:idx] + block + content[idx:]
    else:
        content += f"\n{section_header}\n{block}"

    path.write_text(content, encoding="utf-8")


# ─── MDブロック生成 ───────────────────────────────────────────────────────────

def _format_industry_line(company: dict) -> str:
    name = company.get("industry_name", "")
    tier = company.get("industry_tier")
    if tier is not None:
        return f"- 業種: {name}（tier {tier}） / エリア: {company.get('area_name', '')}"
    return f"- 業種: {name} / エリア: {company.get('area_name', '')}"


def _sent_block(company: dict, extra: dict) -> str:
    message = extra.get("message", "")
    return (
        f"### {company['company_name']}\n"
        f"{_format_industry_line(company)}\n"
        f"- フォーム: {extra.get('form_url', '')}\n"
        f"- LP URL: {extra.get('lp_url', '')}\n\n"
        f"**送信内容:**\n"
        f"```\n{message}\n```\n\n"
        f"---\n\n"
    )


def _pending_block(company: dict, extra: dict) -> str:
    message = extra.get("message", "")
    return (
        f"### {company['company_name']}\n"
        f"{_format_industry_line(company)}\n"
        f"- フォーム: {extra.get('form_url', company.get('website_url', ''))}\n"
        f"- 理由: {extra.get('reason', '')}\n\n"
        + (
            f"**送信予定内容:**\n```\n{message}\n```\n\n"
            if message else ""
        )
        + f"---\n\n"
    )


def _error_block(company: dict, extra: dict) -> str:
    return (
        f"### {company['company_name']}\n"
        f"{_format_industry_line(company)}\n"
        f"- URL: {company.get('website_url', '')}\n"
        f"- 理由: {extra.get('detail', extra.get('reason', ''))}\n\n"
        f"---\n\n"
    )


# ─── 公開 API ──────────────────────────────────────────────────────────────────

def log_result(
    status: str,
    company: dict,
    extra: dict | None = None,
) -> None:
    """
    処理結果を日次 MD ログに書き込む。

    Args:
        status:  "sent" / "no_form" / "error" / "pending" / "form_analysis_failed"
        company: parser.py が返す company dict
        extra:   追加情報
                   sent    → form_url, lp_url, message
                   pending → form_url, reason, message（送信予定文面）
                   error   → detail / reason
    """
    extra = extra or {}
    _ensure_dir()

    if status != "sent" and extra.get("event_identity"):
        event_class = str(extra.get("event_class") or (
            "SAFETY_BLOCKED" if status == "pending" else "FAILED"
        ))
        append_failure_event(
            company,
            event_class=event_class,
            reason=str(extra.get("detail", extra.get("reason", ""))),
            source_execution=str(extra.get("source_execution") or "runtime"),
            attempted=bool(extra.get("attempted", False)),
            submit_clicked=bool(extra.get("submit_clicked", False)),
            post_observed=bool(extra.get("post_observed", False)),
            confirmed_sent=False,
            cooldown_until=str(extra.get("cooldown_until") or ""),
            evidence_reference=str(extra.get("evidence_reference") or ""),
            event_identity=str(extra.get("event_identity")),
        )

    log_path = _daily_log()
    _init_daily_log(log_path)

    if status == "sent":
        _append_to_section(log_path, "## ✅ 送信済み", _sent_block(company, extra))
        _append_sent_index(company["company_name"], company.get("website_url", ""))
        if not extra.get("_skip_sent_csv_append"):
            append_sent_csv_row(company, extra)
        clear_failure_cooldown(company)

    elif status == "pending":
        _append_to_section(log_path, "## ⚠️ 手動確認（reCAPTCHA）", _pending_block(company, extra))
        record_failure_cooldown(company, extra.get("reason", "recaptcha_detected"))

    else:  # no_form / error / form_analysis_failed
        err_reason = extra.get("detail", extra.get("reason", ""))
        _append_to_section(log_path, "## ❌ エラー", _error_block(company, extra))
        append_error_csv_row(company, str(err_reason))


def is_already_sent(company_name: str, website_url: str) -> bool:
    """
    effective status が CONFIRMED_SENT のみ duplicate lock。
    CONFIRMATION_REACHED / FAILED / UNKNOWN は自動再送をブロックしない。
    """
    from submission_state import should_block_duplicate_send

    eff = get_effective_sent_status(company_name, website_url)
    if not should_block_duplicate_send(eff):
        return False

    sent_row = get_effective_sent_row(company_name, website_url)
    if not sent_row:
        return True

    sent_date = _parse_row_date(sent_row)
    if sent_date is None:
        return True
    cutoff = vault_today() - timedelta(days=RESEND_INTERVAL_DAYS)
    return sent_date >= cutoff


def get_stats() -> dict:
    """今日のログファイルから件数を集計して返す。"""
    log_path = _daily_log()
    if not log_path.exists():
        return {"sent": 0, "pending": 0, "error": 0}

    content = log_path.read_text(encoding="utf-8")

    def _count_in_section(text: str, section: str) -> int:
        """セクション内の ### エントリ数をカウントする。"""
        sections = [
            "## ✅ 送信済み",
            "## ⚠️ 手動確認（reCAPTCHA）",
            "## ❌ エラー",
        ]
        start = text.find(section)
        if start == -1:
            return 0
        # 次のセクション開始位置を探して範囲を絞る
        next_start = len(text)
        for s in sections:
            if s == section:
                continue
            idx = text.find(s, start + len(section))
            if idx != -1 and idx < next_start:
                next_start = idx
        chunk = text[start:next_start]
        return chunk.count("\n### ")

    return {
        "sent":    _count_in_section(content, "## ✅ 送信済み"),
        "pending": _count_in_section(content, "## ⚠️ 手動確認（reCAPTCHA）"),
        "error":   _count_in_section(content, "## ❌ エラー"),
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="送信ログ管理（永続除外・レポート）")
    ap.add_argument(
        "--show-permanent-skip",
        action="store_true",
        help="永続除外リストを表示",
    )
    ap.add_argument(
        "--report",
        action="store_true",
        help="直近7日間の業種×エリア別成功率レポートを生成",
    )
    ap.add_argument(
        "--fix-sent-csv",
        action="store_true",
        help="sent.csv の industry_name / area_name を MD・error.csv から補完",
    )
    args = ap.parse_args()

    if args.show_permanent_skip:
        update_permanent_skip_from_errors()
        show_permanent_skip()
    elif args.fix_sent_csv:
        fix_sent_csv()
        print("")
        generate_report()
    elif args.report:
        generate_report()
    else:
        ap.print_help()
