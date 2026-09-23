import unittest

from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold


def _events(count: int) -> list[DomainEvent]:
    return [DomainEvent("test.counted", "pathos", {"n": index}) for index in range(count)]


class CountingFold:
    def __init__(self) -> None:
        self.steps = 0
        self.fold: IncrementalFold[tuple[int, ...]] = IncrementalFold(tuple, self.step)

    def step(self, state: tuple[int, ...], event: DomainEvent) -> tuple[int, ...]:
        self.steps += 1
        return (*state, int(event.payload["n"]))


class IncrementalFoldTests(unittest.TestCase):
    def test_extending_the_same_prefix_only_folds_new_events(self) -> None:
        counter = CountingFold()
        history = _events(50)
        self.assertEqual(counter.fold(history), tuple(range(50)))
        pending = _events(3)
        self.assertEqual(counter.fold(history + pending)[-3:], (0, 1, 2))
        self.assertEqual(counter.steps, 53)

    def test_identical_sequence_is_returned_without_refolding(self) -> None:
        counter = CountingFold()
        history = _events(10)
        counter.fold(history)
        counter.fold(list(history))
        self.assertEqual(counter.steps, 10)

    def test_equal_looking_but_different_events_never_share_a_prefix(self) -> None:
        counter = CountingFold()
        first = _events(5)
        counter.fold(first)
        second = _events(5)
        self.assertEqual(counter.fold(second), tuple(range(5)))
        self.assertEqual(counter.steps, 10)

    def test_filtered_or_reordered_sequences_fold_from_the_start(self) -> None:
        counter = CountingFold()
        history = _events(6)
        counter.fold(history)
        self.assertEqual(counter.fold(history[::-1]), tuple(reversed(range(6))))
        self.assertEqual(counter.fold(history[1:]), tuple(range(1, 6)))

    def test_rejected_speculation_does_not_evict_the_genuine_prefix(self) -> None:
        counter = CountingFold()
        history = _events(40)
        counter.fold(history)
        counter.fold(history + _events(2))
        counter.steps = 0
        counter.fold(history + _events(1))
        self.assertEqual(counter.steps, 1)

    def test_keys_keep_differently_seeded_folds_apart(self) -> None:
        fold: IncrementalFold[tuple[str, int]] = IncrementalFold(
            lambda: ("default", 0), lambda state, _event: (state[0], state[1] + 1)
        )
        history = _events(3)
        self.assertEqual(fold(history, key=1, initial=lambda: ("one", 0)), ("one", 3))
        self.assertEqual(fold(history, key=2, initial=lambda: ("two", 0)), ("two", 3))
        self.assertEqual(fold(history, key=1, initial=lambda: ("ignored", 0)), ("one", 3))


if __name__ == "__main__":
    unittest.main()
