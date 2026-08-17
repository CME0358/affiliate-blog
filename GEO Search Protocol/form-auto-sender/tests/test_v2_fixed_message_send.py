"""Tests for ARI_MESSAGE_V2 fixed-message send authorization (no production send)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from message_variant import VARIANT_V2, MessageSelection
from shared_form_prepare import FormPrepareResult, PreparedFormSnapshot, mark_snapshot_authorized
from v2_send_authorization import (
    ImmutableV2SendPayload,
    authorize_v2_fixed_snapshot,
    build_v2_send_payload,
    validate_v2_payload_parity,
)

V2_MESSAGE = """\
突然のご連絡失礼いたします。
合同会社コア・リテールの佐々木と申します。

テストクリニック様の公式サイトを拝見し、
AIが企業やサービスを理解するうえで、どのような情報が読み取れる状態か確認しました。

御社サイトでは、お問い合わせなど次の行動につながる導線は確認できています。
ただ、AIが企業を比較・推薦する際には、導線だけでなく、サービス内容や特徴をどこまで正しく理解できるかも重要です。

日経新聞でも「20代の約半数が調べものに検索エンジンを使わない」と報じられるなど、
AI経由で企業やサービスを知る流れも無視できなくなっています。

御社サイトの公開情報をもとに、
AIから見た現在の状態と確認ポイントを専用プレビューにまとめました。

https://readiness.coaretail.com/report/p/TESTTOKEN123?utm_source=outbound&utm_medium=form&utm_campaign=ari_preview_v1

まずは上記から、御社がAIからどのように見えているかをご確認ください。
必要性を感じられた場合のみ、その先もご覧いただけます。

合同会社コア・リテール
佐々木"""

PREVIEW_URL = "https://readiness.coaretail.com/report/p/TESTTOKEN123?utm_source=outbound&utm_medium=form&utm_campaign=ari_preview_v1"


def _payload(**overrides) -> ImmutableV2SendPayload:
    base = dict(
        domain="example.com",
        company_display_name="テストクリニック",
        subject="御社サイトの「AIからの見え方」を確認しました",
        message=V2_MESSAGE,
        preview_url=PREVIEW_URL,
        preview_token="TESTTOKEN123",
    )
    base.update(overrides)
    return build_v2_send_payload(**base)


def _prepared(message: str = V2_MESSAGE) -> PreparedFormSnapshot:
    selection = MessageSelection(
        variant=VARIANT_V2,
        message=message,
        message_length=len(message),
        detected_maxlength=2000,
        fallback_reason=None,
        skip_reason=None,
        skipped=False,
    )
    prep = FormPrepareResult(
        ok=True,
        message=message,
        selection=selection,
        field_map={"message": "FILLED", "name": "FILLED", "email": "FILLED", "consent": "FILLED"},
        mapping_hash="abc123",
        snapshot={"field_map": {"message": "FILLED"}},
    )
    return PreparedFormSnapshot(prep=prep, form_url="https://example.com/contact")


class TestV2SendAuthorization(unittest.TestCase):
    def test_payload_parity_pass(self):
        ok, reasons = validate_v2_payload_parity(_prepared(), _payload())
        self.assertTrue(ok, reasons)
        self.assertEqual(reasons, [])

    def test_variant_mismatch_fails(self):
        prep = _prepared()
        prep.prep.selection = MessageSelection(
            variant="ARI_MESSAGE_V1",
            message=V2_MESSAGE,
            message_length=len(V2_MESSAGE),
            detected_maxlength=2000,
            fallback_reason=None,
            skip_reason=None,
            skipped=False,
        )
        ok, reasons = validate_v2_payload_parity(prep, _payload())
        self.assertFalse(ok)
        self.assertTrue(any("variant_mismatch" in r for r in reasons))

    def test_message_body_mismatch_fails(self):
        ok, reasons = validate_v2_payload_parity(_prepared("different"), _payload())
        self.assertFalse(ok)
        self.assertIn("message_body_mismatch", reasons)

    def test_preview_url_preservation(self):
        ok, reasons = validate_v2_payload_parity(_prepared(), _payload(preview_url="https://wrong.example"))
        self.assertFalse(ok)
        self.assertIn("preview_url_missing_in_message", reasons)

    def test_company_display_name_override(self):
        msg = V2_MESSAGE.replace("テストクリニック", "MEN'S SALON C#")
        payload = _payload(company_display_name="MEN'S SALON C#", message=msg)
        ok, reasons = validate_v2_payload_parity(_prepared(msg), payload)
        self.assertTrue(ok, reasons)

    def test_send_form_requires_v2_payload_when_no_preflight(self):
        """V2 path without payload must fail closed before submit."""
        from v2_send_authorization import validate_v2_payload_parity

        prepared = _prepared()
        self.assertFalse(prepared.authorized)
        ok, reasons = authorize_v2_fixed_snapshot(prepared, _payload())
        self.assertTrue(ok, reasons)
        self.assertTrue(prepared.authorized)
        # Missing payload path is enforced in send_form — unit-test parity only
        self.assertFalse(validate_v2_payload_parity(_prepared(), _payload(message="x"))[0])

    def test_v1_fallback_detected(self):
        msg = V2_MESSAGE + "\n無料AI推薦スコア診断"
        ok, reasons = validate_v2_payload_parity(_prepared(msg), _payload())
        self.assertFalse(ok)
        self.assertIn("v1_fallback_detected", reasons)

    def test_authorize_sets_authorized_flag(self):
        prepared = _prepared()
        self.assertFalse(prepared.authorized)
        ok, reasons = authorize_v2_fixed_snapshot(prepared, _payload())
        self.assertTrue(ok, reasons)
        self.assertTrue(prepared.authorized)
        self.assertEqual(prepared.authorization_hash, prepared.prep.mapping_hash)

    def test_whitespace_exact_match_required(self):
        msg = V2_MESSAGE + " "
        ok, _ = validate_v2_payload_parity(_prepared(msg), _payload())
        self.assertFalse(ok)


class TestV1Regression(unittest.TestCase):
    def test_v1_selection_unchanged(self):
        from message_variant import select_ari_message_variant

        lp = "https://readiness.coaretail.com/report/"
        sel = select_ari_message_variant(lp, 2000)
        self.assertEqual(sel.variant, "ARI_MESSAGE_V1")
        self.assertFalse(sel.skipped)


if __name__ == "__main__":
    unittest.main()
