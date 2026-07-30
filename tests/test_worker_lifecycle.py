"""Regression tests for the dashboard worker-lifecycle guarantees.

Root cause fixed: the dashboard spawned a new worker whenever the DB heartbeat
looked stale, without checking whether a worker process was already alive, which
piled up orphan workers. _start_worker_process must now be idempotent (spawn only
when nothing is running) and reap duplicates.
"""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DB_PATH", "data/test_dashboard_company_data.db")
os.environ.setdefault("DASHBOARD_PASS", "")

import dashboard.app as dashboard_app


class TestWorkerLifecycle(unittest.TestCase):
    def test_reap_extra_workers_keeps_first(self):
        procs = [{"pid": 100}, {"pid": 200}, {"pid": 300}]
        with patch.object(dashboard_app, "_terminate_runtime_workers", return_value=[200, 300]) as term:
            reaped = dashboard_app._reap_extra_workers(procs)
        self.assertEqual(reaped, [200, 300])
        term.assert_called_once()
        self.assertEqual([p["pid"] for p in term.call_args[0][0]], [200, 300])

    def test_reap_noop_for_single_worker(self):
        with patch.object(dashboard_app, "_terminate_runtime_workers") as term:
            self.assertEqual(dashboard_app._reap_extra_workers([{"pid": 100}]), [])
            term.assert_not_called()

    def test_start_worker_reuses_existing_process(self):
        existing = [{"pid": 4242}]
        with patch.object(dashboard_app, "_iter_runtime_worker_processes", return_value=existing), \
             patch.object(dashboard_app, "_terminate_runtime_workers", return_value=[]) as term, \
             patch("dashboard.app.subprocess.Popen") as popen:
            result = dashboard_app._start_worker_process()
        popen.assert_not_called()
        term.assert_not_called()
        self.assertTrue(result["reused"])
        self.assertEqual(result["pid"], 4242)

    def test_start_worker_reaps_duplicates(self):
        existing = [{"pid": 10}, {"pid": 20}]
        with patch.object(dashboard_app, "_iter_runtime_worker_processes", return_value=existing), \
             patch.object(dashboard_app, "_terminate_runtime_workers", return_value=[20]) as term, \
             patch("dashboard.app.subprocess.Popen") as popen:
            result = dashboard_app._start_worker_process()
        popen.assert_not_called()
        self.assertTrue(result["reused"])
        self.assertEqual(result["pid"], 10)
        self.assertEqual(result["reaped"], [20])

    def test_start_worker_spawns_when_none_running(self):
        class FakeProc:
            pid = 9999

        with patch.object(dashboard_app, "_iter_runtime_worker_processes", return_value=[]), \
             patch.object(dashboard_app, "_worker_python_executable", return_value="venv/bin/python") as worker_python, \
             patch("dashboard.app.subprocess.Popen", return_value=FakeProc()) as popen:
            result = dashboard_app._start_worker_process()
        popen.assert_called_once()
        worker_python.assert_called_once_with()
        argv = popen.call_args[0][0]
        env = popen.call_args.kwargs["env"]
        self.assertEqual(argv[0], "venv/bin/python")
        self.assertEqual(argv[1], "-u")
        self.assertEqual(env["PYTHONUNBUFFERED"], "1")
        self.assertFalse(result["reused"])
        self.assertEqual(result["pid"], 9999)

    def test_graceful_restart_preserves_queued_jobs(self):
        before = {"runtime_processes": [{"pid": 111}]}
        after = {"runtime_processes": [], "workers": []}

        class FakeDb:
            def request_stop_pipeline_jobs(self, stop_queued=True):
                self.stop_queued = stop_queued
                return {"queued_stopped": 0, "stop_requested": 1}

        fake_db = FakeDb()
        with patch.object(dashboard_app, "_runtime_health_payload", side_effect=[before, after]), \
             patch.object(dashboard_app, "_terminate_runtime_workers", return_value=[111]) as term, \
             patch.object(dashboard_app, "_iter_runtime_worker_processes", return_value=[]), \
             patch.object(dashboard_app, "_start_worker_process", return_value={"pid": 222, "message": "started"}), \
             patch("dashboard.app.time.sleep") as sleep:
            payload = dashboard_app._request_graceful_worker_restart(fake_db)

        self.assertFalse(fake_db.stop_queued)
        term.assert_called_once_with(before["runtime_processes"])
        sleep.assert_called_once_with(1.0)
        self.assertEqual(payload["status"], "restarted")
        self.assertEqual(payload["stop_requested"], {"queued_stopped": 0, "stop_requested": 1})
        self.assertEqual(payload["signaled_pids"], [111])
        self.assertEqual(payload["started_pid"], 222)


if __name__ == "__main__":
    unittest.main()
