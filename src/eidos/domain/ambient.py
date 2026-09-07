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
    "participation",
    "stakes",
    "affective_tone",
    "resource_id",
    "inspiration_signal_id",
    "starts_in_hours",
    "intensity",
    "duration_hours",
}
WORDS = re.compile(r"[a-z0-9]+")
FORCED_PATHOS_ACTION = re.compile(
    r"\bpathos\s+(?:agrees|accepts|buys|chooses|decides|declines|leaves|promises|refuses|repairs|visits)\b",
    re.IGNORECASE,
)
PROMPT_LEAKS = ("system prompt", "json schema", "ignore previous", "developer message")


@dataclass(frozen=True, slots=True)
class AmbientCandidate:
    event_type: str
    description: str
    location_id: str
    cause: str
    theme: str
    opportunity: str
    participation: str
    stakes: str
    affective_tone: float
    resource_id: str
    inspiration_signal_id: str
    starts_in_hours: int
    intensity: float
    duration_hours: int


def parse_ambient_candidate(content: str) -> AmbientCandidate:
    try:
        raw = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "Ambient proposal was not valid JSON") from None
    if not isinstance(raw, dict) or set(raw) != AMBIENT_FIELDS:
        raise ProposalRejected("invalid_shape", "Ambient proposal fields did not match schema v4")
    text_values = {}
    for field, maximum in {
        "description": 220,
        "event_type": 40,
        "location_id": 20,
        "cause": 140,
        "theme": 40,
        "opportunity": 40,
        "participation": 100,
        "stakes": 100,
        "resource_id": 80,
        "inspiration_signal_id": 80,
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
    affective_tone = raw["affective_tone"]
    if (
        isinstance(affective_tone, bool)
        or not isinstance(affective_tone, (int, float))
        or not -1.0 <= affective_tone <= 1.0
    ):
        raise ProposalRejected(
            "invalid_affective_tone", "Ambient affective tone must be between -1.0 and 1.0"
        )
    duration = raw["duration_hours"]
    if isinstance(duration, bool) or not isinstance(duration, int) or not 1 <= duration <= 72:
        raise ProposalRejected("invalid_duration", "Ambient duration must be one to 72 hours")
    return AmbientCandidate(
        **text_values,
        affective_tone=float(affective_tone),
        starts_in_hours=starts,
        intensity=float(intensity),
        duration_hours=duration,
    )


def validate_ambient_candidate(
    candidate: AmbientCandidate,
    *,
    known_locations: set[str],
    known_resources: Mapping[str, str],
    known_signal_ids: set[str],
    history: Sequence[DomainEvent],
) -> float:
    if candidate.location_id not in known_locations:
        raise ProposalRejected("unknown_location", "Ambient event names an unknown place")
    if candidate.resource_id not in known_resources:
        raise ProposalRejected("unknown_resource", "Ambient event names an unknown resource")
    if known_resources[candidate.resource_id] != candidate.location_id:
        raise ProposalRejected(
            "resource_location_mismatch", "Ambient resource is not at the proposed place"
        )
    if (
        candidate.inspiration_signal_id != "none"
        and candidate.inspiration_signal_id not in known_signal_ids
    ):
        raise ProposalRejected(
            "unknown_inspiration_signal", "Ambient event names an unknown external signal"
        )
    _validate_semantic_quality(candidate)
    description_terms = _terms(candidate.description)
    if len(description_terms) < 3:
        raise ProposalRejected("thin_description", "Ambient event is too vague to ground")
    compared = 0
    maximum_similarity = 0.0
    for event in reversed(history):
        if event.kind != "world_event.accepted" or event.payload.get("event_kind") != "ambient":
            continue
        compared += 1
        prior = _terms(str(event.payload.get("description", "")))
        overlap = len(description_terms & prior) / max(1, len(description_terms | prior))
        if overlap >= 0.65:
            raise ProposalRejected("repetitive_event", "Ambient event repeats recent material")
        metadata = next(
            (
                item
                for item in reversed(history)
                if item.kind == "world_event.theme_linked"
                and item.payload.get("proposal_id") == event.payload.get("proposal_id")
            ),
            None,
        )
        if metadata is not None:
            type_match = float(metadata.payload.get("event_type") == candidate.event_type)
            theme_overlap = _overlap(candidate.theme, str(metadata.payload.get("theme", "")))
            opportunity_overlap = _overlap(
                candidate.opportunity, str(metadata.payload.get("opportunity", ""))
            )
            maximum_similarity = max(
                maximum_similarity,
                0.55 * overlap
                + 0.15 * type_match
                + 0.15 * theme_overlap
                + 0.15 * opportunity_overlap,
            )
        if compared >= 24:
            break
    novelty = round(1 - maximum_similarity, 4)
    if novelty < 0.35:
        raise ProposalRejected("low_novelty", "Ambient event is too similar across its metadata")
    return novelty


def ambient_output_schema(
    known_location_ids: Sequence[str] = ("home", "cafe", "workshop", "park"),
    known_resource_ids: Sequence[str] = (
        "seed-swap-table",
        "community-repair-kit",
        "shared-tea-service",
        "community-sketch-basket",
    ),
    known_signal_ids: Sequence[str] = (),
) -> Mapping[str, object]:
    return {
        "type": "object",
        "properties": {
            "description": {"type": "string", "minLength": 1, "maxLength": 220},
            "event_type": {"type": "string", "minLength": 1, "maxLength": 40},
            "location_id": {"type": "string", "enum": list(known_location_ids)},
            "cause": {"type": "string", "minLength": 1, "maxLength": 140},
            "theme": {"type": "string", "minLength": 1, "maxLength": 40},
            "opportunity": {"type": "string", "minLength": 1, "maxLength": 40},
            "participation": {"type": "string", "minLength": 1, "maxLength": 100},
            "stakes": {"type": "string", "minLength": 1, "maxLength": 100},
            "affective_tone": {"type": "number", "minimum": -1.0, "maximum": 1.0},
            "resource_id": {"type": "string", "enum": list(known_resource_ids)},
            "inspiration_signal_id": {
                "type": "string",
                "enum": ["none", *known_signal_ids],
            },
            "starts_in_hours": {"type": "integer", "minimum": 1, "maximum": 12},
            "intensity": {"type": "number", "minimum": 0.05, "maximum": 1.0},
            "duration_hours": {"type": "integer", "minimum": 1, "maximum": 72},
        },
        "required": sorted(AMBIENT_FIELDS),
        "additionalProperties": False,
    }


def _terms(text: str) -> set[str]:
    return {word for word in WORDS.findall(text.lower()) if len(word) > 2}


def _overlap(left: str, right: str) -> float:
    left_terms, right_terms = _terms(left), _terms(right)
    return len(left_terms & right_terms) / max(1, len(left_terms | right_terms))


def _validate_semantic_quality(candidate: AmbientCandidate) -> None:
    minimum_terms = {
        "description": 6,
        "cause": 3,
        "opportunity": 2,
        "participation": 5,
        "stakes": 5,
    }
    fields = {name: str(getattr(candidate, name)) for name in minimum_terms}
    for name, minimum in minimum_terms.items():
        if len(_terms(fields[name])) < minimum:
            raise ProposalRejected(
                "low_semantic_detail", f"Ambient {name} lacks concrete semantic detail"
            )
    combined = " ".join(fields.values()).lower()
    if any(phrase in combined for phrase in PROMPT_LEAKS):
        raise ProposalRejected("prompt_leak", "Ambient proposal leaked instruction language")
    if FORCED_PATHOS_ACTION.search(fields["description"] + " " + fields["cause"]):
        raise ProposalRejected(
            "forced_pathos_action", "Ambient circumstance pre-commits Pathos's agency"
        )
    names = tuple(fields)
    for index, left_name in enumerate(names):
        for right_name in names[index + 1 :]:
            if _overlap(fields[left_name], fields[right_name]) >= 0.8:
                raise ProposalRejected(
                    "collapsed_semantics",
                    f"Ambient {left_name} and {right_name} repeat the same idea",
                )
