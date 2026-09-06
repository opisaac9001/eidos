"""Model invocation, proposal validation, and execution traces."""

import asyncio
import json
from time import perf_counter
from uuid import uuid4

from eidos.domain.events import DomainEvent
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest


async def perform(
    gateway: ModelGateway, role: str, context: dict, at: str, pending: list
) -> str | None:
    started = perf_counter()
    trace = str(uuid4())
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
        proposal = json.loads(response.content)
        if not isinstance(proposal, dict) or set(proposal) != {"text"}:
            raise ValueError("Expected a text-only proposal")
        text = proposal["text"]
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            raise ValueError("Proposal text must contain 1–8000 characters")
        if role == "moira" and text not in {"Clear", "Cloudy", "Light rain", "Breezy"}:
            raise ValueError("Weather is outside the world's vocabulary")
        if role == "mnemosyne" and text != context.get("experience"):
            raise ValueError("A factual memory must preserve its source experience")
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
        pending.append(
            DomainEvent(
                "role.failed",
                "pathos",
                {
                    "role": role,
                    "text": f"{role} did not produce a valid proposal ({type(error).__name__}).",
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
                    "trace_id": trace,
                    "latency_ms": round((perf_counter() - started) * 1000, 2),
                },
            )
        )
        return None
