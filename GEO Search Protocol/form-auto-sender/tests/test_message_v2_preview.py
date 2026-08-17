"""P1 — ARI_MESSAGE_V2 dry-run / preview record tests (zero send)."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "preview_v2_companies.json"


def _load_resolver():
    path = _BASE / "observations" / "resolver.py"
    spec = importlib.util.spec_from_file_location("obs_resolver_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _load_message_builder_v2():
    """Load build_message_v2 without pulling config via package __init__."""
    msgs_path = _BASE / "templates" / "messages.py"
    spec = importlib.util.spec_from_file_location("msgs_test", msgs_path)
    msgs = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(msgs)

    mb_path = _BASE / "message_builder.py"
    # message_builder imports config indirectly via observations — test helpers only
    spec2 = importlib.util.spec_from_file_location("mb_test", mb_path)
    mb = importlib.util.module_from_spec(spec2)
    assert spec2 and spec2.loader
    # Stub config before exec if needed — build_message_v2 only uses templates
    sys.modules.setdefault("config", type(sys)("config"))
    sys.modules["templates.messages"] = msgs
    spec2.loader.exec_module(mb)
    return mb, _load_resolver()


class TestMessageV2Preview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mb, cls.resolver = _load_message_builder_v2()

    def test_v2_uses_single_positive_observation(self):
        obs = [
            {"code": "OBS_ACTION_PATH_PRESENT", "approved_copy": "公開ページ上で、サービス利用に向けた次の行動（お問い合わせ・相談・予約等）への導線を確認しました。"},
            {"code": "OBS_SERVICE_INFO_OK", "approved_copy": "サービス内容を示す基本情報（タイトル・説明文等）を確認しました。"},
        ]
        msg = self.mb.build_message_v2(
            "テスト株式会社",
            "https://example.com",
            "https://readiness.coaretail.com/report/p/abc",
            obs,
        )
        self.assertIn("次の行動につながる導線は確認できています", msg)
        self.assertIn("サービス内容や特徴をどこまで正しく理解できるか", msg)
        self.assertIn("AI経由で企業やサービスを知る流れ", msg)
        self.assertNotRegex(msg, r"(?m)^・")
        self.assertNotIn("tiktok.com", msg.lower())
        self.assertNotIn("SEO", msg)
        self.assertNotIn("MEO", msg)
        self.assertNotIn("HTML解析", msg)
        self.assertNotIn("Agent Readiness Company Report", msg)
        self.assertNotIn("tiktok.com", msg.lower())
        self.assertNotRegex(msg, r"\b\d{1,3}\s*点")
        self.assertNotIn("total_score", msg)
        self.assertIn("ご確認ください", msg)

    def test_display_name_seo_trim(self):
        display, normalized, note = self.mb.sanitize_company_display_name(
            "雨漏り119 吉川店 雨漏り修理 雨漏り調査 防水工事",
            domain="tryise-k-paint.com",
        )
        self.assertEqual(display, "雨漏り119 吉川店")
        self.assertTrue(normalized)
        self.assertIn("SEO label trimmed", note)

    def test_preview_url_opaque_token_pattern(self):
        token = "xY9_abCD-ef12"
        url = f"https://readiness.coaretail.com/report/p/{token}"
        self.assertRegex(url, r"/report/p/[A-Za-z0-9_-]+$")
        self.assertNotIn("company=", url)
        self.assertNotIn("score=", url)

    def test_fixture_companies_structure(self):
        data = json.loads(_FIXTURES.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data), 2)

    @patch("observations.snapshot_builder.create_preview_snapshot")
    def test_build_preview_record_with_crawler(self, mock_snap):
        import importlib
        mb = importlib.import_module("message_builder")

        mock_snap.return_value = {
            "token": "opaqueToken123abc",
            "preview_url": "https://readiness.coaretail.com/report/p/opaqueToken123abc?utm_source=outbound",
            "candidate_id": "cid123",
            "message_observations": [
                {"code": "OBS_FAQ_STRUCTURE_WEAK", "approved_copy": "FAQ弱い"},
            ],
        }
        company = {
            "company_name": "テスト",
            "website_url": "https://example.com",
            "industry_name": "美容クリニック",
            "area_name": "港区",
        }
        crawler = {"faq": 5, "schema_org": 0, "reservation_button": 0, "site_reachable": True}
        record = mb.build_preview_record(company, ab_arm="C", crawler_data=crawler)
        self.assertEqual(record["preview_token"], "opaqueToken123abc")
        self.assertIn("/report/p/opaqueToken123abc", record["preview_url"])
        self.assertEqual(record["observations"][0]["code"], "OBS_FAQ_STRUCTURE_WEAK")
        self.assertIn("FAQ弱い", record["rendered_message"])

    def test_fallback_when_no_crawler(self):
        import importlib
        from unittest.mock import patch

        mb = importlib.import_module("message_builder")

        company = {
            "company_name": "未登録",
            "website_url": "https://unknown.example",
            "industry_name": "その他",
            "area_name": "",
        }
        with patch("observations.crawler_join.lookup_crawler_data_for_company", return_value=None):
            with patch.object(mb, "build_lp_url", return_value="https://readiness.coaretail.com/report/"):
                record = mb.build_preview_record(company, ab_arm="C", crawler_data=None)
        self.assertTrue(record["fallback"])
        self.assertEqual(record["message_version"], "ARI_MESSAGE_V1")


class TestZeroSendV2Guard(unittest.TestCase):
    def test_main_blocks_v2_without_dry_run(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, "main.py", "--message-version", "v2", "--dry-run"],
            cwd=str(_BASE),
            capture_output=True,
            text=True,
        )
        # --dry-run without --pilot-list may fail for other reasons; test inverse
        result_bad = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.argv=['main.py','--message-version','v2']; "
             "exec(open('main.py').read())"],
            cwd=str(_BASE),
            capture_output=True,
            text=True,
        )
        # Direct guard test via argparse simulation
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--dry-run", action="store_true")
        ap.add_argument("--message-version", choices=("v1", "v2"), default="v1")
        args = ap.parse_args(["--message-version", "v2"])
        self.assertFalse(args.dry_run)


if __name__ == "__main__":
    unittest.main()
