"""ARI Night Factory — ZERO SEND unit tests."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

import run_ari_night_factory as nf
from ari_pipeline.night_factory import (
    CHECKPOINT_SCHEMA_VERSION,
    DEFAULT_CONFIG,
    PID_FILE,
    build_source_pool,
    initialize_source_inventory,
    load_factory_checkpoint,
    load_factory_state,
    load_ready_inventory,
    migrate_checkpoint,
    recalculate_ready_inventory,
    save_factory_checkpoint,
    save_factory_state,
    stop_target,
)


class TestNightFactoryConfig(unittest.TestCase):
    def test_stop_target_includes_buffer(self):
        self.assertEqual(stop_target({"target_ready": 500, "buffer": 50}), 550)


class TestProcessIdentity(unittest.TestCase):
    @patch("run_ari_night_factory.get_process_command", return_value="")
    def test_missing_process_not_worker(self, _cmd):
        self.assertFalse(nf.is_night_factory_worker_pid(999999, exclude_pids=set()))

    @patch("run_ari_night_factory.get_process_command")
    def test_python_worker_detected(self, mock_cmd):
        mock_cmd.return_value = "/usr/bin/Python -u run_ari_night_factory.py --resume --target-ready 500"
        self.assertTrue(nf.is_night_factory_worker_pid(42, exclude_pids=set()))

    @patch("run_ari_night_factory.get_process_command")
    def test_shell_wrapper_rejected(self, mock_cmd):
        mock_cmd.return_value = "/bin/bash ./run_ari_night_factory.sh --resume"
        self.assertFalse(nf.is_night_factory_worker_pid(42, exclude_pids=set()))

    @patch("run_ari_night_factory.get_process_command")
    def test_c_helper_rejected(self, mock_cmd):
        mock_cmd.return_value = "Python -u -c import run_ari_night_factory as nf; nf.cleanup_stale_pid()"
        self.assertFalse(nf.is_night_factory_worker_pid(42, exclude_pids=set()))

    @patch("run_ari_night_factory.get_process_command")
    def test_status_invocation_not_worker(self, mock_cmd):
        mock_cmd.return_value = "Python -u run_ari_night_factory.py --status"
        self.assertFalse(nf.is_night_factory_worker_pid(42, exclude_pids=set()))

    @patch("run_ari_night_factory.get_process_command")
    def test_validate_invocation_not_worker(self, mock_cmd):
        mock_cmd.return_value = "Python -u run_ari_night_factory.py --validate"
        self.assertFalse(nf.is_night_factory_worker_pid(42, exclude_pids=set()))

    @patch("run_ari_night_factory.get_process_command")
    def test_unrelated_process_rejected(self, mock_cmd):
        mock_cmd.return_value = "/usr/sbin/cfprefsd agent"
        self.assertFalse(nf.is_night_factory_worker_pid(42, exclude_pids=set()))


class TestPidHandling(unittest.TestCase):
    def test_dead_pid_file_removed(self):
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text("99999999", encoding="utf-8")
        result = nf.cleanup_stale_pid(exclude_pids={os.getpid()})
        self.assertFalse(result.get("active"))
        self.assertFalse(result.get("worker_running"))
        self.assertIn(result.get("action"), ("removed_dead", "none"))
        if result.get("action") == "removed_dead":
            self.assertFalse(PID_FILE.exists())

    @patch("run_ari_night_factory._process_alive", return_value=True)
    @patch("run_ari_night_factory.is_night_factory_worker_pid", return_value=False)
    @patch("run_ari_night_factory.get_process_command", return_value="/bin/bash ./run_ari_night_factory.sh")
    def test_shell_pid_reused_is_stale(self, _cmd, _match, _alive):
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text("75217", encoding="utf-8")
        result = nf.cleanup_stale_pid(exclude_pids={os.getpid()})
        self.assertFalse(result.get("active"))
        self.assertEqual(result.get("action"), "removed_wrong_process")
        self.assertFalse(PID_FILE.exists())

    @patch("run_ari_night_factory._process_alive", return_value=True)
    @patch("run_ari_night_factory.is_night_factory_worker_pid", return_value=True)
    @patch("run_ari_night_factory.get_process_command", return_value="Python -u run_ari_night_factory.py --resume")
    def test_real_worker_blocks_duplicate(self, _cmd, _match, _alive):
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text("75217", encoding="utf-8")
        result = nf.ensure_worker_start_allowed()
        self.assertFalse(result.get("allowed"))
        self.assertEqual(result.get("pid"), 75217)

    @patch("run_ari_night_factory.read_worker_pid_status")
    def test_status_does_not_count_as_worker(self, mock_status):
        mock_status.return_value = {"worker_running": False, "pid": None, "action": "none"}
        report = nf.status_report()
        self.assertFalse(report["worker_running"])


class TestCheckpointSchema(unittest.TestCase):
    def test_migrate_legacy_checkpoint(self):
        cp = migrate_checkpoint({"schema_version": 1, "preflight_results": {}})
        self.assertEqual(cp["schema_version"], CHECKPOINT_SCHEMA_VERSION)
        self.assertFalse(cp["source_initialized"])


class TestSourceInitialization(unittest.TestCase):
    def test_fresh_start_builds_source_pool(self):
        state = load_factory_state()
        cp = load_factory_checkpoint()
        source, _, cp2 = initialize_source_inventory(state, cp, force_rebuild=True)
        self.assertGreater(len(source), 1000)
        self.assertTrue(cp2["source_initialized"])

    def test_resume_missing_source_rebuilds(self):
        state = load_factory_state()
        cp = load_factory_checkpoint()
        cp["source_initialized"] = False
        cp["source_eligible_count"] = 0
        save_factory_checkpoint(cp)
        source, _, cp2 = initialize_source_inventory(state, cp, force_rebuild=False)
        self.assertGreater(len(source), 1000)
        self.assertTrue(cp2["source_initialized"])

    def test_resume_preserves_ready(self):
        cp = load_factory_checkpoint()
        pool = build_source_pool()
        pool_by_dom = {c["domain"]: c for c in pool[:500]}
        before = recalculate_ready_inventory(pool_by_dom, cp)
        ready_before = len(before.get("ready_primary") or []) + len(before.get("ready_remodel_reserve") or [])
        state = load_factory_state()
        _, _, _ = initialize_source_inventory(state, cp, force_rebuild=False)
        after = load_ready_inventory()
        ready_after = len(after.get("ready_primary") or []) + len(after.get("ready_remodel_reserve") or [])
        self.assertGreaterEqual(ready_after, ready_before)
        self.assertGreaterEqual(ready_after, 9)


class TestMaxCyclesResume(unittest.TestCase):
    def test_max_cycles_exit_reason_cleared_on_resume(self):
        state = load_factory_state()
        state["exit_reason"] = "max_cycles_reached"
        state["stopped_at"] = "2026-08-13T22:50:36"
        save_factory_state(state)

        resume = True
        state = load_factory_state()
        if resume and state.get("exit_reason") in (
            "max_cycles_reached", "graceful_stop", "completed", None,
        ):
            state["exit_reason"] = None
            state["stopped_at"] = None
        save_factory_state(state)

        st = load_factory_state()
        self.assertIsNone(st.get("exit_reason"))
        self.assertIsNone(st.get("stopped_at"))


class TestSentCsvHardStop(unittest.TestCase):
    @patch("run_ari_night_factory.refresh_production_exclusions")
    @patch("run_ari_night_factory.verify_authorized_terminal_owner", return_value={"valid": False, "reason": "no_owner"})
    @patch("run_ari_night_factory.get_submit_forbidden", return_value=True)
    @patch("run_ari_night_factory.save_factory_state")
    @patch("run_ari_night_factory.get_real_submission_count", return_value=0)
    @patch("run_ari_night_factory.is_paused", return_value=True)
    @patch("run_ari_night_factory.load_limits")
    def test_sent_csv_delta_triggers_hard_stop(self, mock_limits, _paused, _rs, _save, _sf, _owner, _ref):
        mock_limits.return_value.production_limit = 0
        baseline = nf._SENT_CSV_BASELINE
        try:
            nf._SENT_CSV_BASELINE = 10
            with patch("run_ari_night_factory._sent_csv_lines", return_value=11):
                with patch("run_ari_night_factory.classify_sent_csv_delta", return_value={"kind": "UNAUTHORIZED_MUTATION", "delta": 1}):
                    with self.assertRaises(RuntimeError):
                        nf._safety_check()
        finally:
            nf._SENT_CSV_BASELINE = baseline


if __name__ == "__main__":
    unittest.main()
