"""Nobody in Alderwick shares a past with him from before he came.

He arrived in January 2026 and has known everyone here since then at most. Given a
resident's private "old regret" to talk about, a model wrote Ellis saying "that old project
we never finished" and "I'm sorry it fell through back then", and his memory kept it. A line
that claims history between the speaker and him from years back is caught here.
"""

from __future__ import annotations

import re

_TOGETHER = re.compile(r"\b(we|us|our|you and (?:i|me))\b", re.IGNORECASE)
_LONG_AGO = re.compile(
    r"\b(years (?:back|ago)|ages ago|back (?:then|in the day)|way back|all those years)\b",
    re.IGNORECASE,
)
_UNFINISHED = re.compile(
    r"\b(?:that|the|our) (?:old )?(?:project|plan|idea|scheme|venture|thing|job) "
    r"(?:we|you and (?:i|me))\b|\bwe never (?:finished|got round|followed|did)\b"
    r"|\bremember when (?:we|you)\b|\bfell through\b",
    re.IGNORECASE,
)


def invents_shared_past(text: str) -> bool:
    """Whether a line speaks of a past the speaker and he never had."""
    if _UNFINISHED.search(text):
        return True
    return bool(_LONG_AGO.search(text) and _TOGETHER.search(text))


REVISION = (
    "Say it again without any shared past between you: you have only known each other "
    "since he came to the town in January, and nothing from before is shared. Your own past "
    "is yours alone."
)
