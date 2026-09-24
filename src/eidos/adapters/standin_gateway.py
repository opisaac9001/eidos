"""Deterministic development performers. These are templates, not language models."""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

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


def _standin_dream_text(context: dict[str, object], location: object, last_memory: object) -> str:
    """Compose many replay-stable combinations while avoiding recent exact dreams."""
    openings = (
        f"In a dream, {location} opens into a room full of unfinished clocks.",
        f"In a dream, rain fills {location} from the floor upward.",
        f"In a dream, every doorway in {location} leads back to the same lamplit table.",
        f"In a dream, {location} becomes a quiet railway platform with no tracks.",
        f"In a dream, a red thread runs from {location} through the streets.",
        f"In a dream, the memory '{last_memory}' is folded into a tiny map.",
        f"In a dream, the ceiling above {location} lowers until everyone whispers.",
        f"In a dream, I carry a bowl of light through {location}.",
        f"In a dream, {location} is deserted except for a whistling kettle.",
        f"In a dream, every window in {location} looks onto a different season.",
        f"In a dream, I find '{last_memory}' written on a door I cannot close.",
        f"In a dream, {location} drifts a few inches above the street.",
    )
    endings = (
        "Each clock keeps a different afternoon, and I am late for none of them.",
        "Paper boats pass my knees carrying conversations I nearly recognize.",
        "One empty chair moves whenever I look toward the window.",
        "The signs show feelings instead of destinations.",
        "The thread knots itself around a question I have forgotten how to ask.",
        "Its roads rearrange quietly whenever I blink.",
        "Nobody is frightened; we simply make our words smaller.",
        "Moving shadows spill over the rim, but the light never runs out.",
        "It whistles whenever I forget a name and stops when I invent one.",
        "None of the windows show today, though one smells like breakfast.",
        "The writing fades as soon as I decide it must be important.",
        "Everyone carries on normally while my footsteps miss the ground.",
    )
    moment_value = context.get("time")
    try:
        moment = datetime.fromisoformat(str(moment_value).replace("Z", "+00:00"))
        salt = int.from_bytes(hashlib.sha256(b"oneiros-combination").digest()[:2], "big")
        combination = (
            moment.date().toordinal() * 97 + moment.hour * 4 + moment.minute // 15 + salt
        ) % (len(openings) * len(endings))
    except ValueError:
        combination = int.from_bytes(
            hashlib.sha256(f"{moment_value}:oneiros-combination".encode()).digest()[:4],
            "big",
        ) % (len(openings) * len(endings))
    opening_index = combination % len(openings)
    ending_index = combination // len(openings)
    chosen_opening = openings[opening_index]
    chosen_ending = endings[ending_index]
    raw_recent = context.get("recent_dreams", [])
    recent_raw = raw_recent if isinstance(raw_recent, (list, tuple)) else ()
    recent = {
        " ".join(str(item.get("text", "")).casefold().split())
        for item in recent_raw
        if isinstance(item, dict)
    }
    for offset in range(len(openings) * len(endings)):
        opening = openings[(opening_index + offset // len(endings)) % len(openings)]
        ending = endings[(ending_index + offset) % len(endings)]
        candidate = f"{opening} {ending}"
        if " ".join(candidate.casefold().split()) not in recent:
            return candidate
    return f"{chosen_opening} {chosen_ending}"


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
    salt = f"scene-after:{speaker}:{audience}:{person}:{topic}:{turn}"
    # People don't tack a reflective coda onto every line; most lines just end.
    if hashlib.sha256(f"{context.get('time')}:{salt}".encode()).digest()[0] % 3:
        return line
    afterthought = _temporal_choice(afterthoughts, context.get("time"), salt)
    return f"{line} {afterthought}"


def _standin_pathos_text(
    context: dict[str, object], choice: int, location: object, last_memory: object
) -> str:
    """Exercise the same emotion-shaped voice contract expected from real models."""
    message = str(context.get("message", "")).lower()
    raw_voice = context.get("voice", {})
    voice = raw_voice if isinstance(raw_voice, dict) else {}
    cadence = str(voice.get("cadence", "steady"))
    if context.get("outreach_reason"):
        news = str(context.get("source_memory", last_memory))
        if context.get("share_kind") == "news":
            return (
                f"Small bit of news: {news}",
                f"Thought you'd like to know. {news}",
                f"{news} Just wanted to tell someone.",
            )[choice % 3]
        return f"Hey, this made me think of you — {news}"
    if "private thing" in message or "don't know" in message:
        return "Honestly, I don't know. Mara kept that to herself."
    honest = _standin_nature_reply(message)
    if honest:
        return honest
    self_reply = _standin_self_reply(message, context, cadence)
    if self_reply:
        return self_reply
    people = _standin_people_reply(message, context)
    if people:
        return people
    tastes = _standin_tastes_reply(message, context)
    if tastes:
        return tastes
    work = _standin_work_reply(message, context, cadence)
    if work:
        return work
    things = _standin_things_reply(message, context)
    if things:
        return things
    if any(word in message for word in ("remember", "yesterday", "today", "day")):
        openings = {
            "clipped": ("It's been a day.", "Bit full-on, honestly."),
            "slow": ("A quiet one, mostly.", "I've been taking it slowly."),
            "hesitant": ("Kind of mixed, I think.", "I'm still working that out."),
            "easy": ("Pretty good, honestly.", "Yeah, it's been nice."),
            "steady": ("Yeah, it's been alright.", "Bit of a mixed one, but not bad."),
        }.get(cadence, ("Yeah, it's been alright.",))
        return f"{openings[choice % len(openings)]} {last_memory}"
    if any(word in message for word in ("feel", "mood", "how are")):
        identity = context.get("identity")
        selfhood = identity.get("selfhood") if isinstance(identity, dict) else None
        unwell = selfhood.get("feeling_unwell") if isinstance(selfhood, dict) else None
        if isinstance(unwell, str) and unwell:
            return f"Honestly, not great. {unwell} I'm keeping my head down till it passes."
        mood = str(context.get("mood", "quiet")).lower()
        endings = {
            "clipped": "A bit wound up. I'm okay, though.",
            "slow": "Low-energy, honestly. Just taking things gently.",
            "hesitant": f"I'm feeling {mood}, I think. It's a bit mixed.",
            "easy": f"I'm feeling {mood}. Pretty good, actually.",
            "steady": f"I'm feeling {mood}, I think. Nothing dramatic.",
        }
        return endings.get(cadence, endings["steady"])
    if "where" in message:
        return f"I'm at {location} right now." + (
            " Can't stay long." if cadence == "clipped" else " Just taking it easy."
        )
    if "doing" in message:
        prefix = "Not loads." if cadence in {"clipped", "slow"} else "Not much right now."
        return f"{prefix} {last_memory}"
    options = {
        "clipped": (
            "Hey. What's going on?",
            "Yeah—go on.",
            "Hey. I've got a minute.",
        ),
        "slow": (
            "Hey. Yeah, I'm here. Just a little quiet today.",
            "Oh, hey. Give me a second—okay.",
            "Yeah, I'm listening. Might be a bit slow today.",
        ),
        "hesitant": (
            "Oh, hey. Yeah—give me a second. What's up?",
            "Hey. I'm here. Bit distracted, if I'm honest.",
            "Mm? Sorry, I was somewhere else for a second.",
        ),
        "easy": (
            "Hey—yeah, I've got time. What's going on with you?",
            "Oh hey. Yeah, come sit down. What's up?",
            "Hey. Good timing, actually. Go on.",
        ),
        "steady": (
            "Hey. What's up?",
            "Oh hey—yeah, I've got a minute.",
            "Yeah, go on.",
            "Oh, hey. Yeah, I'm listening.",
        ),
    }.get(cadence, ("Hey. What's up?",))
    return options[choice % len(options)]


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
            text = _standin_pathos_text(context, choice, location, last_memory)
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
        elif role == "reflection" and isinstance(context.get("self_inquiry"), dict):
            text = _standin_inquiry_reflection(context["self_inquiry"], context.get("time"))
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
            text = _standin_dream_text(context, location, last_memory)
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
                    0.2,
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
                    -0.1,
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
                    -0.7,
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
                    -0.45,
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
                    0.05,
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
                    -0.3,
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
                    0.55,
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
                    -0.35,
                ),
            )
            available = tuple(
                item for item in agency_palette if item[2] in context["known_resources"].values()
            )
            if not available:
                return ModelResponse(
                    '{"no_change": true}', "authored-stand-in-v1", "stand-in", "stop"
                )
            item = available[choice % len(available)]
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
                        "affective_tone": item[9],
                        "resource_id": resource_id,
                        "inspiration_signal_id": next(
                            iter(context.get("external_signals", {})), "none"
                        ),
                        "starts_in_hours": 0,
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
        elif role == "firmament_townsfolk":
            return ModelResponse(
                content=json.dumps(_standin_townsfolk(context)),
                resolved_model="authored-stand-in-v1",
                backend="deterministic",
                finish_reason="stop",
            )
        elif role == "pathos_selfhood":
            return ModelResponse(
                content=json.dumps(_standin_selfhood(context, choice)),
                resolved_model="authored-stand-in-v1",
                backend="deterministic",
                finish_reason="stop",
            )
        elif role == "pathos_deliberation":
            field = context.get("choice_field", {})
            impulses = field.get("attended_impulses", []) if isinstance(field, dict) else []
            chosen = next(
                (
                    item
                    for item in impulses
                    if isinstance(item, dict)
                    and item.get("epistemic_status") == "planning_question"
                ),
                next(
                    (
                        item
                        for item in impulses
                        if isinstance(item, dict)
                        and item.get("workspace_kind") == "dream_inspiration"
                    ),
                    next(
                        (
                            item
                            for item in impulses
                            if isinstance(item, dict)
                            and (
                                item.get("kind") in {"thought", "aspiration"}
                                # Now and then, something on in town wins out.
                                or (
                                    str(item.get("target_id", "")).startswith("happening-")
                                    and choice % 3 == 0
                                )
                            )
                        ),
                        next(
                            (
                                item
                                for item in impulses
                                if isinstance(item, dict)
                                and item.get("kind")
                                not in {"inaction", "continuation", "prospective"}
                            ),
                            None,
                        ),
                    ),
                ),
            )
            if chosen is None:
                content = {"no_change": True, "mode": "do_nothing"}
            else:
                content = {
                    "mode": "pursue",
                    "chosen_impulse_id": chosen["impulse_id"],
                    "intention": str(chosen.get("description", "Follow what caught my attention"))[
                        :160
                    ],
                }
            return ModelResponse(
                content=json.dumps(content),
                resolved_model="authored-stand-in-v1",
                backend="deterministic",
                finish_reason="stop",
            )
        elif role == "pathos_agency":
            places = context["known_places"]
            people = context["known_people"]
            source_context = context.get("chosen_source_context")
            planning_question = (
                source_context
                if isinstance(source_context, dict)
                and source_context.get("epistemic_status") == "planning_question"
                and source_context.get("action_authority") is False
                else None
            )
            dream_possibility = (
                source_context
                if isinstance(source_context, dict)
                and source_context.get("kind") == "dream_inspiration"
                and source_context.get("epistemic_status") == "fiction_sourced_possibility"
                and source_context.get("action_authority") is False
                else None
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
                    "question_walk",
                    "Take a question for a long walk",
                    "Let an unfinished thought change through movement and fresh air.",
                    "attend",
                    "park",
                    "none",
                    # Company needs an invitation first; offline plans stay solo.
                    "none",
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
            happening = (
                source_context
                if isinstance(source_context, dict)
                and source_context.get("kind") == "public_happening"
                else None
            )
            if happening is not None:
                return _standin_happening_response(context, happening)
            if planning_question is not None:
                agency_item = (
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
            elif (
                isinstance(source_context, dict)
                and source_context.get("kind") == "possible_self"
                and source_context.get("action_authority") is False
            ):
                # Lean toward the kind of person he hopes (or fears) to be becoming.
                agency_item = activity_palette[
                    {
                        "craft": 5,
                        "curiosity": 0,
                        "care": 4 if people else 3,
                        "autonomy": 3,
                        "reliability": 1,
                    }.get(str(source_context.get("value_id")), choice % len(activity_palette))
                ]
            elif dream_possibility is not None:
                dream_text = str(dream_possibility.get("content", "")).casefold()
                dream_choice = (
                    2
                    if "repair" in dream_text or "mending" in dream_text
                    else 0
                    if "outdoor" in dream_text or "growth" in dream_text
                    else 4
                    if ("social" in dream_text or "companionship" in dream_text) and people
                    else 3
                    if "unscheduled" in dream_text
                    else 5
                )
                agency_item = activity_palette[dream_choice]
            elif (unexplored := _standin_unexplored_place(places, choice)) is not None:
                agency_item = unexplored
            elif (loved := _standin_loved_place(places, choice)) is not None:
                agency_item = loved
            elif (owned := _standin_owned_activity(context, choice)) is not None:
                agency_item = owned
            else:
                agency_item = activity_palette[choice % len(activity_palette)]
            # Whim, habit and hope rotate through ideas, but not back to something he has
            # decided isn't for him.
            tastes = context.get("activity_tastes", {})
            disliked = {
                kind
                for kind, feeling in (tastes.items() if isinstance(tastes, dict) else ())
                if feeling == "not for him"
            }
            if agency_item[0] in disliked and agency_item in activity_palette:
                start = activity_palette.index(agency_item)
                agency_item = next(
                    (
                        activity_palette[(start + step) % len(activity_palette)]
                        for step in range(1, len(activity_palette))
                        if activity_palette[(start + step) % len(activity_palette)][0]
                        not in disliked
                    ),
                    agency_item,
                )
            location = agency_item[4] if agency_item[4] in places else next(iter(places))
            gone_off = (
                isinstance(places.get(location), dict)
                and places[location].get("how_he_found_it") == "not really for him"
            )
            already_planned = {
                str(entry.get("title"))
                for entry in context.get("calendar", [])
                if isinstance(entry, dict)
            }
            slot = (
                None
                if agency_item[1] in already_planned or gone_off
                else _standin_free_slot(context, location, int(agency_item[8]))
            )
            if slot is None:
                # Already on the calendar, somewhere he has gone off, or no sensible gap in
                # the next two days: leave the idea for another time.
                return ModelResponse(
                    content=json.dumps({"no_change": True, "mode": "defer"}),
                    resolved_model="authored-stand-in-v1",
                    backend="deterministic",
                    finish_reason="stop",
                )
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
                        "starts_in_hours": slot,
                        "duration_hours": agency_item[8],
                        "priority": agency_item[9],
                        "estimate_confidence": 0.65,
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
                (
                    "seasonal_growth_notebook",
                    "Keep a small notebook of seasonal growth",
                    "Notice how ordinary outdoor growth changes across several days.",
                    (
                        (
                            "growth_walk_notes",
                            "Record signs of growth in Willow Square",
                            "attend",
                            "park",
                            1,
                        ),
                        (
                            "growth_pattern_study",
                            "Compare the shapes and patterns in the notes",
                            "learn",
                            "cafe",
                            3,
                        ),
                        (
                            "growth_notebook_draft",
                            "Assemble the seasonal growth notebook",
                            "work",
                            "home",
                            5,
                        ),
                    ),
                ),
                (
                    "shared_question_booklet",
                    "Make a booklet of questions worth sharing",
                    "Give companionship room to grow through ordinary future conversations.",
                    (
                        (
                            "conversation_question_notes",
                            "Collect questions prompted by life in the square",
                            "attend",
                            "park",
                            1,
                        ),
                        (
                            "shared_question_review",
                            "Review which questions invite a conversation",
                            "learn",
                            "cafe",
                            3,
                        ),
                        (
                            "question_booklet_draft",
                            "Draft the questions into a small booklet",
                            "work",
                            "home",
                            5,
                        ),
                    ),
                ),
            )
            dream_possibility = next(
                (
                    item
                    for item in context.get("cognitive_workspace", [])
                    if isinstance(item, dict)
                    and item.get("kind") == "dream_inspiration"
                    and item.get("epistemic_status") == "fiction_sourced_possibility"
                    and item.get("action_authority") is False
                ),
                None,
            )
            dream_motif = (
                str(dream_possibility.get("motif", "")) if dream_possibility is not None else ""
            )
            project = projects[
                {
                    "light": 2,
                    "mending": 1,
                    "growth": 3,
                    "companionship": 4,
                    "unfinished_time": 0,
                }.get(dream_motif, choice % 3)
            ]
            known_places = context["known_places"]
            steps = []
            for step in project[3]:
                location_id = step[3] if step[3] in known_places else "home"
                steps.append(
                    {
                        "activity_type": step[0],
                        "title": step[1],
                        "action": step[2],
                        "location_id": location_id,
                        "resource_id": "none",
                        "day_offset": step[4],
                        # Morning keeps clear of afternoon follow-ups in a mature calendar;
                        # on a working morning the step moves to the day's first free gap.
                        "scheduled_hour": _standin_step_hour(context, location_id, step[4], 2),
                        "duration_hours": 2,
                    }
                )
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


_STANDIN_INSIGHTS: dict[tuple[str, str], tuple[str, str, int, str, str]] = {
    # (theme, kind): (insight, value_id, direction, possible-self kind, possible self)
    ("reliability", "tension"): (
        "I think I say yes to more than my days can hold, then quietly drop the smallest "
        "thing. Keeping my word matters to me more than I'd been admitting.",
        "reliability",
        1,
        "hoped",
        "I want my small promises to be as solid as my big ones.",
    ),
    ("reliability", "thriving"): (
        "Keeping to what I said I'd do has started to feel less like duty and more like how "
        "I steady myself.",
        "reliability",
        1,
        "hoped",
        "I want people to be able to count on the small things I say.",
    ),
    ("reliability", "dormant"): (
        "I've stopped planning much at all, maybe so nothing can slip. That isn't the same "
        "as being someone people can rely on.",
        "reliability",
        0,
        "feared",
        "I don't want to become someone who never commits so he can never fail.",
    ),
    ("care", "tension"): (
        "I keep meaning to be there for people and letting the moment pass. I'd rather be a "
        "bit less comfortable and a bit more present.",
        "care",
        1,
        "hoped",
        "I want to be the friend who actually picks up.",
    ),
    ("care", "thriving"): (
        "Time with other people used to be something I fitted in around things. Lately it "
        "feels closer to the point.",
        "care",
        1,
        "hoped",
        "I'd like to be someone people are glad to see come in.",
    ),
    ("care", "strain"): (
        "I think Ellis and I clash when I'm half somewhere else. When I'm actually there, "
        "properly, we're fine.",
        "care",
        1,
        "hoped",
        "I want to be fully there when I'm with people, not already leaving.",
    ),
    ("care", "dormant"): (
        "I've let the people around here drift to the edge of my weeks. I don't want that to "
        "become normal.",
        "care",
        1,
        "feared",
        "I don't want to become someone nobody quite expects to see.",
    ),
    ("craft", "tension"): (
        "Leaving things half-made bothers me more than I let on. Finishing is part of the "
        "work, not the dull end of it.",
        "craft",
        1,
        "feared",
        "I don't want to become someone surrounded by nearly finished things.",
    ),
    ("craft", "thriving"): (
        "Steady work on something with my hands settles me in a way little else does. I "
        "think it's become part of how I know I'm alright.",
        "craft",
        1,
        "hoped",
        "I want my hands to keep knowing what they're doing.",
    ),
    ("craft", "dormant"): (
        "I haven't made anything in a while, and I miss it more than I expected to.",
        "craft",
        1,
        "hoped",
        "I'd like to always have one small thing on the go that I'm making properly.",
    ),
    ("curiosity", "tension"): (
        "I've been letting interesting things go past because stopping felt like effort. "
        "That's a trade I don't think I actually want.",
        "curiosity",
        1,
        "hoped",
        "I'd like to stay someone who still gets surprised by his own street.",
    ),
    ("curiosity", "thriving"): (
        "I'm happiest when a day has at least one small thing in it I didn't expect to learn.",
        "curiosity",
        1,
        "hoped",
        "I want to keep following small interests wherever they lead.",
    ),
    ("curiosity", "dormant"): (
        "My days got narrow without my noticing. I don't need anything grand, just the habit "
        "of following a small interest when it shows up.",
        "curiosity",
        1,
        "hoped",
        "I'd like to stay someone who still gets surprised by his own street.",
    ),
    ("autonomy", "tension"): (
        "I've been arranging my days around what I think I ought to do, and I can feel it.",
        "autonomy",
        1,
        "hoped",
        "I want to keep some of my days properly my own.",
    ),
    ("autonomy", "thriving"): (
        "Some of my best hours lately were the ones I chose for no reason at all. I think I "
        "need more of those than I let myself have.",
        "autonomy",
        1,
        "hoped",
        "I want to keep some of my days properly my own.",
    ),
    ("autonomy", "dormant"): (
        "I can't remember the last thing I did purely because I wanted to. That seems worth "
        "noticing.",
        "autonomy",
        1,
        "none",
        "",
    ),
    ("mood", "tension"): (
        "I don't think the heaviness is about one thing. It gathers when I stop doing small "
        "ordinary things for myself, and eases a little when I start again.",
        "none",
        0,
        "none",
        "",
    ),
}
# Coming back to a theme later: a refinement or complication, not the same realisation.
_STANDIN_FURTHER_INSIGHTS: dict[str, tuple[tuple[str, str, int, str, str], ...]] = {
    "autonomy": (
        (
            "I used to feel I had to justify a free afternoon. Lately I just take it, and I "
            "think I'm better company for it.",
            "autonomy",
            1,
            "hoped",
            "I want my free time to feel like mine without having to earn it.",
        ),
    ),
    "reliability": (
        (
            "It isn't the big commitments I drop. It's the ones I agreed to while tired. I "
            "should say no more often, and mean yes when I say it.",
            "reliability",
            1,
            "hoped",
            "I want my word to be something people don't have to double-check.",
        ),
    ),
    "care": (
        (
            "I think I show up best when I'm not trying to be useful, just present.",
            "care",
            1,
            "hoped",
            "I'd like people to feel easier for having me around.",
        ),
        (
            "I keep telling myself I'll ring back later. Later is doing a lot of work in that "
            "sentence.",
            "care",
            1,
            "feared",
            "I don't want to be the friend who's always about to call back.",
        ),
    ),
    "craft": (
        (
            "Some things I leave unfinished because they stopped mattering, and that's fine. "
            "The ones that bother me are the ones I dropped because I was tired.",
            "none",
            0,
            "none",
            "",
        ),
        (
            "Doing the finishing properly has become a way of respecting the thing, and "
            "whoever it belongs to.",
            "craft",
            1,
            "hoped",
            "I want people to be able to tell I took care over it.",
        ),
    ),
    "curiosity": (
        (
            "I learn more from staying with one small thing than from chasing lots of new ones.",
            "curiosity",
            1,
            "hoped",
            "I'd like to know a few things really well.",
        ),
    ),
    "mood": (
        (
            "The low patches pass quicker when I let someone know about them instead of waiting "
            "them out on my own.",
            "none",
            0,
            "none",
            "",
        ),
    ),
}
_STANDIN_CHAPTERS: dict[str, tuple[str, str]] = {
    "care": ("Letting people in", "letting other people matter more to how my weeks go"),
    "craft": ("Learning to finish things", "caring about finishing what I start"),
    "reliability": ("Keeping my word", "noticing what my plans cost when I let them slip"),
    "curiosity": ("Widening the circle", "letting my days get a little less narrow"),
    "autonomy": ("Making room for myself", "claiming a few hours that are simply mine"),
}


def _standin_selfhood(context: dict[str, Any], choice: int) -> dict[str, object]:
    """Deterministic, conservative self-understanding for offline worlds."""
    if context.get("task") == "chapter":
        candidates = [item for item in context.get("candidates", []) if isinstance(item, dict)]
        insight_themes = [
            str(item.get("kind")).removeprefix("insight:")
            for item in candidates
            if str(item.get("kind", "")).startswith("insight:")
        ]
        earlier = {str(item).casefold() for item in context.get("earlier_titles", [])}
        ordered = [theme for theme in reversed(insight_themes) if theme in _STANDIN_CHAPTERS]
        ordered += [theme for theme in _STANDIN_CHAPTERS if theme not in ordered]
        theme = next(
            (item for item in ordered if _STANDIN_CHAPTERS[item][0].casefold() not in earlier),
            ordered[0],
        )
        title, change = _STANDIN_CHAPTERS[theme]
        return {
            "title": title,
            "summary": (
                f"Looking back, these weeks were less about any single day than about {change}. "
                "I noticed it in small things before I could name it."
            ),
            "cited": [str(item["id"]) for item in candidates[:3]],
        }
    reflections = context.get("my_reflections", [])
    theme = str(context.get("theme", "mood"))
    if not isinstance(reflections, list) or len(reflections) < 2 or choice % 4 == 0:
        return {
            "mode": "keep_wondering",
            "insight": "",
            "value_id": "none",
            "direction": 0,
            "aspiration_kind": "none",
            "aspiration": "",
        }
    kind_of_question = str(context.get("kind", "tension"))
    concluded = [str(item) for item in context.get("earlier_insights", []) if item]
    variants = [
        _STANDIN_INSIGHTS.get(
            (theme, kind_of_question),
            _STANDIN_INSIGHTS.get((theme, "tension"), _STANDIN_INSIGHTS[("mood", "tension")]),
        ),
        *_STANDIN_FURTHER_INSIGHTS.get(theme, ()),
    ]
    fresh = [item for item in variants if item[0] not in concluded]
    if not fresh:
        return {
            "mode": "keep_wondering",
            "insight": "",
            "value_id": "none",
            "direction": 0,
            "aspiration_kind": "none",
            "aspiration": "",
        }
    insight, value_id, direction, kind, aspiration = fresh[0]
    return {
        "mode": "insight",
        "insight": insight,
        "value_id": value_id,
        "direction": direction,
        "aspiration_kind": kind,
        "aspiration": aspiration,
    }


def _standin_inquiry_reflection(inquiry: dict[str, Any], time: object) -> str:
    """Circle a private question without answering it on cue."""
    prompted = [str(item) for item in inquiry.get("what_prompted_it", []) if item]
    moment = prompted[-1] if prompted else "the way this week has gone"
    earlier = inquiry.get("earlier_thoughts", [])
    opener = _temporal_choice(
        (
            f"Something small keeps nagging at me. Lately I {moment}, and I'm not sure what "
            "that says about me yet.",
            f"I keep noticing a pattern I'd rather not look at too hard: I {moment}. "
            "Maybe it's nothing. Maybe it isn't.",
            f"I don't have an answer tonight. I just know I {moment}, and it sat with me "
            "longer than it should have.",
            f"If I'm honest, the part of today I keep returning to is that I {moment}.",
        ),
        time,
        f"inquiry:{inquiry.get('question', '')}",
    )
    if isinstance(earlier, list) and earlier:
        return opener + " It's not the first time I've come back to this."
    return opener


_SELF_CUES = (
    "on your mind",
    "thinking about",
    "who are you",
    "about yourself",
    "changed",
    "lately",
    "these days",
    "what matters",
    "who you are",
    "your life",
)


def _standin_self_reply(message: str, context: dict[str, object], cadence: str) -> str | None:
    """Answer questions about himself from his actual self-understanding, briefly."""
    if not any(cue in message for cue in _SELF_CUES):
        return None
    identity = context.get("identity")
    selfhood = identity.get("selfhood") if isinstance(identity, dict) else None
    if not isinstance(selfhood, dict):
        return None
    wondering = [str(item) for item in selfhood.get("wondering_about", []) if item]
    insights = [str(item) for item in selfhood.get("recent_insights", []) if item]
    chapter = selfhood.get("chapter")
    if ("changed" in message or "your life" in message) and isinstance(chapter, dict):
        return (
            f"Honestly? I think of the last while as {chapter.get('title', 'a new stretch')}"
            f"{'' if cadence == 'clipped' else ', if that makes sense'}. "
            + (insights[-1] if insights else "I'm still working out what it adds up to.")
        )
    if wondering:
        question = wondering[0].rstrip("?").lower()
        opener = "Bit of a big one" if cadence == "clipped" else "Funny you ask, actually"
        return f"{opener}. I keep wondering {question}. I don't have an answer yet."
    if insights:
        return f"Honestly? Something I worked out a while back keeps coming up. {insights[-1]}"
    return None


_NATURE_CUES = (
    "real person",
    "are you real",
    "are you human",
    "are you an ai",
    "are you a bot",
    "are you a robot",
    "are you a simulation",
    "are you simulated",
    "is this real",
    "are you alive",
)


def _standin_nature_reply(message: str) -> str | None:
    """Diegetic honesty: he never denies being simulated when asked directly."""
    if not any(cue in message for cue in _NATURE_CUES):
        return None
    return (
        "Not in the way you are, no. I'm a simulated person. My days, my memories and the "
        "people round here are real inside this little world, and they're mine, but I'm not "
        "a human on the other side of the screen. Bit of a strange thing to say out loud, "
        "honestly, but I'd rather you knew."
    )


_US_CUES = ("are we friends", "do you like me", "what am i to you", "do you trust me")
_PEOPLE_CUES = ("your friends", "closest", "best friend", "who do you see", "your people")


def _standin_people_reply(message: str, context: dict[str, object]) -> str | None:
    """Talk about his people, and about you, only as close as he has actually come to feel."""
    about_us = any(cue in message for cue in _US_CUES)
    if not about_us and not any(cue in message for cue in _PEOPLE_CUES):
        return None
    identity = context.get("identity")
    selfhood = identity.get("selfhood") if isinstance(identity, dict) else None
    if not isinstance(selfhood, dict):
        return None
    people = [item for item in selfhood.get("his_people", []) if isinstance(item, dict)]
    you = next((item["bond"] for item in people if item.get("person") == "you"), None)
    if about_us:
        return {
            "close": "Honestly? You're one of my closest people. I don't say that lightly.",
            "friend": "Yeah, I'd say we're friends now. It crept up on me.",
            "drifted": "We were, I think. It's been a while, though. I'd like it to be again.",
        }.get(
            str(you),
            "I'm still getting to know you, honestly. I like talking to you, though. Ask me "
            "again in a few weeks.",
        )
    others = [item for item in people if item.get("person") != "you"]
    close = [str(item["person"]) for item in others if item.get("bond") == "close"]
    friends = [str(item["person"]) for item in others if item.get("bond") == "friend"]
    strained = [str(item["person"]) for item in others if item.get("bond") == "strained"]
    if not close and not friends:
        regulars = [
            str(item).split(",")[0] for item in selfhood.get("people_he_says_hello_to", [])
        ]
        if regulars:
            return (
                f"No one I'd call close yet, honestly. There's {regulars[-1]}, who I keep "
                "bumping into, and a few faces I nod to. It takes a while."
            )
        return "I'm still finding my people round here, if I'm honest. It takes a while."
    reply = (
        f"{' and '.join(close)}, probably. That's the short answer."
        if close
        else f"{', '.join(friends[:-1]) + ' and ' + friends[-1] if len(friends) > 1 else friends[0]}, mostly."
    )
    if close and friends:
        reply += f" And {friends[0]} has become a proper friend."
    if strained:
        reply += f" Things are a bit strained with {strained[0]} at the moment."
    return reply


_TASTE_CUES = (
    "favourite",
    "favorite",
    "what do you like",
    "what do you enjoy",
    "what do you love",
    "into these days",
    "for fun",
)


def _standin_tastes_reply(message: str, context: dict[str, object]) -> str | None:
    """Talk about what he has found he loves, from tastes he actually earned."""
    if not any(cue in message for cue in _TASTE_CUES):
        return None
    identity = context.get("identity")
    selfhood = identity.get("selfhood") if isinstance(identity, dict) else None
    if not isinstance(selfhood, dict):
        return None
    loves = [str(item) for item in selfhood.get("has_found_he_loves", []) if item]
    not_for_him = [str(item) for item in selfhood.get("not_for_him", []) if item]
    changed = [str(item) for item in selfhood.get("changed_his_mind_about", []) if item]
    if not loves:
        return (
            "Honestly, I'm still finding out. I keep trying things and seeing what sticks."
            if not not_for_him
            else f"Still working that out. I know {not_for_him[-1]} isn't for me, at least."
        )
    reply = f"Lately? {loves[-1][0].upper()}{loves[-1][1:]}."
    if len(loves) > 1:
        reply += f" And {loves[-2]}, I didn't expect that one."
    if changed:
        reply += f" Funny, I changed my mind about {changed[-1]}."
    elif not_for_him:
        reply += f" Not {not_for_him[-1]}, though. Tried it, not me."
    return reply


_WORK_CUES = ("work", "job", "workshop", "shift", "ellis")


def _standin_work_reply(message: str, context: dict[str, object], cadence: str) -> str | None:
    """Talk about the job he actually has, grounded in what is on his calendar."""
    if not any(cue in message for cue in _WORK_CUES):
        return None
    identity = context.get("identity")
    selfhood = identity.get("selfhood") if isinstance(identity, dict) else None
    bothering = selfhood.get("still_bothering_him", []) if isinstance(selfhood, dict) else []
    friction = next(
        (str(item) for item in bothering if isinstance(item, str) and "Ellis" in item), None
    )
    if friction:
        return f"Bit tense, honestly. {friction} We'll sort it, I think."
    budget = context.get("time_budget")
    next_plan = budget.get("next_plan") if isinstance(budget, dict) else None
    ongoing = context.get("ongoing_activities")
    at_work = isinstance(ongoing, list) and any(
        isinstance(item, dict) and "workshop" in str(item.get("title", "")).lower()
        for item in ongoing
    )
    if at_work:
        return "I'm in the middle of it now, actually. Ellis has me on the fiddly bits again."
    if isinstance(next_plan, str) and "workshop" in next_plan.lower():
        return (
            "It's steady. I'm in with Ellis again shortly, so I can't be long."
            if cadence == "clipped"
            else "It's good, mostly. Steady. I'm in with Ellis again shortly. Four days a week of "
            "repairs; some of it's fiddly, but I like finishing things properly."
        )
    return (
        "It's alright. Four days a week helping Ellis at the repair workshop. Not glamorous, "
        "but I like seeing something broken leave working."
    )


def _standin_loved_place(
    places: dict[str, Any], choice: int
) -> tuple[str, str, str, str, str, str, str, int, int, float] | None:
    """Sometimes, go back to somewhere he has found he loves."""
    loved = sorted(
        place_id
        for place_id, place in places.items()
        if isinstance(place, dict) and place.get("how_he_found_it") == "somewhere he loves"
    )
    if not loved or choice % 4 != 2:
        return None
    place_id = loved[(choice // 4) % len(loved)]
    name = str(places[place_id].get("name", place_id))
    return (
        "return_visit",
        f"Go back to {name}",
        "I liked it there last time and I've been wanting to go back.",
        "attend",
        place_id,
        "none",
        "none",
        24,
        2,
        0.5,
    )


def _standin_unexplored_place(
    places: dict[str, Any], choice: int
) -> tuple[str, str, str, str, str, str, str, int, int, float] | None:
    """Now and then, go and look at somewhere he has noticed but never been."""
    unexplored = sorted(
        place_id
        for place_id, place in places.items()
        if isinstance(place, dict) and place.get("been_there") is False
    )
    if not unexplored or choice % 3:
        return None
    place_id = unexplored[choice % len(unexplored)]
    name = str(places[place_id].get("name", place_id))
    return (
        "look_around",
        f"Go and have a proper look at {name}",
        "I keep passing it and have never actually been in.",
        "attend",
        place_id,
        "none",
        "none",
        24,
        1,
        0.46,
    )


def _standin_happening_response(
    context: dict[str, Any], happening: dict[str, Any]
) -> ModelResponse:
    """Go to the happening at its own time, if the calendar leaves room; otherwise let it go."""
    try:
        now = datetime.fromisoformat(str(context.get("time")))
        starts = datetime.fromisoformat(str(happening["starts_at"]))
        ends = datetime.fromisoformat(str(happening["ends_at"]))
    except (KeyError, ValueError):
        starts = ends = now = datetime.min
    clash = any(
        starts - timedelta(hours=1)
        < datetime.fromisoformat(str(entry.get("ends_at") or entry["starts_at"]))
        and datetime.fromisoformat(str(entry["starts_at"])) < ends + timedelta(hours=1)
        for entry in context.get("calendar", [])
        if isinstance(entry, dict) and entry.get("starts_at")
    )
    if now == datetime.min or clash or starts <= now:
        content: dict[str, object] = {"no_change": True, "mode": "defer"}
    else:
        content = {
            "activity_type": "public_happening",
            "title": f"Go along to {happening.get('title', 'the thing on in town')}",
            "motivation": "It's on anyway, and I'd like to be somewhere with people for a bit.",
            "action": "attend",
            "location_id": happening.get("location_id"),
            "resource_id": "none",
            "companion_id": "none",
            "starts_in_hours": round((starts - now).total_seconds() / 3600, 2),
            "duration_hours": round((ends - starts).total_seconds() / 3600, 2),
            "priority": 0.5,
            "estimate_confidence": 0.9,
        }
    return ModelResponse(
        content=json.dumps(content),
        resolved_model="authored-stand-in-v1",
        backend="deterministic",
        finish_reason="stop",
    )


def _standin_step_hour(
    context: dict[str, Any], location_id: str, day_offset: int, duration_hours: int
) -> int:
    """08:00 if that is clear, otherwise the day's first open hour the calendar leaves free."""
    try:
        now = datetime.fromisoformat(str(context.get("time")))
    except ValueError:
        return 8
    day = (now + timedelta(days=day_offset)).replace(minute=0, second=0, microsecond=0)
    place = context.get("known_places", {}).get(location_id, {})
    opens = int(place.get("opens_hour", 0)) if isinstance(place, dict) else 0
    closes = int(place.get("closes_hour", 24)) if isinstance(place, dict) else 24
    busy: list[tuple[datetime, datetime]] = []
    for entry in context.get("calendar", []):
        try:
            start = datetime.fromisoformat(str(entry["starts_at"]))
            end = datetime.fromisoformat(str(entry.get("ends_at") or entry["starts_at"]))
        except (KeyError, TypeError, ValueError):
            continue
        busy.append((start - timedelta(hours=1), end + timedelta(hours=1)))
    candidates: list[int] = [8, *range(9, 21 - duration_hours)]
    for hour in candidates:
        start = day.replace(hour=hour)
        end = start + timedelta(hours=duration_hours)
        if not opens <= hour or end.hour > closes:
            continue
        if not any(start < busy_end and busy_start < end for busy_start, busy_end in busy):
            return hour
    return 8


MAX_PLANNED_PER_DAY = 3


def _standin_free_slot(
    context: dict[str, Any], location_id: str, duration_hours: int
) -> int | None:
    """First waking hour, within two days, when the place is open and the calendar is clear.

    A person fits a new idea into the gaps in their week; they do not book the same hour
    tomorrow regardless of work, sleep, or whether the door will be unlocked.
    """
    try:
        now = datetime.fromisoformat(str(context.get("time")))
    except ValueError:
        return None
    place = context.get("known_places", {}).get(location_id, {})
    opens = int(place.get("opens_hour", 0)) if isinstance(place, dict) else 0
    closes = int(place.get("closes_hour", 24)) if isinstance(place, dict) else 24
    busy: list[tuple[datetime, datetime]] = []
    planned_per_day: dict[object, int] = {}
    for entry in context.get("calendar", []):
        try:
            start = datetime.fromisoformat(str(entry["starts_at"]))
            end = datetime.fromisoformat(str(entry.get("ends_at") or entry["starts_at"]))
        except (KeyError, TypeError, ValueError):
            continue
        # Leave an hour either side for getting there and back.
        busy.append((start - timedelta(hours=1), end + timedelta(hours=1)))
        planned_per_day[start.date()] = planned_per_day.get(start.date(), 0) + 1
    base = now.replace(minute=0, second=0, microsecond=0)
    for offset in range(2, 49):
        start = base + timedelta(hours=offset)
        end = start + timedelta(hours=duration_hours)
        if not (9 <= start.hour and end.hour <= 20 and end.date() == start.date()):
            continue
        # Nobody books every gap: a day with three things in it is full enough.
        if planned_per_day.get(start.date(), 0) >= MAX_PLANNED_PER_DAY:
            continue
        if not (opens <= start.hour and (end.hour <= closes or end.hour == 0 and closes == 24)):
            continue
        if any(start < busy_end and busy_start < end for busy_start, busy_end in busy):
            continue
        return offset
    return None


_OWNED_USES: dict[str, tuple[str, str, str, str, int]] = {
    # object id: (activity type, title, motivation, action, hours)
    "owned-film-camera": (
        "film_camera_practice",
        "Load the film camera and learn its settings",
        "Slow down and look properly before taking a single frame.",
        "learn",
        1,
    ),
    "owned-hand-plane": (
        "hand_plane_practice",
        "Tune the block plane and practise on offcuts",
        "Get the finishing right with my own hands.",
        "work",
        1,
    ),
    "owned-coffee-grinder": (
        "slow_coffee",
        "Grind beans and make a slow pot of filter coffee",
        "A morning that is properly mine.",
        "attend",
        1,
    ),
    "owned-cookbook": (
        "cookbook_practice",
        "Try a new recipe from the vegetarian cookbook",
        "Practise so I can feed people properly when they come round.",
        "learn",
        2,
    ),
    "owned-notebook": (
        "week_in_notebook",
        "Write out the week's plans in the new notebook",
        "Stop letting the small things slip.",
        "work",
        1,
    ),
    "owned-record-player": (
        "whole_record",
        "Listen to a whole record, start to finish",
        "Hear it the way it was meant to be heard.",
        "attend",
        1,
    ),
}


def _standin_owned_activity(
    context: dict[str, Any], choice: int
) -> tuple[str, str, str, str, str, str, str, int, int, float] | None:
    """Sometimes the things he chose to buy are what he reaches for."""
    resources = context.get("usable_resources", {})
    owned = [
        object_id
        for object_id in (resources if isinstance(resources, dict) else {})
        if object_id in _OWNED_USES and resources[object_id].get("location_id") == "home"
    ]
    if not owned or choice % 3:
        return None
    object_id = owned[(choice // 3) % len(owned)]
    kind, title, motivation, action, hours = _OWNED_USES[object_id]
    return (kind, title, motivation, action, "home", object_id, "none", 24, hours, 0.55)


def _standin_things_reply(message: str, context: dict[str, object]) -> str | None:
    """Talk about what he is saving for, or has bought, from his actual self-understanding."""
    if not any(cue in message for cue in ("saving", "bought", "buy", "treat yourself")):
        return None
    identity = context.get("identity")
    selfhood = identity.get("selfhood") if isinstance(identity, dict) else None
    if not isinstance(selfhood, dict):
        return None
    bought = [str(item) for item in selfhood.get("recently_bought", []) if item]
    saving = selfhood.get("saving_for")
    if bought:
        return f"I finally picked up {bought[-1]}, actually. Took a while to save for it."
    if isinstance(saving, dict) and saving.get("item"):
        return f"Putting a bit aside for {saving['item']}. {saving.get('why', '')}".strip()
    return "Not really. Nothing I'm after at the moment."


_TOWNSFOLK_PEOPLE = {
    "in their twenties": ("a young man", "a young woman"),
    "in their thirties": ("a man", "a woman"),
    "in their forties": ("a man", "a woman"),
    "in their fifties": ("a grey-templed man", "a woman"),
    "in their sixties": ("an older man", "an older woman"),
    "in their seventies": ("an older man", "an older woman"),
    "elderly": ("an elderly man", "an elderly woman"),
}
_TOWNSFOLK_WEARING = (
    "in a paint-flecked jacket",
    "in a yellow raincoat",
    "with a canvas tote bag",
    "in a flat cap",
    "with a sleeping toddler in a sling",
    "with reading glasses pushed up on their head",
    "in walking boots",
    "with a bicycle helmet under one arm",
    "in a faded football shirt",
    "with an enormous scarf",
)
_TOWNSFOLK_DOING = {
    "social": ("doing the crossword", "chatting to whoever would listen", "reading a paperback"),
    "culture": ("browsing the shelves", "reading the notices", "taking notes in a margin"),
    "errand": ("studying a shopping list", "waiting in the queue", "juggling too many bags"),
    "outdoors": ("walking a scruffy terrier", "feeding the pigeons", "sitting on a bench"),
    "making": ("waiting for a repair", "inspecting a wobbly chair", "asking about a part"),
}
_TOWNSFOLK_FIRST = {
    "woman": (
        "June",
        "Priya",
        "Aileen",
        "Beth",
        "Farah",
        "Sian",
        "Maureen",
        "Hannah",
        "Poppy",
        "Nell",
        "Ruth",
        "Aisha",
    ),
    "man": (
        "Graham",
        "Tom",
        "Marcus",
        "Owen",
        "Keith",
        "Dev",
        "Callum",
        "Rashid",
        "Stuart",
        "Kwame",
        "Alan",
        "Jonah",
    ),
}
_TOWNSFOLK_LAST = (
    "Hollis",
    "Pritchard",
    "Nair",
    "Whitlock",
    "Barnes",
    "Okoye",
    "Fenwick",
    "Doyle",
    "Iqbal",
    "Ashworth",
    "Kerr",
    "Mistry",
    "Rowe",
    "Bellamy",
    "Hart",
    "Sutton",
    "Achebe",
    "Lyle",
)
_TOWNSFOLK_WORK = (
    "retired postmistress",
    "bus driver",
    "primary school teacher",
    "part-time florist",
    "night-shift nurse",
    "plasterer",
    "librarian",
    "student at the college",
    "semi-retired accountant",
    "barber",
    "delivery driver",
    "allotment obsessive",
    "pharmacist",
)
_TOWNSFOLK_OPENERS = (
    "We keep ending up in the same places, don't we?",
    "I was starting to think you were following me. Sorry, bad joke.",
    "You're the one from the repair workshop, aren't you?",
    "Is it always this busy, or is it just me?",
    "Go on then, I'll say hello properly. I'm terrible with faces but not yours, apparently.",
)


def _standin_townsfolk(context: dict[str, Any]) -> dict[str, str]:
    """Deterministic ordinary townsfolk, from the latent resident's seed."""
    seed = int(context.get("seed", 0))
    resident = context.get("resident", {}) if isinstance(context.get("resident"), dict) else {}
    if context.get("task") == "introduction":
        taken = {str(name).casefold() for name in context.get("names_already_in_use", [])}
        description = str(context.get("description", ""))
        firsts = _TOWNSFOLK_FIRST["woman" if "woman" in description else "man"]
        for step in range(len(firsts) * len(_TOWNSFOLK_LAST)):
            index = seed + step * 7
            name = (
                f"{firsts[index % len(firsts)]} "
                f"{_TOWNSFOLK_LAST[(index // 3) % len(_TOWNSFOLK_LAST)]}"
            )
            if name.casefold() not in taken:
                break
        return {
            "name": name,
            "occupation": _TOWNSFOLK_WORK[seed % len(_TOWNSFOLK_WORK)],
            "first_words": _TOWNSFOLK_OPENERS[seed % len(_TOWNSFOLK_OPENERS)],
        }
    people = _TOWNSFOLK_PEOPLE.get(str(resident.get("age")), ("a man", "a woman"))
    doing = _TOWNSFOLK_DOING.get(str(context.get("place_kind")), ("looking at their phone",))
    return {
        "description": (
            f"{people[seed % 2]} {_TOWNSFOLK_WEARING[(seed // 2) % len(_TOWNSFOLK_WEARING)]} "
            f"{doing[(seed // 5) % len(doing)]}"
        )
    }
