"""Explicit capability-to-model routing for heterogeneous local inference."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

from eidos.adapters.http_gateway import HTTPModelGateway
from eidos.ports.model_gateway import ModelGateway, ModelRequest, ModelResponse

CAPABILITIES = {
    "pathos",
    "murmur",
    "firmament",
    "moira",
    "mnemosyne",
    "reflection",
    "oneiros",
    "chronicler",
    "moira_event",
    "moira_expansion",
    "pathos_agency",
    "npc_agency",
}
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


class RoutedModelGateway(ModelGateway):
    def __init__(
        self,
        routes: Mapping[str, ModelGateway],
        default: ModelGateway | None = None,
    ) -> None:
        unknown = set(routes) - CAPABILITIES
        if unknown:
            raise ValueError("Unknown model route capabilities: " + ", ".join(sorted(unknown)))
        if not routes and default is None:
            raise ValueError("Model routing requires at least one endpoint")
        missing = CAPABILITIES - set(routes)
        if default is None and missing:
            raise ValueError(
                "Model routing without a default is missing: " + ", ".join(sorted(missing))
            )
        self.routes = dict(routes)
        self.default = default
        self.model = "role-routed-local-models"

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if request.capability not in CAPABILITIES:
            raise ValueError(f"Unknown routed model capability: {request.capability}")
        gateway = self.routes.get(request.capability, self.default)
        if gateway is None:
            raise OSError(f"No model route for {request.capability}")
        return await gateway.generate(request)


def routed_gateway_from_file(path: Path, environment: Mapping[str, str]) -> RoutedModelGateway:
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise ValueError(f"Could not read model routing file: {error}") from error
    if not isinstance(raw, dict) or set(raw) - {"default", "routes"}:
        raise ValueError("Model routing file must contain only default and routes")
    raw_routes = raw.get("routes", {})
    if not isinstance(raw_routes, dict):
        raise ValueError("Model routes must be an object")
    routes: dict[str, ModelGateway] = {}
    for capability, specification in raw_routes.items():
        if not isinstance(capability, str):
            raise ValueError("Model route names must be strings")
        routes[capability] = _http_gateway(specification, environment)
    raw_default = raw.get("default")
    default = _http_gateway(raw_default, environment) if raw_default is not None else None
    return RoutedModelGateway(routes, default)


def _http_gateway(value: object, environment: Mapping[str, str]) -> HTTPModelGateway:
    if not isinstance(value, dict) or set(value) - {"base_url", "model", "api_key_env"}:
        raise ValueError("Each model endpoint needs base_url, model, and optional api_key_env")
    base_url, model = value.get("base_url"), value.get("model")
    if not isinstance(base_url, str) or not isinstance(model, str):
        raise ValueError("Model endpoint base_url and model must be strings")
    api_key = None
    api_key_env = value.get("api_key_env")
    if api_key_env is not None:
        if not isinstance(api_key_env, str) or not ENV_NAME.fullmatch(api_key_env):
            raise ValueError("Model endpoint api_key_env must be an uppercase environment name")
        api_key = environment.get(api_key_env)
        if not api_key:
            raise ValueError(f"Model endpoint credential environment is unset: {api_key_env}")
    return HTTPModelGateway(base_url, model, api_key)
