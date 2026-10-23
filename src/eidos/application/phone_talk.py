"""A phone call has words in it, both ways.

A friend rang and the call was answered and completed without a word said; he rang Rowan,
Rowan asked "How are you?", and the call ended there. Now a call he answers has their
opening, his reply and their sign-off; a call he makes goes on past their first answer.
The lines are checked the way texts are (no plan nobody made, no narration in place of
speech), and each becomes a memory of what was said.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Callable, Mapping, Sequence

from eidos.application.bookings import remember
from eidos.application.cognition import perform
from eidos.application.friends_lives import friends_lives_context
from eidos.application.reaching_out import _EMOJI, _SCHEMA, REACHED, REPLIED, invents_a_plan
from eidos.application.shared_past import narrates_the_speaker
from eidos.domain.british import british
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest

TURN = "call.turn_taken"
WITHIN = timedelta(hours=2)


def _at(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


async def call_talk_events(
    history: Sequence[DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    *,
    names: Mapping[str, str],
    whereabouts: Callable[[str], Mapping[str, object]] | None = None,
) -> list[DomainEvent]:
    """Words for a call that has none yet: one call at a time, within two hours of it."""
    talked = {str(e.payload.get("call_id")) for e in events_of(history, TURN)}
    for answered in reversed(events_of(history, "phone.call_answered")[-6:]):
        call_id = str(answered.payload.get("call_id"))
        caller = str(answered.payload.get("caller_id") or "")
        if (
            call_id in talked
            or caller not in names
            or answered.payload.get("scene_id")
            or not at - _at(answered) <= WITHIN
        ):
            continue
        return await _talk(
            history, at, gateway, call_id, caller, names[caller], [], whereabouts, they_open=True
        )
    replied = {str(e.payload.get("contact_id")): e for e in events_of(history, REPLIED)[-20:]}
    for sent in reversed(events_of(history, REACHED)[-12:]):
        contact_id = str(sent.payload.get("contact_id"))
        answer = replied.get(contact_id)
        person = str(sent.payload.get("person_id") or "")
        if (
            sent.payload.get("channel") != "call"
            or answer is None
            or contact_id in talked
            or person not in names
            or not at - _at(sent) <= WITHIN
        ):
            continue
        prior = [
            ("Patrick", str(sent.payload.get("text", ""))),
            (names[person], str(answer.payload.get("text", ""))),
        ]
        return await _talk(
            history, at, gateway, contact_id, person, names[person], prior, whereabouts,
            they_open=False,
        )  # fmt: skip
    return []


async def _talk(
    history: Sequence[DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    call_id: str,
    person_id: str,
    name: str,
    prior: list[tuple[str, str]],
    whereabouts: Callable[[str], Mapping[str, object]] | None,
    *,
    they_open: bool,
) -> list[DomainEvent]:
    output: list[DomainEvent] = []
    turns = list(prior)
    their_life = [
        str(item["what"])
        for item in friends_lives_context(history, at, {person_id: name})
        if item["who"] == name
    ][:3]
    right_now = dict(whereabouts(person_id)) if whereabouts else {}

    async def theirs(instruction: str) -> str | None:
        pending: list[DomainEvent] = []
        asked = {
            "time": at.isoformat(),
            "location": "on the phone",
            "person": name,
            "scene_mode": True,
            "scene_speaker": name,
            "scene_audience": "pathos",
            "scene_topic": "a phone call with Patrick",
            "prior_turns": [{"speaker": s, "text": t} for s, t in turns[-4:]],
            "personal_relationship_context": {
                "owner": name,
                "about": "pathos",
                "what_is_going_on_in_their_life": their_life,
                "right_now": right_now,
                "instruction": instruction,
            },
        }
        line = await perform(gateway, "firmament", asked, at.isoformat(), pending)
        output.extend(e for e in pending if e.kind == "role.completed")
        if line is None or narrates_the_speaker(line, name):
            return None
        if invents_a_plan(history, person_id, line, at) is not None:
            return None
        return line

    async def his(instruction: str) -> str | None:
        request = ModelRequest(
            capability="pathos_text",
            task_version="1",
            temperature=0.7,
            max_output_tokens=120,
            output_schema=_SCHEMA,
            messages=(
                ModelMessage(
                    "user",
                    json.dumps(
                        {
                            "task": "call",
                            "time": at.isoformat(),
                            "to": name,
                            "on_the_phone_so_far": [f"{s}: {t}" for s, t in turns[-4:]],
                            "permission": instruction
                            + " One or two short spoken lines, casual and British, answering "
                            "what they just said. Don't invent news, plans or events. Return "
                            "only the words.",
                        }
                    ),
                ),
            ),
        )
        try:
            response = await asyncio.wait_for(gateway.generate(request), timeout=50)
            raw = json.loads(response.content)
            text = british(
                " ".join(str(raw.get("text", "")).split()) if isinstance(raw, dict) else ""
            )
            text = " ".join(_EMOJI.sub("", text).split())
        except (OSError, TimeoutError, TypeError, ValueError, AttributeError):
            return None
        if not 1 <= len(text.split()) <= 60 or invents_a_plan(history, person_id, text, at):
            return None
        return text

    def turn(speaker: str, text: str, memory: str) -> None:
        event = DomainEvent(
            TURN,
            "pathos",
            {
                "call_id": call_id,
                "person_id": person_id,
                "speaker": speaker,
                "text": text,
                "simulated_at": at.isoformat(),
            },
            correlation_id=call_id,
        )
        output.append(event)
        output.append(remember(event, memory, at, 0.5, origin="lived-phone", person_id=person_id))
        turns.append((speaker, text))

    if they_open:
        opening = await theirs(
            f"{name} has rung Patrick and he's picked up. Say what {name} says first: one or "
            "two short lines, why they rang (to catch up, something from their own life), "
            "from where they are. Invent no news, plans or visits."
        )
        if opening is None:
            return output
        turn(name, opening, f"{name} rang: “{opening}”")
    reply = await his(f"Patrick is on the phone with {name}. Write what he says next.")
    if reply is None:
        return output
    turn("Patrick", reply, f"On the phone to {name}, I said: “{reply}”")
    closing = await theirs(
        f"Answer what Patrick just said and bring the call to a close, as {name} would: one "
        "or two short lines, warm, no plans made."
    )
    if closing is not None:
        turn(name, closing, f"{name}, before ringing off: “{closing}”")
    return output
