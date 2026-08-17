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

# DOM からフィールドを推定（Claude 不要）— confidence scoring + contact-form scope
_EXTRACT_FIELDS_JS = r"""
() => {
  const SCORE_THRESHOLD = 25;
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
    city_field: null,
    contact_form_scope: null,
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
    const form = el.closest('form');
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (form && type === 'submit') {
      if (form.id) return 'form#' + cssEscape(form.id) + ' ' + tag + '[type="submit"]';
      if ((form.className || '').includes('cc-m-form')) {
        return 'form.cc-m-form ' + tag + '[type="submit"]';
      }
      return 'form ' + tag + '[type="submit"]';
    }
    return null;
  }

  function metaText(el) {
    const parts = [];
    ['name', 'id', 'placeholder', 'aria-label', 'title', 'class'].forEach((a) => {
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
    const prev = el.previousElementSibling;
    if (prev && /^(th|dt|label|span|p)$/i.test(prev.tagName)) {
      parts.push(prev.textContent || '');
    }
    return parts.join(' ').toLowerCase();
  }

  function matchAny(text, kws) {
    return kws.some((k) => text.includes(k));
  }

  function isVisible(el) {
    if (!el || el.nodeType !== 1) return false;
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (type === 'hidden') return false;
    return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  }

  function isExcludedNoise(el, t, idn) {
    if (matchAny(idn, ['search', 'newsletter', 'subscribe', 'header', 'nav', 'login', 'password'])) return true;
    if (matchAny(t, ['検索', 'search', 'newsletter', 'メルマガ', 'ログイン', 'login', 'パスワード'])) return true;
    const form = el.closest('form');
    if (form) {
      const fc = ((form.className || '') + ' ' + (form.id || '') + ' ' + (form.action || '')).toLowerCase();
      if (matchAny(fc, ['search-form', 'searchform', 'hidden-search'])) return true;
    }
    return false;
  }

  function isSearchForm(f) {
    const fc = ((f.className || '') + ' ' + (f.id || '') + ' ' + (f.getAttribute('action') || '')).toLowerCase();
    if (matchAny(fc, ['searchform', 'search-form', 'keni_search', 'hidden-search', 'site-search'])) return true;
    if (fc.includes('?s=') || fc.includes('&s=')) return true;
    const inputs = f.querySelectorAll('input, textarea, select');
    let searchLike = 0;
    let contactLike = 0;
    inputs.forEach((el) => {
      const n = ((el.name || '') + ' ' + (el.id || '')).toLowerCase();
      const t = (el.getAttribute('type') || '').toLowerCase();
      if (n === 's' || t === 'search' || matchAny(n, ['search'])) searchLike += 1;
      if (el.tagName === 'TEXTAREA' || t === 'email' || matchAny(n, ['mail', 'email', 'メール', 'お名前'])) contactLike += 1;
    });
    if (searchLike && !contactLike && inputs.length <= 3) return true;
    return false;
  }

  function formScopeSelector(f) {
    f.setAttribute('data-ari-form-scope', 'contact');
    if (f.id) return 'form#' + cssEscape(f.id);
    return 'form[data-ari-form-scope="contact"]';
  }

  function pickContactForm() {
    const forms = Array.from(document.querySelectorAll('form'));
    if (!forms.length) return null;
    let best = forms[0];
    let bestScore = -999;
    for (const f of forms) {
      if (isSearchForm(f)) continue;
      let s = 0;
      const fc = ((f.className || '') + ' ' + (f.id || '') + ' ' + (f.getAttribute('action') || '')).toLowerCase();
      if (matchAny(fc, ['contact', 'inquiry', '問い合わせ', 'mail', 'estimate', 'wpcf7', 'mwform', 'sfm-form'])) s += 35;
      s += f.querySelectorAll('textarea').length * 18;
      s += f.querySelectorAll('input[type="email"]').length * 14;
      s += f.querySelectorAll('input[name*="your-"], textarea[name*="your-"]').length * 10;
      if (f.querySelector('textarea') && (f.querySelector('input[type="email"]') || f.querySelector('input[name*="mail"], input[name*="メール"], input[name*="お名前"]'))) s += 25;
      s += Math.min(f.querySelectorAll('input, textarea, select').length, 25);
      if (matchAny(fc, ['search', 'login', 'newsletter', 'hidden-search', 'subscribe'])) s -= 80;
      if (s > bestScore) {
        bestScore = s;
        best = f;
      }
    }
    if (bestScore < 0) return null;
    return best;
  }

  function scoreEmail(el, t, idn, type) {
    let s = 0;
    if (type === 'email') s += 40;
    const ac = (el.getAttribute('autocomplete') || '').toLowerCase();
    if (ac === 'email') s += 30;
    if (matchAny(idn, ['mail', 'email', 'e-mail', 'your-email'])) s += 20;
    if (matchAny(t, ['メール', 'mail', 'email', 'e-mail'])) s += 15;
    if (matchAny(idn, ['c_email', 'confirm', 're_email', 'email_confirm'])) s -= 30;
    if (isExcludedNoise(el, t, idn)) s -= 50;
    return s;
  }

  function scorePhone(el, t, idn, type) {
    let s = 0;
    if (type === 'tel') s += 40;
    const ac = (el.getAttribute('autocomplete') || '').toLowerCase();
    if (ac === 'tel') s += 30;
    if (matchAny(idn, ['tel', 'phone', 'your-tel', 'mobile', '携帯', '電話番号', 'お電話番号'])) s += 20;
    if (matchAny(t, ['電話', 'tel', 'phone', '携帯', '連絡先'])) s += 15;
    if (matchAny(idn, ['zip', 'postal', 'postcode', 'post_code', 'yubin', 'fax'])) s -= 40;
    if (isExcludedNoise(el, t, idn)) s -= 50;
    return s;
  }

  function scoreName(el, t, idn, type, tag) {
    let s = 0;
    const ac = (el.getAttribute('autocomplete') || '').toLowerCase();
    if (ac === 'name') s += 40;
    if (matchAny(idn, ['your-name', 'fullname', 'full_name', 'inquiry_name', 'your_name', 'name_s', 'contact_name', 'form_name'])) s += 30;
    if (matchAny(idn, ['お名前', '氏名', 'なまえ'])) s += 35;
    if (matchAny(idn, ['input[name]'])) s += 25;
    if (matchAny(idn, ['name']) && !matchAny(idn, ['kana', 'company', 'department', 'user', 'email', 'mail', 'confirm'])) s += 20;
    if (matchAny(idn, ['text_1_must', 'text_1', 'text_2_must'])) s += 28;
    if (matchAny(t, ['氏名', 'お名前', '担当者', 'name', 'なまえ', 'ご氏名'])) s += 15;
    if (matchAny(t, ['フリガナ', 'ふりがな', 'カナ', 'kana', '会社', 'company', 'department', '部署', '法人名'])) s -= 40;
    if (!isVisible(el)) s -= 50;
    if (tag !== 'input' || (type && type !== 'text' && type !== '')) s -= 20;
    if (isExcludedNoise(el, t, idn)) s -= 50;
    return s;
  }

  function scoreCompany(el, t, idn, tag) {
    let s = 0;
    if (matchAny(idn, ['company', 'corporation', 'corporate', 'your-company', 'corp', 'corporate_name'])) s += 25;
    if (matchAny(t, ['会社', 'company', '法人', '店舗', '施設', '医院名', 'クリニック名', '法人名'])) s += 20;
    if (!isVisible(el)) s -= 60;
    if (tag !== 'input' && tag !== 'textarea') s -= 20;
    return s;
  }

  function scoreMessage(el, t, idn, tag) {
    let s = 0;
    if (tag === 'textarea') s += 40;
    if (matchAny(idn, ['your-message', 'message', 'comment', 'inquiry', 'body', 'content', 'form_body', 'comment_s'])) s += 25;
    if (matchAny(t, ['お問い合わせ', '問合せ', '問い合わせ', 'message', '内容', 'ご用件', 'comment', 'inquiry', '備考', '相談', 'ご質問', '詳細'])) s += 20;
    if (tag === 'textarea' && (el.rows >= 3 || (el.getAttribute('rows') && parseInt(el.getAttribute('rows'), 10) >= 3))) s += 10;
    if (matchAny(idn, ['subject', '件名', 'issue']) && tag !== 'textarea') s -= 20;
    if (isExcludedNoise(el, t, idn)) s -= 50;
    return s;
  }

  function pickBest(candidates) {
    let best = null;
    let bestScore = SCORE_THRESHOLD - 1;
    for (const c of candidates) {
      if (c.score > bestScore) {
        bestScore = c.score;
        best = c;
      }
    }
    return best;
  }

  const contactForm = pickContactForm();
  if (contactForm) {
    result.contact_form_scope = formScopeSelector(contactForm);
  }
  const scope = contactForm || document;
  const controls = Array.from(scope.querySelectorAll('input, textarea, select, button'));

  const emailCands = [];
  const emailConfirmCands = [];
  const phoneCands = [];
  const nameCands = [];
  const companyCands = [];
  const messageCands = [];

  for (const el of controls) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    const t = metaText(el);
    const idn = ((el.id || '') + ' ' + (el.name || '')).toLowerCase();

    if (type === 'hidden') continue;

    if (
      tag === 'input'
      && matchAny(idn, ['zip', 'postal', 'postcode', 'post_code', 'yubin', 'zipcode', 'zip1'])
    ) {
      const sel = selectorFor(el);
      if (sel && !result.postal_code_field) result.postal_code_field = sel;
      continue;
    }

    if (type === 'submit' || (tag === 'button' && type !== 'button' && type !== 'reset')) {
      if (type === 'submit' || matchAny(t, ['送信', '確認', 'submit', 'send', '進む', '次へ'])) {
        const sel = selectorFor(el);
        if (sel && !result.submit_button) result.submit_button = sel;
      }
      continue;
    }

    if (type === 'radio' || type === 'checkbox') {
      if (matchAny(t, ['性別', 'gender', 'sex'])) {
        const sel = selectorFor(el);
        if (sel && !result.gender_field) result.gender_field = sel;
      }
      if (matchAny(t, ['年齢', 'age', '年代'])) {
        const sel = selectorFor(el);
        if (sel && !result.age_field) result.age_field = sel;
      }
      continue;
    }

    if (tag === 'input' && (type === 'text' || type === 'email' || type === 'tel' || type === '')) {
      const isEmailConfirm = (
        matchAny(idn, [
          'c_email',
          'confirm',
          're_email',
          'email_confirm',
          'email-confirm',
          'mail_confirm',
          'mail-confirm',
          'confirm_email',
          'confirm-email',
          'email2',
          'mail2'
        ])
        || matchAny(t, [
          'メールアドレス確認',
          'メールアドレス（確認',
          'メールアドレス(確認',
          'メール確認',
          '確認用メール',
          '確認用メールアドレス',
          'email confirmation',
          'confirm email',
          're-enter email'
        ])
      );

      const es = scoreEmail(el, t, idn, type);

      if (isEmailConfirm) {
        emailConfirmCands.push({ el, score: Math.max(es, SCORE_THRESHOLD) + 50 });
      } else if (es >= SCORE_THRESHOLD) {
        emailCands.push({ el, score: es });
      }

      const ps = scorePhone(el, t, idn, type);
      if (ps >= SCORE_THRESHOLD) phoneCands.push({ el, score: ps });
      const ns = scoreName(el, t, idn, type, tag);
      if (ns >= SCORE_THRESHOLD) nameCands.push({ el, score: ns });
      const cs = scoreCompany(el, t, idn, tag);
      if (cs >= SCORE_THRESHOLD) companyCands.push({ el, score: cs });
    }

    if (tag === 'textarea' || (tag === 'input' && (type === 'text' || type === ''))) {
      const ms = scoreMessage(el, t, idn, tag);
      if (ms >= SCORE_THRESHOLD) messageCands.push({ el, score: ms });
    }

    const furiganaText = `${t} ${idn}`;
    if (matchAny(furiganaText, [
      'フリガナ', 'ふりがな', 'カナ', 'kana', 'furigana', 'ruby',
      'your-kana', 'your-ruby'
    ])) {
      const sel = selectorFor(el);
      if (sel && !result.furigana_name_field) {
        result.furigana_name_field = sel;
        if (matchAny(furiganaText, ['フリガナ', 'カナ', 'katakana', 'kana'])) result.furigana_format = 'katakana';
        else if (matchAny(furiganaText, ['ふりがな', 'hiragana'])) result.furigana_format = 'hiragana';
        else if (!result.furigana_format) result.furigana_format = 'katakana';
      }
    }

    if (matchAny(t, ['郵便', 'zip', 'postal', '〒', 'yubin']) || matchAny(idn, ['zip', 'postal', 'yubin', 'zipcode'])) {
      const sel = selectorFor(el);
      if (sel && !result.postal_code_field) result.postal_code_field = sel;
    }

    if (tag === 'select' && (
      matchAny(t, ['都道府県', 'prefecture', 'todofuken', 'state', 'pref'])
      || matchAny(idn, ['prefecture', 'prefectures', 'form_area', '都道府県', 'address_prefectures'])
    )) {
      const sel = selectorFor(el);
      if (sel && !result.prefecture_field) {
        result.prefecture_field = sel;
        el.querySelectorAll('option').forEach((o) => {
          if ((o.textContent || '').includes('東京') && !result.prefecture_option_value) {
            result.prefecture_option_value = o.value;
          }
        });
      }
    }

    if (tag !== 'select' && matchAny(t, ['市町村', '市区町村', 'city', 'municipality', 'address_city'])) {
      const sel = selectorFor(el);
      if (sel && !result.city_field) result.city_field = sel;
    } else if (matchAny(idn, ['市区町村', 'address_city', 'city'])) {
      const sel = selectorFor(el);
      if (sel && !result.city_field) result.city_field = sel;
    }

    if (matchAny(t, ['住所2', 'address2', '建物', 'マンション', 'ビル', '部屋'])) {
      const sel = selectorFor(el);
      if (sel && !result.address_line2_field) result.address_line2_field = sel;
    } else if (matchAny(t, ['住所1', 'address1', 'address_1', '丁目', '番地', 'localadd'])) {
      const sel = selectorFor(el);
      if (sel && !result.address_line1_field) result.address_line1_field = sel;
    } else if (tag !== 'select' && matchAny(t, ['住所', 'address', '所在地']) && !result.address_line1_field) {
      const sel = selectorFor(el);
      if (sel && !result.address_field) result.address_field = sel;
    }
  }

  function assignBest(key, candidates) {
    const best = pickBest(candidates);
    if (best) {
      const sel = selectorFor(best.el);
      if (sel) result[key] = sel;
    }
  }

  assignBest('email_field', emailCands);
  assignBest('email_confirmation_field', emailConfirmCands);
  assignBest('phone_field', phoneCands);
  assignBest('name_field', nameCands);
  assignBest('company_field', companyCands);
  assignBest('message_field', messageCands);

  if (result.address_field && result.prefecture_field && result.address_field === result.prefecture_field) {
    result.address_field = null;
  }

  if (!result.submit_button) {
    const formScope = contactForm || document.querySelector('form.cc-m-form, form[class*="cc-m-form"], form');
    const hit = formScope
      ? formScope.querySelector('input[type="submit"], button[type="submit"], .wpcf7-submit, .mwform-submit')
      : document.querySelector('button[type="submit"], input[type="submit"], .wpcf7-submit, .mwform-submit');
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


async def wait_for_form_hydration(page, timeout_ms: int = 3000) -> None:
    """JS hydration 後に contact form フィールドが現れるまで短時間待機。"""
    js = """
    () => new Promise((resolve) => {
      const deadline = Date.now() + %d;
      function hasContactFields() {
        const form = document.querySelector(
          'form.wpcf7-form, form[class*="wpcf7"], form[id*="contact"], form[id*="sfm"], form'
        );
        if (!form) return false;
        if (form.querySelector('textarea')) return true;
        if (form.querySelector('input[type="email"]')) return true;
        if (form.querySelector('input[name*="your-"], textarea[name*="your-"]')) return true;
        if (form.querySelectorAll('input, textarea').length >= 3) return true;
        return false;
      }
      if (hasContactFields()) {
        resolve(true);
        return;
      }
      const obs = new MutationObserver(() => {
        if (hasContactFields()) {
          obs.disconnect();
          resolve(true);
        } else if (Date.now() > deadline) {
          obs.disconnect();
          resolve(false);
        }
      });
      obs.observe(document.documentElement, { childList: true, subtree: true });
      setTimeout(() => {
        obs.disconnect();
        resolve(hasContactFields());
      }, %d);
    })
    """ % (timeout_ms, timeout_ms)
    try:
        await page.evaluate(js)
    except Exception:
        pass
    try:
        await page.wait_for_timeout(min(500, timeout_ms // 4))
    except Exception:
        pass


def classify_form_analysis_failure(
    partial: dict[str, Any] | None,
    *,
    iframe_detected: bool = False,
) -> str:
    """form_analysis_failed を細分化。"""
    if iframe_detected:
        return "external_iframe"
    if not partial or not isinstance(partial, dict):
        return "form_analysis_failed"

    has_email = bool(partial.get("email_field"))
    has_name = bool(partial.get("name_field"))
    has_message = bool(partial.get("message_field"))
    has_submit = bool(partial.get("submit_button"))

    if not has_message and not has_email and not has_name:
        return "dynamic_form_unresolved"
    if not has_message and not (has_email and has_name):
        if not has_email:
            return "email_field_not_found"
        if not has_name:
            return "name_field_not_found"
        return "message_field_not_found"
    if not has_submit:
        return "submit_field_not_found"
    return "form_analysis_failed"


def _sanitize_resolved_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """prefecture select の address 誤マップ等を除去。"""
    if not fields:
        return fields
    out = dict(fields)
    if out.get("address_field") and out.get("address_field") == out.get("prefecture_field"):
        out["address_field"] = None
    return out


async def extract_partial_fields_from_dom(page) -> dict[str, Any] | None:
    """usable 判定前の生フィールド dict（失敗分類用）。"""
    await wait_for_form_hydration(page)
    try:
        data = await page.evaluate(_EXTRACT_FIELDS_JS)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def clear_field_cache() -> None:
    """Resolver 改善後の stale cache を破棄。"""
    if FORM_FIELD_CACHE_PATH.exists():
        FORM_FIELD_CACHE_PATH.unlink(missing_ok=True)


async def extract_fields_from_dom(page, *, rescan: bool = False) -> dict[str, Any] | None:
    if not rescan:
        await wait_for_form_hydration(page)
    try:
        data = await page.evaluate(_EXTRACT_FIELDS_JS)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    data = _sanitize_resolved_fields(data)
    validated = await _validate_message_field(page, data)
    return validated


_RUNTIME_CONTACT_SCOPE = 'form[data-ari-form-scope="contact"]'


async def _restore_and_validate_cached_scope(
    page,
    cached: dict[str, Any],
) -> dict[str, Any] | None:
    """Re-identify a cached form on the fresh DOM and return live canonical fields.

    Runtime marker selectors are page-local state and cannot be trusted across
    browser contexts.  A fresh DOM resolution both restores that marker and
    supplies selectors derived from the current, uniquely identified form.
    Cache disagreement or ambiguity fails closed to the caller's normal DOM
    fallback.
    """
    stored_scope = str(cached.get("contact_form_scope") or "").strip()
    if not stored_scope:
        return None

    live = await extract_fields_from_dom(page)
    if not live:
        return None
    live_scope = str(live.get("contact_form_scope") or "").strip()
    if live_scope != stored_scope:
        return None

    mapping_keys = (
        "name_field", "company_field", "email_field", "phone_field",
        "message_field", "consent_field",
    )
    check = await page.evaluate(
        """({scope, cached, live, keys}) => {
          let roots=[];
          try { roots=Array.from(document.querySelectorAll(scope)); }
          catch (_) { return {ok:false, reason:'scope_invalid'}; }
          if (roots.length !== 1) return {ok:false, reason:'scope_not_unique', count:roots.length};
          const root=roots[0];
          const one=(selector) => {
            if (!selector) return {count:0, el:null};
            try { const xs=Array.from(document.querySelectorAll(selector)).filter(el=>root.contains(el)); return {count:xs.length,el:xs[0]||null}; }
            catch (_) { return {count:-1,el:null}; }
          };
          for (const key of keys) {
            const a=cached[key]||'', b=live[key]||'';
            if (!a) continue;
            const ca=one(a), cb=one(b);
            if (ca.count !== 1 || cb.count !== 1 || ca.el !== cb.el) return {ok:false,reason:'field_mapping_mismatch',key,cached_count:ca.count,live_count:cb.count};
          }
          const submit=one(live.submit_button||'');
          if (submit.count !== 1) return {ok:false,reason:'submit_not_unique',count:submit.count};
          const el=submit.el, tag=(el.tagName||'').toLowerCase(), type=(el.getAttribute('type')||'').toLowerCase();
          if (!((tag==='input' && ['submit','button','image'].includes(type)) || tag==='button')) return {ok:false,reason:'submit_type_mismatch',tag,type};
          const style=getComputedStyle(el), rect=el.getBoundingClientRect();
          const visible=style.display!=='none' && style.visibility!=='hidden' && style.opacity!=='0' && rect.width>0 && rect.height>0;
          if (!visible) return {ok:false,reason:'submit_hidden'};
          return {ok:true,reason:'restored',submit_disabled:!!el.disabled,tag,type,value:(el.value||''),label:((el.innerText||el.textContent||'')+' '+(el.value||'')).trim()};
        }""",
        {"scope": live_scope, "cached": cached, "live": live, "keys": list(mapping_keys)},
    )
    if not isinstance(check, dict) or not check.get("ok"):
        return None
    return live


async def resolve_form_fields(
    page, html: str, form_url: str, *, skip_cache: bool = False,
) -> tuple[dict[str, Any] | None, str]:
    """
    フィールド dict と解決元（cache / dom / claude / none）を返す。
    """
    if not skip_cache:
        cached = get_cached_fields(form_url)
        if cached:
            validated_cache = await _validate_message_field(page, cached)
            if validated_cache:
                restored = await _restore_and_validate_cached_scope(page, validated_cache)
                if restored and await required_text_mapping_complete(page, restored):
                    source = "cache_scope_restored" if (
                        str(validated_cache.get("contact_form_scope") or "").strip()
                        == _RUNTIME_CONTACT_SCOPE
                    ) else "cache_validated"
                    return restored, source

    dom_fields = await extract_fields_from_dom(page)
    if dom_fields:
        put_cached_fields(form_url, dom_fields, "dom")
        return dom_fields, "dom"

    dom_fields = await extract_fields_from_dom(page, rescan=True)
    if dom_fields:
        put_cached_fields(form_url, dom_fields, "dom_rescan")
        return dom_fields, "dom_rescan"

    claude_fields = analyze_form_with_claude(html)
    if claude_fields:
        validated_claude = await _validate_message_field(page, claude_fields)
        if validated_claude:
            put_cached_fields(form_url, validated_claude, "claude")
            return validated_claude, "claude"

    return None, "none"


async def required_text_mapping_complete(page, fields: dict[str, Any]) -> bool:
    """Reject stale cache mappings that omit a visible required text control."""
    selectors = sorted({
        str(value).strip()
        for key, value in (fields or {}).items()
        if key.endswith("_field") and isinstance(value, str) and value.strip()
    })
    try:
        result = await page.evaluate(
            """({scope, selectors}) => {
              const root = scope ? document.querySelector(scope) : document;
              if (!root) return false;
              const mapped = new Set(selectors);
              const esc = (s) => (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
              const selectorFor = (el) => el.id ? `#${esc(el.id)}` :
                (el.name ? `${el.tagName.toLowerCase()}[name="${String(el.name).replace(/"/g, '\\"')}"]` : '');
              const visible = (el) => {
                const st = getComputedStyle(el), r = el.getBoundingClientRect();
                return st.display !== 'none' && st.visibility !== 'hidden' && r.width > 0 && r.height > 0;
              };
              const controls = Array.from(root.querySelectorAll('input, textarea')).filter((el) => {
                const type = (el.type || '').toLowerCase();
                const textLike = el.tagName === 'TEXTAREA' || ['', 'text', 'email', 'tel', 'url', 'search', 'number'].includes(type);
                const required = el.required || el.getAttribute('aria-required') === 'true' || /(?:^|\\s)wpcf7-validates-as-required(?:\\s|$)/.test(el.className || '');
                return textLike && required && visible(el) && !el.disabled;
              });
              return controls.every((el) => mapped.has(selectorFor(el)));
            }""",
            {"scope": fields.get("contact_form_scope") or "", "selectors": selectors},
        )
    except Exception:
        return False
    return bool(result)
