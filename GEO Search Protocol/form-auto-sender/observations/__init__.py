"""Deterministic observation codes for Personalized Preview Funnel."""

from observations.resolver import (
    build_check_summary,
    build_preview_payload,
    load_catalog,
    resolve_observations,
    select_message_observations,
)

__all__ = [
    "build_check_summary",
    "build_preview_payload",
    "build_preview_url",
    "create_preview_snapshot",
    "load_catalog",
    "load_snapshot",
    "public_snapshot_view",
    "resolve_observations",
    "save_snapshot",
    "select_message_observations",
]


def __getattr__(name: str):
    if name in {
        "build_preview_url",
        "create_preview_snapshot",
        "public_snapshot_view",
    }:
        from observations import snapshot_builder as sb
        return getattr(sb, name)
    if name in {"load_snapshot", "save_snapshot"}:
        from observations import preview_snapshot_store as store
        return getattr(store, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
