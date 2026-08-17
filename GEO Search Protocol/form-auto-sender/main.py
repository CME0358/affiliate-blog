"""
main.py  —  フォーム自動送信システム エントリーポイント

実行例:
    # 単一ファイル（dry-run）
    python main.py --input input/2026-05-12_美容クリニック_港区.md --dry-run

    # Obsidian パス指定（dry-run）
    python main.py --input "@40_Sales/商談メモ/リスト/2026-05-12_美容クリニック_港区.md" --dry-run

    # ディレクトリ一括処理（本番）
    python main.py --input input/

    # 件数制限
    python main.py --input input/ --limit 5 --dry-run

    # error.csv に記録済みの件を修正版ロジックで再処理
    python main.py --retry-errors

    # リトライをドライランで確認
    python main.py --retry-errors --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# 送信可能時間帯（企業営業時間に準拠）
SEND_HOUR_START = 10
SEND_HOUR_END = 18

_BASE_DIR = Path(__file__).resolve().parent
_DASHBOARD_SCRIPT = _BASE_DIR / "build_ops_dashboard.py"


def rebuild_ops_dashboard() -> None:
    """70_outputs/運用ダッシュボード.html の form-auto-sender 指標を更新する。"""
    if not _DASHBOARD_SCRIPT.is_file():
        print("⚠️  build_ops_dashboard.py が見つかりません。ダッシュボードは更新しません。", file=sys.stderr)
        return
    try:
        subprocess.run(
            [sys.executable, str(_DASHBOARD_SCRIPT)],
            cwd=_BASE_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
        print("📊  運用ダッシュボードを更新しました（70_outputs/運用ダッシュボード.html）")
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or str(e)).strip()
        print(f"⚠️  ダッシュボード更新失敗: {err}", file=sys.stderr)

from config import (
    DAILY_OUTCOME_LIMIT,
    FAILURE_COOLDOWN_INDEX,
    INPUT_DIR,
    LOG_ERROR,
    SEND_INTERVAL_MIN,
    SEND_INTERVAL_MAX,
    VAULT_ROOT,
)
from automation_state import is_paused
from parser import parse_md_list, _resolve_path
from form_finder import find_form_url
from url_builder import build_lp_url
from message_builder import build_message
from form_sender import send_form, send_form_dry_run, set_submit_forbidden, get_real_submission_count
from form_detector import detect_form_only
from form_fill_no_submit import fill_form_no_submit, write_canary_report
from form_submit_canary import (
    validate_submit_canary_preconditions,
    submit_canary as run_submit_canary,
    is_live_execution_armed,
    MAX_REAL_SUBMISSIONS,
)
from log_manager import (
    get_stats,
    is_already_sent,
    is_in_failure_cooldown,
    is_permanently_skipped,
    load_companies_from_error_csv,
    log_result,
    seed_failure_cooldown_from_error_csv,
    sync_permanent_skip,
)
from list_filter import apply_list_filter, get_config_exclusion_label


# ─── 起動時チェック ───────────────────────────────────────────────────────────


def ensure_not_paused(job_id: str = "form-auto-sender") -> None:
    """停止フラグが立っていれば即終了（手動起動・長時間バッチの安全弁）。"""
    if is_paused(job_id):
        print(
            f"⏸  {job_id} は停止中です。"
            "再開: python3 automation_control.py resume form-auto-sender",
            file=sys.stderr,
        )
        sys.exit(0)


def ensure_failure_cooldown_seeded() -> None:
    """error.csv があるのにクールダウン索引が空なら初回バックフィルを実行する（P0）。"""
    if not LOG_ERROR.exists():
        return
    has_errors = False
    with LOG_ERROR.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == 0:
                continue
            if line.strip():
                has_errors = True
                break
    if not has_errors:
        return
    if FAILURE_COOLDOWN_INDEX.exists() and FAILURE_COOLDOWN_INDEX.stat().st_size > 80:
        return
    n = seed_failure_cooldown_from_error_csv()
    if n:
        print(f"📋  失敗クールダウン索引を error.csv から生成: {n} 社")


# ─── 1件処理 ─────────────────────────────────────────────────────────────────


def ensure_not_bulk_inventory(input_path: str, pilot: bool) -> None:
    """
    デフォルト INPUT_DIR 一括処理の誤実行を防ぐ。
    パイロットは --pilot / --pilot-list で明示ファイル指定が必須。
    """
    resolved = _resolve_path(input_path).resolve()
    default_dir = Path(INPUT_DIR).resolve()

    if pilot:
        if resolved.is_dir():
            print(
                "⛔  --pilot モードでは単一 MD ファイルを指定してください（ディレクトリ不可）。",
                file=sys.stderr,
            )
            sys.exit(1)
        if not resolved.is_file():
            print(f"⛔  パイロット入力ファイルが見つかりません: {resolved}", file=sys.stderr)
            sys.exit(1)
        return

    if resolved == default_dir and resolved.is_dir():
        print(
            "⛔  全リード在庫（INPUT_DIR）の一括処理はブロックされています。\n"
            "    パイロット: --pilot-list <path> --dry-run\n"
            "    単一リスト: --input <file.md>",
            file=sys.stderr,
        )
        sys.exit(1)


async def process_company(
    company: dict,
    dry_run: bool = False,
    force_retry: bool = False,
    pilot: bool = False,
    detect_only: bool = False,
    detect_timeout: int | None = None,
    fill_no_submit: bool = False,
    submit_canary: bool = False,
    message_version: str = "v1",
) -> tuple[str, str]:
    """
    Returns:
        (outcome, progress_suffix) — outcome: sent|error|pending|skipped|dry_run
    """
    name = company["company_name"]

    # ── submit-canary: 単発 submit（live 未武装時は実装検証のみ）──────────────
    if submit_canary:
        set_submit_forbidden(not is_live_execution_armed())
        form_url = company.get("form_url") or company.get("フォームURL")
        if form_url:
            company["form_url"] = str(form_url).strip()

        lp_url = build_lp_url(company["industry_name"], company.get("area_name", ""))
        message = build_message(
            company["industry_name"],
            company["company_name"],
            lp_url,
            area_name=company.get("area_name", ""),
        )
        result = await run_submit_canary(company, message, lp_url)
        company["_submit_canary_result"] = result
        overall = result.get("overall", "BLOCKED")
        live = result.get("live_execution", False)
        print(
            f"  → SUBMIT-CANARY | {overall} | live={live} | "
            f"submissions={result.get('real_submission_count', 0)}/{MAX_REAL_SUBMISSIONS}"
        )
        if not live:
            assert get_real_submission_count() == 0, "real_submission_count must remain 0 when live not armed"
        if result.get("status") == "error":
            return "error", f"CANARY:{overall}"
        if result.get("status") == "implementation_ready":
            return "canary_ready", f"CANARY:{overall}"
        if result.get("status") == "sent":
            return "sent", "CANARY:SENT"
        return "error", f"CANARY:{overall}"

    # ── fill-no-submit: 入力のみ（submit 禁止）────────────────────────────────
    if fill_no_submit:
        set_submit_forbidden(True)
        name = company["company_name"]
        form_url = company.get("form_url") or company.get("フォームURL")
        if form_url:
            company["form_url"] = str(form_url).strip()
        elif not company.get("form_url"):
            print(f"🔍  フォーム探索中: {name} ({company.get('website_url', '')})")
            form_result = await find_form_url(
                company["website_url"],
                company_name=name,
            )
            if form_result["status"] != "found":
                print(f"❌  フォームなし: {name}  ({form_result.get('reason', '')})")
                return "error", f"ERROR: {form_result.get('reason', 'no_form')}"
            company["form_url"] = form_result["form_url"]

        lp_url = build_lp_url(company["industry_name"], company.get("area_name", ""))
        message = build_message(
            company["industry_name"],
            company["company_name"],
            lp_url,
            area_name=company.get("area_name", ""),
        )
        result = await fill_form_no_submit(company, message, lp_url)
        company["_fill_no_submit_result"] = result
        overall = result.get("overall", "BLOCKED")
        print(f"  → FILL-NO-SUBMIT | {overall} | form={result.get('form_url')}")
        if result.get("field_map"):
            fm = result["field_map"]
            print(
                f"     fields: name={fm.get('name')} email={fm.get('email')} "
                f"message={fm.get('message')} consent={fm.get('consent')}"
            )
        assert get_real_submission_count() == 0, "real_submission_count must remain 0"
        if result.get("status") == "error":
            return "error", f"FILL:{overall}"
        return "filled", f"FILL:{overall}"

    # ── detect-only: フォーム検出のみ（submit/fill 禁止）────────────────────
    if detect_only:
        set_submit_forbidden(True)
        result = await detect_form_only(company, timeout_sec=detect_timeout)
        ft = result.get("form_type", "ERROR")
        conf = result.get("confidence", "LOW")
        print(
            f"  → {ft} | confidence={conf} | form={result.get('form_url') or '—'}"
        )
        if result.get("field_map"):
            fm = result["field_map"]
            print(
                f"     fields: email={fm.get('email')} message={fm.get('message')} "
                f"name={fm.get('name')} captcha={result.get('captcha')}"
            )
        company["_detection_result"] = result
        return "detected", f"DETECT:{ft}"

    exclusion = None if pilot else get_config_exclusion_label(company)
    if exclusion:
        return "skipped", f"SKIP（{exclusion}）"

    # 重複チェック
    if not dry_run and is_already_sent(name, company.get("website_url", "")):
        return "skipped", "SKIP（送信済み）"

    if not dry_run and not force_retry:
        in_cd, cd_msg = is_in_failure_cooldown(company)
        if in_cd:
            return "skipped", f"SKIP（失敗クールダウン）: {cd_msg}"

        in_perm, _perm_reason = is_permanently_skipped(company)
        if in_perm:
            return "skipped", "SKIP（永続除外）"

    # フォーム URL 特定
    if dry_run:
        # dry-run では実際のアクセスをスキップ（website_url をそのまま使用）
        company["form_url"] = company.get("website_url", "")
        form_result = {"status": "found", "form_url": company["form_url"], "reason": ""}
    else:
        print(f"🔍  フォーム探索中: {name} ({company.get('website_url', '')})")
        form_result = await find_form_url(
            company["website_url"],
            company_name=name,
        )

    # LP URL & 文面生成（フォーム探索と並行して先に確定させる）
    if message_version == "v2":
        from message_builder import build_preview_message_for_company
        lp_url, message, _snap = build_preview_message_for_company(
            company,
            ab_arm="C",
            dry_run_snapshot=True,
        )
    else:
        lp_url = build_lp_url(company["industry_name"], company["area_name"])
        message = build_message(
            company["industry_name"],
            company["company_name"],
            lp_url,
            area_name=company.get("area_name", ""),
        )

    if form_result["status"] == "pending":
        print(f"⚠️  要手動確認（reCAPTCHA）: {name}")
        log_result(
            "pending",
            company,
            {
                "reason": form_result["reason"],
                "form_url": form_result.get("form_url", ""),
                "lp_url": lp_url,
                "message": message,
            },
        )
        return "pending", "PENDING（reCAPTCHA）"

    if form_result["status"] != "found":
        print(f"❌  フォームなし: {name}  ({form_result['reason']})")
        log_result(form_result["status"], company, {"detail": form_result["reason"]})
        return "error", f"ERROR: {form_result['reason']}"

    company["form_url"] = form_result["form_url"]

    # send_form は form_url が無い場合は呼ばない（error.csv に form_url_is_none で記録）
    if not dry_run:
        fu = company.get("form_url")
        if not fu or not str(fu).strip():
            print(f"❌  form_url なし（スキップ）: {name}")
            log_result("error", company, {"detail": "form_url_is_none"})
            return "error", "ERROR: form_url_is_none"

    # 送信
    if dry_run:
        result = await send_form_dry_run(company, message, lp_url)
        print(f"📋  [DRY-RUN] {name}")
        return "dry_run", "DRY-RUN"
    else:
        result = await send_form(company, message, lp_url)
        icon = "✅" if result["status"] == "sent" else "❌"
        print(f"{icon}  {name}: {result['status']}")
        log_result(result["status"], company, {**result, "message": message})

    # 送信間隔（本番のみ）
    if not dry_run and result["status"] == "sent":
        await asyncio.sleep(random.uniform(SEND_INTERVAL_MIN, SEND_INTERVAL_MAX))
        return "sent", "SENT"

    if result["status"] == "pending":
        return "pending", f"PENDING: {result.get('reason', '')}"

    reason = result.get("reason") or "send_failed"
    return "error", f"ERROR: {reason}"


# ─── バッチ実行 ───────────────────────────────────────────────────────────────


def _print_industry_tier_summary(companies: list[dict]) -> None:
    counts: dict[int, int] = {}
    for c in companies:
        t = c.get("industry_tier")
        if t is None:
            continue
        counts[t] = counts.get(t, 0) + 1
    if counts:
        ordered = ", ".join(f"T{k}={v}件" for k, v in sorted(counts.items()))
        print(f"業種 tier 内訳: {ordered}\n")


def _company_label(company: dict) -> str:
    name = company["company_name"]
    tier = company.get("industry_tier")
    if tier is not None:
        return f"{name} [業種T{tier}]"
    return name


async def run_batch(
    companies: list[dict],
    dry_run: bool,
    limit: int | None,
    source_label: str,
    force_retry: bool = False,
    pilot: bool = False,
    detect_only: bool = False,
    detect_timeout: int | None = None,
    fill_no_submit: bool = False,
    submit_canary: bool = False,
    pilot_list_path: str = "",
    message_version: str = "v1",
) -> list[dict]:
    if submit_canary:
        mode_label = "[SUBMIT-CANARY]"
    elif fill_no_submit:
        mode_label = "[FILL-NO-SUBMIT]"
    elif detect_only:
        mode_label = "[DETECT-ONLY]"
    elif dry_run:
        mode_label = "[DRY-RUN]"
    else:
        mode_label = "[本番]"
    print(f"\n{'='*60}")
    print(f"  フォーム自動送信システム {mode_label}")
    if pilot:
        print("  [PILOT]")
    if submit_canary:
        print("  ⛔  live 未武装（SUBMIT_CANARY_LIVE≠1）/ submit 禁止 / retry 禁止")
    if fill_no_submit:
        print("  ⛔  submit 禁止 / 入力のみ / CAPTCHA 操作禁止")
    if detect_only:
        print("  ⛔  submit 禁止 / fill 禁止 / CAPTCHA 操作禁止")
    print(f"  {source_label}")
    print(f"{'='*60}\n")

    if not companies:
        print("対象企業が0件です。")
        sys.exit(0)

    ensure_failure_cooldown_seeded()
    sync_permanent_skip()
    print()

    if not force_retry and not submit_canary:
        companies = apply_list_filter(companies, source_label=source_label)

    if not companies:
        print("フィルタ後の送信対象が0件です。")
        sys.exit(0)

    if limit:
        companies = companies[:limit]

    if submit_canary:
        ok, err = validate_submit_canary_preconditions(
            pilot_list_path or source_label,
            companies,
            limit=1,
        )
        if not ok:
            print(f"⛔  submit-canary ガード失敗: {err}", file=sys.stderr)
            sys.exit(1)
        companies = companies[:1]

    print(f"処理対象: {len(companies)} 件")
    _print_industry_tier_summary(companies)

    apply_daily_limit = (
        not dry_run and not detect_only and not fill_no_submit and not submit_canary
        and DAILY_OUTCOME_LIMIT > 0 and not force_retry
    )

    if apply_daily_limit:
        stats0 = get_stats()
        done_today = stats0["sent"] + stats0["pending"] + stats0["error"]
        if done_today >= DAILY_OUTCOME_LIMIT:
            print(
                f"📊  本日の1日上限（{DAILY_OUTCOME_LIMIT}件）に達しています。"
                f"ログ上の本日の処理件数: {done_today} 件（成功+手動確認+エラーの合計）\n"
                f"    明日 10:00 の自動実行で続きを処理するか、日付を変えた別ログで実行してください。\n"
            )
            sys.exit(0)
        remaining_quota = DAILY_OUTCOME_LIMIT - done_today
        print(
            f"📊  本日の残り枠: あと {remaining_quota} 件まで"
            f"（1日上限 {DAILY_OUTCOME_LIMIT} 件 − 本日ログ済み {done_today} 件）\n"
        )

    if force_retry and not dry_run:
        print("📊  --force-retry: 本日の1日上限チェックをスキップします\n")

    batch_counts = {"sent": 0, "error": 0, "skipped": 0, "excluded": 0, "detected": 0, "filled": 0, "canary_ready": 0}
    detection_results: list[dict] = []
    fill_results: list[dict] = []
    submit_canary_results: list[dict] = []

    for i, company in enumerate(companies, 1):
        if not dry_run and not detect_only and not fill_no_submit and not submit_canary and is_paused("form-auto-sender"):
            print(
                f"\n⏸  停止フラグ検知（{i - 1}/{len(companies)} 件処理済）。"
                "残りは再開後に実行してください。"
            )
            break

        if apply_daily_limit:
            st = get_stats()
            if st["sent"] + st["pending"] + st["error"] >= DAILY_OUTCOME_LIMIT:
                print(
                    f"\n📊  本日の1日上限（{DAILY_OUTCOME_LIMIT}件）に達しました。"
                    "明日以降に続きを処理します。"
                )
                break

        if not dry_run and not detect_only and not fill_no_submit and not submit_canary and not force_retry and datetime.now().hour >= SEND_HOUR_END:
            remaining = len(companies) - i + 1
            print(f"\n⏰  18:00 を超えました。残り {remaining} 件は翌日 10:00 に処理します。")
            break

        name = _company_label(company)
        t0 = time.perf_counter()
        try:
            outcome, result_label = await process_company(
                company,
                dry_run=dry_run,
                force_retry=force_retry,
                pilot=pilot,
                detect_only=detect_only,
                detect_timeout=detect_timeout,
                fill_no_submit=fill_no_submit,
                submit_canary=submit_canary,
                message_version=message_version,
            )
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"[{i:02d}/{len(companies):02d}] {name} - ERROR: {e!r} ({elapsed:.1f}秒)")
            batch_counts["error"] += 1
            continue

        elapsed = time.perf_counter() - t0
        print(f"[{i:02d}/{len(companies):02d}] {name} - {result_label} ({elapsed:.1f}秒)")

        if outcome == "sent":
            batch_counts["sent"] += 1
        elif outcome == "skipped":
            batch_counts["skipped"] += 1
            if "業種除外" in result_label or "エリア除外" in result_label:
                batch_counts["excluded"] += 1
        elif outcome in ("error", "pending"):
            batch_counts["error"] += 1
        elif outcome == "dry_run":
            pass
        elif outcome == "canary_ready":
            batch_counts["canary_ready"] += 1
            sr = company.get("_submit_canary_result")
            if sr:
                submit_canary_results.append(sr)
        elif outcome == "filled":
            batch_counts["filled"] = batch_counts.get("filled", 0) + 1
            fr = company.get("_fill_no_submit_result")
            if fr:
                fill_results.append(fr)
        elif outcome == "detected":
            batch_counts["detected"] += 1
            dr = company.get("_detection_result")
            if dr:
                detection_results.append(dr)

    print(f"\n{'='*60}")
    if submit_canary:
        print(f"  SUBMIT-CANARY 完了: {len(submit_canary_results)} 件")
        print(f"  live execution armed: {is_live_execution_armed()}")
        print(f"  実送信: {get_real_submission_count()}（max {MAX_REAL_SUBMISSIONS}）")
        if not is_live_execution_armed():
            assert get_real_submission_count() == 0
    elif fill_no_submit:
        print(f"  FILL-NO-SUBMIT 完了: {len(fill_results)} 件")
        print(f"  実送信: {get_real_submission_count()}（submit 禁止）")
        assert get_real_submission_count() == 0
    elif detect_only:
        found = sum(
            1
            for r in detection_results
            if r.get("form_type") in ("FORM_FOUND", "CAPTCHA", "MULTI_STEP", "EXTERNAL_FORM")
        )
        print(f"  DETECT-ONLY 完了: {len(detection_results)} 件検査 / フォーム検出 {found} 件")
        print(f"  実送信: 0（submit 禁止）")
    elif dry_run:
        print(f"  DRY-RUN 完了: {len(companies)} 件をプレビューしました")
    else:
        stats = get_stats()
        print("  処理完了")
        print(
            f"  再実行完了: 送信{batch_counts['sent']}件 / "
            f"エラー{batch_counts['error']}件 / "
            f"スキップ{batch_counts['skipped']}件（除外{batch_counts['excluded']}件含む）"
        )
        print(f"  ✅  送信成功 : {stats['sent']} 件（累計）")
        print(f"  ❌  エラー   : {stats['error']} 件（累計）")
        print(f"  ⚠️   要手動確認: {stats['pending']} 件（累計）")
        rebuild_ops_dashboard()
        try:
            from export_pending import export_pending
            export_pending()
        except Exception as e:
            print(f"⚠️  reCAPTCHA手動キュー出力スキップ: {e}", file=sys.stderr)
    print(f"{'='*60}\n")
    if submit_canary:
        return submit_canary_results
    if fill_no_submit:
        return fill_results
    return detection_results


async def main(
    input_path: str,
    dry_run: bool,
    limit: int | None,
    pilot: bool = False,
    detect_only: bool = False,
    detect_timeout: int | None = None,
    fill_no_submit: bool = False,
    submit_canary: bool = False,
    message_version: str = "v1",
) -> list[dict]:
    companies = parse_md_list(input_path)
    return await run_batch(
        companies,
        dry_run=dry_run,
        limit=limit,
        source_label=f"入力: {input_path}",
        pilot=pilot,
        detect_only=detect_only,
        detect_timeout=detect_timeout,
        fill_no_submit=fill_no_submit,
        submit_canary=submit_canary,
        pilot_list_path=input_path,
        message_version=message_version,
    )


async def main_retry_errors(
    dry_run: bool,
    limit: int | None,
    force_retry: bool = False,
    pilot: bool = False,
    detect_only: bool = False,
    detect_timeout: int | None = None,
) -> list[dict]:
    companies = load_companies_from_error_csv(LOG_ERROR)
    label = f"リトライ元: {LOG_ERROR}"
    if not companies:
        print(f"{LOG_ERROR} が無いか、データ行がありません。")
        sys.exit(0)
    return await run_batch(
        companies,
        dry_run=dry_run,
        limit=limit,
        source_label=label,
        force_retry=force_retry,
        pilot=pilot,
        detect_only=detect_only,
        detect_timeout=detect_timeout,
    )


# ─── CLI ─────────────────────────────────────────────────────────────────────


def write_detection_log(results: list[dict], pilot_path: str) -> Path:
    """検出結果を Vault 出力フォルダに Markdown ログとして書き出す。"""
    out_dir = VAULT_ROOT / "70_outputs" / "5-Day-Sales-Sprint"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ARI Form Detection Pilot Log.md"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S JST")
    lines = [
        "# ARI Form Detection Pilot Log",
        "",
        f"- **実行日時**: {ts}",
        f"- **パイロットファイル**: `{pilot_path}`",
        f"- **検査件数**: {len(results)}",
        f"- **実送信**: 0",
        "",
        "## Results",
        "",
        "| Company | Industry | Website | Form Type | Captcha | Confidence | Form URL |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            "| {company} | {industry} | {web} | {ftype} | {cap} | {conf} | {form} |".format(
                company=r.get("company_name", "").replace("|", "/"),
                industry=r.get("industry_name", "").replace("|", "/"),
                web=(r.get("website_url") or "")[:60],
                ftype=r.get("form_type", ""),
                cap="Yes" if r.get("captcha") else "No",
                conf=r.get("confidence", ""),
                form=(r.get("form_url") or "—")[:80],
            )
        )
    lines += ["", "## Detail", ""]
    for i, r in enumerate(results, 1):
        lines += [
            f"### {i}. {r.get('company_name')}",
            "",
            f"- Industry: {r.get('industry_name')}",
            f"- Website: {r.get('website_url')}",
            f"- Contact Page: {r.get('contact_page_url')}",
            f"- Form URL: {r.get('form_url') or '—'}",
            f"- Form Type: **{r.get('form_type')}**",
            f"- Confidence: {r.get('confidence')}",
            f"- Captcha: {r.get('captcha')}",
            f"- External Provider: {r.get('external_provider') or '—'}",
            f"- Submit Label: {r.get('submit_label') or '—'}",
            f"- Failure Reason: {r.get('failure_reason') or '—'}",
            f"- Field Map: `{r.get('field_map')}`",
            "",
        ]
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"📝  検出ログ: {out_path}")
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="フォーム自動送信システム",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--input",
        "-i",
        default=str(INPUT_DIR),
        metavar="PATH",
        help=f"MDファイルまたはディレクトリ（--retry-errors 未指定時のデフォルト: {INPUT_DIR}）",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="送信せずに文面・フォームURLをコンソールに表示するだけ",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="処理件数の上限（テスト用）",
    )
    ap.add_argument(
        "--retry-errors",
        action="store_true",
        help=f"{LOG_ERROR.name} の全行を読み込み、修正版ロジックでフォーム探索〜送信まで再処理する",
    )
    ap.add_argument(
        "--pilot",
        action="store_true",
        help="パイロットモード: SKIP_INDUSTRIES をバイパスし、明示 MD ファイルのみ処理",
    )
    ap.add_argument(
        "--pilot-list",
        metavar="PATH",
        help="パイロット用 MD ファイル（--pilot を暗黙的に有効化）",
    )
    ap.add_argument(
        "--detect-only",
        action="store_true",
        help="Playwright でフォーム検出のみ（submit/fill 禁止・--pilot-list 必須）",
    )
    ap.add_argument(
        "--fill-no-submit",
        action="store_true",
        help="フォーム入力のみ（submit 禁止・--pilot-list 必須）",
    )
    ap.add_argument(
        "--submit-canary",
        action="store_true",
        help="ARI 単発 submit canary（--pilot-list 必須・--limit 1 強制・live 未武装時は submit 禁止）",
    )
    ap.add_argument(
        "--detect-timeout",
        type=int,
        default=None,
        metavar="SEC",
        help="detect-only 時のフォーム探索タイムアウト秒（本番デフォルト60は変更しない）",
    )
    ap.add_argument(
        "--force-retry",
        action="store_true",
        help="失敗クールダウンを無視して再処理する（--retry-errors と併用）",
    )
    ap.add_argument(
        "--message-version",
        choices=("v1", "v2"),
        default="v1",
        help="v2 = preview funnel 文面（--dry-run 専用・本番送信不可）",
    )
    args = ap.parse_args()

    if args.message_version == "v2" and not args.dry_run:
        print("⛔  --message-version v2 は --dry-run と併用時のみ許可されます。", file=sys.stderr)
        sys.exit(1)

    if args.pilot_list:
        args.input = args.pilot_list
        args.pilot = True

    if args.detect_only:
        args.pilot = True
        set_submit_forbidden(True)
        if not args.pilot_list:
            print(
                "⛔  --detect-only には --pilot-list <path> が必須です。",
                file=sys.stderr,
            )
            sys.exit(1)

    if args.fill_no_submit:
        args.pilot = True
        set_submit_forbidden(True)
        if not args.pilot_list:
            print(
                "⛔  --fill-no-submit には --pilot-list <path> が必須です。",
                file=sys.stderr,
            )
            sys.exit(1)

    if args.submit_canary:
        args.pilot = True
        args.limit = 1
        set_submit_forbidden(not is_live_execution_armed())
        if not args.pilot_list:
            print(
                "⛔  --submit-canary には --pilot-list <path> が必須です。",
                file=sys.stderr,
            )
            sys.exit(1)

    ensure_not_bulk_inventory(args.input, pilot=args.pilot)

    if not args.dry_run and not args.detect_only and not args.fill_no_submit and not args.submit_canary:
        ensure_not_paused()
        if not args.pilot:
            print(
                "⛔  本番送信には --pilot-list で明示したパイロットファイルが必要です。",
                file=sys.stderr,
            )
            sys.exit(1)

    if args.detect_only and args.dry_run:
        print("⛔  --detect-only と --dry-run は同時指定できません。", file=sys.stderr)
        sys.exit(1)

    if args.fill_no_submit and args.dry_run:
        print("⛔  --fill-no-submit と --dry-run は同時指定できません。", file=sys.stderr)
        sys.exit(1)

    if args.fill_no_submit and args.detect_only:
        print("⛔  --fill-no-submit と --detect-only は同時指定できません。", file=sys.stderr)
        sys.exit(1)

    if args.submit_canary and args.dry_run:
        print("⛔  --submit-canary と --dry-run は同時指定できません。", file=sys.stderr)
        sys.exit(1)

    if args.submit_canary and args.detect_only:
        print("⛔  --submit-canary と --detect-only は同時指定できません。", file=sys.stderr)
        sys.exit(1)

    if args.submit_canary and args.fill_no_submit:
        print("⛔  --submit-canary と --fill-no-submit は同時指定できません。", file=sys.stderr)
        sys.exit(1)

    if args.submit_canary and args.retry_errors:
        print("⛔  --submit-canary と --retry-errors は同時指定できません。", file=sys.stderr)
        sys.exit(1)

    if args.submit_canary and args.force_retry:
        print("⛔  --submit-canary と --force-retry は同時指定できません。", file=sys.stderr)
        sys.exit(1)

    if args.retry_errors:
        asyncio.run(
            main_retry_errors(
                dry_run=args.dry_run,
                limit=args.limit,
                force_retry=args.force_retry,
                pilot=args.pilot,
                detect_only=args.detect_only,
                detect_timeout=args.detect_timeout,
            )
        )
    else:
        results = asyncio.run(
            main(
                args.input,
                dry_run=args.dry_run,
                limit=args.limit,
                pilot=args.pilot,
                detect_only=args.detect_only,
                detect_timeout=args.detect_timeout,
                fill_no_submit=args.fill_no_submit,
                submit_canary=args.submit_canary,
                message_version=args.message_version,
            )
        )
        if args.detect_only and results:
            write_detection_log(results, args.input)
        if args.fill_no_submit and results:
            import subprocess
            test_out = subprocess.run(
                [sys.executable, "-m", "unittest", "tests.test_fill_no_submit", "-v"],
                cwd=str(_BASE_DIR),
                capture_output=True,
                text=True,
            )
            tests_summary = (
                f"tests.test_fill_no_submit: {test_out.result.returncode == 0 and 'OK' or 'FAIL'}\n"
                f"```\n{test_out.stdout[-800:]}\n```"
            )
            write_canary_report(results[0], args.input, tests_summary=tests_summary)
