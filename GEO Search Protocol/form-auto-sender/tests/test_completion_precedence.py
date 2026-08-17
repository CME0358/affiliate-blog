import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from form_fill_no_submit import BACK, FINAL_SUBMIT
from form_sender import _click_submit
from mw_wp_form_state import MW_UNKNOWN
from submission_state import CONFIRMED_SENT, CONFIRMATION_REACHED, FAILED, classify_submission_outcome


def _cf7_meta(status="mail_sent", form_id="45", *, clicked=False, confirmation=True):
    raw = {"contact_form_id": int(form_id), "status": status,
           "message": "正常に送信されました" if status == "mail_sent" else "spam",
           "posted_data_hash": "abc123" if status == "mail_sent" else "", "into": f"#wpcf7-f{form_id}-p12-o1",
           "invalid_fields": []}
    return {"final_submit_clicked": clicked, "confirmation_reached": confirmation,
        "post_requests": [f"https://example.test/wp-json/contact-form-7/v1/contact-forms/{form_id}/feedback"],
        "post_responses": [{"url": f"https://example.test/wp-json/contact-form-7/v1/contact-forms/{form_id}/feedback",
            "status": 200, "body_excerpt": str(raw)}],
        "cf7_feedback": raw, "cf7_feedback_responses": [raw]}


def test_cf7_mail_sent_precedes_weak_confirmation_heuristic():
    outcome = classify_submission_outcome(final_url="https://example.test/contact/",
        form_url="https://example.test/contact/", html='<input disabled value="この内容で送信する">',
        meta=_cf7_meta())
    assert outcome.state == CONFIRMED_SENT
    assert outcome.reason == "cf7_mail_sent"
    assert "cf7_identity_matched_current_attempt" in outcome.evidence.reason_codes


def test_terminal_confirmed_cannot_be_downgraded():
    outcome = classify_submission_outcome(final_url="https://example.test/contact/confirm",
        form_url="https://example.test/contact/", html="<h1>入力内容の確認</h1>", meta=_cf7_meta())
    assert outcome.state == CONFIRMED_SENT


def test_cf7_identity_mismatch_does_not_override_confirmation():
    meta = _cf7_meta()
    meta["post_responses"][0]["url"] = "https://example.test/wp-json/contact-form-7/v1/contact-forms/999/feedback"
    outcome = classify_submission_outcome(final_url="https://example.test/contact/",
        form_url="https://example.test/contact/", html="<h1>入力内容の確認</h1>", meta=meta)
    assert outcome.state == CONFIRMATION_REACHED


def test_explicit_cf7_spam_remains_failed():
    outcome = classify_submission_outcome(final_url="https://example.test/contact/",
        form_url="https://example.test/contact/", html="<h1>入力内容の確認</h1>",
        meta=_cf7_meta(status="spam"))
    assert outcome.state == FAILED
    assert outcome.reason == "cf7_spam"


def _button(label, classification, *, disabled=False, order=0):
    return {"label": label, "classification": classification, "selector": f"#b{order}",
        "tag": "input", "type": "submit", "name": "", "value": label, "order": order,
        "disabled": disabled, "ariaDisabled": False}


def test_disabled_submit_alone_is_not_confirmation():
    async def run():
        page = MagicMock(); page.url = "https://example.test/contact"; page.wait_for_load_state = AsyncMock()
        page.content = AsyncMock(return_value='<input disabled value="この内容で送信する">')
        initial = _button("送信", FINAL_SUBMIT)
        disabled = _button("この内容で送信する", FINAL_SUBMIT, disabled=True)
        mw = {"state": MW_UNKNOWN, "plugin_present": False}
        with patch("form_sender._prepare_submit_surface", new=AsyncMock()), \
             patch("mw_wp_form_state.detect_mw_wp_form_state_dom", new=AsyncMock(return_value=mw)), \
             patch("form_fill_no_submit._audit_buttons", new=AsyncMock(side_effect=[[initial], [disabled]])), \
             patch("form_fill_no_submit._click_button_scoped", new=AsyncMock(return_value=True)), \
             patch("form_sender.asyncio.sleep", new=AsyncMock()):
            return await _click_submit(page, {"contact_form_scope": "form#contact"})
    ok, reason, meta = asyncio.run(run())
    assert ok and not reason
    assert meta["confirmation_reached"] is False


def test_interactive_confirmation_with_back_still_hard_stops():
    async def run():
        page = MagicMock(); page.url = "https://example.test/contact"; page.wait_for_load_state = AsyncMock()
        page.content = AsyncMock(return_value="<h1>入力内容の確認</h1>")
        initial = _button("送信", FINAL_SUBMIT)
        final = _button("この内容で送信する", FINAL_SUBMIT)
        back = _button("戻る", BACK, order=1)
        mw = {"state": MW_UNKNOWN, "plugin_present": False}
        with patch("form_sender._prepare_submit_surface", new=AsyncMock()), \
             patch("mw_wp_form_state.detect_mw_wp_form_state_dom", new=AsyncMock(return_value=mw)), \
             patch("form_fill_no_submit._audit_buttons", new=AsyncMock(side_effect=[[initial], [final, back]])), \
             patch("form_fill_no_submit._click_button_scoped", new=AsyncMock(return_value=True)), \
             patch("form_sender.asyncio.sleep", new=AsyncMock()):
            return await _click_submit(page, {"contact_form_scope": "form#contact"})
    ok, reason, meta = asyncio.run(run())
    assert ok and not reason
    assert meta["confirmation_reached"] is True
    assert meta["final_submit_clicked"] is False

