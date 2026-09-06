"""Strictly validate model-invented ordinary-world material before scheduling it."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected

AMBIENT_FIELDS = {
    "event_type",
    "description",
    "location_id",
    "cause",
    "theme",
    "opportunity",
    "starts_in_hours",
    "intensity",
    "duration_hours",
}
WORDS = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class AmbientCandidate:
    event_type: str
    description: str
    location_id: str
    cause: str
    theme: str
    opportunity: str
    starts_in_hours: int
    intensity: float
    duration_hours: int


def parse_ambient_candidate(content: str) -> AmbientCandidate:
    try:
        raw = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "Ambient proposal was not valid JSON") from None
    if not isinstance(raw, dict) or set(raw) != AMBIENT_FIELDS:
        raise ProposalRejected("invalid_shape", "Ambient proposal fields did not match schema v1")
    text_values = {}
    for field, maximum in {
        "description": 220,
        "event_type": 40,
        "location_id": 20,
        "cause": 140,
        "theme": 40,
        "opportunity": 40,
    }.items():
        value = raw[field]
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ProposalRejected("invalid_text", f"Ambient {field} is invalid")
        text_values[field] = value.strip()
    starts = raw["starts_in_hours"]
    if isinstance(starts, bool) or not isinstance(starts, int) or not 1 <= starts <= 12:
        raise ProposalRejected("invalid_start", "Ambient start must be one to twelve hours away")
    intensity = raw["intensity"]
    if (
        isinstance(intensity, bool)
        or not isinstance(intensity, (int, float))
        or not 0.05 <= intensity <= 1.0
    ):
        raise ProposalRejected("invalid_intensity", "Ambient intensity must be 0.05 to 1.0")
    duration = raw["duration_hours"]
    if isinstance(duration, bool) or not isinstance(duration, int) or not 1 <= duration <= 72:
        raise ProposalRejected("invalid_duration", "Ambient duration must be one to 72 hours")
    return AmbientCandidate(
        **text_values,
        starts_in_hours=starts,
        intensity=float(intensity),
        duration_hours=duration,
    )


def validate_ambient_candidate(
    candidate: AmbientCandidate,
    *,
    known_locations: set[str],
    history: Sequence[DomainEvent],
) -> None:
    if candidate.location_id not in known_locations:
        raise ProposalRejected("unknown_location", "Ambient event names an unknown place")
    description_terms = _terms(candidate.description)
    if len(description_terms) < 3:
        raise ProposalRejected("thin_description", "Ambient event is too vague to ground")
    compared = 0
    for event in reversed(history):
        if event.kind != "world_event.accepted" or event.payload.get("event_kind") != "ambient":
            continue
        compared += 1
        prior = _terms(str(event.payload.get("description", "")))
        overlap = len(description_terms & prior) / max(1, len(description_terms | prior))
        if overlap >= 0.65:
            raise ProposalRejected("repetitive_event", "Ambient event repeats recent material")
        if compared >= 24:
            break


def ambient_output_schema() -> Mapping[str, object]:
    return {
        "type": "object",
        "properties": {
            "description": {"type": "string", "minLength": 1, "maxLength": 220},
            "event_type": {"type": "string", "minLength": 1, "maxLength": 40},
            "location_id": {"type": "string", "enum": ["home", "cafe", "workshop", "park"]},
            "cause": {"type": "string", "minLength": 1, "maxLength": 140},
            "theme": {"type": "string", "minLength": 1, "maxLength": 40},
            "opportunity": {"type": "string", "minLength": 1, "maxLength": 40},
            "starts_in_hours": {"type": "integer", "minimum": 1, "maximum": 12},
            "intensity": {"type": "number", "minimum": 0.05, "maximum": 1.0},
            "duration_hours": {"type": "integer", "minimum": 1, "maximum": 72},
        },
        "required": sorted(AMBIENT_FIELDS),
        "additionalProperties": False,
    }


def _terms(text: str) -> set[str]:
    return {word for word in WORDS.findall(text.lower()) if len(word) > 2}
