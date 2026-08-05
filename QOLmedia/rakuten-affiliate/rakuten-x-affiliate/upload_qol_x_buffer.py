#!/usr/bin/env python3
"""QOL 7ch: CSV 49本ローテ → Buffer 予約投稿（各1本/日・計7本）。

fatigue / focus / pet / stress / factoring / sleep / haircare
08:00 fatigue / 12:00 focus / 15:00 pet / 18:00 stress / 20:00 factoring / 21:00 sleep / 23:00 haircare JST
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import rakuten_core as core
from qol_x_schedule import (
    LOG_PATH,
    QOL_CHANNELS,
    QolChannel,
    STATE_PATH,
    csv_path,
    due_at_iso,
    schedule_base_date,
)
from upload_buffer_drafts import create_buffer_post, is_rate_limit_error

_FAS_DIR = Path(__file__).resolve().parents[3] / "GEO Search Protocol" / "form-auto-sender"
if str(_FAS_DIR) not in sys.path:
    sys.path.insert(0, str(_FAS_DIR))
from automation_state import is_channel_paused  # noqa: E402

# 共感3ch → LP 導線（URLなし投稿の末尾に付与）
CONDITION_LP_FOOTER: dict[str, str] = {
    "fatigue": "https://www.qolmedia.info/sleep-guide.html?utm_source=twitter&utm_medium=social&utm_campaign=fatigue",
    "focus": "https://www.qolmedia.info/sleep-guide.html?utm_source=twitter&utm_medium=social&utm_campaign=focus",
    "stress": "https://www.qolmedia.info/sleep-guide.html?utm_source=twitter&utm_medium=social&utm_campaign=stress",
}
CONDITION_FOOTER_LINE = "\n{url}"


def append_condition_footer(ch: QolChannel, body: str) -> str:
    if not ch.text_only:
        return body
    url = CONDITION_LP_FOOTER.get(ch.key)
    if not url:
        return body
    return body + CONDITION_FOOTER_LINE.format(url=url)


def fit_text_only_post(ch: QolChannel, body: str) -> tuple[str, bool]:
    """共感投稿+フッターが上限内に収まるよう調整。戻り値: (投稿文, trimmed)"""
    base = body.strip()
    limit = core.post_char_limit()
    post = append_condition_footer(ch, base)
    if core.x_weighted_length(post) <= limit:
        return post, False
    url = CONDITION_LP_FOOTER.get(ch.key, "")
    footer = CONDITION_FOOTER_LINE.format(url=url) if url else ""
    trimmed = True
    while len(base) > 20 and core.x_weighted_length(base + footer) > limit:
        base = base[:-1]
    return base.rstrip() + footer, trimmed


LOG_FIELDS = [
    "生成日",
    "channel",
    "csv_no",
    "投稿予定日時",
    "buffer_post_id",
    "status",
    "備考",
]


def load_state() -> dict:
    if not STATE_PATH.is_file():
        return {"indices": {c.key: 0 for c in QOL_CHANNELS}}
    with STATE_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    indices = data.get("indices") or {}
    for c in QOL_CHANNELS:
        indices.setdefault(c.key, 0)
    data["indices"] = indices
    return data


def save_state(data: dict) -> None:
    STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_csv_rows(path: Path, *, text_only: bool) -> list[tuple[str, str, str]]:
    """(no, body, url) のリスト。url は text_only なら空文字。"""
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        raise ValueError(f"CSV にデータ行がありません: {path}")
    header = [h.strip().lower() for h in rows[0]]
    out: list[tuple[str, str, str]] = []

    if text_only or "text" in header:
        try:
            text_idx = header.index("text")
        except ValueError as e:
            raise ValueError(f"text 列がありません: {path}") from e
        for i, row in enumerate(rows[1:], 1):
            if len(row) <= text_idx:
                continue
            body = row[text_idx].strip()
            if body:
                out.append((str(i), body, ""))
    else:
        for row in rows[1:]:
            if len(row) < 3:
                continue
            no, body, url = row[0].strip(), row[1].strip(), row[2].strip()
            if body and url:
                out.append((no, body, url))

    if not out:
        raise ValueError(f"有効行がありません: {path}")
    return out


def prepare_post_text(ch: QolChannel, body: str, url: str) -> tuple[str, str, int, bool]:
    """戻り値: (投稿文, 表示用note_suffix, 加重字数, trimmed)。"""
    if ch.text_only:
        body_t, trimmed = fit_text_only_post(ch, body)
        n = core.x_weighted_length(body_t)
        limit = core.post_char_limit()
        if n > limit:
            raise ValueError(f"投稿全文が{limit}加重字超過: {n}字")
        suffix = " trim" if trimmed else ""
        return body_t, f"{n}字{suffix}", n, trimmed

    body_t, link_t, post_text, trimmed = core.prepare_buffer_post(body, url)
    n = core.x_post_total_length(body_t, link_t)
    limit = core.post_char_limit()
    if n > limit:
        raise ValueError(f"投稿全文{n}加重字（上限{limit}）")
    return post_text, f"{n}字", n, trimmed


def pick_row(rows: list[tuple[str, str, str]], index: int) -> tuple[int, tuple[str, str, str]]:
    """index は次に使う0始まり。戻り値は (新index, row)。"""
    i = index % len(rows)
    return index + 1, rows[i]


def append_log(entry: dict[str, str]) -> None:
    write_header = not LOG_PATH.is_file()
    with LOG_PATH.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if write_header:
            w.writeheader()
        w.writerow({k: entry.get(k, "") for k in LOG_FIELDS})


def upload_channel(
    ch: QolChannel,
    *,
    api_key: str,
    channel_id: str,
    row_index: int,
    base: date,
    dry_run: bool,
    sleep_sec: float,
) -> tuple[int, str | None, str]:
    """戻り値: (new_index, buffer_post_id|None, note)。"""
    path = csv_path(ch)
    if not path.is_file():
        raise FileNotFoundError(f"CSV がありません: {path}")

    rows = read_csv_rows(path, text_only=ch.text_only)
    new_index, (no, body, url) = pick_row(rows, row_index)
    due = due_at_iso(base, ch)

    try:
        post_text, len_note, n, trimmed = prepare_post_text(ch, body, url)
    except ValueError as e:
        return row_index, None, str(e)

    if dry_run:
        print(
            f"  [dry-run] {ch.label_ja} No.{no} {len(post_text)}字 "
            f"dueAt={due} trim={trimmed}"
        )
        return new_index, None, "dry-run"

    post_id, error = create_buffer_post(channel_id, post_text, api_key, due_at=due)
    if post_id:
        note = f"ok; {n}字; dueAt={due}; csv_no={no}"
        if trimmed:
            note = f"trim; {note}"
        print(f"  OK {ch.label_ja} {post_id} ({n}字 dueAt={due})")
        if sleep_sec > 0:
            time.sleep(sleep_sec)
        return new_index, post_id, note

    err_msg = (error or "unknown")[:500]
    print(f"  ERR {ch.label_ja}: {err_msg[:120]}")
    if is_rate_limit_error(err_msg):
        return row_index, None, f"429: {err_msg}"
    return row_index, None, err_msg


def main() -> None:
    parser = argparse.ArgumentParser(description="QOL 5ch X → Buffer（各1本/日）")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="同日に既に実行済みでも再投入（通常はスキップ）",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=30.0,
        help="チャネル間の待機秒（Buffer 429 対策・既定30）",
    )
    parser.add_argument(
        "--channels",
        type=str,
        default="",
        help="指定チャネルのみ（カンマ区切り: sleep,focus,fatigue,haircare,stress）。復旧用",
    )
    parser.add_argument(
        "--content-date",
        type=str,
        default="",
        help="生成日を上書き（YYYY-MM-DD）。欠落日の復旧用",
    )
    args = parser.parse_args()

    core.load_env()
    api_key = os.environ.get("BUFFER_API_KEY", "").strip()
    channel_id = os.environ.get("BUFFER_CHANNEL_ID", "").strip()
    if not args.dry_run and (not api_key or not channel_id):
        raise SystemExit("BUFFER_API_KEY と BUFFER_CHANNEL_ID を .env に設定してください")

    today = date.today()
    content_date: date | None = None
    if args.content_date:
        content_date = date.fromisoformat(args.content_date)
    log_date = (content_date or today).isoformat()
    state = load_state()
    channel_filter = [
        k.strip() for k in args.channels.split(",") if k.strip()
    ]
    if channel_filter:
        valid = {c.key for c in QOL_CHANNELS}
        unknown = [k for k in channel_filter if k not in valid]
        if unknown:
            raise SystemExit(f"未知の channel: {unknown}（有効: {sorted(valid)}）")
    channels = [
        ch
        for ch in QOL_CHANNELS
        if not channel_filter or ch.key in channel_filter
    ]
    if not channels:
        raise SystemExit("処理対象チャネルがありません")

    partial = bool(channel_filter)
    if (
        state.get("last_run_date") == today.isoformat()
        and not args.force
        and not args.dry_run
        and not partial
        and content_date is None
    ):
        print(f"[upload_qol_x] skip: 本日({today.isoformat()})は既に実行済み（--force で再実行）")
        return

    base = schedule_base_date(content_date)
    print(
        f"[upload_qol_x] base_date={base.isoformat()} "
        f"channels={len(channels)}/{len(QOL_CHANNELS)}"
    )

    ok = err = 0
    for ch in channels:
        if is_channel_paused(ch.key):
            print(f"  SKIP {ch.label_ja}: automation_state で停止中")
            continue
        idx = int(state["indices"].get(ch.key, 0))
        try:
            new_idx, post_id, note = upload_channel(
                ch,
                api_key=api_key,
                channel_id=channel_id,
                row_index=idx,
                base=base,
                dry_run=args.dry_run,
                sleep_sec=args.sleep if ch != channels[-1] else 0,
            )
        except FileNotFoundError as e:
            print(f"  SKIP {ch.label_ja}: {e}")
            err += 1
            continue

        if args.dry_run:
            state["indices"][ch.key] = new_idx
            continue

        entry = {
            "生成日": log_date,
            "channel": ch.key,
            "csv_no": note.split("csv_no=")[-1] if "csv_no=" in note else "",
            "投稿予定日時": due_at_iso(base, ch),
            "buffer_post_id": post_id or "",
            "status": "uploaded" if post_id else "error",
            "備考": note[:500],
        }
        append_log(entry)

        if post_id:
            state["indices"][ch.key] = new_idx
            ok += 1
        else:
            err += 1
            if note.startswith("429:"):
                print("[upload_qol_x] 429 — 残りチャネルは次回 run_daily で再試行")
                break

    if not args.dry_run:
        if not partial and (content_date is None or content_date == today):
            state["last_run_date"] = today.isoformat()
        save_state(state)

    print(f"[upload_qol_x] uploaded={ok} error={err} dry_run={args.dry_run}")


if __name__ == "__main__":
    main()
