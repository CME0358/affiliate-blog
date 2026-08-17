import unittest

from form_field_resolver import _restore_and_validate_cached_scope


RUNTIME_SCOPE = 'form[data-ari-form-scope="contact"]'
FIELDS = {
    "contact_form_scope": RUNTIME_SCOPE,
    "name_field": "#name",
    "email_field": "#email",
    "message_field": "#message",
    "submit_button": 'form input[type="submit"]',
}


class FakePage:
    def __init__(self, *, live=None, check=None):
        self.live = live or dict(FIELDS)
        self.check = check or {"ok": True, "reason": "restored", "submit_disabled": False}

    async def wait_for_timeout(self, _ms):
        return None

    async def evaluate(self, script, arg=None):
        if isinstance(arg, dict) and "scope" in arg and "cached" in arg:
            return dict(self.check)
        return dict(self.live)


class CacheScopeRestorationTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_marker_restoration_success(self):
        restored = await _restore_and_validate_cached_scope(FakePage(), dict(FIELDS))
        self.assertEqual(restored, FIELDS)

    async def test_restoration_ambiguity_falls_back(self):
        page = FakePage(check={"ok": False, "reason": "scope_not_unique", "count": 2})
        self.assertIsNone(await _restore_and_validate_cached_scope(page, dict(FIELDS)))

    async def test_multiple_submit_match_fails_closed(self):
        page = FakePage(check={"ok": False, "reason": "submit_not_unique", "count": 2})
        self.assertIsNone(await _restore_and_validate_cached_scope(page, dict(FIELDS)))

    async def test_native_scope_unaffected(self):
        fields = {**FIELDS, "contact_form_scope": "form#contactForm"}
        restored = await _restore_and_validate_cached_scope(FakePage(live=fields), fields)
        self.assertEqual(restored["contact_form_scope"], "form#contactForm")

    async def test_disabled_until_filled_is_compatible(self):
        page = FakePage(check={"ok": True, "reason": "restored", "submit_disabled": True})
        self.assertEqual(await _restore_and_validate_cached_scope(page, dict(FIELDS)), FIELDS)

    async def test_cache_path_uses_live_canonical_fields(self):
        live = {**FIELDS, "submit_button": 'form[data-ari-form-scope="contact"] .wpcf7-submit'}
        restored = await _restore_and_validate_cached_scope(FakePage(live=live), dict(FIELDS))
        self.assertEqual(restored["submit_button"], live["submit_button"])


if __name__ == "__main__":
    unittest.main()
