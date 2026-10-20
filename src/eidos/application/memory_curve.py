"""How memories fade: the curve, and when a thing was in the words he'd use.

Shared by recall (``memory``), nightly archiving (``memory_retention``) and the
believability measures, so they agree on what has faded.
"""

from __future__ import annotations

from datetime import datetime


def half_life_days(importance: float, rehearsals: int = 0, reminders: int = 0) -> float:
    """How long before a memory is half as easy to reach.

    Trivia goes in days, an ordinary evening in weeks, a good night out in months and the
    things that mattered most in years: importance sets it steeply (0.1: 3 days; 0.5: 7
    weeks; 0.7: 6 months; 0.9: 2 years). Each time he goes back to a memory the clock runs
    slower (the spacing effect), and being reminded of it more so.
    """
    base = 1.5 * 2 ** (10.0 * max(0.0, min(1.0, importance)))
    return float(base * 1.2 ** min(5, max(0, rehearsals)) * 1.2 ** min(3, max(0, reminders)))


def accessibility_of(
    importance: float, age_days: float, rehearsals: int = 0, reminders: int = 0
) -> float:
    """How easily a memory comes to mind now, from 1 (just happened) towards 0."""
    return float(0.5 ** (max(0.0, age_days) / half_life_days(importance, rehearsals, reminders)))


def detail_of(accessibility: float, importance: float) -> str:
    """Clear, partial or vague. What mattered keeps its gist however long ago: the night
    itself stays, the details go. Nothing stays clear on importance alone."""
    if accessibility >= 0.55:
        return "clear"
    if accessibility >= 0.2 or importance >= 0.75:
        return "partial"
    return "vague"


def when_words(remembered_at: datetime, now: datetime, detail_level: str = "clear") -> str:
    """When it was, the way he'd say it: exact only while the memory is clear.

    Hazy memories carry a hazy time ("a week or two back"), and old ones feel nearer than
    they were (people telescope: two months reads as "a few weeks ago").
    """
    days = max(0.0, (now - remembered_at).total_seconds() / 86400)
    if detail_level == "clear":
        if days < 1:
            return "earlier today" if remembered_at.date() == now.date() else "last night"
        if days < 2:
            return "yesterday"
        if days < 7:
            return f"on {remembered_at:%A}"
        if days < 14:
            return "last week"
        if days < 60:
            return f"about {max(2, round(days / 7))} weeks ago"
        return f"in {remembered_at:%B}" if days < 365 else f"in {remembered_at:%Y}"
    if days < 3:
        return "the other day"
    if days < 10:
        return "a few days back" if detail_level == "partial" else "a while back"
    if days < 45:
        return "a week or two back" if detail_level == "partial" else "a while back"
    if days < 200:
        return "a few weeks ago" if detail_level == "partial" else "a while back"
    return "months back" if detail_level == "partial" else "a long while back"
