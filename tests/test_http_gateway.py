import asyncio
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from eidos.adapters.http_gateway import HTTPModelGateway
from eidos.application.cognition import perform
from eidos.ports.model_gateway import ModelMessage, ModelRequest


class GatewayTests(unittest.TestCase):
    def setUp(self):
        owner = self
        self.status = 200
        self.envelope = {
            "model": "test-model",
            "choices": [{"message": {"content": '{"text":"hello"}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                owner.path = self.path
                owner.payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(owner.status)
                self.end_headers()
                self.wfile.write(json.dumps(owner.envelope).encode())

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.gateway = HTTPModelGateway(
            f"http://127.0.0.1:{self.server.server_port}/v1", "test-model"
        )

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self):
        return ModelRequest(
            capability="mnemosyne",
            messages=(
                ModelMessage("user", json.dumps({"experience": "hello", "message": "irrelevant"})),
            ),
            output_schema={"type": "object"},
        )

    def test_real_http_contract_and_role_isolation(self):
        result = asyncio.run(self.gateway.generate(self.request()))
        self.assertEqual(self.path, "/v1/chat/completions")
        self.assertEqual(
            json.loads(self.payload["messages"][1]["content"]), {"experience": "hello"}
        )
        self.assertEqual(self.payload["response_format"]["type"], "json_schema")
        self.assertEqual(result.output_tokens, 5)
        self.assertEqual(result.backend, "openai-compatible")

    def test_pathos_receives_owned_beliefs_as_uncertain_context(self):
        request = ModelRequest(
            capability="pathos",
            messages=(
                ModelMessage(
                    "user",
                    json.dumps(
                        {
                            "message": "Can Mara be trusted?",
                            "location": "Workshop",
                            "beliefs": [
                                {
                                    "subject": "mara",
                                    "predicate": "reliability",
                                    "value": "reliable",
                                    "confidence": 0.68,
                                    "status": "contested",
                                    "alternative": "unreliable",
                                }
                            ],
                            "private_operator_field": "must not pass",
                        }
                    ),
                ),
            ),
            output_schema={"type": "object"},
        )
        asyncio.run(self.gateway.generate(request))
        context = json.loads(self.payload["messages"][1]["content"])
        self.assertEqual(context["beliefs"][0]["status"], "contested")
        self.assertNotIn("private_operator_field", context)

    def test_open_world_director_keeps_creative_temperature_and_strict_schema(self):
        request = ModelRequest(
            capability="moira_event",
            messages=(
                ModelMessage(
                    "user",
                    json.dumps(
                        {
                            "time": "2026-01-07T18:00:00+00:00",
                            "season": "winter",
                            "weather": "Clear",
                            "known_locations": ["park"],
                            "recent_events": [],
                            "permission": "invent fiction",
                            "private_state": "must not pass",
                        }
                    ),
                ),
            ),
            temperature=0.85,
            max_output_tokens=300,
            output_schema={"type": "object", "properties": {}},
        )
        asyncio.run(self.gateway.generate(request))
        self.assertEqual(self.payload["temperature"], 0.85)
        self.assertEqual(self.payload["max_tokens"], 300)
        system = self.payload["messages"][0]["content"]
        self.assertIn("conforming exactly to the supplied schema", system)
        self.assertIn("do not select from a fixed menu", system)
        context = json.loads(self.payload["messages"][1]["content"])
        self.assertNotIn("private_state", context)

    def test_incomplete_and_invalid_envelopes_rejected(self):
        self.envelope["choices"][0]["finish_reason"] = "length"
        with self.assertRaises(ValueError):
            asyncio.run(self.gateway.generate(self.request()))
        self.envelope = {}
        with self.assertRaises(ValueError):
            asyncio.run(self.gateway.generate(self.request()))

    def test_failure_does_not_fall_back(self):
        self.status = 503
        pending = []
        result = asyncio.run(
            perform(
                self.gateway,
                "mnemosyne",
                {"experience": "hello"},
                "2026-01-01T08:00:00+00:00",
                pending,
            )
        )
        self.assertIsNone(result)
        self.assertTrue(any(e.kind == "role.failed" for e in pending))

    def test_fabricated_memory_rejected(self):
        pending = []
        result = asyncio.run(
            perform(
                self.gateway,
                "mnemosyne",
                {"experience": "different source"},
                "2026-01-01T08:00:00+00:00",
                pending,
            )
        )
        self.assertIsNone(result)

    def test_endpoint_credentials_rejected(self):
        with self.assertRaises(ValueError):
            HTTPModelGateway("http://user:secret@example.com/v1", "model")
