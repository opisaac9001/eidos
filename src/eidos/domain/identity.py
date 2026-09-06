"""Stable, explicit identity facts used to ground choices and performer context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.preferences import preference_dimensions

DEFAULT_VALUES: Mapping[str, float] = {
    "care": 0.78,
    "curiosity": 0.84,
    "reliability": 0.74,
    "autonomy": 0.68,
    "craft": 0.72,
}
DEFAULT_PREFERENCES = (
    "quiet mornings",
    "repairing useful objects",
    "unhurried neighborhood walks",
)


@dataclass(frozen=True, slots=True)
class IdentityState:
    name: str
    values: Mapping[str, float]
    preferences: tuple[str, ...]
    established: bool


def default_identity() -> IdentityState:
    return IdentityState("Pathos", dict(DEFAULT_VALUES), DEFAULT_PREFERENCES, False)


def identity_established_event(simulated_at: str) -> DomainEvent:
    return DomainEvent(
        "identity.established",
        "pathos",
        {
            "name": "Pathos",
            **{f"value_{name}": value for name, value in DEFAULT_VALUES.items()},
            **{
                f"preference_{position}": preference
                for position, preference in enumerate(DEFAULT_PREFERENCES, 1)
            },
            "simulated_at": simulated_at,
            "source": "character-pack-v1",
        },
        correlation_id="identity-pathos-v1",
    )


def project_identity(events: Sequence[DomainEvent]) -> IdentityState:
    identity = default_identity()
    learned: dict[str, str] = {}
    learned_sources: dict[str, str] = {}
    learned_at: dict[str, datetime] = {}
    last_preference_change: datetime | None = None
    seen: dict[str, DomainEvent] = {}
    for event in events:
        if event.kind == "preference.emerged":
            if not identity.established:
                raise ValueError("Preferences cannot develop before identity exists")
            preference_id = _required(event, "preference_id")
            label = _required(event, "label")
            source_ids: list[str] = []
            for position in range(1, 6):
                source_id = event.payload.get(f"source_event_{position}")
                if source_id is None:
                    continue
                if not isinstance(source_id, str) or not source_id:
                    raise ValueError("Preference evidence IDs must be text")
                source_ids.append(source_id)
            count = event.payload.get("evidence_count")
            if (
                preference_id in learned
                or not 3 <= len(source_ids) <= 5
                or len(set(source_ids)) != len(source_ids)
                or isinstance(count, bool)
                or not isinstance(count, int)
                or count < len(source_ids)
            ):
                raise ValueError("Preference emergence needs distinct repeated evidence")
            for source_id in source_ids:
                source = seen.get(source_id)
                if source is None or (preference_id, label) not in preference_dimensions(source):
                    raise ValueError("Preference evidence does not support the claimed preference")
            source_times = [_event_time(seen[source_id]) for source_id in source_ids]
            change_time = _event_time(event)
            if (
                last_preference_change is not None
                and change_time - last_preference_change < timedelta(days=14)
            ):
                raise ValueError("Preference changes must be at least fourteen days apart")
            if max(source_times) - min(source_times) < timedelta(days=7):
                raise ValueError("Preference evidence must span at least seven days")
            if max(source_times) > change_time:
                raise ValueError("Preference evidence cannot come from the future")
            if label in identity.preferences or label in learned.values():
                raise ValueError("Preference label already exists")
            if len(learned) >= 5:
                raise ValueError("Learned preference limit exceeded")
            learned[preference_id] = label
            learned_sources[preference_id] = str(event.event_id)
            learned_at[preference_id] = change_time
            last_preference_change = change_time
            identity = IdentityState(
                identity.name,
                identity.values,
                (*DEFAULT_PREFERENCES, *learned.values()),
                True,
            )
        elif event.kind == "preference.retired":
            preference_id = _required(event, "preference_id")
            if preference_id not in learned or _required(event, "label") != learned[preference_id]:
                raise ValueError("Only an active learned preference can retire")
            if _required(event, "source_emergence_id") != learned_sources[preference_id]:
                raise ValueError("Preference retirement must cite its active emergence")
            change_time = _event_time(event)
            if (
                last_preference_change is not None
                and change_time - last_preference_change < timedelta(days=14)
            ):
                raise ValueError("Preference changes must be at least fourteen days apart")
            support_times = [
                _event_time(source)
                for source in seen.values()
                if (preference_id, learned[preference_id]) in preference_dimensions(source)
                and _event_time(source) > learned_at[preference_id]
            ]
            last_support = max(support_times, default=learned_at[preference_id])
            if change_time - last_support < timedelta(days=120):
                raise ValueError("Preference retirement requires 120 days without support")
            del learned[preference_id]
            del learned_sources[preference_id]
            del learned_at[preference_id]
            last_preference_change = change_time
            identity = IdentityState(
                identity.name,
                identity.values,
                (*DEFAULT_PREFERENCES, *learned.values()),
                True,
            )
        elif event.kind != "identity.established":
            seen[str(event.event_id)] = event
            continue
        else:
            if identity.established:
                raise ValueError("Identity can only be established once")
            name = event.payload.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Identity requires a name")
            values: dict[str, float] = {}
            for key in DEFAULT_VALUES:
                value = event.payload.get(f"value_{key}")
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("Identity values must be numeric")
                if not 0 <= float(value) <= 1:
                    raise ValueError("Identity values must be between zero and one")
                values[key] = float(value)
            raw_preferences = tuple(
                event.payload.get(f"preference_{position}")
                for position in range(1, len(DEFAULT_PREFERENCES) + 1)
            )
            if not all(isinstance(item, str) and item.strip() for item in raw_preferences):
                raise ValueError("Identity preferences must be non-empty text")
            identity = IdentityState(
                name, values, tuple(str(item) for item in raw_preferences), True
            )
        seen[str(event.event_id)] = event
    return identity


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _event_time(event: DomainEvent) -> datetime:
    value = _required(event, "simulated_at")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Identity development time must be timezone-aware")
    return parsed
