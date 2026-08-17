"""
message_builder.py  —  業種別文面生成モジュール

url_builder で生成した LP URL と templates/messages.py のテンプレートを組み合わせ、
送信用メッセージ文字列を返す。
"""

from __future__ import annotations

from url_builder import build_lp_url, get_industry_slug
from templates.messages import (
    ARI_MESSAGE_V1,
    ARI_MESSAGE_V2,
    ARI_MESSAGE_V2_SUBJECT_RECOMMENDATION,
)

# Email body: max 1 positive observation (deterministic priority)
EMAIL_POSITIVE_OBS_PRIORITY: tuple[str, ...] = (
    "OBS_ACTION_PATH_PRESENT",
    "OBS_BOOKING_PATH_PRESENT",
    "OBS_FAQ_STRUCTURE_OK",
    "OBS_SCHEMA_OK",
    "OBS_SERVICE_INFO_OK",
    "OBS_LLMS_TXT_OK",
)

# Human-facing email copy (semantics aligned with catalog approved_copy; no internal wording)
EMAIL_OBSERVATION_COPY: dict[str, str] = {
    "OBS_ACTION_PATH_PRESENT": (
        "お問い合わせなど、サービス利用に向けた導線を確認できました。"
    ),
    "OBS_BOOKING_PATH_PRESENT": (
        "予約・問い合わせに向けた導線を確認できました。"
    ),
    "OBS_FAQ_STRUCTURE_OK": (
        "FAQ / よくある質問に関する情報を確認できました。"
    ),
    "OBS_SCHEMA_OK": (
        "構造化データ（Schema.org）を確認できました。"
    ),
    "OBS_SERVICE_INFO_OK": (
        "サービス内容を示す基本情報を確認できました。"
    ),
    "OBS_LLMS_TXT_OK": (
        "llms.txt に関する情報を確認できました。"
    ),
}

_SEO_TAIL_MARKERS = ("修理", "調査", "工事", "対応", "サービス", "エリア", "近く", "おすすめ", "塗装", "清掃")

# slug → 検索フレーズ用の業種キーワード短縮形
INDUSTRY_KEYWORD_BY_SLUG: dict[str, str] = {
    "beauty-clinic": "美容クリニック",
    "restaurant": "飲食店",
    "hr": "求人",
    "accountant": "税理士",
    "dental": "歯科",
    "gym": "パーソナルジム",
    "esthetic": "エステ",
    "hair-salon": "美容院",
    "nail-salon": "ネイルサロン",
    "hair-removal": "医療脱毛",
    "aga": "AGA",
    "seitai": "整体院",
    "realestate": "不動産査定",
    "housing": "ハウスメーカー",
    "reform": "リフォーム",
    "career": "転職エージェント",
    "programming": "プログラミングスクール",
    "lawyer-general": "弁護士",
    "emergency": "緊急修理",
    "ceremony": "結婚式場",
    "car-buy": "車買取",
    "saas": "業務システム",
    "web-agency": "Web制作",
    "meo": "MEO",
    "seo": "SEO",
    "lawyer": "士業",
    "shindan": "AI検索診断",
    "dermatology": "皮膚科",
    "psychiatry": "心療内科",
    "orthopedics": "整形外科",
    "fertility": "不妊治療",
    "diet-clinic": "ダイエット外来",
    "eyeclinic": "眼科",
    "childcare": "学習塾",
    "cram-school": "予備校",
    "online-school": "オンライン英会話",
    "nursery": "保育園",
    "pet-hotel": "ペットホテル",
    "pet-clinic": "動物病院",
    "funeral": "葬儀社",
    "inheritance": "遺品整理",
    "insurance": "保険相談",
    "car-lease": "カーリース",
    "used-car-buy": "中古車",
    "moving": "引越し",
    "storage": "トランクルーム",
    "cleaning": "ハウスクリーニング",
    "pest-control": "害虫駆除",
    "interior": "インテリア",
    "meal-kit": "食材宅配",
    "temp-agency": "人材派遣",
    "divorce-law": "離婚弁護士",
    "exterior-painting": "外壁塗装",
    "dental-cosmetic": "ホワイトニング",
}

# 日本語業種名 → キーワード（slug 解決前のフォールバック）
INDUSTRY_KEYWORD_BY_NAME: dict[str, str] = {
    "美容クリニック": "美容クリニック",
    "飲食店": "飲食店",
    "求人・採用": "求人",
    "税理士・会計士": "税理士",
    "歯科クリニック": "歯科",
    "歯科": "歯科",
    "パーソナルジム": "パーソナルジム",
    "エステサロン": "エステ",
    "美容院・ヘアサロン": "美容院",
    "ネイルサロン": "ネイルサロン",
    "医療脱毛・エステ脱毛": "医療脱毛",
    "AGA・薄毛治療": "AGA",
    "整体院・整骨院": "整体院",
    "整骨院": "整体院",
    "接骨院": "整体院",
    "鍼灸院": "整体院",
    "整体院": "整体院",
    "不動産売却・査定": "不動産査定",
    "注文住宅・ハウスメーカー": "ハウスメーカー",
    "リフォーム・リノベーション": "リフォーム",
    "転職エージェント": "転職エージェント",
    "プログラミングスクール": "プログラミングスクール",
    "弁護士事務所": "弁護士",
    "水道修理・鍵開け緊急サービス": "緊急修理",
    "結婚式場・葬儀社": "結婚式場",
    "中古車買取": "車買取",
    "BtoB SaaS・業務システム": "業務システム",
    "Web制作・マーケティング支援": "Web制作",
    "MEO対策": "MEO",
    "SEO対策": "SEO",
    "司法書士・社労士・行政書士": "士業",
    "AI検索診断": "AI検索診断",
    "皮膚科・アトピークリニック": "皮膚科",
    "心療内科・精神科クリニック": "心療内科",
    "整形外科・スポーツ整体": "整形外科",
    "不妊治療クリニック": "不妊治療",
    "ダイエット外来・肥満外科": "ダイエット外来",
    "眼科・レーシック・ICL": "眼科",
    "学習塾・個別指導塾": "学習塾",
    "予備校・大学受験対策": "予備校",
    "オンライン英会話・語学スクール": "オンライン英会話",
    "保育園・託児所": "保育園",
    "ペットホテル・トリミング": "ペットホテル",
    "動物病院・ペットクリニック": "動物病院",
    "葬儀・斎場": "葬儀社",
    "遺品整理・相続手続き代行": "遺品整理",
    "保険代理店・FP相談": "保険相談",
    "カーリース・車販売": "カーリース",
    "中古車販売": "中古車",
    "引越し業者・単身引越し": "引越し",
    "トランクルーム・収納サービス": "トランクルーム",
    "ハウスクリーニング・エアコン清掃": "ハウスクリーニング",
    "害虫駆除・シロアリ対策": "害虫駆除",
    "インテリアコーディネート・家具": "インテリア",
    "食材宅配・ミールキット": "食材宅配",
    "人材派遣・スタッフィング": "人材派遣",
    "離婚専門弁護士・調停サポート": "離婚弁護士",
    "外壁塗装・屋根工事": "外壁塗装",
    "ホワイトニング・審美歯科": "ホワイトニング",
    "歯科・歯医者": "歯科",
    "整体院・整骨院・鍼灸院": "整体院",
    "不動産会社": "不動産査定",
}


def get_industry_keyword(industry_name: str, slug: str | None = None) -> str:
    """業種名から検索フレーズ用キーワード短縮形を返す。"""
    name = (industry_name or "").strip()
    if name and name in INDUSTRY_KEYWORD_BY_NAME:
        return INDUSTRY_KEYWORD_BY_NAME[name]
    resolved_slug = slug or (get_industry_slug(name) if name else None)
    if resolved_slug and resolved_slug in INDUSTRY_KEYWORD_BY_SLUG:
        return INDUSTRY_KEYWORD_BY_SLUG[resolved_slug]
    if name:
        for key, kw in INDUSTRY_KEYWORD_BY_NAME.items():
            if name in key or key in name:
                return kw
        return name
    return "おすすめ"


def format_search_phrase(area_name: str, industry_keyword: str, slug: str | None = None) -> str:
    """業種別 AI 検索クエリを優先。未登録時は area + keyword。"""
    area = (area_name or "").strip()
    if slug and slug in AI_SEARCH_QUERY:
        return AI_SEARCH_QUERY[slug].format(area_name=area)
    parts = [p.strip() for p in (area, industry_keyword) if p and p.strip()]
    return " ".join(parts) if parts else industry_keyword


def build_message(
    industry_name: str,
    company_name: str,
    lp_url: str,
    area_name: str = "",
) -> str:
    """
    業種・会社名・エリア・LP URL からフォーム送信用メッセージを生成する。

    Args:
        industry_name: 業種名（日本語）例: "美容クリニック"
        company_name:  会社名        例: "麻布台美容皮膚科クリニック"
        lp_url:        LP URL
        area_name:     エリア名      例: "港区"

    Returns:
        送信用メッセージ文字列（変数展開済み）
    """
    slug = get_industry_slug(industry_name)
    industry_keyword = get_industry_keyword(industry_name, slug)

    return ARI_MESSAGE_V1.format(
        lp_url=lp_url,
    )


def sanitize_company_display_name(
    name: str,
    *,
    domain: str = "",
) -> tuple[str, bool, str]:
    """
    Trim SEO-stuffed listing labels for email salutation.

    Returns:
        (display_name, was_normalized, review_note)
        review_note is non-empty when human review is recommended.
    """
    original = (name or "").strip()
    if not original:
        return "貴社", False, ""

    normalized = original
    was_normalized = False
    review_note = ""

    if "【" in normalized:
        candidate = normalized.split("【", 1)[0].strip()
        if candidate and len(candidate) < len(normalized):
            normalized = candidate
            was_normalized = True

    if "（" in normalized and len(normalized) > 40:
        candidate = normalized.split("（", 1)[0].strip()
        if candidate and len(candidate) <= 35:
            normalized = candidate
            was_normalized = True

    parts = normalized.split()
    if len(parts) >= 3:
        tail_seo = sum(
            1 for part in parts[2:] if any(marker in part for marker in _SEO_TAIL_MARKERS)
        )
        if tail_seo >= max(1, len(parts) - 2):
            candidate = " ".join(parts[:2])
            if candidate and candidate != normalized:
                normalized = candidate
                was_normalized = True

    if was_normalized and normalized != original:
        review_note = f"SEO label trimmed: `{original}` → `{normalized}`"
    elif len(original) > 45:
        review_note = f"Long display name retained: `{original}`"

    return normalized, was_normalized, review_note


def select_email_positive_observation(observations: list[dict]) -> dict | None:
    """Pick at most one observation for the email body (positive preferred)."""
    if not observations:
        return None

    by_code = {
        (obs.get("code") or "").strip(): obs
        for obs in observations
        if (obs.get("code") or "").strip()
    }
    for code in EMAIL_POSITIVE_OBS_PRIORITY:
        if code in by_code:
            return by_code[code]

    for obs in observations:
        code = (obs.get("code") or "").strip()
        if not code or code.endswith("_UNREACHABLE"):
            continue
        if obs.get("severity") == "info" or code.endswith(("_OK", "_PRESENT")):
            return obs

    for obs in observations:
        code = (obs.get("code") or "").strip()
        if code and not code.endswith("_UNREACHABLE"):
            return obs
    return None


def humanize_email_observation(obs: dict | None) -> str:
    """Render catalog observation as human-facing email sentence (no internal jargon)."""
    if not obs:
        return "公開情報から主要な確認項目を整理しました。"

    code = (obs.get("code") or "").strip()
    if code in EMAIL_OBSERVATION_COPY:
        return EMAIL_OBSERVATION_COPY[code]

    copy = (obs.get("approved_copy") or obs.get("copy") or "").strip()
    for prefix in (
        "公開ページ上で、",
        "公開ページ上では、",
        "公開ページ上で",
        "確認した公開ページでは ",
        "確認した公開ページのHTML解析時点。",
    ):
        if copy.startswith(prefix):
            copy = copy[len(prefix):].lstrip()
            break

    if copy.endswith("。"):
        return copy
    if copy:
        return f"{copy}。"
    return "公開情報から主要な確認項目を整理しました。"


def build_message_v2(
    company_name: str,
    website_url: str,
    lp_url: str,
    observations: list[dict],
    *,
    company_display_name: str | None = None,
) -> str:
    """V2 文面（observation 1件 + bridge + preview URL）。送信切替前の dry-run 用。"""
    display_name, _, _ = sanitize_company_display_name(
        company_display_name or company_name,
    )
    selected = select_email_positive_observation(observations)
    positive_observation = humanize_email_observation(selected)
    return ARI_MESSAGE_V2.format(
        company_name=display_name,
        lp_url=lp_url,
    )


def build_message_v2_render_context(
    company_name: str,
    website_url: str,
    lp_url: str,
    observations: list[dict],
    *,
    domain: str = "",
    company_display_name: str | None = None,
) -> dict:
    """Deterministic V2 render metadata for review artifacts."""
    original = (company_name or "").strip()
    display_name, was_normalized, review_note = sanitize_company_display_name(
        company_display_name or company_name,
        domain=domain,
    )
    selected = select_email_positive_observation(observations)
    positive_observation = humanize_email_observation(selected)
    rendered = ARI_MESSAGE_V2.format(
        company_name=display_name,
        lp_url=lp_url,
    )
    return {
        "company_original": original,
        "company_display_name": display_name,
        "display_name_normalized": was_normalized,
        "display_name_review_note": review_note,
        "domain": domain,
        "website_url": (website_url or "").strip(),
        "selected_observation_code": (selected or {}).get("code", ""),
        "selected_observation_approved_copy": (selected or {}).get("approved_copy", ""),
        "positive_observation_sentence": positive_observation,
        "subject": ARI_MESSAGE_V2_SUBJECT_RECOMMENDATION,
        "rendered_message": rendered,
    }


def build_preview_message_for_company(
    company: dict,
    *,
    ab_arm: str = "C",
    dry_run_snapshot: bool = False,
) -> tuple[str, str, dict | None]:
    """
    crawler join → snapshot → V2 文面を生成（送信はしない）。

    Returns:
        (preview_url_or_lp, message, snapshot_or_none)
    """
    from observations.snapshot_builder import create_preview_snapshot
    from observations.crawler_join import lookup_crawler_data_for_company
    from url_builder import build_lp_url

    crawler = lookup_crawler_data_for_company(company)
    if not crawler:
        lp = build_lp_url(company.get("industry_name", ""), company.get("area_name", ""))
        msg = build_message(
            company.get("industry_name", ""),
            company.get("company_name", ""),
            lp,
            area_name=company.get("area_name", ""),
        )
        return lp, msg, None

    snap = create_preview_snapshot(
        company,
        crawler_data=crawler,
        ab_arm=ab_arm,
        dry_run=dry_run_snapshot,
    )
    lp_url = snap["preview_url"] if ab_arm == "C" else build_lp_url(
        company.get("industry_name", ""), company.get("area_name", "")
    )
    message = build_message_v2(
        company.get("company_name", ""),
        company.get("website_url") or company.get("url", ""),
        lp_url,
        snap.get("message_observations") or [],
    )
    return lp_url, message, snap


def build_message_for_company(company: dict) -> tuple[str, str]:
    """
    company dict（parser.py の出力）から LP URL とメッセージを一括生成する。

    Args:
        company: parser.parse_md_file() が返す dict

    Returns:
        (lp_url, message) のタプル
    """
    lp_url = build_lp_url(company["industry_name"], company["area_name"])
    message = build_message(
        company["industry_name"],
        company["company_name"],
        lp_url,
        area_name=company.get("area_name", ""),
    )
    return lp_url, message


def build_preview_record(
    company: dict,
    *,
    ab_arm: str = "C",
    dry_run_snapshot: bool = True,
    crawler_data: dict | None = None,
) -> dict:
    """
    Structured preview record for P1 validation (zero send).
    """
    from urllib.parse import urlparse
    import hashlib

    from observations.resolver import map_industry_to_form

    website_url = company.get("website_url") or company.get("url") or ""
    company_name = company.get("company_name") or ""
    industry_name = company.get("industry_name") or company.get("industry") or ""
    domain = urlparse(website_url).netloc or website_url

    def _local_candidate_id() -> str:
        raw = f"{domain}|{company_name}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    record: dict = {
        "company": company_name,
        "domain": domain,
        "url": website_url,
        "industry": map_industry_to_form(industry_name),
        "industry_source": industry_name,
        "message_version": "ARI_MESSAGE_V2" if ab_arm in ("B", "C") else "ARI_MESSAGE_V1",
        "ab_arm": ab_arm,
        "observations": [],
        "preview_token": None,
        "preview_url": None,
        "rendered_message": "",
        "fallback": False,
        "fallback_reason": "",
    }

    if ab_arm == "A":
        lp_url, message = build_message_for_company(company)
        record["preview_url"] = lp_url
        record["rendered_message"] = message
        return record

    # B / C — V2 path
    from observations.snapshot_builder import create_preview_snapshot

    row = crawler_data
    if row is None:
        from observations.crawler_join import lookup_preview_evidence
        row, evidence_src = lookup_preview_evidence(company)
    else:
        evidence_src = row.get("evidence_source") or "reservation_crawler"

    if not row:
        lp_url = build_lp_url(company.get("industry_name", ""), company.get("area_name", ""))
        message = build_message(
            company.get("industry_name", ""),
            company_name,
            lp_url,
            area_name=company.get("area_name", ""),
        )
        record["fallback"] = True
        record["fallback_reason"] = "preview_evidence_not_found"
        record["preview_url"] = lp_url
        record["rendered_message"] = message
        record["message_version"] = "ARI_MESSAGE_V1"
        return record

    try:
        snap = create_preview_snapshot(
            company,
            crawler_data=row,
            ab_arm=ab_arm,
            dry_run=dry_run_snapshot,
        )
    except ValueError as e:
        lp_url = build_lp_url(company.get("industry_name", ""), company.get("area_name", ""))
        message = build_message(
            company.get("industry_name", ""),
            company_name,
            lp_url,
            area_name=company.get("area_name", ""),
        )
        record["fallback"] = True
        record["fallback_reason"] = str(e)
        record["preview_url"] = lp_url
        record["rendered_message"] = message
        record["message_version"] = "ARI_MESSAGE_V1"
        return record

    lp_url = snap["preview_url"] if ab_arm == "C" else build_lp_url(
        company.get("industry_name", ""), company.get("area_name", "")
    )
    message = build_message_v2(
        company_name,
        website_url,
        lp_url,
        snap.get("message_observations") or [],
    )
    record["preview_token"] = snap.get("token")
    record["preview_url"] = lp_url
    record["candidate_id"] = snap.get("candidate_id") or _local_candidate_id()
    record["observations"] = [
        {
            "code": o.get("code"),
            "approved_copy": o.get("approved_copy") or o.get("copy"),
        }
        for o in (snap.get("message_observations") or [])
    ]
    record["rendered_message"] = message
    return record


def preview_v2(company: dict, *, ab_arm: str = "C", as_json: bool = False) -> None:
    """Console preview for V2 / preview funnel (dry-run only)."""
    import json as _json

    record = build_preview_record(company, ab_arm=ab_arm, dry_run_snapshot=True)
    if as_json:
        print(_json.dumps(record, ensure_ascii=False, indent=2))
        return

    print(f"{'─'*60}")
    print(f"  [V2 PREVIEW] {record['company']}")
    print(f"  domain: {record['domain']}")
    print(f"  url: {record['url']}")
    print(f"  industry: {record['industry']} ({record['industry_source']})")
    print(f"  ab_arm: {record['ab_arm']}  version: {record['message_version']}")
    if record.get("fallback"):
        print(f"  ⚠ fallback: {record['fallback_reason']}")
    if record.get("preview_token"):
        print(f"  preview_token: {record['preview_token']}")
    print(f"  preview_url: {record['preview_url']}")
    for obs in record.get("observations") or []:
        print(f"  observation: {obs.get('code')}")
        print(f"    copy: {obs.get('approved_copy')}")
    print(f"  文字数: {len(record['rendered_message'])} 字")
    print(f"{'─'*60}")
    print(record["rendered_message"])
    print()


def preview(company: dict, *, message_version: str = "v1") -> None:
    """
    company dict の内容をもとに送信予定の文面をコンソールに表示する（dry-run 用）。
    """
    if message_version == "v2":
        preview_v2(company, ab_arm="C")
        return
    lp_url, message = build_message_for_company(company)

    print(f"{'─'*60}")
    print(f"  宛先: {company['company_name']}")
    print(f"  業種: {company['industry_name']}  /  エリア: {company['area_name']}")
    print(f"  LP URL: {lp_url}")
    print(f"  文字数: {len(message)} 字")
    print(f"{'─'*60}")
    print(message)
    print()


# ─── --preview モード ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from parser import parse_md_file

    ap = argparse.ArgumentParser(description="文面プレビュー")
    ap.add_argument("--preview", metavar="FILE", help="MDファイルを読み込んで全件の文面をプレビュー")
    ap.add_argument("--limit", type=int, default=3, metavar="N", help="プレビュー件数（デフォルト: 3）")
    ap.add_argument(
        "--message-version",
        choices=("v1", "v2"),
        default="v1",
        help="v2 = ARI_MESSAGE_V2 + preview URL（--preview 専用・送信不可）",
    )
    ap.add_argument("--json", action="store_true", help="V2 preview を JSON 出力")
    args = ap.parse_args()

    if args.message_version == "v2" and not args.preview:
        print("⛔  --message-version v2 は --preview と併用時のみ許可されます。", file=sys.stderr)
        sys.exit(1)

    if args.preview:
        companies = parse_md_file(args.preview)
        targets = companies[: args.limit]
        print(f"\n全 {len(companies)} 件中、先頭 {len(targets)} 件をプレビュー [{args.message_version}]\n")
        for c in targets:
            if args.message_version == "v2":
                preview_v2(c, ab_arm="C", as_json=args.json)
            else:
                preview(c)
    else:
        ap.print_help()
