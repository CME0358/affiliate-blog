"""
list_filter.py — 送信キュー前処理（P0）

フォーム自動送信対象外の企業を別チャネル（電話・手動）へ振り分ける。
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from urllib.parse import urlparse

from config import LOG_DIR, SKIP_AREAS, SKIP_INDUSTRIES, VAULT_ROOT
from exclude_places import is_excluded_place
from log_manager import vault_today

# SNS・地図のみ等 — フォーム探索不可
NON_SENDABLE_HOST_FRAGMENTS: tuple[str, ...] = (
    "lin.ee",
    "line.me/R",
    "instagram.com",
    "facebook.com",
    "fb.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
    "google.com/maps",
    "goo.gl/maps",
    "maps.app.goo.gl",
)

# 予約専用URL（問い合わせフォームではない）
RESERVATION_URL_FRAGMENTS: tuple[str, ...] = (
    "/reserve",
    "/reservation",
    "/booking",
    "/yoyaku",
    "/schedule",
    "hotpepper",
    "minagine",
    "salon-board",
    "reserva.be",
    "coubic",
    "stores.jp/reserve",
    "airrsv",
    "sattou.net",
)

ALTERNATE_CHANNEL_CSV = LOG_DIR / "alternate_channel.csv"
_ALTERNATE_HEADERS = [
    "logged_date",
    "company_name",
    "industry_name",
    "area_name",
    "website_url",
    "phone",
    "address",
    "place_id",
    "skip_reason",
    "channel",
]

# Vault 内の別チャネルリスト（電話アプローチ用）
ALTERNATE_CHANNEL_MD_DIR = VAULT_ROOT / "40_Sales" / "商談メモ" / "リスト" / "別チャネル"


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def is_sns_or_non_web_url(url: str | None) -> bool:
    if not url or not str(url).strip():
        return False
    u = str(url).strip().lower()
    host = _host_of(u)
    return any(frag in u or frag in host for frag in NON_SENDABLE_HOST_FRAGMENTS)


def is_reservation_only_list_url(url: str | None) -> bool:
    if not url or not str(url).strip():
        return False
    u = str(url).strip().lower()
    if any(frag in u for frag in RESERVATION_URL_FRAGMENTS):
        return True
    return bool(re.search(r"(?<![a-z0-9])book(?:$|(?![a-z0-9])|[/._?&#=-])", u))


def classify_skip(company: dict) -> tuple[str, str] | None:
    """
    送信スキップ対象なら (skip_reason, channel) を返す。
    channel: "phone" | "manual"
    """
    excluded, reason = is_excluded_place(company)
    if excluded:
        return reason, "manual"

    url = (company.get("website_url") or "").strip() or None
    phone = (company.get("phone") or "").strip()

    if not url:
        if phone:
            return "website_url_is_none", "phone"
        return "website_url_is_none", "manual"

    if is_sns_or_non_web_url(url):
        return "list_filter_sns_only", "phone" if phone else "manual"

    if is_reservation_only_list_url(url):
        return "list_filter_reservation_url", "phone" if phone else "manual"

    return None


def split_sendable(companies: list[dict]) -> tuple[list[dict], list[dict]]:
    """(送信対象, スキップ対象+skip_reason/channel を付与した dict)"""
    sendable: list[dict] = []
    skipped: list[dict] = []
    for c in companies:
        hit = classify_skip(c)
        if hit:
            reason, channel = hit
            row = {**c, "skip_reason": reason, "alternate_channel": channel}
            skipped.append(row)
        else:
            sendable.append(c)
    return sendable, skipped


def _ensure_alternate_csv() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not ALTERNATE_CHANNEL_CSV.exists():
        with ALTERNATE_CHANNEL_CSV.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(_ALTERNATE_HEADERS)


def append_alternate_channel_rows(skipped: list[dict]) -> int:
    """別チャネル CSV に追記。戻り値は追記件数。"""
    if not skipped:
        return 0
    _ensure_alternate_csv()
    today = vault_today().isoformat()
    with ALTERNATE_CHANNEL_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for c in skipped:
            w.writerow([
                today,
                c.get("company_name", ""),
                c.get("industry_name", ""),
                c.get("area_name", ""),
                (c.get("website_url") or "").strip(),
                c.get("phone") or "",
                c.get("address") or "",
                c.get("place_id") or "",
                c.get("skip_reason", ""),
                c.get("alternate_channel", "phone"),
            ])
    return len(skipped)


def write_alternate_channel_md(skipped: list[dict], source_label: str = "") -> Path | None:
    """当日の別チャネル MD を Vault に追記保存。"""
    if not skipped:
        return None
    ALTERNATE_CHANNEL_MD_DIR.mkdir(parents=True, exist_ok=True)
    today = vault_today().isoformat()
    path = ALTERNATE_CHANNEL_MD_DIR / f"{today}_別チャネル.md"

    lines: list[str] = []
    if not path.exists():
        lines.append(f"# 別チャネルリスト（フォーム送信対象外）")
        lines.append("")
        lines.append(f"- 作成日: {today}")
        lines.append(f"- 用途: 電話アプローチ / 手動フォーム送信")
        lines.append("")
        lines.append("## 企業一覧")
        lines.append("")

    for c in skipped:
        ch = c.get("alternate_channel", "phone")
        reason = c.get("skip_reason", "")
        lines.append(f"### {c.get('company_name', '')}")
        lines.append(f"- 業種: {c.get('industry_name', '')} / エリア: {c.get('area_name', '')}")
        lines.append(f"- 理由: {reason}")
        lines.append(f"- チャネル: {ch}")
        if c.get("website_url"):
            lines.append(f"- Web: {c['website_url']}")
        if c.get("phone"):
            lines.append(f"- 電話: {c['phone']}")
        lines.append("")

    block = "\n".join(lines)
    if path.exists():
        with path.open("a", encoding="utf-8") as f:
            if source_label:
                f.write(f"\n<!-- source: {source_label} -->\n")
            f.write(block)
    else:
        path.write_text(block, encoding="utf-8")
    return path


def get_config_exclusion_label(company: dict) -> str | None:
    """
    config.SKIP_INDUSTRIES / SKIP_AREAS に該当する場合、
    ログ用ラベル（例: 業種除外: 整骨院）を返す。該当なしは None。
    """
    industry = (company.get("industry_name") or "").strip()
    area = (company.get("area_name") or "").strip()

    for skip_ind in SKIP_INDUSTRIES:
        if skip_ind in industry:
            return f"業種除外: {skip_ind}"

    for skip_area in SKIP_AREAS:
        if area == skip_area:
            return f"エリア除外: {skip_area}"

    return None


def apply_list_filter(companies: list[dict], source_label: str = "") -> list[dict]:
    """
    送信対象のみ返す。スキップ分は alternate_channel.csv / MD に記録。
    """
    sendable, skipped = split_sendable(companies)
    if skipped:
        n = append_alternate_channel_rows(skipped)
        md_path = write_alternate_channel_md(skipped, source_label)
        print(f"📞  別チャネル振り分け: {n} 件（送信キューから除外）")
        if md_path:
            print(f"    → {md_path}")
        for c in skipped[:5]:
            print(f"    · {c['company_name']}: {c.get('skip_reason')}")
        if len(skipped) > 5:
            print(f"    … 他 {len(skipped) - 5} 件")
    return sendable
