"""
observations/preview_snapshot_store.py — Persistent preview snapshot store abstraction.

Backends (via PREVIEW_STORE_BACKEND):
  upstash     — Upstash Redis REST (production / Vercel reader + local writer)
  memory      — in-process dict (tests)
  filesystem  — local JSON files (PREVIEW_STORE_ALLOW_FILESYSTEM=1, forbidden on Vercel)

PRODUCTION USE of filesystem = FORBIDDEN.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SNAPSHOT_TTL_SECONDS = 90 * 24 * 60 * 60
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

_VAULT_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_SNAPSHOT_DIR = (
    _VAULT_ROOT / "10_Projects" / "Agent Readiness" / "data" / "preview_snapshots"
)


class PreviewStoreError(RuntimeError):
    def __init__(self, message: str, code: str = "PREVIEW_STORE_ERROR") -> None:
        super().__init__(message)
        self.code = code


def _token_hash(token: str) -> str:
    if not token:
        return "none"
    return hashlib.sha256(token.encode()).hexdigest()[:8]


def log_preview_store_event(event: str, token: str = "", **extra: Any) -> None:
    if os.environ.get("PREVIEW_STORE_SILENT") == "1":
        return
    payload = {"event": event, "token_hash": _token_hash(token), **extra}
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)


def is_valid_token(token: str) -> bool:
    return bool(token) and bool(TOKEN_PATTERN.fullmatch(token)) and len(token) <= 128


def is_expired_snapshot(snapshot: dict[str, Any]) -> bool:
    expires = snapshot.get("expires_at")
    if not expires:
        return False
    try:
        exp_dt = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > exp_dt
    except ValueError:
        return False


def resolve_preview_store_backend() -> str:
    explicit = (os.environ.get("PREVIEW_STORE_BACKEND") or "").strip().lower()
    on_vercel = os.environ.get("VERCEL") == "1"

    if on_vercel:
        if explicit in ("filesystem", "memory"):
            raise PreviewStoreError(
                "filesystem/memory backend forbidden on Vercel",
                "PREVIEW_STORE_FORBIDDEN_BACKEND",
            )
        return "upstash"

    if explicit:
        if explicit == "filesystem" and os.environ.get("PREVIEW_STORE_ALLOW_FILESYSTEM") != "1":
            raise PreviewStoreError(
                "filesystem backend requires PREVIEW_STORE_ALLOW_FILESYSTEM=1",
                "PREVIEW_STORE_FORBIDDEN_BACKEND",
            )
        return explicit

    if os.environ.get("UPSTASH_REDIS_REST_URL") and os.environ.get("UPSTASH_REDIS_REST_TOKEN"):
        return "upstash"
    if os.environ.get("PREVIEW_STORE_ALLOW_FILESYSTEM") == "1":
        return "filesystem"
    return "memory"


def _storage_key(token: str) -> str:
    prefix = (os.environ.get("PREVIEW_STORE_KEY_PREFIX") or "preview:").strip()
    return f"{prefix}{token}"


def _ttl_seconds() -> int:
    raw = os.environ.get("PREVIEW_STORE_TTL_SECONDS", str(SNAPSHOT_TTL_SECONDS))
    try:
        val = int(raw)
        return val if val > 0 else SNAPSHOT_TTL_SECONDS
    except ValueError:
        return SNAPSHOT_TTL_SECONDS


def _upstash_pipeline(command: list[Any]) -> Any:
    base_url = (os.environ.get("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or ""
    if not base_url or not token:
        raise PreviewStoreError("Upstash credentials missing", "PREVIEW_STORE_UNCONFIGURED")

    req = urllib.request.Request(
        f"{base_url}/pipeline",
        data=json.dumps([command]).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise PreviewStoreError(f"Upstash HTTP {e.code}", "PREVIEW_STORE_ERROR") from e
    except urllib.error.URLError as e:
        raise PreviewStoreError(str(e.reason), "PREVIEW_STORE_ERROR") from e

    if isinstance(body, list):
        if not body:
            return None
        item = body[0]
        if isinstance(item, dict) and item.get("error"):
            raise PreviewStoreError(str(item["error"]), "PREVIEW_STORE_ERROR")
        if isinstance(item, dict):
            return item.get("result")
        return item

    if isinstance(body, dict):
        if body.get("error"):
            raise PreviewStoreError(str(body["error"]), "PREVIEW_STORE_ERROR")
        result = body.get("result") or []
        return result[0] if result else None

    return None


class MemoryPreviewSnapshotStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def save(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        token = snapshot.get("token", "")
        if not is_valid_token(token):
            raise PreviewStoreError("invalid token", "PREVIEW_STORE_INVALID_TOKEN")
        self._data[token] = json.loads(json.dumps(snapshot, ensure_ascii=False))
        log_preview_store_event("snapshot_write_success", token, backend="memory")
        return {"ok": True, "token": token}

    def get(self, token: str) -> dict[str, Any] | None:
        if not is_valid_token(token):
            log_preview_store_event("snapshot_read_not_found", token, reason="invalid_token")
            return None
        snap = self._data.get(token)
        if not snap:
            log_preview_store_event("snapshot_read_not_found", token, backend="memory")
            return None
        if is_expired_snapshot(snap):
            self.delete(token)
            log_preview_store_event("snapshot_read_expired", token, backend="memory")
            return None
        log_preview_store_event("snapshot_read_success", token, backend="memory")
        return json.loads(json.dumps(snap, ensure_ascii=False))

    def delete(self, token: str) -> bool:
        if not is_valid_token(token):
            return False
        return self._data.pop(token, None) is not None

    def healthcheck(self) -> dict[str, Any]:
        return {"ok": True, "backend": "memory"}


class FilesystemPreviewSnapshotStore:
    def __init__(self, directory: Path | None = None) -> None:
        if os.environ.get("VERCEL") == "1":
            raise PreviewStoreError("filesystem forbidden on Vercel", "PREVIEW_STORE_FORBIDDEN_BACKEND")
        if os.environ.get("PREVIEW_STORE_ALLOW_FILESYSTEM") != "1":
            raise PreviewStoreError(
                "filesystem requires PREVIEW_STORE_ALLOW_FILESYSTEM=1",
                "PREVIEW_STORE_FORBIDDEN_BACKEND",
            )
        self.directory = directory or FIXTURE_SNAPSHOT_DIR

    def _path(self, token: str) -> Path:
        return self.directory / f"{token}.json"

    def save(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        token = snapshot.get("token", "")
        if not is_valid_token(token):
            raise PreviewStoreError("invalid token", "PREVIEW_STORE_INVALID_TOKEN")
        self.directory.mkdir(parents=True, exist_ok=True)
        self._path(token).write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log_preview_store_event("snapshot_write_success", token, backend="filesystem")
        return {"ok": True, "token": token}

    def get(self, token: str) -> dict[str, Any] | None:
        if not is_valid_token(token):
            log_preview_store_event("snapshot_read_not_found", token, reason="invalid_token")
            return None
        path = self._path(token)
        if not path.exists():
            log_preview_store_event("snapshot_read_not_found", token, backend="filesystem")
            return None
        try:
            snap = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log_preview_store_event("snapshot_read_not_found", token, backend="filesystem", reason="parse_error")
            return None
        if is_expired_snapshot(snap):
            log_preview_store_event("snapshot_read_expired", token, backend="filesystem")
            return None
        log_preview_store_event("snapshot_read_success", token, backend="filesystem")
        return snap

    def delete(self, token: str) -> bool:
        if not is_valid_token(token):
            return False
        path = self._path(token)
        if path.exists():
            path.unlink()
            return True
        return False

    def healthcheck(self) -> dict[str, Any]:
        return {"ok": self.directory.exists(), "backend": "filesystem"}


class UpstashPreviewSnapshotStore:
    def save(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        token = snapshot.get("token", "")
        if not is_valid_token(token):
            raise PreviewStoreError("invalid token", "PREVIEW_STORE_INVALID_TOKEN")
        key = _storage_key(token)
        payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
        try:
            result = _upstash_pipeline(["SETEX", key, _ttl_seconds(), payload])
            if result != "OK":
                raise PreviewStoreError(f"SETEX unexpected: {result}", "PREVIEW_STORE_ERROR")
            log_preview_store_event("snapshot_write_success", token, backend="upstash")
            return {"ok": True, "token": token}
        except PreviewStoreError:
            log_preview_store_event("snapshot_write_failure", token, backend="upstash")
            raise

    def get(self, token: str) -> dict[str, Any] | None:
        if not is_valid_token(token):
            log_preview_store_event("snapshot_read_not_found", token, reason="invalid_token")
            return None
        key = _storage_key(token)
        try:
            raw = _upstash_pipeline(["GET", key])
        except PreviewStoreError as e:
            log_preview_store_event(
                "snapshot_store_error", token, backend="upstash", phase="read", error=e.code
            )
            raise
        if raw is None:
            log_preview_store_event("snapshot_read_not_found", token, backend="upstash")
            return None
        try:
            snap = json.loads(raw)
        except json.JSONDecodeError:
            log_preview_store_event("snapshot_read_not_found", token, backend="upstash", reason="parse_error")
            return None
        if is_expired_snapshot(snap):
            self.delete(token)
            log_preview_store_event("snapshot_read_expired", token, backend="upstash")
            return None
        log_preview_store_event("snapshot_read_success", token, backend="upstash")
        return snap

    def delete(self, token: str) -> bool:
        if not is_valid_token(token):
            return False
        _upstash_pipeline(["DEL", _storage_key(token)])
        return True

    def healthcheck(self) -> dict[str, Any]:
        pong = _upstash_pipeline(["PING"])
        return {"ok": pong == "PONG", "backend": "upstash"}


_STORE_SINGLETON: Any | None = None


def create_preview_snapshot_store(backend: str | None = None) -> Any:
    resolved = backend or resolve_preview_store_backend()
    if resolved == "upstash":
        return UpstashPreviewSnapshotStore()
    if resolved == "filesystem":
        return FilesystemPreviewSnapshotStore()
    if resolved == "memory":
        return MemoryPreviewSnapshotStore()
    raise PreviewStoreError(f"unknown backend: {resolved}", "PREVIEW_STORE_UNKNOWN_BACKEND")


def get_preview_snapshot_store() -> Any:
    global _STORE_SINGLETON
    if _STORE_SINGLETON is None:
        _STORE_SINGLETON = create_preview_snapshot_store()
    return _STORE_SINGLETON


def reset_preview_snapshot_store() -> None:
    global _STORE_SINGLETON
    _STORE_SINGLETON = None


def save_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return get_preview_snapshot_store().save(snapshot)


def load_snapshot(token: str) -> dict[str, Any] | None:
    return get_preview_snapshot_store().get(token)
