"""QOL コンディション改善メディア X 投稿スケジュール（同一 Buffer チャネル）。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import rakuten_core as core

QOLMEDIA_DIR = Path(__file__).resolve().parent.parent.parent
STATE_PATH = Path(__file__).resolve().parent / "qol_x_state.json"
LOG_PATH = Path(__file__).resolve().parent / "qol_x_upload_log.csv"


@dataclass(frozen=True)
class QolChannel:
    key: str
    label_ja: str
    csv_name: str
    hour: int
    minute: int
    extra_day_offset: int  # 投稿基準日からの追加日数
    text_only: bool = False  # True = URLなし共感投稿（condition CSV）


# 楽天アフィ: run_daily.sh 内 upload_buffer_drafts.py を停止（2026-06-06〜）

# 現行7ch — コンディション改善 + 収益導線（JST・extra_day_offset=0）
# pet/factoring は 2026-08-05 再開（2026-06-06 停止分を復帰）
QOL_CHANNELS: tuple[QolChannel, ...] = (
    QolChannel("fatigue", "疲労", "x_posts_fatigue_49.csv", 8, 0, 0, text_only=True),
    QolChannel("focus", "集中力", "x_posts_focus_49.csv", 12, 0, 0, text_only=True),
    QolChannel("pet", "ペット", "x_posts_pet_49.csv", 15, 0, 0),
    QolChannel("stress", "ストレス", "x_posts_stress_49.csv", 18, 0, 0, text_only=True),
    QolChannel("factoring", "ファクタリング", "x_posts_factoring_49.csv", 20, 0, 0),
    QolChannel("sleep", "睡眠", "x_posts_sleep_49.csv", 21, 0, 0),
    QolChannel("haircare", "ヘアケア", "x_posts_hc_49.csv", 23, 0, 0),
)


def csv_path(ch: QolChannel) -> Path:
    return QOLMEDIA_DIR / ch.csv_name


def schedule_base_date(content_date: date | None = None) -> date:
    """生成日 + SCHEDULE_DATE_OFFSET_DAYS（既定+1日）。"""
    return core.post_schedule_date(content_date or date.today())


def due_at_iso(base: date, ch: QolChannel) -> str:
    d = base + timedelta(days=ch.extra_day_offset)
    dt = datetime(d.year, d.month, d.day, ch.hour, ch.minute, tzinfo=core.JST)
    return dt.isoformat(timespec="seconds")


def daily_schedule_summary(base: date | None = None) -> list[tuple[str, str]]:
    b = schedule_base_date(base)
    return [(c.label_ja, due_at_iso(b, c)) for c in QOL_CHANNELS]
