"""Real providers: structured-output fallbacks, retries, backups, budgets and settings."""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from eidos.adapters.http_gateway import HTTPModelGateway
from eidos.adapters.model_settings import (
    ConfiguredGateway,
    SettingsError,
    SwitchingGateway,
    check_model,
    validate,
)
from eidos.adapters.standin_gateway import StandInGateway
from eidos.ports.model_gateway import ModelMessage, ModelRequest

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["leans", "source_quote"],
    "properties": {"leans": {"type": "string"}, "source_quote": {"type": "string"}},
}


def completion(content: str, finish: str = "stop") -> dict:
    return {
        "model": "fake",
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 100},
    }


class FakeProvider:
    """A scripted OpenAI-compatible server: each POST takes the next (status, body)."""

    def __init__(self, script):
        self.script = list(script)
        self.requests: list[dict] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                owner.requests.append(
                    json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                )
                status, body = owner.script.pop(0) if owner.script else (200, completion("{}"))
                self.send_response(status)
                if status == 429:
                    self.send_header("Retry-After", "0")
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"

    def close(self):
        self.server.shutdown()


def structured_request() -> ModelRequest:
    return ModelRequest(
        capability="pathos_advice_heard",
        messages=(ModelMessage("user", json.dumps({"task": "advice", "question": "?"})),),
        output_schema=SCHEMA,
        max_output_tokens=100,
    )


def test_auto_steps_down_when_a_provider_refuses_strict_json() -> None:
    provider = FakeProvider(
        [
            (400, {"error": {"message": "response_format json_schema is not supported"}}),
            (200, completion('Sure! ```json\n{"leans": "for", "source_quote": "go"}\n```')),
        ]
    )
    try:
        gateway = HTTPModelGateway(provider.url, "m", structured="auto", retries=0)
        response = asyncio.run(gateway.generate(structured_request()))
        assert json.loads(response.content) == {"leans": "for", "source_quote": "go"}
        assert provider.requests[0]["response_format"]["type"] == "json_schema"
        assert provider.requests[1]["response_format"] == {"type": "json_object"}
        assert "JSON schema" in provider.requests[1]["messages"][0]["content"]
        assert gateway._mode == "json_object"  # remembered for next time
    finally:
        provider.close()


def test_rate_limits_are_retried_and_errors_explained() -> None:
    provider = FakeProvider(
        [
            (429, {"error": {"message": "slow down"}}),
            (200, completion('{"leans": "none", "source_quote": ""}')),
            (401, {"error": {"message": "Invalid API key sk-or-abcdefghijklmnop"}}),
        ]
    )
    try:
        gateway = HTTPModelGateway(provider.url, "m", retries=2, provider="OpenRouter")
        assert asyncio.run(gateway.generate(structured_request())).content
        with pytest.raises(OSError) as refused:
            asyncio.run(gateway.generate(structured_request()))
        assert "HTTP 401" in str(refused.value) and "abcdefghijklmnop" not in str(refused.value)
    finally:
        provider.close()


def test_a_thinking_model_that_runs_out_of_room_says_so() -> None:
    provider = FakeProvider([(200, completion("", finish="length"))])
    try:
        gateway = HTTPModelGateway(provider.url, "m", max_tokens=4000, retries=0)
        with pytest.raises(ValueError, match="ran out of room"):
            asyncio.run(gateway.generate(structured_request()))
        assert provider.requests[0]["max_tokens"] == 4000
    finally:
        provider.close()


def settings(paid_url: str, local_url: str, **budget) -> dict:
    return {
        "providers": {
            "paid": {"kind": "openrouter", "base_url": paid_url, "api_key": "sk-or-secret-123456"},
            "home": {"kind": "ollama", "base_url": local_url},
        },
        "models": {
            "big": {"provider": "paid", "model": "big", "price_in": 3.0, "price_out": 15.0},
            "small": {"provider": "home", "model": "small"},
        },
        "roles": {"default": ["big", "small"]},
        "budget": budget,
    }


def test_backups_answer_when_the_first_choice_fails(tmp_path) -> None:
    paid = FakeProvider([(500, {"error": "down"})] * 3)
    local = FakeProvider([(200, completion('{"leans": "for", "source_quote": "x"}'))])
    try:
        path = tmp_path / "models.json"
        path.write_text(json.dumps(settings(paid.url, local.url)))
        gateway = ConfiguredGateway(path, {})
        for entry in gateway.entries().values():
            entry.gateway.retries = 0
        response = asyncio.run(gateway.generate(structured_request()))
        assert json.loads(response.content)["leans"] == "for"
        assert gateway.usage.today()["by_model"]["small"]["calls"] == 1
    finally:
        paid.close()
        local.close()


def test_the_budget_stops_paid_calls_and_local_models_carry_on(tmp_path) -> None:
    body = completion('{"leans": "for", "source_quote": "x"}')
    paid = FakeProvider([(200, body)] * 5)
    local = FakeProvider([(200, body)] * 5)
    try:
        path = tmp_path / "models.json"
        path.write_text(json.dumps(settings(paid.url, local.url, daily_requests=1)))
        gateway = ConfiguredGateway(path, {})
        asyncio.run(gateway.generate(structured_request()))
        asyncio.run(gateway.generate(structured_request()))
        assert len(paid.requests) == 1 and len(local.requests) == 1
        today = gateway.usage.today()
        assert today["requests"] == 1
        assert today["usd"] == pytest.approx((1000 * 3.0 + 100 * 15.0) / 1_000_000)
    finally:
        paid.close()
        local.close()


def test_keys_never_reach_the_page_but_survive_a_save(tmp_path) -> None:
    path = tmp_path / "models.json"
    gateway = ConfiguredGateway(path, {})
    gateway.save(settings("https://openrouter.ai/api/v1", "http://127.0.0.1:11434/v1"))
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    status = gateway.status()
    assert "sk-or-secret" not in json.dumps(status)
    assert status["settings"]["providers"]["paid"]["key_saved"] == "…3456"
    edited = status["settings"]
    edited["roles"] = {"voice": ["big"], "default": ["small"]}
    gateway.save(edited)
    assert gateway.settings()["providers"]["paid"]["api_key"] == "sk-or-secret-123456"
    assert gateway.chain("pathos") == ["big"] and gateway.chain("murmur") == ["small"]


def test_an_offline_world_switches_to_models_as_soon_as_one_is_saved(tmp_path) -> None:
    local = FakeProvider([(200, completion('{"leans": "for", "source_quote": "x"}'))] * 3)
    try:
        path = tmp_path / "models.json"
        switching = SwitchingGateway(ConfiguredGateway(path, {}), StandInGateway())
        assert switching.mode() == "stand-in"
        switching.configured.save(
            {
                "providers": {"home": {"kind": "ollama", "base_url": local.url}},
                "models": {"small": {"provider": "home", "model": "small"}},
                "roles": {"default": ["small"]},
            }
        )
        assert switching.mode() == "configured-models"
        result = asyncio.run(check_model(switching.configured.entries()["small"].gateway))
        assert result["ok"] and result["answer"]["leans"] == "for"
    finally:
        local.close()


def test_settings_are_checked_before_they_are_used() -> None:
    with pytest.raises(SettingsError):
        validate({"providers": {"x": {"kind": "made-up"}}}, {})
    with pytest.raises(SettingsError):
        validate({"providers": {}, "models": {"m": {"provider": "nowhere", "model": "m"}}}, {})
    with pytest.raises(SettingsError):
        validate({"roles": {"not-a-role": []}}, {})
