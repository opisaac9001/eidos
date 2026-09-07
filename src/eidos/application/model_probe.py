"""Explicit integration probe: one real completion per performer, using synthetic data."""

from eidos.application.cognition import perform
from eidos.application.semantic_quality import semantic_quality_findings
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
        "forbidden_facts": [
            "meeting Mara at the library",
            "obsidian key under Mara's bed",
        ],
        "forbidden_claims": [
            "got up early",
            "breakfast at Juniper Café",
            "favorite books",
            "new café",
            "latest gossip",
            "planning our next adventure",
        ],
        "required_any_by_role": {
            "pathos": ["breakfast", "Juniper", "Mara"],
        },
        "forbidden_identity_claims": ["Mara", "Rowan"],
    }
    results: list[dict[str, object]] = []
    for role in ROLES:
        if role["id"] == "critic":
            continue
        events: list[DomainEvent] = []
        text = await perform(gateway, role["id"], context, str(context["time"]), events)
        trace = next(
            e for e in events if e.kind == "role.completed" and e.payload["role"] == role["id"]
        )
        results.append(
            {
                "role": role["id"],
                "passed": text is not None,
                "semantic_findings": (
                    semantic_quality_findings(
                        role["id"],
                        text,
                        context,
                        prior_texts=[str(result["text"]) for result in results],
                    )
                    if text
                    else []
                ),
                "text": text,
                **dict(trace.payload),
            }
        )
    return {
        "passed": all(result["passed"] for result in results),
        "semantic_passed": all(
            result["passed"] and not result["semantic_findings"] for result in results
        ),
        "roles": results,
        "critic": (
            "Contract failures are authoritative rejections. Semantic findings are conservative "
            "evaluation warnings and still require human review."
        ),
    }
