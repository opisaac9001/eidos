"""Recurring, relationship-paced conversations grounded in shared observations."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.application.cognition import perform
from eidos.application.epistemics import pathos_person_introduction_event
from eidos.application.followups import project_followups
from eidos.application.freelance import work_view
from eidos.application.gossip import they_remember
from eidos.application.inner_stream import near_repeat
from eidos.application.pronouns import SAYING, pronoun_of
from eidos.application.relationship_experience import personal_relationship_context
from eidos.application.shared_past import (
    ITS_HIS,
    NOT_TO_YOURSELF,
    NOT_YOURS,
    REVISION,
    SAY_IT,
    THING_REVISION,
    addresses_self,
    claims_his_project,
    gives_away_his_project,
    invents_past_talk,
    invents_shared_past,
    invents_shared_thing,
    narrates_the_speaker,
)
from eidos.application.talking_points import his_projects, setting, talking_points
from eidos.domain.character_history import eligible_character_fact
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.relationship_repairs import project_relationship_repairs
from eidos.domain.relationships import Relationship
from eidos.domain.scenes import (
    SceneEndProposal,
    SceneEndReason,
    ScenePrivacy,
    SceneStartProposal,
    SceneTurnProposal,
    project_scenes,
    resolve_scene_end,
    resolve_scene_start,
    resolve_scene_turn,
)
from eidos.domain.social_preferences import project_social_preferences
from eidos.ports.model_gateway import ModelGateway


async def recurring_dialogue_events(
    history: Sequence[DomainEvent],
    actor_locations: Mapping[str, str],
    actor_names: Mapping[str, str],
    relationships: Mapping[str, Relationship],
    simulated_at: datetime,
    actual_revision: int,
    gateway: ModelGateway,
    meeting: str | None = None,
) -> list[DomainEvent]:
    """Start or advance one ordinary NPC conversation without leaking private state.

    ``meeting`` is someone he arranged to meet here now: the conversation is with them."""
    state = project_scenes(history)
    active = next(
        (
            scene
            for scene in state.scenes.values()
            if scene.status == "active"
            and scene.scene_id.startswith("ordinary-")
            and "pathos" in {scene.initiator_id, scene.partner_id}
        ),
        None,
    )
    if active is not None:
        partner_id = active.partner_id if active.initiator_id == "pathos" else active.initiator_id
        if (
            actor_locations.get(partner_id) != active.location_id
            or actor_locations.get("pathos") != active.location_id
        ):
            ended = resolve_scene_end(
                SceneEndProposal(
                    f"leave-{active.scene_id}-{simulated_at.isoformat()}",
                    active.scene_id,
                    partner_id,
                    SceneEndReason.LEFT,
                    actual_revision,
                ),
                state=state,
                history=history,
                actual_revision=actual_revision,
                simulated_at=simulated_at.isoformat(),
            )
            return list(ended.events)
        return await _advance_scene(
            history,
            [],
            actor_locations,
            actor_names,
            relationships.get(partner_id, Relationship(partner_id)),
            simulated_at,
            actual_revision,
            gateway,
            active.scene_id,
            partner_id,
        )
    if any(
        scene.status in {"active", "paused"} and "pathos" in {scene.initiator_id, scene.partner_id}
        for scene in state.scenes.values()
    ):
        return []
    location_id = actor_locations.get("pathos")
    if location_id in {None, "home"}:
        return []
    ready_people = {
        item.person_id for item in project_followups(history).values() if item.status == "ready"
    }
    busy_actors = {
        actor_id
        for scene in state.scenes.values()
        if scene.status in {"active", "paused"}
        for actor_id in (scene.initiator_id, scene.partner_id)
    }
    candidates = sorted(
        (
            actor_id
            for actor_id, location in actor_locations.items()
            if actor_id not in {"pathos", "user"}
            and actor_id not in busy_actors
            and location == location_id
            and actor_id in actor_names
            and (
                actor_id == meeting
                or _cooldown_complete(history, actor_id, simulated_at, relationships)
            )
        ),
        key=lambda actor_id: (actor_id != meeting, actor_id not in ready_people, actor_id),
    )
    if not candidates:
        return []
    partner_id = candidates[0]
    relationship = relationships.get(partner_id, Relationship(partner_id))
    topics, _ = _topics(
        history,
        simulated_at,
        location_id,
        partner_id,
        actor_names.get(partner_id, partner_id.replace("-", " ").title()),
    )
    scene_id = f"ordinary-{simulated_at.date().isoformat()}-{partner_id}-{location_id}"
    max_turns = 2 if relationship.familiarity < 0.35 else 4 if relationship.familiarity < 0.7 else 6
    start = resolve_scene_start(
        SceneStartProposal(
            f"start-{scene_id}",
            scene_id,
            "pathos",
            partner_id,
            topics[0],
            max_turns,
            actual_revision,
        ),
        state=state,
        actor_locations=actor_locations,
        known_actor_ids=set(actor_locations),
        actual_revision=actual_revision,
        simulated_at=simulated_at.isoformat(),
    )
    output = list(start.events)
    if not start.accepted:
        return output
    started = next(event for event in output if event.kind == "scene.started")
    introduction = pathos_person_introduction_event(
        history,
        person_id=partner_id,
        source_event=started,
        simulated_at=simulated_at,
        location_id=location_id,
        manner="in_person_conversation",
    )
    if introduction is not None:
        output.append(introduction)
    return await _advance_scene(
        history,
        output,
        actor_locations,
        actor_names,
        relationship,
        simulated_at,
        actual_revision,
        gateway,
        scene_id,
        partner_id,
    )


async def _advance_scene(
    history: Sequence[DomainEvent],
    output: list[DomainEvent],
    actor_locations: Mapping[str, str],
    actor_names: Mapping[str, str],
    relationship: Relationship,
    simulated_at: datetime,
    actual_revision: int,
    gateway: ModelGateway,
    scene_id: str,
    partner_id: str,
) -> list[DomainEvent]:
    topics, topic_words = _topics(
        history,
        simulated_at,
        actor_locations["pathos"],
        partner_id,
        actor_names.get(partner_id, partner_id.replace("-", " ").title()),
    )
    for _ in range(2):
        combined = [*history, *output]
        scene = project_scenes(combined).scenes[scene_id]
        if scene.status != "active":
            break
        topic_id = topics[min(scene.turn_count // 2, len(topics) - 1)]
        speaker_id = scene.next_actor_id
        name = actor_names.get(partner_id, partner_id.replace("-", " ").title())
        disclosure = (
            eligible_character_fact(combined, partner_id, relationship.familiarity, scene_id)
            if speaker_id == partner_id
            else None
        )
        text: str | None
        asked: dict[str, object] | None = None
        if disclosure is not None:
            decision = DomainEvent(
                "npc.biography_disclosure_decided",
                "pathos",
                {
                    "fact_id": disclosure.fact_id,
                    "person_id": partner_id,
                    "scene_id": scene_id,
                    "decision": "share",
                    "owner": partner_id,
                    "visibility": "private",
                    "simulated_at": simulated_at.isoformat(),
                },
                correlation_id=scene_id,
            )
            output.append(decision)
            topic_id = f"personal-history-{disclosure.topic}"
            text = f"I haven't told many people this: {disclosure.text}"
        else:
            asked = {
                "time": simulated_at.isoformat(),
                "location": scene.location_id,
                "person": name,
                "scene_mode": True,
                "scene_speaker": speaker_id,
                "scene_audience": (
                    scene.partner_id if speaker_id == scene.initiator_id else scene.initiator_id
                ),
                "scene_topic": topic_words.get(topic_id) or _topic_words(topic_id, name),
                # Speaking himself, he talks from how his life really stands, not a
                # version the model makes up ("talking it over with Beth").
                **(
                    {"his_news": news}
                    if speaker_id == "pathos" and (news := work_view(combined, simulated_at)[:3])
                    else {}
                ),
                # Why they're both there: at work, he isn't "just dropping in".
                "setting": setting(
                    combined, simulated_at, scene.location_id.replace("-", " "), name
                ),
                # Everyone he knows, so people mentioned in passing are right too.
                "pronouns": {
                    person_name: SAYING[pronoun_of(pid)]
                    for pid, person_name in actor_names.items()
                    if pid not in {"pathos", "user"}
                }
                | {"Patrick": "he/him"},
                **(
                    {"they_remember": remembered}
                    if speaker_id == partner_id
                    and (remembered := they_remember(combined, partner_id, simulated_at))
                    else {}
                ),
                "who_is_who": {
                    partner_id: name,
                    **{k: v for k, v in actor_names.items() if k in {speaker_id, partner_id}},
                },
                "personal_relationship_context": personal_relationship_context(
                    combined,
                    speaker_id,
                    "pathos" if speaker_id == partner_id else partner_id,
                    simulated_at,
                ),
                "prior_turns": [
                    {
                        "speaker": str(event.payload["actor_id"]),
                        "text": str(event.payload["text"]),
                    }
                    for event in combined
                    if event.kind == "scene.turn_taken"
                    and event.payload.get("scene_id") == scene_id
                ][-6:],
            }
            text = await perform(
                gateway,
                "firmament",
                asked,
                simulated_at.isoformat(),
                output,
            )
        held = asked.get("they_remember") if asked else None
        memories = [str(m) for m in held] if isinstance(held, list) else []
        their_lines = [
            str(event.payload["text"])
            for event in [*history, *output]
            if event.kind == "scene.turn_taken"
            and event.payload.get("scene_id") == scene_id
            and event.payload.get("actor_id") == speaker_id
        ]
        if text is not None and asked is not None and near_repeat(text, their_lines):
            # Saying the same thing again ("Cheers, Patrick. I should probably reach out to
            # Ellis...", twice running): asked once for something that moves it on.
            text = await perform(
                gateway,
                "firmament",
                {**asked, "revision_instruction": SAID_IT_ALREADY},
                simulated_at.isoformat(),
                output,
            )
            if text is not None and near_repeat(text, their_lines):
                text = None
        grounded = (
            " ".join(str(asked.get(key, "")) for key in ("scene_topic", "setting", "his_news"))
            if asked
            else ""
        )
        projects = his_projects(combined)
        if (
            text is not None
            and asked is not None
            and invents_shared_thing(text, grounded, projects)
        ):
            # "Have you talked to Ellis about that old project yet?": there is no project.
            text = await perform(
                gateway,
                "firmament",
                {**asked, "revision_instruction": THING_REVISION},
                simulated_at.isoformat(),
                output,
            )
            if text is not None and invents_shared_thing(text, grounded, projects):
                text = None
        speaker_name = "Patrick" if speaker_id == "pathos" else name
        if text is not None and asked is not None and narrates_the_speaker(text, speaker_name):
            # "Mara waves over to Rowan and asks...", given as Mara's own words.
            text = await perform(
                gateway,
                "firmament",
                {**asked, "revision_instruction": SAY_IT},
                simulated_at.isoformat(),
                output,
            )
            if text is not None and narrates_the_speaker(text, speaker_name):
                text = None
        if text is not None and asked is not None and addresses_self(text, speaker_name):
            # Hannah: "Hannah, I remember you mentioned turning down an opportunity...":
            # Patrick's line, given to her.
            text = await perform(
                gateway,
                "firmament",
                {**asked, "revision_instruction": NOT_TO_YOURSELF},
                simulated_at.isoformat(),
                output,
            )
            if text is not None and addresses_self(text, speaker_name):
                text = None
        if (
            text is not None
            and asked is not None
            and speaker_id == "pathos"
            and gives_away_his_project(text, projects)
        ):
            # Patrick to Ellis: "mics that'd suit your project", of his own atlas.
            text = await perform(
                gateway,
                "firmament",
                {**asked, "revision_instruction": ITS_HIS},
                simulated_at.isoformat(),
                output,
            )
            if text is not None and gives_away_his_project(text, projects):
                text = None
        if (
            text is not None
            and asked is not None
            and speaker_id != "pathos"
            and claims_his_project(text, projects)
        ):
            # Ellis: "I've been working on this small atlas of neighbourhood sounds". It's his.
            text = await perform(
                gateway,
                "firmament",
                {**asked, "revision_instruction": NOT_YOURS},
                simulated_at.isoformat(),
                output,
            )
            if text is not None and claims_his_project(text, projects):
                text = None
        if (
            text is not None
            and asked is not None
            and (invents_shared_past(text) or invents_past_talk(text, memories))
        ):
            # A past with him from before he came: asked once to say it without one.
            text = await perform(
                gateway,
                "firmament",
                {**asked, "revision_instruction": REVISION},
                simulated_at.isoformat(),
                output,
            )
            if text is not None and (
                invents_shared_past(text) or invents_past_talk(text, memories)
            ):
                text = None
        if text is None:
            text = (
                f"{name} talked a little about something from before."
                if speaker_id == partner_id
                else f"I listened to {name} for a bit."
            )
            output.append(
                DomainEvent(
                    "scene.turn_fallback_used",
                    "pathos",
                    {
                        "scene_id": scene_id,
                        "actor_id": speaker_id,
                        "reason": "Dialogue performer did not return an accepted proposal",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    correlation_id=scene_id,
                )
            )
        turn = resolve_scene_turn(
            SceneTurnProposal(
                f"{scene_id}-turn-{scene.turn_count + 1}",
                scene_id,
                speaker_id,
                text,
                "share" if speaker_id == partner_id else "respond",
                topic_id,
                ScenePrivacy.PRIVATE,
                actual_revision + len(output),
            ),
            state=project_scenes([*history, *output]),
            history=[*history, *output],
            actor_locations=actor_locations,
            actual_revision=actual_revision + len(output),
            simulated_at=simulated_at.isoformat(),
            speaker_name=name if speaker_id == partner_id else "Patrick",
        )
        output.extend(turn.events)
        if not turn.accepted:
            break
        if speaker_id == "pathos" and topic_id.startswith("remember-"):
            # He brought up something they went through together: told, so not again as new.
            spoken_line = next((e for e in turn.events if e.kind == "scene.turn_taken"), None)
            memory_id = topic_id.removeprefix("remember-")
            about = set(_WORDS_OF.findall(str(topic_words.get(topic_id, "")).casefold()))
            said = (
                set(_WORDS_OF.findall(str(spoken_line.payload.get("text", "")).casefold()))
                if spoken_line is not None
                else set()
            )
            if spoken_line is not None and len(about & said) >= 2:
                output.append(
                    DomainEvent(
                        "memory.told",
                        "pathos",
                        {
                            "memory_id": memory_id,
                            "to": partner_id,
                            "simulated_at": simulated_at.isoformat(),
                        },
                        causation_id=spoken_line.event_id,
                        correlation_id=f"told-{memory_id}",
                    )
                )
        if disclosure is not None:
            spoken = next(event for event in turn.events if event.kind == "scene.turn_taken")
            output.append(
                DomainEvent(
                    "npc.biography_disclosed",
                    "pathos",
                    {
                        "fact_id": disclosure.fact_id,
                        "person_id": partner_id,
                        "audience_id": "pathos",
                        "scene_id": scene_id,
                        "source_turn_event_id": str(spoken.event_id),
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=spoken.event_id,
                    correlation_id=scene_id,
                )
            )
    scene = project_scenes([*history, *output]).scenes[scene_id]
    if scene.status == "active" and relationship.tension >= 0.5 and scene.turn_count >= 2:
        ended = resolve_scene_end(
            SceneEndProposal(
                f"tension-exit-{scene_id}",
                scene_id,
                partner_id,
                SceneEndReason.LEFT,
                actual_revision + len(output),
            ),
            state=project_scenes([*history, *output]),
            history=[*history, *output],
            actual_revision=actual_revision + len(output),
            simulated_at=simulated_at.isoformat(),
        )
        output.extend(ended.events)
        scene = project_scenes([*history, *output]).scenes[scene_id]
    if scene.status == "ended" and scene.end_reason == SceneEndReason.TURN_BUDGET.value:
        last_turn = next(
            event
            for event in reversed(output)
            if event.kind == "scene.turn_taken" and event.payload.get("scene_id") == scene_id
        )
        output.append(
            DomainEvent(
                "relationship.changed",
                "pathos",
                {
                    "person_id": partner_id,
                    "evidence_actor_id": "pathos",
                    "familiarity_delta": 0.02,
                    "trust_delta": 0.0,
                    "reason": "An unforced ordinary conversation reached a natural close.",
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=last_turn.event_id,
                correlation_id=scene_id,
            )
        )
    return output


_WORDS_OF = re.compile(r"[a-z']{4,}")

SAID_IT_ALREADY = (
    "That repeats what this speaker already said in this conversation. Answer the other "
    "person's last line with something new, or let the conversation wind down."
)


def _topics(
    history: Sequence[DomainEvent],
    at: datetime,
    location_id: str,
    partner_id: str,
    name: str,
) -> tuple[list[str], dict[str, str]]:
    """What they talk about, in order: a repair or follow-up first if one's due, then
    what's really going on between them (``talking_points``), then what he's noticed
    here, then the weather."""
    observed = _observable_topics(history, location_id, partner_id)
    points = talking_points(history, at, partner_id, name, location_id)
    repair = [topic for topic in observed if topic.startswith("cautious-repair-")]
    follow_up = [topic for topic in observed if topic.startswith("following-up-with-")]
    noticed = [
        topic
        for topic in observed
        if topic not in repair + follow_up and not topic.startswith("ordinary-life-at-")
    ]
    news = [point_id for point_id, _ in points if point_id != "the-weather"][:3]
    weather = [point_id for point_id, _ in points if point_id == "the-weather"]
    # Big news before a vague follow-up: the morning he gives notice, that's the talk.
    ids = [*repair, *news, *follow_up, *noticed, *weather] or observed
    return ids, dict(points)


def _observable_topics(
    history: Sequence[DomainEvent], location_id: str, partner_id: str
) -> list[str]:
    topics: list[str] = []
    ready = any(
        item.status == "ready" and item.person_id == partner_id
        for item in project_followups(history).values()
    )
    repair = next(
        (
            item
            for item in reversed(list(project_relationship_repairs(history).values()))
            if item.person_id == partner_id and item.status in {"open", "improving"}
        ),
        None,
    )
    if ready:
        topics.append(
            f"cautious-repair-{repair.topic_id}-forgiveness-unknown"
            if repair is not None
            else f"following-up-with-{partner_id}"
        )
    for item in project_social_preferences(history).values():
        if item.person_id == partner_id and item.status == "held":
            topics.append(f"remembered-{item.stance}-{item.topic}")
            break
    for event in reversed(events_of(history, "perception.recorded")):
        if (
            event.payload.get("owner") != "pathos"
            or event.payload.get("location_id") != location_id
        ):
            continue
        value = next(
            (
                event.payload.get(key)
                for key in ("topic_id", "event_type", "theme", "source_event_id")
                if isinstance(event.payload.get(key), str)
            ),
            None,
        )
        if isinstance(value, str) and value not in topics:
            topics.append(value)
        if len(topics) == 2:
            break
    return topics or [f"ordinary-life-at-{location_id}"]


def _cooldown_complete(
    history: Sequence[DomainEvent],
    partner_id: str,
    simulated_at: datetime,
    relationships: Mapping[str, Relationship],
) -> bool:
    relationship = relationships.get(partner_id, Relationship(partner_id))
    cooldown = timedelta(
        days=max(1, round(5 - 3 * relationship.familiarity + 2 * relationship.tension))
    )
    previous = next(
        (
            event
            for event in reversed(events_of(history, "scene.started"))
            if str(event.payload.get("scene_id", "")).startswith("ordinary-")
            and partner_id in {event.payload.get("initiator_id"), event.payload.get("partner_id")}
        ),
        None,
    )
    if previous is None:
        return True
    value = previous.payload.get("simulated_at")
    if not isinstance(value, str):
        return False
    return simulated_at - datetime.fromisoformat(value) >= cooldown


def _topic_words(topic_id: str, name: str) -> str:
    """What the scene is about, in words that keep someone's past their own."""
    if topic_id.startswith("personal-history-"):
        about = topic_id.removeprefix("personal-history-").replace("-", " ")
        return (
            f"{name}'s own {about}, from {name}'s life before they knew Patrick; it's "
            f"{name}'s story, not something the two of them share"
        )
    return topic_id.replace("-", " ")
