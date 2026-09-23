"""How often the neighbours reach out to Patrick.

Residents feel the need for company often; only occasionally is it Patrick they ring or
call on. Each person reaches out to him at most every few days, he fields at most one such
unprompted contact a day, and only a wish for company formed recently can prompt one.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent

PER_PERSON_GAP = timedelta(days=3)
DAILY_LIMIT = 1
FRESH_GOAL = timedelta(days=2)
_CONTACT_KINDS = frozenset({"phone.call_received", "visitor.planned"})


def contact_allowed(
    history: Sequence[DomainEvent], caller_id: str, goal: DomainEvent, simulated_at: datetime
) -> bool:
    formed = datetime.fromisoformat(str(goal.payload.get("simulated_at")))
    if simulated_at - formed > FRESH_GOAL:
        return False
    today = 0
    for event in reversed(history[-4000:]):
        if event.kind not in _CONTACT_KINDS:
            continue
        at = datetime.fromisoformat(str(event.payload.get("simulated_at")))
        if simulated_at - at >= PER_PERSON_GAP:
            break
        who = event.payload.get("caller_id") or event.payload.get("visitor_id")
        if who == caller_id:
            return False
        if at.date() == simulated_at.date():
            today += 1
    return today < DAILY_LIMIT
