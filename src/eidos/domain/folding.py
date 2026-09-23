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
from collections.abc import Callable, Hashable, Sequence
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
