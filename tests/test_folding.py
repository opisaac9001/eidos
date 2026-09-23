import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.preference_development import preference_development_events
from eidos.application.trait_development import trait_development_events
from eidos.domain import identity as identity_module
from eidos.domain import traits as traits_module
from eidos.domain.events import DomainEvent
from eidos.domain.folding import GrowOnlyMap, IncrementalFold, PersistentMap
from eidos.domain.identity import identity_established_event, project_identity
from eidos.domain.traits import project_traits


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


class GrowOnlyMapTests(unittest.TestCase):
    def test_each_state_sees_only_its_own_entries(self) -> None:
        empty: GrowOnlyMap[str, int] = GrowOnlyMap()
        one = empty.with_item("a", 1)
        two = one.with_item("b", 2)
        self.assertNotIn("a", empty)
        self.assertEqual(one.get("a"), 1)
        self.assertNotIn("b", one)
        self.assertEqual((two.get("a"), two.get("b"), len(two)), (1, 2, 2))

    def test_divergent_branches_do_not_see_each_other(self) -> None:
        base: GrowOnlyMap[str, int] = GrowOnlyMap().with_item("root", 0)
        left = base.with_item("left", 1)
        right = base.with_item("right", 2)
        self.assertIn("left", left)
        self.assertNotIn("right", left)
        self.assertIn("right", right)
        self.assertNotIn("left", right)
        self.assertEqual(left.with_item("more", 3).get("left"), 1)


class PersistentMapTests(unittest.TestCase):
    def test_overwrites_behave_like_dict_assignment_without_touching_old_states(self) -> None:
        reference: dict[str, int] = {}
        state: PersistentMap[str, int] = PersistentMap()
        states = [state]
        for key, value in [("a", 1), ("b", 2), ("a", 3), ("c", 4), ("b", 5)]:
            reference[key] = value
            state = state.with_item(key, value)
            states.append(state)
            self.assertEqual(list(state.items()), list(reference.items()))
        self.assertEqual(list(states[2].items()), [("a", 1), ("b", 2)])
        self.assertEqual((states[3]["a"], states[2]["a"]), (3, 1))
        self.assertNotIn("c", states[3])
        with self.assertRaises(KeyError):
            states[1]["b"]

    def test_divergent_branches_keep_their_own_values(self) -> None:
        base: PersistentMap[str, int] = PersistentMap().with_item("a", 1).with_item("b", 2)
        left = base.with_item("a", 10).with_item("x", 0)
        right = base.with_item("b", 20)
        self.assertEqual(list(left.items()), [("a", 10), ("b", 2), ("x", 0)])
        self.assertEqual(list(right.items()), [("a", 1), ("b", 20)])
        self.assertEqual(list(base.items()), [("a", 1), ("b", 2)])
        self.assertEqual(list(left.with_item("b", 7).values()), [10, 7, 0])
        self.assertEqual(list(right.items()), [("a", 1), ("b", 20)])


class ProjectionReuseTests(unittest.TestCase):
    """Folding a prefix, then extending it, must match a fold from scratch."""

    start = datetime(2026, 1, 1, 16, tzinfo=timezone.utc)

    def realized(self, day: int, action: str) -> DomainEvent:
        return DomainEvent(
            "agency.activity_realized",
            "pathos",
            {
                "activity_type": f"voluntary_activity_{day}",
                "action": action,
                "title": f"Voluntary activity {day}",
                "location_id": "new-place",
                "companion_id": None,
                "simulated_at": (self.start + timedelta(days=day)).isoformat(),
            },
        )

    def test_identity_reuse_matches_a_fresh_fold_through_emergence_and_retirement(self) -> None:
        established = identity_established_event(self.start.isoformat())
        sources = [self.realized(day, "work") for day in (0, 4, 8)]
        emerged_at = (self.start + timedelta(days=8)).replace(hour=20)
        history = [established, *sources]
        emerged = preference_development_events(history, emerged_at)[0]
        history.append(emerged)
        retired = preference_development_events(history, emerged_at + timedelta(days=120))[0]
        full = [*history, retired]

        incremental = [project_identity(full[:size]) for size in range(len(full) + 1)]
        # A speculative branch that is later abandoned must not disturb the real one.
        project_identity([*history, self.realized(9, "work")])
        extended = project_identity(full)
        identity_module._IDENTITY_FOLD.clear()
        fresh = [project_identity(list(full[:size])) for size in range(len(full) + 1)]
        self.assertEqual(incremental, fresh)
        self.assertEqual(extended, fresh[-1])
        self.assertEqual(incremental[-2].preferences[-1], "making things through focused work")

        # A reused prefix must fail at the same event with the same message.
        project_identity(history)
        with self.assertRaisesRegex(ValueError, "Preference changes must be at least fourteen"):
            project_identity(
                [
                    *history,
                    DomainEvent(
                        "preference.retired",
                        "pathos",
                        {
                            **retired.payload,
                            "simulated_at": (emerged_at + timedelta(days=1)).isoformat(),
                        },
                    ),
                ]
            )

    def test_traits_reuse_matches_a_fresh_fold_and_tracks_replaced_identity(self) -> None:
        established = identity_established_event(self.start.isoformat())
        sources = [self.realized(day, "learn") for day in (0, 8, 16, 24, 32)]
        review = (self.start + timedelta(days=32)).replace(hour=20)
        adjusted = trait_development_events([established, *sources], review)
        self.assertEqual(len(adjusted), 1)
        full = [established, *sources, *adjusted]

        incremental = [project_traits(full[:size]) for size in range(len(full) + 1)]
        traits_module._TRAIT_FOLD.clear()
        fresh = [project_traits(list(full[:size])) for size in range(len(full) + 1)]
        self.assertEqual(incremental, fresh)
        self.assertNotEqual(fresh[-1], fresh[-2])

        # An event reusing the identity event's id replaces it in the evidence map, so the
        # adjustment must then fail exactly as the former dict-based scan did.
        impostor = DomainEvent("note.recorded", "pathos", {}, event_id=established.event_id)
        project_traits([established, *sources])
        with self.assertRaisesRegex(ValueError, "before identity exists"):
            project_traits([established, *sources, impostor, *adjusted])
        self.assertEqual(project_traits(full), fresh[-1])


if __name__ == "__main__":
    unittest.main()
