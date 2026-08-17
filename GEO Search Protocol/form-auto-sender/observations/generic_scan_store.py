"""
observations/generic_scan_store.py — Persist derived generic scan signals (not raw HTML).

Key namespace: generic_scan:{domain} (separate from preview:{token}).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

SCAN_TTL_SECONDS = 90 * 24 * 60 * 60
DOMAIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$", re.IGNORECASE)


class GenericScanStoreError(RuntimeError):
    def __init__(self, message: str, code: str = "GENERIC_SCAN_STORE_ERROR") -> None:
        super().__init__(message)
        self.code = code


def is_valid_domain_key(domain: str) -> bool:
    d = (domain or "").lower().removeprefix("www.")
    return bool(d) and len(d) <= 253 and bool(DOMAIN_PATTERN.match(d))


def resolve_generic_scan_backend() -> str:
    explicit = (os.environ.get("GENERIC_SCAN_STORE_BACKEND") or "").strip().lower()
    on_vercel = os.environ.get("VERCEL") == "1"
    if on_vercel:
        return "upstash"
    if explicit:
        return explicit
    if os.environ.get("UPSTASH_REDIS_REST_URL") and os.environ.get("UPSTASH_REDIS_REST_TOKEN"):
        return "upstash"
    return "memory"


def _storage_key(domain: str) -> str:
    prefix = (os.environ.get("GENERIC_SCAN_KEY_PREFIX") or "generic_scan:").strip()
    d = domain.lower().removeprefix("www.")
    return f"{prefix}{d}"


def _ttl_seconds() -> int:
    raw = os.environ.get("GENERIC_SCAN_TTL_SECONDS", str(SCAN_TTL_SECONDS))
    try:
        val = int(raw)
        return val if val > 0 else SCAN_TTL_SECONDS
    except ValueError:
        return SCAN_TTL_SECONDS


def _upstash_pipeline(command: list[Any]) -> Any:
    base_url = (os.environ.get("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or ""
    if not base_url or not token:
        raise GenericScanStoreError("Upstash credentials missing", "GENERIC_SCAN_UNCONFIGURED")

    req = urllib.request.Request(
        f"{base_url}/pipeline",
        data=json.dumps([command]).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise GenericScanStoreError(f"Upstash HTTP {e.code}", "GENERIC_SCAN_STORE_ERROR") from e
    except urllib.error.URLError as e:
        raise GenericScanStoreError(str(e.reason), "GENERIC_SCAN_STORE_ERROR") from e

    if isinstance(body, list) and body:
        item = body[0]
        if isinstance(item, dict) and item.get("error"):
            raise GenericScanStoreError(str(item["error"]), "GENERIC_SCAN_STORE_ERROR")
        if isinstance(item, dict):
            return item.get("result")
        return item
    if isinstance(body, dict):
        result = body.get("result") or []
        return result[0] if result else None
    return None


class MemoryGenericScanStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def save(self, row: dict[str, Any]) -> dict[str, Any]:
        dom = (row.get("domain") or "").lower().removeprefix("www.")
        if not is_valid_domain_key(dom):
            raise GenericScanStoreError("invalid domain", "GENERIC_SCAN_INVALID_DOMAIN")
        self._data[dom] = json.loads(json.dumps(row, ensure_ascii=False))
        return {"ok": True, "domain": dom}

    def get(self, domain: str) -> dict[str, Any] | None:
        dom = (domain or "").lower().removeprefix("www.")
        if not is_valid_domain_key(dom):
            return None
        return self._data.get(dom)

    def delete(self, domain: str) -> bool:
        dom = (domain or "").lower().removeprefix("www.")
        return self._data.pop(dom, None) is not None


class UpstashGenericScanStore:
    def save(self, row: dict[str, Any]) -> dict[str, Any]:
        dom = (row.get("domain") or "").lower().removeprefix("www.")
        if not is_valid_domain_key(dom):
            raise GenericScanStoreError("invalid domain", "GENERIC_SCAN_INVALID_DOMAIN")
        payload = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        result = _upstash_pipeline(["SETEX", _storage_key(dom), _ttl_seconds(), payload])
        if result != "OK":
            raise GenericScanStoreError(f"SETEX unexpected: {result}", "GENERIC_SCAN_STORE_ERROR")
        return {"ok": True, "domain": dom}

    def get(self, domain: str) -> dict[str, Any] | None:
        dom = (domain or "").lower().removeprefix("www.")
        if not is_valid_domain_key(dom):
            return None
        raw = _upstash_pipeline(["GET", _storage_key(dom)])
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def delete(self, domain: str) -> bool:
        dom = (domain or "").lower().removeprefix("www.")
        if not is_valid_domain_key(dom):
            return False
        _upstash_pipeline(["DEL", _storage_key(dom)])
        return True


_STORE: Any | None = None


def create_generic_scan_store(backend: str | None = None) -> Any:
    resolved = backend or resolve_generic_scan_backend()
    if resolved == "upstash":
        return UpstashGenericScanStore()
    if resolved == "memory":
        return MemoryGenericScanStore()
    raise GenericScanStoreError(f"unknown backend: {resolved}", "GENERIC_SCAN_UNKNOWN_BACKEND")


def get_generic_scan_store() -> Any:
    global _STORE
    if _STORE is None:
        _STORE = create_generic_scan_store()
    return _STORE


def reset_generic_scan_store() -> None:
    global _STORE
    _STORE = None


def save_generic_scan(row: dict[str, Any]) -> dict[str, Any]:
    return get_generic_scan_store().save(row)


def load_generic_scan(domain: str) -> dict[str, Any] | None:
    return get_generic_scan_store().get(domain)
