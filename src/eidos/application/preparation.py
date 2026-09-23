"""Optional scales of domestic effort, never an automatic morning itinerary."""

from math import ceil
from typing import Mapping, Sequence

from eidos.domain.domestic_effort import DISH_LOAD_PER_WASH_SECOND
from eidos.domain.events import DomainEvent
from eidos.domain.household import project_household


def preparation_context(
    history: Sequence[DomainEvent],
    *,
    location_id: str | None,
    needs: Mapping[str, float],
    time_budget: Mapping[str, object],
) -> dict[str, object]:
    """Describe tradeoffs; choosing, booking and executing remain separate."""
    pulls = []
    if needs.get("energy", 0.5) < 0.35 or needs.get("rest", 0.5) < 0.3:
        pulls.append(
            "Low energy: starting or returning to effort may feel harder; resting is an option."
        )
    if needs.get("hunger", 0.0) >= 0.55:
        pulls.append("Hunger competes for attention; a chore does not satisfy it.")
    if needs.get("connection", 0.5) < 0.35:
        pulls.append("Wanting company can coexist with tiredness or unfinished chores.")
    free = time_budget.get("free_minutes")
    alternatives = []
    household = project_household(history) if location_id == "home" else None
    if household is not None and household.established and household.loads["dishes"] >= 0.25:
        # Rough estimates, not a reading of a stopwatch or an enforced duration.
        full = max(
            5, 5 * ceil(household.loads["dishes"] / DISH_LOAD_PER_WASH_SECOND / 0.75 / 60 / 5)
        )
        for scope, minutes, consequence in (
            ("small_batch", 5, "Wash a few things; most of a large pile may remain."),
            ("make_a_dent", 15, "Reduce the pile, without promising a clear kitchen."),
            (
                "longer_session",
                min(30, full),
                "Work through more of the pile; a large backlog may remain.",
            ),
        ):
            slower = needs.get("energy", 0.5) < 0.35
            upper = ceil(minutes * (1.5 if slower else 1.2))
            alternatives.append(
                {
                    "activity_type": "household_dishes",
                    "action": "work",
                    "location_id": "home",
                    "scope": scope,
                    "estimated_minutes": [minutes, upper],
                    "fits_before_departure": None if free is None else upper <= float(str(free)),
                    "possible_consequence": consequence,
                }
            )
    return {
        "felt_tradeoffs": pulls,
        "optional_scales": alternatives,
        "action_authority": False,
        "meaning": (
            "Examples, not a menu or checklist. No activity has happened. You may choose another "
            "activity, do less, defer chores, leave early, or make no new plan. Estimates can be wrong; "
            "do not shrink the same accomplishment into fewer minutes. Mood and needs can pull in "
            "different directions; no strongest need is required to win. Existing commitments are "
            "not moved or renegotiated by this context."
        ),
    }
