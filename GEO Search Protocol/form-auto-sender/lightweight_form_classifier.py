"""Lightweight classification + scoring from detect_form_only results (no fill/submit)."""

from __future__ import annotations

LIKELY_AUTO_READY = "LIKELY_AUTO_READY"
PREFLIGHT_CANDIDATE = "PREFLIGHT_CANDIDATE"
LIKELY_NOT_READY = "LIKELY_NOT_READY"
LW_MANUAL_INTERVENTION = "MANUAL_INTERVENTION"
LW_FORM_NOT_SUITABLE = "FORM_NOT_SUITABLE"

# Preflight へ進める lightweight 候補
PREFLIGHT_BOUNDARY = frozenset({LIKELY_AUTO_READY, PREFLIGHT_CANDIDATE})

LARGE_LAW_MARKERS = (
    "弁護士会",
    "法律事務所法人",
    "紹介エージェント",
    "bengo4.com",
)
LARGE_REVIEW_THRESHOLD = 250

PRIORITY_A1_KEYWORDS = (
    "リフォーム", "外壁塗装", "屋根工事", "工務", "建築", "住宅", "リノベ", "塗装",
)
PRIORITY_A2_KEYWORDS = ("不動産",)
PRIORITY_B_KEYWORDS = ("税理士", "会計士", "行政書士", "司法書士")

REAL_ESTATE_CHAIN_MARKERS = (
    "リバブル", "野村", "東急", "住友", "三井", "みずほ", "大京", "ニッショー",
)

PROVEN_AREAS = ("東京都台東区", "東京都足立区")


def segment_bucket(industry: str, company_name: str, review_count: int) -> str:
    ind = industry or ""
    name = company_name or ""
    if any(k in ind for k in PRIORITY_A1_KEYWORDS):
        return "A1"
    if any(k in ind for k in PRIORITY_A2_KEYWORDS):
        if any(m in name for m in REAL_ESTATE_CHAIN_MARKERS):
            return "C"
        return "A2"
    if any(k in ind for k in PRIORITY_B_KEYWORDS):
        if review_count > LARGE_REVIEW_THRESHOLD:
            return "C"
        if any(m in name for m in LARGE_LAW_MARKERS):
            return "C"
        return "B"
    if "弁護士" in ind:
        return "C"
    return "C"


def is_proven_segment(company: dict) -> bool:
    area = (company.get("area_name") or "").strip()
    if area not in PROVEN_AREAS:
        return False
    return segment_bucket(
        company.get("industry_name", ""),
        company.get("company_name", ""),
        int(company.get("review_count") or 0),
    ) == "A1"


def _segment_tier(industry: str, company_name: str, review_count: int) -> str:
    b = segment_bucket(industry, company_name, review_count)
    if b == "A1":
        return "A"
    if b in ("A2", "B"):
        return "B" if b == "B" else "A"
    return "C"


def _form_url_present(det: dict) -> bool:
    return bool((det.get("form_url") or "").strip())


def _submit_signal(det: dict) -> bool:
    if det.get("submit_label"):
        return True
    form_type = (det.get("form_type") or "").upper()
    if form_type == "MULTI_STEP":
        return True
    html_hint = (det.get("failure_reason") or "").lower()
    if any(k in html_hint for k in ("confirm", "確認", "next", "次へ")):
        return True
    return False


def _form_presence(det: dict) -> bool:
    form_type = (det.get("form_type") or "").upper()
    if not _form_url_present(det):
        return False
    if form_type in ("FORM_FOUND", "MULTI_STEP"):
        return True
    if form_type in ("ERROR", "NO_FORM", "BLOCKED") and _form_url_present(det):
        return True
    return False


def classify_lightweight(det: dict) -> tuple[str, str, list[str]]:
    """
    Returns (classification, reject_reason, score_notes).

    軽量段階では email/message 完全検出を必須にしない。
    """
    notes: list[str] = []
    form_type = (det.get("form_type") or "ERROR").upper()
    captcha = bool(det.get("captcha"))
    fm = det.get("field_map") or {}
    failure = (det.get("failure_reason") or "").lower()
    ext = det.get("external_provider")

    if captcha or form_type == "CAPTCHA" or "recaptcha" in failure:
        return LW_MANUAL_INTERVENTION, "captcha_or_human_verification", notes

    if form_type in ("EXTERNAL_FORM", "CONTACT_PAGE_ONLY"):
        return LW_FORM_NOT_SUITABLE, f"external_or_non_contact:{ext or form_type}", notes

    if form_type == "LOGIN_REQUIRED":
        return LW_FORM_NOT_SUITABLE, "login_required", notes

    if ext:
        return LW_FORM_NOT_SUITABLE, f"external_provider:{ext}", notes

    if not _form_url_present(det):
        reason = det.get("failure_reason") or form_type or "no_form_url"
        if form_type in ("NO_FORM", "ERROR", "BLOCKED") or "timeout" in failure or "no_form" in failure:
            return LIKELY_NOT_READY, reason, notes
        return LIKELY_NOT_READY, reason, notes

    if not _form_presence(det):
        return LIKELY_NOT_READY, det.get("failure_reason") or "form_presence_unclear", notes

    email_ok = fm.get("email") == "FOUND"
    message_ok = fm.get("message") == "FOUND"
    name_ok = fm.get("name") == "FOUND"
    submit_ok = _submit_signal(det)
    confidence = det.get("confidence", "LOW")

    if not submit_ok:
        return LIKELY_NOT_READY, "no_submit_candidate", notes

    core_complete = email_ok and message_ok
    if core_complete and form_type in ("FORM_FOUND", "MULTI_STEP") and confidence in ("HIGH", "MEDIUM"):
        if name_ok or fm.get("phone") == "FOUND":
            return LIKELY_AUTO_READY, "", notes
        notes.append("core_fields_ok_name_phone_partial")

    if core_complete and confidence in ("HIGH", "MEDIUM"):
        return LIKELY_AUTO_READY, "", notes

    missing = []
    if not email_ok:
        missing.append("email")
    if not message_ok:
        missing.append("message")
    partial = ",".join(missing) if missing else "fields_partial"

    if form_type in ("FORM_FOUND", "MULTI_STEP") or _form_url_present(det):
        return PREFLIGHT_CANDIDATE, f"preflight_worthy:missing_{partial}", notes

    return LIKELY_NOT_READY, f"unsupported_structure:{form_type}", notes


def score_lightweight(det: dict, classification: str, company: dict | None = None) -> int:
    score = 0
    fm = det.get("field_map") or {}
    form_type = (det.get("form_type") or "").upper()
    company = company or {}

    if classification == LW_MANUAL_INTERVENTION:
        return -100
    if classification == LW_FORM_NOT_SUITABLE:
        return -80
    if classification == LIKELY_NOT_READY:
        return -20

    if fm.get("message") == "FOUND":
        score += 30
    elif classification == PREFLIGHT_CANDIDATE:
        score += 10
    if det.get("submit_label"):
        score += 20
    elif form_type == "MULTI_STEP":
        score += 12
    if form_type in ("FORM_FOUND", "MULTI_STEP"):
        score += 15
    core_found = sum(1 for k in ("name", "email", "phone") if fm.get(k) == "FOUND")
    if core_found >= 2:
        score += 10
    elif core_found == 1:
        score += 5
    if not det.get("captcha"):
        score += 10
    if det.get("confidence") == "HIGH":
        score += 10
    elif det.get("confidence") == "MEDIUM":
        score += 5

    if classification == LIKELY_AUTO_READY:
        score += 15
    elif classification == PREFLIGHT_CANDIDATE:
        score += 8

    tier = _segment_tier(
        company.get("industry_name", ""),
        company.get("company_name", ""),
        int(company.get("review_count") or 0),
    )
    if tier == "A":
        score += 25
    elif tier == "B":
        score += 10
    else:
        score -= 15

    if is_proven_segment(company):
        score += 20

    reviews = int(company.get("review_count") or 0)
    if reviews > LARGE_REVIEW_THRESHOLD:
        score -= 10

    return score


def pool_segment_score(company: dict) -> tuple[int, int]:
    bucket = segment_bucket(
        company.get("industry_name", ""),
        company.get("company_name", ""),
        int(company.get("review_count") or 0),
    )
    tier_score = {"A1": 400, "A2": 180, "B": 150, "C": 0}.get(bucket, 0)
    area_bonus = 80 if is_proven_segment(company) else 0
    reviews = int(company.get("review_count") or 0)
    if 3 <= reviews <= 80:
        review_bonus = 50
    elif reviews <= 150:
        review_bonus = 30
    elif reviews <= LARGE_REVIEW_THRESHOLD:
        review_bonus = 10
    else:
        review_bonus = -20
    return tier_score + area_bonus + review_bonus, reviews
