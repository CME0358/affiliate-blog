"""Semantic submit-target resolver — regression tests."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from canonical_submit_target import resolve_canonical_submit_target
from multistep_state import CONFIRMATION, FINAL_SUBMIT_READY, FORM_ENTRY
from submit_target_semantics import (
    RESOLUTION_AMBIGUOUS,
    RESOLUTION_EQUIVALENT,
    RESOLUTION_UNIQUE,
    build_specific_selector,
    filter_actionable_candidates,
    resolve_submit_from_candidates,
)

SCOPE = 'form[data-ari-form-scope="contact"]'


def _c(**kwargs):
    base = {
        "tag": "input",
        "type": "submit",
        "name": "",
        "id": "",
        "className": "",
        "value": "",
        "text": "",
        "label": "",
        "visible": True,
        "enabled": True,
        "inSelectedForm": True,
        "domOrder": 0,
        "formAction": "",
    }
    base.update(kwargs)
    if not base.get("label"):
        base["label"] = base.get("value") or base.get("text") or ""
    return base


class TestSemanticResolverCases(unittest.TestCase):
    def test_single_button_type_submit(self):
        res = resolve_submit_from_candidates(
            [_c(tag="button", type="submit", value="送信する", label="送信する")],
            contact_form_scope=SCOPE,
            multistep_state=FORM_ENTRY,
        )
        self.assertTrue(res["valid"])
        self.assertEqual(res["policy"], RESOLUTION_UNIQUE)
        self.assertIn("button", res["selector"])

    def test_single_input_type_submit(self):
        res = resolve_submit_from_candidates(
            [_c(value="送信", label="送信")],
            contact_form_scope=SCOPE,
            multistep_state=FORM_ENTRY,
        )
        self.assertTrue(res["valid"])
        self.assertIn('[value="送信"]', res["selector"])

    def test_input_type_image(self):
        res = resolve_submit_from_candidates(
            [_c(type="image", value="Send", label="Send")],
            contact_form_scope=SCOPE,
            multistep_state=FORM_ENTRY,
        )
        self.assertTrue(res["valid"])
        self.assertIn("image", res["selector"])

    def test_submit_plus_back_button(self):
        res = resolve_submit_from_candidates(
            [
                _c(type="button", value="入力画面へ戻る", label="入力画面へ戻る", domOrder=0),
                _c(value="送信する", label="送信する", domOrder=1),
            ],
            contact_form_scope=SCOPE,
            multistep_state=FINAL_SUBMIT_READY,
        )
        self.assertTrue(res["valid"])
        self.assertIn("送信", res["selector"])

    def test_confirm_plus_back_on_confirmation_page(self):
        res = resolve_submit_from_candidates(
            [
                _c(type="button", value="入力画面へ戻る", label="入力画面へ戻る", domOrder=0),
                _c(value="確認画面へ", label="確認画面へ", className="wpcf7-confirm", domOrder=1),
            ],
            contact_form_scope=SCOPE,
            multistep_state=FORM_ENTRY,
        )
        self.assertTrue(res["valid"])
        self.assertIn("wpcf7-confirm", res["selector"])

    def test_multiple_equivalent_submit_controls(self):
        res = resolve_submit_from_candidates(
            [
                _c(value="送信する", label="送信する", domOrder=0),
                _c(value="送信する", label="送信する", domOrder=1),
            ],
            contact_form_scope=SCOPE,
            multistep_state=FINAL_SUBMIT_READY,
        )
        self.assertTrue(res["valid"])
        self.assertEqual(res["policy"], RESOLUTION_EQUIVALENT)
        self.assertEqual(res["equivalent_count"], 2)

    def test_multiple_materially_different_submit_controls(self):
        res = resolve_submit_from_candidates(
            [
                _c(value="送信する", label="送信する", domOrder=0),
                _c(value="問い合わせる", label="問い合わせる", domOrder=1),
            ],
            contact_form_scope=SCOPE,
            multistep_state=FINAL_SUBMIT_READY,
        )
        self.assertFalse(res["valid"])
        self.assertEqual(res["policy"], RESOLUTION_AMBIGUOUS)

    def test_hidden_duplicate_submit_excluded(self):
        actionable = filter_actionable_candidates([
            _c(value="確認画面へ", visible=False, domOrder=0),
            _c(value="送信する", visible=True, domOrder=1),
        ])
        res = resolve_submit_from_candidates(
            actionable,
            contact_form_scope=SCOPE,
            multistep_state=FORM_ENTRY,
        )
        self.assertTrue(res["valid"])
        self.assertIn("送信", res["selector"])

    def test_disabled_duplicate_submit_excluded(self):
        res = resolve_submit_from_candidates(
            [
                _c(value="送信する", enabled=False, domOrder=0),
                _c(value="送信する", enabled=True, domOrder=1),
            ],
            contact_form_scope=SCOPE,
            multistep_state=FINAL_SUBMIT_READY,
        )
        self.assertTrue(res["valid"])
        self.assertEqual(res["policy"], RESOLUTION_UNIQUE)

    def test_dynamically_duplicated_button_equivalent(self):
        res = resolve_submit_from_candidates(
            [
                _c(tag="button", type="submit", value="送信", label="送信", className="btn primary", domOrder=0),
                _c(tag="button", type="submit", value="送信", label="送信", className="btn primary", domOrder=1),
            ],
            contact_form_scope=SCOPE,
            multistep_state=FINAL_SUBMIT_READY,
        )
        self.assertTrue(res["valid"])
        self.assertEqual(res["policy"], RESOLUTION_EQUIVALENT)

    def test_multistep_next_vs_final_on_form_entry(self):
        res = resolve_submit_from_candidates(
            [
                _c(value="確認画面へ", label="確認画面へ", domOrder=0),
                _c(value="送信する", label="送信する", domOrder=1),
            ],
            contact_form_scope=SCOPE,
            multistep_state=FORM_ENTRY,
        )
        self.assertTrue(res["valid"])
        self.assertIn("確認", res["selector"])

    def test_berk_regression_fixture(self):
        candidates = [
            _c(tag="button", type="button", id="ZipInput", text="住所の自動入力", label="住所の自動入力", domOrder=0),
            _c(
                value="確認画面へ",
                className="wpcf7-form-control wpcf7-confirm wpcf7c-elm-step1 wpcf7c-btn-confirm wpcf7c-force-hide",
                visible=False,
                domOrder=1,
            ),
            _c(
                type="button",
                value="入力画面へ戻る",
                className="wpcf7-form-control wpcf7-back wpcf7c-elm-step2 wpcf7c-btn-back wpcf7c-force-hide",
                visible=False,
                domOrder=2,
            ),
            _c(
                value="送信する",
                className="wpcf7-form-control wpcf7-submit has-spinner form-btn-bg",
                visible=True,
                domOrder=3,
            ),
        ]
        res = resolve_submit_from_candidates(
            candidates,
            contact_form_scope=SCOPE,
            submit_selector_hint='form input[type="submit"]',
            multistep_state=FORM_ENTRY,
        )
        self.assertTrue(res["valid"])
        self.assertEqual(res["policy"], RESOLUTION_UNIQUE)
        self.assertIn("wpcf7-submit", res["selector"])
        self.assertEqual("送信する", res["candidate"]["value"])

    def test_build_specific_selector_prefers_value(self):
        sel = build_specific_selector(SCOPE, _c(value="送信する"))
        self.assertIn('[value="送信する"]', sel)


class TestCanonicalResolverIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_live_resolution_refines_broad_selector(self):
        page = MagicMock()
        page.url = "https://example.com/contact/"
        page.evaluate = AsyncMock(side_effect=self._mock_eval)

        ok, record, reasons = await resolve_canonical_submit_target(
            page,
            contact_form_scope=SCOPE,
            submit_selector='form input[type="submit"]',
        )
        self.assertTrue(ok, reasons)
        self.assertIn("wpcf7-submit", record["submit_selector"])
        self.assertEqual(record["resolution_policy"], RESOLUTION_UNIQUE)

    async def _mock_eval(self, js, arg=None):
        if "hint_candidates" in js or "hintMatches" in js:
            return {
                "ok": True,
                "hint_candidates": [
                    {
                        "tag": "input", "type": "submit", "name": "", "id": "",
                        "className": "wpcf7-submit", "value": "送信する", "text": "",
                        "label": "送信する", "visible": True, "enabled": True,
                        "inSelectedForm": True, "domOrder": 1, "formAction": "/contact/",
                    },
                    {
                        "tag": "input", "type": "submit", "name": "", "id": "",
                        "className": "wpcf7-confirm hidden", "value": "確認画面へ", "text": "",
                        "label": "確認画面へ", "visible": False, "enabled": True,
                        "inSelectedForm": True, "domOrder": 0, "formAction": "/contact/",
                    },
                ],
            }
        return {
            "valid": True,
            "reason": "valid",
            "matches": 1,
            "visible": True,
            "enabled": True,
            "element_type": "input:submit",
            "label": "送信する",
            "final_submit_eligible": True,
        }


if __name__ == "__main__":
    unittest.main()
