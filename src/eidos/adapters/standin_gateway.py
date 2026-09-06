"""Deterministic development performers. These are templates, not language models."""

import hashlib
import json
from datetime import datetime

from eidos.ports.model_gateway import ModelGateway, ModelRequest, ModelResponse


class StandInGateway(ModelGateway):
    async def generate(self, request: ModelRequest) -> ModelResponse:
        context = json.loads(request.messages[-1].content)
        role = request.capability
        location = context.get("location", "home")
        memories = context.get("memories", [])
        last_memory = memories[-1] if memories else "The day is still beginning."
        key = f"{role}:{context.get('time', '')}:{context.get('message', '')}"
        choice = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
        if role == "pathos":
            message = context.get("message", "").lower()
            if context.get("outreach_reason"):
                text = f"Something from today brought you to mind: {context.get('source_memory', last_memory)}"
            elif "private thing" in message or "don't know" in message:
                text = "I don't know what Mara kept private, and I don't want to pretend that I do."
            elif any(word in message for word in ("remember", "yesterday", "today", "day")):
                text = f"I've been thinking back over the day. {last_memory} I'm at {location} now."
            elif any(word in message for word in ("feel", "mood", "how are")):
                text = f"{context.get('mood', 'Quiet')} is probably the word. Being at {location} suits me right now."
            elif any(word in message for word in ("where", "doing")):
                text = f"I'm at {location}. {last_memory} What's happening where you are?"
            else:
                text = (
                    f"It's good to hear from you. I'm at {location}; there's a little room to think here.",
                    f"You caught me thinking about something from earlier. {last_memory} How has your day been?",
                    "I'm glad you stopped by. Tell me a little more; I'd like to hear what's on your mind.",
                )[choice % 3]
        elif role == "murmur":
            text = (
                f"I find something comforting in the familiar rhythm of {location}.",
                f"I notice a fragment from earlier coming back: {last_memory}",
                "I should leave a little space in the day for something unplanned.",
                "I think some days are held together by very small things.",
            )[choice % 4]
        elif role == "firmament":
            if context.get("scene_mode") is True:
                text = (
                    "The weathering is part of why the old bench belongs here."
                    if context.get("scene_speaker") == "rowan"
                    else "I can see why replacing it outright would feel like losing something."
                )
            else:
                person = context["person"]
                lines = {
                    "Mara": "Mara asks whether the little lamp at the workshop is working yet.",
                    "Ellis": "Ellis holds up a repaired wooden joint, pleased with how neatly it fits.",
                    "Rowan": "Rowan shares a sketch of the square and points out a detail Pathos missed.",
                }
                text = lines.get(
                    person,
                    f"{person} pauses nearby and mentions a small detail from their day.",
                )
        elif role == "reflection":
            text = f"Looking back, this is the moment that stays with me: {last_memory}"
        elif role == "oneiros":
            dreams = (
                f"In a dream, {location} opens into a room full of unfinished clocks. Each one keeps a different afternoon.",
                f"In a dream, rain fills {location} from the floor upward, while paper boats carry half-remembered conversations.",
                f"In a dream, every doorway in {location} leads back to the same lamplit table, but one chair keeps moving.",
                f"In a dream, {location} becomes a quiet railway platform where the signs display feelings instead of destinations.",
                f"In a dream, a red thread runs from {location} through the streets and knots itself around an unfinished question.",
                f"In a dream, the memory '{last_memory}' is folded into a tiny map whose roads rearrange whenever I blink.",
            )
            text = dreams[choice % len(dreams)]
        elif role == "chronicler":
            text = " ".join(memories[-7:]) or "A quiet day, with no recorded encounters yet."
        elif role == "mnemosyne":
            text = context["experience"]
        elif role == "moira":
            text = ("Clear", "Cloudy", "Light rain", "Breezy")[choice % 4]
        elif role == "moira_event":
            agency_palette = (
                (
                    "wandering_mender",
                    "A bicycle mender sets up a folding repair stand beside the park gate after a touring strap snaps.",
                    "park",
                    "a broken touring strap",
                    "usefulness",
                    "offer help",
                    2,
                    0.28,
                    5,
                ),
                (
                    "misdirected_delivery",
                    "A crate of hand-painted theatre masks is delivered to the cafe while the touring company searches the neighborhood.",
                    "cafe",
                    "a rain-smeared address label",
                    "mistaken identity",
                    "trace the owner",
                    3,
                    0.34,
                    7,
                ),
                (
                    "brief_power_fault",
                    "The workshop lights begin pulsing unevenly as an old junction box warms beneath the stairwell.",
                    "workshop",
                    "a loose aging connection",
                    "fragility",
                    "investigate safely",
                    1,
                    0.43,
                    4,
                ),
                (
                    "injured_migrating_bird",
                    "A tired ringed swift settles beneath the park noticeboard after being driven inland by the wind.",
                    "park",
                    "an unexpected coastal wind",
                    "care",
                    "find local expertise",
                    4,
                    0.31,
                    6,
                ),
                (
                    "forgotten_recording",
                    "A pocket recorder found behind a cafe radiator plays fragments of an unfinished oral-history interview.",
                    "cafe",
                    "spring cleaning dislodged it",
                    "unfinished stories",
                    "identify the voices",
                    2,
                    0.37,
                    12,
                ),
                (
                    "water_main_markings",
                    "Fresh survey marks appear outside the workshop before anyone nearby has heard about planned street work.",
                    "workshop",
                    "a contractor's early survey",
                    "change",
                    "ask what is planned",
                    5,
                    0.26,
                    18,
                ),
                (
                    "seedling_gift",
                    "Someone leaves six carefully labelled tomato seedlings on the park bench with a note inviting strangers to adopt them.",
                    "park",
                    "a gardener raised too many",
                    "generosity",
                    "care for something",
                    3,
                    0.22,
                    8,
                ),
                (
                    "after_hours_rehearsal",
                    "A lone cellist asks to rehearse quietly in the closed cafe because the community hall has flooded.",
                    "cafe",
                    "a burst pipe at the hall",
                    "hospitality",
                    "listen or assist",
                    6,
                    0.35,
                    3,
                ),
            )
            item = agency_palette[choice % len(agency_palette)]
            resource_id = next(
                object_id
                for object_id, resource_location in context["known_resources"].items()
                if resource_location == item[2]
            )
            return ModelResponse(
                content=json.dumps(
                    {
                        "event_type": item[0],
                        "description": item[1],
                        "location_id": item[2],
                        "cause": item[3],
                        "theme": item[4],
                        "opportunity": item[5],
                        "participation": f"A present neighbor may {item[5]} without a guaranteed outcome.",
                        "stakes": "The event may change an ordinary plan or relationship, but need not.",
                        "resource_id": resource_id,
                        "inspiration_signal_id": next(
                            iter(context.get("external_signals", {})), "none"
                        ),
                        "starts_in_hours": item[6],
                        "intensity": item[7],
                        "duration_hours": item[8],
                    }
                ),
                resolved_model="authored-stand-in-v1",
                backend="deterministic",
                finish_reason="stop",
            )
        elif role == "moira_expansion":
            simulated_at = datetime.fromisoformat(context["time"])
            occurrence = ((simulated_at.date() - datetime(2026, 1, 14).date()).days // 7) % 3
            expansion = (
                {
                    "entity_kind": "person",
                    "entity_id": "nina-vale",
                    "name": "Nina Vale",
                    "description": "A traveling bookbinder staying nearby while cataloguing family papers.",
                    "location_id": "cafe",
                    "purpose": "Independent book conservator",
                    "color": "#a68fc2",
                    "label": "Nina",
                    "x": 50,
                    "y": 50,
                    "opens_hour": 8,
                    "closes_hour": 18,
                    "travel_minutes": 10,
                },
                {
                    "entity_kind": "place",
                    "entity_id": "old-glasshouse",
                    "name": "The old glasshouse",
                    "description": "A repaired municipal glasshouse used for seedlings, workshops, and quiet shelter.",
                    "location_id": "park",
                    "purpose": "Shared growing and gathering space",
                    "color": "#91ad91",
                    "label": "Glasshouse",
                    "x": 39,
                    "y": 84,
                    "opens_hour": 8,
                    "closes_hour": 19,
                    "travel_minutes": 8,
                },
                {
                    "entity_kind": "object",
                    "entity_id": "blue-handcart",
                    "name": "The blue handcart",
                    "description": "A sturdy shared cart with one newly replaced wheel and many old paint marks.",
                    "location_id": "workshop",
                    "purpose": "Moving awkward repairs and neighborhood supplies",
                    "color": "#6689a6",
                    "label": "Handcart",
                    "x": 50,
                    "y": 50,
                    "opens_hour": 8,
                    "closes_hour": 18,
                    "travel_minutes": 10,
                },
            )[occurrence]
            return ModelResponse(
                content=json.dumps(expansion),
                resolved_model="authored-stand-in-v1",
                backend="deterministic",
                finish_reason="stop",
            )
        elif role == "pathos_agency":
            places = context["known_places"]
            people = context["known_people"]
            activity_palette = (
                (
                    "street_texture_walk",
                    "Make a texture map of the neighborhood",
                    "Notice overlooked surfaces and patterns without needing a useful result.",
                    "attend",
                    "park",
                    "none",
                    "none",
                    24,
                    2,
                    0.42,
                ),
                (
                    "recipe_annotation",
                    "Annotate a familiar recipe by hand",
                    "Pay attention to how memory and habit shape a small domestic ritual.",
                    "learn",
                    "home",
                    "none",
                    "none",
                    24,
                    1,
                    0.38,
                ),
                (
                    "repair_sketch_study",
                    "Sketch the joints on repaired furniture",
                    "Understand why some repairs remain visible and others disappear.",
                    "learn",
                    "workshop",
                    "none",
                    "none",
                    24,
                    2,
                    0.55,
                ),
                (
                    "quiet_observation",
                    "Keep a one-hour table-side observation log",
                    "Make room for curiosity about the ordinary rhythms of the cafe.",
                    "attend",
                    "cafe",
                    "none",
                    "none",
                    24,
                    1,
                    0.34,
                ),
                (
                    "shared_question_walk",
                    "Take a question for a walk with someone",
                    "Let an unfinished thought change through conversation and movement.",
                    "attend",
                    "park",
                    "none",
                    next(iter(people), "none"),
                    24,
                    1,
                    0.48,
                ),
                (
                    "object_story_notes",
                    "Write imagined histories for three worn objects",
                    "Practice noticing material clues while keeping invention separate from fact.",
                    "work",
                    "home",
                    "none",
                    "none",
                    24,
                    2,
                    0.51,
                ),
            )
            agency_item = activity_palette[choice % len(activity_palette)]
            location = agency_item[4] if agency_item[4] in places else next(iter(places))
            return ModelResponse(
                content=json.dumps(
                    {
                        "activity_type": agency_item[0],
                        "title": agency_item[1],
                        "motivation": agency_item[2],
                        "action": agency_item[3],
                        "location_id": location,
                        "resource_id": agency_item[5],
                        "companion_id": agency_item[6],
                        "starts_in_hours": agency_item[7],
                        "duration_hours": agency_item[8],
                        "priority": agency_item[9],
                    }
                ),
                resolved_model="authored-stand-in-v1",
                backend="deterministic",
                finish_reason="stop",
            )
        elif role == "npc_agency":
            actor = context["actor"]
            need = context["selected_need"]
            places = context["known_places"]
            npc_palette = (
                (
                    "window_light_notes",
                    "Make a sequence of notes about changing window light",
                    "observe",
                    "cafe",
                ),
                (
                    "tool_sound_catalog",
                    "Record the different sounds of hand tools in use",
                    "catalog",
                    "workshop",
                ),
                (
                    "small_kindness_route",
                    "Leave three useful handwritten directions around the neighborhood",
                    "prepare",
                    "park",
                ),
                (
                    "material_weather_test",
                    "Compare how scrap materials respond to the damp air",
                    "study",
                    "workshop",
                ),
                ("unhurried_rest", "Keep an evening entirely free of obligations", "rest", "home"),
                (
                    "local_question_list",
                    "Write five questions to ask familiar neighbors",
                    "write",
                    "home",
                ),
                (
                    "seasonal_color_walk",
                    "Collect a palette of the neighborhood's seasonal colors",
                    "observe",
                    "park",
                ),
                (
                    "counter_story_notes",
                    "Write down the small stories implied by objects left on tables",
                    "write",
                    "cafe",
                ),
            )
            npc_item = npc_palette[choice % len(npc_palette)]
            preferred = "home" if need == "energy" else npc_item[3]
            location = preferred if preferred in places else actor["usual_location_id"]
            return ModelResponse(
                content=json.dumps(
                    {
                        "activity_type": npc_item[0],
                        "title": npc_item[1],
                        "motivation": f"Give {actor['name']} a concrete way to tend a low {need} need without assuming an outcome.",
                        "action": "rest" if need == "energy" else npc_item[2],
                        "location_id": location,
                        "day_offset": 1,
                        "scheduled_hour": 0 if need == "energy" else 12,
                    }
                ),
                resolved_model="authored-stand-in-v1",
                backend="deterministic",
                finish_reason="stop",
            )
        elif role == "pathos_project":
            projects = (
                (
                    "neighborhood_sound_atlas",
                    "Make a small atlas of neighborhood sounds",
                    "Follow curiosity across several places and notice how their rhythms differ.",
                    (
                        (
                            "listening_walk",
                            "Collect sound notes in Willow Square",
                            "attend",
                            "park",
                            1,
                        ),
                        (
                            "workshop_rhythm_notes",
                            "Compare the workshop's working rhythms",
                            "learn",
                            "workshop",
                            3,
                        ),
                        (
                            "sound_atlas_draft",
                            "Draft the neighborhood sound atlas",
                            "work",
                            "home",
                            5,
                        ),
                    ),
                ),
                (
                    "ordinary_object_study",
                    "Trace the lives of three ordinary objects",
                    "Practice patient observation while keeping imagination distinct from fact.",
                    (
                        (
                            "cafe_object_notes",
                            "Observe the wear on objects at the café",
                            "attend",
                            "cafe",
                            1,
                        ),
                        (
                            "repair_construction_study",
                            "Study how repaired objects were constructed",
                            "learn",
                            "workshop",
                            3,
                        ),
                        (
                            "object_history_draft",
                            "Write three evidence-based object sketches",
                            "work",
                            "home",
                            5,
                        ),
                    ),
                ),
                (
                    "seasonal_light_journal",
                    "Build a short journal of changing seasonal light",
                    "Give sustained attention to a subtle change that cannot be understood at once.",
                    (
                        (
                            "morning_light_notes",
                            "Record morning light in the square",
                            "attend",
                            "park",
                            1,
                        ),
                        (
                            "indoor_light_comparison",
                            "Compare afternoon light at the café",
                            "attend",
                            "cafe",
                            3,
                        ),
                        (
                            "light_journal_assembly",
                            "Assemble the seasonal light journal",
                            "work",
                            "home",
                            5,
                        ),
                    ),
                ),
            )
            project = projects[choice % len(projects)]
            known_places = context["known_places"]
            steps = [
                {
                    "activity_type": step[0],
                    "title": step[1],
                    "action": step[2],
                    "location_id": step[3] if step[3] in known_places else "home",
                    "resource_id": "none",
                    "day_offset": step[4],
                    # Morning keeps this integration fixture clear of the afternoon
                    # follow-ups and other emergent plans already in a mature calendar.
                    "scheduled_hour": 8,
                    "duration_hours": 2,
                }
                for step in project[3]
            ]
            return ModelResponse(
                content=json.dumps(
                    {
                        "project_type": project[0],
                        "title": project[1],
                        "motivation": project[2],
                        "priority": 0.56,
                        "steps": steps,
                    }
                ),
                resolved_model="authored-stand-in-v1",
                backend="deterministic",
                finish_reason="stop",
            )
        else:
            raise ValueError(f"Unknown stand-in capability: {role}")
        return ModelResponse(
            content=json.dumps({"text": text}),
            resolved_model="authored-stand-in-v1",
            backend="deterministic",
            finish_reason="stop",
        )
