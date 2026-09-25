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

Checking a prefix event by event would itself cost time proportional to the life lived, and
there are thousands of fold calls an hour. So every sequence is first matched once against
a few shared logs (``_LINEAGE``): append-only lists that successive sequences extend. Cached
folds then only remember a log and a length, and a prefix test is an identity comparison.
Sequences passed to folds are treated as the event stream is: they may grow by appending,
but a list is never reordered or overwritten in place once folded.
"""

from __future__ import annotations

import operator
from bisect import bisect_left
from collections.abc import Callable, Hashable, Iterable, Iterator, Sequence
from datetime import datetime
from heapq import merge
from itertools import islice
from operator import itemgetter
from threading import Lock
from typing import Any, Generic, NoReturn, TypeVar

from eidos.domain.events import DomainEvent

S = TypeVar("S")


def _same(log: list[DomainEvent], events: Sequence[DomainEvent]) -> bool:
    """Whether two equally long sequences hold the same events.

    List equality checks identity first per element in C, ~3.5x faster than map(is_), and
    needs no copy. An equal but distinct event is the same fact (same id and content), so it
    folds to the same state.
    """
    if isinstance(events, list):
        return log == events
    return all(map(operator.is_, log, events))


class _Log:
    """An append-only list of events shared by every sequence that is a prefix of it.

    ``ancestors`` records logs this one was forked from, each with the length of the
    prefix the two share, so a fold cached against an ancestor still resumes here.
    """

    __slots__ = ("events", "ancestors")

    _DEPTH = 4

    def __init__(self, events: list[DomainEvent], parent: _Log | None, shared: int) -> None:
        self.events = events
        self.ancestors: tuple[tuple[_Log, int], ...] = (
            ()
            if parent is None
            else (
                (parent, shared),
                *((log, min(shared, length)) for log, length in parent.ancestors),
            )[: self._DEPTH]
        )

    def covers(self, events: Sequence[DomainEvent]) -> bool:
        """Whether ``events`` is a prefix of this log, extending the log if it continues it."""
        log = self.events
        known, size = len(log), len(events)
        if size <= known:
            if size and log[size - 1] is not events[size - 1]:
                return False
            return _same(log, events) if size == known else _same(log[:size], events)
        if known and log[known - 1] is not events[known - 1]:
            return False
        log.extend(events[known:] if isinstance(events, list) else islice(events, known, None))
        if _same(log, events):
            return True
        del log[known:]
        return False

    def shared_with(self, events: Sequence[DomainEvent]) -> int:
        """The length of the longest prefix this log shares with ``events``."""
        log = self.events
        limit = min(len(log), len(events))
        # Sequences that diverge mostly do so near their end, so look back from there.
        length, back = limit, 1
        while length > 0:
            if log[length - 1] is events[length - 1] and _same(log[:length], events[:length]):
                break
            length, back = max(0, limit - back), back * 2
        while length < limit and log[length] is events[length]:
            length += 1
        return length


def _prefix_of(log: _Log | None, size: int, events_log: _Log | None, length: int) -> bool:
    """Whether ``log[:size]`` is a prefix of the sequence ``events_log[:length]``."""
    if size == 0:
        return True
    if size > length or events_log is None:
        return False
    if log is events_log:
        return True
    for ancestor, shared in events_log.ancestors:
        if ancestor is log:
            return size <= shared
    return False


class _Lineage:
    """The shared logs, and which log recently seen sequences are prefixes of."""

    _LOGS = 8
    _RECENT = 8

    def __init__(self) -> None:
        self._logs: list[_Log] = []
        # id(sequence) -> (sequence, its length then, its log); the sequence is held so its
        # id cannot be reused. Sequences only ever grow, so an unchanged length is the same
        # sequence and one that grew is matched again.
        self._recent: dict[int, tuple[Sequence[DomainEvent], int, _Log]] = {}
        self._lock = Lock()

    def resolve(self, events: Sequence[DomainEvent]) -> _Log | None:
        """A log of which ``events`` is a prefix, or None for an empty sequence."""
        if not events:
            return None
        with self._lock:
            seen = self._recent.get(id(events))
            if seen is not None and seen[0] is events and seen[1] == len(events):
                return seen[2]
            match = next((log for log in self._logs if log.covers(events)), None)
            if match is None:
                # A new branch: fork from the log it shares the longest prefix with. (The
                # first log sharing anything may be an unrelated ordering of the same events,
                # such as history beside a time-ordered view, that agrees on only a few.)
                parent, shared = None, 0
                for log in self._logs:
                    length = log.shared_with(events)
                    if length > shared:
                        parent, shared = log, length
                match = _Log(list(events), parent, shared)
            else:
                self._logs.remove(match)
            self._logs.insert(0, match)
            del self._logs[self._LOGS :]
            self._recent.pop(id(events), None)
            self._recent[id(events)] = (events, len(events), match)
            while len(self._recent) > self._RECENT:
                del self._recent[next(iter(self._recent))]
            return match


_LINEAGE = _Lineage()


class _Entry(Generic[S]):
    __slots__ = ("log", "size", "state")

    def __init__(self, log: _Log | None, size: int, state: S) -> None:
        self.log = log
        self.size = size
        self.state = state


class EventView(list[DomainEvent]):
    """A list of history's events in some other order, such as by simulated time.

    It is an ordinary list; its type only tells ``IncrementalFold`` to cache it apart from
    history-ordered sequences, which it rarely shares more than a short prefix with.
    """

    __slots__ = ()


class CombinedEvents(list[DomainEvent]):
    """History and the events pending with it, shared read-only between their readers."""

    __slots__ = ()

    def _refuse(self) -> NoReturn:
        raise TypeError("Combined history is shared and read-only; copy it to change it")

    def append(self, *args: Any, **kwargs: Any) -> NoReturn:
        self._refuse()

    def extend(self, *args: Any, **kwargs: Any) -> NoReturn:
        self._refuse()

    def insert(self, *args: Any, **kwargs: Any) -> NoReturn:
        self._refuse()

    def pop(self, *args: Any, **kwargs: Any) -> NoReturn:
        self._refuse()

    def remove(self, *args: Any, **kwargs: Any) -> NoReturn:
        self._refuse()

    def sort(self, *args: Any, **kwargs: Any) -> NoReturn:
        self._refuse()

    def reverse(self, *args: Any, **kwargs: Any) -> NoReturn:
        self._refuse()

    def clear(self, *args: Any, **kwargs: Any) -> NoReturn:
        self._refuse()

    def __setitem__(self, *args: Any, **kwargs: Any) -> NoReturn:
        self._refuse()

    def __delitem__(self, *args: Any, **kwargs: Any) -> NoReturn:
        self._refuse()

    # In-place ``+=`` and ``*=`` would change the shared list too.
    def __iadd__(self, *args: Any, **kwargs: Any) -> NoReturn:  # type: ignore[misc]
        self._refuse()

    def __imul__(self, *args: Any, **kwargs: Any) -> NoReturn:  # type: ignore[misc]
        self._refuse()


class PendingEvents(list[DomainEvent]):
    """Events accepted during an advance but not yet committed; they are only appended.

    ``history + pending`` is evaluated hundreds of times an hour, almost always with
    nothing new in between, and each evaluation copied the whole life. While neither list
    has grown, the same ``CombinedEvents`` is handed out again; it refuses modification,
    so sharing it is safe, and folds recognise it without comparing it again.
    """

    __slots__ = ("_combined",)

    def __init__(self, events: Iterable[DomainEvent] = ()) -> None:
        super().__init__(events)
        self._combined: tuple[list[DomainEvent], int, int, CombinedEvents] | None = None

    def __radd__(self, history: object) -> list[DomainEvent]:
        if type(history) is not list:
            return NotImplemented
        combined = self._combined
        if (
            combined is not None
            and combined[0] is history
            and combined[1] == len(history)
            and combined[2] == len(self)
            and (not self or combined[3][-1] is self[-1])
        ):
            return combined[3]
        joined = CombinedEvents(history)
        list.extend(joined, self)
        self._combined = (history, len(history), len(self), joined)
        return joined


class IncrementalFold(Generic[S]):
    """Folds ``step`` over events, reusing the longest identical cached prefix.

    Besides the recent heads it keeps a checkpoint every ``CHECKPOINT_EVERY`` events. A
    sequence that differs from a cached one only near its end (a time-ordered view in which
    a late event was slotted in before the last few) then resumes from the checkpoint before
    the difference instead of folding the whole life again.
    """

    CHECKPOINT_EVERY = 4096
    CHECKPOINTS = 2

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
        self._checkpoints: dict[Hashable, list[_Entry[S]]] = {}
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
        An ``EventView`` is cached apart, so it never evicts the history-ordered sequences
        it cannot share a prefix with, nor they it.
        """
        log, length = _LINEAGE.resolve(events), len(events)
        with self._lock:
            slot = (key, isinstance(events, EventView))
            entries = self._entries.setdefault(slot, [])
            checkpoints = self._checkpoints.setdefault(slot, [])
            best: _Entry[S] | None = None
            for entry in (*entries, *checkpoints):
                if (best is None or entry.size > best.size) and _prefix_of(
                    entry.log, entry.size, log, length
                ):
                    best = entry
            if best is None:
                state = (initial or self._initial)()
                start = 0
            else:
                state = best.state
                start = best.size
                if start == length:
                    self._touch(entries, best)
                    return state
            step = self._step
            every = self.CHECKPOINT_EVERY
            for index in range(start, length):
                state = step(state, events[index])
                if (index + 1) % every == 0 and length - (index + 1) < every:
                    # The last checkpoint before the head, kept for late insertions.
                    checkpoints.insert(0, _Entry(log, index + 1, state))
                    del checkpoints[self.CHECKPOINTS :]
            # Keep the shorter prefix too: speculative sequences (a proposal later rejected)
            # must not evict the prefix the next genuine sequence will continue from.
            entries.insert(0, _Entry(log, length, state))
            del entries[self._capacity :]
            return state

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._checkpoints.clear()

    @staticmethod
    def _touch(entries: list[_Entry[S]], entry: _Entry[S]) -> None:
        if entries[0] is not entry:
            entries.remove(entry)
            entries.insert(0, entry)


R = TypeVar("R")


class LinearReplay(Generic[S]):
    """One mutable replay state for a sequence that grows call after call.

    Some derived data is too rich to keep as immutable fold states. ``advance(state, events,
    start)`` brings ``state`` up to date with ``events[start:]`` in place. A call whose
    events extend the previously replayed sequence (the identical prefix test of
    ``IncrementalFold``) continues it; any other sequence is replayed from ``initial()``.
    The state is only lent to ``read`` under a lock, which must not keep or modify it.
    """

    def __init__(
        self,
        initial: Callable[[], S],
        advance: Callable[[S, Sequence[DomainEvent], int], None],
    ) -> None:
        self._initial = initial
        self._advance = advance
        self._log: _Log | None = None
        self._size = 0
        self._state: S | None = None
        self._lock = Lock()

    def use(self, events: Sequence[DomainEvent], read: Callable[[S], R]) -> R:
        log, length = _LINEAGE.resolve(events), len(events)
        with self._lock:
            state, start = self._state, self._size
            if state is None or not _prefix_of(self._log, start, log, length):
                state, start = self._initial(), 0
            # A replay that fails part way must not be continued later.
            self._state = None
            self._advance(state, events, start)
            self._log, self._size, self._state = log, length, state
            return read(state)


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

    def latest(
        self, key: Hashable, where: Callable[[DomainEvent], bool] | None = None
    ) -> DomainEvent | None:
        """The newest of the key's events satisfying ``where``, found without a copy."""
        bounds = self._bounds(key, 0)
        if bounds is None:
            return None
        _, first, visible = bounds
        events = self._log.events[key]
        for position in range(visible - 1, first - 1, -1):
            if where is None or where(events[position]):
                return events[position]
        return None

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
        positions: list[int] = []
        events: list[DomainEvent] = []
        groups = 0
        for key in unique:
            bounds = self._bounds(key, start)
            if bounds is None:
                continue
            key_positions, first, visible = bounds
            positions += key_positions[first:visible]
            events += self._log.events[key][first:visible]
            groups += 1
        if groups < 2:
            return events
        # Positions are unique, so ordering by them alone restores history order.
        order = sorted(range(len(positions)), key=positions.__getitem__)
        return list(itemgetter(*order)(events))

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


def kind_subset_index(*kinds: str) -> Callable[[Sequence[DomainEvent]], GroupIndex]:
    """A private, incrementally maintained index of just ``kinds``, grouped by kind.

    Unlike ``kind_index`` its cache is its own, so sequences that are folded only now and
    then (time-ordered views of history, say) are not evicted by the shared index's traffic,
    and it records nothing but the kinds asked for.
    """
    wanted = frozenset(kinds)
    fold: IncrementalFold[GroupIndex] = IncrementalFold(
        GroupIndex,
        lambda index, event: index.with_event(event.kind if event.kind in wanted else None, event),
    )
    return fold


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
IRREGULAR = _IRREGULAR = object()


def str_match_key(value: object) -> Hashable:
    """Group key for a value that may be compared with a string.

    A plain ``str`` is its own key; a value that can never equal one is None (ungrouped);
    anything else is ``IRREGULAR``, a group every string query must also consider.
    """
    kind = type(value)
    return value if kind is str else None if kind in _NEVER_EQUAL_TO_STR else _IRREGULAR


def _payload_key(field: str) -> Callable[[GroupIndex, DomainEvent], GroupIndex]:
    def step(index: GroupIndex, event: DomainEvent) -> GroupIndex:
        return index.with_event(str_match_key(event.payload.get(field)), event)

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
