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
from collections.abc import Callable, Hashable, Iterator, Sequence
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
                if all(map(operator.is_, entry.events, events)):
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
