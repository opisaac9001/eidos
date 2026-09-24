# Selfhood: how Patrick comes to know himself

Patrick begins with an authored character pack: a biography, starting values, and a few
soft preferences. That pack is a starting point, not a script. Selfhood is the slow loop
through which he comes to understand, and gradually change, who he is. Everything in it
grows from how he has actually lived.

Code: `src/eidos/domain/selfhood.py` (rules and replay) and
`src/eidos/application/selfhood.py` (cadence, prompts, context). UI: the **Becoming** view.

## The loop

```text
lived events ──► felt as honouring / neglecting a value (evidence)
                     │
       sustained tension, a dormant value, or one he is thriving in
                     ▼
            a private open question (inquiry)
                     │   the 21:00 reflection returns to it
                     ▼   (≥3 revisits over ≥4 days)
      insight in his own words ── or ── keep wondering / let it fade
          │                  │
          ▼                  ▼
   one small value step   a hoped-for or feared possible self
          │                  │
          ▼                  ▼
  identity values seen    impulses that pull (modestly) toward
  by every planner        choices that fit who he hopes to be
                     │
       turning points accumulate into life chapters
```

### 1. Evidence

`value_evidence(event)` classifies only Pathos-owned experience as honouring (+1) or
neglecting (−1) one of five values: **care, curiosity, reliability, autonomy, craft**.
A kept plan honours reliability; a missed call or visitor is felt as care slipping, even
though he did not choose it; finishing work honours craft; doing something purely on his
own terms honours autonomy. Twelve consecutive heavy hours leave one *mood* mark. One lived
moment often lands as several events, so each kind of feeling counts once per day.

### 2. Questions (inquiries)

Each evening at 20:00 the daily pass may open **one** question when, over the last three
weeks:

| Kind | When | Example |
|---|---|---|
| tension | a held value (≥0.6) was neglected at least three times, and at least 60% as often as honoured (real ambivalence counts) | "Am I someone who follows through, or just someone who means to?" |
| thriving | a value below 0.8 was honoured six or more times, with neglect at most a fifth as often | "Is making things properly becoming who I am?" |
| dormant | a strongly held value (≥0.7) went completely unlived for three weeks | "When did I last go and learn something just because I wanted to?" |
| mood | two heavy stretches within a week | "What has been weighing on me lately?" |

A theme and kind he has already been through ranks lower than parts of his life not yet asked about. At most three questions are open at a time. They open at least two days apart, never twice
on the same theme, and a closed theme cools off for 30 days. A question that sits untouched
for three weeks, or has been revisited six times without an answer, fades: "set down
without an answer" is a real, common outcome.

### 3. Reflection and insight

The 21:00 reflection receives the least recently revisited question as `self_inquiry`.
It is asked to turn toward the question honestly, without having to answer it. Each
reflection is recorded as a revisit.

After at least **three revisits spanning four days**, the `pathos_selfhood` performer
reads his own reflections and either keeps wondering or proposes one modest first-person
insight. Rules reject:

- third-person, reader-addressed or diagnostic language;
- claims of new actions;
- repeating an insight he already had;
- moving a value his recent life does not support (a different value may only move in the
  direction his lived evidence shows).

### 4. Values

A validated insight may move one value by **0.03**, in its stated direction. A value moves
at most once every 21 days, drifts at most ±0.24 over a lifetime, and stays within
0.05–0.98. No value moves in his first fortnight of lived evidence. The prior value must
match what he currently holds. Shifted values flow into `project_identity`, so the
planners, agency and every personal performer see the values he now holds.

### 5. Possible selves

An insight may crystallise a **hoped-for** or **feared** self ("I want to be the friend
who actually picks up"; "I don't want to become someone surrounded by nearly finished
things"). There is one per value at most, four in total, and a new hope on the same value
releases the old one. Each evening, progress is counted **only from cited evidence**:
moments toward the hope (or away from the fear) and moments the other way. A possible self
with no evidence for 90 days is released.

Active possible selves enter the impulse field as modest `aspiration` pulls, stronger when
he has been drifting from them. They compete with hunger, chores, thoughts and doing
nothing inside his limited attention. They are hopes, never goals or obligations.

### 6. Life chapters

The first chapter, "Finding my feet", opens once he has lived a little. On Sunday evenings,
at least six weeks into a chapter, a real turning point (an insight **and** a value shift or
new possible self) invites the performer to name the next chapter and summarise it from
cited candidates. Titles must be new. Chapters are the autobiography he can actually cite.

### 7. Wants

Money is part of identity only if it can become something. On Saturday mornings, if he
has no live want, the value he has lived most over three weeks, or the value behind a hope
he holds, points toward one ordinary thing that fits his authored interests: a secondhand
film camera (curiosity), a block plane (craft), a hand coffee grinder (autonomy), a
vegetarian cookbook (care), a notebook (reliability), a record player (curiosity). He
sits with it for three days, saves until he can buy it and keep a £200 cushion, and picks
it up on a free day while he is out. The purchase is charged to the ledger and becomes an
owned object at home that his plans can use. It is recorded as a milestone memory and as
lived evidence for its value. A want still out of reach after 60 days is let go. A taste
comes first: having found he loves the café makes the coffee grinder appealing ("I've
found I love Juniper Café…"). Something tied to what he has gone off, such as a cookbook
after deciding recipe annotation isn't for him, is never wanted.
(`application/wants.py`)

### 8. Tastes

Nobody is born loving the Friday film. After each activity he chooses (not work shifts),
the rules settle how much he enjoyed it, from -1 to 1 (`experience.felt`). That depends on:

- how well it fits the value that kind of place speaks to: outdoors is autonomy, making is
  craft, social places are care, culture is curiosity;
- whether he was short of company, and sociable enough to want it, or too tired for it;
- the weather, for outdoor things;
- the small lift of a first visit, which scales with openness;
- a thing getting samey after four goes in a fortnight;
- the mood he brought with him;
- his temperament: a stable, hidden affinity for each place or kind of home activity.
  Some things just suit him and some don't, consistently, and he only finds out by trying;
- a smaller share of plain unpredictability.

Notable experiences leave a memory in his words, for example "Going along to the quiz:
loved it, honestly. It was good to be among people."

One experience at 0.65 or more, or at least two that average 0.35 or more (up to the last
five count), becomes a taste (`taste.formed`) about that place or kind of activity:
something he loves, or something that isn't for him. If the next two or three experiences
go the other way, he changes his mind (`taste.revised`), and both stances stay in his
history. Loving something is lived evidence for its value. Tastes reach:

- his self-context: `has_found_he_loves`, `not_for_him`, `changed_his_mind_about`;
- his choices: a known place carries `how_he_found_it`, a happening at a loved venue pulls
  harder, and one at a place he has gone off pulls less;
- his voice;
- the Becoming view.

(`application/experience.py`, `domain/tastes.py`)

### 9. His people

Friendship follows the twelve-level view in
[12 Levels of Friendship](https://sparkjoyandflow.substack.com/p/12-levels-of-friendship-and-why-it)
(Spark Joy and Flow). Most friendships sit at level five or below, deep ones are built by
what people go through together, and a deep friendship doesn't need constant upkeep.
(`application/friendship.py`)

| Levels | Tier | What he calls them | Needs keeping up? |
|---|---|---|---|
| 1-3 | everyday | a familiar face, easy company, someone to chat with | fades after about two weeks apart |
| 4-5 | real connection | a friend to hang out with, a friend who cares | fades slowly after about six weeks without contact, never below 3 |
| 6-8 | deepening | someone he can rely on, a true friend, an effortless friend | **no**: absence never erodes it |
| 9-12 | soul-level | someone who knows him deeply, a confidant, the first person he'd call, inseparable | **no** |

**How depth is earned.** Depth is separate from recency. It grows from shared moments, and
each level is harder to reach than the last:

| Moment | Weight |
|---|---|
| a passing encounter or scene | 0.05–0.1 |
| a follow-up, a call, shared use of something | 0.1–0.15 |
| planned time together or a visit | 0.3 |
| going through an incident together, clearing the air, repairing a rift | 0.5–0.6 |

A single day counts for at most 0.5, and after a year a real friendship also gains a little
from the years. A friendship without any hard moments shared tops out at level five, and
the higher levels also need time:

| To reach | Needs about |
|---|---|
| level 7 | two months |
| level 8 | four months |
| level 9 | six months and three moments gone through together |
| level 10 | a year |
| levels 11-12 | two years |

**What he notices** (`application/bonds.py`), at the 20:00 review and only one thing a day:

- someone has become a friend (4), someone he can count on (6), or one of his closest
  people (9). How close someone is isn't re-decided more than every three weeks;
- a lighter friendship has drifted ("No falling out, just life");
- things have got strained, or feel right again. Strain is a passing state that never
  costs levels;
- he hasn't seen a close friend in about N weeks ("It'll be like no time has passed when
  we do");
- the reunion ("Picked up right where we left off").

The friendship-drift setback (care −1) now only applies to real-connection friendships
after six weeks apart; acquaintances fade without anyone minding.

**You.** The person talking with him is one of his people by the same rules. Each day you
talk is a shared moment, and a long conversation (six or more messages) counts as going
through something together. A close friend who goes quiet for a month is still a close
friend: he notes that it's been a while and hopes you're alright, without pressure.

Growing closer is lived evidence of care. `his_people`, with each person's level, any
strain and time apart, reaches his self-context and the Becoming view, so "are we
friends?" is answered only as close as he has come to feel.

## What performers see

`identity.selfhood` (voice, Murmur, reflection, dreams):

```json
{
  "chapter": {"number": 2, "title": "Keeping my word", "since": "2026-02-15", "summary": "…"},
  "wondering_about": ["Why do I keep letting the things I've planned slip?"],
  "recent_insights": ["Leaving things half-made bothers me more than I let on…"],
  "hopes": ["I want my small promises to be as solid as my big ones."],
  "fears": ["I don't want to become someone surrounded by nearly finished things."],
  "values_that_have_shifted": [{"value": "craft", "direction": "matters more"}],
  "epistemic_status": "subjective_self_understanding"
}
```

It shapes what he notices, admits or hesitates over. He rarely talks about it unprompted.

## Replay contract

Every `self.*` event is re-validated on restart: sources must be lived evidence or his own
reflections, revisits must cite real reflections, value steps must match current values
and bounds, and progress counts are recomputed from cited evidence rather than trusted.
**The constants in `domain/selfhood.py` are part of that contract.** Loosening a bound is
safe. Tightening one can make an existing life unreplayable, so it needs a versioned rule
rather than an in-place edit.

## Boundaries

- Nothing here is a diagnosis. Diagnostic words are rejected.
- Questions and insights are private. The Becoming view is an observer's window, not
  something he recites.
- Only rules move values, and only a little. A model's eloquence cannot rewrite who he is.
- Diegetic honesty holds: self-understanding is his, and it never obscures that he is a
  simulated person when directly asked.
