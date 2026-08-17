import asyncio
from unittest.mock import AsyncMock, MagicMock

from form_fill_no_submit import (FINAL_SUBMIT, NEXT_STEP_SAFE, classify_button_action,
                                 pick_final_submit_button)
from mw_wp_form_state import (MW_COMPLETE, MW_CONFIRMATION, MW_INITIAL, MW_UNKNOWN,
                              detect_mw_wp_form_state, probe_mw_wp_form_state_dom)
from multistep_state import (FINAL_SUBMIT_READY, VALIDATION_FAILED,
                             detect_multistep_state_dom,
                             run_validation_feedback_once)
from submission_state import (CONFIRMATION_REACHED, CONFIRMED_SENT, UNKNOWN,
                              _is_inquiry_post, classify_submission_outcome)


def test_states():
    assert detect_mw_wp_form_state('<div class="mw_wp_form mw_wp_form_input">') == MW_INITIAL
    assert detect_mw_wp_form_state('<div class="mw_wp_form mw_wp_form_confirm">') == MW_CONFIRMATION
    assert detect_mw_wp_form_state('<div class="mw_wp_form mw_wp_form_complete">') == MW_COMPLETE
    assert detect_mw_wp_form_state('<form>plain</form>') == MW_UNKNOWN


def test_submit_confirm_is_next_step():
    assert classify_button_action("確認画面へ", "submit", name="submitConfirm") == NEXT_STEP_SAFE


def test_confirm_is_not_sent_and_complete_is_sent():
    confirm = classify_submission_outcome(final_url="https://x.test/contact", form_url="https://x.test/contact",
        html='<div class="mw_wp_form mw_wp_form_confirm">確認</div>', meta={"final_submit_clicked": True, "post_requests": ["https://x.test/contact"]})
    complete = classify_submission_outcome(final_url="https://x.test/contact", form_url="https://x.test/contact",
        html='<div class="mw_wp_form mw_wp_form_complete">完了</div>', meta={"final_submit_clicked": True, "post_requests": ["https://x.test/contact"]})
    assert confirm.state == CONFIRMATION_REACHED
    assert complete.state == CONFIRMED_SENT and complete.counts_toward_confirmed_sent


def test_tracking_posts_are_not_inquiry_posts():
    assert not _is_inquiry_post("https://analytics.google.com/g/collect", "https://x.test/contact")
    assert not _is_inquiry_post("https://x.test/wp-json/wordpress-popular-posts/v2/views/282", "https://x.test/contact")
    assert _is_inquiry_post("https://x.test/contact", "https://x.test/contact")


def test_ambiguous_final_control_fails_closed():
    buttons = [{"classification": FINAL_SUBMIT}, {"classification": FINAL_SUBMIT}]
    target, reason = pick_final_submit_button(buttons)
    assert target is None and reason == "final_submit_ambiguous:2"


def test_non_mw_post_only_remains_unknown():
    outcome = classify_submission_outcome(final_url="https://x.test/contact", form_url="https://x.test/contact",
        html="<form>same</form>", meta={"final_submit_clicked": True, "post_requests": ["https://x.test/contact"]})
    assert outcome.state == UNKNOWN


def _locator_page(*, count=0, root_class=""):
    page = MagicMock()
    roots = MagicMock()
    roots.count = AsyncMock(return_value=count)
    roots.first.get_attribute = AsyncMock(return_value=root_class)
    page.locator.return_value = roots
    page.evaluate = AsyncMock()
    return page


def test_non_mw_generic_evaluate_contract_unchanged():
    async def _run():
        page = _locator_page(count=0)
        page.evaluate = AsyncMock(return_value=VALIDATION_FAILED)
        state = await detect_multistep_state_dom(page)
        return page, state

    page, state = asyncio.run(_run())
    assert state == VALIDATION_FAILED
    page.evaluate.assert_awaited_once()


def test_mw_probe_non_match_falls_back_to_generic():
    async def _run():
        page = _locator_page(count=0)
        page.evaluate = AsyncMock(return_value=VALIDATION_FAILED)
        return page, await detect_multistep_state_dom(page)

    page, state = asyncio.run(_run())
    assert state == VALIDATION_FAILED
    page.evaluate.assert_awaited_once()


def test_mw_probe_failure_falls_back_to_generic():
    async def _run():
        page = _locator_page(count=0)
        page.locator.side_effect = RuntimeError("probe failed")
        page.evaluate = AsyncMock(return_value=VALIDATION_FAILED)
        return page, await detect_multistep_state_dom(page)

    page, state = asyncio.run(_run())
    assert state == VALIDATION_FAILED
    page.evaluate.assert_awaited_once()


def test_validation_feedback_retries_once_with_isolated_probe():
    async def _run():
        page = _locator_page(count=0)
        page.evaluate = AsyncMock(side_effect=[VALIDATION_FAILED, [], FINAL_SUBMIT_READY, []])
        choice_log = {}
        from unittest.mock import patch
        with patch(
            "required_choice_resolver.apply_rational_required_choices",
            new=AsyncMock(return_value={"applied": [], "skipped": [], "unsuitable": []}),
        ):
            first = await run_validation_feedback_once(page, choice_log)
            second = await run_validation_feedback_once(page, choice_log)
        return page, first, second

    page, first, second = asyncio.run(_run())
    assert first["retried"] is True
    assert second["retried"] is False
    # First pass: state, errors, post-retry state. Second pass: state, errors.
    assert page.evaluate.await_count == 5


def test_mw_confirm_semantics_unchanged_with_isolated_probe():
    async def _run():
        page = _locator_page(count=1, root_class="mw_wp_form mw_wp_form_confirm")
        page.evaluate = AsyncMock(return_value="FORM_ENTRY")
        return page, await detect_multistep_state_dom(page), await probe_mw_wp_form_state_dom(page)

    page, state, evidence = asyncio.run(_run())
    assert state == FINAL_SUBMIT_READY
    assert evidence["state"] == MW_CONFIRMATION
    page.evaluate.assert_not_awaited()


def test_mw_probe_does_not_consume_page_evaluate_fixture():
    async def _run():
        page = _locator_page(count=0)
        page.evaluate = AsyncMock(side_effect=[VALIDATION_FAILED])
        evidence = await probe_mw_wp_form_state_dom(page)
        state = await detect_multistep_state_dom(page)
        return page, evidence, state

    page, evidence, state = asyncio.run(_run())
    assert evidence["state"] == MW_UNKNOWN
    assert state == VALIDATION_FAILED
    page.evaluate.assert_awaited_once()
