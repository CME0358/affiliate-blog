"""
observations/snapshot_builder.py — Create opaque-token preview snapshots.

Persistence via preview_snapshot_store (Upstash Redis / memory / local filesystem).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from observations.crawler_join import lookup_crawler_data_for_company, lookup_preview_evidence
from observations.preview_snapshot_store import PreviewStoreError, save_snapshot
from observations.resolver import (
    build_preview_payload,
    map_industry_to_form,
    select_message_observations,
)
from observations.video_segment import classify_video_segment, normalize_video_segment

PREVIEW_BASE_URL = "https://readiness.coaretail.com/report/p"
SNAPSHOT_TTL_DAYS = 90
SNAPSHOT_VERSION = 1


def generate_token() -> str:
    return secrets.token_urlsafe(16)


def _candidate_id(company: dict[str, Any]) -> str:
    url = company.get("website_url") or company.get("url") or ""
    name = company.get("company_name") or ""
    dom = urlparse(url).netloc or url
    raw = f"{dom}|{name}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_preview_url(token: str, *, campaign_id: str = "ari_preview_v1") -> str:
    return f"{PREVIEW_BASE_URL}/{token}?utm_source=outbound&utm_medium=form&utm_campaign={campaign_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_preview_snapshot(
    company: dict[str, Any],
    *,
    crawler_data: dict[str, Any] | None = None,
    campaign_id: str = "ari_preview_v1",
    template_version: str = "ARI_MESSAGE_V2_PREVIEW",
    ab_arm: str = "C",
    has_llms_txt: bool | None = None,
    has_robots_txt: bool | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Build and optionally persist a preview snapshot.

    Returns snapshot dict including `token` and `preview_url`.
    Raises ValueError if crawler data missing or site blocked.
    Raises PreviewStoreError if persistence fails (no send-eligible URL without confirmed write).
    """
    website_url = company.get("website_url") or company.get("url") or ""
    company_name = company.get("company_name") or company.get("clinic_name") or ""
    industry_name = company.get("industry_name") or company.get("industry") or ""

    row = crawler_data
    if row is None:
        row, _src = lookup_preview_evidence(company)
    if not row:
        row = lookup_crawler_data_for_company(company)
    if not row:
        raise ValueError(f"preview_evidence_not_found:{website_url}")

    if has_llms_txt is not None:
        row = {**row, "has_llms_txt": has_llms_txt}
    if has_robots_txt is not None:
        row = {**row, "has_robots_txt": has_robots_txt}

    cid = company.get("candidate_id") or _candidate_id({
        "website_url": website_url,
        "company_name": company_name,
    })

    video_segment = classify_video_segment(industry_name)

    public_payload = build_preview_payload(
        company_name=company_name,
        url=website_url,
        industry_name=industry_name,
        crawler_data=row,
        candidate_id=cid,
    )

    if public_payload.get("blocked"):
        raise ValueError("preview_blocked:site_unreachable")

    token = generate_token()
    created = _now_iso()
    expires = (
        datetime.now(timezone.utc) + timedelta(days=SNAPSHOT_TTL_DAYS)
    ).replace(microsecond=0).isoformat()

    snapshot = {
        "version": SNAPSHOT_VERSION,
        "token": token,
        "candidate_id": cid,
        "company_name": company_name,
        "url": website_url,
        "industry": map_industry_to_form(industry_name),
        "industry_source": industry_name,
        "video_segment": video_segment,
        "area_name": company.get("area_name", ""),
        "campaign_id": campaign_id,
        "template_version": template_version,
        "ab_arm": ab_arm,
        "created_at": created,
        "expires_at": expires,
        "crawled_at": public_payload.get("crawled_at"),
        "preview": public_payload,
        "message_observations": select_message_observations(row),
        "preview_url": build_preview_url(token, campaign_id=campaign_id),
        "_evidence": {
            "crawler_row": {k: v for k, v in row.items() if not str(k).startswith("_")},
        },
    }

    if not dry_run:
        try:
            save_snapshot(snapshot)
        except PreviewStoreError as e:
            raise PreviewStoreError(
                f"snapshot persistence failed — preview URL must not be used: {e}",
                e.code,
            ) from e

    return snapshot


def public_snapshot_view(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Strip internal fields for API / PreviewPage."""
    preview = snapshot.get("preview") or {}
    return {
        "token": snapshot.get("token"),
        "company_name": snapshot.get("company_name"),
        "url": snapshot.get("url"),
        "industry": snapshot.get("industry"),
        "candidate_id": snapshot.get("candidate_id"),
        "campaign_id": snapshot.get("campaign_id"),
        "template_version": snapshot.get("template_version"),
        "crawled_at": snapshot.get("crawled_at"),
        "created_at": snapshot.get("created_at"),
        "video_segment": normalize_video_segment(snapshot.get("video_segment")),
        "observations": preview.get("observations", []),
        "check_summary": preview.get("check_summary", {}),
    }
