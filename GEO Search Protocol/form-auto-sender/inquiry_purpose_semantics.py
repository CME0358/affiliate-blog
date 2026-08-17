"""
inquiry_purpose_semantics.py — Generic inquiry-purpose choice compatibility.

Fail-closed: never select a semantically false purpose to satisfy required validation.
"""

from __future__ import annotations

import re
from typing import Any

INQUIRY_PURPOSE_COMPATIBLE = "INQUIRY_PURPOSE_COMPATIBLE"
INQUIRY_PURPOSE_INCOMPATIBLE = "INQUIRY_PURPOSE_INCOMPATIBLE"
INQUIRY_PURPOSE_AMBIGUOUS = "INQUIRY_PURPOSE_AMBIGUOUS"

REASON_NO_COMPATIBLE = "inquiry_purpose_no_compatible_option"
REASON_AMBIGUOUS = "inquiry_purpose_ambiguous"

# Higher semantic closeness to GENERAL_INQUIRY = lower rank number (preferred first).
_COMPATIBLE_RANKED: tuple[tuple[int, tuple[str, ...]], ...] = (
    (0, ("一般のお問い合わせ", "一般お問い合わせ")),
    (1, ("お問い合わせ",)),
    (2, ("その他のお問い合わせ",)),
    (3, ("その他のご用件", "その他のご相談", "その他ご相談")),
    (4, ("ご相談", "ご依頼")),
    (5, ("法人のお問い合わせ", "法人お問い合わせ")),
    (6, ("営業・提携", "取材・その他")),
    (7, ("その他", "other")),
)

_INCOMPATIBLE_PATTERNS: tuple[str, ...] = (
    "資料請求",
    "カタログ請求",
    "見積依頼",
    "見積もり依頼",
    "無料見積",
    "現地調査",
    "来店予約",
    "訪問予約",
    "予約",
    "初診予約",
    "再診予約",
    "治療相談",
    "カウンセリング予約",
    "来院相談",
    "症状について",
    "工事依頼",
    "施工依頼",
    "商品購入",
    "サンプル請求",
    "体験予約",
    "採用",
    "求人",
    "リクルート",
    "recruit",
    "アフターサービス",
    "修理",
    "クレーム",
    "既存顧客",
    "既存顧客向け",
    "オーナー向け",
    "協力会社応募",
    "業者登録",
    "患者様専用",
    "会員専用",
    "患者様",
    "catalog",
    "カタログ",
    "mitsumori",
    "estimate",
    "reservation",
    "appointment",
)

_INQUIRY_GROUP_MARKERS: tuple[str, ...] = (
    "お問い合わせ種類",
    "お問い合わせ項目",
    "お問い合わせ内容",
    "問い合わせ種類",
    "問い合わせ項目",
    "問合せ種類",
    "問合せ項目",
    "ご用件",
    "用件",
    "inquiry",
    "mailtonum",
    "category",
    "purpose",
    "catalog",
    "種別",
    "ご希望の内容",
)

_NON_INQUIRY_GROUP_MARKERS: tuple[str, ...] = (
    "法人",
    "個人",
    "都道府県",
    "prefecture",
    "連絡方法",
    "contact method",
    "同意",
    "consent",
    "privacy",
    "個人情報",
    "リフォーム箇所",
    "施工内容",
    "予算",
    "キッチン",
    "浴室",
    "外壁",
    "屋根",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _option_blob(option: dict[str, Any], *, context: str = "") -> str:
    parts = [
        option.get("label") or "",
        option.get("value") or "",
        option.get("id") or "",
        context or "",
    ]
    return _norm(" ".join(parts))


def _contains_any(blob: str, patterns: tuple[str, ...]) -> bool:
    low = blob.lower()
    for pat in patterns:
        if pat.lower() in low:
            return True
    return False


def is_inquiry_purpose_group(group: dict[str, Any], *, category: str | None = None) -> bool:
    """True when the choice group semantically represents inquiry purpose / ご用件."""
    cat = category or group.get("_category") or ""
    if cat == "INQUIRY_CATEGORY":
        return True
    if cat in {"CONSENT", "PREFECTURE", "CUSTOMER_TYPE", "CONTACT_METHOD", "SERVICE_TYPE"}:
        return False

    blob = _norm(f"{group.get('context', '')} {group.get('name', '')}")
    if _contains_any(blob, _NON_INQUIRY_GROUP_MARKERS):
        # Customer-type groups can mention お問い合わせ in page chrome — require explicit markers.
        if cat != "UNKNOWN":
            return False
    return _contains_any(blob, _INQUIRY_GROUP_MARKERS)


def classify_inquiry_purpose_option(
    option: dict[str, Any],
    *,
    context: str = "",
) -> tuple[str, int | None]:
    """
    Classify one option.
    Returns (classification, compatible_rank_or_none).
    """
    label_blob = _option_blob(option, context="")
    full_blob = _option_blob(option, context=context)
    if not label_blob:
        return INQUIRY_PURPOSE_AMBIGUOUS, None

    # Incompatible signals win — use label + field context (e.g. catalog / 資料).
    if _contains_any(full_blob, _INCOMPATIBLE_PATTERNS):
        if label_blob.strip() in ("その他", "other", "その他のお問い合わせ"):
            pass
        else:
            return INQUIRY_PURPOSE_INCOMPATIBLE, None

    for rank, patterns in _COMPATIBLE_RANKED:
        for pat in patterns:
            if pat.lower() in label_blob.lower():
                return INQUIRY_PURPOSE_COMPATIBLE, rank

    if _contains_any(label_blob, ("問い合わせ", "問合せ", "inquiry", "contact")):
        return INQUIRY_PURPOSE_AMBIGUOUS, None

    return INQUIRY_PURPOSE_AMBIGUOUS, None


def resolve_inquiry_purpose_choice(group: dict[str, Any]) -> tuple[dict | None, str, str]:
    """
    Returns (option, status, reason).
    status: selected | skip | unsuitable
    reason: inquiry_purpose_* when unsuitable
    """
    opts = group.get("options") or []
    if not opts:
        return None, "skip", ""

    context = group.get("context") or ""
    classified: list[tuple[dict, str, int | None]] = []
    for opt in opts:
        cls, rank = classify_inquiry_purpose_option(opt, context=context)
        classified.append((opt, cls, rank))

    compatible = [(opt, rank) for opt, cls, rank in classified if cls == INQUIRY_PURPOSE_COMPATIBLE]
    if compatible:
        compatible.sort(key=lambda item: (item[1], _norm(item[0].get("label") or "")))
        return compatible[0][0], "selected", ""

    if not group.get("required"):
        return None, "skip", ""

    has_incompatible = any(cls == INQUIRY_PURPOSE_INCOMPATIBLE for _, cls, _ in classified)
    has_ambiguous = any(cls == INQUIRY_PURPOSE_AMBIGUOUS for _, cls, _ in classified)

    if has_incompatible and not has_ambiguous:
        return None, "unsuitable", REASON_NO_COMPATIBLE
    if has_ambiguous and not has_incompatible:
        return None, "unsuitable", REASON_AMBIGUOUS
    if has_incompatible:
        return None, "unsuitable", REASON_NO_COMPATIBLE
    return None, "unsuitable", REASON_AMBIGUOUS


def audit_selected_purpose(label: str, *, context: str = "", category: str = "") -> str:
    """Map a historically selected label to COMPATIBLE | INCOMPATIBLE | AMBIGUOUS | NOT_APPLICABLE."""
    if not label and category not in ("INQUIRY_CATEGORY",):
        return "NOT_APPLICABLE"
    if not label:
        return "NOT_APPLICABLE"
    cls, _ = classify_inquiry_purpose_option({"label": label}, context=context)
    if cls == INQUIRY_PURPOSE_COMPATIBLE:
        return "COMPATIBLE"
    if cls == INQUIRY_PURPOSE_INCOMPATIBLE:
        return "INCOMPATIBLE"
    return "AMBIGUOUS"
