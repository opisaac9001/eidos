import http.client
import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.adapters.web_server import Runtime, make_handler
from eidos.application.life import Life


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
        self.runtime.stop.wait(0.08)
        self.assertEqual(self.runtime.snapshot()["time"], paused_time)
        for path in ("/", "/app.js", "/style.css", "/health", "/api/export"):
            status, body = self.request("GET", path)
            self.assertEqual(status, 200, path)
            self.assertTrue(body)

    def test_boundary_rejects_cross_origin_and_bad_requests(self):
        status, _ = self.request(
            "POST",
            "/api/step",
            {"hours": 1},
            {"Content-Type": "application/json", "Origin": "https://example.org"},
        )
        self.assertEqual(status, 403)

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
