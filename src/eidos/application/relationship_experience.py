"""Bounded NPC recollection of promises made to them, never another mind's ledger."""

from datetime import datetime
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

_RECALLED = ("commitment.created", "commitment.missed", "commitment.fulfilled", "apology.offered")


def personal_relationship_context(
    history: Sequence[DomainEvent], owner: str, other: str, now: datetime
) -> dict[str, object]:
    # Patrick's autobiographical recall must go through his existing fallible
    # memory pipeline, not this operational source adapter for resident performers.
    if owner in {"pathos", "user"} or owner == other:
        return {}
    promises: dict[str, DomainEvent] = {}
    recollections = []
    # Other kinds only reach the timestamp checks, which can raise solely for a naive ``now``.
    events = history if now.utcoffset() is None else events_of(history, *_RECALLED)
    for event in events:
        p = event.payload
        try:
            at = datetime.fromisoformat(str(p["simulated_at"]))
        except (KeyError, ValueError):
            continue
        if at.utcoffset() is None or at > now:
            continue
        if event.kind == "commitment.created":
            if p.get("creditor_id") == owner and p.get("debtor_id") == other:
                promises[str(p["commitment_id"])] = event
        elif (
            event.kind in {"commitment.missed", "commitment.fulfilled"}
            and str(p.get("commitment_id")) in promises
        ):
            age = (now - at).total_seconds() / 86400
            if age > 30:
                continue
            promise = promises[str(p["commitment_id"])]
            missed = event.kind == "commitment.missed"
            recollections.append(
                {
                    "kind": "let_down" if missed else "followed_through",
                    "recollection": (
                        "I was left waiting for something they had agreed to do."
                        if missed
                        else "They followed through on something they owed me."
                    ),
                    "detail": str(promise.payload["title"]) if age <= 3 else None,
                    "clarity": "recent" if age <= 3 else "a fading impression",
                }
            )
        elif (
            event.kind == "apology.offered"
            and p.get("actor_id") == other
            and p.get("target_id") == owner
        ):
            if (now - at).total_seconds() <= 30 * 86400:
                recollections.append(
                    {
                        "kind": "apology",
                        "recollection": "They offered me an apology. That alone does not decide whether I forgive them.",
                        "clarity": "an impression",
                    }
                )
    recent = recollections[-4:]
    misses = sum(r["kind"] == "let_down" for r in recent)
    kept = sum(r["kind"] == "followed_through" for r in recent)
    return {
        "owner": owner,
        "about": other,
        "recollections": recent,
        "inclination": "cautious about relying on another promise"
        if misses > kept
        else "some reason to rely on them"
        if kept
        else "no strong conclusion",
        "instruction": "These are your own limited impressions, not the other person's feelings or motives. Let them quietly influence your choice to agree, decline, ask a question or set a condition. Positive follow-through is not a let-down: do not default to mistrust. You need not mention these impressions. Do not turn fading impressions into exact dates, quotations or invented explanations.",
    }
