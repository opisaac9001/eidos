"""Wake a decision from a fresh cause, not a date in an authored itinerary."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from heapq import merge
from operator import itemgetter
from threading import Lock
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold

_MIN = datetime.min


def instant(at: datetime) -> timedelta:
    """An aware time as a UTC instant; ``a - b`` of aware datetimes is exactly the difference.

    Arithmetic on timedeltas cannot overflow for any datetime, unlike conversion to UTC.
    """
    offset = at.utcoffset()
    assert offset is not None
    return at.replace(tzinfo=None) - _MIN - offset


class _TimelineLog:
    __slots__ = ("positions", "events", "bounds", "folded")

    def __init__(self) -> None:
        self.positions: list[int] = []
        self.events: list[DomainEvent] = []
        self.bounds: list[timedelta] = []
        self.folded = 0


class EventTimeline:
    """One kind's events in history order, each with the running maximum of a time key.

    Scanning newest first can stop once every earlier key is below a bound, without
    assuming history is in time order. States share an append-only log like ``GroupIndex``.
    """

    __slots__ = ("_log", "_size")

    def __init__(self, log: _TimelineLog | None = None, size: int = 0) -> None:
        self._log = _TimelineLog() if log is None else log
        self._size = size

    def advanced(self, event: DomainEvent, key: timedelta | None) -> EventTimeline:
        """The next state; an event without a key only advances the position."""
        log = self._log
        if log.folded != self._size:
            log = self._fork()
        if key is not None:
            bounds = log.bounds
            log.positions.append(self._size)
            log.events.append(event)
            bounds.append(max(bounds[-1], key) if bounds else key)
        log.folded = self._size + 1
        return EventTimeline(log, self._size + 1)

    def newest_from(self, minimum: timedelta) -> Iterator[tuple[int, DomainEvent]]:
        """(position, event) newest first, until every earlier key is below ``minimum``."""
        log = self._log
        index = bisect_left(log.positions, self._size) - 1
        while index >= 0 and log.bounds[index] >= minimum:
            yield log.positions[index], log.events[index]
            index -= 1

    def _fork(self) -> _TimelineLog:
        log = _TimelineLog()
        visible = bisect_left(self._log.positions, self._size)
        log.positions = self._log.positions[:visible]
        log.events = self._log.events[:visible]
        log.bounds = self._log.bounds[:visible]
        log.folded = self._size
        return log


def timeline_fold(
    kind: str, key: Callable[[DomainEvent], timedelta]
) -> IncrementalFold[EventTimeline]:
    """An incremental ``EventTimeline`` of ``kind`` events keyed by ``key``."""
    return IncrementalFold(
        EventTimeline,
        lambda state, event: state.advanced(event, key(event) if event.kind == kind else None),
    )


def _cause_key(event: DomainEvent) -> timedelta:
    # Events that can never be a fresh cause sort below every bound; anything the scan
    # below might fail on sorts above them all, so it is still reached and fails alike.
    try:
        at = datetime.fromisoformat(str(event.payload.get("simulated_at")))
    except ValueError:
        return timedelta.min
    except Exception:
        return timedelta.max
    return timedelta.min if at.utcoffset() is None else instant(at)


_CAUSES: dict[str, IncrementalFold[EventTimeline]] = {}
_CAUSES_LOCK = Lock()


def _causes(kind: str) -> IncrementalFold[EventTimeline]:
    fold = _CAUSES.get(kind)
    if fold is None:
        with _CAUSES_LOCK:
            fold = _CAUSES.setdefault(kind, timeline_fold(kind, _cause_key))
    return fold


def fresh_cause(
    history: Sequence[DomainEvent],
    now: datetime,
    kinds: frozenset[str],
) -> DomainEvent | None:
    """Newest eligible cause only; never drain stale incidents into new stories."""
    if now.utcoffset() is None:
        raise ValueError("Decision time must be timezone-aware")
    # Only events at most an hour old can qualify, so older ones need not be looked at.
    floor = instant(now) - timedelta(hours=1)
    candidates = merge(
        *(_causes(kind)(history).newest_from(floor) for kind in kinds),
        key=itemgetter(0),
        reverse=True,
    )
    for _, event in candidates:
        try:
            at = datetime.fromisoformat(str(event.payload.get("simulated_at")))
        except ValueError:
            continue
        if event.kind == "thought.recorded":
            if event.aggregate_id != "pathos" or event.payload.get("owner", "pathos") != "pathos":
                continue
            if at.utcoffset() is None or now - at >= timedelta(minutes=30):
                continue
        if at.utcoffset() is not None and timedelta(0) <= now - at <= timedelta(hours=1):
            return event
    return None


def optional_schema(candidate_schema: Mapping[str, object]) -> dict[str, object]:
    """A valid thought or world update can end without creating an activity."""
    return {
        "anyOf": [
            candidate_schema,
            {
                "type": "object",
                "properties": {"no_change": {"const": True}},
                "required": ["no_change"],
                "additionalProperties": False,
            },
        ]
    }
