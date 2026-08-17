"""
r2_industry_filter.py — Dental / esthetic industry classification for R2 supply.
"""

from __future__ import annotations

from typing import Literal

R2Industry = Literal["dental", "esthetic"]

REMODEL_EXCLUDE_KWS = (
    "リフォーム", "外壁", "塗装", "工務店", "建築", "住宅", "リノベ", "屋根", "外構",
    "塗装", "リノベーション", "ハウスメーカー", "注文住宅", "建設", "改修", "修繕",
    "外壁塗装", "屋根工事", "内装", "解体",
)

DENTAL_KWS = (
    "歯科", "デンタル", "矯正歯科", "審美歯科", "インプラント", "ホワイトニング",
    "歯医者", "歯科・歯医者", "小児歯科", "予防歯科",
)

ESTHETIC_KWS = (
    "エステ", "エステサロン", "beauty salon", "facial", "ボディ", "脱毛",
    "美容クリニック", "皮膚科", "医療脱毛", "痩身", "ネイルサロン",
)

# Unrelated medical — exclude unless clearly esthetic/dental context
UNRELATED_MEDICAL_KWS = (
    "整骨", "接骨", "鍼灸", "整体", "心療内科", "精神科", "内科", "外科",
    "産婦人科", "小児科", "眼科", "耳鼻", "泌尿器", "循環器", "不妊",
)

RECRUITMENT_KWS = ("採用", "求人", "リクルート", "recruit")
SUPPORT_ONLY_KWS = ("サポート専用", "カスタマーサポート", "ヘルプデスク", "患者様専用", "会員専用")


def is_remodel_industry(industry: str) -> bool:
    ind = industry or ""
    return any(k in ind for k in REMODEL_EXCLUDE_KWS)


def classify_r2_industry(industry: str) -> R2Industry | None:
    ind = industry or ""
    if is_remodel_industry(ind):
        return None
    if any(k in ind for k in UNRELATED_MEDICAL_KWS):
        return None
    if any(k in ind for k in DENTAL_KWS):
        return "dental"
    if any(k in ind for k in ESTHETIC_KWS):
        return "esthetic"
    return None


def is_r2_eligible_industry(industry: str) -> bool:
    return classify_r2_industry(industry) is not None


def industry_name_excluded_by_keywords(industry: str, company_name: str = "") -> str:
    blob = f"{industry} {company_name}"
    if any(k in blob for k in RECRUITMENT_KWS):
        return "recruitment_only"
    if any(k in blob for k in SUPPORT_ONLY_KWS):
        return "support_only"
    return ""
