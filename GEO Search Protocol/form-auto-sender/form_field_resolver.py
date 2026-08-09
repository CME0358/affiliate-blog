"""
form_field_resolver.py — フォームフィールド解決（API コスト削減）

優先順:
  1. キャッシュ（form_url）
  2. DOM ルールベース（Playwright、API 不要）
  3. Claude API（短縮 HTML のみ）
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    FORM_FIELD_CACHE_PATH,
    FORM_FIELD_CACHE_TTL_DAYS,
    HTML_MAX_CHARS_FOR_CLAUDE,
    LOG_DIR,
)

JST = timezone(timedelta(hours=9))

FORM_ANALYSIS_PROMPT = """\
以下はWebサイトの問い合わせフォーム周辺HTMLです。
入力フィールドを特定し、JSONのみ返してください。

返すべきフィールド:
- name_field, furigana_name_field, furigana_format ("hiragana"|"katakana"|null)
- company_field, email_field, phone_field
- postal_code_field, prefecture_field, prefecture_option_value
- address_field, address_line1_field, address_line2_field
- message_field, submit_button
- gender_field, age_field, gender_other_value, age_other_value

セレクタはCSS形式。存在しないキーはnull。説明文不要。

HTML:
{html}
"""

# DOM からフィールドを推定（Claude 不要）
_EXTRACT_FIELDS_JS = r"""
() => {
  const result = {
    name_field: null,
    furigana_name_field: null,
    furigana_format: null,
    company_field: null,
    email_field: null,
    phone_field: null,
    postal_code_field: null,
    prefecture_field: null,
    prefecture_option_value: null,
    address_field: null,
    address_line1_field: null,
    address_line2_field: null,
    message_field: null,
    submit_button: null,
    gender_field: null,
    age_field: null,
    gender_other_value: null,
    age_other_value: null,
  };

  function cssEscape(s) {
    if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(s);
    return String(s).replace(/([!"#$%&'()*+,.\/:;<=>?@[\\\]^`{|}~])/g, '\\$1');
  }

  function selectorFor(el) {
    if (!el || el.nodeType !== 1) return null;
    if (el.id) return '#' + cssEscape(el.id);
    const name = el.getAttribute('name');
    if (name) {
      const tag = el.tagName.toLowerCase();
      const esc = name.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
      return tag + '[name="' + esc + '"]';
    }
    return null;
  }

  function metaText(el) {
    const parts = [];
    ['name', 'id', 'placeholder', 'aria-label', 'title'].forEach((a) => {
      const v = el.getAttribute && el.getAttribute(a);
      if (v) parts.push(v);
    });
    if (el.type) parts.push(el.type);
    const labels = el.labels ? Array.from(el.labels) : [];
    labels.forEach((lb) => parts.push(lb.textContent || ''));
    const parentLabel = el.closest('label');
    if (parentLabel) parts.push(parentLabel.textContent || '');
    const tr = el.closest('tr');
    if (tr) {
      const th = tr.querySelector('th');
      if (th) parts.push(th.textContent || '');
    }
    const dt = el.closest('dl')?.querySelector('dt');
    if (dt) parts.push(dt.textContent || '');
    return parts.join(' ').toLowerCase();
  }

  function assignOnce(key, el) {
    if (result[key]) return;
    const sel = selectorFor(el);
    if (sel) result[key] = sel;
  }

  function matchAny(text, kws) {
    return kws.some((k) => text.includes(k));
  }

  const forms = document.querySelectorAll('form');
  const controls = [];
  if (forms.length) {
    forms.forEach((f) => {
      f.querySelectorAll('input, textarea, select, button').forEach((el) => controls.push(el));
    });
  } else {
    document.querySelectorAll('input, textarea, select, button').forEach((el) => controls.push(el));
  }

  for (const el of controls) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    const t = metaText(el);

    if (type === 'hidden') continue;

    if (type === 'submit' || (tag === 'button' && type !== 'button' && type !== 'reset')) {
      if (type === 'submit' || matchAny(t, ['送信', '確認', 'submit', 'send', '進む', '次へ'])) {
        assignOnce('submit_button', el);
      }
      continue;
    }

    if (type === 'radio' || type === 'checkbox') {
      if (matchAny(t, ['性別', 'gender', 'sex'])) assignOnce('gender_field', el);
      if (matchAny(t, ['年齢', 'age', '年代'])) assignOnce('age_field', el);
      continue;
    }

    if (
      tag !== 'select'
      && (
        tag === 'textarea'
        || (tag === 'input' && (type === 'text' || type === ''))
      )
      && matchAny(t, [
        'お問い合わせ', '問合せ', '問い合わせ', 'message', '内容', 'ご用件',
        'comment', 'inquiry', '備考', '相談', 'ご質問',
      ])
    ) {
      assignOnce('message_field', el);
    }
    if (matchAny(t, ['mail', 'メール', 'e-mail', 'email']) && tag === 'input') {
      assignOnce('email_field', el);
    }
    if (matchAny(t, ['会社', 'company', '法人', '店舗', '施設', '医院名', 'クリニック名'])) {
      assignOnce('company_field', el);
    }
    if (matchAny(t, ['フリガナ', 'ふりがな', 'カナ', 'kana', 'furigana'])) {
      assignOnce('furigana_name_field', el);
      if (matchAny(t, ['フリガナ', 'カナ', 'katakana'])) result.furigana_format = 'katakana';
      else if (matchAny(t, ['ふりがな', 'hiragana'])) result.furigana_format = 'hiragana';
      else if (!result.furigana_format) result.furigana_format = 'katakana';
    }
    if (
      matchAny(t, ['氏名', 'お名前', '担当者', 'name', 'なまえ'])
      && !matchAny(t, ['フリガナ', 'ふりがな', 'カナ', 'kana', '会社', 'company'])
    ) {
      assignOnce('name_field', el);
    }
    if (matchAny(t, ['電話', 'tel', 'phone', '携帯', '連絡先'])) {
      assignOnce('phone_field', el);
    }
    if (matchAny(t, ['郵便', 'zip', 'postal', '〒', 'yubin'])) {
      assignOnce('postal_code_field', el);
    }
    if (tag === 'select' && matchAny(t, ['都道府県', 'prefecture', 'todofuken'])) {
      assignOnce('prefecture_field', el);
      el.querySelectorAll('option').forEach((o) => {
        if ((o.textContent || '').includes('東京') && !result.prefecture_option_value) {
          result.prefecture_option_value = o.value;
        }
      });
    }
    if (matchAny(t, ['住所2', 'address2', '建物', 'マンション', 'ビル', '部屋'])) {
      assignOnce('address_line2_field', el);
    } else if (matchAny(t, ['住所1', 'address1', 'address_1', '丁目', '番地', '市区'])) {
      assignOnce('address_line1_field', el);
    } else if (matchAny(t, ['住所', 'address', '所在地']) && !result.address_line1_field) {
      assignOnce('address_field', el);
    }
  }

  if (!result.submit_button) {
    const hit = document.querySelector(
      'button[type="submit"], input[type="submit"], .wpcf7-submit, .mwform-submit'
    );
    if (hit) {
      const s = selectorFor(hit);
      if (s) result.submit_button = s;
    }
  }

  return result;
}
"""


def normalize_form_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    parsed = urlparse(u)
    path = parsed.path.rstrip("/") or "/"
    netloc = parsed.netloc.lower()
    scheme = (parsed.scheme or "https").lower()
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def _fields_usable(fields: dict[str, Any] | None) -> bool:
    if not fields or not isinstance(fields, dict):
        return False
    if fields.get("message_field"):
        return True
    if fields.get("email_field") and fields.get("name_field"):
        return True
    return False


def _ensure_cache_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _load_cache() -> dict[str, Any]:
    _ensure_cache_dir()
    if not FORM_FIELD_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(FORM_FIELD_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(data: dict[str, Any]) -> None:
    _ensure_cache_dir()
    FORM_FIELD_CACHE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _cache_entry_fresh(entry: dict[str, Any]) -> bool:
    raw = entry.get("cached_at")
    if not raw:
        return False
    try:
        cached = datetime.fromisoformat(str(raw))
        if cached.tzinfo is None:
            cached = cached.replace(tzinfo=JST)
    except ValueError:
        return False
    ttl = timedelta(days=FORM_FIELD_CACHE_TTL_DAYS)
    return datetime.now(JST) - cached < ttl


def get_cached_fields(form_url: str) -> dict[str, Any] | None:
    key = normalize_form_url(form_url)
    if not key:
        return None
    store = _load_cache()
    entry = store.get(key)
    if not entry or not _cache_entry_fresh(entry):
        return None
    fields = entry.get("fields")
    return fields if _fields_usable(fields) else None


def put_cached_fields(form_url: str, fields: dict[str, Any], source: str) -> None:
    key = normalize_form_url(form_url)
    if not key or not _fields_usable(fields):
        return
    store = _load_cache()
    store[key] = {
        "fields": fields,
        "source": source,
        "cached_at": datetime.now(JST).isoformat(timespec="seconds"),
    }
    _save_cache(store)


def extract_form_html_snippet(html: str) -> str:
    """
    フォーム周辺のみ抽出（script/style/コメント除去 → form タグ優先）。
    """
    html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<!--[\s\S]*?-->", "", html)

    forms = re.findall(r"<form[\s\S]*?</form>", html, flags=re.IGNORECASE)
    if forms:
        snippet = "\n".join(forms)
    else:
        parts: list[str] = []
        for tag in ("form", "fieldset", "input", "textarea", "select", "label", "button"):
            parts.extend(
                re.findall(rf"<{tag}[^>]*>[\s\S]*?(?:</{tag}>|>)", html, flags=re.IGNORECASE)
            )
        snippet = "\n".join(parts) if parts else html
        m = re.search(r"<body[^>]*>([\s\S]*?)</body>", html, flags=re.IGNORECASE)
        if not parts and m:
            snippet = m.group(1)

    snippet = re.sub(r"\s+", " ", snippet).strip()
    if len(snippet) > HTML_MAX_CHARS_FOR_CLAUDE:
        snippet = snippet[:HTML_MAX_CHARS_FOR_CLAUDE]
    return snippet


def _parse_claude_json(raw: str) -> dict[str, Any] | None:
    t = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
    if fence:
        t = fence.group(1).strip()
    start = t.find("{")
    end = t.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(t[start : end + 1])
    except json.JSONDecodeError:
        return None


def analyze_form_with_claude(html: str) -> dict[str, Any] | None:
    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY.startswith("sk-..."):
        return None
    trimmed = extract_form_html_snippet(html)
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": FORM_ANALYSIS_PROMPT.format(html=trimmed),
            }],
        )
        raw = response.content[0].text.strip()
        return _parse_claude_json(raw)
    except (IndexError, anthropic.APIError):
        return None


_FIND_MESSAGE_FIELD_JS = r"""
() => {
  function cssEscape(s) {
    if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(s);
    return String(s).replace(/([!"#$%&'()*+,.\/:;<=>?@[\\\]^`{|}~])/g, '\\$1');
  }
  function selectorFor(el) {
    if (!el || el.nodeType !== 1) return null;
    if (el.id) return '#' + cssEscape(el.id);
    const name = el.getAttribute('name');
    if (name) {
      const tag = el.tagName.toLowerCase();
      const esc = name.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
      return tag + '[name="' + esc + '"]';
    }
    return null;
  }
  function metaText(el) {
    const parts = [];
    ['name', 'id', 'placeholder', 'aria-label', 'title'].forEach((a) => {
      const v = el.getAttribute && el.getAttribute(a);
      if (v) parts.push(v);
    });
    if (el.type) parts.push(el.type);
    const labels = el.labels ? Array.from(el.labels) : [];
    labels.forEach((lb) => parts.push(lb.textContent || ''));
    const parentLabel = el.closest('label');
    if (parentLabel) parts.push(parentLabel.textContent || '');
    return parts.join(' ').toLowerCase();
  }
  function matchAny(text, kws) {
    return kws.some((k) => text.includes(k));
  }
  const kws = [
    'お問い合わせ', '問合せ', '問い合わせ', 'message', '内容', 'ご用件',
    'comment', 'inquiry', '備考', '相談', 'ご質問',
  ];
  const forms = document.querySelectorAll('form');
  const controls = [];
  if (forms.length) {
    forms.forEach((f) => {
      f.querySelectorAll('textarea, input').forEach((el) => controls.push(el));
    });
  } else {
    document.querySelectorAll('textarea, input').forEach((el) => controls.push(el));
  }
  for (const el of controls) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (type === 'hidden') continue;
    if (tag === 'select') continue;
    if (tag === 'textarea' || type === 'text' || type === '') {
      if (matchAny(metaText(el), kws)) {
        const sel = selectorFor(el);
        if (sel) return sel;
      }
    }
  }
  for (const el of controls) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (type === 'hidden' || tag === 'select') continue;
    if (tag === 'textarea') {
      const sel = selectorFor(el);
      if (sel) return sel;
    }
  }
  for (const el of controls) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (type === 'hidden' || tag === 'select') continue;
    if (tag === 'input' && (type === 'text' || type === '')) {
      const sel = selectorFor(el);
      if (sel) return sel;
    }
  }
  return null;
}
"""


async def _element_tag(page, selector: str) -> str | None:
    if not selector:
        return None
    try:
        return await page.eval_on_selector(selector, "el => el.tagName.toLowerCase()")
    except Exception:
        return None


async def _validate_message_field(page, fields: dict[str, Any]) -> dict[str, Any] | None:
    """
    message_field が <select> の場合は除外し、textarea / input[type=text] を再探索する。
    見つからなければ None（Claude フォールバック用）。
    """
    sel = fields.get("message_field")
    if not sel:
        return fields if _fields_usable(fields) else None

    tag = await _element_tag(page, sel)
    if tag != "select":
        return fields if _fields_usable(fields) else None

    fields = dict(fields)
    fields["message_field"] = None

    try:
        alt = await page.evaluate(_FIND_MESSAGE_FIELD_JS)
    except Exception:
        alt = None

    if alt:
        fields["message_field"] = alt
        return fields if _fields_usable(fields) else None

    return None


async def extract_fields_from_dom(page) -> dict[str, Any] | None:
    try:
        data = await page.evaluate(_EXTRACT_FIELDS_JS)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    validated = await _validate_message_field(page, data)
    return validated


async def resolve_form_fields(page, html: str, form_url: str) -> tuple[dict[str, Any] | None, str]:
    """
    フィールド dict と解決元（cache / dom / claude / none）を返す。
    """
    cached = get_cached_fields(form_url)
    if cached:
        validated_cache = await _validate_message_field(page, cached)
        if validated_cache:
            return validated_cache, "cache"

    dom_fields = await extract_fields_from_dom(page)
    if dom_fields:
        put_cached_fields(form_url, dom_fields, "dom")
        return dom_fields, "dom"

    claude_fields = analyze_form_with_claude(html)
    if claude_fields:
        validated_claude = await _validate_message_field(page, claude_fields)
        if validated_claude:
            put_cached_fields(form_url, validated_claude, "claude")
            return validated_claude, "claude"

    return None, "none"
