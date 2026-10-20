"""A cue brings back what it's about, not only what shares its words."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from eidos.adapters.sqlite_memory_vectors import SQLiteMemoryVectors
from eidos.application.memory import recall
from eidos.application.memory_meaning import MeaningIndex, rescaled, set_meaning_index
from eidos.domain.events import DomainEvent

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
# A toy sense of meaning: words that mean the same share an axis.
_AXES = {
    "lamp": 0, "light": 0, "fitting": 0, "bulb": 0,
    "bread": 1, "loaf": 1, "bakery": 1,
    "river": 2, "water": 2, "bank": 2,
}  # fmt: skip


class _Embedder:
    model = "toy"

    def __init__(self) -> None:
        self.calls = 0
        self.down = False

    def embed(self, texts):
        self.calls += 1
        if self.down:
            return None
        out = []
        for text in texts:
            vector = [0.05] * 4
            for word in text.casefold().split():
                axis = _AXES.get(word.strip(".,?'"))
                if axis is not None:
                    vector[axis] += 1.0
            out.append(vector)
        return out


def _memory(text: str, days_ago: float) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "owner": "pathos",
            "importance": 0.5,
            "confidence": 1.0,
            "simulated_at": (NOW - timedelta(days=days_ago)).isoformat(),
        },
    )


def test_the_light_fitting_brings_back_the_lamp(tmp_path: Path) -> None:
    lamp = _memory("Mara asked about the lamp.", 3)
    loaf = _memory("Picked up a loaf from the bakery.", 3)
    river = _memory("Walked by the river.", 3)
    history = [lamp, loaf, river]
    set_meaning_index(None)
    try:
        by_words = recall(history, "the light fitting", NOW, 3)
        assert all(item.components.get("meaning", 0.0) == 0.0 for item in by_words)
        index = MeaningIndex(_Embedder(), SQLiteMemoryVectors(tmp_path / "v.sqlite3"))
        assert index.embed_missing(history) == 3
        set_meaning_index(index)
        by_meaning = recall(history, "the light fitting", NOW, 3)
        assert by_meaning[0].event is lamp
        assert by_meaning[0].components["meaning"] > 0.1
        assert "meaning" in by_meaning[0].components
        assert math.isclose(
            sum(by_meaning[0].components.values()), by_meaning[0].score, abs_tol=1e-3
        )
        # Kept beside his history: a fresh index loads them without asking the model again.
        again = MeaningIndex(_Embedder(), SQLiteMemoryVectors(tmp_path / "v.sqlite3"))
        assert len(again) == 3 and again.embed_missing(history) == 0
    finally:
        set_meaning_index(None)


def test_what_comes_up_primes_the_memories_near_it(tmp_path: Path) -> None:
    lamp = _memory("Mara asked about the lamp.", 3)
    bulb = _memory("The bulb for the light went in the end.", 20)
    loaf = _memory("Picked up a loaf from the bakery.", 1)
    history = [lamp, bulb, loaf]
    index = MeaningIndex(_Embedder(), None)
    index.embed_missing(history)
    set_meaning_index(index)
    try:
        results = recall(history, "lamp fitting", NOW, 3)
        primed = next(item for item in results if item.event is bulb)
        assert primed.components.get("spread", 0.0) > 0
        unrelated = next(item for item in results if item.event is loaf)
        assert "spread" not in unrelated.components
    finally:
        set_meaning_index(None)


def test_without_the_model_recall_goes_on_by_words() -> None:
    embedder = _Embedder()
    embedder.down = True
    index = MeaningIndex(embedder, None)
    history = [_memory("Mara asked about the lamp.", 3)]
    assert index.embed_missing(history) == 0
    set_meaning_index(index)
    try:
        results = recall(history, "the lamp", NOW, 3)
        assert results and results[0].components.get("meaning", 0.0) == 0.0
    finally:
        set_meaning_index(None)
    assert rescaled(0.2) == 0.0 and rescaled(0.9) == 1.0 and 0 < rescaled(0.6) < 1
