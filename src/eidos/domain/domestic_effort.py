"""Explicit simulation calibration, not a model's claimed accomplishment."""

# A thirty-minute dish session devotes 75% of its effort to washing. Keep
# physical output independent of how short a session the planner books.
DISH_LOAD_PER_WASH_SECOND = 0.55 / (30 * 60 * 0.75)


def washed_load(wash_seconds: float) -> float:
    return min(0.55, max(0.0, wash_seconds) * DISH_LOAD_PER_WASH_SECOND)
