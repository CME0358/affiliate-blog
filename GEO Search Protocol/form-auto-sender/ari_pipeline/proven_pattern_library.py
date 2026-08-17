"""
ari_pipeline/proven_pattern_library.py — Proven Form Pattern Library (derived, read-only source).

Clusters historical CONFIRMED_SENT successes into reusable generic form classes.
Does NOT modify historical records.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from config import LOG_DIR, LOG_SENT, VAULT_ROOT
from ari_pipeline.sent_domain_index import get_sent_domain_index, normalize_domain
from inquiry_purpose_semantics import audit_selected_purpose

OUTPUT_DIR = VAULT_ROOT / "70_outputs/5-Day-Sales-Sprint"
LIBRARY_JSON = OUTPUT_DIR / "ARI-Proven-Form-Pattern-Library.json"
LIBRARY_MD = OUTPUT_DIR / "ARI Proven Form Pattern Library.md"

TIER_A = "TIER_A"
TIER_B = "TIER_B"
TIER_C = "TIER_C"
FAST_PATH_ELIGIBLE_TIERS = frozenset({TIER_A, TIER_B})

# Candidate classification outcomes
PROVEN_FAST_PATH = "PROVEN_FAST_PATH"
SLOW_PATH_REVIEW = "SLOW_PATH_REVIEW"
FORM_NOT_SUITABLE = "FORM_NOT_SUITABLE"
CAPTCHA_MANUAL = "CAPTCHA_MANUAL"
UNREACHABLE = "UNREACHABLE"
DUPLICATE_ALREADY_SENT = "DUPLICATE_ALREADY_SENT"
OTHER_SKIP = "OTHER_SKIP"

_STRONG_EVIDENCE = frozenset({
    "cf7_mail_sent",
    "cf7_mail_sent_ok",
    "wpcf7_mail_sent_ok",
    "mw_wp_form_complete_appeared",
    "mw_wp_form_state_to_complete",
    "mw_wp_form_complete_form_removed",
    "form_removed_with_success_dom",
    "post_response_success_body",
    "thanks_url_redirect",
    "success_message_in_dom",
    "success_heading_appeared",
    "aria_live_success",
})

_FRAMEWORK_URL_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("contact_form_7", ("wpcf7", "contact-form-7", "contactform7")),
    ("mw_wp_form", ("mwform", "mw_wp_form", "mw-wp-form")),
    ("formmail", ("formmail", "form.cgi", "mailform")),
    ("jimdo", ("jimdo", "jimdosite")),
    ("google_forms", ("docs.google.com/forms", "forms.gle")),
    ("hotpepper_external", ("hotpepper.jp",)),
    ("generic_contact_path", ("/contact", "/inquiry", "/otoiawase", "/form", "/info")),
)


@dataclass
class HistoricalSuccessRecord:
    domain: str
    company_name: str = ""
    form_url: str = ""
    success_evidence: str = ""
    form_type: str = ""
    framework: str = ""
    multistep_state: str = ""
    submit_pattern: str = ""
    inquiry_purpose_pattern: str = ""
    auto_reply: bool = False
    source: str = ""
    confirmed_at: str = ""


@dataclass
class ProvenPattern:
    pattern_id: str
    tier: str
    framework: str
    form_structure: str
    submit_control_pattern: str
    success_detection_pattern: str
    multistep_behavior: str
    inquiry_purpose_pattern: str
    typical_selectors: list[str] = field(default_factory=list)
    domain_count: int = 0
    sample_domains: list[str] = field(default_factory=list)
    auto_reply_domains: list[str] = field(default_factory=list)
    success_evidence_types: list[str] = field(default_factory=list)
    known_failure_conditions: list[str] = field(default_factory=list)
    fast_path_eligible: bool = False
    minimum_support_met: bool = False


def normalize_success_evidence(raw: str) -> str:
    s = (raw or "").strip().lower()
    if not s:
        return "unknown"
    if "wpcf7" in s or "cf7" in s or "mail_sent" in s:
        return "cf7_mail_sent"
    if "mw_wp_form" in s or "mwform" in s:
        return "mw_wp_form_complete"
    if "thanks" in s or "complete" in s and "url" in s:
        return "thanks_url_redirect"
    if "form_removed" in s:
        return "form_removed_with_success_dom"
    if "post_response" in s:
        return "post_response_success_body"
    if "success_message" in s or "success_heading" in s:
        return "success_message_in_dom"
    if "aria_live" in s:
        return "aria_live_success"
    return s.split()[0] if s else "unknown"


def infer_framework_from_signals(*, form_url: str = "", html_hint: str = "", submit_pattern: str = "") -> str:
    blob = f"{form_url} {html_hint} {submit_pattern}".lower()
    for fw, markers in _FRAMEWORK_URL_MARKERS:
        if any(m in blob for m in markers):
            return fw
    if "/contact" in blob or "お問い合わせ" in blob:
        return "generic_contact_path"
    return "generic_html_form"


def infer_form_structure(form_type: str, multistep_state: str) -> str:
    ft = (form_type or "").lower()
    ms = (multistep_state or "").upper()
    if ms in ("CONFIRMATION", "FINAL_SUBMIT_READY"):
        return "multi_step_confirm"
    if ft == "multi_step" or ms:
        return "multi_step"
    if ft == "single_step":
        return "single_step"
    return "unknown"


def _pattern_cluster_key(rec: HistoricalSuccessRecord) -> str:
    parts = [
        rec.framework or "generic_html_form",
        infer_form_structure(rec.form_type, rec.multistep_state),
        normalize_success_evidence(rec.success_evidence),
        rec.multistep_state or "none",
        rec.submit_pattern or "generic_submit",
    ]
    return "|".join(parts)


def _pattern_id_from_key(key: str) -> str:
    return "PAT-" + hashlib.sha256(key.encode()).hexdigest()[:12]


def assign_tier(
    *,
    domain_count: int,
    auto_reply_count: int,
    success_evidence: str,
    has_strong_external: bool = False,
) -> str:
    norm = normalize_success_evidence(success_evidence)
    strong_internal = norm in _STRONG_EVIDENCE

    if auto_reply_count >= 1 or has_strong_external:
        return TIER_A
    if domain_count >= 2 and strong_internal:
        return TIER_A
    if domain_count >= 2:
        return TIER_B
    if strong_internal:
        return TIER_B
    return TIER_C


def minimum_pattern_support_met(*, tier: str, domain_count: int, auto_reply_count: int) -> bool:
    if tier == TIER_C:
        return False
    if auto_reply_count >= 1:
        return True
    return domain_count >= 2


def parse_daily_logs(log_dir: Path | None = None) -> dict[str, dict[str, str]]:
    """Extract domain → {form_url, company_name} from daily markdown logs."""
    log_dir = log_dir or LOG_DIR
    out: dict[str, dict[str, str]] = {}
    form_re = re.compile(r"^- フォーム:\s*(.+)$", re.MULTILINE)
    for md in sorted(log_dir.glob("2026-*.md")):
        text = md.read_text(encoding="utf-8", errors="replace")
        sections = re.split(r"\n---+\n", text)
        for sec in sections:
            if "送信済み" not in sec and "✅" not in sec:
                continue
            m_name = re.search(r"^###\s+(.+)$", sec, re.MULTILINE)
            m_form = form_re.search(sec)
            if not m_form:
                continue
            form_url = m_form.group(1).strip()
            dom = normalize_domain(form_url)
            if not dom:
                continue
            out[dom] = {
                "form_url": form_url,
                "company_name": (m_name.group(1).strip() if m_name else ""),
                "log_date": md.stem,
            }
    return out


def _load_conversion_auto_reply() -> set[str]:
    path = LOG_DIR / "ari_conversion_tracking.csv"
    if not path.exists():
        return set()
    out: set[str] = set()
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("reply_classification") or "").upper() == "AUTO_REPLY":
                dom = (row.get("domain") or "").strip().lower()
                if dom:
                    out.add(dom)
    return out


def _load_batch_success_records() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for path in sorted(OUTPUT_DIR.glob("*Results*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for key in ("results", "prior_results", "resumed_results", "final4_results", "historical_results"):
            for row in data.get(key) or []:
                if row.get("submission_state") != "CONFIRMED_SENT":
                    continue
                dom = (row.get("domain") or "").strip().lower()
                if not dom:
                    continue
                out[dom] = {
                    "success_evidence": row.get("success_evidence_type") or row.get("reason") or "",
                    "form_url": row.get("form_url") or "",
                    "company_name": row.get("company") or "",
                    "source": path.name,
                }
    return out


def _load_preflight_by_domain() -> dict[str, dict]:
    cp = LOG_DIR / "ari_checkpoints" / "full_preflight_2026-08-12.json"
    if not cp.exists():
        return {}
    data = json.loads(cp.read_text(encoding="utf-8"))
    results = data.get("results") or {}
    if isinstance(results, dict):
        return {r.get("domain", ""): r for r in results.values() if r.get("domain")}
    return {r.get("domain", ""): r for r in results if r.get("domain")}


def audit_historical_successes() -> dict[str, Any]:
    """Build derived success records from canonical CONFIRMED_SENT domains."""
    get_sent_domain_index.cache_clear()
    idx = get_sent_domain_index()
    confirmed = sorted(idx.confirmed_domains)

    daily = parse_daily_logs()
    batch = _load_batch_success_records()
    auto_reply = _load_conversion_auto_reply()
    preflight = _load_preflight_by_domain()

    sent_rows: dict[str, dict] = {}
    if LOG_SENT.exists():
        with LOG_SENT.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                dom = normalize_domain(row.get("website_url", ""))
                if dom and dom not in sent_rows:
                    sent_rows[dom] = row

    records: list[HistoricalSuccessRecord] = []
    for dom in confirmed:
        sr = sent_rows.get(dom, {})
        dl = daily.get(dom, {})
        br = batch.get(dom, {})
        pf = preflight.get(dom, {})
        fn = pf.get("fill_no_submit") or {}
        le = pf.get("lightweight_evidence") or {}

        form_url = br.get("form_url") or dl.get("form_url") or sr.get("form_url") or pf.get("form_url") or ""
        success_ev = br.get("success_evidence") or ""
        submit_pat = (le.get("submit_label") or fn.get("final_submit_label") or "")

        rec = HistoricalSuccessRecord(
            domain=dom,
            company_name=br.get("company_name") or dl.get("company_name") or sr.get("company_name") or pf.get("company_name") or "",
            form_url=form_url,
            success_evidence=success_ev,
            form_type=pf.get("form_type") or le.get("form_type") or "",
            framework=infer_framework_from_signals(form_url=form_url, submit_pattern=submit_pat),
            multistep_state=fn.get("multistep_state") or "",
            submit_pattern=submit_pat or "generic_submit",
            inquiry_purpose_pattern="compatible_or_none",
            auto_reply=dom in auto_reply,
            source=br.get("source") or ("daily_log" if dom in daily else "sent_index"),
            confirmed_at=sr.get("date") or dl.get("log_date") or "",
        )
        records.append(rec)

    clusters: dict[str, list[HistoricalSuccessRecord]] = defaultdict(list)
    for rec in records:
        clusters[_pattern_cluster_key(rec)].append(rec)

    patterns: list[ProvenPattern] = []
    for key, members in sorted(clusters.items(), key=lambda x: -len(x[1])):
        fw = Counter(m.framework for m in members).most_common(1)[0][0]
        se = Counter(normalize_success_evidence(m.success_evidence) for m in members).most_common(1)[0][0]
        fs = Counter(infer_form_structure(m.form_type, m.multistep_state) for m in members).most_common(1)[0][0]
        ms = Counter(m.multistep_state or "none" for m in members).most_common(1)[0][0]
        sp = Counter(m.submit_pattern or "generic_submit" for m in members).most_common(1)[0][0]
        ar_domains = [m.domain for m in members if m.auto_reply]
        tier = assign_tier(
            domain_count=len(members),
            auto_reply_count=len(ar_domains),
            success_evidence=se,
        )
        min_ok = minimum_pattern_support_met(tier=tier, domain_count=len(members), auto_reply_count=len(ar_domains))
        patterns.append(ProvenPattern(
            pattern_id=_pattern_id_from_key(key),
            tier=tier,
            framework=fw,
            form_structure=fs,
            submit_control_pattern=sp,
            success_detection_pattern=se,
            multistep_behavior=ms,
            inquiry_purpose_pattern="compatible_or_none",
            typical_selectors=_typical_selectors_for_framework(fw),
            domain_count=len(members),
            sample_domains=[m.domain for m in members[:8]],
            auto_reply_domains=ar_domains[:8],
            success_evidence_types=sorted({normalize_success_evidence(m.success_evidence) for m in members if m.success_evidence}),
            known_failure_conditions=[],
            fast_path_eligible=tier in FAST_PATH_ELIGIBLE_TIERS and min_ok,
            minimum_support_met=min_ok,
        ))

    tier_counts = Counter(p.tier for p in patterns)
    fast_eligible = [p for p in patterns if p.fast_path_eligible]
    domains_ab = set()
    for p in fast_eligible:
        domains_ab.update(p.sample_domains)

    return {
        "generated_at": datetime.now().isoformat(),
        "effective_confirmed_sent_baseline": len(confirmed),
        "successes_audited": len(records),
        "auto_reply_domains": sorted(auto_reply),
        "patterns_extracted": len(patterns),
        "tier_a_count": tier_counts.get(TIER_A, 0),
        "tier_b_count": tier_counts.get(TIER_B, 0),
        "tier_c_count": tier_counts.get(TIER_C, 0),
        "fast_path_eligible_patterns": len(fast_eligible),
        "domains_covered_tier_ab": len(domains_ab),
        "top_frameworks": dict(Counter(p.framework for p in patterns).most_common(15)),
        "top_success_evidence": dict(Counter(p.success_detection_pattern for p in patterns).most_common(15)),
        "records": [asdict(r) for r in records],
        "patterns": [asdict(p) for p in patterns],
    }


def _typical_selectors_for_framework(framework: str) -> list[str]:
    mapping = {
        "contact_form_7": ["form.wpcf7-form", ".wpcf7-submit", ".wpcf7-mail-sent-ok"],
        "mw_wp_form": ["form.mw_wp_form", ".mwform-submit", ".mw_wp_form_complete"],
        "formmail": ["form[action*='formmail']", "input[type='submit']"],
        "jimdo": ["form.contact-form", "button[type='submit']"],
        "generic_contact_path": ["form", "input[type='submit']", "button[type='submit']"],
    }
    return mapping.get(framework, ["form", "input[type='submit']"])


def load_pattern_library(path: Path | None = None) -> dict[str, Any]:
    p = path or LIBRARY_JSON
    if not p.exists():
        return audit_historical_successes()
    return json.loads(p.read_text(encoding="utf-8"))


def write_pattern_library(audit: dict[str, Any] | None = None) -> tuple[Path, Path]:
    audit = audit or audit_historical_successes()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LIBRARY_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# ARI Proven Form Pattern Library",
        "",
        f"Generated: {audit['generated_at']}",
        "",
        "## Summary",
        f"- Effective CONFIRMED_SENT audited: **{audit['successes_audited']}**",
        f"- Patterns extracted: **{audit['patterns_extracted']}**",
        f"- Tier A: **{audit['tier_a_count']}** | Tier B: **{audit['tier_b_count']}** | Tier C: **{audit['tier_c_count']}**",
        f"- Fast Path eligible patterns: **{audit['fast_path_eligible_patterns']}**",
        f"- AUTO_REPLY-supported domains: **{len(audit.get('auto_reply_domains') or [])}**",
        "",
        "## Top Frameworks",
    ]
    for fw, cnt in (audit.get("top_frameworks") or {}).items():
        lines.append(f"- {fw}: {cnt}")
    lines.extend(["", "## Fast Path Eligible Patterns", ""])
    for p in audit.get("patterns") or []:
        if not p.get("fast_path_eligible"):
            continue
        lines.append(
            f"### {p['pattern_id']} ({p['tier']}) — {p['framework']} / {p['form_structure']}\n"
            f"- domains: {p['domain_count']} | success: {p['success_detection_pattern']}\n"
            f"- samples: {', '.join(p.get('sample_domains') or [])[:5]}"
        )
    LIBRARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return LIBRARY_JSON, LIBRARY_MD


def has_detection_evidence(candidate: dict) -> bool:
    """Fast Path requires offline detect/preflight evidence — not URL guess alone."""
    fn = candidate.get("fill_no_submit") or {}
    le = candidate.get("lightweight_evidence") or {}
    form_url = (candidate.get("form_url") or le.get("form_url") or "").strip()
    if fn:
        return True
    if form_url and le.get("field_map"):
        return True
    if candidate.get("preflight_classification") == "AUTO_READY":
        return True
    return False


def candidate_structural_signature(candidate: dict) -> dict[str, str] | None:
    if not has_detection_evidence(candidate):
        return None
    form_url = candidate.get("form_url") or (candidate.get("lightweight_evidence") or {}).get("form_url") or ""
    fn = candidate.get("fill_no_submit") or {}
    le = candidate.get("lightweight_evidence") or {}
    submit_pat = le.get("submit_label") or fn.get("final_submit_label") or ""
    fw = infer_framework_from_signals(form_url=form_url, submit_pattern=submit_pat)
    form_type = candidate.get("form_type") or le.get("form_type") or ""
    ms = fn.get("multistep_state") or ""
    return {
        "framework": fw,
        "form_structure": infer_form_structure(form_type, ms),
        "multistep_behavior": ms or "none",
        "submit_pattern": submit_pat or "generic_submit",
        "form_type": form_type or "unknown",
    }


def match_proven_pattern(candidate: dict, library: dict[str, Any] | None = None) -> dict[str, Any] | None:
    library = library or load_pattern_library()
    sig = candidate_structural_signature(candidate)
    if sig is None:
        return None
    patterns = [p for p in (library.get("patterns") or []) if p.get("fast_path_eligible")]
    if not patterns:
        return None

    best: dict[str, Any] | None = None
    best_score = -1
    for p in patterns:
        score = 0
        if p.get("framework") == sig["framework"]:
            score += 3
        if p.get("form_structure") == sig["form_structure"]:
            score += 2
        if p.get("multistep_behavior") == sig["multistep_behavior"]:
            score += 1
        if score > best_score:
            best_score = score
            best = {
                "matched_pattern_id": p["pattern_id"],
                "pattern_tier": p["tier"],
                "similarity_score": score,
                "framework": sig["framework"],
                "submit_pattern": sig["submit_pattern"],
                "success_evidence_lineage": p.get("success_detection_pattern"),
                "equivalence_evidence": {
                    "candidate_framework": sig["framework"],
                    "pattern_framework": p.get("framework"),
                    "candidate_structure": sig["form_structure"],
                    "pattern_structure": p.get("form_structure"),
                },
            }
    if best is None or best["similarity_score"] < 3:
        return None
    return best


def inquiry_purpose_compatible(candidate: dict) -> tuple[bool, str]:
    fn = candidate.get("fill_no_submit") or {}
    rc = fn.get("required_choices") or {}
    unsuitable = rc.get("unsuitable") or fn.get("unsuitable_required_labels") or []
    if unsuitable:
        return False, "incompatible_required_choices"
    for choice in rc.get("choices") or []:
        label = choice.get("label") or choice.get("value") or ""
        cat = choice.get("category") or "INQUIRY_CATEGORY"
        if audit_selected_purpose(label, context=choice.get("context") or "", category=cat) == "INCOMPATIBLE":
            return False, "incompatible_inquiry_purpose_only"
    return True, ""


def is_terminal_eligible_auto_ready(candidate: dict, refresh_row: dict | None = None) -> bool:
    """AUTO_READY + REFRESH_READY + compatible semantic evidence → production-cleared."""
    if candidate.get("preflight_classification") != "AUTO_READY":
        return False
    if not refresh_row or refresh_row.get("refresh_outcome") != "REFRESH_READY":
        return False
    sem = refresh_row.get("semantic_evidence_v2") or {}
    if not sem.get("canonical_snapshot", {}).get("submit_target"):
        return False
    return True


def classify_candidate(
    candidate: dict,
    *,
    library: dict[str, Any] | None = None,
    sent_index=None,
    excluded_domains: frozenset[str] | None = None,
    refresh_row: dict | None = None,
) -> dict[str, Any]:
    library = library or load_pattern_library()
    dom = (candidate.get("domain") or normalize_domain(candidate.get("website_url") or "")).lower()
    if sent_index is None:
        get_sent_domain_index.cache_clear()
        sent_index = get_sent_domain_index()

    if sent_index.should_no_resend(dom):
        return {"classification": DUPLICATE_ALREADY_SENT, "domain": dom, "reason": "effective_confirmed_sent"}
    if excluded_domains and dom in excluded_domains:
        return {"classification": OTHER_SKIP, "domain": dom, "reason": "canonical_excluded"}

    fn = candidate.get("fill_no_submit") or {}
    if fn.get("captcha_detected") or candidate.get("preflight_outcome") == "CAPTCHA_MANUAL":
        return {"classification": CAPTCHA_MANUAL, "domain": dom, "reason": "captcha_detected"}
    if fn.get("form_not_suitable") or candidate.get("preflight_classification") == "FORM_NOT_SUITABLE":
        return {"classification": FORM_NOT_SUITABLE, "domain": dom, "reason": "form_not_suitable"}

    ok, why = inquiry_purpose_compatible(candidate)
    if not ok:
        return {"classification": FORM_NOT_SUITABLE, "domain": dom, "reason": why}

    match = match_proven_pattern(candidate, library)
    if match:
        return {
            "classification": PROVEN_FAST_PATH,
            "domain": dom,
            "matched_pattern_id": match["matched_pattern_id"],
            "pattern_tier": match["pattern_tier"],
            "similarity_score": match["similarity_score"],
            "framework": match["framework"],
            "submit_pattern": match["submit_pattern"],
            "success_evidence_lineage": match["success_evidence_lineage"],
            "equivalence_evidence": match["equivalence_evidence"],
            "fast_path_basis": "proven_pattern_match",
        }

    if is_terminal_eligible_auto_ready(candidate, refresh_row):
        sig = candidate_structural_signature(candidate) or {}
        return {
            "classification": PROVEN_FAST_PATH,
            "domain": dom,
            "matched_pattern_id": "AUTO_READY_REFRESH_CLEARED",
            "pattern_tier": TIER_B,
            "similarity_score": 0,
            "framework": sig.get("framework", "generic_html_form"),
            "submit_pattern": sig.get("submit_pattern", "generic_submit"),
            "success_evidence_lineage": "auto_ready_semantic_refresh",
            "equivalence_evidence": {"basis": "AUTO_READY_REFRESH_READY"},
            "fast_path_basis": "auto_ready_refresh_cleared",
        }

    return {"classification": SLOW_PATH_REVIEW, "domain": dom, "reason": "no_proven_pattern_match"}
