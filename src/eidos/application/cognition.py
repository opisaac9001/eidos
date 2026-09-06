"""Model invocation, proposal validation, and execution traces."""

import asyncio
import json
from time import perf_counter
from uuid import uuid4

from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected, validate_proposal
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest


async def perform(
    gateway: ModelGateway, role: str, context: dict, at: str, pending: list
) -> str | None:
    started = perf_counter()
    trace = str(uuid4())
    response = None
    try:
        response = await asyncio.wait_for(
            gateway.generate(
                ModelRequest(
                    capability=role,
                    messages=(ModelMessage("user", json.dumps(context)),),
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
            ),
            timeout=50,
        )
        text = validate_proposal(role, response.content, context)
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
