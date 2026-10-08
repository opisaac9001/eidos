"""Someone he keeps thinking about gets set aside for a while; retellings aren't padded."""

import random

from eidos.adapters.http_gateway import compact_context
from eidos.application.inner_stream import Cue, choose_cue, rutted_people
from eidos.application.voicing import unpadded

EVENING = [
    "Dusk feels thick here. Wonder if Rowan's latest piece catches the light tonight.",
    "Still light out. Wonder if Beth's actually packing her bag tonight.",
    "Clouds low over the river. Wonder if Rowan's work catches the light.",
    "River's quiet now. Hope Rowan gets some rest before that drive home.",
    "Parcel left by Mara. Wonder if Rowan needs a break.",
]
NAMES = {"Rowan", "Beth", "Mara", "Ellis"}


def test_someone_in_most_of_his_last_thoughts_is_set_aside() -> None:
    assert rutted_people(EVENING, NAMES) == ["Rowan"]
    assert rutted_people(EVENING[:2], NAMES) == []


def test_cues_about_them_are_mostly_passed_over() -> None:
    cues = [Cue("concern", "worried about Rowan"), Cue("here", "the river, evening")]
    rng = random.Random(4)
    picks = [choose_cue(cues, [], rng, (), ["Rowan"]).text for _ in range(400)]
    assert picks.count("worried about Rowan") < 0.3 * len(picks)
    rng = random.Random(4)
    fair = [choose_cue(cues, [], rng).text for _ in range(400)]
    assert fair.count("worried about Rowan") > picks.count("worried about Rowan")


def test_the_small_model_is_told_and_shown_what_it_will_be_judged_against() -> None:
    details = compact_context(
        "murmur", {"recent_inner_stream": EVENING[-3:], "leave_aside": ["Rowan"]}
    )
    assert details["leave_out_people"] == ["Rowan"]
    assert len(details["recent_thoughts"]) == 3


def test_retellings_lose_their_filler_endings() -> None:
    assert (
        unpadded(
            "New motor brushes in the hoover, and no more burning smell. Not much to add, really."
        )
        == "New motor brushes in the hoover, and no more burning smell."
    )
    assert unpadded("I fixed it, anyway, and it works.") == "I fixed it, anyway, and it works."
    assert unpadded("Anyway, Mum rang.") == "Anyway, Mum rang."
