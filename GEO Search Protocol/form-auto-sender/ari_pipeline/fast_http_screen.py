"""
fast_http_screen.py — Stage 0 cheap HTTP pre-screen (ZERO SEND).

FAST_HTTP budget: 5–10s. No Playwright.
"""

from __future__ import annotations

import asyncio
import re
import ssl
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ari_pipeline.r2_lane_c_filter import lane_c_url_pattern_score

FAST_HTTP_TIMEOUT_SEC = 8
CAPTCHA_MARKERS = (
    "recaptcha", "g-recaptcha", "hcaptcha", "cf-challenge", "cloudflare",
    "captcha", "turnstile",
)
RESERVATION_MARKERS = (
    "/reserve", "/reservation", "/booking", "/yoyaku", "初診", "再診",
    "予約専用", "appointment", "カウンセリング予約",
)
FORM_MARKERS = (
    "<form", "<textarea", 'type="email"', "type='email'",
    'name="email"', "お問い合わせ", "問い合わせ", "contact",
)
FRAMEWORK_MARKERS = (
    "wpcf7", "mwform", "contact-form-7", "formrun", "hubspot",
)


@dataclass
class FastScreenResult:
    domain: str
    url: str
    lane: str  # NIGHT_FAST_LANE | NIGHT_SLOW_LANE
    outcome: str  # FAST_OK | UNREACHABLE | CAPTCHA | NO_HTML | RESERVATION | SLOW_PATH
    promote_browser: bool
    elapsed_sec: float
    http_status: int | None = None
    signals: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


def classify_lane(candidate: dict) -> str:
    url = candidate.get("lw_entry_url") or candidate.get("website_url") or ""
    score = lane_c_url_pattern_score(url)
    known = score >= 70 or url != (candidate.get("website_url") or "").strip().rstrip("/")
    return "NIGHT_FAST_LANE" if known else "NIGHT_SLOW_LANE"


def _sync_fetch(url: str, timeout: int) -> tuple[int | None, str, str, str]:
    """Returns (status, body_snippet, content_type, error)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ja,en;q=0.9",
        },
    )
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            ctype = resp.headers.get("Content-Type", "")
            raw = resp.read(256_000)
            try:
                body = raw.decode("utf-8", errors="replace")
            except Exception:
                body = raw.decode("latin-1", errors="replace")
            return resp.status, body[:120_000], ctype, ""
    except HTTPError as e:
        try:
            body = e.read(32_000).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return e.code, body, e.headers.get("Content-Type", ""), str(e)
    except URLError as e:
        return None, "", "", str(e.reason if hasattr(e, "reason") else e)
    except Exception as e:
        return None, "", "", str(e)[:200]


async def fast_http_screen(candidate: dict, *, timeout: int | None = None) -> FastScreenResult:
    import time

    t0 = time.monotonic()
    url = (candidate.get("lw_entry_url") or candidate.get("website_url") or "").strip()
    dom = (candidate.get("domain") or "").lower()
    lane = classify_lane(candidate)
    timeout = timeout or FAST_HTTP_TIMEOUT_SEC

    if not url:
        return FastScreenResult(
            domain=dom, url="", lane=lane, outcome="UNREACHABLE",
            promote_browser=False, elapsed_sec=time.monotonic() - t0, reason="no_url",
        )

    if not url.startswith("http"):
        url = "https://" + url.lstrip("/")

    loop = asyncio.get_event_loop()
    status, body, ctype, err = await loop.run_in_executor(None, _sync_fetch, url, timeout)
    elapsed = time.monotonic() - t0

    low_url = url.lower()
    if any(m in low_url for m in RESERVATION_MARKERS):
        return FastScreenResult(
            domain=dom, url=url, lane=lane, outcome="RESERVATION",
            promote_browser=False, elapsed_sec=elapsed, http_status=status,
            reason="reservation_url",
        )

    if err and status is None:
        return FastScreenResult(
            domain=dom, url=url, lane=lane, outcome="UNREACHABLE",
            promote_browser=False, elapsed_sec=elapsed, reason=err[:120],
        )

    if status and status >= 400:
        return FastScreenResult(
            domain=dom, url=url, lane=lane, outcome="UNREACHABLE",
            promote_browser=False, elapsed_sec=elapsed, http_status=status,
            reason=f"http_{status}",
        )

    if ctype and "html" not in ctype.lower() and "text/" not in ctype.lower():
        return FastScreenResult(
            domain=dom, url=url, lane=lane, outcome="NO_HTML",
            promote_browser=False, elapsed_sec=elapsed, http_status=status,
            reason=f"content_type:{ctype[:40]}",
        )

    if not body.strip():
        return FastScreenResult(
            domain=dom, url=url, lane=lane, outcome="UNREACHABLE",
            promote_browser=False, elapsed_sec=elapsed, http_status=status,
            reason="empty_body",
        )

    low = body.lower()
    if any(m in low for m in CAPTCHA_MARKERS):
        return FastScreenResult(
            domain=dom, url=url, lane=lane, outcome="CAPTCHA",
            promote_browser=False, elapsed_sec=elapsed, http_status=status,
            reason="captcha_html",
        )

    if any(m in low for m in RESERVATION_MARKERS):
        return FastScreenResult(
            domain=dom, url=url, lane=lane, outcome="RESERVATION",
            promote_browser=False, elapsed_sec=elapsed, http_status=status,
            reason="reservation_content",
        )

    has_form = any(m in low for m in FORM_MARKERS)
    has_framework = any(m in low for m in FRAMEWORK_MARKERS)
    signals = {
        "has_form": has_form,
        "has_framework": has_framework,
        "has_textarea": "<textarea" in low,
        "has_email_input": 'type="email"' in low or "type='email'" in low,
    }

    if lane == "NIGHT_SLOW_LANE" and not (has_form or has_framework):
        return FastScreenResult(
            domain=dom, url=url, lane=lane, outcome="SLOW_PATH",
            promote_browser=False, elapsed_sec=elapsed, http_status=status,
            signals=signals, reason="needs_homepage_discovery",
        )

    if has_form or has_framework or lane == "NIGHT_FAST_LANE":
        return FastScreenResult(
            domain=dom, url=url, lane=lane, outcome="FAST_OK",
            promote_browser=True, elapsed_sec=elapsed, http_status=status,
            signals=signals, reason="promote_browser",
        )

    return FastScreenResult(
        domain=dom, url=url, lane=lane, outcome="SLOW_PATH",
        promote_browser=False, elapsed_sec=elapsed, http_status=status,
        signals=signals, reason="weak_form_signal",
    )


def fast_outcome_to_lw(outcome: str) -> str:
    mapping = {
        "UNREACHABLE": "UNREACHABLE_ERROR",
        "CAPTCHA": "CAPTCHA_MANUAL",
        "RESERVATION": "FORM_NOT_SUITABLE",
        "NO_HTML": "UNREACHABLE_ERROR",
        "SLOW_PATH": "SLOW_PATH_REVIEW",
    }
    return mapping.get(outcome, "")
