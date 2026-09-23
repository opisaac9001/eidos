"""Incremental memoization for left folds over the append-only event stream.

Projections such as scenes, planning or NPC state are pure folds: an initial state plus
``apply`` for each event in order. The simulation repeatedly projects ``history + pending``
lists that share almost their entire prefix, so re-folding from the first event makes each
simulated hour cost time proportional to the whole life lived so far.

``IncrementalFold`` remembers a few recently folded sequences and resumes from the longest
cached prefix. A prefix is reused only when every cached event is the *identical* object at
the same position, so filtered, reordered or speculative sequences can never be mistaken
for one another; they simply fold from the start. States must be immutable, which every
frozen projection state in the domain already is.
"""

from __future__ import annotations

import operator
from bisect import bisect_left
from collections.abc import Callable, Hashable, Iterator, Sequence
from datetime import datetime
from heapq import merge
from threading import Lock
from typing import Generic, TypeVar

from eidos.domain.events import DomainEvent

S = TypeVar("S")


class _Entry(Generic[S]):
    __slots__ = ("events", "state")

    def __init__(self, events: list[DomainEvent], state: S) -> None:
        self.events = events
        self.state = state


class IncrementalFold(Generic[S]):
    """Folds ``step`` over events, reusing the longest identical cached prefix."""

    def __init__(
        self,
        initial: Callable[[], S],
        step: Callable[[S, DomainEvent], S],
        *,
        capacity: int = 6,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._initial = initial
        self._step = step
        self._capacity = capacity
        self._entries: dict[Hashable, list[_Entry[S]]] = {}
        self._lock = Lock()

    def __call__(
        self,
        events: Sequence[DomainEvent],
        *,
        key: Hashable = None,
        initial: Callable[[], S] | None = None,
    ) -> S:
        """Return the fold of ``events``.

        ``key`` separates folds whose initial state differs (for example by the hour a
        seed schedule is sampled at); ``initial`` overrides the default seed for that key.
        """
        with self._lock:
            entries = self._entries.setdefault(key, [])
            best: _Entry[S] | None = None
            for entry in entries:
                size = len(entry.events)
                if size > len(events) or (best is not None and size <= len(best.events)):
                    continue
                if size and entry.events[size - 1] is not events[size - 1]:
                    continue
                # List equality checks identity first per element in C, ~3.5x faster than
                # map(is_). An equal but distinct event is the same fact (same id and content),
                # so it folds to the same state.
                if (
                    events[:size] == entry.events
                    if isinstance(events, list)
                    else all(map(operator.is_, entry.events, events))
                ):
                    best = entry
            if best is None:
                state = (initial or self._initial)()
                start = 0
            else:
                state = best.state
                start = len(best.events)
                if start == len(events):
                    self._touch(entries, best)
                    return state
            step = self._step
            for index in range(start, len(events)):
                state = step(state, events[index])
            # Keep the shorter prefix too: speculative sequences (a proposal later rejected)
            # must not evict the prefix the next genuine sequence will continue from.
            entries.insert(0, _Entry(list(events), state))
            del entries[self._capacity :]
            return state

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    @staticmethod
    def _touch(entries: list[_Entry[S]], entry: _Entry[S]) -> None:
        if entries[0] is not entry:
            entries.remove(entry)
            entries.insert(0, entry)


K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class GrowOnlyMap(Generic[K, V]):
    """A persistent map for folds whose states only ever add keys.

    Successive states share one dict and each sees only the entries added before it. When a
    state is extended after another branch already grew the shared dict, the new branch
    copies its own visible entries first, so every state keeps an exact, immutable view
    while the common linear case appends in O(1).
    """

    __slots__ = ("_data", "_size")

    def __init__(self, data: dict[K, tuple[int, V]] | None = None, size: int = 0) -> None:
        self._data: dict[K, tuple[int, V]] = {} if data is None else data
        self._size = size

    def get(self, key: K) -> V | None:
        item = self._data.get(key)
        return item[1] if item is not None and item[0] < self._size else None

    def __contains__(self, key: object) -> bool:
        item = self._data.get(key)  # type: ignore[arg-type]
        return item is not None and item[0] < self._size

    def __len__(self) -> int:
        return self._size

    def with_item(self, key: K, value: V) -> GrowOnlyMap[K, V]:
        if key in self:
            return self
        data = self._data
        if len(data) != self._size:
            data = {k: item for k, item in data.items() if item[0] < self._size}
        data[key] = (self._size, value)
        return GrowOnlyMap(data, self._size + 1)


class _MapLog(Generic[K, V]):
    __slots__ = ("latest", "older", "writes")

    def __init__(self) -> None:
        # ``latest`` keeps keys in first-write order, exactly like a dict that is assigned
        # to repeatedly; ``older`` holds the superseded writes of overwritten keys.
        self.latest: dict[K, tuple[int, V]] = {}
        self.older: dict[K, list[tuple[int, V]]] = {}
        self.writes = 0


class PersistentMap(Generic[K, V]):
    """A persistent map with plain ``dict`` assignment semantics for folds.

    Unlike ``GrowOnlyMap`` a later write to a key replaces its value (last write wins) while
    the key keeps its original iteration position, matching ``d[key] = value``. Successive
    states share one write log and each sees only the writes made before it, so the linear
    case costs O(1) per write; extending a state after another branch already wrote copies
    that state's visible entries first. Old states stay exact and immutable.
    """

    __slots__ = ("_log", "_size")

    def __init__(self, log: _MapLog[K, V] | None = None, size: int = 0) -> None:
        self._log: _MapLog[K, V] = _MapLog() if log is None else log
        self._size = size

    def _visible(self, key: K) -> tuple[int, V] | None:
        item = self._log.latest.get(key)
        if item is None:
            return None
        if item[0] < self._size:
            return item
        for entry in reversed(self._log.older.get(key, ())):
            if entry[0] < self._size:
                return entry
        return None

    def get(self, key: K) -> V | None:
        item = self._visible(key)
        return None if item is None else item[1]

    def __getitem__(self, key: K) -> V:
        item = self._visible(key)
        if item is None:
            raise KeyError(key)
        return item[1]

    def __contains__(self, key: object) -> bool:
        return self._visible(key) is not None  # type: ignore[arg-type]

    def items(self) -> Iterator[tuple[K, V]]:
        """Visible entries in first-write order, as ``dict.items()`` would yield them."""
        older = self._log.older
        for key, item in self._log.latest.items():
            first = older[key][0] if key in older else item
            if first[0] >= self._size:
                break
            visible = self._visible(key)
            assert visible is not None
            yield key, visible[1]

    def values(self) -> Iterator[V]:
        return (value for _key, value in self.items())

    def with_item(self, key: K, value: V) -> PersistentMap[K, V]:
        log = self._log
        if log.writes != self._size:
            log = self._fork()
        previous = log.latest.get(key)
        if previous is not None:
            log.older.setdefault(key, []).append(previous)
        log.latest[key] = (self._size, value)
        log.writes = self._size + 1
        return PersistentMap(log, self._size + 1)

    def _fork(self) -> _MapLog[K, V]:
        log: _MapLog[K, V] = _MapLog()
        source = self._log
        for key, item in source.latest.items():
            visible = [
                entry for entry in (*source.older.get(key, ()), item) if entry[0] < self._size
            ]
            if not visible:
                break
            log.latest[key] = visible[-1]
            if len(visible) > 1:
                log.older[key] = visible[:-1]
        log.writes = self._size
        return log


_EVENT_INDEX: IncrementalFold[GrowOnlyMap[str, DomainEvent]] = IncrementalFold(
    GrowOnlyMap, lambda index, event: index.with_item(str(event.event_id), event)
)


def event_index(events: Sequence[DomainEvent]) -> GrowOnlyMap[str, DomainEvent]:
    """Events by id (first occurrence wins), maintained incrementally across ticks."""
    return _EVENT_INDEX(events)


class _GroupLog:
    __slots__ = ("positions", "events", "folded")

    def __init__(self) -> None:
        self.positions: dict[Hashable, list[int]] = {}
        self.events: dict[Hashable, list[DomainEvent]] = {}
        self.folded = 0


class GroupIndex:
    """Events grouped by a key, in history order, shared append-only between states.

    Each state sees only events at positions below its ``size``. Extending a state after a
    divergent branch already appended copies that state's visible prefix first, so every
    cached state stays exact while the linear case appends in O(1). Positions are indexes
    into the folded sequence, so callers can keep order relative to other groups.
    """

    __slots__ = ("_log", "size")

    def __init__(self, log: _GroupLog | None = None, size: int = 0) -> None:
        self._log = _GroupLog() if log is None else log
        self.size = size

    def with_event(self, key: Hashable, event: DomainEvent) -> GroupIndex:
        """The next state; an event without a key only advances the position."""
        log = self._log
        if log.folded != self.size:
            log = self._fork()
        if key is not None:
            log.positions.setdefault(key, []).append(self.size)
            log.events.setdefault(key, []).append(event)
        log.folded = self.size + 1
        return GroupIndex(log, self.size + 1)

    def _bounds(self, key: Hashable, start: int) -> tuple[list[int], int, int] | None:
        positions = self._log.positions.get(key)
        if not positions:
            return None
        visible = bisect_left(positions, self.size)
        first = bisect_left(positions, start, 0, visible) if start > 0 else 0
        return (positions, first, visible) if first < visible else None

    def has(self, key: Hashable) -> bool:
        return self._bounds(key, 0) is not None

    def keys(self) -> list[Hashable]:
        """Every key with at least one visible event, in first-seen order."""
        return [key for key in self._log.positions if self._bounds(key, 0) is not None]

    def of(self, key: Hashable, start: int = 0) -> list[DomainEvent]:
        """A fresh list of the key's events at positions ``start`` or later."""
        bounds = self._bounds(key, start)
        if bounds is None:
            return []
        _, first, visible = bounds
        return self._log.events[key][first:visible]

    def positioned(self, key: Hashable, start: int = 0) -> list[tuple[int, DomainEvent]]:
        bounds = self._bounds(key, start)
        if bounds is None:
            return []
        positions, first, visible = bounds
        return list(zip(positions[first:visible], self._log.events[key][first:visible]))

    def select(self, *keys: Hashable, start: int = 0) -> list[DomainEvent]:
        """Events of any of ``keys`` (duplicates ignored), merged back into history order."""
        unique = list(dict.fromkeys(keys))
        if len(unique) == 1:
            return self.of(unique[0], start)
        return [event for _, event in self.select_positioned(*unique, start=start)]

    def select_positioned(self, *keys: Hashable, start: int = 0) -> list[tuple[int, DomainEvent]]:
        groups = [
            group for group in (self.positioned(key, start) for key in dict.fromkeys(keys)) if group
        ]
        if len(groups) == 1:
            return groups[0]
        # Positions are unique, so the merge never compares the events themselves.
        return list(merge(*groups))

    def _fork(self) -> _GroupLog:
        log = _GroupLog()
        for key, positions in self._log.positions.items():
            visible = bisect_left(positions, self.size)
            if visible:
                log.positions[key] = positions[:visible]
                log.events[key] = self._log.events[key][:visible]
        log.folded = self.size
        return log


KindIndex = GroupIndex

_KIND_INDEX: IncrementalFold[GroupIndex] = IncrementalFold(
    GroupIndex, lambda index, event: index.with_event(event.kind, event), capacity=8
)


def kind_index(events: Sequence[DomainEvent]) -> GroupIndex:
    """Events grouped by kind, maintained incrementally across ticks."""
    return _KIND_INDEX(events)


def events_of(events: Sequence[DomainEvent], *kinds: str) -> list[DomainEvent]:
    """Events of the given kinds, in history order, without scanning the whole history.

    Exactly ``[event for event in events if event.kind in kinds]``, as a fresh list.
    """
    return _KIND_INDEX(events).select(*kinds)


def events_with_prefix(events: Sequence[DomainEvent], prefix: str) -> list[DomainEvent]:
    """Exactly ``[event for event in events if event.kind.startswith(prefix)]``."""
    index = _KIND_INDEX(events)
    return index.select(
        *(kind for kind in index.keys() if isinstance(kind, str) and kind.startswith(prefix))
    )


# Values of these exact types never compare equal to a string, so they need no grouping.
_NEVER_EQUAL_TO_STR: frozenset[type] = frozenset(
    {type(None), bool, int, float, list, dict, tuple, datetime}
)
# Any other non-``str`` value (a ``str`` subclass or an arbitrary object) might, so such
# events are kept together under this key and every candidate query includes them.
_IRREGULAR = object()


def _payload_key(field: str) -> Callable[[GroupIndex, DomainEvent], GroupIndex]:
    def step(index: GroupIndex, event: DomainEvent) -> GroupIndex:
        value = event.payload.get(field)
        kind = type(value)
        key: Hashable = (
            value if kind is str else None if kind in _NEVER_EQUAL_TO_STR else _IRREGULAR
        )
        return index.with_event(key, event)

    return step


_PAYLOAD_INDEXES: dict[str, IncrementalFold[GroupIndex]] = {}
_PAYLOAD_INDEXES_LOCK = Lock()


def payload_candidates(
    events: Sequence[DomainEvent], field: str, value: object
) -> list[DomainEvent]:
    """Events, in history order, whose ``payload.get(field)`` might equal ``value``.

    For a plain ``str`` value this is every event whose payload holds exactly that string
    plus the rare events holding a value of any type that could still compare equal to one;
    the index behind it is maintained incrementally per field. Any other value returns every
    event. It is a superset, so callers apply their original test to the result:
    ``[e for e in payload_candidates(events, f, v) if e.payload.get(f) == v]`` is exactly
    ``[e for e in events if e.payload.get(f) == v]``.
    """
    if type(value) is not str:
        return list(events)
    fold = _PAYLOAD_INDEXES.get(field)
    if fold is None:
        with _PAYLOAD_INDEXES_LOCK:
            fold = _PAYLOAD_INDEXES.setdefault(
                field, IncrementalFold(GroupIndex, _payload_key(field))
            )
    return fold(events).select(value, _IRREGULAR)
