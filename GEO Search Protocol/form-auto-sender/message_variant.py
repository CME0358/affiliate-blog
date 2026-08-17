"""
message_variant.py — ARI 送信本文の maxlength フォールバック選択

Priority 1: ARI_MESSAGE_V1（通常版）
Priority 2: ARI_MESSAGE_COMPACT（maxlength 超過時のみ）
Skip: Compact も超過する場合（truncate 禁止）
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from templates.messages import ARI_MESSAGE_COMPACT, ARI_MESSAGE_V1

VARIANT_V1 = "ARI_MESSAGE_V1"
VARIANT_V2 = "ARI_MESSAGE_V2"
VARIANT_COMPACT = "ARI_MESSAGE_COMPACT"
VARIANT_SKIP = "SKIP"

FALLBACK_EXCEEDS_MAX = "message_exceeds_maxlength"
SKIP_COMPACT_EXCEEDS = "compact_message_exceeds_maxlength"
SKIP_INSUFFICIENT_CAPACITY = "insufficient_message_capacity"
SKIP_V2_EXCEEDS_MAX = "v2_message_exceeds_maxlength"
FALLBACK_VALIDATION_TOO_LONG = "validation_too_long_after_v1_fill"

MIN_MESSAGE_CAPACITY = 300


@dataclass
class MessageSelection:
    variant: str
    message: str
    message_length: int
    detected_maxlength: int | None
    fallback_reason: str | None
    skip_reason: str | None
    skipped: bool

    def to_log_fields(self) -> dict[str, Any]:
        out = {
            "message_variant": self.variant if not self.skipped else VARIANT_SKIP,
            "message_length": self.message_length,
            "detected_maxlength": self.detected_maxlength,
        }
        if self.fallback_reason:
            out["fallback_reason"] = self.fallback_reason
        if self.skip_reason:
            out["skip_reason"] = self.skip_reason
        return out


def build_ari_message_v1(lp_url: str) -> str:
    return ARI_MESSAGE_V1.format(lp_url=lp_url)


def build_ari_message_compact(lp_url: str) -> str:
    return ARI_MESSAGE_COMPACT.format(lp_url=lp_url)


def select_ari_message_variant(lp_url: str, maxlength: int | None) -> MessageSelection:
    """
    maxlength が None の場合は推測せず V1 を返す。
    maxlength がある場合のみ V1 → COMPACT → SKIP を判定。
    """
    v1 = build_ari_message_v1(lp_url)
    compact = build_ari_message_compact(lp_url)

    if maxlength is None:
        return MessageSelection(
            variant=VARIANT_V1,
            message=v1,
            message_length=len(v1),
            detected_maxlength=None,
            fallback_reason=None,
            skip_reason=None,
            skipped=False,
        )

    if maxlength < MIN_MESSAGE_CAPACITY:
        return MessageSelection(
            variant=VARIANT_SKIP,
            message="",
            message_length=0,
            detected_maxlength=maxlength,
            fallback_reason=None,
            skip_reason=SKIP_INSUFFICIENT_CAPACITY,
            skipped=True,
        )

    if len(v1) <= maxlength:
        return MessageSelection(
            variant=VARIANT_V1,
            message=v1,
            message_length=len(v1),
            detected_maxlength=maxlength,
            fallback_reason=None,
            skip_reason=None,
            skipped=False,
        )

    if len(compact) <= maxlength:
        return MessageSelection(
            variant=VARIANT_COMPACT,
            message=compact,
            message_length=len(compact),
            detected_maxlength=maxlength,
            fallback_reason=FALLBACK_EXCEEDS_MAX,
            skip_reason=None,
            skipped=False,
        )

    return MessageSelection(
        variant=VARIANT_SKIP,
        message="",
        message_length=0,
        detected_maxlength=maxlength,
        fallback_reason=None,
        skip_reason=SKIP_COMPACT_EXCEEDS,
        skipped=True,
    )


_GET_MAXLENGTH_JS = r"""
(selector) => {
  if (!selector) return null;
  const el = document.querySelector(selector);
  if (!el) return null;
  const tag = el.tagName.toLowerCase();
  if (tag === 'select') return null;
  if (tag !== 'textarea' && tag !== 'input') return null;
  const ml = el.maxLength;
  if (typeof ml === 'number' && ml > 0) return ml;
  const attr = el.getAttribute('maxlength');
  if (attr) {
    const n = parseInt(attr, 10);
    if (!isNaN(n) && n > 0) return n;
  }
  return null;
}
"""

_CHECK_VALIDITY_JS = r"""
(selector) => {
  if (!selector) return { tooLong: false, maxLength: null };
  const el = document.querySelector(selector);
  if (!el) return { tooLong: false, maxLength: null };
  const ml = el.maxLength;
  const maxLength = (typeof ml === 'number' && ml > 0) ? ml : null;
  const tooLong = !!(el.validity && el.validity.tooLong);
  return { tooLong, maxLength };
}
"""


async def detect_message_field_maxlength(page, fields: dict) -> int | None:
    """本文フィールドの maxlength を DOM から取得。取得不可なら None。"""
    candidates: list[str] = []
    primary = (fields.get("message_field") or "").strip()
    if primary:
        candidates.append(primary)

    try:
        from form_field_resolver import _FIND_MESSAGE_FIELD_JS

        alt = await page.evaluate(_FIND_MESSAGE_FIELD_JS)
        if alt and alt not in candidates:
            candidates.append(alt)
    except Exception:
        pass

    for sel in candidates:
        try:
            ml = await page.evaluate(_GET_MAXLENGTH_JS, sel)
            if isinstance(ml, int) and ml > 0:
                return ml
        except Exception:
            continue
    return None


async def resolve_ari_message_for_form(
    page,
    fields: dict,
    lp_url: str,
    *,
    allow_validation_fallback: bool = False,
) -> MessageSelection:
    """
    フォーム DOM 上の maxlength に基づき送信本文を選択。
    allow_validation_fallback=True のときのみ、上限不明で validity.tooLong の場合 COMPACT を試行。
    """
    maxlength = await detect_message_field_maxlength(page, fields)
    selection = select_ari_message_variant(lp_url, maxlength)

    if selection.skipped:
        return selection

    if maxlength is not None or not allow_validation_fallback:
        return selection

    # 上限不明 + fill-no-submit: V1 入力後に validity.tooLong なら COMPACT を試行
    primary = (fields.get("message_field") or "").strip()
    if not primary:
        return selection

    try:
        await page.fill(primary, selection.message)
        check = await page.evaluate(_CHECK_VALIDITY_JS, primary)
        if not check.get("tooLong"):
            return selection

        compact = build_ari_message_compact(lp_url)
        await page.fill(primary, compact)
        check2 = await page.evaluate(_CHECK_VALIDITY_JS, primary)
        if check2.get("tooLong"):
            return MessageSelection(
                variant=VARIANT_SKIP,
                message="",
                message_length=0,
                detected_maxlength=check2.get("maxLength"),
                fallback_reason=FALLBACK_VALIDATION_TOO_LONG,
                skip_reason=SKIP_COMPACT_EXCEEDS,
                skipped=True,
            )

        effective_max = check2.get("maxLength") or check.get("maxLength")
        return MessageSelection(
            variant=VARIANT_COMPACT,
            message=compact,
            message_length=len(compact),
            detected_maxlength=effective_max,
            fallback_reason=FALLBACK_VALIDATION_TOO_LONG,
            skip_reason=None,
            skipped=False,
        )
    except Exception:
        return selection


def format_selection_log_line(selection: MessageSelection) -> str:
    """コンソール / ログ用の1行。"""
    parts = [
        f"message_variant={selection.to_log_fields()['message_variant']}",
        f"message_length={selection.message_length}",
    ]
    if selection.detected_maxlength is not None:
        parts.append(f"detected_maxlength={selection.detected_maxlength}")
    if selection.fallback_reason:
        parts.append(f"fallback_reason={selection.fallback_reason}")
    if selection.skip_reason:
        parts.append(f"skip_reason={selection.skip_reason}")
    return " ".join(parts)


def selection_as_dict(selection: MessageSelection) -> dict[str, Any]:
    return asdict(selection)
