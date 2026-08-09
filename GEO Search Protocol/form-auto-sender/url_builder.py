"""
url_builder.py  —  LP URL 動的生成モジュール

業種名（日本語）× エリア名（区名）→ aiscan.coaretail.com の URL を生成する。
"""

from __future__ import annotations

BASE_URL = "https://aiscan.coaretail.com"

INDUSTRY_SLUG_MAP: dict[str, str] = {
    "美容クリニック":               "beauty-clinic",
    "飲食店":                       "restaurant",
    "求人・採用":                   "hr",
    "税理士・会計士":               "accountant",
    "歯科クリニック":               "dental",
    "歯科・歯医者":                 "dental",
    "ホワイトニング・審美歯科":   "dental-cosmetic",
    "パーソナルジム":               "gym",
    "エステサロン":                 "esthetic",
    "美容院・ヘアサロン":           "hair-salon",
    "ネイルサロン":                 "nail-salon",
    "医療脱毛・エステ脱毛":         "hair-removal",
    "AGA・薄毛治療":                "aga",
    "整体院・整骨院":               "seitai",
    "整体院・整骨院・鍼灸院":       "seitai",
    "外壁塗装・屋根工事":           "exterior-painting",
    "不動産売却・査定":             "realestate",
    "不動産会社":                   "realestate",
    "注文住宅・ハウスメーカー":     "housing",
    "リフォーム・リノベーション":   "reform",
    "転職エージェント":             "career",
    "プログラミングスクール":       "programming",
    "弁護士事務所":                 "lawyer-general",
    "水道修理・鍵開け緊急サービス": "emergency",
    "結婚式場・葬儀社":             "ceremony",
    "中古車買取":                   "car-buy",
    "BtoB SaaS・業務システム":      "saas",
    "Web制作・マーケティング支援":  "web-agency",
    "MEO対策":                      "meo",
    "SEO対策":                      "seo",
    "司法書士・社労士・行政書士":   "lawyer",
    "AI検索診断":                   "shindan",
    "皮膚科・アトピークリニック":   "dermatology",
    "心療内科・精神科クリニック":   "psychiatry",
    "整形外科・スポーツ整体":       "orthopedics",
    "不妊治療クリニック":           "fertility",
    "ダイエット外来・肥満外科":     "diet-clinic",
    "眼科・レーシック・ICL":        "eyeclinic",
    "学習塾・個別指導塾":           "childcare",
    "予備校・大学受験対策":         "cram-school",
    "オンライン英会話・語学スクール": "online-school",
    "保育園・託児所":               "nursery",
    "ペットホテル・トリミング":     "pet-hotel",
    "動物病院・ペットクリニック":   "pet-clinic",
    "葬儀・斎場":                   "funeral",
    "遺品整理・相続手続き代行":     "inheritance",
    "保険代理店・FP相談":           "insurance",
    "カーリース・車販売":           "car-lease",
    "中古車販売":                   "used-car-buy",
    "引越し業者・単身引越し":       "moving",
    "トランクルーム・収納サービス": "storage",
    "ハウスクリーニング・エアコン清掃": "cleaning",
    "害虫駆除・シロアリ対策":       "pest-control",
    "インテリアコーディネート・家具": "interior",
    "食材宅配・ミールキット":       "meal-kit",
    "人材派遣・スタッフィング":     "temp-agency",
    "離婚専門弁護士・調停サポート": "divorce-law",
}

WARD_SLUG_MAP: dict[str, str] = {
    "千代田区": "chiyoda",   "中央区":  "chuo",      "港区":    "minato",
    "新宿区":   "shinjuku",  "文京区":  "bunkyo",    "台東区":  "taito",
    "墨田区":   "sumida",    "江東区":  "koto",      "品川区":  "shinagawa",
    "目黒区":   "meguro",    "大田区":  "ota",       "世田谷区": "setagaya",
    "渋谷区":   "shibuya",   "中野区":  "nakano",    "杉並区":  "suginami",
    "豊島区":   "toshima",   "北区":    "kita",      "荒川区":  "arakawa",
    "板橋区":   "itabashi",  "練馬区":  "nerima",    "足立区":  "adachi",
    "葛飾区":   "katsushika","江戸川区": "edogawa",
}


def _fuzzy_slug(industry_name: str) -> str | None:
    """
    完全一致しない場合に部分一致でスラッグを探す。
    例: "整骨院" → "整体院・整骨院" にマッチ → "seitai"
        "歯科"  → "歯科クリニック" にマッチ → "dental"
    """
    industry_name = (industry_name or "").strip()
    if not industry_name:
        return None
    for key, slug in INDUSTRY_SLUG_MAP.items():
        if industry_name in key or key in industry_name:
            return slug
    return None


def build_lp_url(industry_name: str, area_name: str) -> str:
    """
    業種名とエリア名から LP URL を生成する。

    config.LP_URL_OVERRIDE が非空のときは常にそのURL（一時措置）。

    通常時の優先順位:
    1. 完全一致 → スラッグ確定
    2. 部分一致（スクレイパーの略称対応）→ スラッグ確定
    3. 東京23区 → /area/tokyo/{ward_slug}/
    4. 業種のみ（23区外）→ /{industry_slug}/
    5. 業種不明 → BASE_URL/（フォールバック）
    """
    from config import LP_URL_OVERRIDE

    fixed = (LP_URL_OVERRIDE or "").strip()
    if fixed:
        return fixed

    industry_slug = INDUSTRY_SLUG_MAP.get(industry_name) or _fuzzy_slug(industry_name)
    ward_slug = WARD_SLUG_MAP.get(area_name)

    if not industry_slug:
        return f"{BASE_URL}/"

    if ward_slug:
        return f"{BASE_URL}/area/tokyo/{ward_slug}/"

    return f"{BASE_URL}/{industry_slug}/"


def get_industry_slug(industry_name: str) -> str | None:
    """業種名から slug を返す（部分一致フォールバックあり）。未登録の場合は None。"""
    return INDUSTRY_SLUG_MAP.get(industry_name) or _fuzzy_slug(industry_name)
