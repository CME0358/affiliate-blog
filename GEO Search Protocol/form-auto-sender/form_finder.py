"""
form_finder.py  —  問い合わせフォーム URL 特定モジュール

処理フロー:
    1. website_url にアクセス（Playwright・domcontentloaded + 2秒待機）
    2. ページ内リンク + <iframe src> をスキャン（予約系・外部予約・PDFは除外）
    3. 同一オリジンルート + /contact, /inquiry, /form 等を試行（問い合わせ<form>のみ採用・予約除外）
    4. トップ（店舗URL含む）に問い合わせらしい<form>があるか（予約ページは除外）
    5. 候補が検索枠のみ等なら棄却し、3 を再試行（チェーン本部フォーム向け）
    6. （任意）Google 検索で「{会社名} お問い合わせ」から候補URLを取得
    7. 予約フォームのみ: no_contact_form_only_reservation / 外部予約のみ: no_form_external_booking
    8. 深いパスの店舗でフォームなし: no_form_chain_site

CLI:
    python form_finder.py --check-url https://example.com/reservation
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urljoin, urlparse

from config import (
    CHAIN_SITE_MAX_NAVIGATIONS,
    CHAIN_SITE_MAX_PARENT_LEVELS,
    ENABLE_GOOGLE_FORM_SEARCH,
    FORM_FIND_MAX_CONTACT_PATHS,
    FORM_FIND_MAX_GOOGLE_FOLLOWS,
    FORM_FIND_MAX_IFRAME_FOLLOWS,
    FORM_FIND_MAX_LINK_FOLLOWS,
    FORM_FIND_MAX_NAVIGATIONS,
    FORM_FIND_TOTAL_TIMEOUT_SEC,
)

# ─── 定数 ─────────────────────────────────────────────────────────────────────

FORM_KEYWORDS = [
    "お問い合わせ", "問い合わせ", "ご相談", "無料相談",
    "contact", "inquiry", "form", "お申し込み", "相談する",
    "問合せ", "お問合せ", "メッセージ", "資料請求",
    # 追加（リンク文言・パス対応）
    "メール", "電話予約", "ご予約", "アクセス", "来院予約",
    "カウンセリング", "初診", "予約フォーム", "相談フォーム",
    "recruit", "採用", "request", "consultation",
]


def _candidate_paths_ordered() -> list[str]:
    """
    キーワードで見つからない場合に試行するパス（指定順）。
    各パスについて `/path` と `/path/` の両方を試す。
    """
    bases = [
        "/contact",
        "/inquiry",
        "/form",
        "/consultation",
    ]
    out: list[str] = []
    seen: set[str] = set()
    for raw in bases:
        b = raw.strip().rstrip("/")
        if not b.startswith("/"):
            b = "/" + b.lstrip("/")
        for variant in (b, b + "/"):
            if variant not in seen:
                seen.add(variant)
                out.append(variant)
    extras = [
        "/contact-us/",
        "/contact-us",
        "/お問い合わせ/",
        "/toiawase/",
        "/toiawase",
        "/mail/",
        "/support/",
        "/info/contact/",
        "/company/contact/",
        "/form/contact/",
    ]
    for e in extras:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


CANDIDATE_PATHS = _candidate_paths_ordered()

# チェーン本部向け（短時間で打ち切る）
CHAIN_FAST_CONTACT_PATHS: tuple[str, ...] = (
    "/contact/",
    "/contact",
    "/inquiry/",
    "/toiawase/",
    "/support/",
    "/form/contact/",
)

# reCAPTCHA を示す文字列（pending 判定用）
RECAPTCHA_INDICATORS = [
    "recaptcha",
    "grecaptcha",
    "g-recaptcha",
    "hcaptcha",
]

# タイムアウト（ミリ秒）・読み込み後待機（秒）
NAV_TIMEOUT = 15_000
# page.goto() には明示的に短い上限を渡す（asyncio 全体タイムアウトと二重化）
GOTO_TIMEOUT = 10_000
POST_LOAD_WAIT_SEC = 2.0

# ダウンロード誤遷移（PDF/Office）
FILE_DOWNLOAD_SUFFIXES: tuple[str, ...] = (
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
)

# 外部予約・LINE誘導のみのサイト（問い合わせフォームなしとして記録）
# チェーン本部サイト（店舗ページから問い合わせフォームはほぼ無し → 探索を短絡）
CHAIN_SITE_HOST_FRAGMENTS: tuple[str, ...] = (
    "s-b-c.net",
    "sbc-dental.com",
    "takasu.co.jp",
    "shinagawa-skin.com",
    "shonan-clinic.com",
    "tcb-sekisei.com",
    "aoki-tsuyoshi.com",
)

EXTERNAL_BOOKING_ONLY_SUBSTRINGS: tuple[str, ...] = (
    "lin.ee",
    "page.line.me",
    "hotpepper.jp",
    "beauty.hotpepper",
    "minagine",
    "coubic",
    "reserva.be",
    "airrsv",
    "stores.jp/reserve",
)

# 予約フォーム・外部予約導線は問い合わせフォームとして採用しない
RESERVATION_EXCLUDE_URL_SUBSTRINGS: tuple[str, ...] = (
    "reservation",
    "reserve",
    "yoyaku",
    "booking",
    "schedule",
    "calendar",
    "hotpepper",
    "minagine",
    "beauty.hotpepper",
    "salon-board",
    "reserva.be",
    "coubic",
    "stores.jp/reserve",
    "airrsv",
)

RESERVATION_EXCLUDE_TITLE_SUBSTRINGS: tuple[str, ...] = (
    "ご予約",
    "予約フォーム",
    "ネット予約",
    "オンライン予約",
    "来院予約",
    "Web予約",
    "WEB予約",
)

# 外部ホストの問い合わせフォーム（同一オリジン以外も採用）
EXTERNAL_FORM_HOST_FRAGMENTS: tuple[str, ...] = (
    "form.run",
    "forms.gle",
    "docs.google.com/forms",
    "business.form-mailer.jp",
    "form-mailer.jp",
    "ssl.form-mailer.jp",
    "hubspot.com",
    "typeform.com",
    "form.kintoneapp.com",
    "formzu.net",
)


# ─── ヘルパー ─────────────────────────────────────────────────────────────────

def _normalize_url(base: str, href: str) -> str:
    """相対 href を絶対 URL に変換する。"""
    return urljoin(base, href)


def _is_same_origin(url1: str, url2: str) -> bool:
    """2つの URL が同一オリジンかどうかを判定する。"""
    p1, p2 = urlparse(url1), urlparse(url2)
    return p1.scheme == p2.scheme and p1.netloc == p2.netloc


def _url_contains_booking_or_book_token(url: str) -> bool:
    """URL に booking または単独の book（facebook 等の誤検知を避ける）。"""
    u = (url or "").lower()
    if "booking" in u:
        return True
    return bool(re.search(r"(?<![a-z0-9])book(?:$|(?![a-z0-9])|[/._?&#=-])", u))


def is_reservation_excluded_url(url: str) -> bool:
    """予約系として除外すべき URL か（小文字化して部分一致）。"""
    u = (url or "").lower()
    for sub in RESERVATION_EXCLUDE_URL_SUBSTRINGS:
        if sub in u:
            return True
    return _url_contains_booking_or_book_token(url)


def is_external_booking_only_url(url: str) -> bool:
    """LINE・ホットペッパー等、問い合わせフォームを持たない外部予約導線か。"""
    u = (url or "").lower()
    return any(sub in u for sub in EXTERNAL_BOOKING_ONLY_SUBSTRINGS)


def is_file_download_url(url: str) -> bool:
    """PDF/Office 等のファイル直リンクか。"""
    path = urlparse(url or "").path.lower().split("?")[0]
    return any(path.endswith(suf) for suf in FILE_DOWNLOAD_SUFFIXES)


@dataclass
class NavigationBudget:
    """1回の find_form_url 内でのページ遷移上限。"""

    max_navigations: int = FORM_FIND_MAX_NAVIGATIONS
    deadline: float = field(default_factory=lambda: time.monotonic() + FORM_FIND_TOTAL_TIMEOUT_SEC)
    count: int = 0
    exhausted: bool = False

    def can_navigate(self) -> bool:
        if self.exhausted:
            return False
        if self.count >= self.max_navigations:
            self.exhausted = True
            return False
        if time.monotonic() >= self.deadline:
            self.exhausted = True
            return False
        return True

    def record(self) -> None:
        self.count += 1


def is_chain_corporate_host(url: str) -> bool:
    host = urlparse(url or "").netloc.lower()
    return any(frag in host for frag in CHAIN_SITE_HOST_FRAGMENTS)


def is_chain_branch_listing_url(url: str) -> bool:
    """チェーンの店舗一覧・支店ページへのリンク（問い合わせフォーム探索では辿らない）。"""
    path = urlparse(url or "").path.lower()
    if "/clinic/branch/" in path:
        return True
    if re.search(r"/clinic/[^/]+/branch/", path):
        return True
    if path.rstrip("/").endswith("/clinic") and path.count("/") <= 2:
        return True
    return False


def _contact_path_priority(path: str) -> int:
    p = path.lower()
    for i, key in enumerate(("contact", "inquiry", "toiawase", "form", "support", "mail")):
        if key in p:
            return i
    return 99


def _anchor_follow_priority(abs_url: str, text: str) -> int:
    blob = (abs_url + " " + text).lower()
    for i, key in enumerate(
        ("contact", "inquiry", "toiawase", "問い合わせ", "問合せ", "support", "mail", "form")
    ):
        if key in blob:
            return i
    if _is_external_form_host(abs_url):
        return 20
    return 50


async def _goto_settled(
    page,
    url: str,
    budget: NavigationBudget | None = None,
    *,
    goto_timeout: int = GOTO_TIMEOUT,
) -> bool:
    """domcontentloaded 後に POST_LOAD_WAIT_SEC 秒待ってから続行。"""
    from playwright.async_api import TimeoutError as PWTimeout

    if budget is not None and not budget.can_navigate():
        return False
    try:
        await page.goto(url, timeout=goto_timeout, wait_until="domcontentloaded")
        if budget is not None:
            budget.record()
        await asyncio.sleep(POST_LOAD_WAIT_SEC)
        return True
    except PWTimeout:
        return False


def _strip_tags_fragment(fragment: str) -> str:
    t = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", t).strip()


def _extract_title_and_h1_inner_text(html: str) -> str:
    parts: list[str] = []
    for pattern in (
        r"<title[^>]*>([\s\S]*?)</title>",
        r"<h1[^>]*>([\s\S]*?)</h1>",
    ):
        m = re.search(pattern, html, flags=re.IGNORECASE)
        if m:
            parts.append(_strip_tags_fragment(m.group(1)))
    return " ".join(parts)


def _is_external_form_host(url: str) -> bool:
    u = (url or "").lower()
    host = urlparse(u).netloc.lower()
    return any(frag in u or frag in host for frag in EXTERNAL_FORM_HOST_FRAGMENTS)


def is_reservation_excluded_title_blob(title_h1_blob: str) -> bool:
    """ページタイトル・h1 テキストに予約系キーワードが含まれるか。"""
    s = title_h1_blob or ""
    return any(k in s for k in RESERVATION_EXCLUDE_TITLE_SUBSTRINGS)


def is_reservation_excluded_page(url: str, html: str) -> bool:
    """URL またはタイトル・h1 に基づき予約ページとして除外するか。"""
    if is_reservation_excluded_url(url):
        return True
    return is_reservation_excluded_title_blob(_extract_title_and_h1_inner_text(html))


def _looks_like_form_link(href: str, text: str) -> bool:
    """href または表示テキストがフォームへのリンクっぽいか判定する。"""
    combined = (href + " " + text).lower()
    return any(kw.lower() in combined for kw in FORM_KEYWORDS)


def _has_recaptcha(html: str) -> bool:
    """HTML 内に reCAPTCHA らしき記述があるか確認する。"""
    html_lower = html.lower()
    return any(ind in html_lower for ind in RECAPTCHA_INDICATORS)


def _has_form_element(html: str) -> bool:
    """HTML 内に <form> タグがあるか確認する。"""
    return bool(re.search(r"<form[\s>]", html, re.IGNORECASE))


def _has_inquiry_like_form(html: str) -> bool:
    """
    お問い合わせ用のフォームか（検索ボックスのみの<form>を除外）。
    チェーン店舗ページで<form>だけあるケースを弾く。
    """
    if not _has_form_element(html):
        return False
    hl = html.lower()
    if "<textarea" in hl:
        return True
    if re.search(r'type\s*=\s*["\']email["\']', hl, re.IGNORECASE):
        return True
    if re.search(r'name\s*=\s*["\'][^"\']*mail[^"\']*["\']', hl, re.IGNORECASE):
        return True
    if re.search(r'id\s*=\s*["\'][^"\']*mail[^"\']*["\']', hl, re.IGNORECASE):
        return True
    if "お問い合わせ" in html or "問い合わせ" in html or "contact" in hl:
        if re.search(r"<input[^>]+type\s*=\s*[\"']text[\"']", hl, re.IGNORECASE):
            return True
    return False


def _is_branch_store_url(url: str) -> bool:
    """店舗・支店ページ想定: ドメイン直下以外のパスか。"""
    path = urlparse(url).path.strip("/")
    return bool(path)


async def _page_has_inquiry_link_hint(page, base_url: str) -> bool:
    """ページ上に問い合わせ系リンク（外部予約以外）があるか。"""
    try:
        anchors = await page.eval_on_selector_all(
            "a[href]",
            """els => els.map(el => ({
                href: el.getAttribute('href') || '',
                text: (el.innerText || el.textContent || '').trim()
            }))""",
        )
    except Exception:
        return False
    for a in anchors:
        href = (a.get("href") or "").strip()
        text = (a.get("text") or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        abs_url = _normalize_url(base_url, href)
        if is_file_download_url(abs_url) or is_external_booking_only_url(abs_url):
            continue
        if _looks_like_form_link(href, text) or _is_external_form_host(abs_url):
            return True
    return False


async def _page_is_external_booking_only_signal(page, base_url: str) -> bool:
    """
    外部予約/LINE 導線はあるが問い合わせリンクが見つからない場合 True。
    """
    try:
        payload = await page.evaluate(
            """() => {
              const anchors = [...document.querySelectorAll('a[href]')].map(a => ({
                href: a.getAttribute('href') || '',
                text: (a.innerText || a.textContent || '').trim()
              }));
              const iframes = [...document.querySelectorAll('iframe[src]')].map(
                f => f.getAttribute('src') || ''
              );
              return { anchors, iframes };
            }"""
        )
    except Exception:
        return False

    has_external = False
    for a in payload.get("anchors") or []:
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        abs_url = _normalize_url(base_url, href)
        if is_external_booking_only_url(abs_url):
            has_external = True
    for src in payload.get("iframes") or []:
        src = (src or "").strip()
        if not src:
            continue
        if is_external_booking_only_url(_normalize_url(base_url, src)):
            has_external = True

    if not has_external:
        return False
    return not await _page_has_inquiry_link_hint(page, base_url)


async def _scan_iframe_sources_for_inquiry_form(
    page,
    base_url: str,
    rejected_counter: list[int] | None = None,
    external_booking_counter: list[int] | None = None,
    budget: NavigationBudget | None = None,
    max_follows: int = FORM_FIND_MAX_IFRAME_FOLLOWS,
) -> str | None:
    """<iframe src> から問い合わせフォーム URL を探す。"""
    rc = rejected_counter if rejected_counter is not None else [0]
    eb = external_booking_counter if external_booking_counter is not None else [0]

    try:
        iframe_srcs = await page.eval_on_selector_all(
            "iframe[src]",
            "els => els.map(el => el.getAttribute('src') || '').filter(Boolean)",
        )
    except Exception:
        return None

    seen: set[str] = set()
    followed = 0
    for src in iframe_srcs:
        if followed >= max_follows:
            break
        if budget is not None and budget.exhausted:
            break
        src = (src or "").strip()
        if not src:
            continue
        abs_url = _normalize_url(base_url, src)
        if abs_url in seen:
            continue
        seen.add(abs_url)
        if is_file_download_url(abs_url):
            continue
        if is_external_booking_only_url(abs_url):
            eb[0] += 1
            continue
        if is_reservation_excluded_url(abs_url):
            continue
        if not await _goto_settled(page, abs_url, budget=budget):
            continue
        followed += 1
        html = await page.content()
        if _is_external_form_host(abs_url) and not is_reservation_excluded_page(abs_url, html):
            return abs_url
        if _has_inquiry_like_form(html) and not is_reservation_excluded_page(abs_url, html):
            return abs_url
        if is_reservation_excluded_page(abs_url, html):
            rc[0] += 1
    return None


async def _scan_anchor_links_for_inquiry_form(
    page,
    base_url: str,
    rejected_counter: list[int] | None = None,
    external_booking_counter: list[int] | None = None,
    budget: NavigationBudget | None = None,
    max_follows: int = FORM_FIND_MAX_LINK_FOLLOWS,
    chain_mode: bool = False,
) -> str | None:
    """ページ内リンクから問い合わせフォームURLを探す（Step 2 相当）。"""
    rc = rejected_counter if rejected_counter is not None else [0]
    eb = external_booking_counter if external_booking_counter is not None else [0]
    try:
        anchors = await page.eval_on_selector_all(
            "a[href]",
            """els => els.map(el => ({
                href: el.getAttribute('href') || '',
                text: el.innerText || el.textContent || ''
            }))""",
        )
    except Exception:
        return None

    anchor_candidates: list[str] = []
    for a in anchors:
        href = a["href"].strip()
        text = a["text"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        abs_url = _normalize_url(base_url, href)

        # Do not treat a link back to the current document as a recovered
        # inquiry-form destination. The current page is evaluated separately
        # by the normal base-page/form checks. Keeping self-links here can
        # prematurely stop discovery before a real nested form URL
        # (e.g. /reserve/) is inspected.
        try:
            _base_cmp = urlparse(base_url)
            _abs_cmp = urlparse(abs_url)
            _same_document = (
                _base_cmp.scheme.lower() == _abs_cmp.scheme.lower()
                and _base_cmp.netloc.lower() == _abs_cmp.netloc.lower()
                and _base_cmp.path.rstrip("/") == _abs_cmp.path.rstrip("/")
                and _base_cmp.query == _abs_cmp.query
            )
        except Exception:
            _same_document = abs_url.rstrip("/") == base_url.rstrip("/")

        if _same_document:
            continue

        if is_file_download_url(abs_url):
            continue
        if is_external_booking_only_url(abs_url):
            eb[0] += 1
            continue
        if not _is_same_origin(base_url, abs_url) and not _is_external_form_host(abs_url):
            if not _looks_like_form_link(href, text):
                continue
        if chain_mode and is_chain_branch_listing_url(abs_url):
            continue
        if _looks_like_form_link(href, text) or _is_external_form_host(abs_url):
            anchor_candidates.append((abs_url, text))

    anchor_candidates.sort(key=lambda pair: _anchor_follow_priority(pair[0], pair[1]))
    anchor_urls = [u for u, _ in anchor_candidates]

    seen_anchor: set[str] = set()
    external_candidates: list[str] = []
    followed = 0
    for abs_url in anchor_urls:
        if followed >= max_follows:
            break
        if budget is not None and budget.exhausted:
            break
        if abs_url in seen_anchor:
            continue
        seen_anchor.add(abs_url)
        if is_file_download_url(abs_url):
            continue
        if is_external_booking_only_url(abs_url):
            eb[0] += 1
            continue
        if is_reservation_excluded_url(abs_url):
            continue
        if not _is_same_origin(base_url, abs_url):
            if _is_external_form_host(abs_url) or _looks_like_form_link(abs_url, ""):
                external_candidates.append(abs_url)
            continue
        if not await _goto_settled(page, abs_url, budget=budget):
            continue
        followed += 1
        html = await page.content()
        if not _has_inquiry_like_form(html) and not _is_external_form_host(abs_url):
            continue
        if is_reservation_excluded_page(abs_url, html):
            rc[0] += 1
            continue
        return abs_url

    # 外部フォームホスト（form.run / Google Forms 等）
    seen_ext: set[str] = set()
    for abs_url in external_candidates:
        if followed >= max_follows:
            break
        if budget is not None and budget.exhausted:
            break
        if abs_url in seen_ext:
            continue
        seen_ext.add(abs_url)
        if is_file_download_url(abs_url):
            continue
        if is_external_booking_only_url(abs_url):
            eb[0] += 1
            continue
        if is_reservation_excluded_url(abs_url):
            continue
        if not await _goto_settled(page, abs_url, budget=budget):
            continue
        followed += 1
        html = await page.content()
        if _is_external_form_host(abs_url):
            if is_reservation_excluded_page(abs_url, html):
                rc[0] += 1
                continue
            return abs_url
        if _has_inquiry_like_form(html) and not is_reservation_excluded_page(abs_url, html):
            return abs_url
    return None



async def recover_form_url_on_live_page(
    page,
    base_url: str,
    *,
    max_link_follows: int = 6,
    max_iframe_follows: int = 3,
) -> str | None:
    """
    Recover an inquiry form URL using the existing live Playwright page.

    Intended for resolver recovery only:
      resolver failure
        -> anchor inquiry scan
        -> iframe inquiry scan
        -> common contact paths

    Does not create a browser/context.
    Does not submit forms.
    """
    if not base_url:
        return None

    try:
        parsed = urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            return None

        origin = f"{parsed.scheme}://{parsed.netloc}"

        rejected_counter = [0]
        external_booking_counter = [0]

        # Recovery gets its own small navigation budget.
        budget = NavigationBudget(
            max_navigations=max(
                max_link_follows + max_iframe_follows + 4,
                8,
            ),
            deadline=time.monotonic() + min(
                FORM_FIND_TOTAL_TIMEOUT_SEC,
                30,
            ),
        )

        # Always restore/open the supplied starting URL first.
        if not await _goto_settled(page, base_url, budget=budget):
            return None

        # 1. Inquiry/contact links on current page.
        recovered = await _scan_anchor_links_for_inquiry_form(
            page,
            base_url,
            rejected_counter,
            external_booking_counter,
            budget,
            max_follows=max_link_follows,
            chain_mode=False,
        )
        if recovered:
            return recovered

        # Anchor scan may navigate away. Restore before iframe scan.
        if not budget.exhausted:
            await _goto_settled(page, base_url, budget=budget)

        # 2. Embedded inquiry forms.
        recovered = await _scan_iframe_sources_for_inquiry_form(
            page,
            base_url,
            rejected_counter,
            external_booking_counter,
            budget,
            max_follows=max_iframe_follows,
        )
        if recovered:
            return recovered

        # 3. Common same-origin inquiry paths.
        if not budget.exhausted:
            recovered = await _try_contact_paths_on_origin(
                page,
                origin,
                rejected_counter,
                budget,
            )

            # Recovery must actually move us to a different document.
            # Do not "recover" back to the same supplied URL.
            if recovered:
                try:
                    base_cmp = urlparse(base_url)
                    rec_cmp = urlparse(recovered)

                    same_document = (
                        base_cmp.scheme.lower() == rec_cmp.scheme.lower()
                        and base_cmp.netloc.lower() == rec_cmp.netloc.lower()
                        and base_cmp.path.rstrip("/") == rec_cmp.path.rstrip("/")
                        and base_cmp.query == rec_cmp.query
                    )
                except Exception:
                    same_document = (
                        recovered.rstrip("/") == base_url.rstrip("/")
                    )

                if not same_document:
                    return recovered

        return None

    except Exception:
        # Recovery is fail-closed. Existing resolver classification
        # remains authoritative when recovery cannot complete.
        return None

async def _try_chain_site_fallback(
    page,
    base_url: str,
    origin: str,
    rejected_counter: list[int] | None = None,
    external_booking_counter: list[int] | None = None,
    budget: NavigationBudget | None = None,
    max_parent_levels: int = CHAIN_SITE_MAX_PARENT_LEVELS,
) -> str | None:
    """
    店舗・支店URL向け: サイトルートのリンク探索と /contact 系パスを追加試行する（P1）。
    """
    rc = rejected_counter if rejected_counter is not None else [0]
    eb = external_booking_counter if external_booking_counter is not None else [0]
    root = origin.rstrip("/") + "/"
    if not await _goto_settled(page, root, budget=budget):
        return None

    form_url = await _scan_anchor_links_for_inquiry_form(
        page, root, rc, eb, budget, chain_mode=True
    )
    if form_url:
        return form_url

    form_url = await _try_contact_paths_on_origin(page, origin, rc, budget)
    if form_url:
        return form_url

    parsed = urlparse(base_url)
    parts = [p for p in parsed.path.split("/") if p]
    levels = 0
    while len(parts) > 1 and levels < max_parent_levels:
        levels += 1
        parts.pop()
        parent = f"{parsed.scheme}://{parsed.netloc}/{'/'.join(parts)}/"
        if budget is not None and budget.exhausted:
            break
        if not await _goto_settled(page, parent, budget=budget):
            break
        hit = await _try_contact_paths_on_origin(page, f"{parsed.scheme}://{parsed.netloc}", rc, budget)
        if hit:
            return hit
    return None


async def _try_contact_paths_on_origin(
    page,
    origin: str,
    rejected_counter: list[int] | None = None,
    budget: NavigationBudget | None = None,
    max_paths: int = FORM_FIND_MAX_CONTACT_PATHS,
    paths: tuple[str, ...] | list[str] | None = None,
) -> str | None:
    """
    同一オリジンのルートに /contact, /inquiry, /form 等を付与して試行する。
    問い合わせらしい<form>があり、かつ予約ページでない URL だけ返す。
    """
    rc = rejected_counter if rejected_counter is not None else [0]

    path_list = list(paths) if paths is not None else CANDIDATE_PATHS
    path_list = sorted(path_list, key=_contact_path_priority)[:max_paths]
    for path in path_list:
        if budget is not None and budget.exhausted:
            break
        candidate = origin.rstrip("/") + path
        if is_file_download_url(candidate):
            continue
        if not await _goto_settled(page, candidate, budget=budget):
            continue
        html = await page.content()
        if not _has_inquiry_like_form(html):
            continue
        if is_reservation_excluded_page(candidate, html):
            rc[0] += 1
            continue
        return candidate
    return None


async def _google_search_inquiry_form(
    page,
    company_name: str,
    origin: str,
    rejected_counter: list[int] | None = None,
    budget: NavigationBudget | None = None,
    max_follows: int = FORM_FIND_MAX_GOOGLE_FOLLOWS,
) -> str | None:
    """
    最終手段: Google で「{会社名} お問い合わせ」を検索し、問い合わせフォーム URL を探す。
    """
    if not ENABLE_GOOGLE_FORM_SEARCH or not (company_name or "").strip():
        return None
    if is_chain_corporate_host(origin):
        return None

    rc = rejected_counter if rejected_counter is not None else [0]
    q = quote_plus(f"{company_name.strip()} お問い合わせ")
    search_url = f"https://www.google.com/search?q={q}&hl=ja&num=10"
    if not await _goto_settled(page, search_url, budget=budget):
        return None

    try:
        hrefs = await page.eval_on_selector_all(
            "a[href]",
            """els => els.map(el => el.href).filter(h => h && h.startsWith('http'))""",
        )
    except Exception:
        return None

    seen: set[str] = set()
    origin_host = urlparse(origin).netloc.lower()
    followed = 0
    for href in hrefs[:15]:
        if followed >= max_follows:
            break
        if budget is not None and budget.exhausted:
            break
        href = (href or "").strip()
        if not href or href in seen:
            continue
        seen.add(href)
        if "google." in urlparse(href).netloc.lower():
            continue
        if is_file_download_url(href):
            continue
        if is_external_booking_only_url(href) or is_reservation_excluded_url(href):
            continue
        host = urlparse(href).netloc.lower()
        path_l = urlparse(href).path.lower()
        same_site = host == origin_host
        contactish = any(
            k in path_l or k in href.lower()
            for k in (
                "contact",
                "inquiry",
                "inquire",
                "toiawase",
                "form",
                "support",
                "mail",
            )
        )
        if not same_site and not contactish and not _is_external_form_host(href):
            continue
        if not await _goto_settled(page, href, budget=budget):
            continue
        followed += 1
        html = await page.content()
        if not _has_inquiry_like_form(html) and not _is_external_form_host(href):
            continue
        if is_reservation_excluded_page(href, html):
            rc[0] += 1
            continue
        return href
    return None


# ─── メイン処理 ───────────────────────────────────────────────────────────────

async def _find_form_url_inner(
    website_url: str,
    company_name: str | None = None,
    timeout_sec: int | None = None,
) -> dict:
    """
    website_url からフォーム URL を特定する。

    Args:
        website_url: 企業サイト URL
        company_name: Google 検索フォールバック用（任意）

    Returns:
        {
            "form_url": str | None,
            "status":   "found" | "no_form" | "pending" | "error",
            "reason":   str  # status が found 以外の場合の詳細
        }
    """
    if not website_url or not str(website_url).strip():
        return {
            "form_url": None,
            "status":   "error",
            "reason":   "website_url_is_none",
        }

    base_url = str(website_url).strip()
    if is_file_download_url(base_url):
        return {
            "form_url": None,
            "status":   "error",
            "reason":   "pdf_or_file_download",
        }
    if is_external_booking_only_url(base_url):
        return {
            "form_url": None,
            "status":   "no_form",
            "reason":   "no_form_external_booking",
        }

    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    except ImportError:
        return {
            "form_url": None,
            "status":   "error",
            "reason":   "playwright がインストールされていません: pip install playwright && playwright install chromium",
        }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await context.new_page()
        page.set_default_navigation_timeout(NAV_TIMEOUT)
        page.set_default_timeout(NAV_TIMEOUT + 5_000)

        chain_mode = is_chain_corporate_host(base_url)
        total_timeout = timeout_sec or FORM_FIND_TOTAL_TIMEOUT_SEC
        budget = NavigationBudget(
            max_navigations=CHAIN_SITE_MAX_NAVIGATIONS if chain_mode else FORM_FIND_MAX_NAVIGATIONS,
            deadline=time.monotonic() + total_timeout,
        )

        try:
            origin = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
            rejected_reservation_inquiry: list[int] = [0]
            external_booking_signals: list[int] = [0]
            form_url: str | None = None

            # ── Step 1: トップページ ─────────────────────────────────────────
            if not form_url:
                if not await _goto_settled(page, base_url, budget=budget):
                    await browser.close()
                    reason = "form_find_timeout" if budget.exhausted else "timeout"
                    return {"form_url": None, "status": "error", "reason": reason}
                if await _page_is_external_booking_only_signal(page, base_url):
                    await browser.close()
                    return {
                        "form_url": None,
                        "status":   "no_form",
                        "reason":   "no_form_external_booking",
                    }

            # ── Step 2: リンク候補 ───────────────────────────────────────────
            if not form_url:
                form_url = await _scan_anchor_links_for_inquiry_form(
                    page,
                    base_url,
                    rejected_reservation_inquiry,
                    external_booking_signals,
                    budget,
                    max_follows=4 if chain_mode else FORM_FIND_MAX_LINK_FOLLOWS,
                    chain_mode=chain_mode,
                )

            # ── Step 2b: iframe ──────────────────────────────────────────────
            if not form_url and not chain_mode:
                form_url = await _scan_iframe_sources_for_inquiry_form(
                    page, base_url, rejected_reservation_inquiry, external_booking_signals, budget
                )

            # ── Step 3: /contact 等 ──────────────────────────────────────────
            if not form_url:
                form_url = await _try_contact_paths_on_origin(
                    page, origin, rejected_reservation_inquiry, budget
                )

            # ── Step 4: トップに<form> ───────────────────────────────────────
            if not form_url and not budget.exhausted:
                if await _goto_settled(page, base_url, budget=budget):
                    html = await page.content()
                    if _has_inquiry_like_form(html):
                        if is_reservation_excluded_page(base_url, html):
                            rejected_reservation_inquiry[0] += 1
                        elif not is_file_download_url(base_url):
                            form_url = base_url

            # ── Step 5: 候補の再検証 ─────────────────────────────────────────
            if form_url and not is_file_download_url(form_url):
                if await _goto_settled(page, form_url, budget=budget):
                    html = await page.content()
                    if not _has_inquiry_like_form(html):
                        form_url = None
                    elif is_reservation_excluded_page(form_url, html):
                        rejected_reservation_inquiry[0] += 1
                        form_url = None
                else:
                    form_url = None

            # ── Step 5b: チェーン店舗（浅いフォールバックのみ）────────────────
            if not form_url and _is_branch_store_url(base_url) and not budget.exhausted:
                form_url = await _try_chain_site_fallback(
                    page,
                    base_url,
                    origin,
                    rejected_reservation_inquiry,
                    external_booking_signals,
                    budget,
                )

            # ── Step 6: Google（チェーン・予算枯渇時はスキップ）────────────────
            if not form_url and not chain_mode and not budget.exhausted:
                form_url = await _google_search_inquiry_form(
                    page,
                    company_name or "",
                    origin,
                    rejected_reservation_inquiry,
                    budget,
                )

            # ── Step 7: 最終確認・reCAPTCHA ─────────────────────────────────
            if form_url and not is_file_download_url(form_url):
                if await _goto_settled(page, form_url, budget=budget):
                    html = await page.content()
                    if is_reservation_excluded_page(form_url, html):
                        rejected_reservation_inquiry[0] += 1
                        form_url = None
                    elif _has_recaptcha(html):
                        await browser.close()
                        return {
                            "form_url": form_url,
                            "status":   "pending",
                            "reason":   "recaptcha_detected",
                        }
                else:
                    form_url = None

            if form_url and not is_file_download_url(form_url):
                await browser.close()
                return {"form_url": form_url, "status": "found", "reason": ""}

            await browser.close()
            if budget.exhausted:
                fail_reason = "form_find_timeout"
                status = "error"
            elif external_booking_signals[0] > 0 and rejected_reservation_inquiry[0] == 0:
                fail_reason = "no_form_external_booking"
                status = "no_form"
            elif rejected_reservation_inquiry[0] > 0:
                fail_reason = "no_contact_form_only_reservation"
                status = "no_form"
            elif chain_mode or _is_branch_store_url(base_url):
                fail_reason = "no_form_chain_site"
                status = "no_form"
            else:
                fail_reason = "問い合わせページが見つからない"
                status = "no_form"
            return {
                "form_url": None,
                "status":   status,
                "reason":   fail_reason,
            }

        except PWTimeout:
            await browser.close()
            return {"form_url": None, "status": "error", "reason": "timeout"}
        except Exception as e:
            await browser.close()
            err = str(e)
            if is_file_download_url(base_url) or "Download is starting" in err:
                return {"form_url": None, "status": "error", "reason": "pdf_or_file_download"}
            return {"form_url": None, "status": "error", "reason": err}


def _chain_site_early_result(website_url: str) -> dict | None:
    """チェーン本部ドメインは Playwright を起動せず即スキップ。"""
    if is_chain_corporate_host(website_url or ""):
        return {
            "form_url": None,
            "status":   "no_form",
            "reason":   "no_form_chain_site",
        }
    return None


async def find_form_url(
    website_url: str,
    company_name: str | None = None,
    timeout_sec: int | None = None,
) -> dict:
    """
    website_url からフォーム URL を特定する（全体タイムアウト・遷移上限付き）。
    チェーン本部ドメインはブラウザ起動前に即 no_form_chain_site を返す。

    timeout_sec: detect-only 等で一時的に延長する場合のみ指定（本番デフォルトは変更しない）。
    """
    if not website_url or not str(website_url).strip():
        return {
            "form_url": None,
            "status":   "error",
            "reason":   "website_url_is_none",
        }

    base_url = str(website_url).strip()
    if is_file_download_url(base_url):
        return {
            "form_url": None,
            "status":   "error",
            "reason":   "pdf_or_file_download",
        }
    if is_external_booking_only_url(base_url):
        return {
            "form_url": None,
            "status":   "no_form",
            "reason":   "no_form_external_booking",
        }

    chain_hit = _chain_site_early_result(base_url)
    if chain_hit is not None:
        return chain_hit

    total_timeout = timeout_sec or FORM_FIND_TOTAL_TIMEOUT_SEC
    try:
        return await asyncio.wait_for(
            _find_form_url_inner(base_url, company_name=company_name, timeout_sec=total_timeout),
            timeout=total_timeout,
        )
    except asyncio.TimeoutError:
        return {
            "form_url": None,
            "status":   "error",
            "reason":   "form_find_timeout",
        }


# ─── CLI ─────────────────────────────────────────────────────────────────────


async def _cli_check_url(url: str) -> None:
    """--check-url: URL・実ページのタイトル/h1 に基づき除外判定を表示する。"""
    raw = url.strip()
    url_hit = is_reservation_excluded_url(raw)
    title_blob = ""
    title_hit = False
    fetch_err: str | None = None

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await _goto_settled(page, raw)
            html = await page.content()
            await browser.close()
            title_blob = _extract_title_and_h1_inner_text(html)
            title_hit = is_reservation_excluded_title_blob(title_blob)
    except Exception as e:
        fetch_err = str(e)

    print(f"URL: {raw}")
    print(f"  URLキーワード除外: {'はい' if url_hit else 'いいえ'}")
    if fetch_err:
        print(f"  ページ取得: 失敗 ({fetch_err}) — タイトル・h1は未判定")
    else:
        preview = (title_blob[:160] + "…") if len(title_blob) > 160 else title_blob
        print(f"  ページタイトル+h1抜粋: {preview!r}")
        print(f"  タイトル・h1キーワード除外: {'はい' if title_hit else 'いいえ'}")

    if fetch_err and not url_hit:
        print("→ 総合: ページ未取得のためタイトル・h1は未判定（URLキーワードのみ参考）")
    else:
        overall = url_hit or title_hit
        print(
            "→ 総合: "
            + (
                "除外対象（予約系としてフォームURLに採用しない）"
                if overall
                else "除外しない（問い合わせ候補になり得る）"
            )
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="問い合わせフォームURL探索ユーティリティ")
    ap.add_argument(
        "--check-url",
        metavar="URL",
        help="そのURLが予約除外ルールに該当するか表示（Playwrightでタイトル・h1も取得）",
    )
    args = ap.parse_args()
    if args.check_url:
        asyncio.run(_cli_check_url(args.check_url))
    else:
        ap.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
