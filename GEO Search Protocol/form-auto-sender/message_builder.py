"""
message_builder.py  —  業種別文面生成モジュール

url_builder で生成した LP URL と templates/messages.py のテンプレートを組み合わせ、
送信用メッセージ文字列を返す。
"""

from __future__ import annotations

from url_builder import build_lp_url, get_industry_slug
from templates.messages import ARI_MESSAGE_V1

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
    area = (area_name or "").strip()
    area_context = f"{area}の{industry_keyword}" if area else industry_keyword

    return ARI_MESSAGE_V1.format(
        company_name=company_name,
        area_context=area_context,
        lp_url=lp_url,
    )


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


def preview(company: dict) -> None:
    """
    company dict の内容をもとに送信予定の文面をコンソールに表示する（dry-run 用）。
    """
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
    args = ap.parse_args()

    if args.preview:
        companies = parse_md_file(args.preview)
        targets = companies[: args.limit]
        print(f"\n全 {len(companies)} 件中、先頭 {len(targets)} 件をプレビュー\n")
        for c in targets:
            preview(c)
    else:
        ap.print_help()
