"""ARI Commercial Fit scoring for Controlled Pilot cohort selection (read-only)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

# PILOT POLICY EXCLUSION — not a judgment on long-term ARI demand.
HARD_EXCLUSION_INDUSTRY_KEYWORDS: tuple[str, ...] = (
    "不動産",
    "不動産仲介",
    "不動産売買",
    "賃貸",
    "住宅販売",
    "リフォーム",
    "工務店",
    "住宅リフォーム",
    "外壁塗装",
    "屋根工事",
    "防水工事",
    "雨漏り修理",
)

HARD_EXCLUSION_COMPANY_KEYWORDS: tuple[str, ...] = (
    "不動産",
    "賃貸",
    "リフォーム",
    "工務店",
    "外壁塗装",
    "屋根工事",
    "防水工事",
    "雨漏り",
)

P1_INDUSTRY_KEYWORDS: tuple[str, ...] = (
    "歯科",
    "歯医者",
    "矯正歯",
    "審美歯",
    "インプラント",
    "美容クリニック",
    "美容皮膚",
    "美容外科",
    "医療脱毛",
    "AGA",
    "自由診療",
    "ホワイトニング",
    "皮膚科",
    "形成外科",
    "再生医療",
)

P2_INDUSTRY_KEYWORDS: tuple[str, ...] = (
    "パーソナルジム",
    "ピラティス",
    "ヨガ",
    "エステ",
    "美容サロン",
    "整体",
    "整骨",
    "鍼灸",
    "税理士",
    "会計士",
    "弁護士",
    "司法書士",
    "社労士",
    "行政書士",
    "士業",
    "クリニック",
    "病院",
    "脱毛",
    "ジム",
    "フィットネス",
    "サロン",
    "カウンセリング",
    "結婚相談",
)

# Industry-level commercial characteristic baselines (max per component).
# No firm-specific revenue/LTV — industry + visible service category only.
_INDUSTRY_BASELINE: dict[str, dict[str, int]] = {
    "p1_dental": {"A": 24, "B": 18, "C": 14, "D": 14, "E": 9, "G": 5},
    "p1_cosmetic": {"A": 23, "B": 18, "C": 14, "D": 14, "E": 9, "G": 5},
    "p1_medical": {"A": 22, "B": 17, "C": 13, "D": 14, "E": 8, "G": 5},
    "p2_premium_local": {"A": 17, "B": 15, "C": 12, "D": 13, "E": 7, "G": 4},
    "p2_professional": {"A": 15, "B": 13, "C": 11, "D": 12, "E": 8, "G": 4},
    "p3_default": {"A": 10, "B": 10, "C": 8, "D": 9, "E": 6, "G": 3},
    "p3_auto_retail": {"A": 8, "B": 8, "C": 10, "D": 8, "E": 5, "G": 2},
    "p3_education": {"A": 9, "B": 9, "C": 9, "D": 8, "E": 5, "G": 3},
}

_BRANCH_MARKERS = ("支社", "支店", "営業所", "本部", "本社", "エリア", "事業部")
_CHAIN_DOMAIN_HINTS = ("co.jp/store", "stores.", "shop.", "branch")


@dataclass
class CommercialFitResult:
    domain: str
    company_name: str
    industry_name: str
    vertical_priority: str
    ari_commercial_fit_score: int
    score_breakdown: dict[str, int]
    exclusion_reason: str
    technical_ready: bool
    commercial_ready: bool
    commercial_fit_reason: str
    preview_url: str = ""
    preview_token: str = ""
    preview_status: str = ""
    cohort_role: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(k in text for k in keywords)


def classify_vertical_priority(industry_name: str, company_name: str = "") -> tuple[str, str]:
    """Return (priority, note)."""
    ind = (industry_name or "").strip()
    company = (company_name or "").strip()
    combined = f"{ind} {company}"

    if _contains_any(ind, HARD_EXCLUSION_INDUSTRY_KEYWORDS) or _contains_any(
        company, HARD_EXCLUSION_COMPANY_KEYWORDS
    ):
        return "EXCLUDED", "PILOT POLICY EXCLUSION: real estate / reform vertical"

    if _contains_any(ind, P1_INDUSTRY_KEYWORDS):
        if any(k in ind for k in ("歯科", "歯医者", "矯正", "審美", "インプラント", "ホワイトニング")):
            return "P1", "Tier 1 high-APR dental / aesthetic dental"
        return "P1", "Tier 1 high-APR cosmetic / medical clinic"

    if _contains_any(ind, P2_INDUSTRY_KEYWORDS):
        return "P2", "Tier 2 premium local / professional services"

    return "P3", "Other local service"


def _baseline_key(priority: str, industry_name: str) -> str:
    ind = industry_name or ""
    if priority == "P1":
        if any(k in ind for k in ("歯科", "歯医者", "矯正", "審美", "インプラント", "ホワイトニング")):
            return "p1_dental"
        return "p1_cosmetic"
    if priority == "P2":
        if any(k in ind for k in ("税理士", "会計", "弁護士", "司法書士", "社労士", "行政書士")):
            return "p2_professional"
        return "p2_premium_local"
    if any(k in ind for k in ("中古車", "車販売", "車検", "カーリース", "自動車")):
        return "p3_auto_retail"
    if any(k in ind for k in ("スクール", "塾", "英会話", "プログラミング", "保育")):
        return "p3_education"
    return "p3_default"


def _entity_domain_alignment(company_name: str, domain: str, website_url: str = "") -> tuple[int, str]:
    """Component F — max 10."""
    score = 10
    notes: list[str] = []
    company = (company_name or "").strip()
    domain = (domain or "").strip().lower()

    if any(m in company for m in _BRANCH_MARKERS):
        score -= 4
        notes.append("branch/corporate office label vs single-site outreach risk")

    if re.search(r"㈱|株式会社", company) and len(company) <= 8:
        score -= 1
        notes.append("generic corporate label")

    # Multi-location chain: domain may not match the marketed local entity.
    if any(k in company for k in ("院", "店", "サロン", "クリニック", "ジム", "スタジオ")):
        domain_tokens = re.sub(r"[^a-z0-9]", "", domain.split(".")[0])
        company_tokens = re.sub(r"[^a-z0-9]", "", company.lower())
        if domain_tokens and company_tokens and domain_tokens not in company_tokens:
            if len(domain_tokens) >= 4 and domain_tokens[:4] not in company_tokens:
                score -= 2
                notes.append("domain-brand vs local entity name mismatch")

    if website_url and any(h in website_url for h in _CHAIN_DOMAIN_HINTS):
        score -= 2
        notes.append("chain / store-path website pattern")

    score = max(0, min(10, score))
    return score, "; ".join(notes) if notes else "domain aligns with marketed local entity"


def score_commercial_fit(
    *,
    domain: str,
    company_name: str,
    industry_name: str,
    technical_ready: bool = True,
    website_url: str = "",
    preview_url: str = "",
    preview_token: str = "",
) -> CommercialFitResult:
    priority, priority_reason = classify_vertical_priority(industry_name, company_name)

    if priority == "EXCLUDED":
        return CommercialFitResult(
            domain=domain,
            company_name=company_name,
            industry_name=industry_name,
            vertical_priority="EXCLUDED",
            ari_commercial_fit_score=0,
            score_breakdown={"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0, "G": 0},
            exclusion_reason="PILOT POLICY EXCLUSION",
            technical_ready=technical_ready,
            commercial_ready=False,
            commercial_fit_reason=priority_reason,
            preview_url=preview_url,
            preview_token=preview_token,
            preview_status="PREVIEW_AVAILABLE" if preview_url else "PREVIEW_UNKNOWN",
        )

    baseline = _INDUSTRY_BASELINE[_baseline_key(priority, industry_name)]
    f_score, f_note = _entity_domain_alignment(company_name, domain, website_url)

    breakdown = {
        "A_revenue_recovery_potential": baseline["A"],
        "B_ai_discovery_relevance": baseline["B"],
        "C_comparison_intensity": baseline["C"],
        "D_digital_conversion_importance": baseline["D"],
        "E_commercial_ability_to_pay": baseline["E"],
        "F_entity_domain_alignment": f_score,
        "G_actionability": baseline["G"],
    }
    total = sum(breakdown.values())

    # Commercial ready: priority-weighted threshold (technical ready assumed).
    if priority == "P1":
        commercial_ready = total >= 70
    elif priority == "P2":
        commercial_ready = total >= 62
    else:
        commercial_ready = total >= 68  # high bar for P3 in conversion pilot

    reason_parts = [priority_reason, f_note]
    if priority == "P1":
        reason_parts.append("high-APR clinic vertical; strong AI comparison use case")
    elif priority == "P2":
        reason_parts.append("premium local / professional; comparison + booking economics")
    else:
        reason_parts.append("lower conversion economics for ¥29,800 report in this pilot")

    return CommercialFitResult(
        domain=domain,
        company_name=company_name,
        industry_name=industry_name,
        vertical_priority=priority,
        ari_commercial_fit_score=total,
        score_breakdown=breakdown,
        exclusion_reason="",
        technical_ready=technical_ready,
        commercial_ready=commercial_ready and technical_ready,
        commercial_fit_reason=" — ".join(reason_parts),
        preview_url=preview_url,
        preview_token=preview_token,
        preview_status="PREVIEW_AVAILABLE" if preview_url else "PREVIEW_REQUIRED",
    )


def rank_key(result: CommercialFitResult) -> tuple[int, int, str]:
    """Sort: non-excluded first, P1>P2>P3, score desc, domain asc."""
    if result.vertical_priority == "EXCLUDED":
        prio = 99
    elif result.vertical_priority == "P1":
        prio = 1
    elif result.vertical_priority == "P2":
        prio = 2
    else:
        prio = 3
    return (prio, -result.ari_commercial_fit_score, result.domain)


def is_dental(industry_name: str) -> bool:
    ind = industry_name or ""
    return any(k in ind for k in ("歯科", "歯医者", "矯正", "審美", "インプラント", "ホワイトニング"))


def is_cosmetic_clinic(industry_name: str) -> bool:
    ind = industry_name or ""
    return any(
        k in ind
        for k in ("美容クリニック", "美容皮膚", "美容外科", "医療脱毛", "AGA", "脱毛")
    ) and not is_dental(ind)


def is_other_high_apr_medical(industry_name: str) -> bool:
    ind = industry_name or ""
    if is_dental(ind) or is_cosmetic_clinic(ind):
        return False
    return any(k in ind for k in ("クリニック", "皮膚科", "自由診療", "形成外科", "再生医療"))
