"""運用ダッシュボード用 — Agent Readiness Insights Season 1 日次運用指標。"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_JST = ZoneInfo("Asia/Tokyo")
_ARI_ROOT = "10_Projects/Agent Readiness"
_SCHEDULE = "insights/_scheduled/schedule.json"
_BUFFER_QUEUE = "insights/_social/buffer/queue.json"
_BUFFER_FAILED = "insights/_social/buffer/failed-log.json"


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _load_schedule(vault_root: Path) -> list[dict[str, Any]]:
    path = vault_root / _ARI_ROOT / _SCHEDULE
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [a for a in data.get("articles", []) if a.get("series") == "v2"]


def _today_article(articles: list[dict[str, Any]], today: date) -> dict[str, Any] | None:
    prefix = today.isoformat()
    for a in articles:
        if a.get("status") == "scheduled" and (a.get("publishAt") or "").startswith(prefix):
            return a
    for a in articles:
        if a.get("status") == "scheduled":
            return a
    return None


def _load_buffer_queue(vault_root: Path) -> list[dict[str, Any]]:
    path = vault_root / _ARI_ROOT / _BUFFER_QUEUE
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("posts", [])


def _buffer_status_for_slug(posts: list[dict[str, Any]], slug: str) -> str:
    post = next((p for p in posts if p.get("slug") == slug), None)
    if not post:
        return "queue.json にエントリなし"
    channels = post.get("channels") or {}
    parts = []
    for ch in ("linkedin", "facebook", "x"):
        c = channels.get(ch) or {}
        st = c.get("status", "—")
        bid = c.get("bufferUpdateId")
        mark = "✓" if bid else "—"
        parts.append(f"{ch}: {st} {mark}")
    return f"記事 status={post.get('status', '—')} · " + " · ".join(parts)


def _recent_buffer_failures(vault_root: Path, limit: int = 3) -> list[str]:
    path = vault_root / _ARI_ROOT / _BUFFER_FAILED
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries") or []
    lines = []
    for e in reversed(entries[-limit:]):
        lines.append(
            f"{e.get('at', '—')[:16]} · {e.get('slug', '—')} · {e.get('channel') or e.get('error', '—')}"
        )
    return lines


def build_ari_dynamic_html(vault_root: Path, today: date, generated: datetime) -> str:
    articles = _load_schedule(vault_root)
    buffer_posts_all = _load_buffer_queue(vault_root)
    st: dict[str, int] = {"published": 0, "scheduled": 0, "editorial_hold": 0}
    for a in articles:
        status = a.get("status", "unknown")
        st[status] = st.get(status, 0) + 1

    today_art = _today_article(articles, today)
    # Prefer buffer queue entry for today's transfer date
    today_ymd = today.isoformat()
    buffer_today = next(
        (
            p
            for p in buffer_posts_all
            if (p.get("bufferTransferAt") or "").startswith(today_ymd)
        ),
        None,
    )

    if buffer_today:
        slug = buffer_today.get("slug", "—")
        title = buffer_today.get("title") or next(
            (a.get("title", "—") for a in articles if a.get("slug") == slug), "—"
        )
        note = _buffer_status_for_slug(buffer_posts_all, slug)
    elif today_art:
        slug = today_art.get("slug", "—")
        title = today_art.get("title", "—")
        publish_at = today_art.get("publishAt", "—")
        note = f"schedule: {today_art.get('status', '—')} · 公開 {publish_at}"
    else:
        slug = "—"
        title = "本日 transfer 対象なし"
        note = "editorial_hold 順次 unlock"

    failures = _recent_buffer_failures(vault_root)
    fail_html = ""
    if failures:
        fail_html = (
            '<div class="expo-note" style="margin-bottom:20px;border-color:rgba(248,113,113,0.35)">'
            "<strong>Buffer failed-log（直近）:</strong><br>"
            + "<br>".join(_escape(x) for x in failures)
            + "</div>"
        )

    ts = generated.strftime("%Y-%m-%d %H:%M:%S")
    return f"""<p class="sub" style="margin:0 0 12px">生成: <strong>{ts}</strong> · schedule.json + buffer/queue.json 同期</p>
<div class="kpis" style="margin-bottom:20px">
<div class="kpi"><div class="label">Season 1 記事</div><div class="value">{len(articles)}</div><div class="note">v2 Core</div></div>
<div class="kpi"><div class="label">公開済</div><div class="value" style="color:var(--success)">{st.get('published', 0)}</div><div class="note">published</div></div>
<div class="kpi"><div class="label">公開待ち</div><div class="value" style="color:var(--warn)">{st.get('scheduled', 0)}</div><div class="note">scheduled</div></div>
<div class="kpi"><div class="label">editorial_hold</div><div class="value">{st.get('editorial_hold', 0)}</div><div class="note">unlock 順次</div></div>
<div class="kpi"><div class="label">v5 Review</div><div class="value">28</div><div class="note">avg 88.7 · PASS</div></div>
<div class="kpi"><div class="label">Evidence</div><div class="value">13</div><div class="note">Batch 4–6</div></div>
</div>
<div class="expo-note" style="margin-bottom:12px">
<strong>本日の Buffer 対象:</strong> <code>{_escape(slug)}</code> — {_escape(str(title))}
<span class="hint" style="display:block;margin-top:6px">{_escape(note)}</span>
</div>
{fail_html}"""


def build_ari_section_html(vault_root: Path, today: date, generated: datetime) -> str:
    template = Path(__file__).resolve().parent / "templates" / "ops_dashboard_ari_section.html"
    if not template.exists():
        return ""
    dynamic = build_ari_dynamic_html(vault_root, today, generated)
    return template.read_text(encoding="utf-8").replace("__ARI_DYNAMIC__", dynamic, 1).strip()
