"""Talking with Pathos: inbox messages, live visits and his replies."""

import asyncio
from datetime import datetime, timedelta
from typing import Callable, Mapping, Sequence

from eidos.application.activity_execution import execution_context
from eidos.application.advice import advice_asked_events, advice_context, advice_names
from eidos.application.alertness import body_now
from eidos.application.ambient_population import ambient_population
from eidos.application.cognition import perform_pathos_reply
from eidos.application.cognitive_workspace import cognitive_workspace, recent_inner_stream
from eidos.application.day_recall import recall_of_that_time
from eidos.application.epistemics import pathos_known_person_ids
from eidos.application.feelings import feelings_view
from eidos.application.freelance import work_view
from eidos.application.in_jokes import jokes_with_you
from eidos.application.inner_life import active_concerns, active_dream_inspirations
from eidos.application.life_context import (
    latest_weather,
    mood_name,
    self_concept_context,
    semantic_expectation_context,
    vars_for,
)
from eidos.application.life_lately import life_lately
from eidos.application.life_projections import LifeProjections
from eidos.application.masking import masking_context
from eidos.application.memory import RecalledMemory, recall, terms
from eidos.application.memory_life import is_routine_note, stayed_with_me
from eidos.application.mental_layers import mind_context
from eidos.application.messaging import communication_availability, reply_due_at
from eidos.application.open_loops import loops_view
from eidos.application.opinions import his_views
from eidos.application.outreach import nearly_told_you
from eidos.application.personal_journeys import journey_context
from eidos.application.reaching_out import texts_view
from eidos.application.reconsolidation import reconsolidation_events
from eidos.application.repair_jobs import bench_view
from eidos.application.self_interview import Question, interview_report, questions_for
from eidos.application.selfhood import selfhood_context
from eidos.application.social_preferences import social_preference_events
from eidos.application.time_budget import personal_time_budget
from eidos.application.time_feel import time_feel_now
from eidos.application.user_notes import asked_about_events, user_knowledge_context
from eidos.application.world_news import news_context
from eidos.domain.conversation_time import reply_pacing
from eidos.domain.emotions import emotional_planning_bias, emotional_speech_bias, project_emotion
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.identity import identity_established_event, project_identity
from eidos.domain.life_story import passages_for
from eidos.domain.planning import PlanningState
from eidos.domain.relationship_repairs import project_relationship_repairs
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
from eidos.domain.state import PathosState
from eidos.domain.traits import project_traits
from eidos.domain.world_catalog import WorldCatalog


def _is_explicit_memory_reminder(text: str) -> bool:
    lowered = text.lower()
    return any(
        cue in lowered
        for cue in (
            "remember",
            "recall",
            "remind you",
            "reminder that",
            "don't forget",
            "do not forget",
        )
    )


def _while_you_were_away(history: Sequence[DomainEvent], at: datetime) -> list[str]:
    """After a long gap, the things from his days he might tell you about, if it fits."""
    yours = [
        e for e in events_of(history, "conversation.message") if e.payload.get("speaker") == "you"
    ]
    # The message he's answering now is the newest; the gap is before it.
    earlier = yours[:-1] if yours else []
    if not earlier:
        return []
    try:
        last = datetime.fromisoformat(str(earlier[-1].payload.get("simulated_at")))
    except ValueError:
        return []
    if at - last < timedelta(hours=12):
        return []
    moments: list[tuple[float, str]] = []
    for memory in events_of(history, "memory.recorded")[-400:]:
        p = memory.payload
        try:
            when = datetime.fromisoformat(str(p.get("simulated_at")))
        except ValueError:
            continue
        text = str(p.get("text", ""))
        if (
            when <= last
            or p.get("owner", "pathos") != "pathos"
            or p.get("category") == "dream"
            or is_routine_note(text)
            or float(p.get("importance", 0.3) or 0.3) < 0.45
        ):
            continue
        moments.append((float(p.get("importance", 0.45)), text[:160]))
    return [text for _, text in sorted(moments, key=lambda m: -m[0])[:5]]


class LifeConversation(LifeProjections):
    """Visits, inbox messages and live turns; the replies are composed from his whole life."""

    # What's going through his mind right now, from the always-running stream when a
    # server runs one: {"thoughts": [...], "pulling_at_him": [...]}.
    live_mind: Callable[[], Mapping[str, object]] | None = None

    def _his_mind_just_now(self, history: Sequence[DomainEvent], at: datetime) -> dict[str, object]:
        """What he was just thinking, what's pulling at him, and his recent texts."""
        live: Mapping[str, object] = {}
        if self.live_mind is not None:
            try:
                live = self.live_mind()
            except Exception:  # a stream hiccup must never cost him his reply
                live = {}
        thoughts = live.get("thoughts")
        context: dict[str, object] = {
            "just_been_thinking": list(thoughts)[-4:]
            if isinstance(thoughts, (list, tuple)) and thoughts
            else recent_inner_stream(history, at),
        }
        pulls = live.get("pulling_at_him")
        if isinstance(pulls, (list, tuple)) and pulls:
            context["pulling_at_him"] = list(pulls)[:4]
        texts = texts_view(history, limit=3)
        if texts:
            context["texts_lately"] = texts
        # What's weighing on him or coming up, and what he keeps meaning to do: a person
        # asked how they are says so.
        weighing = [
            str(concern.payload.get("text"))
            for concern in active_concerns(history)[-4:]
            if concern.payload.get("text")
        ]
        if weighing:
            context["on_his_mind_lately"] = weighing
        # A question of his you left hanging when you went: he may pick it back up.
        said = [
            e
            for e in events_of(history, "conversation.message")[-6:]
            if e.payload.get("speaker") in {"you", "pathos"}
        ]
        # Your message just now (the one he's answering) isn't an answer to his question.
        while said and said[-1].payload.get("speaker") == "you":
            try:
                sent = datetime.fromisoformat(str(said[-1].payload.get("simulated_at")))
            except ValueError:
                break
            if at - sent > timedelta(minutes=15):
                break
            said.pop()
        if said and said[-1].payload.get("speaker") == "pathos":
            last = said[-1]
            text = str(last.payload.get("text", "")).strip()
            try:
                waited = at - datetime.fromisoformat(str(last.payload.get("simulated_at")))
            except ValueError:
                waited = timedelta(0)
            if text.endswith("?") and waited >= timedelta(hours=2):
                context["left_hanging"] = text[-200:]
        nearly = nearly_told_you(history, at)
        if nearly:
            context["nearly_told_you"] = nearly
        away = _while_you_were_away(history, at)
        if away:
            context["while_you_were_away"] = away
        feeling = [str(f["feeling"]) for f in feelings_view(history, at)[:3]]
        if feeling:
            context["feeling_now"] = feeling
        catalog = self._world_catalog(list(history))
        views = his_views(history, at, {pid: person.name for pid, person in catalog.people.items()})
        if views:
            context["how_i_feel_about_people"] = views
        stayed = stayed_with_me(history)
        if stayed:
            context["stayed_with_him"] = stayed
        lately = life_lately(history)
        if lately:
            context["my_life_lately"] = lately
        week = time_feel_now(list(history), at)
        if week:
            context["how_the_day_feels"] = week
        felt = body_now(history, at)
        if felt:
            context["body_right_now"] = felt
        meaning = [str(loop["text"]) for loop in loops_view(history, at)[:3]]
        if meaning:
            context["meaning_to"] = meaning
        bench = bench_view(history, at)
        if bench:
            context["on_the_bench"] = bench
        work = work_view(history, at)
        if work:
            context["my_work"] = work
        return context

    async def _advance(self, hours: float) -> None:
        """Advance simulated time; implemented by ``Life`` (live turns take real seconds)."""
        raise NotImplementedError

    def request_visit(self, request_id: str) -> None:
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
            raise ValueError("A request ID is required")
        history = self.history()
        if any(
            event.kind == "visit.requested" and event.payload.get("request_id") == request_id
            for event in history
        ):
            return
        state = self._project_state(history)
        at = state.simulated_at.isoformat()
        requested = DomainEvent(
            "visit.requested",
            "pathos",
            {"request_id": request_id, "simulated_at": at},
            correlation_id=request_id,
        )
        availability = communication_availability(history, state)
        if not availability.can_visit or availability.status == "in_conversation":
            declined = DomainEvent(
                "visit.declined",
                "pathos",
                {
                    "request_id": request_id,
                    "reason": availability.reason,
                    "simulated_at": at,
                },
                causation_id=requested.event_id,
                correlation_id=request_id,
            )
            self.store.append("pathos", [requested, declined], len(history))
            return
        scene_id = f"user-visit-{request_id}"
        actor_locations = {"pathos": state.location_id, "user": state.location_id}
        start = resolve_scene_start(
            SceneStartProposal(
                f"start-{scene_id}",
                scene_id,
                "pathos",
                "user",
                "open-conversation",
                40,
                len(history) + 1,
            ),
            state=project_scenes([*history, requested]),
            actor_locations=actor_locations,
            known_actor_ids=set(actor_locations),
            actual_revision=len(history) + 1,
            simulated_at=at,
        )
        output = [requested, *start.events]
        if start.accepted:
            output.append(
                DomainEvent(
                    "visit.accepted",
                    "pathos",
                    {
                        "request_id": request_id,
                        "scene_id": scene_id,
                        "location_id": state.location_id,
                        "hurried": availability.hurried,
                        "simulated_at": at,
                    },
                    causation_id=start.events[-1].event_id,
                    correlation_id=scene_id,
                )
            )
        self.store.append("pathos", output, len(history))

    def end_visit(self, request_id: str) -> None:
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
            raise ValueError("A request ID is required")
        history = self.history()
        if any(
            event.kind == "visit.ended" and event.payload.get("request_id") == request_id
            for event in history
        ):
            return
        scene = next(
            (
                item
                for item in project_scenes(history).scenes.values()
                if item.status in {"active", "paused"}
                and {item.initiator_id, item.partner_id} == {"pathos", "user"}
            ),
            None,
        )
        if scene is None:
            raise ValueError("There is no live visit to end")
        state = self._project_state(history)
        ended = resolve_scene_end(
            SceneEndProposal(
                f"end-{scene.scene_id}-{request_id}",
                scene.scene_id,
                "user",
                SceneEndReason.LEFT,
                len(history),
            ),
            state=project_scenes(history),
            history=history,
            actual_revision=len(history),
            simulated_at=state.simulated_at.isoformat(),
        )
        output = list(ended.events)
        if ended.accepted:
            output.append(
                DomainEvent(
                    "visit.ended",
                    "pathos",
                    {
                        "request_id": request_id,
                        "scene_id": scene.scene_id,
                        "reason": "user_left",
                        "simulated_at": state.simulated_at.isoformat(),
                    },
                    causation_id=ended.events[-1].event_id,
                    correlation_id=scene.scene_id,
                )
            )
        self.store.append("pathos", output, len(history))

    def chat(self, text: str, request_id: str) -> None:
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise ValueError("Messages must contain 1–2000 characters")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
            raise ValueError("A request ID is required")
        history = self.history()
        previous = next(
            (
                e
                for e in history
                if e.kind == "conversation.message"
                and e.payload.get("request_id") == request_id
                and e.payload.get("speaker") == "you"
            ),
            None,
        )
        if previous:
            if previous.payload["text"] != text.strip():
                raise ValueError("Request ID was already used for a different message")
            return
        user_scene = next(
            (
                scene
                for scene in project_scenes(history).scenes.values()
                if scene.status in {"active", "paused"}
                and {scene.initiator_id, scene.partner_id} == {"pathos", "user"}
            ),
            None,
        )
        if user_scene is not None:
            if user_scene.status == "paused":
                raise ValueError("The live conversation is temporarily interrupted")
            if user_scene.next_actor_id != "user":
                raise ValueError("Pathos is still responding")
            asyncio.run(self._live_exchange(user_scene.scene_id, text.strip(), request_id))
            return
        state = self._project_state(history)
        at = state.simulated_at.isoformat()
        due_at = reply_due_at(history, state, request_id)
        incoming = DomainEvent(
            "conversation.message",
            "pathos",
            {
                "text": text.strip(),
                "speaker": "you",
                "simulated_at": at,
                "request_id": request_id,
                "delivery_status": "delivered",
                "reply_due_at": due_at.isoformat(),
            },
            correlation_id=request_id,
        )
        self.store.append("pathos", [incoming], len(history))

    async def _live_exchange(self, scene_id: str, text: str, request_id: str) -> None:
        history = self.history()
        state = self._project_state(history)
        actor_locations = {"pathos": state.location_id, "user": state.location_id}
        user_turn = resolve_scene_turn(
            SceneTurnProposal(
                f"{scene_id}-{request_id}-user",
                scene_id,
                "user",
                text,
                "converse",
                "open-conversation",
                ScenePrivacy.PRIVATE,
                len(history),
            ),
            state=project_scenes(history),
            history=history,
            actor_locations=actor_locations,
            actual_revision=len(history),
            simulated_at=state.simulated_at.isoformat(),
        )
        if not user_turn.accepted:
            raise ValueError(user_turn.events[-1].payload.get("reason", "The turn was rejected"))
        incoming = DomainEvent(
            "conversation.message",
            "pathos",
            {
                "text": text,
                "speaker": "you",
                "simulated_at": state.simulated_at.isoformat(),
                "request_id": request_id,
                "delivery_status": "heard",
                "channel": "live_visit",
                "scene_id": scene_id,
            },
            causation_id=next(
                event.event_id for event in user_turn.events if event.kind == "scene.turn_taken"
            ),
            correlation_id=scene_id,
        )
        self.store.append("pathos", [*user_turn.events, incoming], len(history))
        await self._respond_to_message(incoming)
        history = self.history()
        reply = next(
            (
                event
                for event in reversed(history)
                if event.kind == "conversation.message"
                and event.payload.get("request_id") == request_id
                and event.payload.get("speaker") == "pathos"
            ),
            None,
        )
        if reply is None:
            return
        state = self._project_state(history)
        pathos_turn = resolve_scene_turn(
            SceneTurnProposal(
                f"{scene_id}-{request_id}-pathos",
                scene_id,
                "pathos",
                str(reply.payload["text"]),
                "respond",
                "open-conversation",
                ScenePrivacy.PRIVATE,
                len(history),
            ),
            state=project_scenes(history),
            history=history,
            actor_locations={"pathos": state.location_id, "user": state.location_id},
            actual_revision=len(history),
            simulated_at=state.simulated_at.isoformat(),
        )
        output = list(pathos_turn.events)
        elapsed_seconds = 0
        if pathos_turn.accepted:
            user_turn_event = next(
                event for event in user_turn.events if event.kind == "scene.turn_taken"
            )
            pathos_turn_event = next(
                event for event in pathos_turn.events if event.kind == "scene.turn_taken"
            )
            speech_cadence = str(reply.payload.get("speech_cadence", "steady"))
            pacing = reply_pacing(
                text,
                str(reply.payload["text"]),
                speech_cadence=speech_cadence,
            )
            elapsed_seconds = pacing.total_seconds
            output.append(
                DomainEvent(
                    "conversation.time_elapsed",
                    "pathos",
                    {
                        "scene_id": scene_id,
                        "request_id": request_id,
                        "user_turn_event_id": str(user_turn_event.event_id),
                        "pathos_turn_event_id": str(pathos_turn_event.event_id),
                        "seconds": elapsed_seconds,
                        "listening_seconds": pacing.listening_seconds,
                        "thinking_seconds": pacing.thinking_seconds,
                        "speaking_seconds": pacing.speaking_seconds,
                        "speech_cadence": speech_cadence,
                        "text": (
                            f"{elapsed_seconds} seconds passed while the conversation continued."
                        ),
                        "started_at": state.simulated_at.isoformat(),
                        "ends_at": (
                            state.simulated_at + timedelta(seconds=elapsed_seconds)
                        ).isoformat(),
                        "simulated_at": state.simulated_at.isoformat(),
                    },
                    causation_id=pathos_turn_event.event_id,
                    correlation_id=scene_id,
                )
            )
            ended = next(
                (event for event in pathos_turn.events if event.kind == "scene.ended"), None
            )
            if ended is not None:
                visit_ended = DomainEvent(
                    "visit.ended",
                    "pathos",
                    {
                        "request_id": f"natural-end-{scene_id}",
                        "scene_id": scene_id,
                        "reason": "conversation_complete",
                        "simulated_at": state.simulated_at.isoformat(),
                    },
                    causation_id=ended.event_id,
                    correlation_id=scene_id,
                )
                output.extend(
                    (
                        visit_ended,
                        DomainEvent(
                            "conversation.message",
                            "pathos",
                            {
                                "request_id": f"natural-end-{scene_id}",
                                "speaker": "system",
                                "text": "The conversation reached a natural stopping point.",
                                "channel": "live_visit",
                                "scene_id": scene_id,
                                "simulated_at": state.simulated_at.isoformat(),
                            },
                            causation_id=visit_ended.event_id,
                            correlation_id=scene_id,
                        ),
                    )
                )
        self.store.append("pathos", output, len(history))
        if elapsed_seconds:
            await self._advance(elapsed_seconds / 3600)

    async def _respond_to_due_messages(self) -> None:
        while True:
            history = self.history()
            state = self._project_state(history)
            if communication_availability(history, state).status in {
                "asleep",
                "occupied",
                "interrupted",
                "in_conversation",
            }:
                return
            replied = {
                str(event.payload["request_id"])
                for event in history
                if event.kind == "conversation.message"
                and event.payload.get("speaker") in {"pathos", "system"}
            }
            incoming = next(
                (
                    event
                    for event in history
                    if event.kind == "conversation.message"
                    and event.payload.get("speaker") == "you"
                    and str(event.payload.get("request_id")) not in replied
                    and "reply_due_at" in event.payload
                    and datetime.fromisoformat(str(event.payload["reply_due_at"]))
                    <= state.simulated_at
                ),
                None,
            )
            if incoming is None:
                return
            await self._respond_to_message(incoming)

    def _reply_context(
        self,
        history: list[DomainEvent],
        text: str,
        request_id: str,
        incoming: DomainEvent | None,
    ) -> tuple[PathosState, str, list[DomainEvent], dict[str, object], dict[str, object]]:
        """Everything his voice needs to answer ``text`` now, and the events that go with it.

        Without ``incoming`` (a question nobody actually sent, as in the self-interview),
        nothing is tied to a real message.
        """
        state = self._project_state(history)
        at = state.simulated_at.isoformat()
        pending: list[DomainEvent] = []
        identity = project_identity(history)
        traits = project_traits(history)
        if not identity.established:
            pending.append(identity_established_event(at))
            identity = project_identity(history + pending)
        pending.extend(social_preference_events(history + pending, state.simulated_at))
        planning = self._planning(history)
        catalog = self._world_catalog(history)
        selected = self._recall_for_message(history, text, state, planning, catalog)
        reminder = (
            _reminder_event(incoming, text, selected, request_id, at)
            if incoming is not None
            else None
        )
        if reminder is not None:
            pending.append(reminder)
        reply_emotion = project_emotion(history)
        reply_availability = communication_availability(history, state)
        reply_voice: dict[str, object] = {
            **vars_for(
                emotional_speech_bias(
                    reply_emotion.valence,
                    reply_emotion.arousal,
                    state.energy,
                    reply_emotion.sustained_low_hours,
                    reply_emotion.complexity,
                    hurried=reply_availability.hurried,
                )
            ),
            "register": "casual, direct, familiar, and unpolished in a natural way",
            "instruction": (
                "Answer like a person already in this conversation. Use contractions and "
                "ordinary phrasing; fragments and pauses are fine. Let the disposition "
                "quietly shape rhythm and how much is shared without naming its metrics, "
                "performing an emotion, sounding therapeutic, or becoming an assistant. "
                "Do not pad to the target length or end every reply with a question."
            ),
        }
        context: dict[str, object] = {
            "message": text.strip(),
            "time": at,
            "location": catalog.location_name(state.location_id),
            "journey": journey_context(history, state.simulated_at, catalog),
            "ambient_presence": {"activity": "Travelling; neither endpoint is currently visible."}
            if state.location_id == "in_transit"
            else vars_for(
                ambient_population(
                    catalog,
                    state.simulated_at,
                    latest_weather(history),
                )[state.location_id]
            ),
            "mood": mood_name(state.energy, state.valence, state.arousal),
            "voice": reply_voice,
            "time_budget": personal_time_budget(
                self._planning(history), catalog, state.simulated_at, state.location_id
            ),
            "ongoing_activities": execution_context(
                history, self._planning(history), state.simulated_at
            ),
            "recent_dialogue": [
                {
                    "speaker": str(event.payload["speaker"]),
                    "text": str(event.payload["text"]),
                }
                for event in history
                if event.kind == "conversation.message"
                and (incoming is None or event.event_id != incoming.event_id)
                and event.payload.get("speaker") in {"you", "pathos"}
            ][-8:],
            "identity": {
                "name": identity.name,
                "nickname": identity.nickname,
                "values": dict(identity.values),
                "preferences": list(identity.preferences),
                "traits": dict(traits.levels),
                "self_concepts": self_concept_context(history),
                "selfhood": selfhood_context(history, state.simulated_at),
            },
            "memories": [item.recalled_text for item in selected],
            "memory_recollections": [
                {
                    "text": item.recalled_text,
                    "felt_confidence": item.felt_confidence,
                    "detail_level": item.detail_level,
                    "emotional_tone": item.emotional_label,
                    "remembered_person_id": item.remembered_person_id,
                    "remembered_location_id": item.remembered_location_id,
                    "remembered_at": item.remembered_at.isoformat(),
                }
                for item in selected
            ],
            "semantic_expectations": [*semantic_expectation_context(history)],
            "beliefs": [
                {
                    "subject": belief.subject_id,
                    "predicate": belief.predicate,
                    "value": belief.object_value,
                    "confidence": belief.confidence,
                    "status": belief.status,
                    "alternative": belief.alternative_value,
                }
                for belief in self._beliefs(history).beliefs.values()
                if belief.owner_id == "pathos"
            ],
            "remembered_preferences": [
                vars_for(item)
                for item in project_social_preferences(history + pending).values()
                if item.person_id == "user"
            ],
            **user_knowledge_context(history, state.simulated_at),
            **advice_context(history, state.simulated_at, advice_names(history)),
            "running_jokes_with_you": jokes_with_you(history),
            **news_context(history, state.simulated_at),
            "relationship_repairs": [
                {
                    **vars_for(item),
                    "forgiveness_known": False,
                }
                for item in project_relationship_repairs(history + pending).values()
            ],
            "dream_inspirations": [
                {
                    "suggestion": item.suggestion,
                    "motif": item.motif,
                    "fiction_source": True,
                    "action_authority": False,
                }
                for item in active_dream_inspirations(history, state.simulated_at)
            ],
            "emotion": {
                **vars_for(reply_emotion),
                "planning_bias": vars_for(
                    emotional_planning_bias(
                        state.valence,
                        state.arousal,
                        reply_emotion.sustained_low_hours,
                        reply_emotion.complexity,
                    )
                ),
            },
            "mind_layers": mind_context(history),
            "recent_inner_stream": recent_inner_stream(history, state.simulated_at),
            "cognitive_workspace": cognitive_workspace(history, state.simulated_at),
            **self._his_mind_just_now(history, state.simulated_at),
        }
        pending.extend(_memory_access_events(selected, at))
        pending.extend(reconsolidation_events(history + pending, selected, state.simulated_at))
        from eidos.application.bonds import current_bonds

        honesty, honesty_events = masking_context(
            history,
            state.simulated_at,
            text,
            state.valence,
            current_bonds(history).get("user"),
            request_id,
        )
        context.update(honesty)
        pending.extend(honesty_events)
        # The parts of his life story that bear on what's being said (authored background,
        # never memories).
        dialogue = context.get("recent_dialogue")
        turns = (
            [t for t in dialogue if isinstance(t, Mapping)] if isinstance(dialogue, list) else []
        )
        talked = " ".join([text, *(str(turn.get("text", "")) for turn in turns[-2:])])
        story = passages_for(talked)
        if story:
            context["my_life_story"] = story
        # Asked about a particular time, he thinks back to that time.
        then = recall_of_that_time(history, text, state.simulated_at)
        if then is not None:
            context["that_time"] = then
        return state, at, pending, context, reply_voice

    def interview_prompts(self) -> list[tuple[Question, dict[str, object], str]]:
        """Questions about his week, each with the context his voice would answer from.

        Call under the world lock; the answers themselves can be fetched without it.
        """
        history = self.history()
        state = self._project_state(history)
        catalog = self._world_catalog(history)
        names = {person_id: person.name for person_id, person in catalog.people.items()}
        prompts: list[tuple[Question, dict[str, object], str]] = []
        for number, question in enumerate(questions_for(history, state.simulated_at, names)):
            _, at, _, context, _ = self._reply_context(
                history, question.text, f"self-interview-{number}", None
            )
            prompts.append((question, context, at))
        return prompts

    async def interview_answers(
        self, prompts: Sequence[tuple[Question, dict[str, object], str]]
    ) -> dict[str, object]:
        """His answers, scored against what happened; nothing is recorded in his life."""
        asked: list[tuple[Question, str]] = []
        for question, context, at in prompts:
            scratch: list[DomainEvent] = []
            answer = await perform_pathos_reply(self.gateway, context, at, scratch)
            if not answer:  # one more try, as anyone asked twice would answer
                answer = await perform_pathos_reply(self.gateway, context, at, scratch)
            asked.append((question, answer or ""))
        return interview_report(asked)

    async def _respond_to_message(self, incoming: DomainEvent) -> None:
        history = self.history()
        request_id = str(incoming.payload["request_id"])
        if any(
            event.kind == "conversation.message"
            and event.payload.get("request_id") == request_id
            and event.payload.get("speaker") in {"pathos", "system"}
            for event in history
        ):
            return
        text = str(incoming.payload["text"])
        state, at, pending, context, reply_voice = self._reply_context(
            history, text, request_id, incoming
        )
        reply = await perform_pathos_reply(self.gateway, context, at, pending)
        if reply:
            pending.extend(
                self._reply_events(incoming, text, reply, reply_voice, request_id, state)
            )
            pending.extend(asked_about_events(history, state.simulated_at, reply))
            pending.extend(
                advice_asked_events(history, state.simulated_at, reply, advice_names(history))
            )
        else:
            pending.append(
                DomainEvent(
                    "conversation.message",
                    "pathos",
                    {
                        "text": "Pathos couldn't produce a reply. Your message was saved; try sending again.",
                        "speaker": "system",
                        "simulated_at": at,
                        "request_id": request_id,
                        "source": "runtime",
                    },
                )
            )
        self.store.append("pathos", pending, len(history))
        committed = [*history, *pending]
        self._save_memory_index(committed)
        self._save_planning(committed)
        self._save_beliefs(committed)
        self._save_relationships(committed)
        self._save_consolidation_index(committed)

    def _recall_for_message(
        self,
        history: list[DomainEvent],
        text: str,
        state: PathosState,
        planning: PlanningState,
        catalog: WorldCatalog,
    ) -> list[RecalledMemory]:
        """Recall what the message is about: named people, places, objects and goals."""
        query_terms = terms(text)
        known_person_ids = pathos_known_person_ids(history)
        entity_ids = {
            person.person_id
            for person in catalog.people.values()
            if person.person_id in known_person_ids
            and (terms(person.name) & query_terms or person.person_id in query_terms)
        } | {
            place.place_id
            for place in catalog.places.values()
            if terms(place.name) & query_terms or place.place_id in query_terms
        }
        entity_ids.update(
            item.object_id
            for item in planning.objects.values()
            if terms(item.name) & query_terms or item.object_id in query_terms
        )
        relationship_ids = {
            person.person_id
            for person in catalog.people.values()
            if person.person_id in known_person_ids and person.person_id in entity_ids
        }
        goal_ids = {
            goal.goal_id
            for goal in planning.goals.values()
            if goal.status == "active" and terms(goal.title) & query_terms
        }
        return recall(
            history,
            text.strip(),
            state.simulated_at,
            7,
            entity_ids=entity_ids,
            goal_ids=goal_ids,
            relationship_ids=relationship_ids,
            diverse=True,
            index=self._memory_index(history),
        )

    def _reply_events(
        self,
        incoming: DomainEvent,
        text: str,
        reply: str,
        reply_voice: dict[str, object],
        request_id: str,
        state: PathosState,
    ) -> list[DomainEvent]:
        """His reply, paced when spoken aloud, and the memory of an inbox message."""
        at = state.simulated_at.isoformat()
        output: list[DomainEvent] = []
        pacing = (
            reply_pacing(
                text,
                reply,
                speech_cadence=str(reply_voice["cadence"]),
            )
            if incoming.payload.get("channel") == "live_visit"
            else None
        )
        output.append(
            DomainEvent(
                "conversation.message",
                "pathos",
                {
                    "text": reply,
                    "speaker": "pathos",
                    "simulated_at": at,
                    "request_id": request_id,
                    "source": self.mode,
                    "channel": incoming.payload.get("channel", "inbox"),
                    "scene_id": incoming.payload.get("scene_id"),
                    "speech_cadence": reply_voice["cadence"],
                    "pacing_listening_seconds": (
                        pacing.listening_seconds if pacing is not None else None
                    ),
                    "pacing_thinking_seconds": (
                        pacing.thinking_seconds if pacing is not None else None
                    ),
                    "pacing_speaking_seconds": (
                        pacing.speaking_seconds if pacing is not None else None
                    ),
                    "pacing_total_seconds": (pacing.total_seconds if pacing is not None else None),
                },
                causation_id=incoming.event_id,
                correlation_id=incoming.correlation_id or request_id,
            )
        )
        if incoming.payload.get("channel") != "live_visit":
            output.append(
                DomainEvent(
                    "memory.recorded",
                    "pathos",
                    {
                        "text": f"You sent a message: {text.strip()}",
                        "simulated_at": at,
                        "source": "user-conversation",
                        "source_event_id": str(incoming.event_id),
                        "category": "conversation",
                        "location_id": state.location_id,
                        "owner": "pathos",
                        "importance": 0.7,
                        "confidence": 1.0,
                    },
                    causation_id=incoming.event_id,
                    correlation_id=incoming.correlation_id or request_id,
                )
            )
        return output


def _reminder_event(
    incoming: DomainEvent,
    text: str,
    selected: list[RecalledMemory],
    request_id: str,
    at: str,
) -> DomainEvent | None:
    """When the user explicitly reminds him, note which memory the reminder brought back."""
    reminder_candidates = [
        item
        for item in selected
        if item.matched_terms
        or item.matched_entities
        or item.matched_goals
        or item.matched_relationships
    ]
    reminder = max(
        reminder_candidates,
        key=lambda item: (
            len(item.matched_terms),
            len(item.matched_entities),
            len(item.matched_goals),
            len(item.matched_relationships),
            item.score,
        ),
        default=None,
    )
    if reminder is None or not _is_explicit_memory_reminder(text):
        return None
    return DomainEvent(
        "memory.reminded",
        "pathos",
        {
            "memory_id": str(reminder.event.event_id),
            "reminded_by": "user",
            "source_message_id": str(incoming.event_id),
            "recalled_text": reminder.recalled_text,
            "felt_confidence": reminder.felt_confidence,
            "confidence_basis": reminder.confidence_basis,
            "remembered_at": reminder.remembered_at.isoformat(),
            "cue_terms": ",".join(reminder.matched_terms),
            "cue_term_count": len(reminder.matched_terms),
            "simulated_at": at,
        },
        causation_id=incoming.event_id,
        correlation_id=incoming.correlation_id or request_id,
    )


def _memory_access_events(selected: list[RecalledMemory], at: str) -> list[DomainEvent]:
    """Record each memory the conversation brought to mind, with why it surfaced."""
    return [
        DomainEvent(
            "memory.accessed",
            "pathos",
            {
                "memory_id": str(item.event.event_id),
                "simulated_at": at,
                "reason": item.reason,
                "score": item.score,
                "lexical_score": item.components["lexical"],
                "entity_score": item.components["entity"],
                "goal_score": item.components["goal"],
                "relationship_score": item.components["relationship"],
                "accessibility_score": item.components["accessibility"],
                "importance_score": item.components["importance"],
                "confidence_score": item.components["confidence"],
                "mood_congruence_score": item.components["mood_congruence"],
                "matched_entity_count": len(item.matched_entities),
                "matched_goal_count": len(item.matched_goals),
                "matched_relationship_count": len(item.matched_relationships),
                "query_source": "user-conversation",
                "detail_level": item.detail_level,
                "recalled_text": item.recalled_text,
                "felt_confidence": item.felt_confidence,
                "confidence_basis": item.confidence_basis,
            },
        )
        for item in selected
    ]
