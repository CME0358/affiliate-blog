"""
submission_state.py — ARI 送信成功判定コントラクト

States:
  CONFIRMED_SENT              最終送信完了の強い証拠あり
  CONFIRMATION_REACHED        確認画面到達のみ（SENT ではない）
  FAILED                      送信失敗
  MANUAL_INTERVENTION_REQUIRED CAPTCHA 等
  UNKNOWN                     証拠不足
  SKIPPED                     意図的スキップ
  FORM_NOT_SUITABLE           営業問合せとして合理的に満たせない必須項目あり
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ─── State constants ───────────────────────────────────────────────────────────

CONFIRMED_SENT = "CONFIRMED_SENT"
CONFIRMATION_REACHED = "CONFIRMATION_REACHED"
FAILED = "FAILED"
MANUAL_INTERVENTION_REQUIRED = "MANUAL_INTERVENTION_REQUIRED"
UNKNOWN = "UNKNOWN"
SKIPPED = "SKIPPED"
FORM_NOT_SUITABLE = "FORM_NOT_SUITABLE"
NOT_SENT = "not_sent"

# Legacy sent.csv raw value
RAW_SENT = "sent"

# External success evidence (explicit confirmation only — never auto-inferred)
EXTERNAL_CONFIRMATION = "EXTERNAL_CONFIRMATION"
EXTERNAL_CONFIRMATION_TYPES = (
    "automatic_acknowledgement_email",
    "submission_receipt",
    "external_confirmation_record",
)

# Effective statuses that block automatic duplicate send
DUPLICATE_BLOCK_STATUSES = frozenset({CONFIRMED_SENT, RAW_SENT})

# Statuses that do NOT permanently exclude — require manual review for resend
NON_BLOCKING_EFFECTIVE_STATUSES = frozenset({
    CONFIRMATION_REACHED,
    FAILED,
    UNKNOWN,
    FORM_NOT_SUITABLE,
    NOT_SENT,
})

_CONFIRM_HTML_KEYWORDS = (
    "確認画面",
    "入力内容の確認",
    "入力内容確認",
    "この内容で送信",
    "内容をご確認",
    "ご入力内容",
    "入力内容をご確認",
)

_CONFIRM_URL_FRAGMENTS = (
    "/confirm",
    "confirmation",
    "confirm.php",
    "conf.php",
    "/conf/",
)

_SUCCESS_HTML_KEYWORDS = (
    "送信完了",
    "送信しました",
    "送信いたしました",
    "送信が完了",
    "ありがとうございました",
    "お問い合わせを受け付け",
    "お問い合わせありがとう",
    "受付完了",
    "受け付けました",
    "thank you",
    "thanks for",
)

_SUCCESS_URL_FRAGMENTS = (
    "thanks",
    "thank-you",
    "thankyou",
    "/complete",
    "/done",
    "/success",
    "完了",
)

_CAPTCHA_KEYWORDS = (
    "recaptcha",
    "g-recaptcha",
    "hcaptcha",
    "captcha",
    "turnstile",
)

# Generic completion markers (not site-specific)
_WPCF7_SUCCESS_MARKERS = (
    "wpcf7-mail-sent-ok",
    "wpcf7-form sent",
    "wpcf7-submit",
)

# MW WP Form (WordPress plugin) — generic state markers, not site-specific
_MW_WP_FORM_SUCCESS_MARKERS = (
    "mw_wp_form_complete",
)
_MW_WP_FORM_PRE_COMPLETE_MARKERS = (
    "mw_wp_form_input",
    "mw_wp_form_confirm",
)

_COMPLETION_CLASS_FRAGMENTS = (
    "mail-sent-ok",
    "thanks",
    "thank-you",
    "complete",
    "completion",
    "success-message",
    "form-complete",
    "mw_wp_form_complete",
)

_COMPLETION_HEADING_KEYWORDS = (
    "送信完了",
    "送信しました",
    "ありがとうございました",
    "お問い合わせを受け付け",
    "受付完了",
)

_CONFIRM_VALIDATION_ERROR_PATTERNS = (
    "を選択してください",
    "は一覧にありません",
    "入力してください",
    "必須項目が未記入",
    "必須項目です",
)

_POSTMAIL_URL_FRAGMENT = "postmail"
_POSTMAIL_SUCCESS_PHRASES = (
    "送信ありがとう",
    "送信しました",
    "送信が完了",
    "メールを送信",
    "お問い合わせありがとう",
    "受け付けました",
    "送信完了",
)
_POSTMAIL_ERROR_PHRASES = (
    "必須項目",
    "入力されていません",
    "送信できませんでした",
    "エラーが発生",
)

_SAME_URL_POST_SUCCESS_PHRASES = _POSTMAIL_SUCCESS_PHRASES + (
    "ありがとうございました",
    "お問い合わせを受け付け",
    "受付完了",
)


@dataclass
class SubmissionEvidence:
    final_url: str = ""
    form_url: str = ""
    html_excerpt: str = ""
    html_before_excerpt: str = ""
    has_success_dom: bool = False
    has_confirmation_dom: bool = False
    has_confirmation_url: bool = False
    has_success_url: bool = False
    final_submit_clicked: bool = False
    confirmation_reached: bool = False
    captcha_detected: bool = False
    post_requests: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    completion_signal: str = ""
    external_confirmation_type: str = ""
    form_count_before: int = -1
    form_count_after: int = -1
    mw_wp_form_state_before: str = "UNKNOWN_STATE"
    mw_wp_form_state_after: str = "UNKNOWN_STATE"
    inquiry_post_requests: list[str] = field(default_factory=list)
    ignored_post_requests: list[str] = field(default_factory=list)


@dataclass
class SubmissionOutcome:
    state: str
    reason: str
    evidence: SubmissionEvidence
    counts_toward_confirmed_sent: bool = False


def _html_signals(html: str) -> tuple[bool, bool, bool]:
    html_l = (html or "").lower()
    success = any(k.lower() in html_l for k in _SUCCESS_HTML_KEYWORDS)
    confirm = any(k in (html or "") for k in _CONFIRM_HTML_KEYWORDS)
    captcha = any(k in html_l for k in _CAPTCHA_KEYWORDS)
    return success, confirm, captcha


def _url_signals(final_url: str, form_url: str) -> tuple[bool, bool, bool]:
    final_u = (final_url or "").rstrip("/").lower()
    form_u = (form_url or "").rstrip("/").lower()
    changed = bool(final_u and form_u and final_u != form_u)
    confirm_url = any(f in final_u for f in _CONFIRM_URL_FRAGMENTS)
    success_url = any(f in final_u for f in _SUCCESS_URL_FRAGMENTS)
    return changed, confirm_url, success_url


def _count_forms(html: str) -> int:
    return (html or "").lower().count("<form")


def has_confirm_validation_errors(html: str) -> bool:
    """確認画面でのサーバ側バリデーションエラー（汎用パターン）。"""
    text = html or ""
    return any(p in text for p in _CONFIRM_VALIDATION_ERROR_PATTERNS)


def _same_path(url_a: str, url_b: str) -> bool:
    """Compare URLs ignoring hash fragment and trailing slash."""
    try:
        from urllib.parse import urlparse
        a = urlparse((url_a or "").split("#")[0].rstrip("/"))
        b = urlparse((url_b or "").split("#")[0].rstrip("/"))
        return a.netloc == b.netloc and a.path.rstrip("/") == b.path.rstrip("/")
    except Exception:
        return False


def _detect_post_response_completion(meta: dict, html_after: str, form_url: str) -> tuple[bool, str]:
    """
    Same-URL / full-page POST: success phrases in response body or updated DOM.
    POST alone without success text → False (caller keeps UNKNOWN).
    """
    before = (meta.get("html_before") or "")
    after = html_after or ""
    for entry in meta.get("post_responses") or []:
        body = entry.get("body_excerpt") or ""
        url = entry.get("url") or ""
        if any(p in body for p in _POSTMAIL_ERROR_PHRASES):
            continue
        if not _same_path(url, form_url) and _POSTMAIL_URL_FRAGMENT not in url.lower():
            if not any(k in url.lower() for k in ("contact", "form", "mail", "send", "inquiry")):
                continue
        for phrase in _SAME_URL_POST_SUCCESS_PHRASES:
            if phrase in body and phrase not in before:
                return True, "post_response_success_body"
            if phrase in body and phrase not in after[: len(before) + 200]:
                return True, "post_response_success_body"
    return False, ""


def _detect_title_change(meta: dict, html_after: str) -> tuple[bool, str]:
    """Title changed to success-oriented text after final submit."""
    import re
    before = meta.get("html_before") or ""
    m_before = re.search(r"<title[^>]*>([^<]+)</title>", before, re.I)
    m_after = re.search(r"<title[^>]*>([^<]+)</title>", html_after or "", re.I)
    if not m_before or not m_after:
        return False, ""
    t_before = m_before.group(1).strip()
    t_after = m_after.group(1).strip()
    if t_before == t_after:
        return False, ""
    if any(k in t_after for k in _COMPLETION_HEADING_KEYWORDS + _SUCCESS_HTML_KEYWORDS):
        return True, "title_change_success"
    return False, ""


def _detect_postmail_completion(
    html_before: str,
    html_after: str,
    meta: dict,
) -> tuple[bool, str]:
    """Postmail CGI 等 — full-page POST 後の明示的成功メッセージ。"""
    final_url = (meta.get("final_url") or "").lower()
    if _POSTMAIL_URL_FRAGMENT not in final_url:
        return False, ""
    after = html_after or ""
    before = html_before or ""
    if any(p in after for p in _POSTMAIL_ERROR_PHRASES):
        return False, ""
    for phrase in _POSTMAIL_SUCCESS_PHRASES:
        if phrase in after and phrase not in before:
            return True, "postmail_success_message_appeared"
    if any(p in after for p in _POSTMAIL_SUCCESS_PHRASES):
        fc_before = meta.get("form_count_before", _count_forms(before))
        fc_after = meta.get("form_count_after", _count_forms(after))
        if fc_before > 0 and fc_after == 0:
            return True, "postmail_form_removed_success"
    return False, ""


def _detect_completion_transition(
    html_before: str,
    html_after: str,
    meta: dict,
) -> tuple[bool, str]:
    """
    same-URL submit 向け completion 証拠（強いもののみ）。
    form reset / URL unchanged 単独では False。
    """
    before_l = (html_before or "").lower()
    after_l = (html_after or "").lower()

    postmail_ok, postmail_reason = _detect_postmail_completion(html_before, html_after, meta)
    if postmail_ok:
        return True, postmail_reason

    post_resp_ok, post_resp_reason = _detect_post_response_completion(meta, html_after, meta.get("form_url") or "")
    if post_resp_ok:
        return True, post_resp_reason

    title_ok, title_reason = _detect_title_change(meta, html_after)
    if title_ok:
        return True, title_reason

    # Contact Form 7 AJAX success
    for marker in _WPCF7_SUCCESS_MARKERS:
        if marker in after_l and marker not in before_l:
            if "mail-sent-ok" in marker or " wpcf7-form sent" in after_l:
                return True, "wpcf7_mail_sent_ok"
    if "wpcf7-mail-sent-ok" in after_l:
        return True, "wpcf7_mail_sent_ok"

    # MW WP Form — same-URL multi-step completion (plugin-generic classes)
    fc_before = meta.get("form_count_before", _count_forms(html_before))
    fc_after = meta.get("form_count_after", _count_forms(html_after))
    for marker in _MW_WP_FORM_SUCCESS_MARKERS:
        if marker not in after_l:
            continue
        if marker not in before_l:
            return True, "mw_wp_form_complete_appeared"
        if any(m in before_l for m in _MW_WP_FORM_PRE_COMPLETE_MARKERS):
            return True, "mw_wp_form_state_to_complete"
        if fc_before > 0 and fc_after == 0:
            return True, "mw_wp_form_complete_form_removed"

    # Completion class / block newly visible
    for frag in _COMPLETION_CLASS_FRAGMENTS:
        if frag in after_l and frag not in before_l:
            if any(k in after_l for k in _SUCCESS_HTML_KEYWORDS + _COMPLETION_HEADING_KEYWORDS):
                return True, f"completion_block_{frag}"

    # Success heading newly appeared (same URL)
    for kw in _COMPLETION_HEADING_KEYWORDS:
        if kw in (html_after or "") and kw not in (html_before or ""):
            return True, "success_heading_appeared"

    # Form removed / replaced by completion (strong)
    if fc_before > 0 and fc_after == 0:
        if any(k.lower() in after_l for k in _SUCCESS_HTML_KEYWORDS):
            return True, "form_removed_with_success_dom"
        if any(m in after_l for m in _MW_WP_FORM_SUCCESS_MARKERS):
            return True, "form_removed_mw_wp_form_complete"

    # Hidden success state in aria-live / response container
    if 'role="alert"' in after_l or 'aria-live' in after_l:
        if any(k in (html_after or "") for k in _SUCCESS_HTML_KEYWORDS):
            if not any(k in (html_before or "") for k in _SUCCESS_HTML_KEYWORDS):
                return True, "aria_live_success"

    return False, ""


def _is_inquiry_post(url: str, form_url: str) -> bool:
    u = (url or "").lower()
    if any(h in u for h in (
        "google-analytics", "analytics.google", "googletagmanager", "doubleclick", "g/collect",
        "wordpress-popular-posts", "/views/", "pageview", "tracking", "beacon",
    )):
        return False
    if any(k in u for k in ("wpcf7", "formmail", "postmail", "mwform", "contact", "mail.php", "cgi-bin", "send")):
        return True
    try:
        from urllib.parse import urlparse
        if form_url and urlparse(url).netloc == urlparse(form_url).netloc and "POST" not in url:
            return "/contact" in u or "form" in u
    except Exception:
        pass
    return False


def _cf7_feedback_matches_current_attempt(meta: dict, cf7: Any) -> bool:
    """Bind terminal CF7 feedback to this attempt's captured response identity."""
    import re
    expected_id = str(getattr(cf7, "contact_form_id", "") or "")
    if not expected_id:
        return False
    matching_response = False
    from cf7_feedback import is_cf7_feedback_url
    for entry in meta.get("post_responses") or []:
        url = str(entry.get("url") or "")
        status = int(entry.get("status") or 0)
        if not is_cf7_feedback_url(url) or not (200 <= status < 300):
            continue
        match = re.search(r"/contact-forms/([^/]+)/feedback", url, re.I)
        if match and match.group(1) == expected_id:
            matching_response = True
            break
    if not matching_response:
        return False
    captured = meta.get("cf7_feedback_responses") or []
    for raw in captured:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("contact_form_id") or "") != expected_id:
            continue
        if str(raw.get("status") or "") != str(getattr(cf7, "status", "") or ""):
            continue
        expected_hash = str(getattr(cf7, "posted_data_hash", "") or "")
        if expected_hash and str(raw.get("posted_data_hash") or "") != expected_hash:
            continue
        return True
    return False


def classify_submission_outcome(
    *,
    final_url: str,
    form_url: str,
    html: str,
    meta: dict | None = None,
    submit_error: str = "",
    captcha_hint: bool = False,
    skipped: bool = False,
) -> SubmissionOutcome:
    """
    Success State Contract に基づき outcome を分類する。
    URL の confirmation だけでは CONFIRMED_SENT にしない。
    """
    meta = meta or {}
    html_before = meta.get("html_before") or ""
    meta_for_detect = {**meta, "form_url": form_url}
    ev = SubmissionEvidence(
        final_url=final_url or "",
        form_url=form_url or "",
        html_excerpt=(html or "")[:500],
        html_before_excerpt=html_before[:500],
        final_submit_clicked=bool(meta.get("final_submit_clicked")),
        confirmation_reached=bool(meta.get("confirmation_reached")),
        captcha_detected=captcha_hint,
        post_requests=list(meta.get("post_requests") or []),
        form_count_before=int(meta.get("form_count_before", -1)),
        form_count_after=int(meta.get("form_count_after", -1)),
    )
    from mw_wp_form_state import MW_COMPLETE, MW_CONFIRMATION, detect_mw_wp_form_state
    ev.mw_wp_form_state_before = detect_mw_wp_form_state(html_before)
    ev.mw_wp_form_state_after = detect_mw_wp_form_state(html)
    ev.inquiry_post_requests = [u for u in ev.post_requests if _is_inquiry_post(u, form_url)]
    ev.ignored_post_requests = [u for u in ev.post_requests if u not in ev.inquiry_post_requests]

    if skipped:
        return SubmissionOutcome(SKIPPED, "skipped", ev)

    if captcha_hint:
        ev.reason_codes.append("captcha_detected")
        return SubmissionOutcome(MANUAL_INTERVENTION_REQUIRED, "captcha_detected", ev)

    if submit_error:
        ev.reason_codes.append(submit_error)
        if "captcha" in submit_error.lower() or "recaptcha" in submit_error.lower():
            return SubmissionOutcome(MANUAL_INTERVENTION_REQUIRED, submit_error, ev)
        return SubmissionOutcome(FAILED, submit_error, ev)

    success_dom, confirm_dom, captcha_dom = _html_signals(html)
    url_changed, confirm_url, success_url = _url_signals(final_url, form_url)
    ev.has_success_dom = success_dom
    ev.has_confirmation_dom = confirm_dom
    ev.has_confirmation_url = confirm_url
    ev.has_success_url = success_url
    ev.captcha_detected = ev.captcha_detected or captcha_dom

    if captcha_dom:
        return SubmissionOutcome(MANUAL_INTERVENTION_REQUIRED, "captcha_in_dom", ev)

    # MW WP Form has an explicit state machine. Confirmation is never success;
    # complete is strong plugin-generic completion evidence.
    if ev.mw_wp_form_state_after == MW_COMPLETE:
        ev.reason_codes.append("mw_wp_form_complete")
        ev.completion_signal = "mw_wp_form_complete"
        return SubmissionOutcome(
            CONFIRMED_SENT, "mw_wp_form_complete", ev, counts_toward_confirmed_sent=True,
        )
    if ev.mw_wp_form_state_after == MW_CONFIRMATION:
        ev.reason_codes.append("mw_wp_form_confirm")
        return SubmissionOutcome(
            CONFIRMATION_REACHED, "mw_wp_form_confirmation_reached", ev,
        )

    # EXTERNAL_CONFIRMATION — explicit human-verified evidence only (never auto-inferred)
    ext_conf = meta.get("external_confirmation")
    if isinstance(ext_conf, dict) and ext_conf.get("confirmed") and ev.final_submit_clicked:
        ext_type = ext_conf.get("type") or EXTERNAL_CONFIRMATION
        ev.external_confirmation_type = str(ext_type)
        ev.reason_codes.append("external_confirmation")
        ev.completion_signal = f"external_confirmation:{ext_type}"
        return SubmissionOutcome(
            CONFIRMED_SENT,
            "external_confirmation",
            ev,
            counts_toward_confirmed_sent=True,
        )

    # CF7 REST feedback response (stronger than POST alone)
    from cf7_feedback import classify_cf7_feedback, is_cf7_feedback_url, parse_cf7_feedback_body

    cf7_raw = meta.get("cf7_feedback")
    cf7_responses = meta.get("cf7_feedback_responses") or []
    cf7 = None
    if cf7_raw:
        cf7 = parse_cf7_feedback_body(cf7_raw)
    elif cf7_responses:
        cf7 = parse_cf7_feedback_body(cf7_responses[-1])

    cf7_identity_matched = bool(cf7 and cf7.parsed_ok and _cf7_feedback_matches_current_attempt(meta, cf7))
    if cf7 and cf7.parsed_ok and (ev.final_submit_clicked or cf7_identity_matched):
        cf7_state, cf7_reason = classify_cf7_feedback(cf7)
        ev.reason_codes.append(f"cf7_status:{cf7.status}")
        if cf7_identity_matched:
            ev.reason_codes.append("cf7_identity_matched_current_attempt")
        if cf7.message:
            ev.completion_signal = cf7_reason
        if cf7_state == CONFIRMED_SENT:
            return SubmissionOutcome(
                CONFIRMED_SENT, cf7_reason, ev, counts_toward_confirmed_sent=True,
            )
        if cf7_state == FORM_NOT_SUITABLE:
            return SubmissionOutcome(FORM_NOT_SUITABLE, cf7_reason, ev)
        if cf7_state == FAILED:
            return SubmissionOutcome(FAILED, cf7_reason, ev)

    completion_ok, completion_reason = _detect_completion_transition(html_before, html, meta_for_detect)
    if completion_ok:
        ev.completion_signal = completion_reason
        ev.reason_codes.append(completion_reason)
        if ev.final_submit_clicked:
            return SubmissionOutcome(
                CONFIRMED_SENT, completion_reason, ev, counts_toward_confirmed_sent=True,
            )

    # ── CONFIRMED_SENT: 強い成功証拠 ─────────────────────────────────────
    if success_dom:
        ev.reason_codes.append("success_dom")
        return SubmissionOutcome(
            CONFIRMED_SENT, "success_message_in_dom", ev, counts_toward_confirmed_sent=True,
        )

    if ev.final_submit_clicked and success_url and not confirm_url:
        ev.reason_codes.append("success_url_after_final_submit")
        return SubmissionOutcome(
            CONFIRMED_SENT, "success_url_after_final_submit", ev, counts_toward_confirmed_sent=True,
        )

    if ev.final_submit_clicked and meta.get("post_success"):
        ev.reason_codes.append("post_success")
        return SubmissionOutcome(
            CONFIRMED_SENT, "post_xhr_success", ev, counts_toward_confirmed_sent=True,
        )

    # POST + success DOM (same URL AJAX)
    inquiry_posts = ev.inquiry_post_requests
    if ev.final_submit_clicked and inquiry_posts and success_dom:
        ev.reason_codes.append("post_with_success_dom")
        return SubmissionOutcome(
            CONFIRMED_SENT, "post_with_success_dom", ev, counts_toward_confirmed_sent=True,
        )

    # URL alone with "confirmation" is NOT sufficient for CONFIRMED_SENT
    if ev.final_submit_clicked and url_changed and not confirm_url and not confirm_dom:
        # URL changed away from form, not to confirmation pattern — weak but with final click
        if success_url:
            return SubmissionOutcome(
                CONFIRMED_SENT, "url_change_success_fragment", ev, counts_toward_confirmed_sent=True,
            )

    if meta.get("confirm_validation_failed"):
        ev.reason_codes.append("confirm_validation_failed")
        return SubmissionOutcome(FAILED, "confirm_validation_failed", ev)

    # ── CONFIRMATION_REACHED ───────────────────────────────────────────────
    if ev.confirmation_reached or confirm_dom or confirm_url:
        if not ev.final_submit_clicked:
            ev.reason_codes.append("confirmation_without_final_submit")
            return SubmissionOutcome(
                CONFIRMATION_REACHED, "confirmation_page_no_final_submit", ev,
            )
        if confirm_url or confirm_dom:
            ev.reason_codes.append("confirmation_url_or_dom_without_success")
            return SubmissionOutcome(
                CONFIRMATION_REACHED, "confirmation_reached_no_success_evidence", ev,
            )

    if meta.get("confirmation_reached") and not meta.get("final_submit_clicked"):
        return SubmissionOutcome(CONFIRMATION_REACHED, "confirmation_only", ev)

    # ── UNKNOWN ──────────────────────────────────────────────────────────
    cf7_posts = [u for u in ev.post_requests if is_cf7_feedback_url(u)]
    if ev.final_submit_clicked and cf7_posts and not (cf7 and cf7.parsed_ok):
        return SubmissionOutcome(UNKNOWN, "cf7_response_unknown", ev)

    inquiry_posts = ev.inquiry_post_requests
    if (
        ev.final_submit_clicked
        and inquiry_posts
        and not success_dom
        and not completion_ok
        and not cf7_posts
    ):
        ev.reason_codes.append("post_only_no_completion")
        return SubmissionOutcome(UNKNOWN, "post_only_no_completion_evidence", ev)

    if ev.final_submit_clicked and not success_dom and not success_url:
        return SubmissionOutcome(UNKNOWN, "final_click_no_completion_evidence", ev)

    if not ev.final_submit_clicked and url_changed and confirm_url:
        return SubmissionOutcome(CONFIRMATION_REACHED, "navigated_to_confirmation_url", ev)

    if not ev.final_submit_clicked:
        return SubmissionOutcome(FAILED, "no_final_submit", ev)

    return SubmissionOutcome(UNKNOWN, "insufficient_evidence", ev)


def normalize_effective_status(raw_or_corrected: str) -> str:
    """sent.csv / corrections の値を canonical state へ。"""
    s = (raw_or_corrected or "").strip()
    if not s or s == NOT_SENT:
        return NOT_SENT
    if s == RAW_SENT:
        return CONFIRMED_SENT  # raw sent treated as confirmed unless corrected
    upper = s.upper()
    if upper in {
        CONFIRMED_SENT, CONFIRMATION_REACHED, FAILED,
        MANUAL_INTERVENTION_REQUIRED, UNKNOWN, SKIPPED, FORM_NOT_SUITABLE,
    }:
        return upper
    return s


def should_block_duplicate_send(effective_status: str) -> bool:
    """自動送信 duplicate lock — CONFIRMED_SENT のみ。"""
    norm = normalize_effective_status(effective_status)
    return norm in DUPLICATE_BLOCK_STATUSES or norm == CONFIRMED_SENT


@dataclass
class SubmissionCounters:
    attempted: int = 0
    final_submit_clicked: int = 0
    confirmed_sent: int = 0
    confirmation_reached: int = 0
    failed: int = 0
    skipped: int = 0
    manual_intervention: int = 0
    unknown: int = 0
    form_not_suitable: int = 0

    def record(self, outcome: SubmissionOutcome, *, attempted: bool = True) -> None:
        if attempted:
            self.attempted += 1
        if outcome.evidence.final_submit_clicked:
            self.final_submit_clicked += 1
        st = outcome.state
        if st == CONFIRMED_SENT:
            self.confirmed_sent += 1
        elif st == CONFIRMATION_REACHED:
            self.confirmation_reached += 1
        elif st == FAILED:
            self.failed += 1
        elif st == SKIPPED:
            self.skipped += 1
        elif st == FORM_NOT_SUITABLE:
            self.form_not_suitable += 1
        elif st == MANUAL_INTERVENTION_REQUIRED:
            self.manual_intervention += 1
        elif st == UNKNOWN:
            self.unknown += 1

    def to_dict(self) -> dict[str, int]:
        return {
            "attempted": self.attempted,
            "final_submit_clicked": self.final_submit_clicked,
            "confirmed_sent": self.confirmed_sent,
            "confirmation_reached": self.confirmation_reached,
            "failed": self.failed,
            "skipped": self.skipped,
            "manual_intervention": self.manual_intervention,
            "unknown": self.unknown,
            "form_not_suitable": self.form_not_suitable,
        }


def record_send_result(counters: SubmissionCounters, result: dict, *, attempted: bool = True) -> None:
    """send_form / batch runner の result dict から counters を更新。"""
    meta = result.get("submission_meta") or {}
    state = result.get("submission_state")
    ev = SubmissionEvidence(
        final_url=result.get("final_url", ""),
        form_url=result.get("form_url", ""),
        final_submit_clicked=bool(meta.get("final_submit_clicked")),
        confirmation_reached=bool(meta.get("confirmation_reached")),
    )
    if state:
        outcome = SubmissionOutcome(
            state,
            result.get("reason", ""),
            ev,
            counts_toward_confirmed_sent=(state == CONFIRMED_SENT),
        )
    elif result.get("status") == "sent":
        outcome = SubmissionOutcome(CONFIRMED_SENT, result.get("reason", ""), ev, True)
    elif result.get("status") == "pending":
        outcome = SubmissionOutcome(MANUAL_INTERVENTION_REQUIRED, result.get("reason", ""), ev)
    elif result.get("status") == "skipped":
        outcome = SubmissionOutcome(SKIPPED, result.get("reason", ""), ev)
    elif result.get("status") == "error":
        reason = result.get("reason", "")
        if "captcha" in reason.lower() or "recaptcha" in reason.lower():
            outcome = SubmissionOutcome(MANUAL_INTERVENTION_REQUIRED, reason, ev)
        else:
            outcome = SubmissionOutcome(FAILED, reason, ev)
    else:
        outcome = SubmissionOutcome(UNKNOWN, result.get("reason", ""), ev)
    counters.record(outcome, attempted=attempted)


def outcome_to_send_status(outcome: SubmissionOutcome) -> str:
    """form_sender / log_manager 互換 status 文字列。"""
    if outcome.state == CONFIRMED_SENT:
        return "sent"
    if outcome.state == MANUAL_INTERVENTION_REQUIRED:
        return "pending"
    if outcome.state == SKIPPED:
        return "skipped"
    if outcome.state == FORM_NOT_SUITABLE:
        return "skipped"
    return "error"
