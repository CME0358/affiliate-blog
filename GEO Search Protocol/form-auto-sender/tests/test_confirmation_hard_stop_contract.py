import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from form_fill_no_submit import BACK, FINAL_SUBMIT
from form_sender import _click_submit
from mw_wp_form_state import MW_UNKNOWN
from submission_state import CONFIRMATION_REACHED, classify_submission_outcome


def _button(label, classification, order):
    return {"label": label, "classification": classification, "selector": f"#b{order}",
            "tag": "input", "type": "submit", "name": "", "value": label, "order": order}


def _page():
    page = MagicMock()
    page.url = "https://example.test/contact"
    page.wait_for_load_state = AsyncMock()
    page.content = AsyncMock(return_value="<h1>入力内容の確認</h1><button>戻る</button><input type=submit value=送信する>")
    return page


def test_single_step_confirmation_returns_without_final_click():
    async def run():
        page = _page(); initial = _button("送信", FINAL_SUBMIT, 0)
        final = _button("送信する", FINAL_SUBMIT, 0); back = _button("戻る", BACK, 1)
        mw = {"state": MW_UNKNOWN, "plugin_present": False}
        with patch("form_sender._prepare_submit_surface", new=AsyncMock()), \
             patch("mw_wp_form_state.detect_mw_wp_form_state_dom", new=AsyncMock(return_value=mw)), \
             patch("form_fill_no_submit._audit_buttons", new=AsyncMock(side_effect=[[initial], [final, back]])), \
             patch("form_fill_no_submit._click_button_scoped", new=AsyncMock(return_value=True)) as click, \
             patch("form_fill_no_submit.click_final_submit_button", new=AsyncMock()) as final_click, \
             patch("form_sender.asyncio.sleep", new=AsyncMock()):
            ok, reason, meta = await _click_submit(page, {"contact_form_scope": "form#contact"})
        return ok, reason, meta, click, final_click
    ok, reason, meta, click, final_click = asyncio.run(run())
    assert ok and reason == ""
    assert meta["confirmation_reached"] is True
    assert meta["final_submit_clicked"] is False
    assert meta["confirmation_auto_follow"] is False
    assert meta["confirmation_snapshot"]["final_control_count"] == 1
    assert click.await_count == 1
    final_click.assert_not_awaited()
    outcome = classify_submission_outcome(final_url="https://example.test/contact", form_url="https://example.test/contact",
        html="<h1>入力内容の確認</h1>", meta=meta)
    assert outcome.state == CONFIRMATION_REACHED


def test_explicit_multistep_opt_in_isolated():
    async def run():
        page = _page(); initial = _button("送信", FINAL_SUBMIT, 0)
        final = _button("送信する", FINAL_SUBMIT, 0); back = _button("戻る", BACK, 1)
        mw = {"state": MW_UNKNOWN, "plugin_present": False}
        with patch("form_sender._prepare_submit_surface", new=AsyncMock()), \
             patch("mw_wp_form_state.detect_mw_wp_form_state_dom", new=AsyncMock(return_value=mw)), \
             patch("form_fill_no_submit._audit_buttons", new=AsyncMock(side_effect=[[initial], [final, back]])), \
             patch("form_fill_no_submit._click_button_scoped", new=AsyncMock(return_value=True)), \
             patch("form_fill_no_submit.click_final_submit_button", new=AsyncMock(return_value=(True, "送信する", final))) as final_click, \
             patch("submission_state.has_confirm_validation_errors", return_value=False), \
             patch("form_sender.asyncio.sleep", new=AsyncMock()):
            ok, reason, meta = await _click_submit(page, {"contact_form_scope": "form#contact"},
                allow_confirmation_final_submit=True)
        return ok, reason, meta, final_click
    ok, reason, meta, final_click = asyncio.run(run())
    assert ok and reason == ""
    assert meta["confirmation_reached"] is True
    assert meta["confirmation_auto_follow"] is True
    assert meta["final_submit_clicked"] is True
    final_click.assert_awaited_once()


def test_default_signature_is_fail_closed():
    import inspect
    assert inspect.signature(_click_submit).parameters["allow_confirmation_final_submit"].default is False
