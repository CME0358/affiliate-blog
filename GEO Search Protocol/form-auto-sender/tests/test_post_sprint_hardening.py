import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import form_field_resolver as resolver
import log_manager
from playwright_environment import prepare_isolated_browser_path
from shared_form_prepare import verify_required_text_coverage


class FakePage:
    def __init__(self, controls):
        self.controls = controls

    async def evaluate(self, _script, _args=None):
        return self.controls


class RequiredFieldHardeningTests(unittest.IsolatedAsyncioTestCase):
    def test_furigana_identifier_vocabulary(self):
        for token in ("your-ruby", "your-kana", "furigana", "kana", "ruby"):
            self.assertIn(token, resolver._EXTRACT_FIELDS_JS)

    def test_furigana_identifiers_resolve(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                for token in ("your-ruby", "your-kana", "furigana", "kana", "ruby"):
                    with self.subTest(token=token):
                        page = browser.new_page()
                        page.set_content(f'''<form>
                          <input name="your-name" aria-label="お名前">
                          <input name="{token}" required>
                          <input name="your-email" type="email">
                          <textarea name="your-message"></textarea>
                          <input type="submit" value="送信">
                        </form>''')
                        fields = page.evaluate(resolver._EXTRACT_FIELDS_JS)
                        self.assertIn(token, fields.get("furigana_name_field") or "")
                        page.close()
            finally:
                browser.close()

    async def test_unmapped_required_text_holds(self):
        result = await verify_required_text_coverage(
            FakePage([{"selector": "input[name=other]", "mapped": False, "filled": False}]),
            {"name_field": "input[name=your-name]"},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "required_text_field_unmapped")

    async def test_mapped_but_unfilled_required_text_holds(self):
        result = await verify_required_text_coverage(
            FakePage([{"selector": "input[name=your-ruby]", "mapped": True, "filled": False}]),
            {"furigana_name_field": "input[name=your-ruby]"},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "required_text_field_unfilled")

    async def test_mapped_and_filled_required_text_passes(self):
        result = await verify_required_text_coverage(
            FakePage([{"selector": "input[name=your-ruby]", "mapped": True, "filled": True}]),
            {"furigana_name_field": "input[name=your-ruby]"},
        )
        self.assertTrue(result["ok"])

    async def test_stale_cached_mapping_falls_back_to_dom(self):
        from playwright.async_api import async_playwright
        stale = {"name_field": 'input[name="your-name"]',
                 "email_field": 'input[name="your-email"]',
                 "message_field": 'textarea[name="your-message"]',
                 "submit_button": 'input[type="submit"]'}
        html = '''<form><input name="your-name"><input name="your-ruby" required>
          <input name="your-email" type="email"><textarea name="your-message"></textarea>
          <input type="submit" value="送信"></form>'''
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_content(html)
                with patch("form_field_resolver.get_cached_fields", return_value=stale), \
                     patch("form_field_resolver.put_cached_fields"):
                    fields, source = await resolver.resolve_form_fields(page, html, "https://fixture.test/contact")
                self.assertIn(source, ("dom", "dom_rescan"))
                self.assertIn("your-ruby", fields.get("furigana_name_field") or "")
            finally:
                await browser.close()


class PlaywrightEnvironmentTests(unittest.TestCase):
    def test_isolated_runtime_does_not_touch_shared_cache(self):
        shared = Path.home() / "Library/Caches/ms-playwright"
        before = sorted(str(p.relative_to(shared)) for p in shared.rglob("*")) if shared.exists() else []
        with tempfile.TemporaryDirectory() as temp:
            root = prepare_isolated_browser_path(Path(temp))
            wrapper = root / "chromium_headless_shell-1234/chrome-headless-shell-mac-x64/chrome-headless-shell"
            self.assertTrue(wrapper.is_file())
            self.assertIn("Google Chrome.app", wrapper.read_text())
        after = sorted(str(p.relative_to(shared)) for p in shared.rglob("*")) if shared.exists() else []
        self.assertEqual(before, after)


class FailureLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "failure_events.csv"
        self.correction_path = Path(self.temp.name) / "failure_status_corrections.csv"
        self.cooldown_path = Path(self.temp.name) / ".failure_cooldown.csv"
        self.patchers = [
            patch.object(log_manager, "FAILURE_EVENT_LOG", self.path),
            patch.object(log_manager, "FAILURE_STATUS_CORRECTIONS", self.correction_path),
            patch.object(log_manager, "FAILURE_COOLDOWN_INDEX", self.cooldown_path),
        ]
        for item in self.patchers:
            item.start()

    def tearDown(self):
        for item in reversed(self.patchers):
            item.stop()
        self.temp.cleanup()

    def test_append_and_execution_identity_dedupe(self):
        company = {"company_name": "Nitta", "domain": "nittaclinic.net"}
        first, event_id = log_manager.append_failure_event(
            company, event_class="FAILED", reason="validation_failed",
            source_execution="r3", attempted=True, submit_clicked=True,
            post_observed=True, event_identity="r3:nitta:failed",
        )
        second, same_id = log_manager.append_failure_event(
            company, event_class="FAILED", reason="validation_failed",
            source_execution="r3", attempted=True, submit_clicked=True,
            post_observed=True, event_identity="r3:nitta:failed",
        )
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(event_id, same_id)
        self.assertEqual(len(log_manager.load_failure_events(domain="nittaclinic.net")), 1)

    def test_distinct_presubmit_and_delivery_events_are_immutable(self):
        company = {"company_name": "Nitta", "domain": "nittaclinic.net"}
        for identity, event_class, attempted in (
            ("r1:nitta:limit", "PRE_SUBMIT_SAFETY_BLOCK", False),
            ("r3:nitta:validation", "FAILED", True),
        ):
            log_manager.append_failure_event(
                company, event_class=event_class, reason=identity,
                source_execution=identity.split(":")[0], attempted=attempted,
                submit_clicked=attempted, post_observed=attempted,
                event_identity=identity,
            )
        events = log_manager.load_failure_events(domain="nittaclinic.net")
        self.assertEqual([e["event_class"] for e in events], ["PRE_SUBMIT_SAFETY_BLOCK", "FAILED"])

    def test_status_correction_is_append_only_and_idempotent(self):
        company = {"company_name": "Seijo", "domain": "seijopeaks.com"}
        args = dict(original_status="UNKNOWN", corrected_status="FAILED",
                    reason="explicit rejection", evidence_reference="candidate.json",
                    source_execution="remaining7-r3")
        first, correction_id = log_manager.append_failure_status_correction(company, **args)
        second, same_id = log_manager.append_failure_status_correction(company, **args)
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(correction_id, same_id)
        self.assertEqual(log_manager.get_effective_failure_status("seijopeaks.com"), "FAILED")

    def test_cooldown_updates_current_state_without_mutating_event_ledger(self):
        company = {"company_name": "Nitta", "domain": "nittaclinic.net",
                   "website_url": "http://www.nittaclinic.net"}
        log_manager.append_failure_event(
            company, event_class="PRE_SUBMIT_SAFETY_BLOCK", reason="production_limit_violation",
            source_execution="r1", attempted=False, submit_clicked=False, post_observed=False,
            event_identity="r1:nitta:limit",
        )
        log_manager.record_failure_cooldown(company, "production_limit_violation")
        log_manager.record_failure_cooldown(company, "validation_failed")
        rows = log_manager._load_failure_cooldown_rows()
        self.assertEqual(next(iter(rows.values()))["reason_key"], "validation_failed")
        events = log_manager.load_failure_events(domain="nittaclinic.net")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["reason"], "production_limit_violation")


if __name__ == "__main__":
    unittest.main()
