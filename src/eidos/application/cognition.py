"""Model invocation, proposal validation, and execution traces."""

import asyncio
import json
from time import perf_counter
from typing import Mapping
from uuid import uuid4

from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected, validate_completion
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest

ROLE_MODEL_PROFILES = {
    "pathos": ("3", 160, 0.55),
    "murmur": ("3", 100, 0.65),
    "firmament": ("3", 140, 0.7),
    "moira": ("3", 16, 0.2),
    "mnemosyne": ("3", 384, 0.0),
    "reflection": ("3", 140, 0.55),
    "oneiros": ("3", 220, 0.8),
    "chronicler": ("3", 180, 0.2),
}


def request_for(role: str, context: Mapping[str, object]) -> ModelRequest:
    try:
        task_version, max_output_tokens, temperature = ROLE_MODEL_PROFILES[role]
    except KeyError:
        raise ValueError(f"Unknown cognition role: {role}") from None
    return ModelRequest(
        capability=role,
        messages=(ModelMessage("user", json.dumps(context)),),
        task_version=task_version,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        output_schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    **(
                        {"enum": ["Clear", "Cloudy", "Light rain", "Breezy"]}
                        if role == "moira"
                        else {}
                    ),
                }
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    )


async def perform(
    gateway: ModelGateway,
    role: str,
    context: Mapping[str, object],
    at: str,
    pending: list[DomainEvent],
) -> str | None:
    started = perf_counter()
    trace = str(uuid4())
    response = None
    try:
        response = await asyncio.wait_for(
            gateway.generate(request_for(role, context)),
            timeout=50,
        )
        text = validate_completion(role, response.content, response.finish_reason, context)
        pending.append(
            DomainEvent(
                "role.completed",
                "pathos",
                {
                    "role": role,
                    "simulated_at": at,
                    "status": "ok",
                    "trace_id": trace,
                    "latency_ms": round((perf_counter() - started) * 1000, 2),
                    "model": response.resolved_model,
                    "backend": response.backend,
                    "finish_reason": response.finish_reason,
                    "prompt_tokens": response.prompt_tokens,
                    "output_tokens": response.output_tokens,
                },
            )
        )
        pending.append(
            DomainEvent(
                "role.completed",
                "pathos",
                {
                    "role": "critic",
                    "simulated_at": at,
                    "status": "ok",
                    "trace_id": trace,
                    "latency_ms": 0,
                    "model": "schema-rules-v1",
                    "backend": "rules",
                },
            )
        )
        return text
    except (ValueError, TypeError, KeyError, TimeoutError, OSError) as error:
        code = (
            error.code
            if isinstance(error, ProposalRejected)
            else (
                "timeout"
                if isinstance(error, TimeoutError)
                else "endpoint_unavailable"
                if isinstance(error, OSError)
                else "invalid_completion"
            )
        )
        explanation = (
            str(error)
            if isinstance(error, ProposalRejected)
            else {
                "timeout": "Model request timed out",
                "endpoint_unavailable": "Model endpoint could not complete the request",
                "invalid_completion": "Endpoint returned an incomplete or invalid response",
            }[code]
        )
        pending.append(
            DomainEvent(
                "role.failed",
                "pathos",
                {
                    "role": role,
                    "text": f"{role}: {explanation}.",
                    "error_code": code,
                    "simulated_at": at,
                    "trace_id": trace,
                },
            )
        )
        pending.append(
            DomainEvent(
                "role.completed",
                "pathos",
                {
                    "role": role,
                    "simulated_at": at,
                    "status": "failed",
                    "error_code": code,
                    "model": response.resolved_model
                    if response
                    else getattr(gateway, "model", "unknown"),
                    "backend": response.backend if response else "unknown",
                    "trace_id": trace,
                    "latency_ms": round((perf_counter() - started) * 1000, 2),
                },
            )
        )
        if response is not None:
            pending.append(
                DomainEvent(
                    "role.completed",
                    "pathos",
                    {
                        "role": "critic",
                        "simulated_at": at,
                        "status": "rejected",
                        "trace_id": trace,
                        "latency_ms": 0,
                        "error_code": code,
                        "model": "schema-rules-v1",
                        "backend": "rules",
                    },
                )
            )
        return None
