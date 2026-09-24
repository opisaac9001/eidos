"""Conservative contract checks, not a general semantic truth detector."""

import json
import re
from typing import Mapping

STRUCTURED_CAPABILITIES = {
    "firmament_townsfolk",
    "moira_event",
    "moira_expansion",
    "npc_agency",
    "npc_backstory",
    "pathos_agency",
    "pathos_deliberation",
    "pathos_selfhood",
    "pathos_project",
}


class ProposalRejected(ValueError):
    def __init__(self, code: str, explanation: str):
        super().__init__(explanation)
        self.code = code


def validate_completion(
    role: str,
    content: str,
    finish_reason: str,
    context: Mapping[str, object],
) -> str:
    """Validate a transport envelope; structured domain semantics remain downstream."""
    if finish_reason != "stop":
        raise ProposalRejected("incomplete", "Model completion did not finish")
    if role in STRUCTURED_CAPABILITIES:
        try:
            value = json.loads(content)
        except (TypeError, ValueError):
            raise ProposalRejected("invalid_json", "Response was not valid JSON") from None
        if not isinstance(value, dict):
            raise ProposalRejected("invalid_shape", "Structured proposal must be an object")
        return content
    return validate_proposal(role, content, context)


def validate_proposal(role: str, content: str, context: Mapping[str, object]) -> str:
    try:
        proposal = json.loads(content)
    except (ValueError, TypeError):
        raise ProposalRejected("invalid_json", "Response was not valid JSON") from None
    if not isinstance(proposal, dict) or set(proposal) != {"text"}:
        raise ProposalRejected("invalid_shape", "Expected exactly one text field")
    text = proposal["text"]
    if not isinstance(text, str) or not text.strip() or len(text) > 8000:
        raise ProposalRejected("invalid_text", "Text must contain 1–8000 characters")
    if role == "moira" and text not in {"Clear", "Cloudy", "Light rain", "Breezy"}:
        raise ProposalRejected("invalid_weather", "Weather is outside the world's vocabulary")
    if role == "mnemosyne" and text != context.get("experience"):
        raise ProposalRejected("source_mismatch", "Memory changed its source experience")
    if role == "firmament":
        if len(re.findall(r"\w+", text)) < 5 or text.rstrip().endswith(":"):
            raise ProposalRejected("empty_scene", "Encounter was an unfinished fragment")
        if context.get("scene_mode") is True:
            return text
        person_value = context.get("person")
        person = person_value if isinstance(person_value, str) else None
        if person and not re.search(r"\b" + re.escape(person) + r"\b", text, re.IGNORECASE):
            raise ProposalRejected("missing_actor", "Encounter omitted its scheduled neighbor")
    if role == "oneiros" and not text.lower().startswith("in a dream"):
        raise ProposalRejected("unmarked_dream", "Dream must explicitly identify itself as a dream")
    return text
