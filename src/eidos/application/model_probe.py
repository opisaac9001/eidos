"""Explicit integration probe: one real completion per performer, using synthetic data."""

from eidos.application.cognition import perform
from eidos.domain.events import DomainEvent
from eidos.domain.world import ROLES
from eidos.ports.model_gateway import ModelGateway


async def probe_roles(gateway: ModelGateway) -> dict[str, object]:
    context: dict[str, object] = {
        "time": "2026-01-01T13:00:00+00:00",
        "location": "Willow Square",
        "mood": "Content",
        "person": "Rowan",
        "message": "Where are you, and how was your day?",
        "memories": ["Woke up and made breakfast.", "Visited Juniper Café and spoke with Mara."],
        "experience": "Rowan showed Pathos a sketch in Willow Square.",
    }
    results = []
    for role in ROLES:
        if role["id"] == "critic":
            continue
        events: list[DomainEvent] = []
        text = await perform(gateway, role["id"], context, str(context["time"]), events)
        trace = next(
            e for e in events if e.kind == "role.completed" and e.payload["role"] == role["id"]
        )
        results.append(
            {"role": role["id"], "passed": text is not None, "text": text, **dict(trace.payload)}
        )
    return {
        "passed": all(result["passed"] for result in results),
        "roles": results,
        "critic": "The deterministic validator checked every accepted response; semantic quality needs review.",
    }
