#!/usr/bin/env python3
"""ARI authoritative READY live revalidation. Zero submit; no production authorization."""

from __future__ import annotations

import argparse
import asyncio
import csv
import copy
import hashlib
import json
import os
import re
import ssl
import tempfile
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright
import certifi

from ari_pipeline.sent_domain_index import get_sent_domain_index
from audit_safe149_live_presubmit import audit_one
from form_sender import (
    get_real_submission_count,
    get_submit_forbidden,
    reset_real_submission_count,
    set_submit_forbidden,
)
from shared_form_prepare import compute_semantic_hash

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE.parents[2] / "70_outputs/5-Day-Sales-Sprint"
LOG_DIR = BASE / "logs"
SOURCE = OUT_DIR / "ARI-Safe200-Persistent-V2-Manifest-2026-08-16.json"
SAFE_SOURCE = OUT_DIR / "Next-READY-Sales-Purpose-Audit-2026-08-16.json"
PF_SOURCE = OUT_DIR / "Next-READY-Full-Preflight-2026-08-16.json"
RECOVERED_FINAL = OUT_DIR / "Recovered1001-FINAL-READY-2026-08-17.json"

FIXED_INVENTORY = OUT_DIR / "ARI-125-Ready-Fixed-Inventory-2026-08-17.json"
CHECKPOINT = OUT_DIR / "ARI-125-Live-Revalidation-Checkpoint-2026-08-17.json"
OUT_JSON = OUT_DIR / "ARI-125-Live-Revalidation-2026-08-17.json"
OUT_CSV = OUT_DIR / "ARI-125-Live-Revalidation-2026-08-17.csv"
CANARY_JSON = OUT_DIR / "ARI-125-Canary-Candidate-Manifest-2026-08-17.json"

EXPECTED_SOURCE = 125
CONCURRENCY = 3
LEGACY_WORDING = re.compile(r"aiscan\.coaretail\.com|GEO診断|GEO対策診断", re.I)
PREVIEW_PREFIX = "https://readiness.coaretail.com/report/p/"


def strict_tls_context() -> ssl.SSLContext:
    """Use the environment CA bundle while retaining certificate verification."""
    return ssl.create_default_context(cafile=certifi.where())


def norm_domain(value: str) -> str:
    v = str(value or "").strip()
    if not v:
        return ""
    if "://" not in v:
        v = "https://" + v
    host = (urlparse(v).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def truthy(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"STOP invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"STOP invalid JSON root {path}")
    return value


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def current_attempted_domains() -> set[str]:
    found: set[str] = set()
    for path in list(OUT_DIR.glob("*.json")) + list(LOG_DIR.glob("*.csv")):
        rows = []
        try:
            if path.suffix == ".json":
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                for key in ("results", "per_company"):
                    if isinstance(data.get(key), list):
                        rows.extend(data[key])
            else:
                with path.open(encoding="utf-8-sig", newline="") as f:
                    rows = list(csv.DictReader(f))
        except Exception:
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            if truthy(row.get("attempted")) or truthy(row.get("final_submit_attempted")) or truthy(row.get("final_submit_clicked")):
                dom = norm_domain(row.get("domain") or row.get("website_url") or row.get("form_url"))
                if dom:
                    found.add(dom)
    return found


def active_cooldown() -> tuple[set[str], set[str]]:
    domains: set[str] = set(); companies: set[str] = set()
    path = LOG_DIR / ".failure_cooldown.csv"
    if not path.exists():
        return domains, companies
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                active = date.fromisoformat(row.get("cooldown_until") or "") >= date.today()
            except ValueError:
                active = False
            if active:
                dom = norm_domain(row.get("website_url")); company = (row.get("company_name") or "").strip()
                if dom: domains.add(dom)
                if company: companies.add(company)
    return domains, companies


def permanent_exclusions() -> tuple[set[str], set[str]]:
    domains: set[str] = set(); companies: set[str] = set()
    path = LOG_DIR / "permanent_skip.csv"
    if not path.exists():
        return domains, companies
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            dom = norm_domain(row.get("website_url")); company = (row.get("company_name") or "").strip()
            if dom: domains.add(dom)
            if company: companies.add(company)
    return domains, companies


def consumed_domains() -> set[str]:
    found: set[str] = set()
    for path in OUT_DIR.glob("*READY*.json"):
        try: data = load_json(path)
        except RuntimeError: continue
        for value in data.values():
            if not isinstance(value, list): continue
            for row in value:
                if isinstance(row, dict) and row.get("consumed_by_production"):
                    dom = norm_domain(row.get("domain") or row.get("website_url"))
                    if dom: found.add(dom)
    return found


def history_reason(domain: str, company: str, sent_index, attempted, cooldown_d, cooldown_c, perm_d, perm_c, consumed) -> str:
    if sent_index.should_no_resend(domain): return "ALREADY_SENT"
    if domain in attempted: return "ALREADY_ATTEMPTED"
    if domain in cooldown_d or company in cooldown_c: return "COOLDOWN"
    if domain in perm_d or company in perm_c: return "PERMANENT_EXCLUSION"
    if domain in consumed: return "CONSUMED_BY_PRODUCTION"
    return ""


def message_validation(item: dict) -> tuple[bool, list[str]]:
    row = item.get("row") or {}; ready = item.get("ready") or {}; message = item.get("message") or ""
    errors = []
    company = row.get("company_name") or ready.get("company_name") or ""
    preview_url = row.get("preview_url") or ""
    if row.get("message_variant") != "ARI_MESSAGE_V2": errors.append("wrong_message_variant")
    if not message.strip(): errors.append("empty_message")
    if len(message) < 250: errors.append("truncated_message")
    if company and company not in message: errors.append("company_identity_missing")
    if not preview_url or preview_url not in message: errors.append("preview_url_missing_in_message")
    if LEGACY_WORDING.search(message): errors.append("prohibited_legacy_wording")
    urls = re.findall(r"https?://[^\s]+", message)
    if preview_url and preview_url not in urls: errors.append("malformed_preview_url")
    return not errors, errors


def parse_expiry(payload: dict) -> tuple[bool, str]:
    raw = payload.get("expires_at") or payload.get("expiry") or payload.get("expiresAt") or ""
    if not raw:
        return True, "persistent_no_expiry_declared"
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt > datetime.now(timezone.utc), str(raw)
    except ValueError:
        return False, "invalid_expiry"


def preview_revalidate_sync(item: dict) -> dict:
    row = item.get("row") or {}; ready = item.get("ready") or {}
    token = str(row.get("preview_token") or "").strip(); url = str(row.get("preview_url") or "").strip()
    domain = str(row.get("domain") or ready.get("domain") or "").lower(); company = row.get("company_name") or ready.get("company_name") or ""
    result = {"valid": False, "token": token, "url": url, "api_status": None, "page_status": None,
              "expired": False, "identity_mismatch": False, "missing": False, "reason": ""}
    if not token or not url:
        result.update(missing=True, reason="missing_token_or_url"); return result
    expected = PREVIEW_PREFIX + token
    if not url.startswith(expected):
        result.update(identity_mismatch=True, reason="token_url_mismatch"); return result
    try:
        api_url = f"https://readiness.coaretail.com/api/preview/{token}"
        with urllib.request.urlopen(urllib.request.Request(api_url, headers={"User-Agent":"ARI-125-Revalidation/1.0"}), timeout=20, context=strict_tls_context()) as resp:
            result["api_status"] = getattr(resp, "status", 200); payload = json.loads(resp.read(2_000_000).decode("utf-8"))
        ok_expiry, expiry = parse_expiry(payload); result["expiry"] = expiry
        if not ok_expiry: result.update(expired=True, reason="preview_expired"); return result
        blob = json.dumps(payload, ensure_ascii=False)
        company_payload = payload.get("company") if isinstance(payload.get("company"), dict) else {}
        explicit_domain = payload.get("domain") or company_payload.get("domain")
        explicit_company = payload.get("company_name") or company_payload.get("name")
        if explicit_domain and norm_domain(explicit_domain) != domain:
            result.update(identity_mismatch=True, reason="snapshot_domain_mismatch"); return result
        if explicit_company and str(explicit_company).strip() != str(company).strip():
            result.update(identity_mismatch=True, reason="snapshot_company_mismatch"); return result
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent":"ARI-125-Revalidation/1.0"}), timeout=20, context=strict_tls_context()) as resp:
            result["page_status"] = getattr(resp, "status", 200); resp.read(4096)
        result["snapshot_identity_present"] = bool(explicit_domain or explicit_company or company in blob or domain in blob)
        if not result["snapshot_identity_present"]:
            result.update(identity_mismatch=True, reason="snapshot_identity_missing")
            return result
        result.update(valid=result["api_status"] == 200 and result["page_status"] == 200, reason="preview_valid")
        return result
    except Exception as exc:
        result["reason"] = f"{type(exc).__name__}:{str(exc)[:180]}"; return result


def build_fixed_inventory() -> tuple[list[dict], list[dict], dict]:
    manifest = load_json(SOURCE); selected = manifest.get("selected") or []
    if len(selected) != 149: raise RuntimeError(f"STOP persistent source !=149: {len(selected)}")
    safe_domains = {str(r.get("domain") or "").lower() for r in load_json(SAFE_SOURCE).get("safe_ready") or []}
    recovered = {str(r.get("domain") or "").lower() for r in load_json(RECOVERED_FINAL).get("ready") or []}
    sent_index = get_sent_domain_index(); attempted = current_attempted_domains(); cd, cc = active_cooldown(); pd, pc = permanent_exclusions(); consumed = consumed_domains()
    pf_map = load_pf_map()
    fixed=[]; excluded=[]; seen=set()
    for rank,item in enumerate(selected,1):
        row=item.get("row") or {}; ready=item.get("ready") or {}; domain=str(row.get("domain") or ready.get("domain") or "").lower(); company=row.get("company_name") or ready.get("company_name") or ""
        reason=""
        if not domain or domain in seen: reason="DUPLICATE_OR_MISSING_DOMAIN"
        elif domain not in safe_domains: reason="NOT_CANONICAL_SAFE_READY"
        elif domain in recovered: reason="RECOVERED1001_EXCLUDED"
        else: reason=history_reason(domain,company,sent_index,attempted,cd,cc,pd,pc,consumed)
        seen.add(domain)
        if reason: excluded.append({"domain":domain,"company_name":company,"reason":reason}); continue
        msg_ok,msg_errors=message_validation(item)
        pf = pf_map.get(domain) or {}
        fixed.append({"rank":rank,"domain":domain,"company_name":company,"industry_name":row.get("industry_name") or ready.get("industry_name") or "UNKNOWN","area_name":row.get("area_name") or "","website_url":row.get("website_url") or ready.get("website_url") or "","form_url":row.get("form_url") or ready.get("form_url") or "","message_variant":row.get("message_variant") or "","message":item.get("message") or "","preview_token":row.get("preview_token") or "","preview_url":row.get("preview_url") or "","preview_verification_state":{"manifest_api_status":item.get("preview_api_status"),"manifest_page_verified":item.get("preview_page_verified"),"snapshot_backend":item.get("snapshot_backend")},"candidate_id":row.get("candidate_id") or ready.get("candidate_id") or "","semantic_evidence":pf_semantic_evidence(pf),"preflight_mapping_hash":pf_mapping_hash(pf),"sales_purpose_state":"SAFE_READY","history_state":"CLEAN_AT_REVALIDATION","message_precheck_valid":msg_ok,"message_precheck_errors":msg_errors})
    if len({r['domain'] for r in fixed}) != len(fixed): raise RuntimeError("STOP duplicate fixed domains")
    if len(fixed) != EXPECTED_SOURCE: raise RuntimeError(f"STOP fixed cohort mismatch expected{EXPECTED_SOURCE} got{len(fixed)} exclusions={excluded}")
    if any(not r["message_precheck_valid"] for r in fixed): raise RuntimeError("STOP authoritative source contains invalid stored message")
    if any(not r["preview_token"] or not r["preview_url"] for r in fixed): raise RuntimeError("STOP authoritative source missing preview metadata")
    if any(r["industry_name"] == "UNKNOWN" for r in fixed): raise RuntimeError("STOP authoritative source contains UNKNOWN industry")
    return fixed,excluded,{"sent_domains":len(sent_index.confirmed_domains),"attempted_domains":len(attempted),"active_cooldown_domains":len(cd),"consumed_domains":len(consumed)}


def load_pf_map() -> dict[str,dict]:
    data=load_json(PF_SOURCE); return {str(r.get("domain") or "").lower():r for r in data.get("results") or [] if r.get("domain")}


def pf_semantic_evidence(record: dict) -> dict:
    fill = record.get("fill_no_submit") if isinstance(record.get("fill_no_submit"), dict) else {}
    return record.get("semantic_evidence") or fill.get("semantic_evidence") or {}


def pf_mapping_hash(record: dict) -> str:
    fill = record.get("fill_no_submit") if isinstance(record.get("fill_no_submit"), dict) else {}
    return str(record.get("preflight_mapping_hash") or fill.get("preflight_mapping_hash") or "")


def expected_current_mapping_hash(record: dict, message_variant: str, message: str) -> str:
    """Rebase historical form evidence onto the fixed current message contract."""
    evidence = pf_semantic_evidence(record)
    snapshot = copy.deepcopy(evidence.get("canonical_snapshot") or {})
    if not snapshot:
        return ""
    snapshot["message_variant"] = message_variant
    snapshot["message_length"] = len(message)
    return compute_semantic_hash(snapshot)


def save_checkpoint(results: dict[str,dict]) -> None:
    atomic_json(CHECKPOINT,{"source":str(FIXED_INVENTORY),"source_count":EXPECTED_SOURCE,"processed":len(results),"results":list(results.values()),"submit_forbidden":True,"real_sends":0,"final_submit":0,"updated_at":datetime.now().isoformat()})


def load_checkpoint() -> dict[str,dict]:
    if not CHECKPOINT.exists(): return {}
    data=load_json(CHECKPOINT)
    if data.get("source_count")!=EXPECTED_SOURCE or not isinstance(data.get("results"),list): raise RuntimeError("STOP checkpoint corruption")
    rows=data["results"]
    if any(not r.get("domain") for r in rows) or len({r['domain'] for r in rows})!=len(rows): raise RuntimeError("STOP checkpoint duplicate/corrupt")
    return {r['domain']:r for r in rows}


async def live_validate(records:list[dict], prechecks:dict[str,dict]) -> list[dict]:
    done=load_checkpoint(); pf=load_pf_map(); record_by={r['domain']:r for r in records}
    for domain, raw in done.items():
        src=record_by.get(domain) or {}; expected=expected_current_mapping_hash(pf.get(domain) or {},src.get('message_variant') or '',src.get('message') or ''); actual=raw.get('audit_mapping_hash') or raw.get('runtime_semantic_hash') or ''
        raw['expected_semantic_hash']=expected; raw['runtime_semantic_hash']=actual
        if raw.get('classification')=='SAFE_TO_SUBMIT': raw['revalidation_classification']='RUNTIME_DIVERGENCE' if not expected or not actual or expected!=actual else 'PRODUCTION_READY'
    pending=[r for r in records if r['domain'] in prechecks and prechecks[r['domain']]['precheck_classification']=='PASS' and r['domain'] not in done]
    set_submit_forbidden(True); reset_real_submission_count(); before=get_real_submission_count(); sem=asyncio.Semaphore(CONCURRENCY)
    items={r['domain']:{"row":r,"ready":r,"message":r['message']} for r in records}
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        try:
            for start in range(0,len(pending),12):
                wave=pending[start:start+12]
                audited=await asyncio.gather(*(audit_one(browser,items[r['domain']],r['rank'],sem) for r in wave))
                for raw in audited:
                    domain=raw['domain']; src=record_by[domain]; expected=expected_current_mapping_hash(pf.get(domain) or {},src['message_variant'],src['message']); actual=raw.get('audit_mapping_hash') or ''
                    if raw['classification']=='SAFE_TO_SUBMIT':
                        cls='RUNTIME_DIVERGENCE' if not expected or not actual or expected!=actual else 'PRODUCTION_READY'
                    elif raw.get('captcha_detected') or raw['classification'] in ('UNSUITABLE_REQUIRED_CHOICE',): cls='NOT_SUITABLE'
                    elif raw['classification'] in ('UNKNOWN_REQUIRED_CHOICE','VALIDATION_BLOCKED','OTHER_REVIEW'): cls='HOLD'
                    else: cls='INTERNAL_ERROR' if ':' in str(raw.get('blocker_reason') or '') else 'HOLD'
                    done[domain]={**raw,"revalidation_classification":cls,"expected_semantic_hash":expected,"runtime_semantic_hash":actual,"semantic_evidence":pf_semantic_evidence(pf.get(domain) or {}),"preview_validation":prechecks[domain]['preview_validation'],"message_validation":prechecks[domain]['message_validation']}
                save_checkpoint(done)
                if get_real_submission_count()!=before or not get_submit_forbidden(): raise RuntimeError("STOP SAFETY VIOLATION")
                print(f"CHECKPOINT {len(done)}/{sum(x['precheck_classification']=='PASS' for x in prechecks.values())}",flush=True)
        finally: await browser.close()
    if get_real_submission_count()!=before or not get_submit_forbidden(): raise RuntimeError("STOP SAFETY VIOLATION after live validation")
    return list(done.values())


def balanced_canary(ready:list[dict]) -> list[dict]:
    buckets=defaultdict(list)
    for r in sorted(ready,key=lambda x:x.get('rank',9999)): buckets[r.get('industry_name') or 'UNKNOWN'].append(r)
    order=['DENTAL','ESTHETIC_SALON','PERSONAL_GYM','BEAUTY_CLINIC']; selected=[]
    while len(selected)<10:
        progressed=False
        for industry in order:
            if buckets[industry] and len(selected)<10: selected.append(buckets[industry].pop(0));progressed=True
        if not progressed: break
    return selected


async def main() -> None:
    ap=argparse.ArgumentParser();ap.add_argument('--precheck-only',action='store_true');args=ap.parse_args()
    state_before=load_json(BASE/'automation_state.json');limits_before=load_json(LOG_DIR/'ari_daily_limits.json');set_submit_forbidden(True);reset_real_submission_count();before=get_real_submission_count()
    fixed,history_excluded,history_snapshot=build_fixed_inventory()
    atomic_json(FIXED_INVENTORY,{"generated_at":datetime.now().isoformat(),"source":str(SOURCE),"source_count":len(fixed),"history_excluded":history_excluded,"history_snapshot":history_snapshot,"duplicate_domains":0,"recovered1001_included":0,"records":fixed,"production":False,"production_authorization":None,"real_sends":0,"final_submit":0})
    sem=asyncio.Semaphore(12)
    async def check(r):
        async with sem:
            item={"row":r,"ready":r,"message":r["message"]}
            pv=await asyncio.to_thread(preview_revalidate_sync,item);mv_ok,mv_errors=message_validation(item);errors=[]
            if not pv['valid']:errors.append('preview:'+pv['reason'])
            if not mv_ok:errors.extend('message:'+x for x in mv_errors)
            return r['domain'],{"precheck_classification":"PASS" if not errors else "HOLD","preview_validation":pv,"message_validation":{"valid":mv_ok,"errors":mv_errors},"errors":errors}
    prechecks=dict(await asyncio.gather(*(check(r) for r in fixed)))
    if args.precheck_only:
        print(json.dumps({"source":len(fixed),"pass":sum(x['precheck_classification']=='PASS' for x in prechecks.values()),"hold":sum(x['precheck_classification']=='HOLD' for x in prechecks.values())},ensure_ascii=False));return
    live=await live_validate(fixed,prechecks); live_by={r['domain']:r for r in live}; results=[]
    for r in fixed:
        pc=prechecks[r['domain']]
        if pc['precheck_classification']!='PASS': results.append({**r,**pc,"revalidation_classification":"HOLD","blocker_reason":";".join(pc['errors'])})
        else: results.append({**r,**live_by[r['domain']]})
    counts=Counter(r['revalidation_classification'] for r in results);ready=[r for r in results if r['revalidation_classification']=='PRODUCTION_READY'];canary=balanced_canary(ready)
    atomic_json(OUT_JSON,{"generated_at":datetime.now().isoformat(),"source_count":len(fixed),"history_re_excluded":len(history_excluded),"preview_invalid":sum(not x['preview_validation']['valid'] for x in prechecks.values()),"message_invalid":sum(not x['message_validation']['valid'] for x in prechecks.values()),"live_validation_targets":sum(x['precheck_classification']=='PASS' for x in prechecks.values()),"classification_distribution":dict(counts),"results":results,"submit_forbidden":True,"real_sends_before":before,"real_sends_after":get_real_submission_count(),"final_submit":0,"production":False,"production_authorization":None})
    with OUT_CSV.open('w',encoding='utf-8-sig',newline='') as f:
        fields=['rank','company_display_name','domain','form_url','revalidation_classification','blocker_reason','captcha_detected','expected_semantic_hash','runtime_semantic_hash','audit_timestamp'];w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(results)
    canary_rows=[]
    fixed_by={r['domain']:r for r in fixed}
    for r in canary:
        src=fixed_by[r['domain']];canary_rows.append({"rank":len(canary_rows)+1,"company_name":src['company_name'],"domain":src['domain'],"industry_name":src['industry_name'],"form_url":src['form_url'],"message_variant":src['message_variant'],"message_identity":{"candidate_id":src['candidate_id'],"message_length":len(src['message']),"message_sha256":hashlib.sha256(src['message'].encode('utf-8')).hexdigest()},"preview_identity":{"token":src['preview_token'],"url":src['preview_url']},"semantic_evidence_hash":r.get('runtime_semantic_hash') or r.get('expected_semantic_hash') or '',"revalidated_at":r.get('audit_timestamp')})
    atomic_json(CANARY_JSON,{"generated_at":datetime.now().isoformat(),"source":str(OUT_JSON),"canary_count":len(canary_rows),"hard_cap":10,"production_authorized":False,"production":False,"real_sends":0,"final_submit":0,"exact_domains":[r['domain'] for r in canary_rows],"candidates":canary_rows})
    state_after=load_json(BASE/'automation_state.json');limits_after=load_json(LOG_DIR/'ari_daily_limits.json')
    if state_before!=state_after or limits_before!=limits_after: raise RuntimeError('STOP production state changed')
    if get_real_submission_count()!=before or not get_submit_forbidden(): raise RuntimeError('STOP submission safety failed')
    print(json.dumps({"source":len(fixed),"precheck_pass":sum(x['precheck_classification']=='PASS' for x in prechecks.values()),"classification":dict(counts),"canary":len(canary_rows),"real_sends":0,"final_submit":0},ensure_ascii=False,indent=2))


if __name__=='__main__': asyncio.run(main())
