"""Deterministic development performers. These are templates, not language models."""

import hashlib
import json
from datetime import datetime

from eidos.ports.model_gateway import ModelGateway, ModelRequest, ModelResponse


def _temporal_choice(options: tuple[str, ...], value: object, salt: str = "") -> str:
    """Choose replay-stably while making adjacent hours and days move through a palette."""
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        digest = hashlib.sha256(f"{value}:{salt}".encode()).digest()
        return options[int.from_bytes(digest[:4], "big") % len(options)]
    salt_value = int.from_bytes(hashlib.sha256(salt.encode()).digest()[:2], "big")
    # Ninety-seven gives each 96-quarter day its own non-overlapping range while
    # advancing same-time daily choices through even small palettes.
    index = moment.date().toordinal() * 97 + moment.hour * 4 + moment.minute // 15 + salt_value
    return options[index % len(options)]


def _short_fragment(value: object, maximum_words: int = 14) -> str:
    words = str(value).strip().rstrip(".!?").split()
    return " ".join(words[:maximum_words]) or "the quiet part of the day"


def _standin_murmur_text(context: dict[str, object], location: object, last_memory: object) -> str:
    raw_layers = context.get("mind_layers", [])
    layers = raw_layers if isinstance(raw_layers, list) else []
    attention = next(
        (
            layer.get("focus_text")
            for layer in layers
            if isinstance(layer, dict) and layer.get("layer") == "attention"
        ),
        "the thing just at the edge of my attention",
    )
    raw_emotion = context.get("emotion", {})
    emotion = raw_emotion if isinstance(raw_emotion, dict) else {}
    feeling = _short_fragment(emotion.get("label", "quiet"), 3).casefold()
    place = _short_fragment(location, 8)
    memory = _short_fragment(last_memory)
    focus = _short_fragment(attention, 10).casefold()
    moment = context.get("time")
    prefix = _temporal_choice(
        (
            "Right now,",
            "For some reason,",
            "Quietly,",
            "At the edge of everything else,",
            "Without really trying,",
            "More than I expected,",
            "Underneath the practical stuff,",
            "For a moment,",
            "Somewhere in the background,",
            "Even while I carry on,",
            "If I'm honest,",
        ),
        moment,
        "murmur-prefix",
    )
    core = _temporal_choice(
        (
            f"I keep coming back to this: {memory}.",
            f"my attention keeps settling on {focus}.",
            f"I feel {feeling}, but it isn't the whole shape of the moment.",
            f"I notice how {place} changes when I stop treating it as background.",
            f"I can't quite tell why {memory} still has a hold on me.",
            f"part of me is still occupied with {focus}.",
            f"I feel the familiar rhythm of {place}, though today it lands differently.",
            f"my mind keeps putting {memory} beside {focus}.",
            f"I am more aware of feeling {feeling} than I was a little while ago.",
            f"I keep noticing the gap between being in {place} and paying attention to it.",
            f"something in {memory} feels unfinished, even if it probably isn't.",
            f"I am letting {focus} sit there without forcing it into an answer.",
            f"my thoughts keep brushing past {memory} and then turning back.",
        ),
        moment,
        "murmur-core",
    )
    tail_options = (
        "I don't need to settle it yet.",
        "It may pass if I leave it alone.",
        "That feels worth noticing, at least.",
        "I might feel differently after something ordinary happens.",
        "The thought is quieter than it was, but still here.",
        "I can hold two versions of it for a while.",
        "There is probably more to it than the first answer.",
        "I don't mind not knowing what to do with it.",
        "It feels close without feeling urgent.",
        "Maybe this is just where my attention has landed.",
        "I can come back to it later if it still matters.",
        "The feeling changes slightly when I name it.",
        "For now, noticing it is enough.",
        "I wonder what detail will replace it in a few minutes.",
        "It is strange how quickly the mind makes a pattern.",
        "I don't want to turn it into a bigger thing than it is.",
        "Some thoughts are better left a little unfinished.",
    )
    tail = _temporal_choice(tail_options, moment, "murmur-tail")
    candidate = f"{prefix} {core} {tail}"
    raw_recent = context.get("recent_inner_stream", [])
    recent = raw_recent if isinstance(raw_recent, list) else []
    if candidate in recent:
        tail = _temporal_choice(tail_options, moment, "murmur-tail-alternate")
        candidate = f"{prefix} {core} {tail}"
    return candidate


def _standin_scene_text(context: dict[str, object]) -> str:
    """Give development scenes varied dialogue without inventing hidden knowledge."""
    speaker = str(context.get("scene_speaker", ""))
    audience = str(context.get("scene_audience", ""))
    person = str(context.get("person", "the other person"))
    topic = str(context.get("scene_topic", "ordinary life")).casefold()
    raw_prior = context.get("prior_turns", [])
    prior_turns = raw_prior if isinstance(raw_prior, list) else []
    turn = len(prior_turns) + 1
    is_pathos = speaker == "pathos"
    options: tuple[str, ...]

    if "forgiveness unknown" in topic or "cautious repair" in topic:
        options = (
            (
                "I don't expect that apology to settle everything. I just wanted to say it properly.",
                "We don't have to sort it all out now. I know it might take time.",
                "I meant what I said before. I'm not asking you to make me feel better about it.",
                "I still feel awkward about how that went. I can live with leaving it there for now.",
            )
            if is_pathos
            else (
                "I heard what you said. I'm not ready to pretend it's all fine, though.",
                "I appreciate you saying it. I still need a bit of time.",
                "We can talk. I just don't want to rush past what happened.",
                "I'm glad you brought it up again. That doesn't mean I've worked out how I feel yet.",
            )
        )
    elif "following up" in topic:
        options = (
            (
                "Yeah, I didn't want to leave that hanging. How did it turn out?",
                "I kept thinking about that after we spoke. Did anything change?",
                "I'm glad we ran into each other. I meant to ask what happened with that.",
                "Before we get distracted, I wanted to come back to what you mentioned last time.",
            )
            if is_pathos
            else (
                "I was wondering if we'd come back to that. A little has changed since then.",
                "I'm glad you remembered. I didn't really finish what I was saying last time.",
                "It turned out less dramatically than I expected, which was probably a good thing.",
                "I nearly brought that up myself. I've had another thought about it.",
            )
        )
    elif "bench" in topic:
        options = (
            (
                "I can see why replacing it outright would feel like losing something.",
                "The worn parts are probably the reason everyone recognizes it.",
                "Maybe fixing it doesn't have to mean making it look new.",
                "I'd keep the marks if we can. They feel like part of the square now.",
            )
            if is_pathos
            else (
                "The weathering is part of why the old bench belongs here.",
                "Everyone talks about the splinters, but nobody wants a shiny new bench here.",
                "That pale patch on the arm is where people have rested their hands for years.",
                "It needs care, not erasing. Those are different jobs.",
            )
        )
    elif is_pathos:
        options = (
            "Yeah, I know what you mean. It's funny which small things end up sticking with you.",
            "I hadn't thought about it that way, actually.",
            "Maybe. I think I'd leave it alone for a bit and see how it feels tomorrow.",
            "That sounds about right. The day has felt slightly off-center somehow.",
            "I noticed that too, but I couldn't work out why it felt different.",
            "Honestly, I could go either way on it. What would you do?",
            "I like that. It makes the whole thing feel less finished, in a good way.",
            "That's probably the sensible answer. I'm still tempted by the other one, though.",
            "Mm. Give me a second—I think there's something in that.",
            "I get it. I don't think I was paying enough attention before.",
            "That's nicer than the version I had in my head.",
            "Fair. I might change my mind later, but fair.",
        )
    else:
        person_lines: dict[str, tuple[str, ...]] = {
            "Mara": (
                "The morning crowd all chose the same corner today. No idea why.",
                "Someone moved the sugar jar again. Tiny mystery of the day.",
                "I nearly changed the window display, then decided I liked it being a bit tired.",
                "It went quiet for ten whole minutes earlier. I could hear the clock arguing with itself.",
                "A regular ordered something completely different and looked betrayed by their own choice.",
                "I've had three people ask if rain counts as a reason to stay for another cup.",
                "The noticeboard is getting crowded. Half those events can't possibly all happen on Saturday.",
                "I found a teaspoon in the plant pot. I'm choosing not to investigate.",
                "The kettle behaved perfectly until someone complimented it.",
                "There's a new dog outside that seems convinced the café belongs to him.",
                "I saved the last decent pastry, then forgot who I was saving it for.",
                "The light in here changed about an hour ago. Makes everything look calmer than it is.",
            ),
            "Ellis": (
                "That drawer only sticks when someone is watching me test it.",
                "I found the missing pencil. It was behind my ear, obviously.",
                "This joint is nearly right, which is somehow more irritating than completely wrong.",
                "Someone donated a box of screws sorted by color instead of size.",
                "The workshop smells like wet coats and sawdust today. Could be worse.",
                "I fixed the rattle and immediately started missing it.",
                "There's a point where tidying the bench becomes avoiding the actual job.",
                "I keep saving little scraps of good wood. Eventually they'll need their own room.",
                "This hinge has a very specific opinion about being repaired.",
                "The quiet jobs always take longer. They give you too much time to notice things.",
                "I lent out the good screwdriver and got back one that might be its distant cousin.",
                "That repair looked simple until I touched it. They usually do.",
            ),
            "Rowan": (
                "Two crows have been moving the same bit of paper around the square all afternoon.",
                "The old tree looks almost silver in this light.",
                "I drew that corner three times and somehow made it less accurate each time.",
                "Someone left one glove on the rail. It looks oddly deliberate.",
                "The puddles are reflecting more sky than the actual sky seems to have.",
                "I like the square when people are passing through instead of trying to enjoy it properly.",
                "That shop sign is slightly crooked. Now that I've seen it, I can't stop seeing it.",
                "A kid tried to explain pigeons to me earlier. Very confident, mostly wrong.",
                "The wind keeps turning the same page of my sketchbook back over.",
                "There was a patch of sun here five minutes ago. I think we imagined it.",
                "I came out to draw people and ended up drawing their empty chairs.",
                "Everything looks more temporary just before it rains.",
            ),
        }
        options = person_lines.get(
            person,
            (
                "It's been an oddly busy day without much actually happening.",
                "I noticed something small earlier and now I can't stop thinking about it.",
                "The place feels different today. Not worse, just different.",
                "I took the long way here and still somehow arrived early.",
                "Everyone seems to be between one thing and another today.",
                "I had a thought worth keeping and lost it before I found somewhere to write it down.",
            ),
        )
    line = _temporal_choice(
        options,
        context.get("time"),
        f"scene:{speaker}:{audience}:{person}:{topic}:{turn}",
    )
    afterthoughts = (
        (
            "I'm still working out what I think.",
            "Maybe that's enough of an answer for now.",
            "I could be wrong about the shape of it.",
            "Anyway, that's where my head is.",
            "It feels a little different saying it out loud.",
            "I don't need to force it any further right now.",
            "There's probably another way of looking at it.",
            "I'm not completely settled on it.",
            "That might land differently with me tomorrow.",
            "I keep coming back to the same small part of it.",
            "It's easier to notice now that we're talking about it.",
            "I think I mean that, even if I said it badly.",
            "I'll leave it there for now.",
        )
        if is_pathos
        else (
            "That's about as much as I know, honestly.",
            "I may feel differently once I've slept on it.",
            "Anyway, it was on my mind.",
            "I haven't quite decided what I make of it.",
            "It sounded clearer before I said it aloud.",
            "There is probably a less complicated version of that.",
            "I don't think it needs solving this minute.",
            "Maybe I only noticed because today has been quiet.",
            "I keep finding my way back to that bit.",
            "That might not be the important part, but it stayed with me.",
            "I'm curious whether it will still matter tomorrow.",
            "I suppose that's the small story of my day.",
            "For now, that's where I've landed.",
        )
    )
    afterthought = _temporal_choice(
        afterthoughts,
        context.get("time"),
        f"scene-after:{speaker}:{audience}:{person}:{topic}:{turn}",
    )
    return f"{line} {afterthought}"


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
                text = (
                    f"Hey, this made me think of you — {context.get('source_memory', last_memory)}"
                )
            elif "private thing" in message or "don't know" in message:
                text = "Honestly, I don't know. Mara kept that to herself."
            elif any(word in message for word in ("remember", "yesterday", "today", "day")):
                opening = (
                    "Pretty good, honestly.",
                    "Yeah, it's been alright.",
                    "Bit of a mixed one, but not bad.",
                )[choice % 3]
                text = f"{opening} {last_memory}"
            elif any(word in message for word in ("feel", "mood", "how are")):
                text = f"I'm feeling {str(context.get('mood', 'quiet')).lower()}, I think. Nothing dramatic."
            elif "where" in message:
                text = f"I'm at {location} right now. Just taking it easy."
            elif "doing" in message:
                text = f"Not much right this second. {last_memory}"
            else:
                text = (
                    "Hey. What's up?",
                    "Oh hey — yeah, I've got a minute.",
                    "Yeah, go on.",
                    "Hey — give me a second. Okay, what's up?",
                    "Oh, hey. Yeah, I'm listening.",
                    "Hi. Sorry, I was miles away for a second.",
                    "Hey. I'm here—go ahead.",
                    "Mm? Oh, hey. What's going on?",
                )[choice % 8]
        elif role == "murmur":
            text = _standin_murmur_text(context, location, last_memory)
        elif role == "firmament":
            if context.get("scene_mode") is True:
                text = _standin_scene_text(context)
            else:
                person = context["person"]
                lines: dict[str, tuple[str, ...]] = {
                    "Mara": (
                        "Mara asks whether the little lamp at the workshop is working yet.",
                        "Mara arrives with rain on one shoulder and sets a chipped blue mug by the kettle.",
                        "Mara pauses over the repair shelf and asks which job has been the most stubborn.",
                        "Mara brings over a paper bag of screws that someone left outside the workshop door.",
                        "Mara notices the lamp cord has twisted again and kneels to straighten it.",
                        "Mara stays for tea and tells Pathos the café has changed its window display.",
                        "Mara turns the café sign around twice before noticing it already says open.",
                        "Mara slides a plate aside to make room for a stack of new community flyers.",
                        "Mara watches a customer leave with the wrong umbrella and decides they may sort it out themselves.",
                        "Mara finds a handwritten recipe tucked inside the till and tries to remember who left it.",
                        "Mara lowers the music when the rain against the window becomes louder than the song.",
                        "Mara counts the clean cups, loses track, and starts again with an exaggerated sigh.",
                    ),
                    "Ellis": (
                        "Ellis holds up a repaired wooden joint, pleased with how neatly it fits.",
                        "Ellis finds a pencil behind the tool chest and claims it has been missing for months.",
                        "Ellis asks Pathos to listen to the faint click in a newly repaired drawer.",
                        "Ellis sweeps a curl of wood from the bench and makes room for the next job.",
                        "Ellis tests a repaired hinge, frowns once, and reaches for the screwdriver again.",
                        "Ellis leaves half a biscuit beside Pathos's tea and denies wanting the rest.",
                        "Ellis discovers that someone has labeled the smallest drawer simply 'probably useful'.",
                        "Ellis holds a bent brass catch to the light and says it might still have another repair in it.",
                        "Ellis opens the back door to clear the smell of varnish and lets in a scatter of rain.",
                        "Ellis measures the same shelf three times and gets a different answer each time.",
                        "Ellis sets aside a cracked handle because the obvious fix does not feel like the right one.",
                        "Ellis finds yesterday's tea untouched behind a clamp and quietly pours it away.",
                    ),
                    "Rowan": (
                        "Rowan shares a sketch of the square and points out a detail Pathos missed.",
                        "Rowan stops beneath the willows to watch two crows argue over a paper wrapper.",
                        "Rowan asks whether the old bench looks more silver or green in today's light.",
                        "Rowan shows Pathos a smudged drawing made while waiting for the rain to ease.",
                        "Rowan spots a lost glove on the park rail and moves it somewhere easier to see.",
                        "Rowan walks one slow circuit of the square with Pathos before turning home.",
                        "Rowan sketches the shadow of the park rail instead of the rail itself.",
                        "Rowan notices that someone has tied a faded ribbon around the youngest willow.",
                        "Rowan moves along the bench to let a strip of winter sun reach the empty seat.",
                        "Rowan points out a rooftop aerial that looks briefly like a person waving.",
                        "Rowan closes the sketchbook when the wind begins choosing the pages.",
                        "Rowan watches a bus pass the square and wonders aloud where everyone on it is going.",
                    ),
                }
                options = lines.get(
                    person,
                    (
                        f"{person} pauses nearby and mentions a small detail from their day.",
                        f"{person} stops long enough to share an ordinary piece of neighborhood news.",
                        f"{person} notices something out of place, then decides it can wait.",
                    ),
                )
                ambient = _temporal_choice(
                    (
                        "A door closes somewhere nearby",
                        "A bus passes at the end of the street",
                        "The light shifts as a cloud moves over",
                        "A brief draft lifts the edge of a paper",
                        "Someone laughs in another part of the room",
                        "Footsteps approach and then turn away",
                        "Rain starts lightly against the nearest window",
                        "A chair scrapes across the floor",
                        "A bicycle bell sounds outside",
                        "The room goes unexpectedly quiet",
                        "A kettle begins to murmur in the background",
                        "Someone drops a coin and follows its roll",
                        "A coat slips from a hook nearby",
                        "The smell of toast drifts through for a moment",
                        "A loose sign taps once in the wind",
                        "A delivery van pauses outside and moves on",
                        "The clock becomes noticeable between sentences",
                    ),
                    context.get("time"),
                    f"{person}:encounter-ambient",
                )
                ending = _temporal_choice(
                    (
                        "and they both lose the thread for a second",
                        "but neither of them seems in a hurry to fill the pause",
                        "and the conversation turns briefly toward it",
                        "before the ordinary noise of the place returns",
                        "and Pathos notices the interruption more than he expected",
                        "but the small exchange carries on around it",
                        "and the moment feels less arranged than it did before",
                        "before they return to what they were saying",
                        "and it gives them an easy reason to pause",
                        "while the rest of the place carries on without them",
                        "and for a moment they simply listen",
                        "before one of them remembers the original point",
                        "and the brief distraction makes them both smile",
                    ),
                    context.get("time"),
                    f"{person}:encounter-ending",
                )
                text = (
                    f"{_temporal_choice(options, context.get('time'), str(person))} "
                    f"{ambient}, {ending}."
                )
        elif role == "reflection":
            text = _temporal_choice(
                (
                    f"This is the bit that stayed with me: {last_memory}",
                    f"I keep coming back to one ordinary moment: {last_memory}",
                    f"The day feels clearer when I start here: {last_memory}",
                    f"I didn't expect this to matter as much as it did: {last_memory}",
                    f"If I carry one thing out of today, it's this: {last_memory}",
                ),
                context.get("time"),
                "reflection",
            )
        elif role == "oneiros":
            dreams = (
                f"In a dream, {location} opens into a room full of unfinished clocks. Each one keeps a different afternoon.",
                f"In a dream, rain fills {location} from the floor upward, while paper boats carry half-remembered conversations.",
                f"In a dream, every doorway in {location} leads back to the same lamplit table, but one chair keeps moving.",
                f"In a dream, {location} becomes a quiet railway platform where the signs display feelings instead of destinations.",
                f"In a dream, a red thread runs from {location} through the streets and knots itself around an unfinished question.",
                f"In a dream, the memory '{last_memory}' is folded into a tiny map whose roads rearrange whenever I blink.",
                f"In a dream, the ceiling above {location} lowers gently until everyone has to speak in whispers.",
                f"In a dream, I carry a bowl of light through {location}, careful not to spill its moving shadows.",
                f"In a dream, {location} is deserted except for a kettle that whistles whenever I forget somebody's name.",
                f"In a dream, all the windows in {location} look onto different seasons, and none of them show today.",
                f"In a dream, I find '{last_memory}' written on the back of every door I close.",
                f"In a dream, {location} drifts a few inches above the street while everyone behaves as if nothing changed.",
            )
            text = _temporal_choice(dreams, context.get("time"), "oneiros")
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
            planning_question = next(
                (
                    item
                    for item in context.get("cognitive_workspace", [])
                    if isinstance(item, dict)
                    and item.get("epistemic_status") == "planning_question"
                    and item.get("action_authority") is False
                ),
                None,
            )
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
            agency_item = (
                (
                    "plan_reconsideration",
                    "Make some quiet room to reconsider a plan",
                    str(planning_question.get("content", "Decide what still fits.")),
                    "work",
                    "home",
                    "none",
                    "none",
                    24,
                    1,
                    0.62,
                )
                if planning_question is not None
                else activity_palette[choice % len(activity_palette)]
            )
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
        elif role == "npc_backstory":
            histories = (
                (
                    "early influence",
                    "I learned to notice small changes in a room while helping an elderly neighbor sort old postcards.",
                    "private ritual",
                    "I've kept a folded list of unfamiliar words since my first job, even though I rarely show it to anyone.",
                    "turning point",
                    "I once left a course I had worked hard to enter because the life around it felt borrowed rather than mine.",
                ),
                (
                    "childhood habit",
                    "I used to map every shortcut near my childhood home and give each one a private name.",
                    "unfinished ambition",
                    "I've quietly wanted to make one useful thing that lasts longer than the story of who made it.",
                    "difficult choice",
                    "I turned down a secure opportunity years ago because I was afraid it would make every week feel identical.",
                ),
                (
                    "formative summer",
                    "I spent one summer waking before dawn to help at a market, and I still associate morning air with possibility.",
                    "kept memento",
                    "I've carried the same blank railway ticket between notebooks for years without deciding why it matters.",
                    "old regret",
                    "I once let a close friendship fade by waiting too long to say that I wanted it to continue.",
                ),
            )
            backstory_item = histories[choice % len(histories)]
            return ModelResponse(
                content=json.dumps(
                    {
                        "fact_1_topic": backstory_item[0],
                        "fact_1_text": backstory_item[1],
                        "fact_2_topic": backstory_item[2],
                        "fact_2_text": backstory_item[3],
                        "fact_3_topic": backstory_item[4],
                        "fact_3_text": backstory_item[5],
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
