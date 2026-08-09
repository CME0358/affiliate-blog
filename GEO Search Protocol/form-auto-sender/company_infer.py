"""
company_infer.py — sent.csv 等で業種・エリア未記録の行を会社名から補完
"""

from __future__ import annotations

import re

# 会社名に含まれる地名 → 区名（東京23区）
_AREA_HINTS: tuple[tuple[str, str], ...] = (
    ("新宿", "新宿区"),
    ("渋谷", "渋谷区"),
    ("池袋", "豊島区"),
    ("銀座", "中央区"),
    ("日本橋", "中央区"),
    ("恵比寿", "渋谷区"),
    ("代々木", "渋谷区"),
    ("表参道", "渋谷区"),
    ("六本木", "港区"),
    ("麻布", "港区"),
    ("赤坂", "港区"),
    ("青山", "港区"),
    ("上野", "台東区"),
    ("秋葉原", "千代田区"),
    ("神保町", "千代田区"),
    ("飯田橋", "千代田区"),
    ("大手町", "千代田区"),
    ("品川", "品川区"),
    ("目黒", "目黒区"),
    ("世田谷", "世田谷区"),
    ("中野", "中野区"),
    ("杉並", "杉並区"),
    ("練馬", "練馬区"),
    ("板橋", "板橋区"),
    ("文京", "文京区"),
)


def infer_industry_from_company_name(company_name: str) -> str:
    """会社名から業種名（url_builder / message_builder 用の日本語ラベル）を推定。"""
    n = company_name or ""
    if re.search(r"歯科|デンタル|矯正歯科|歯医者", n):
        return "歯科"
    if re.search(r"整骨|接骨|鍼灸|整体|カイロ|リラク|せいこつ", n, re.I):
        return "整体院"
    if re.search(r"皮膚科|美容クリニック|美容外科|ビューティ", n):
        return "美容クリニック"
    if re.search(r"動物病院|ペットクリニック|獣医", n):
        return "動物病院"
    return ""


def infer_area_from_company_name(company_name: str) -> str:
    """会社名に含まれる地名から区名を推定。"""
    n = company_name or ""
    for hint, ward in _AREA_HINTS:
        if hint in n:
            return ward
    m = re.search(r"(.+?区)", n)
    if m:
        return m.group(1)
    return ""


def enrich_company_metadata(company: dict) -> dict:
    """
    industry_name / area_name が空のとき会社名から補完する。
    既存値は上書きしない。
    """
    name = company.get("company_name") or ""
    if not (company.get("industry_name") or "").strip():
        inferred = infer_industry_from_company_name(name)
        if inferred:
            company["industry_name"] = inferred
    if not (company.get("area_name") or "").strip():
        inferred_area = infer_area_from_company_name(name)
        if inferred_area:
            company["area_name"] = inferred_area
    return company
