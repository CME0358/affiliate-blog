"""
form_sender.py  —  フォーム自動送信エンジン

処理フロー:
    1. フォームページにアクセス（Playwright）
    2. フィールド解決（キャッシュ → DOM ルール → Claude API）
    3. 各フィールドに入力（会社名・氏名・ふりがな・メール・本文）
    4. 3〜8 秒ランダム待機（bot 検知回避）
    5. 送信ボタンをクリック
    6. 結果を返す
"""

from __future__ import annotations

import asyncio
import random
import re

from config import (
    SENDER_ADDRESS_FULL,
    SENDER_ADDRESS_LINE1,
    SENDER_ADDRESS_LINE2,
    SENDER_COMPANY,
    SENDER_EMAIL,
    SENDER_NAME,
    SENDER_PHONE,
    SENDER_POSTAL_CODE,
    SENDER_PREFECTURE,
    SEND_INTERVAL_MIN,
    SEND_INTERVAL_MAX,
)
from form_field_resolver import resolve_form_fields, _FIND_MESSAGE_FIELD_JS, _element_tag
from form_finder import NAV_TIMEOUT, is_file_download_url
from form_finder import _goto_settled

# detect-only / fill-no-submit モードでは submit を絶対に実行しない（二重安全弁）
_SUBMIT_FORBIDDEN = False
_REAL_SUBMISSION_COUNT = 0


def set_submit_forbidden(value: bool) -> None:
    global _SUBMIT_FORBIDDEN
    _SUBMIT_FORBIDDEN = value


def get_real_submission_count() -> int:
    return _REAL_SUBMISSION_COUNT


def _record_real_submission() -> None:
    global _REAL_SUBMISSION_COUNT
    _REAL_SUBMISSION_COUNT += 1


def _digits_only(s: str) -> str:
    return re.sub(r"\D", "", s)


def _postal_variants(postal: str) -> list[str]:
    """1060045 → ['1060045', '106-0045']"""
    d = _digits_only(postal)
    if len(d) == 7:
        return [d, f"{d[:3]}-{d[3:]}"]
    return [postal.strip()]


def _address_without_prefecture(full: str, prefecture: str) -> str:
    s = full.strip()
    if s.startswith(prefecture):
        return s[len(prefecture):].strip()
    return s


async def _fill_postal_code(page, selector: str) -> None:
    if not selector:
        return
    for v in _postal_variants(SENDER_POSTAL_CODE):
        try:
            await page.fill(selector, v)
            return
        except Exception:
            continue


async def _fill_prefecture(page, fields: dict) -> None:
    sel = fields.get("prefecture_field")
    if not sel:
        return
    try:
        if fields.get("prefecture_option_value"):
            await page.select_option(sel, value=str(fields["prefecture_option_value"]))
            return
    except Exception:
        pass
    try:
        await page.select_option(sel, label=SENDER_PREFECTURE)
    except Exception:
        try:
            await page.select_option(sel, value=SENDER_PREFECTURE)
        except Exception:
            pass


# 送信ボタン探索: 描画待ち後に DOM から直接特定（Claude セレクタ失敗・動的生成対応）
_SUBMIT_CONTROL_SELECTOR = (
    'button, input[type="submit"], input[type="button"], '
    'input[type="image"], [role="button"]'
)
_SUBMIT_WAIT_MS = 5_000

_FIND_SUBMIT_ELEMENT_JS = r"""
() => {
  const TEXT_KWS = [
    '送信', '送　信', '確認', '確認画面', '入力内容を確認', 'この内容で送信',
    '同意して送信', '送信する', '確認する', '予約', '進む', '次へ',
    'submit', 'send', 'reserve', '申し込む', '問い合わせる', '内容を送る'
  ];
  const ATTR_KWS = [
    'submit', 'send', 'btn-confirm', 'btn_confirm', 'js-submit', 'js_submit',
    'reserve', 'wpcf7', 'mwform', 'mw_wp_form', 'contact-submit', 'form-submit',
    'gform', 'btn_send', 'btn-send', 'c-btn--submit', 'btn-reserve-confirm'
  ];
  const visible = (el) => {
    if (!el || !(el instanceof Element)) return false;
    const st = window.getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') return false;
    const r = el.getBoundingClientRect();
    if (r.width < 2 && r.height < 2) return false;
    return true;
  };
  const norm = (s) => (s || '').toLowerCase();
  const textMatch = (el) => {
    const t = norm((el.innerText || '') + ' ' + (el.textContent || '') + ' ' + (el.value || ''));
    return TEXT_KWS.some((k) => t.includes(k.toLowerCase()));
  };
  const attrMatch = (el) => {
    const id = norm(el.id);
    const cl = norm(el.getAttribute('class') || '');
    const s = id + ' ' + cl;
    return ATTR_KWS.some((k) => s.includes(k));
  };
  const firstVisible = (list) => {
    for (const el of list) if (visible(el)) return el;
    return null;
  };

  // 1 type=submit の button / input（表示状態を優先）
  let hit = firstVisible(
    Array.from(document.querySelectorAll('button[type="submit"], input[type="submit"]'))
  );
  if (hit) return hit;

  // 1b 歯科・WordPress系 CMS（Contact Form 7 / MW WP Form 等）
  hit = firstVisible(Array.from(document.querySelectorAll(
    '.wpcf7-submit, input.wpcf7-submit, .mwform-submit, .mw_wp_form_submit, ' +
    'button.gform_button, input.gform_button, #submit, button[name="submit"], input[name="submit"], ' +
    '.btn-reserve-confirm, .js-submit, .c-btn--submit, a.btn-submit, input[value*="確認"]'
  )));
  if (hit) return hit;

  // 1c 確認画面へ（2段階フォームの第1クリック）
  hit = firstVisible(Array.from(document.querySelectorAll('a, button')).filter((el) => {
    const t = norm((el.innerText || '') + ' ' + (el.textContent || '') + ' ' + (el.value || ''));
    return t.includes('確認画面') || t.includes('入力内容') || t.includes('次へ');
  }));
  if (hit) return hit;

  const pool = Array.from(
    document.querySelectorAll('button, input[type="button"], input[type="image"], [role="button"]')
  );

  // 2 テキスト・value にキーワード
  hit = firstVisible(pool.filter(textMatch));
  if (hit) return hit;

  // 3 class / id にキーワード
  hit = firstVisible(pool.filter(attrMatch));
  if (hit) return hit;

  // 4 role=button かつテキスト一致（プール外の a[role=button] 等）
  hit = firstVisible(Array.from(document.querySelectorAll('[role="button"]')).filter(textMatch));
  if (hit) return hit;

  // 5 フォーム内の最後の button / input[type=submit]（フォールバック）
  const forms = document.querySelectorAll('form');
  for (let i = forms.length - 1; i >= 0; i--) {
    const subs = forms[i].querySelectorAll(
      'button[type="submit"], input[type="submit"], button, input[type="button"]'
    );
    if (subs.length) {
      const last = subs[subs.length - 1];
      if (visible(last)) return last;
    }
  }

  // 6 非表示でも type=submit があれば最終手段（歯科CMSで display:none 回避が多い）
  const anySubmit = document.querySelector(
    'form button[type="submit"], form input[type="submit"], form .wpcf7-submit, form .mwform-submit'
  );
  if (anySubmit) return anySubmit;

  return null;
}
"""

# CSS セレクタフォールバック（Claude / JS 探索の次）
_FALLBACK_SUBMIT_SELECTORS: tuple[str, ...] = (
    "button[type='submit']",
    "input[type='submit']",
    ".wpcf7-submit",
    "input.wpcf7-submit",
    ".mwform-submit",
    ".mw_wp_form_submit",
    "button.gform_button",
    "input.gform_button",
    "#submit",
    "button[name='submit']",
    "input[name='submit']",
    "button.btn-submit",
    "input.btn-submit",
    "button.submit",
    "a.btn-submit",
    ".btn-reserve-confirm",
    ".js-submit",
    ".c-btn--submit",
    "a.btn[href*='confirm']",
    "input[value*='確認']",
    "[class*='submit']",
)


async def _wait_for_submit_controls(page) -> None:
    """動的ボタン描画を待つ（失敗しても続行）。"""
    try:
        await page.wait_for_selector(
            _SUBMIT_CONTROL_SELECTOR,
            timeout=_SUBMIT_WAIT_MS,
            state="attached",
        )
    except Exception:
        pass


async def _find_submit_element_handle(page):
    """page.evaluate_handle で送信相当の要素を返す。見つからなければ None。"""
    h = await page.evaluate_handle(_FIND_SUBMIT_ELEMENT_JS)
    el = h.as_element()
    await h.dispose()
    return el


async def _click_fallback_submit_selectors(page) -> bool:
    """歯科CMS等向け: 既知セレクタを順にクリック試行。"""
    for sel in _FALLBACK_SUBMIT_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            await loc.click(timeout=_SUBMIT_WAIT_MS)
            return True
        except Exception:
            continue
    return False


async def _click_submit(page, fields: dict) -> tuple[bool, str]:
    """
    送信ボタンをクリックする（2段階フォーム: 確認 → 送信 に対応）。
    Returns:
        (成功したか, 失敗時理由コード)
    """
    if _SUBMIT_FORBIDDEN:
        return False, "submit_forbidden_detect_only"

    await _wait_for_submit_controls(page)

    claude_sel = (fields.get("submit_button") or "").strip()

    async def _try_once() -> bool:
        if claude_sel:
            try:
                await page.wait_for_selector(claude_sel, timeout=_SUBMIT_WAIT_MS, state="visible")
                await page.click(claude_sel, timeout=_SUBMIT_WAIT_MS)
                return True
            except Exception:
                pass
        try:
            el = await _find_submit_element_handle(page)
            if el:
                await el.click(timeout=_SUBMIT_WAIT_MS)
                await el.dispose()
                return True
        except Exception:
            pass
        return await _click_fallback_submit_selectors(page)

    if not await _try_once():
        return False, "submit_button_not_found"

    # 2段階フォーム: 確認画面で第2の送信ボタンを探す
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=8_000)
    except Exception:
        pass
    await asyncio.sleep(1.2)

    html = await page.content()
    if any(k in html for k in ("確認画面", "入力内容の確認", "この内容で送信", "g-recaptcha")):
        if not await _try_once():
            # 第1クリックで完了した可能性もある
            return True, ""
    return True, ""


async def _fill_message_field(page, fields: dict, message: str) -> tuple[bool, str]:
    """
    message_field に入力する。select 要素はスキップし代替候補を試行する。
    Returns: (成功, 使用したセレクタ or 空)
    """
    candidates: list[str] = []
    primary = (fields.get("message_field") or "").strip()
    if primary:
        candidates.append(primary)

    try:
        alt = await page.evaluate(_FIND_MESSAGE_FIELD_JS)
        if alt and alt not in candidates:
            candidates.append(alt)
    except Exception:
        pass

    for sel in candidates:
        tag = await _element_tag(page, sel)
        if tag == "select":
            continue
        if tag not in ("textarea", "input"):
            continue
        try:
            await page.fill(sel, message)
            fields["message_field"] = sel
            return True, sel
        except Exception:
            continue

    return False, ""


_PREFER_GENDER = ("男性", "男", "male", "その他", "other")
_AVOID_GENDER = ("女", "female", "女性")
_PREFER_AGE = ("50代", "40代", "30代", "20代", "60代", "その他", "成人", "大人")
_AVOID_AGE = ("10代", "10", "小学生", "中学生", "高校生")


async def _reset_gender_age_fields(page, fields: dict) -> None:
    """
    性別・年齢をデフォルト（女性・10代等）から変更する。
    select / radio の両方に対応。
    """
    for field_key, value_key, kind in (
        ("gender_field", "gender_other_value", "gender"),
        ("age_field", "age_other_value", "age"),
    ):
        selector = (fields.get(field_key) or "").strip()
        if not selector:
            continue
        value = fields.get(value_key)
        try:
            tag = await page.eval_on_selector(
                selector, "el => el ? el.tagName.toLowerCase() : ''"
            )
        except Exception:
            continue

        if tag == "select":
            try:
                if value:
                    await page.select_option(selector, value=str(value))
                else:
                    options = await page.eval_on_selector(
                        selector,
                        "el => Array.from(el.options).map(o => ({v:o.value,t:(o.text||'').trim()}))",
                    )
                    if options:
                        prefer = _PREFER_GENDER if kind == "gender" else _PREFER_AGE
                        avoid = _AVOID_GENDER if kind == "gender" else _AVOID_AGE
                        chosen = None
                        for label in prefer:
                            for o in options:
                                if label in o.get("t", "") or label in o.get("v", ""):
                                    chosen = o["v"]
                                    break
                            if chosen:
                                break
                        if not chosen:
                            for o in options:
                                txt = o.get("t", "") + o.get("v", "")
                                if not any(a in txt for a in avoid):
                                    chosen = o["v"]
                                    break
                        if not chosen and options:
                            chosen = options[-1]["v"]
                        if chosen:
                            await page.select_option(selector, value=chosen)
            except Exception:
                pass
            continue

        # radio / checkbox グループ（name="sex" 等）
        try:
            radio_name = await page.eval_on_selector(
                selector, "el => el.getAttribute('name')"
            )
            if not radio_name:
                continue
            options = await page.evaluate(
                """(name) => {
                  const nodes = Array.from(document.querySelectorAll(
                    `input[type="radio"][name="${name}"]`
                  ));
                  return nodes.map((el) => {
                    let label = '';
                    if (el.id) {
                      const lb = document.querySelector(`label[for="${el.id}"]`);
                      if (lb) label = (lb.textContent || '').trim();
                    }
                    if (!label && el.closest('label')) {
                      label = (el.closest('label').textContent || '').trim();
                    }
                    return { value: el.value || '', label };
                  });
                }""",
                radio_name,
            )
            if not options:
                continue
            prefer = _PREFER_GENDER if kind == "gender" else _PREFER_AGE
            avoid = _AVOID_GENDER if kind == "gender" else _AVOID_AGE
            chosen_value = None
            for label in prefer:
                for o in options:
                    blob = o.get("label", "") + o.get("value", "")
                    if label in blob:
                        chosen_value = o["value"]
                        break
                if chosen_value is not None:
                    break
            if chosen_value is None:
                for o in options:
                    blob = o.get("label", "") + o.get("value", "")
                    if not any(a in blob for a in avoid):
                        chosen_value = o["value"]
                        break
            if chosen_value is None and options:
                chosen_value = options[-1]["value"]
            if chosen_value is not None:
                loc = page.locator(
                    f'input[type="radio"][name="{radio_name}"][value="{chosen_value}"]'
                )
                if await loc.count() > 0:
                    await loc.first.click(timeout=3000)
        except Exception:
            pass


async def _fill_address_block(page, fields: dict) -> None:
    """
    住所・建物 split / 単一 / 都道府県別select の組み合わせに対応。
    """
    l1, l2 = fields.get("address_line1_field"), fields.get("address_line2_field")
    single = fields.get("address_field")
    has_pref = bool(fields.get("prefecture_field"))

    if l1 and l2:
        await page.fill(l1, SENDER_ADDRESS_LINE1)
        await page.fill(l2, SENDER_ADDRESS_LINE2)
        return

    if l1 and not l2:
        text = (
            _address_without_prefecture(SENDER_ADDRESS_FULL, SENDER_PREFECTURE)
            if has_pref
            else SENDER_ADDRESS_FULL
        )
        await page.fill(l1, text)
        return

    if single:
        if has_pref:
            await page.fill(single, _address_without_prefecture(SENDER_ADDRESS_FULL, SENDER_PREFECTURE))
        else:
            await page.fill(single, SENDER_ADDRESS_FULL)
        return


# ─── メイン送信処理 ───────────────────────────────────────────────────────────

async def send_form(company: dict, message: str, lp_url: str) -> dict:
    """
    フォームページにアクセスし、メッセージを送信する。

    Args:
        company: parser.py が返す company dict（"form_url" キーが必須）
        message: message_builder.py が生成した送信文面
        lp_url:  LP URL（ログ記録用）

    Returns:
        {
            "status":      "sent" | "error" | "pending",
            "reason":      str,
            "form_url":    str,
            "lp_url":      str,
            "message_slug": str,
        }
    """
    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    except ImportError:
        return {
            "status": "error",
            "reason": "playwright がインストールされていません",
            "form_url": company.get("form_url", ""),
            "lp_url": lp_url,
            "message_slug": "",
        }

    from url_builder import get_industry_slug
    message_slug = get_industry_slug(company.get("industry_name", "")) or "unknown"

    form_url_raw = company.get("form_url")
    if not form_url_raw or not str(form_url_raw).strip():
        return {
            "status": "error",
            "reason": "form_url_is_none",
            "form_url": "",
            "lp_url": lp_url,
            "message_slug": message_slug,
        }
    if is_file_download_url(str(form_url_raw).strip()):
        return {
            "status": "error",
            "reason": "pdf_or_file_download",
            "form_url": str(form_url_raw).strip(),
            "lp_url": lp_url,
            "message_slug": message_slug,
        }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await context.new_page()

        try:
            # ── 1. フォームページにアクセス ─────────────────────────────────
            if not await _goto_settled(page, str(form_url_raw).strip(), goto_timeout=NAV_TIMEOUT):
                await browser.close()
                return {
                    "status": "error",
                    "reason": "timeout",
                    "form_url": str(form_url_raw).strip(),
                    "lp_url": lp_url,
                    "message_slug": message_slug,
                }

            # ── 2. フィールド解決（cache → DOM → Claude）────────────────────
            html = await page.content()
            fields, field_source = await resolve_form_fields(
                page, html, str(form_url_raw).strip()
            )
            if field_source != "none":
                print(f"  📋 フィールド解決: {field_source}")

            if not fields:
                await browser.close()
                return {
                    "status":       "error",
                    "reason":       "form_analysis_failed",
                    "form_url":     str(form_url_raw).strip(),
                    "lp_url":       lp_url,
                    "message_slug": message_slug,
                }

            # ── 3. 各フィールドに入力 ────────────────────────────────────────
            # 会社・担当者（先に入れるフォームが多い）
            if fields.get("company_field"):
                await page.fill(fields["company_field"], SENDER_COMPANY)

            if fields.get("name_field"):
                await page.fill(fields["name_field"], SENDER_NAME)

            if fields.get("furigana_name_field"):
                furigana_value = (
                    "ささきたけし"
                    if fields.get("furigana_format") == "hiragana"
                    else "ササキタケシ"
                )
                await page.fill(fields["furigana_name_field"], furigana_value)

            if fields.get("email_field"):
                await page.fill(fields["email_field"], SENDER_EMAIL)

            if fields.get("phone_field"):
                await page.fill(fields["phone_field"], SENDER_PHONE)

            # 郵便番号 → 都道府県 → 住所（1つ／2分割／県別select）
            await _fill_postal_code(page, fields.get("postal_code_field") or "")
            await _fill_prefecture(page, fields)
            await _fill_address_block(page, fields)

            # 性別・年齢（ラジオのデフォルト女性・10代を先にリセット）
            await _reset_gender_age_fields(page, fields)

            msg_ok, _msg_sel = await _fill_message_field(page, fields, message)
            if not msg_ok:
                await browser.close()
                return {
                    "status":       "error",
                    "reason":       "message_field_not_found",
                    "form_url":     str(form_url_raw).strip(),
                    "lp_url":       lp_url,
                    "message_slug": message_slug,
                }

            # 送信直前に性別・年齢を再確認（本文入力後にフォームJSで戻る場合）
            await _reset_gender_age_fields(page, fields)

            # ── 4. 送信前ランダム待機（bot 検知回避）───────────────────────
            await asyncio.sleep(random.uniform(SEND_INTERVAL_MIN, SEND_INTERVAL_MAX))

            # ── 5. 送信ボタンをクリック（wait_for_selector + DOM 多段フォールバック）────
            ok_submit, submit_err = await _click_submit(page, fields)
            if not ok_submit:
                await browser.close()
                return {
                    "status":       "error",
                    "reason":       submit_err,
                    "form_url":     str(form_url_raw).strip(),
                    "lp_url":       lp_url,
                    "message_slug": message_slug,
                }
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=15_000)
            except Exception:
                pass

            _record_real_submission()
            await browser.close()
            return {
                "status":       "sent",
                "reason":       "",
                "form_url":     str(form_url_raw).strip(),
                "lp_url":       lp_url,
                "message_slug": message_slug,
            }

        except Exception as e:
            await browser.close()
            return {
                "status":       "error",
                "reason":       str(e),
                "form_url":     str(form_url_raw).strip() if form_url_raw else "",
                "lp_url":       lp_url,
                "message_slug": message_slug,
            }


async def send_form_dry_run(company: dict, message: str, lp_url: str) -> dict:
    """
    実際には送信せず、入力内容のみコンソールに表示する（--dry-run 用）。
    Playwright / Claude API を呼び出さない。
    """
    from url_builder import get_industry_slug
    message_slug = get_industry_slug(company.get("industry_name", "")) or "unknown"

    print(f"\n{'─'*60}")
    print(f"  [DRY-RUN] {company['company_name']}")
    print(f"  フォーム: {company.get('form_url', '（未特定）')}")
    print(f"  送信者: {SENDER_COMPANY} / {SENDER_NAME} <{SENDER_EMAIL}>")
    print(f"  電話: {SENDER_PHONE}")
    print(f"  郵便番号: {SENDER_POSTAL_CODE} / 都道府県: {SENDER_PREFECTURE}")
    print(f"  住所（1行）: {SENDER_ADDRESS_FULL}")
    print(f"  住所（分割）: {SENDER_ADDRESS_LINE1} / {SENDER_ADDRESS_LINE2}")
    print(f"  LP URL: {lp_url}")
    print(f"  メッセージ ({len(message)}字):")
    for line in message.splitlines():
        print(f"    {line}")
    print(f"{'─'*60}")

    return {
        "status":       "dry_run",
        "reason":       "",
        "form_url":     company.get("form_url", ""),
        "lp_url":       lp_url,
        "message_slug": message_slug,
    }
