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
import hashlib
import os
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
from message_variant import format_selection_log_line, resolve_ari_message_for_form, selection_as_dict
from form_finder import NAV_TIMEOUT, is_file_download_url
from form_finder import _goto_settled

# detect-only / fill-no-submit / submit-canary（live 未武装）では submit 禁止
_SUBMIT_FORBIDDEN = False
_REAL_SUBMISSION_COUNT = 0


def set_submit_forbidden(value: bool) -> None:
    global _SUBMIT_FORBIDDEN
    _SUBMIT_FORBIDDEN = value


def get_submit_forbidden() -> bool:
    return _SUBMIT_FORBIDDEN


def get_real_submission_count() -> int:
    return _REAL_SUBMISSION_COUNT


def _record_real_submission() -> None:
    global _REAL_SUBMISSION_COUNT
    max_prod = int(os.environ.get("ARI_PRODUCTION_MAX_SUBMISSIONS", "0") or "0")
    if max_prod and _REAL_SUBMISSION_COUNT >= max_prod:
        raise RuntimeError(f"hard_limit_{max_prod}_real_submissions")
    _REAL_SUBMISSION_COUNT += 1


def reset_real_submission_count() -> None:
    """テスト用: 送信カウンタをリセット。"""
    global _REAL_SUBMISSION_COUNT
    _REAL_SUBMISSION_COUNT = 0


async def _page_fill(page, selector: str, value: str) -> None:
    """Production: Playwright default fill. Night Factory PF budget: bounded + interactable pick."""
    try:
        from ari_pipeline.pf_rf_hardening import nf_pf_fill, nf_pf_mode_active
        if nf_pf_mode_active():
            await nf_pf_fill(page, selector, value)
            return
    except ImportError:
        pass
    await page.fill(selector, value)


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
            await _page_fill(page, selector, v)
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
    'form button[type="submit"], form input[type="submit"], '
    'button[type="submit"], input[type="submit"], input[type="button"], '
    'input[type="image"], [role="button"]'
)
_SUBMIT_WAIT_MS = 5_000
_GENERIC_SUBMIT_SELECTORS = frozenset({"input", "button", "submit", "a", "img"})


def _is_usable_submit_selector(sel: str) -> bool:
    """Reject tag-only Claude selectors like ``input`` / ``button``."""
    s = (sel or "").strip().lower()
    if not s or s in _GENERIC_SUBMIT_SELECTORS:
        return False
    if re.match(r"^[a-z]+$", s):
        return False
    return True


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
  const isCookieBanner = (el) => {
    if (!el || el.closest('form')) return false;
    const id = norm(el.id);
    const cl = norm(el.getAttribute('class') || '');
    if (id.includes('cookie') || cl.includes('cookie')) return true;
    const root = el.closest('[id*="cookie" i], [class*="cookie" i]');
    return !!root;
  };
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
    for (const el of list) if (visible(el) && !isCookieBanner(el)) return el;
    return null;
  };
  const formSubmitSelector = (form) =>
    'button[type="submit"], input[type="submit"], input[type="image"]';

  // 0 Jimdo / cc-m-form（フォーム内 submit を最優先）
  let hit = firstVisible(Array.from(document.querySelectorAll(
    'form.cc-m-form input[type="submit"], form.cc-m-form button[type="submit"], ' +
    'form[class*="cc-m-form"] input[type="submit"], form[class*="cc-m-form"] button[type="submit"]'
  )));
  if (hit) return hit;

  // 1 各 form 内の type=submit（cookie バナー外）
  for (const form of document.querySelectorAll('form')) {
    hit = firstVisible(Array.from(form.querySelectorAll(formSubmitSelector(form))));
    if (hit) return hit;
  }

  // 2 ページ全体の type=submit（後方互換）
  hit = firstVisible(
    Array.from(document.querySelectorAll('button[type="submit"], input[type="submit"]'))
  );
  if (hit) return hit;

  // 1a 画像送信ボタン（alt/name のみ・テキストラベルなし）
  hit = firstVisible(Array.from(document.querySelectorAll('input[type="image"]')).filter((el) => {
    const alt = norm(el.getAttribute('alt') || '');
    const nm = norm(el.getAttribute('name') || '');
    return attrMatch(el) || nm.includes('send') || nm.includes('submit')
      || alt.includes('送信') || alt.includes('submit') || alt.includes('確認');
  }));
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
    "form.cc-m-form input[type='submit']",
    "form.cc-m-form button[type='submit']",
    "form[class*='cc-m-form'] input[type='submit']",
    "form input[type='submit']",
    "form button[type='submit']",
    "button[type='submit']",
    "input[type='submit']",
    "input[type='image'][name='send']",
    "input[type='image']",
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


async def _prepare_submit_surface(page) -> None:
    """Cookie オーバーレイ解除 → submit コントロール描画待ち。"""
    from cookie_banner import dismiss_cookie_banner

    await dismiss_cookie_banner(page)
    await _wait_for_submit_controls(page)
    await asyncio.sleep(0.45)


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


_CONFIRM_HTML_KEYWORDS = (
    "確認画面",
    "入力内容の確認",
    "入力内容確認",
    "この内容で送信",
    "内容をご確認",
)

_SUCCESS_HTML_KEYWORDS = (
    "送信完了",
    "送信しました",
    "ありがとうございました",
    "お問い合わせを受け付け",
    "受付完了",
    "thank you",
    "thanks",
)

_SUCCESS_URL_FRAGMENTS = (
    "thanks",
    "thank-you",
    "complete",
    "done",
    "success",
)


def detect_submission_success(
    final_url: str,
    form_url: str,
    html: str,
    meta: dict,
) -> tuple[bool, str]:
    """
    Real submission 判定（Success State Contract 準拠）。
    URL の confirmation だけでは True にしない。
    Returns: (success, reason_code)
    """
    from submission_state import CONFIRMED_SENT, classify_submission_outcome

    outcome = classify_submission_outcome(
        final_url=final_url,
        form_url=form_url,
        html=html,
        meta=meta,
    )
    return outcome.counts_toward_confirmed_sent, outcome.reason


async def _click_audited_button(page, btn: dict) -> bool:
    sel = (btn.get("selector") or "").strip()
    if sel:
        try:
            await page.click(sel, timeout=_SUBMIT_WAIT_MS)
            return True
        except Exception:
            pass
    label = (btn.get("label") or "").strip()
    if label:
        try:
            loc = page.get_by_role("button", name=label.split()[0], exact=False)
            if await loc.count():
                await loc.first.click(timeout=_SUBMIT_WAIT_MS)
                return True
        except Exception:
            pass
    return False


async def _await_post_submit_settle(page) -> None:
    """AJAX / same-URL フォームの完了 DOM 出現を待つ。"""
    selectors = (
        ".wpcf7-mail-sent-ok",
        ".wpcf7-response-output",
        '[class*="mail-sent"]',
        '[class*="thanks"]',
        '[class*="complete"]',
        '[role="alert"]',
    )
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=6_000)
            await asyncio.sleep(0.6)
            return
        except Exception:
            continue
    await asyncio.sleep(2.5)


async def _click_submit(
    page,
    fields: dict,
    *,
    allow_confirmation_final_submit: bool = False,
) -> tuple[bool, str, dict]:
    """
    送信ボタンをクリックする（2段階フォーム: 確認 → 送信 に対応）。
    Uses scoped button audit from shared runtime (contact_form_scope).
    Returns:
        (成功したか, 失敗時理由コード, submission_meta)
    """
    meta: dict = {
        "steps_clicked": 0,
        "confirmation_reached": False,
        "final_submit_clicked": False,
    }
    from mw_wp_form_state import (
        MW_COMPLETE, MW_CONFIRMATION, MW_INITIAL, detect_mw_wp_form_state_dom,
    )
    mw_before = await detect_mw_wp_form_state_dom(page)
    meta["mw_wp_form_state_before"] = mw_before
    if _SUBMIT_FORBIDDEN:
        return False, "submit_forbidden_detect_only", meta

    await _prepare_submit_surface(page)

    contact_scope = fields.get("contact_form_scope")
    from form_fill_no_submit import (
        BACK,
        FINAL_SUBMIT,
        NEXT_STEP_SAFE,
        _audit_buttons,
        _click_button_scoped,
        click_final_submit_button,
        pick_final_submit_button,
    )
    from submission_state import _html_signals, _url_signals

    claude_sel = (fields.get("submit_button") or "").strip()
    if not _is_usable_submit_selector(claude_sel):
        claude_sel = ""

    async def _try_scoped_submit() -> bool:
        audited = await _audit_buttons(page, contact_scope)
        interactive = [b for b in audited if not b.get("disabled") and not b.get("ariaDisabled")]
        finals = [b for b in interactive if b.get("classification") == FINAL_SUBMIT]
        nexts = [b for b in interactive if b.get("classification") == NEXT_STEP_SAFE]
        if len(finals) == 1 and not nexts:
            btn = finals[0]
            if await _click_button_scoped(page, btn, contact_scope):
                meta["final_submit_label"] = btn.get("label")
                return True
        if len(nexts) == 1 and not finals:
            btn = nexts[0]
            if await _click_button_scoped(page, btn, contact_scope):
                meta["final_submit_label"] = btn.get("label")
                return True
        if claude_sel:
            try:
                scoped = f"{contact_scope} {claude_sel.split(' ', 1)[-1]}" if contact_scope and claude_sel.startswith("form") else claude_sel
                await page.wait_for_selector(scoped, timeout=_SUBMIT_WAIT_MS, state="visible")
                await page.click(scoped, timeout=_SUBMIT_WAIT_MS)
                return True
            except Exception:
                pass
        return False

    async def _try_legacy_once() -> bool:
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

    if not await _try_scoped_submit():
        if not await _try_legacy_once():
            return False, "submit_button_not_found", meta

    form_url_before = page.url
    meta["steps_clicked"] = 1

    try:
        await page.wait_for_load_state("domcontentloaded", timeout=8_000)
    except Exception:
        pass
    await asyncio.sleep(1.2)

    html = await page.content()
    mw_after = await detect_mw_wp_form_state_dom(page)
    meta["mw_wp_form_state_after_first_click"] = mw_after
    if mw_before.get("state") == MW_INITIAL and mw_after.get("state") == MW_CONFIRMATION:
        meta["confirmation_reached"] = True
        meta["final_submit_clicked"] = False
        meta["mw_wp_form_final_contract_required"] = True
        return True, "", meta
    if mw_after.get("state") == MW_COMPLETE:
        meta["final_submit_clicked"] = True
        return True, "", meta
    audited = await _audit_buttons(page, contact_scope)
    interactive = [b for b in audited if not b.get("disabled") and not b.get("ariaDisabled")]
    finals = [b for b in interactive if b.get("classification") == "FINAL_SUBMIT"]
    nexts = [b for b in interactive if b.get("classification") == "NEXT_STEP_SAFE"]
    backs = [b for b in interactive if b.get("classification") == BACK]
    _, confirm_url_flag, success_url_flag = _url_signals(page.url, form_url_before)
    _, confirm_dom, _ = _html_signals(html)
    url_changed = page.url.rstrip("/") != form_url_before.rstrip("/")

    is_confirm = (
        bool(nexts)
        or confirm_url_flag
        or (confirm_dom and bool(finals))
        or (any(k in html for k in _CONFIRM_HTML_KEYWORDS) and bool(finals))
        or (bool(finals) and bool(backs))
        or (bool(finals) and url_changed and not success_url_flag)
        or (bool(finals) and confirm_dom and meta["steps_clicked"] == 1)
    )

    if is_confirm:
        meta["confirmation_reached"] = True
        meta["confirmation_snapshot"] = {
            "page_url": page.url,
            "final_controls": [
                {k: b.get(k) for k in ("selector", "label", "tag", "type", "name", "value", "order")}
                for b in finals
            ],
            "back_controls": [
                {k: b.get(k) for k in ("selector", "label", "tag", "type", "name", "value", "order")}
                for b in backs
            ],
            "final_control_count": len(finals),
        }
        if not allow_confirmation_final_submit:
            meta["confirmation_auto_follow"] = False
            meta["final_submit_clicked"] = False
            return True, "", meta
        meta["confirmation_auto_follow"] = True
        if finals:
            ok_final, detail, _btn = await click_final_submit_button(page, audited)
            if ok_final:
                meta["steps_clicked"] = 2
                meta["final_submit_label"] = detail
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=8_000)
                except Exception:
                    pass
                await asyncio.sleep(1.5)
                from submission_state import has_confirm_validation_errors, _url_signals as _url_sig
                html_after_final = await page.content()
                _, still_confirm, success_after = _url_sig(page.url, form_url_before)
                if has_confirm_validation_errors(html_after_final):
                    meta["confirm_validation_failed"] = True
                    meta["final_submit_clicked"] = False
                elif still_confirm and not success_after:
                    meta["confirm_submit_stalled"] = True
                    meta["final_submit_clicked"] = True
                else:
                    meta["final_submit_clicked"] = True
            else:
                return False, detail or "final_submit_click_failed", meta
        elif await _try_scoped_submit() or await _try_legacy_once():
            meta["steps_clicked"] = 2
            audited2 = await _audit_buttons(page, contact_scope)
            if not [b for b in audited2 if b.get("classification") == NEXT_STEP_SAFE]:
                meta["final_submit_clicked"] = True
        else:
            return False, "confirmation_no_final_submit", meta
    else:
        meta["final_submit_clicked"] = True

    return True, "", meta


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
            await _page_fill(page, sel, message)
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
    住所・建物 split / 単一 / 都道府県別select / 市町村 の組み合わせに対応。
    """
    async def _is_text_field(selector: str) -> bool:
        try:
            tag = await page.eval_on_selector(selector, "el => el.tagName.toLowerCase()")
            return tag in ("input", "textarea")
        except Exception:
            return False

    city = fields.get("city_field")
    if city and await _is_text_field(city):
        await _page_fill(page, city, SENDER_ADDRESS_LINE1)

    l1, l2 = fields.get("address_line1_field"), fields.get("address_line2_field")
    single = fields.get("address_field")
    has_pref = bool(fields.get("prefecture_field"))

    if l1 and l2:
        if await _is_text_field(l1):
            await _page_fill(page, l1, SENDER_ADDRESS_LINE1)
        if await _is_text_field(l2):
            await _page_fill(page, l2, SENDER_ADDRESS_LINE2)
        return

    if l1 and not l2:
        if await _is_text_field(l1):
            text = (
                _address_without_prefecture(SENDER_ADDRESS_FULL, SENDER_PREFECTURE)
                if has_pref
                else SENDER_ADDRESS_FULL
            )
            await _page_fill(page, l1, text)
        return

    if single and await _is_text_field(single):
        if has_pref:
            await _page_fill(page, single, _address_without_prefecture(SENDER_ADDRESS_FULL, SENDER_PREFECTURE))
        else:
            await _page_fill(page, single, SENDER_ADDRESS_FULL)
        return


# ─── メイン送信処理 ───────────────────────────────────────────────────────────

async def submit_prepared_form(
    prepared,
    *,
    lp_url: str,
    message_slug: str,
    preflight_mapping_hash: str | None = None,
    company: dict | None = None,
    allow_confirmation_final_submit: bool = False,
) -> dict:
    """
    FINAL_SUBMIT using the same PreparedFormSnapshot state (no second prepare).
    Caller must have authorized the snapshot and passed validate_snapshot_invariants.
    """
    from shared_form_prepare import (
        RUNTIME_DIVERGENCE,
        validate_snapshot_invariants,
    )

    form_url = prepared.form_url
    prep = prepared.prep
    page = prepared.page
    selection = prep.selection
    fields = prep.fields
    message = prep.message

    valid, inv_reasons = await validate_snapshot_invariants(prepared)
    if not valid:
        return {
            "status": "error",
            "reason": RUNTIME_DIVERGENCE,
            "form_url": form_url,
            "lp_url": lp_url,
            "message_slug": message_slug,
            "runtime_divergence": inv_reasons,
            "production_mapping_hash": prep.mapping_hash,
            "prepare_snapshot": prep.snapshot,
        }

    if _SUBMIT_FORBIDDEN:
        return {
            "status": "skipped",
            "reason": "submit_forbidden",
            "form_url": form_url,
            "lp_url": lp_url,
            "message_slug": message_slug,
            "production_mapping_hash": prep.mapping_hash,
            "prepare_snapshot": prep.snapshot,
            "single_snapshot": True,
        }

    await asyncio.sleep(random.uniform(SEND_INTERVAL_MIN, SEND_INTERVAL_MAX))

    html_before_submit = await page.content()
    from submission_state import _count_forms
    form_count_before = _count_forms(html_before_submit)
    post_requests: list[str] = []
    post_responses: list[dict] = []

    def _on_request(req):
        if req.method == "POST":
            post_requests.append(req.url)

    async def _on_response(resp):
        try:
            if resp.request.method.upper() != "POST":
                return
            body = await resp.text()
            headers = await resp.all_headers()
            digest = hashlib.sha256((body or "").encode("utf-8", errors="replace")).hexdigest()
            marker_re = re.compile(r"mail_sent|mailsent|送信完了|送信しました|ありがとうございました|error|invalid|failed", re.I)
            match = marker_re.search(body or "")
            start = max(0, (match.start() - 300) if match else 0)
            excerpt = (body or "")[start:start + (1200 if match else 500)]
            post_responses.append({
                "url": resp.url,
                "status": resp.status,
                "headers": {k: v for k, v in headers.items() if k.lower() in {
                    "content-type", "location", "cache-control", "x-powered-by",
                }},
                "content_type": headers.get("content-type", ""),
                "body_sha256": digest,
                "body_excerpt": excerpt,
            })
        except Exception:
            pass

    page.on("request", _on_request)
    page.on("response", _on_response)
    from cf7_feedback import attach_cf7_feedback_capture
    cf7_feedback_responses = attach_cf7_feedback_capture(page)

    ok_submit, submit_err, submit_meta = await _click_submit(
        page,
        fields,
        allow_confirmation_final_submit=allow_confirmation_final_submit,
    )
    submit_meta["html_before"] = html_before_submit
    submit_meta["form_count_before"] = form_count_before
    submit_meta["form_url"] = form_url
    submit_meta["post_requests"] = post_requests
    submit_meta["post_responses"] = post_responses
    submit_meta["production_mapping_hash"] = prep.mapping_hash
    submit_meta["preflight_mapping_hash"] = preflight_mapping_hash
    submit_meta["prepare_snapshot"] = prep.snapshot
    submit_meta["field_map"] = prep.field_map
    submit_meta["required_choices"] = prep.choice_log
    submit_meta["cf7_feedback_responses"] = cf7_feedback_responses
    submit_meta["single_snapshot"] = True
    if cf7_feedback_responses:
        submit_meta["cf7_feedback"] = cf7_feedback_responses[-1]

    if not ok_submit:
        return {
            "status": "error",
            "reason": submit_err,
            "form_url": form_url,
            "lp_url": lp_url,
            "message_slug": message_slug,
            "submission_meta": submit_meta,
            "production_mapping_hash": prep.mapping_hash,
            "prepare_snapshot": prep.snapshot,
        }

    try:
        await page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except Exception:
        pass
    await _await_post_submit_settle(page)

    final_url = page.url
    html_after = await page.content()
    submit_meta["form_count_after"] = _count_forms(html_after)
    from submission_state import (
        CONFIRMED_SENT,
        classify_submission_outcome,
        outcome_to_send_status,
    )

    outcome = classify_submission_outcome(
        final_url=final_url,
        form_url=form_url,
        html=html_after,
        meta=submit_meta,
    )
    send_status = outcome_to_send_status(outcome)
    prepared.submitted = True

    if outcome.state != CONFIRMED_SENT:
        return {
            "status": send_status,
            "reason": outcome.reason,
            "form_url": form_url,
            "lp_url": lp_url,
            "message_slug": message_slug,
            "submission_meta": submit_meta,
            "submission_state": outcome.state,
            "final_url": final_url,
            "message_selection": selection_as_dict(selection),
            **selection.to_log_fields(),
        }

    _record_real_submission()
    return {
        "status": "sent",
        "reason": outcome.reason,
        "form_url": form_url,
        "lp_url": lp_url,
        "message_slug": message_slug,
        "message_selection": selection_as_dict(selection),
        **selection.to_log_fields(),
        "final_url": final_url,
        "submission_meta": submit_meta,
        "submission_state": CONFIRMED_SENT,
        "production_mapping_hash": prep.mapping_hash,
        "prepare_snapshot": prep.snapshot,
    }


async def send_form(
    company: dict,
    message: str,
    lp_url: str,
    *,
    preflight_snapshot: dict | None = None,
    preflight_mapping_hash: str | None = None,
    preflight_evidence: dict | None = None,
    prepared_snapshot=None,
    allow_expected_selector_refinement: bool = False,
    fixed_message_variant: str | None = None,
    fixed_subject: str | None = None,
    v2_send_payload=None,
) -> dict:
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
        # TLS bypass is opt-in and intended only for discovery/preflight
        # of explicitly recovered cohorts.
        # Default and production behavior remains strict TLS verification.
        _tls_discovery_mode = (
            os.environ.get("ARI_PREFLIGHT_TLS_DISCOVERY", "")
            .strip()
            .lower()
            in {"1", "true", "yes"}
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            ignore_https_errors=_tls_discovery_mode,
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

            # ── 2–3. SINGLE-SNAPSHOT: prepare_once → authorize → submit ────
            from shared_form_prepare import (
                RUNTIME_DIVERGENCE,
                authorize_snapshot,
                build_preflight_semantic_evidence,
                mark_snapshot_authorized,
                prepare_once,
            )

            if prepared_snapshot is not None:
                prepared = prepared_snapshot
            else:
                html = await page.content()
                prepared = await prepare_once(
                    page,
                    str(form_url_raw).strip(),
                    message,
                    lp_url,
                    allow_validation_fallback=False,
                    html=html,
                    fixed_message_variant=fixed_message_variant,
                    fixed_subject=fixed_subject,
                )
                prepared.page = page
                prepared.browser = browser
                prepared.context = context

            prep = prepared.prep
            if prep.blocked or not prep.ok:
                await browser.close()
                status = "skipped" if prep.reason in (
                    "form_not_suitable", "unsuitable_required_choices",
                    "compact_message_exceeds_maxlength",
                ) else "error"
                return {
                    "status": status,
                    "reason": prep.reason,
                    "form_url": str(form_url_raw).strip(),
                    "lp_url": lp_url,
                    "message_slug": message_slug,
                    "production_mapping_hash": prep.mapping_hash,
                    "prepare_snapshot": prep.snapshot,
                    "single_snapshot": True,
                }

            fields = prep.fields
            selection = prep.selection
            message = prep.message
            print(f"  📝 {format_selection_log_line(selection)}")

            if prep.field_map.get("message") not in ("FILLED", "FOUND"):
                await browser.close()
                return {
                    "status": "error",
                    "reason": "message_field_not_found",
                    "form_url": str(form_url_raw).strip(),
                    "lp_url": lp_url,
                    "message_slug": message_slug,
                }

            from message_variant import VARIANT_V2

            # Authorize fresh snapshot against FULL_PREFLIGHT semantic evidence
            semantic_evidence = preflight_evidence
            auth_meta: dict = {}
            if semantic_evidence is None and preflight_snapshot:
                semantic_evidence = dict(preflight_snapshot)
                if preflight_mapping_hash:
                    semantic_evidence.setdefault("mapping_hash", preflight_mapping_hash)

            if fixed_message_variant == VARIANT_V2 and not semantic_evidence:
                from v2_send_authorization import (
                    ImmutableV2SendPayload,
                    authorize_v2_fixed_snapshot,
                )

                if v2_send_payload is None:
                    await browser.close()
                    return {
                        "status": "error",
                        "reason": RUNTIME_DIVERGENCE,
                        "form_url": str(form_url_raw).strip(),
                        "lp_url": lp_url,
                        "message_slug": message_slug,
                        "runtime_divergence": ["v2_send_payload_missing"],
                        "prepare_snapshot": prep.snapshot,
                        "single_snapshot": True,
                    }

                payload = (
                    v2_send_payload
                    if isinstance(v2_send_payload, ImmutableV2SendPayload)
                    else ImmutableV2SendPayload(**v2_send_payload)
                )
                authorized, auth_reasons = authorize_v2_fixed_snapshot(prepared, payload)
                if not authorized:
                    await browser.close()
                    return {
                        "status": "error",
                        "reason": RUNTIME_DIVERGENCE,
                        "form_url": str(form_url_raw).strip(),
                        "lp_url": lp_url,
                        "message_slug": message_slug,
                        "runtime_divergence": auth_reasons,
                        "v2_authorization": "payload_parity_failed",
                        "prepare_snapshot": prep.snapshot,
                        "single_snapshot": True,
                    }
                auth_meta["v2_payload_authorized"] = True
            elif semantic_evidence:
                from shared_form_prepare import mark_snapshot_authorized
                from evidence_reauthorization import authorize_production_evidence

                authorized, auth_reasons, auth_meta = authorize_production_evidence(
                    prepared,
                    semantic_evidence,
                    allow_selector_refinement=allow_expected_selector_refinement,
                )
                if not authorized:
                    await browser.close()
                    return {
                        "status": "error",
                        "reason": RUNTIME_DIVERGENCE,
                        "form_url": str(form_url_raw).strip(),
                        "lp_url": lp_url,
                        "message_slug": message_slug,
                        "preflight_mapping_hash": semantic_evidence.get("mapping_hash"),
                        "production_mapping_hash": prep.mapping_hash,
                        "runtime_divergence": auth_reasons,
                        "hash_drift_class": auth_meta.get("hash_drift_class"),
                        "prepare_snapshot": prep.snapshot,
                        "single_snapshot": True,
                    }
                mark_snapshot_authorized(prepared)

            result = await submit_prepared_form(
                prepared,
                lp_url=lp_url,
                message_slug=message_slug,
                preflight_mapping_hash=(
                    preflight_mapping_hash or (semantic_evidence or {}).get("mapping_hash")
                ),
                company=company,
            )
            if auth_meta.get("evidence_reauthorized"):
                result["evidence_reauthorized"] = True
                result["reauthorization_reason"] = auth_meta.get("reauthorization_reason")
                result["hash_drift_class"] = auth_meta.get("hash_drift_class")
                result["preflight_mapping_hash"] = auth_meta.get("preflight_hash")
                result["production_mapping_hash"] = auth_meta.get("production_hash") or prep.mapping_hash
            await browser.close()
            return result

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
