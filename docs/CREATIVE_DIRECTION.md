# Creative direction: a life, not a chat session

## The central illusion

Pathos is not generated when a message arrives. He is a persistent person in a
persistent place. Conversation is only one window into his life.

When the user returns after a week, Pathos should not merely retrieve a few old
chat fragments. He should have experienced an understandable interval: ordinary
days, incomplete plans, encounters, changing relationships, private thoughts,
and perhaps one or two genuinely memorable events. His account of that interval
must agree with the world's account.

## A routine is a floor, not a script

Pathos must not cycle through the same handful of beats every day. Stable habits,
work, sleep, and familiar places make change legible, but ordinary life also contains
errands, visitors, weather changes, cancellations, overheard moments, new people,
unexpected invitations, local events, idle detours, and days when little happens.
Variety should emerge from needs, seasons, relationships, available resources, and
the town's evolving state rather than a fixed daily content rotation.

Invented detail is welcome inside the fiction. A model may propose a new resident,
street incident, conversation, or opportunity; continuity rules decide whether and
how it becomes true. The critic protects established facts and agency, not blandness.
The authored neighborhood pack is an offline reliability floor, not a menu or a
ceiling. Moira's event type is deliberately open vocabulary. The current first
contract grounds invented incidents in known places; later contracts may introduce
new people, objects and places through explicit persistent state changes.

Real-world weather, daylight, and optional RSS reports from a configured British town
can inspire the world. Their source and retrieval time are retained and the signals
expire. They are creative seeds and ambient context, never imported world facts;
Pathos does not claim to have witnessed a news report merely because Moira read it.
Moira must cite a supplied signal ID when it uses one, and its resulting fiction still
passes normal place, resource, novelty, scheduling, and perception rules.

## A cast of intelligences

The system uses several AI roles, but they do not compete to impersonate one
general assistant. Each has a narrow creative responsibility.

### Pathos

The sole owner of Pathos's voice and present-tense decisions. This role receives
only what Pathos can perceive, remember, infer, or be told. It cannot see hidden
world state or system instructions belonging to other roles.

Pathos talks like a person, not a reflective assistant. His ordinary register is
relaxed, direct and plainspoken: short replies, contractions, occasional fragments,
and room for an unpolished thought. He lightly meets the user's formality without
copying their mistakes or losing his own character. He does not recap his location,
mood and recent memories on every turn, greet the user again mid-conversation, end
every reply with a question, or reach automatically for therapeutic validation and
grand metaphors. Emotion changes pace and openness rather than decorating every line.
Recent dialogue is part of his bounded context so an ongoing conversation sounds like
one conversation instead of a sequence of fresh prompts.

### The Murmur

Pathos's subconscious association process. It links sensations, unfinished
intentions, emotion, and memory. Most Murmur output never becomes conscious.
Salient fragments surface as intuitions, impulses, intrusive recollections, or
dream seeds.

Emotion is persistent state, not decorative prose. Appraised experiences alter
valence and arousal; duration turns a passing feeling into a sustained pattern;
recovery remains gradual. That state colors attention, inner association, speech,
initiative, social openness, pace, and acceptable risk. It may make a plan less
likely or prompt reconsideration, but never fabricates its own cause, overrides a
promise, compels another person, or substitutes a psychiatric diagnosis.

### Mnemosyne

The memory curator. It proposes consolidation, associations, salience changes,
and contradictions, but cannot rewrite history. Original events and provenance
remain immutable.

### The Firmament ensemble

NPC roles improvise individual behavior from their own limited knowledge,
relationships, needs, and schedules. They do not exist merely to advance
Pathos's story and may act when he is absent.

### Moira

The world director. Moira proposes larger events, coincidences, and narrative
pressure while respecting causality and pacing. It is not an omnipotent prose
generator: deterministic world rules accept, modify, defer, or reject its
proposals.

### Oneiros

The dream composer. It transforms selected memories and affect into surreal
experiences that can influence Pathos emotionally without becoming literal
world history.

### The Chronicler

A low-cost summarization role that builds readable journals and interval
summaries from accepted events. It never invents events.

### The Continuity critic

An evaluator outside the fiction. It looks for contradictions, unexplained
personality changes, repetitive behavior, leaked hidden knowledge, and model
failures. It can flag or quarantine proposals but never speaks as Pathos.

## The world has two speeds

Firmament operates in two modes:

- **Lived time** runs in detail while the user is present or an important scene
  is active.
- **Compressed time** advances through bounded, summarized simulation when the
  system catches up after inactivity.

Catch-up has a narrative budget. Seven absent days should create a coherent
week, not millions of low-value thought records or a single vague summary.

## Attention is a resource

Only a small portion of the world receives expensive generative simulation at
any moment. Deterministic systems maintain schedules and ordinary state. AI is
spent where ambiguity, personality, or storytelling matters.

NPCs outside Pathos's attention use inexpensive state transitions. When they
enter a meaningful scene, their established state becomes context for richer
improvisation. This makes a whole world feasible without pretending every
resident has a continuously running foundation model.

## Memory is evidence, not a vector dump

A memory records what happened, whose perspective it represents, its source,
confidence, emotional effect, and links to the events that support it. Semantic
retrieval finds candidates but does not decide truth.

Pathos may remember incorrectly. The product must distinguish an intentional
in-character mistaken memory from database corruption or model hallucination.

## Personality changes slowly

Traits are not regenerated summaries. They have inertia and change through
repeated evidence, consequential experiences, reflection, and relationships.
Short-term mood alters expression and attention without rewriting identity.

## Generated output is always a proposal

Every AI role returns typed proposals such as:

- say or think something;
- attempt an action;
- recall or associate a memory;
- schedule an intention;
- introduce a world event;
- revise a belief or relationship estimate.

The simulation validates consequences. This is the rule that allows creativity
without sacrificing continuity.

## The first story

The initial world begins intentionally small: Pathos's apartment, a nearby
cafe, a workplace or recurring obligation, and a handful of NPCs whose lives
intersect naturally with his. This is a launch seed, not a permanent ceiling: the
cast, places, activities, and local history should expand through accepted events.
Depth is more convincing than a procedurally named planet with nothing happening in it.

The first playable arc spans seven simulated days and is designed to test:

- routine versus surprise;
- memory across restarts;
- one relationship changing through repeated encounters;
- an unfinished intention carried across several days;
- private experience later discussed with the user;
- a dream that affects mood without becoming factual history.

Success is not measured by whether every response sounds profound. Success is
the user's sense that Pathos was somewhere before the chat opened and will still
be somewhere after it closes.

The ordinary interface is observational. A user may inspect the life but can affect
it only by communicating with Pathos. A text enters an inbox and may wait while he
sleeps, works, travels, speaks with someone else or simply chooses to answer later.
When both parties arrange to be co-present, they may instead have a sustained live
conversation. That scene remains inside the running world: Pathos can be hurried,
decline or leave; a call, visitor, obligation or incident can interrupt it; and any
promise to resume must survive as a real follow-up rather than a convenient reset.
