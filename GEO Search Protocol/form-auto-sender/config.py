# config.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# 送信者情報
SENDER_NAME    = "佐々木 健之"
SENDER_COMPANY = "合同会社コア・リテール"
SENDER_EMAIL   = os.environ.get("SENDER_EMAIL", "your@email.com")  # 環境変数優先

# 連絡先（フォーム自動入力）— .env 必須（実PIIのフォールバックは持たない）
def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"必須環境変数 {name} が未設定です。.env を確認してください。"
        )
    return value


SENDER_PHONE        = _require_env("SENDER_PHONE")
SENDER_POSTAL_CODE  = _require_env("SENDER_POSTAL_CODE")
SENDER_PREFECTURE   = _require_env("SENDER_PREFECTURE")

# 住所（パターンに応じて使い分け）
# ・1フィールドにまとまるフォーム → SENDER_ADDRESS_FULL
# ・都道府県が別selectのフォーム   → select後に SENDER_ADDRESS_WITHOUT_PREFECTURE を入れる
# ・住所1／住所2に分かれるフォーム → LINE1 / LINE2
SENDER_ADDRESS_FULL = _require_env("SENDER_ADDRESS_FULL")
SENDER_ADDRESS_LINE1 = _require_env("SENDER_ADDRESS_LINE1")
SENDER_ADDRESS_LINE2 = _require_env("SENDER_ADDRESS_LINE2")

# --- LP URL 固定（文面・ログ共通）---
# 動的 aiscan URL に戻すときは LP_URL_OVERRIDE = "" にする（または .env で空指定）
LP_URL_OVERRIDE = os.environ.get(
    "LP_URL_OVERRIDE",
    "https://readiness.coaretail.com/report/",
)

# Anthropic API
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "sk-...")

# 送信間隔（秒）— 実際に送信した場合のみ待機
SEND_INTERVAL_MIN = 2
SEND_INTERVAL_MAX = 4

# 1日の処理上限（本番のみ適用）
# 当日のログ（成功+手動確認+エラー）の合計がこの件数に達したら、それ以上は処理しない
DAILY_OUTCOME_LIMIT = 300

# 同一企業への再送インターバル（日）
RESEND_INTERVAL_DAYS = 30

# 送信対象外業種（スクレイパー側でも除外済み）
# 既存ログに残っている分の再処理も防ぐ
SKIP_INDUSTRIES = [
    "整骨院",
    "接骨院",
    "鍼灸院",
    "整体院",
    "歯科",
    "歯科クリニック",
]

SKIP_AREAS = [
    "渋谷区",
    "中央区",
]

# 失敗理由ごとの再試行クールダウン（日）。P0: 同一企業の毎日再試行を止める
FAILURE_COOLDOWN_DAYS: dict[str, int] = {
    "form_not_found": 30,
    "submit_button": 7,
    "no_form_chain": 14,
    "reservation_only": 30,
    "external_booking_only": 30,
    "pdf_or_file_download": 30,
    "no_website": 30,
    "site_down": 7,
    "timeout": 7,
    "pending_recaptcha": 7,
    "other": 14,
}

# フォーム探索の最終手段: Google 検索（{会社名} お問い合わせ）
ENABLE_GOOGLE_FORM_SEARCH = os.environ.get("ENABLE_GOOGLE_FORM_SEARCH", "1").strip().lower() in (
    "1",
    "true",
    "yes",
)

# form_finder ハング対策（1社あたり上限）
FORM_FIND_TOTAL_TIMEOUT_SEC = int(os.environ.get("FORM_FIND_TOTAL_TIMEOUT_SEC", "60"))
FORM_FIND_MAX_NAVIGATIONS = int(os.environ.get("FORM_FIND_MAX_NAVIGATIONS", "28"))
FORM_FIND_MAX_LINK_FOLLOWS = int(os.environ.get("FORM_FIND_MAX_LINK_FOLLOWS", "8"))
FORM_FIND_MAX_IFRAME_FOLLOWS = int(os.environ.get("FORM_FIND_MAX_IFRAME_FOLLOWS", "5"))
FORM_FIND_MAX_CONTACT_PATHS = int(os.environ.get("FORM_FIND_MAX_CONTACT_PATHS", "10"))
FORM_FIND_MAX_GOOGLE_FOLLOWS = int(os.environ.get("FORM_FIND_MAX_GOOGLE_FOLLOWS", "3"))
CHAIN_SITE_MAX_NAVIGATIONS = int(os.environ.get("CHAIN_SITE_MAX_NAVIGATIONS", "8"))
CHAIN_SITE_MAX_PARENT_LEVELS = int(os.environ.get("CHAIN_SITE_MAX_PARENT_LEVELS", "1"))

# reCAPTCHA対策（必要な場合はTrueに変更）
USE_2CAPTCHA    = False
CAPTCHA_API_KEY = ""

# パス設定
BASE_DIR  = Path(__file__).parent
LOG_DIR   = BASE_DIR / "logs"

# launchd / ダッシュボード連動の停止フラグ（automation_state.py が更新）
from automation_state import AUTOMATION_STATE_PATH  # noqa: F401 — 後方互換

# Obsidian Vault ルート（@プレフィックスのパス解決に使用）
VAULT_ROOT = BASE_DIR.parent.parent.parent  # form-auto-sender/ → GEO Search Protocol/ → 10_Projects/ → Obsidian_Vault/

# 入力ディレクトリ：スクレイパーが毎日 MD を出力する場所
INPUT_DIR = VAULT_ROOT / "40_Sales" / "商談メモ" / "リスト"

# ログファイルパス
LOG_SENT    = LOG_DIR / "sent.csv"
LOG_ERROR   = LOG_DIR / "error.csv"
LOG_PERMANENT_SKIP = LOG_DIR / "permanent_skip.csv"
LOG_PENDING = LOG_DIR / "pending.csv"
# 手動除外（誤送信の取り消し・監査用。送信済みインデックスから外した企業を記録）
LOG_MANUALLY_EXCLUDED = LOG_DIR / "manually_excluded.csv"
FAILURE_COOLDOWN_INDEX = LOG_DIR / ".failure_cooldown.csv"
# フォームフィールド解析キャッシュ（form_url → セレクタ JSON）。Claude API 削減用
FORM_FIELD_CACHE_PATH = LOG_DIR / "form_field_cache.json"
FORM_FIELD_CACHE_TTL_DAYS = 90
# Claude に渡す HTML の上限（フォーム周辺のみ抽出後）
HTML_MAX_CHARS_FOR_CLAUDE = 12_000
