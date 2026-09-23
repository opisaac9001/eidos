import asyncio
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from eidos.adapters.durable_gateway import DurableModelGateway
from eidos.adapters.http_gateway import HTTPModelGateway
from eidos.adapters.sqlite_jobs import SQLiteJobStore
from eidos.application.cognition import perform, request_for
from eidos.application.cognition_supervisor import CognitionSupervisor
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

    def test_resident_relationship_context_stays_with_its_owner(self):
        private = {"owner": "mara", "about": "pathos", "recollections": ["private impression"]}
        for speaker, audience, allowed in (
            ("mara", "pathos", True),
            ("ellis", "pathos", False),
            ("pathos", "mara", False),
            ("mara", "ellis", False),
        ):
            request = request_for(
                "firmament",
                {
                    "scene_speaker": speaker,
                    "scene_audience": audience,
                    "personal_relationship_context": private,
                },
            )
            asyncio.run(self.gateway.generate(request))
            context = json.loads(self.payload["messages"][1]["content"])
            self.assertEqual("personal_relationship_context" in context, allowed)

    def test_real_http_contract_and_role_isolation(self):
        result = asyncio.run(self.gateway.generate(self.request()))
        self.assertEqual(self.path, "/v1/chat/completions")
        self.assertEqual(
            json.loads(self.payload["messages"][1]["content"]), {"experience": "hello"}
        )
        self.assertEqual(self.payload["response_format"]["type"], "json_schema")
        self.assertEqual(result.output_tokens, 5)
        self.assertEqual(result.backend, "openai-compatible")
        self.assertNotIn("reasoning_effort", self.payload)
        self.assertNotIn("Patrick's authored background", self.payload["messages"][0]["content"])

    def test_explicit_reasoning_control_does_not_change_default_routes(self):
        self.gateway.reasoning_effort = "none"
        asyncio.run(self.gateway.generate(self.request()))
        self.assertEqual(self.payload["reasoning_effort"], "none")

    def test_partial_memory_guidance_preserves_subjective_confidence(self):
        context = {
            "message": "Who did you meet?",
            "memory_recollections": [{"text": "I met Mara", "felt_confidence": 0.95}],
            "operator_hidden_truth": "The original event named someone else",
        }
        asyncio.run(self.gateway.generate(request_for("pathos", context)))
        system = self.payload["messages"][0]["content"]
        supplied = json.loads(self.payload["messages"][1]["content"])
        self.assertIn("partial view, not a complete inventory", system)
        self.assertIn("missing evidence supports only not remembering", system)
        self.assertIn("answer firmly from it, even if it is mistaken", system)
        self.assertEqual(supplied["memory_recollections"], context["memory_recollections"])
        self.assertNotIn("operator_hidden_truth", supplied)

    def test_scene_speaker_keeps_other_peoples_words_separate(self):
        context = {
            "scene_mode": True,
            "scene_speaker": "mara",
            "scene_audience": "pathos",
            "prior_turns": [{"speaker": "pathos", "text": "I've got to leave."}],
            "memories": ["Private Patrick memory must not reach Mara"],
        }
        asyncio.run(self.gateway.generate(request_for("firmament", context)))
        supplied = json.loads(self.payload["messages"][1]["content"])
        self.assertEqual(supplied["prior_turns"], context["prior_turns"])
        self.assertNotIn("memories", supplied)
        self.assertIn("not a narrator", self.payload["messages"][0]["content"])

    def test_dream_context_and_creativity_reach_the_actual_http_request(self):
        context = {
            "time": "2026-01-02T02:00:00+00:00",
            "recent_dreams": [{"text": "In a dream the stairs folded."}],
            "memories": ["I left a letter unfinished."],
            "private_npc_truth": "not allowed",
        }
        asyncio.run(self.gateway.generate(request_for("oneiros", context)))
        sent = json.loads(self.payload["messages"][1]["content"])
        self.assertEqual(sent["recent_dreams"], context["recent_dreams"])
        self.assertEqual(sent["time"], context["time"])
        self.assertNotIn("private_npc_truth", sent)
        self.assertEqual(self.payload["temperature"], 0.8)
        self.assertIn("fictional dream content", self.payload["messages"][0]["content"])

    def test_blended_persona_is_shared_only_by_personal_performers(self):
        personal = {
            "pathos",
            "murmur",
            "reflection",
            "oneiros",
            "pathos_deliberation",
            "pathos_agency",
            "pathos_project",
        }
        for role in sorted(personal | {"npc_agency", "npc_backstory", "chronicler", "moira"}):
            with self.subTest(role=role):
                request = ModelRequest(
                    capability=role,
                    messages=(ModelMessage("user", "{}"),),
                    output_schema={"type": "object"},
                )
                asyncio.run(self.gateway.generate(request))
                system = self.payload["messages"][0]["content"]
                self.assertEqual("Patrick's authored background" in system, role in personal)

    def test_waking_thoughts_and_memory_copying_keep_distinct_settings(self):
        asyncio.run(self.gateway.generate(request_for("murmur", {"memories": ["I made tea."]})))
        self.assertEqual(self.payload["temperature"], 0.55)
        self.assertEqual(self.payload["max_tokens"], 128)
        self.assertIn("not a message to anyone", self.payload["messages"][0]["content"])
        asyncio.run(self.gateway.generate(request_for("mnemosyne", {"experience": "I made tea."})))
        self.assertEqual(self.payload["temperature"], 0)

    def test_supervised_sqlite_job_reaches_real_http_with_its_saved_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = SQLiteJobStore(Path(directory) / "jobs.sqlite3")
            supervisor = CognitionSupervisor(jobs, self.gateway, lambda _: 0)
            durable = DurableModelGateway(self.gateway, jobs, lambda _: 0, supervisor=supervisor)
            request = self.request()
            try:
                result = asyncio.run(durable.generate(request))
            finally:
                durable.close()
            self.assertEqual(json.loads(result.content), {"text": "hello"})
            self.assertEqual(
                self.payload["response_format"]["json_schema"]["schema"],
                {"type": "object"},
            )
            saved = jobs.get_job(request.correlation_id)
            self.assertEqual(saved.status, "completed")
            self.assertEqual(saved.resolved_model, "test-model")

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

    def test_pathos_voice_is_casual_and_keeps_recent_dialogue(self):
        request = ModelRequest(
            capability="pathos",
            messages=(
                ModelMessage(
                    "user",
                    json.dumps(
                        {
                            "message": "ok so what have you been up to",
                            "location": "Juniper Café",
                            "ambient_presence": {"estimated_people": 4},
                            "voice": {"cadence": "easy", "target_words": 18},
                            "recent_dialogue": [
                                {"speaker": "you", "text": "you still at the cafe?"},
                                {"speaker": "pathos", "text": "Yeah, for a bit."},
                            ],
                            "remembered_preferences": [{"topic": "coffee", "stance": "likes"}],
                            "relationship_repairs": [{"status": "open"}],
                            "cognitive_workspace": [
                                {
                                    "from_faculty": "murmur",
                                    "content": "Maybe don't rush this answer.",
                                    "epistemic_status": "inner_monologue",
                                    "action_authority": False,
                                }
                            ],
                        }
                    ),
                ),
            ),
            output_schema={"type": "object"},
        )

        asyncio.run(self.gateway.generate(request))

        context = json.loads(self.payload["messages"][1]["content"])
        self.assertEqual(context["recent_dialogue"][-1]["text"], "Yeah, for a bit.")
        self.assertEqual(context["voice"]["target_words"], 18)
        self.assertEqual(context["ambient_presence"]["estimated_people"], 4)
        self.assertEqual(context["remembered_preferences"][0]["topic"], "coffee")
        self.assertEqual(context["relationship_repairs"][0]["status"], "open")
        self.assertEqual(context["cognitive_workspace"][0]["from_faculty"], "murmur")
        self.assertFalse(context["cognitive_workspace"][0]["action_authority"])
        system = self.payload["messages"][0]["content"]
        self.assertIn("relaxed person talking", system)
        self.assertIn("Patrick Shaw", system)
        self.assertIn("grew up in Wye", system)
        self.assertIn("supplied learned preferences and experience take precedence", system)
        self.assertIn("do not deceive the user", system)
        self.assertIn("Unknown does not mean it never happened", system)
        self.assertIn(
            "explicitly supplied mistaken recollection remains his sincere belief", system
        )
        self.assertIn("nickname some close friends from university use", system)
        self.assertIn("stable internal actor identifier remains pathos", system)
        self.assertIn("Do not end every reply with a question", system)
        self.assertIn("never imitate spelling mistakes", system)
        self.assertIn("If they decline advice", system)
        self.assertIn("not facts, mandatory phrases", system)
        self.assertIn("without restarting the story", system)

    def test_pathos_receives_felt_memory_confidence_without_hidden_source_truth(self):
        request = ModelRequest(
            capability="pathos",
            messages=(
                ModelMessage(
                    "user",
                    json.dumps(
                        {
                            "message": "What do you remember?",
                            "memories": ["I remember the cup was green."],
                            "memory_recollections": [
                                {
                                    "text": "I remember the cup was green.",
                                    "felt_confidence": 0.92,
                                    "detail_level": "clear",
                                    "remembered_person_id": "rowan",
                                    "remembered_location_id": "workshop",
                                    "remembered_at": "2026-02-01T12:00:00+00:00",
                                }
                            ],
                            "source_confidence": 0.35,
                        }
                    ),
                ),
            ),
            output_schema={"type": "object"},
        )

        asyncio.run(self.gateway.generate(request))

        context = json.loads(self.payload["messages"][1]["content"])
        self.assertEqual(context["memory_recollections"][0]["felt_confidence"], 0.92)
        self.assertEqual(context["memory_recollections"][0]["remembered_person_id"], "rowan")
        self.assertEqual(
            context["memory_recollections"][0]["remembered_at"],
            "2026-02-01T12:00:00+00:00",
        )
        self.assertNotIn("source_confidence", context)
        self.assertIn("subjective certainty", self.payload["messages"][0]["content"])

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
                            "known_resources": {"community-sketch-basket": "park"},
                            "external_signals": {"signal-1": "Attributed weather report"},
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
        self.assertEqual(context["external_signals"], {"signal-1": "Attributed weather report"})
        self.assertNotIn("private_state", context)

    def test_multi_step_project_gets_bounded_larger_envelope_and_filtered_context(self):
        request = ModelRequest(
            capability="pathos_project",
            messages=(
                ModelMessage(
                    "user",
                    json.dumps(
                        {
                            "time": "2026-01-16T09:00:00+00:00",
                            "needs": {"curiosity": 0.8},
                            "preferences": ["spending reflective time outdoors"],
                            "traits": {"openness": 0.69},
                            "semantic_expectations": [
                                {
                                    "text": "I expect Mara is usually at the cafe.",
                                    "confidence": 0.61,
                                    "epistemic_status": "subjective_generalization",
                                }
                            ],
                            "self_concepts": [
                                {
                                    "text": "Lately, my follow-through has felt uneven.",
                                    "confidence": 0.55,
                                    "epistemic_status": "subjective_self_interpretation",
                                }
                            ],
                            "skills": [
                                {
                                    "skill_id": "field_recording",
                                    "level": 0.47,
                                    "status": "rusty",
                                    "authority": "capability_signal_only",
                                }
                            ],
                            "habits": [
                                {
                                    "activity_type": "sketching_walk",
                                    "location_id": "park",
                                    "time_band": "morning",
                                    "strength": 0.3,
                                    "authority": "soft_pattern_only",
                                }
                            ],
                            "known_places": {"home": {"name": "Home"}},
                            "calendar": [],
                            "private_operator_field": "must not pass",
                        }
                    ),
                ),
            ),
            temperature=0.9,
            max_output_tokens=900,
            output_schema={"type": "object", "properties": {}},
        )
        asyncio.run(self.gateway.generate(request))
        self.assertEqual(self.payload["max_tokens"], 640)
        context = json.loads(self.payload["messages"][1]["content"])
        self.assertEqual(context["needs"], {"curiosity": 0.8})
        self.assertEqual(context["preferences"], ["spending reflective time outdoors"])
        self.assertEqual(context["traits"], {"openness": 0.69})
        self.assertEqual(
            context["semantic_expectations"][0]["epistemic_status"],
            "subjective_generalization",
        )
        self.assertEqual(
            context["self_concepts"][0]["epistemic_status"],
            "subjective_self_interpretation",
        )
        self.assertEqual(context["skills"][0]["status"], "rusty")
        self.assertEqual(context["skills"][0]["authority"], "capability_signal_only")
        self.assertEqual(context["habits"][0]["authority"], "soft_pattern_only")
        self.assertIn("slowly learned preferences", self.payload["messages"][0]["content"])
        self.assertIn("not obligations", self.payload["messages"][0]["content"])
        self.assertIn("not world facts", self.payload["messages"][0]["content"])
        self.assertNotIn("private_operator_field", context)

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
