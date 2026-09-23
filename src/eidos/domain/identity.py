"""Stable, explicit identity facts used to ground choices and performer context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, NamedTuple, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold, PersistentMap
from eidos.domain.preferences import preference_dimensions
from eidos.domain.selfhood import STARTING_VALUES, VALUE_CEILING, VALUE_FLOOR

DEFAULT_VALUES: Mapping[str, float] = STARTING_VALUES
DEFAULT_PREFERENCES = (
    "quiet mornings",
    "repairing useful objects",
    "unhurried neighborhood walks",
)

FULL_NAME = "Patrick Shaw"
NICKNAME = "Pathos"
NAME_CONTEXT = (
    "Patrick Shaw is his ordinary full name; he normally introduces himself as Patrick. "
    "Pathos is the nickname some close friends from university use. Both refer to the "
    "same person, whose stable internal actor identifier remains pathos. "
    "Do not invent a new naming ceremony, recent name change, or remembered conversation."
)


@dataclass(frozen=True, slots=True)
class IdentityState:
    name: str
    values: Mapping[str, float]
    preferences: tuple[str, ...]
    established: bool

    @property
    def nickname(self) -> str:
        return NICKNAME if self.name == FULL_NAME else ""


def default_identity() -> IdentityState:
    return IdentityState(FULL_NAME, dict(DEFAULT_VALUES), DEFAULT_PREFERENCES, False)


def identity_established_event(simulated_at: str) -> DomainEvent:
    return DomainEvent(
        "identity.established",
        "pathos",
        {
            "name": FULL_NAME,
            "nickname": NICKNAME,
            **{f"value_{name}": value for name, value in DEFAULT_VALUES.items()},
            **{
                f"preference_{position}": preference
                for position, preference in enumerate(DEFAULT_PREFERENCES, 1)
            },
            "simulated_at": simulated_at,
            "source": "character-pack-v2-original-name",
        },
        correlation_id="identity-pathos-v1",
    )


class _Learned(NamedTuple):
    preference_id: str
    label: str
    source_id: str
    at: datetime


class _IdentityFold(NamedTuple):
    identity: IdentityState
    # Learned preferences in the order they emerged, as the former dicts iterated them.
    learned: tuple[_Learned, ...]
    last_preference_change: datetime | None
    seen: PersistentMap[str, DomainEvent]


def _learned(fold: _IdentityFold, preference_id: str) -> _Learned | None:
    return next((item for item in fold.learned if item.preference_id == preference_id), None)


def _identity_step(fold: _IdentityFold, event: DomainEvent) -> _IdentityFold:
    identity = fold.identity
    seen = fold.seen
    last_preference_change = fold.last_preference_change
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
            _learned(fold, preference_id) is not None
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
        if last_preference_change is not None and change_time - last_preference_change < timedelta(
            days=14
        ):
            raise ValueError("Preference changes must be at least fourteen days apart")
        if max(source_times) - min(source_times) < timedelta(days=7):
            raise ValueError("Preference evidence must span at least seven days")
        if max(source_times) > change_time:
            raise ValueError("Preference evidence cannot come from the future")
        if label in identity.preferences or any(item.label == label for item in fold.learned):
            raise ValueError("Preference label already exists")
        if len(fold.learned) >= 5:
            raise ValueError("Learned preference limit exceeded")
        learned = (
            *fold.learned,
            _Learned(preference_id, label, str(event.event_id), change_time),
        )
        return _IdentityFold(
            IdentityState(
                identity.name,
                identity.values,
                (*DEFAULT_PREFERENCES, *(item.label for item in learned)),
                True,
            ),
            learned,
            change_time,
            seen.with_item(str(event.event_id), event),
        )
    if event.kind == "preference.retired":
        preference_id = _required(event, "preference_id")
        active = _learned(fold, preference_id)
        if active is None or _required(event, "label") != active.label:
            raise ValueError("Only an active learned preference can retire")
        if _required(event, "source_emergence_id") != active.source_id:
            raise ValueError("Preference retirement must cite its active emergence")
        change_time = _event_time(event)
        if last_preference_change is not None and change_time - last_preference_change < timedelta(
            days=14
        ):
            raise ValueError("Preference changes must be at least fourteen days apart")
        # Retirement is rare, so scanning every earlier event here keeps the ordinary tick
        # at O(1) while reproducing the former evidence scan exactly.
        support_times = [
            _event_time(source)
            for source in seen.values()
            if (preference_id, active.label) in preference_dimensions(source)
            and _event_time(source) > active.at
        ]
        last_support = max(support_times, default=active.at)
        if change_time - last_support < timedelta(days=120):
            raise ValueError("Preference retirement requires 120 days without support")
        learned = tuple(item for item in fold.learned if item.preference_id != preference_id)
        return _IdentityFold(
            IdentityState(
                identity.name,
                identity.values,
                (*DEFAULT_PREFERENCES, *(item.label for item in learned)),
                True,
            ),
            learned,
            change_time,
            seen.with_item(str(event.event_id), event),
        )
    if event.kind == "self.value_shifted":
        # Validated by the selfhood projection; identity only carries the result so every
        # planner and performer sees the values he now holds rather than the pack's.
        value_id = _required(event, "value_id")
        if value_id in identity.values:
            shift = float(event.payload["next"]) - float(event.payload["prior"])
            shifted = dict(identity.values)
            shifted[value_id] = round(
                max(VALUE_FLOOR, min(VALUE_CEILING, shifted[value_id] + shift)), 4
            )
            identity = IdentityState(
                identity.name, shifted, identity.preferences, identity.established
            )
        return fold._replace(identity=identity, seen=seen.with_item(str(event.event_id), event))
    if event.kind != "identity.established":
        return fold._replace(seen=seen.with_item(str(event.event_id), event))
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
    return fold._replace(
        identity=IdentityState(
            # Legacy packs recorded only his nickname. Resolve that alias without
            # rewriting the historical event or changing any actor identifiers.
            FULL_NAME if name == NICKNAME else name,
            values,
            tuple(str(item) for item in raw_preferences),
            True,
        ),
        seen=seen.with_item(str(event.event_id), event),
    )


_IDENTITY_FOLD: IncrementalFold[_IdentityFold] = IncrementalFold(
    lambda: _IdentityFold(default_identity(), (), None, PersistentMap()), _identity_step
)


def project_identity(events: Sequence[DomainEvent]) -> IdentityState:
    return _IDENTITY_FOLD(events).identity


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
