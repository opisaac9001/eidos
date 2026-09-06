"""Strict shape checks for model-proposed, resident-private history."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from eidos.domain.proposals import ProposalRejected

FACT_FIELDS = {f"fact_{index}_{field}" for index in (1, 2, 3) for field in ("topic", "text")}
FIRST_PERSON = re.compile(r"\b(I|I'm|I've|I'd|my|me)\b", re.IGNORECASE)
FORBIDDEN_REFERENCES = {"pathos", "eidos", "the user", "system prompt"}


@dataclass(frozen=True, slots=True)
class GeneratedCharacterFact:
    topic: str
    text: str
    reveal_after_familiarity: float


def character_history_output_schema() -> Mapping[str, object]:
    properties: dict[str, object] = {}
    for index in (1, 2, 3):
        properties[f"fact_{index}_topic"] = {
            "type": "string",
            "minLength": 2,
            "maxLength": 48,
        }
        properties[f"fact_{index}_text"] = {
            "type": "string",
            "minLength": 12,
            "maxLength": 240,
        }
    return {
        "type": "object",
        "properties": properties,
        "required": sorted(FACT_FIELDS),
        "additionalProperties": False,
    }


def parse_character_history_candidate(
    content: str, *, known_people: Sequence[str]
) -> tuple[GeneratedCharacterFact, ...]:
    try:
        raw = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "Resident history was not valid JSON") from None
    if not isinstance(raw, dict) or set(raw) != FACT_FIELDS:
        raise ProposalRejected("invalid_shape", "Resident history fields did not match schema v1")
    forbidden = {item.casefold() for item in known_people if item.strip()} | FORBIDDEN_REFERENCES
    facts: list[GeneratedCharacterFact] = []
    topics: set[str] = set()
    for index, threshold in zip((1, 2, 3), (0.2, 0.5, 0.8), strict=True):
        topic = _text(raw[f"fact_{index}_topic"], 2, 48, "topic")
        text = _text(raw[f"fact_{index}_text"], 12, 240, "text")
        if topic.casefold() in topics:
            raise ProposalRejected("duplicate_topic", "Resident history topics must be distinct")
        if not FIRST_PERSON.search(text):
            raise ProposalRejected("not_first_person", "Resident history must be first-person")
        folded = text.casefold()
        if any(re.search(r"\b" + re.escape(name) + r"\b", folded) for name in forbidden):
            raise ProposalRejected(
                "known_person_claim", "Private history cannot invent facts about known people"
            )
        topics.add(topic.casefold())
        facts.append(GeneratedCharacterFact(topic, text, threshold))
    return tuple(facts)


def _text(value: object, minimum: int, maximum: int, label: str) -> str:
    if not isinstance(value, str):
        raise ProposalRejected("invalid_text", f"Resident history {label} must be text")
    text = " ".join(value.split())
    if not minimum <= len(text) <= maximum:
        raise ProposalRejected("invalid_text", f"Resident history {label} has invalid length")
    return text
