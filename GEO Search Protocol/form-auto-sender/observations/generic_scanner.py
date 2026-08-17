"""
observations/generic_scanner.py — Minimal public HTTP fetch for generic preview signals.

Pilot scope: homepage (required), /llms.txt (optional). No deep crawl / browser automation.
"""

from __future__ import annotations

import re
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

USER_AGENT = "ARI-Generic-Preview-Scanner/1.0 (+https://www.coaretail.com; read-only)"
REQUEST_TIMEOUT_SEC = 15
INTER_REQUEST_DELAY_SEC = 0.55
MAX_REQUESTS_PER_DOMAIN = 2  # homepage + llms.txt
MAX_HTML_BYTES = 500_000

ACTION_KW = re.compile(
    r"予約|ご予約|web予約|ネット予約|体験|無料相談|相談|お問い合わせ|問い合わせ|"
    r"見積|内見|資料請求|申込|申し込み|来店|"
    r"contact|inquiry|consult|estimate|booking|reserve|appointment|viewing",
    re.IGNORECASE,
)
FAQ_KW = re.compile(r"よくある質問|FAQ|Q\s*&\s*A|Q&A", re.IGNORECASE)
FAQ_PATH = re.compile(r"/(faq|qa|question|よくある)(/|$|\?)", re.IGNORECASE)
SCHEMA_RE = re.compile(r"application/ld\+json|schema\.org", re.IGNORECASE)


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.meta_desc = ""
        self.links: list[str] = []
        self._in_title = False
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k: (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        if tag == "meta" and ad.get("name", "").lower() == "description":
            self.meta_desc = ad.get("content", "")
        if tag == "a" and ad.get("href"):
            self.links.append(ad["href"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        t = data.strip()
        if t:
            self._text_parts.append(t)

    @property
    def body_text(self) -> str:
        return " ".join(self._text_parts)


@dataclass
class FetchResult:
    ok: bool
    status: int | None
    final_url: str
    html: str = ""
    error: str = ""


def _fetch(url: str, *, timeout: int = REQUEST_TIMEOUT_SEC) -> FetchResult:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read(MAX_HTML_BYTES)
            charset = resp.headers.get_content_charset() or "utf-8"
            html = raw.decode(charset, errors="replace")
            return FetchResult(True, resp.status, resp.geturl(), html)
    except urllib.error.HTTPError as e:
        return FetchResult(False, e.code, url, "", str(e))
    except Exception as e:
        return FetchResult(False, None, url, "", str(e))


def _normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if not u.startswith("http"):
        u = f"https://{u}"
    return u


def _base_origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def scan_domain(
    *,
    website_url: str,
    domain: str = "",
    industry_name: str = "",
    delay_sec: float = INTER_REQUEST_DELAY_SEC,
) -> dict[str, Any]:
    """
    Fetch homepage (+ llms.txt) and derive generic preview signals.
    Returns evidence row suitable for generic resolver (no raw HTML stored).
    """
    url = _normalize_url(website_url)
    dom = (domain or urlparse(url).netloc or "").lower().removeprefix("www.")
    scanned_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    base_row: dict[str, Any] = {
        "evidence_source": "generic_scan",
        "domain": dom,
        "website_url": url,
        "url": url,
        "industry_name": industry_name,
        "scanned_at": scanned_at,
        "site_reachable": False,
        "http_status": None,
        "action_path_scanned": False,
        "action_path_present": False,
        "faq_scanned": False,
        "faq_present": False,
        "schema_scanned": False,
        "schema_present": False,
        "service_info_scanned": False,
        "service_info_ok": False,
        "service_info_weak": False,
        "llms_txt_scanned": False,
        "has_llms_txt": False,
        "scan_error": "",
        "requests_used": 0,
    }

    if not url:
        base_row["scan_error"] = "missing_url"
        return base_row

    home = _fetch(url)
    base_row["requests_used"] = 1
    if not home.ok or home.status != 200:
        base_row["scan_error"] = home.error or f"http_{home.status}"
        base_row["http_status"] = home.status
        return base_row

    base_row["site_reachable"] = True
    base_row["http_status"] = home.status
    base_row["url"] = home.final_url

    parser = _PageParser()
    try:
        parser.feed(home.html)
    except Exception:
        pass

    combined_text = parser.body_text + " " + home.html[:80_000]
    action_hit = bool(ACTION_KW.search(combined_text))
    for href in parser.links[:100]:
        if ACTION_KW.search(href) or FAQ_PATH.search(href):
            action_hit = True
            break

    faq_hit = bool(FAQ_KW.search(combined_text)) or any(
        FAQ_PATH.search(h) for h in parser.links[:100]
    )
    schema_hit = bool(SCHEMA_RE.search(home.html))
    title_ok = len(parser.title.strip()) >= 4
    meta_ok = len(parser.meta_desc.strip()) >= 20
    body_ok = len(parser.body_text) >= 800
    service_ok = title_ok and (meta_ok or body_ok)
    service_weak = title_ok and not service_ok

    base_row.update({
        "action_path_scanned": True,
        "action_path_present": action_hit,
        "faq_scanned": True,
        "faq_present": faq_hit,
        "schema_scanned": True,
        "schema_present": schema_hit,
        "service_info_scanned": True,
        "service_info_ok": service_ok,
        "service_info_weak": service_weak and not service_ok,
    })

    if delay_sec > 0:
        time.sleep(delay_sec)

    llms_url = _base_origin(home.final_url) + "/llms.txt"
    llms = _fetch(llms_url, timeout=10)
    base_row["requests_used"] = 2
    base_row["llms_txt_scanned"] = True
    base_row["has_llms_txt"] = llms.ok and llms.status == 200

    return base_row


def is_scan_success(row: dict[str, Any]) -> bool:
    return bool(row.get("site_reachable")) and bool(row.get("action_path_scanned"))


def has_safe_observation(row: dict[str, Any]) -> bool:
    from observations.resolver import select_message_observations

    if not is_scan_success(row):
        return False
    return len(select_message_observations(row)) >= 1
