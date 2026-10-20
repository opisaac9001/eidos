"""Recall by meaning: a cue brings back what it's about, not only what shares its words.

Recall matched words. "The light fitting" never brought back the lamp, and nothing one
memory brought up primed the ones like it. With a small local embedding model each
memory has a vector; a cue's vector is compared with them (cosine), and the memory that
comes up most strongly primes the ones near it (spreading activation, as in the
Generative Agents retrieval). Vectors are derived and kept beside his history, never in
it; without the model, recall goes on by words alone.
"""

from __future__ import annotations

import logging
import math
from collections import OrderedDict
from threading import Lock
from typing import Mapping, Protocol, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

logger = logging.getLogger(__name__)
# nomic's cosines run about 0.3 for unrelated text and 0.8 for the same thing said again.
UNRELATED, SAME = 0.35, 0.85


class Embedder(Protocol):
    model: str

    def embed(self, texts: Sequence[str]) -> list[list[float]] | None: ...


class VectorStore(Protocol):
    def load_all(self, model: str) -> dict[str, list[float]]: ...

    def put_many(self, model: str, rows: Sequence[tuple[str, Sequence[float]]]) -> None: ...


def _unit(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(math.sumprod(vector, vector)) or 1.0
    return [x / norm for x in vector]


def rescaled(cosine: float) -> float:
    """Cosine as a 0-to-1 strength: nothing below unrelated, full at 'the same thing'."""
    return max(0.0, min(1.0, (cosine - UNRELATED) / (SAME - UNRELATED)))


class MeaningIndex:
    """Vectors for his memories, and what a cue is close to."""

    def __init__(self, embedder: Embedder, store: VectorStore | None = None) -> None:
        self.embedder = embedder
        self.store = store
        self.model = embedder.model
        self.vectors: dict[str, list[float]] = {}
        if store is not None:
            try:
                self.vectors = {k: _unit(v) for k, v in store.load_all(self.model).items()}
            except Exception:
                logger.exception("Couldn't load memory vectors")
        self._queries: OrderedDict[str, list[float] | None] = OrderedDict()
        self._lock = Lock()

    def __len__(self) -> int:
        return len(self.vectors)

    def embed_missing(self, history: Sequence[DomainEvent], limit: int = 256) -> int:
        """Vectors for memories that have none yet, oldest first; how many were added."""
        waiting: list[tuple[str, str]] = []
        for memory in events_of(history, "memory.recorded"):
            if memory.payload.get("owner", "pathos") != "pathos":
                continue
            if memory.payload.get("category") == "dream":
                continue
            memory_id = str(memory.event_id)
            text = str(memory.payload.get("text", "")).strip()
            if text and memory_id not in self.vectors:
                waiting.append((memory_id, text))
            if len(waiting) >= limit:
                break
        if not waiting:
            return 0
        vectors = self.embedder.embed([text for _, text in waiting])
        if vectors is None:
            return 0
        rows = [(memory_id, vector) for (memory_id, _), vector in zip(waiting, vectors)]
        with self._lock:
            for memory_id, vector in rows:
                self.vectors[memory_id] = _unit(vector)
        if self.store is not None:
            try:
                self.store.put_many(self.model, rows)
            except Exception:
                logger.exception("Couldn't keep memory vectors")
        return len(rows)

    def query_vector(self, text: str) -> list[float] | None:
        key = " ".join(text.casefold().split())[:400]
        if not key:
            return None
        with self._lock:
            if key in self._queries:
                self._queries.move_to_end(key)
                return self._queries[key]
        vectors = self.embedder.embed([key])
        vector = _unit(vectors[0]) if vectors else None
        with self._lock:
            self._queries[key] = vector
            while len(self._queries) > 256:
                self._queries.popitem(last=False)
        return vector

    def similarities(self, text: str, memory_ids: Sequence[str]) -> dict[str, float]:
        """How close each memory is to the cue, 0 to 1; only those with a vector."""
        query = self.query_vector(text)
        if query is None:
            return {}
        with self._lock:
            return {
                memory_id: rescaled(math.sumprod(query, vector))
                for memory_id in memory_ids
                if (vector := self.vectors.get(memory_id)) is not None
            }

    def between(self, memory_id: str, others: Sequence[str]) -> dict[str, float]:
        """How close other memories are to this one: what it primes."""
        with self._lock:
            anchor = self.vectors.get(memory_id)
            if anchor is None:
                return {}
            return {
                other: rescaled(math.sumprod(anchor, vector))
                for other in others
                if other != memory_id and (vector := self.vectors.get(other)) is not None
            }


_CURRENT: MeaningIndex | None = None


def set_meaning_index(index: MeaningIndex | None) -> None:
    global _CURRENT
    _CURRENT = index


def meaning_index() -> MeaningIndex | None:
    return _CURRENT


def meaning_context(similarities: Mapping[str, float]) -> dict[str, float]:
    return {k: round(v, 4) for k, v in similarities.items()}
