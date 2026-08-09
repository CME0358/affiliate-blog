#!/usr/bin/env python3
"""
自動運用ジョブの停止/再開（ファイルベース）。

使い方:
  python3 automation_control.py pause JOB_ID
  python3 automation_control.py resume JOB_ID
  python3 automation_control.py toggle JOB_ID
  python3 automation_control.py status [JOB_ID]
  python3 automation_control.py check JOB_ID        # 停止中なら exit 1
  python3 automation_control.py sync-defaults       # default OFF をファイルに反映
  python3 automation_control.py enforce             # 停止中ジョブのプロセス終了
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from automation_registry import AUTOMATION_JOBS, JOBS_BY_ID
from automation_state import AUTOMATION_STATE_PATH, is_paused, set_paused, sync_defaults


def _kill_matching(patterns: tuple[str, ...]) -> list[str]:
    if not patterns:
        return []
    killed: list[str] = []
    try:
        out = subprocess.check_output(["ps", "aux"], text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return killed
    my_pid = os.getpid()
    for line in out.splitlines()[1:]:
        if any(p in line for p in patterns):
            if "automation_control.py enforce" in line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                pid = int(parts[1])
            except ValueError:
                continue
            if pid == my_pid:
                continue
            try:
                os.kill(pid, 15)
                killed.append(f"pid={pid} ({patterns[0]})")
            except OSError:
                pass
    return killed


def _bootout_launchd(label: str) -> bool:
    if not label or label in ("—", "cron 未確認") or "等" in label:
        return False
    uid = os.getuid()
    domain = f"gui/{uid}"
    target = f"{domain}/{label}"
    r = subprocess.run(
        ["launchctl", "bootout", target],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def cmd_pause(job_id: str) -> int:
    set_paused(job_id, True, by="automation_control.py pause")
    job = JOBS_BY_ID[job_id]
    killed = _kill_matching(job.kill_patterns)
    if killed:
        print(f"   終了: {', '.join(killed)}")
    print(f"⏸  {job_id} を停止しました")
    print(f"   状態ファイル: {AUTOMATION_STATE_PATH}")
    return 0


def cmd_resume(job_id: str) -> int:
    set_paused(job_id, False, by="automation_control.py resume")
    print(f"▶️  {job_id} を再開しました")
    return 0


def cmd_toggle(job_id: str) -> int:
    if is_paused(job_id):
        return cmd_resume(job_id)
    return cmd_pause(job_id)


def cmd_status(job_id: str | None) -> int:
    ids = [job_id] if job_id else [j.id for j in AUTOMATION_JOBS]
    for jid in ids:
        if jid not in JOBS_BY_ID:
            print(f"未知のジョブ ID: {jid}", file=sys.stderr)
            return 1
        job = JOBS_BY_ID[jid]
        paused = is_paused(jid)
        label = "停止中" if paused else "稼働中"
        print(f"{jid}: {label} (default={'ON' if job.default_on else 'OFF'})")
    return 0


def cmd_check(job_id: str) -> int:
    if is_paused(job_id):
        print(f"⏸  {job_id} は停止中のため実行しません")
        return 1
    return 0


def cmd_sync_defaults() -> int:
    changed = sync_defaults()
    if changed:
        print("sync-defaults: 停止に設定 → " + ", ".join(changed))
    else:
        print("sync-defaults: 変更なし")
    return 0


def cmd_enforce() -> int:
    """停止中ジョブのプロセス終了 + default OFF の launchd bootout。"""
    sync_defaults(by="automation_control.py enforce")
    killed_all: list[str] = []
    booted: list[str] = []
    for job in AUTOMATION_JOBS:
        if not is_paused(job.id):
            continue
        killed_all.extend(_kill_matching(job.kill_patterns))
        if not job.default_on and job.launchd.startswith("com."):
            if _bootout_launchd(job.launchd):
                booted.append(job.launchd)
    if killed_all:
        print("enforce: プロセス終了 → " + ", ".join(killed_all))
    if booted:
        print("enforce: launchd bootout → " + ", ".join(booted))
    if not killed_all and not booted:
        print("enforce: 対象なし")
    return 0


def main() -> int:
    job_ids = sorted(JOBS_BY_ID)
    ap = argparse.ArgumentParser(description="自動運用ジョブの停止/再開（ファイルベース）")
    sub = ap.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("pause", "ジョブを停止"),
        ("resume", "ジョブを再開"),
        ("toggle", "ジョブをトグル"),
        ("check", "停止中なら exit 1（launchd ラッパー用）"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("job_id", choices=job_ids)

    p_status = sub.add_parser("status", help="状態表示")
    p_status.add_argument("job_id", nargs="?", choices=job_ids)

    sub.add_parser("sync-defaults", help="default OFF のジョブを停止状態に揃える")
    sub.add_parser("enforce", help="停止中ジョブを即時停止（プロセス終了・launchd bootout）")

    args = ap.parse_args()
    if args.command == "pause":
        return cmd_pause(args.job_id)
    if args.command == "resume":
        return cmd_resume(args.job_id)
    if args.command == "toggle":
        return cmd_toggle(args.job_id)
    if args.command == "status":
        return cmd_status(args.job_id)
    if args.command == "check":
        return cmd_check(args.job_id)
    if args.command == "sync-defaults":
        return cmd_sync_defaults()
    if args.command == "enforce":
        return cmd_enforce()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
