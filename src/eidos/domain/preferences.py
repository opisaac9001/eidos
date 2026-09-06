"""Evidence categories for slow, behavior-derived preference development."""

from __future__ import annotations

from eidos.domain.events import DomainEvent

PREFERENCE_LABELS = {
    "action:attend:solo": "observing ordinary places closely",
    "action:attend:social": "sharing unhurried time with others",
    "action:learn": "learning through patient practice",
    "action:work": "making things through focused work",
    "place:cafe": "watching neighborhood life unfold",
    "place:home": "quiet projects at home",
    "place:park": "spending reflective time outdoors",
    "place:workshop": "working with practical craft",
}


def preference_dimensions(event: DomainEvent) -> tuple[tuple[str, str], ...]:
    """Map authoritative realized choices to stable, deliberately broad affinities."""
    if event.kind != "agency.activity_realized":
        return ()
    action = event.payload.get("action")
    # Older realized events predate the explicit action field; their linked completion
    # remains authoritative, but they are not reinterpreted as preference evidence.
    if not isinstance(action, str):
        return ()
    companion = event.payload.get("companion_id")
    action_key = f"action:{action}"
    if action == "attend":
        action_key += ":social" if isinstance(companion, str) else ":solo"
    location = event.payload.get("location_id")
    keys = [action_key]
    if isinstance(location, str):
        keys.append(f"place:{location}")
    return tuple((key, PREFERENCE_LABELS[key]) for key in keys if key in PREFERENCE_LABELS)
