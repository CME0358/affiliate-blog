"""
submit_target_semantics.py — Generic semantic submit-target disambiguation.

Prefers semantic identity over positional heuristics. Fail-closed on true ambiguity.
"""

from __future__ import annotations

import re
from typing import Any

from form_fill_no_submit import (
    BACK,
    FINAL_SUBMIT,
    NEXT_STEP_SAFE,
    UNKNOWN,
    classify_button_action,
)
from multistep_state import CONFIRMATION, FINAL_SUBMIT_READY, FORM_ENTRY

RESOLUTION_UNIQUE = "UNIQUE_HIGH_CONFIDENCE"
RESOLUTION_EQUIVALENT = "MULTIPLE_EQUIVALENT_TARGETS"
RESOLUTION_AMBIGUOUS = "TRUE_AMBIGUITY"

_AUXILIARY_LABEL_FRAGMENTS = (
    "住所検索",
    "zip2addr",
    "自動住所",
    "自動入力",
    "住所の自動入力",
    "郵便番号から",
    "search",
)

_DISTINCTIVE_SUBMIT_CLASSES = (
    "wpcf7-submit",
    "wpcf7-confirm",
    "wpcf7c-btn-confirm",
    "mwform-submit",
    "form_submit",
    "btn-submit",
)

_NAMED_SUBMIT_RE = re.compile(
    r"^(?:form(?:\[[^\]]+\]|#[^\s]+)?\s+)?(?P<tag>input|button)\[name=\"(?P<name>[^\"]+)\"\]$",
    re.I,
)
_TYPED_SUBMIT_RE = re.compile(
    r"^(?:form(?:\[[^\]]+\]|#[^\s]+)?\s+)?(?P<tag>input|button)\[type=\"(?P<type>[^\"]+)\"\]$",
    re.I,
)
_ID_SUBMIT_RE = re.compile(r"(?:^|\s)#(?P<id>[^\s]+)$", re.I)


def parse_submit_selector_identity(selector: str) -> dict[str, str]:
    """Extract semantic identity from a submit selector (scope-agnostic local part)."""
    raw = (selector or "").strip()
    if not raw:
        return {}
    local = raw.split()[-1] if " " in raw else raw
    scope = raw[: raw.rfind(local)].strip() if local != raw else ""
    out: dict[str, str] = {"raw": raw, "local": local, "scope": scope}
    for target in (raw, local):
        m_name = re.search(r"(?P<tag>input|button)\[name=\"(?P<name>[^\"]+)\"\]", target, re.I)
        if m_name:
            out.update(tag=m_name.group("tag").lower(), name=m_name.group("name"), kind="named")
            return out
        m_type = re.search(r"(?P<tag>input|button)\[type=\"(?P<type>[^\"]+)\"\]", target, re.I)
        if m_type:
            out.update(tag=m_type.group("tag").lower(), type=m_type.group("type").lower(), kind="typed")
            return out
    m_id = _ID_SUBMIT_RE.search(local)
    if m_id:
        out.update(id=m_id.group("id"), kind="id")
        return out
    for marker in _DISTINCTIVE_SUBMIT_CLASSES:
        if marker in raw:
            out.update(class_marker=marker, kind="class")
            return out
    out["kind"] = "other"
    return out


def is_scoped_refinement_of(base_selector: str, refined_selector: str) -> bool:
    """
    True when refined_selector adds form scope (or equivalent prefix) but targets the same control.
    """
    base = (base_selector or "").strip()
    refined = (refined_selector or "").strip()
    if not base or not refined:
        return False
    if base == refined:
        return True
    if refined.endswith(base) and refined != base:
        return True
    if f" {base}" in refined:
        return True

    base_id = parse_submit_selector_identity(base)
    refined_id = parse_submit_selector_identity(refined)
    if not base_id or not refined_id:
        return False
    if base_id.get("kind") != refined_id.get("kind"):
        # named base with refined adding value/class suffix on same name
        base_name = base_id.get("name")
        refined_name = refined_id.get("name")
        if base_name and base_name == refined_name:
            return base in refined or refined.endswith(base_id.get("local", base))
        return False
    if base_id.get("kind") == "named":
        if base_id.get("name") != refined_id.get("name"):
            return False
        if base_id.get("tag") != refined_id.get("tag"):
            return False
        return base in refined or refined.endswith(base_id.get("local", base))
    if base_id.get("kind") == "typed":
        return base_id.get("type") == refined_id.get("type") and base_id.get("tag") == refined_id.get("tag") and (
            base in refined or refined.endswith(base_id.get("local", base))
        )
    if base_id.get("kind") == "id":
        return base_id.get("id") == refined_id.get("id")
    if base_id.get("kind") == "class":
        return base_id.get("class_marker") == refined_id.get("class_marker")
    return False


def is_named_submit_selector(selector: str) -> bool:
    ident = parse_submit_selector_identity(selector)
    return ident.get("kind") == "named"


def is_generic_typed_submit_selector(selector: str) -> bool:
    ident = parse_submit_selector_identity(selector)
    return ident.get("kind") == "typed" and ident.get("type") in ("submit", "image")


def _css_escape(value: str) -> str:
    return re.sub(r'([!"#$%&\'()*+,./:;<=>?@[\\\]^`{|}~])', r"\\\1", value)


def candidate_label(candidate: dict[str, Any]) -> str:
    parts = [
        candidate.get("label") or "",
        candidate.get("text") or "",
        candidate.get("value") or "",
        candidate.get("ariaLabel") or "",
    ]
    return " ".join(p for p in parts if p).strip()


def classify_submit_candidate(
    candidate: dict[str, Any],
    *,
    page_url: str = "",
    form_action: str = "",
) -> str:
    return classify_button_action(
        candidate_label(candidate),
        candidate.get("type") or "",
        name=candidate.get("name") or "",
        el_id=candidate.get("id") or "",
        form_action=form_action or candidate.get("formAction") or "",
        page_url=page_url,
        class_name=candidate.get("className") or "",
    )


def is_auxiliary_submit_candidate(candidate: dict[str, Any]) -> bool:
    blob = candidate_label(candidate).lower()
    cls = (candidate.get("className") or "").lower()
    cid = (candidate.get("id") or "").lower()
    if candidate.get("type") == "reset":
        return True
    if any(k in blob or k in cls or k in cid for k in _AUXILIARY_LABEL_FRAGMENTS):
        return True
    tag = (candidate.get("tag") or "").lower()
    typ = (candidate.get("type") or "").lower()
    if tag == "button" and typ == "button" and classify_submit_candidate(candidate) == UNKNOWN:
        return True
    return False


def filter_actionable_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for candidate in candidates:
        if not candidate.get("inSelectedForm", True):
            continue
        if not candidate.get("visible"):
            continue
        if candidate.get("enabled") is False:
            continue
        if is_auxiliary_submit_candidate(candidate):
            continue
        out.append(candidate)
    return out


def desired_submit_classes(multistep_state: str) -> tuple[str, ...]:
    if multistep_state in (CONFIRMATION, FINAL_SUBMIT_READY):
        return (FINAL_SUBMIT, NEXT_STEP_SAFE)
    return (NEXT_STEP_SAFE, FINAL_SUBMIT)


def select_semantic_pool(
    candidates: list[dict[str, Any]],
    *,
    multistep_state: str,
    page_url: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (selected_pool, annotated_candidates)."""
    annotated: list[dict[str, Any]] = []
    by_class: dict[str, list[dict[str, Any]]] = {
        FINAL_SUBMIT: [],
        NEXT_STEP_SAFE: [],
        UNKNOWN: [],
        BACK: [],
    }
    for candidate in candidates:
        cls = classify_submit_candidate(
            candidate,
            page_url=page_url,
            form_action=candidate.get("formAction") or "",
        )
        enriched = {**candidate, "semantic_class": cls}
        annotated.append(enriched)
        if cls in by_class:
            by_class[cls].append(enriched)

    for preferred in desired_submit_classes(multistep_state):
        pool = [c for c in by_class.get(preferred, []) if not is_auxiliary_submit_candidate(c)]
        if pool:
            return pool, annotated

    unknown_pool = [c for c in by_class.get(UNKNOWN, []) if not is_auxiliary_submit_candidate(c)]
    if len(unknown_pool) == 1:
        return unknown_pool, annotated
    return [], annotated


def equivalence_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        candidate.get("tag") or "",
        candidate.get("type") or "",
        candidate.get("name") or "",
        candidate.get("value") or "",
        candidate.get("semantic_class") or classify_submit_candidate(candidate),
    )


def build_specific_selector(scope: str, candidate: dict[str, Any]) -> str:
    tag = (candidate.get("tag") or "input").lower()
    typ = (candidate.get("type") or "").lower()
    cid = (candidate.get("id") or "").strip()
    name = (candidate.get("name") or "").strip()
    value = candidate.get("value") or ""
    class_name = (candidate.get("className") or "").strip()

    def scoped(local: str) -> str:
        local = local.strip()
        if scope and local:
            return f"{scope} {local}"
        return local or scope

    if cid:
        return scoped(f"#{_css_escape(cid)}")
    if name and typ in ("submit", "button", "image"):
        esc = name.replace("\\", "\\\\").replace('"', '\\"')
        return scoped(f'{tag}[name="{esc}"]')
    for marker in _DISTINCTIVE_SUBMIT_CLASSES:
        if marker in class_name.split():
            return scoped(f".{marker}")
    if value and typ in ("submit", "image"):
        esc = value.replace("\\", "\\\\").replace('"', '\\"')
        return scoped(f'{tag}[type="{typ}"][value="{esc}"]')
    if typ:
        return scoped(f'{tag}[type="{typ}"]')
    return scoped(tag)


def resolve_submit_from_candidates(
    candidates: list[dict[str, Any]],
    *,
    contact_form_scope: str = "",
    submit_selector_hint: str = "",
    page_url: str = "",
    multistep_state: str = FORM_ENTRY,
) -> dict[str, Any]:
    """
    Semantic resolver entry point.
    Returns dict with policy, selector, candidate, reasons, annotated candidates.
    """
    actionable = filter_actionable_candidates(candidates)
    pool, annotated = select_semantic_pool(
        actionable,
        multistep_state=multistep_state,
        page_url=page_url,
    )

    if not pool:
        return {
            "policy": RESOLUTION_AMBIGUOUS,
            "valid": False,
            "reason": "submit_missing",
            "selector": (submit_selector_hint or "").strip(),
            "candidate": None,
            "matches": 0,
            "annotated_candidates": annotated,
        }

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for candidate in pool:
        grouped.setdefault(equivalence_key(candidate), []).append(candidate)

    if len(grouped) > 1:
        return {
            "policy": RESOLUTION_AMBIGUOUS,
            "valid": False,
            "reason": "submit_ambiguous",
            "selector": (submit_selector_hint or "").strip(),
            "candidate": None,
            "matches": len(pool),
            "annotated_candidates": annotated,
            "ambiguous_classes": sorted({k[4] for k in grouped.keys()}),
        }

    equivalents = next(iter(grouped.values()))
    chosen = sorted(equivalents, key=lambda c: int(c.get("domOrder") or 0))[0]
    policy = RESOLUTION_EQUIVALENT if len(equivalents) > 1 else RESOLUTION_UNIQUE
    selector = build_specific_selector(contact_form_scope, chosen)
    return {
        "policy": policy,
        "valid": True,
        "reason": "valid",
        "selector": selector,
        "candidate": chosen,
        "matches": 1,
        "annotated_candidates": annotated,
        "equivalent_count": len(equivalents),
    }
