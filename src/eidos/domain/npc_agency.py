"""Strict open-vocabulary proposals for privately owned NPC plans."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from eidos.domain.proposals import ProposalRejected

_SLUG = re.compile(r"[a-z][a-z0-9_]{2,39}")
_FIELDS = {
    "activity_type",
    "title",
    "motivation",
    "action",
    "location_id",
    "day_offset",
    "scheduled_hour",
}
_OUTCOME = re.compile(r"\b(?:completed|finished|succeeded|achieved|already did)\b", re.I)


@dataclass(frozen=True, slots=True)
class NPCAgencyCandidate:
    activity_type: str
    title: str
    motivation: str
    action: str
    location_id: str
    day_offset: int
    scheduled_hour: int


def npc_agency_output_schema(location_ids: list[str]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_FIELDS),
        "properties": {
            "activity_type": {"type": "string", "pattern": _SLUG.pattern},
            "title": {"type": "string", "minLength": 4, "maxLength": 100},
            "motivation": {"type": "string", "minLength": 8, "maxLength": 240},
            "action": {"type": "string", "pattern": _SLUG.pattern},
            "location_id": {"type": "string", "enum": location_ids},
            "day_offset": {"type": "integer", "minimum": 0, "maximum": 3},
            "scheduled_hour": {"type": "integer", "minimum": 0, "maximum": 23},
        },
    }


def parse_npc_agency_candidate(content: str) -> NPCAgencyCandidate:
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "NPC agency proposal was not valid JSON") from None
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ProposalRejected("invalid_shape", "NPC agency fields did not match schema v1")
    for field in ("activity_type", "action"):
        item = value[field]
        if not isinstance(item, str) or not _SLUG.fullmatch(item):
            raise ProposalRejected("invalid_activity", f"{field} must be a stable activity slug")
    for field, minimum, maximum in (("title", 4, 100), ("motivation", 8, 240)):
        item = value[field]
        if not isinstance(item, str) or not minimum <= len(item.strip()) <= maximum:
            raise ProposalRejected("invalid_text", f"{field} length is outside policy")
        if _OUTCOME.search(item):
            raise ProposalRejected("claims_outcome", "A private plan cannot claim it happened")
    location = value["location_id"]
    if not isinstance(location, str) or not location:
        raise ProposalRejected("invalid_location", "location_id must be a non-empty string")
    day_offset, hour = value["day_offset"], value["scheduled_hour"]
    if isinstance(day_offset, bool) or not isinstance(day_offset, int) or not 0 <= day_offset <= 3:
        raise ProposalRejected("invalid_day", "day_offset must be from zero to three")
    if isinstance(hour, bool) or not isinstance(hour, int) or not 0 <= hour <= 23:
        raise ProposalRejected("invalid_hour", "scheduled_hour must be from zero to 23")
    return NPCAgencyCandidate(
        value["activity_type"],
        value["title"].strip(),
        value["motivation"].strip(),
        value["action"],
        location,
        day_offset,
        hour,
    )
