import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from eidos.adapters.durable_gateway import DurableModelGateway
from eidos.adapters.sqlite_jobs import SQLiteJobStore
from eidos.ports.model_gateway import ModelMessage, ModelRequest, ModelResponse


class CountingGateway:
    model = "fixture"

    def __init__(self, content='{"text":"remembered result"}'):
        self.content = content
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        return ModelResponse(self.content, self.model, "fixture", "stop")


class DurableGatewayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.jobs = SQLiteJobStore(Path(self.directory.name) / "world.sqlite3")
        self.revision = 3

    def request(self):
        return ModelRequest(
            capability="murmur",
            messages=(
                ModelMessage(
                    "user",
                    json.dumps(
                        {
                            "time": "2026-01-01T08:00:00+00:00",
                            "location": "home",
                            "memories": [],
                        }
                    ),
                ),
            ),
            output_schema={"type": "object"},
        )

    def test_completed_work_is_reused_after_gateway_recreation(self):
        inner = CountingGateway()
        gateway = DurableModelGateway(inner, self.jobs, lambda _: self.revision)
        first = asyncio.run(gateway.generate(self.request()))
        second_gateway = DurableModelGateway(inner, SQLiteJobStore(self.jobs.path), lambda _: 3)
        second = asyncio.run(second_gateway.generate(self.request()))
        self.assertEqual(json.loads(first.content)["text"], "remembered result")
        self.assertEqual(json.loads(second.content)["text"], "remembered result")
        self.assertEqual(second.backend, "durable-cache")
        self.assertEqual(inner.calls, 1)
        self.assertEqual(len(self.jobs.list_jobs()), 1)

    def test_invalid_result_is_terminal_and_never_cached_as_success(self):
        inner = CountingGateway('{"wrong":"shape"}')
        gateway = DurableModelGateway(inner, self.jobs, lambda _: self.revision)
        with self.assertRaises(ValueError):
            asyncio.run(gateway.generate(self.request()))
        job = self.jobs.list_jobs()[0]
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.error_code, "invalid_completion")


if __name__ == "__main__":
    unittest.main()
