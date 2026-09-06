import http.client
import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from eidos.adapters.sqlite_jobs import SQLiteJobStore
from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.adapters.web_server import Runtime, make_handler
from eidos.application.life import Life
from eidos.domain.jobs import CognitionJob


class WebTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        life = Life(SQLiteEventStore(Path(self.directory.name) / "world.db"), StandInGateway())
        self.runtime = Runtime(life, interval=0.02)
        self.runtime.start()
        self.addCleanup(self.runtime.close)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.runtime))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        self.addCleanup(connection.close)
        connection.request(
            method,
            path,
            json.dumps(data) if data is not None else None,
            headers or ({"Content-Type": "application/json"} if data is not None else {}),
        )
        response = connection.getresponse()
        body = response.read()
        return response.status, body

    def test_live_loop_runs_pauses_and_serves_assets(self):
        self.request("POST", "/api/control", {"running": True, "minutes_per_tick": 60})
        deadline = time.monotonic() + 3
        while self.runtime.ticks < 2 and time.monotonic() < deadline:
            self.runtime.stop.wait(0.02)
        self.assertGreaterEqual(self.runtime.ticks, 2)
        status, body = self.request(
            "POST", "/api/control", {"running": False, "minutes_per_tick": 60}
        )
        paused_time = json.loads(body)["time"]
        self.assertIn(json.loads(body)["season"], {"winter", "spring", "summer", "autumn"})
        self.runtime.stop.wait(0.08)
        self.assertEqual(self.runtime.snapshot()["time"], paused_time)
        self.assertEqual(self.runtime.snapshot()["jobs"]["counts"]["queued"], 0)
        for path in ("/", "/operator", "/app.js", "/style.css", "/health", "/api/export"):
            status, body = self.request("GET", path)
            self.assertEqual(status, 200, path)
            self.assertTrue(body)
            if path == "/":
                self.assertIn(b'data-view="plans"', body)
                self.assertIn(b'id="calendar-list"', body)
                self.assertIn(b'id="catch-up"', body)
                self.assertIn(b'id="dream-inspiration"', body)
                self.assertIn(b'id="index-status"', body)
                self.assertIn(b'id="load-memories"', body)
                self.assertIn(b'class="controls" data-operator-only hidden', body)
            if path == "/operator":
                self.assertIn(b"data-operator-only hidden", body)
            if path == "/app.js":
                self.assertIn(b"function renderPlans()", body)
                self.assertIn(b"person.plan_scheduled_for", body)
                self.assertIn(b"state.scenes", body)
                self.assertIn(b"state.emotion", body)
                self.assertIn(b"function loadMemoryArchive", body)
                self.assertIn(b'window.location.pathname === "/operator"', body)
            if path == "/api/export":
                exported = json.loads(body)
                self.assertEqual(exported["schema"], 2)
                self.assertIn("correlation_id", exported["events"][0])
        status, body = self.request("GET", "/api/events?limit=3")
        page = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(len(page["events"]), 3)
        self.assertEqual(
            [item["revision"] for item in page["events"]],
            sorted((item["revision"] for item in page["events"]), reverse=True),
        )
        self.assertIsNotNone(page["next_before"])
        status, body = self.request("GET", f"/api/events?limit=3&before={page['next_before']}")
        second_page = json.loads(body)
        self.assertEqual(status, 200)
        self.assertFalse(
            {item["revision"] for item in page["events"]}
            & {item["revision"] for item in second_page["events"]}
        )
        status, _ = self.request("GET", "/api/events?limit=999")
        self.assertEqual(status, 400)
        status, body = self.request("GET", "/api/memories?limit=2&q=lamp&category=all")
        memories = json.loads(body)
        self.assertEqual(status, 200)
        self.assertLessEqual(len(memories["items"]), 2)
        self.assertEqual(memories["category"], "all")
        self.assertTrue(all(item.get("owner", "pathos") == "pathos" for item in memories["items"]))
        status, _ = self.request("GET", "/api/memories?limit=500")
        self.assertEqual(status, 400)

    def test_boundary_rejects_cross_origin_and_bad_requests(self):
        status, _ = self.request(
            "POST",
            "/api/step",
            {"hours": 1},
            {"Content-Type": "application/json", "Origin": "https://example.org"},
        )
        self.assertEqual(status, 403)

    def test_queued_job_can_be_cancelled_without_waiting_for_world_lock(self):
        jobs = SQLiteJobStore(Path(self.directory.name) / "queue.db")
        job = jobs.enqueue(
            CognitionJob(
                capability="murmur",
                aggregate_id="pathos",
                context={},
                expected_revision=0,
                simulated_at="2026-01-01T00:00:00+00:00",
                idempotency_key="cancel-from-ui",
                job_id=uuid4(),
                created_at=datetime.now(timezone.utc),
                available_at=datetime.now(timezone.utc),
            )
        )
        original = self.runtime.life.gateway
        self.runtime.life.gateway = SimpleNamespace(jobs=jobs, model="fixture")
        try:
            status, body = self.request("POST", f"/api/jobs/{job.job_id}/cancel", {})
        finally:
            self.runtime.life.gateway = original
        self.assertEqual(status, 200)
        self.assertEqual(jobs.get_job(job.job_id).status, "cancelled")
        self.assertEqual(json.loads(body)["jobs"]["counts"]["cancelled"], 1)

        status, _ = self.request("POST", "/api/step", {"hours": 999})
        self.assertEqual(status, 400)
        status, _ = self.request("GET", "/../../pyproject.toml")
        self.assertEqual(status, 404)
        status, _ = self.request("GET", "/api/state", headers={"Host": "evil.example"})
        self.assertEqual(status, 403)

    def test_snapshot_stays_responsive_during_model_work(self):
        entered = threading.Event()
        release = threading.Event()

        def slow_operation():
            with self.runtime.mutation():
                entered.set()
                release.wait(3)

        thread = threading.Thread(target=slow_operation)
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            started = time.monotonic()
            status, body = self.request("GET", "/api/state")
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)["runtime"]["working"])
            self.assertLess(time.monotonic() - started, 1)
        finally:
            release.set()
            thread.join()

    def test_chat_and_step_work_through_http(self):
        status, _ = self.request(
            "POST", "/api/chat", {"text": "Where are you?", "request_id": "http-1"}
        )
        self.assertEqual(status, 200)
        status, body = self.request("POST", "/api/step", {"hours": 1})
        snapshot = json.loads(body)
        self.assertEqual(snapshot["pathos"]["location_id"], "cafe")
        self.assertEqual(len(snapshot["conversations"]), 2)

    def test_user_can_opt_in_and_back_out_of_in_app_outreach(self):
        self.assertFalse(self.runtime.snapshot()["outreach"]["enabled"])
        status, body = self.request("POST", "/api/outreach", {"enabled": True})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["outreach"]["enabled"])
        status, body = self.request("POST", "/api/outreach", {"enabled": False})
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["outreach"]["enabled"])

    def test_live_visit_and_immediate_exchange_work_through_http(self):
        status, body = self.request("POST", "/api/visit", {"request_id": "http-visit-1"})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["communication"]["live_scene_id"])
        status, body = self.request(
            "POST", "/api/chat", {"text": "Can we talk?", "request_id": "http-live-1"}
        )
        snapshot = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(snapshot["communication"]["live_turn_count"], 2)
        self.assertEqual(snapshot["conversations"][-1]["speaker"], "pathos")
        status, body = self.request("POST", "/api/visit/end", {"request_id": "http-leave-1"})
        self.assertEqual(status, 200)
        self.assertIsNone(json.loads(body)["communication"]["live_scene_id"])

    def test_catch_up_requires_explicit_preview_and_request(self):
        before = self.runtime.snapshot()["time"]
        status, body = self.request("GET", "/api/catch-up/preview?hours=2")
        preview = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(preview["hours"], 2.0)
        self.assertEqual(self.runtime.snapshot()["time"], before)
        status, body = self.request("POST", "/api/catch-up", {"hours": 2})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["time"], preview["ends_at"])
        self.assertTrue(
            any(event.kind == "catch_up.completed" for event in self.runtime.life.history())
        )
        self.assertTrue(json.loads(body)["catch_up_summaries"])

    def test_restart_restores_time_but_requires_explicit_resume(self):
        self.runtime.close()
        with self.runtime.lock:
            self.runtime.life.configure(True, 60)
            before = self.runtime.life.snapshot()["time"]
        replacement = Runtime(self.runtime.life, interval=0.02)
        replacement.start()
        self.addCleanup(replacement.close)
        self.assertFalse(replacement.snapshot()["config"]["running"])
        replacement.stop.wait(0.05)
        self.assertEqual(replacement.snapshot()["time"], before)
