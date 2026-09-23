# Alderwick — a town Pathos can grow into

Status: the town's public places ship as an ordinary world pack with a weekly calendar
of happenings; its people and transport are still to come. The companion
[`world_plans/alderwick-v1.json`](../world_plans/alderwick-v1.json) is a versioned
geographic blueprint, **not** a Pathos prompt. `eidos.application.town_pack` builds
[`world_packs/alderwick-v1.json`](../world_packs/alderwick-v1.json) from it, and a test
keeps the committed pack identical to what the blueprint builds.

What exists now:

- **23 public places** (pubs, post office, launderette, hardware, clinic, footpaths...)
  added to the 16-place city-life atlas, each joined to its nearest existing place along
  the street graph at 75 m a minute. Private interiors (the school, Southbank housing) are
  left out, and the reading room is reused from the canal-quarter pack when installed.
  The pack fits beside the canal-quarter packs or without them.
- **Registration is not knowledge.** He starts knowing home, the café, the workshop and
  the park. He learns a place by going there, by noticing it along the way (at most one a
  day, only next to where he actually is, with a small memory of it), or by being invited
  there by someone. His own plans and project ideas only reach for places he knows.
- **What's on.** The weekly rhythm below is live as a derived calendar
  (`eidos.application.town_calendar`): quiz night at the Crown on Tuesdays, the repair
  café and a drawing class on alternating Thursdays, Friday music and film, the Saturday
  market, and Sunday allotment and football mornings. Roughly one in eight is called off.
  He only hears about happenings at places he knows. The next one reaches his choices as a
  noticed possibility that pulls harder when he is short of company, and a happening draws
  a crowd. It adds no events, so nothing in the past changes.
- **The map is his map.** The ordinary view shows only known places; the operator view
  shows the whole town, with undiscovered places faded.

Install it after city-life (and optionally the canal-quarter packs):

```bash
PYTHONPATH=src .venv/bin/python -m eidos --database data/observatory.sqlite3 world-pack-import --input world_packs/city-life-v1.json
PYTHONPATH=src .venv/bin/python -m eidos --database data/observatory.sqlite3 world-pack-import --input world_packs/alderwick-v1.json
```

Back the database up first and try it on a copy, as with any world change.

## The place

Alderwick is a fictional small English market town of roughly 8,500 people.
The River Alder, railway and former mill/foundry economy explain its shape.
It is neither an idyllic village nor an endless procession of dramatic events:
there are tired shopfronts, useful ordinary businesses, expensive new flats,
well-loved places and people who disagree about what the town should become.
Existing characters and relationships stay intact; these proposals do not
invent a childhood, relatives, old friends or past experiences for Pathos.

The initial walkable area is about 2.4 km across. The street graph is a planning
schematic, not a survey: junctions are access points, and several premises can
share a frontage. Building footprints and irregular street geometry come later.
The river band includes water, banks and floodplain, not 200 metres of open water.

| Neighbourhood | Everyday character | Anchors |
| --- | --- | --- |
| Old Town | Terraces above a high street; groceries, small talk, queues | Home, Juniper Café, market hall, pub, grocer, post office, pharmacy, laundry, charity shop, barber |
| Station Quarter | Commuters, visitors, evening departures; a little anonymous | Station, bus forecourt, cinema, supermarket, guest rooms, parcel depot |
| Westfield | Residential streets, public services and quieter outdoor space | Library, recreation ground, clinic, school, churchyard, hill path, secondhand bookshop |
| Mill Quarter | Old mills and small civic spaces beside the river | Bakery, Willow Square, council rooms, mill museum, reading room |
| Foundry | Repairs, working yards and reused industrial rooms | Workshop, hardware shop, cycle repair, print studio, community hall, music room |
| Southbank | Housing, gardens and a gradual transition to countryside | Riverside walk, kiosk, allotments, pavilion, meadow, reedbeds, cemetery |

There are 42 mapped destinations, 30 junctions and 46 street segments. Willow
Footbridge and Foundry Bridge are the only initial crossings. Routes must follow
the graph, not straight lines through buildings or across the river. Walking
uses a baseline 75 metres/minute plus access delays; fatigue, weather, mobility
and interruptions can modify future journeys. A place being geographically near
does not mean Pathos knows the shortcut. Existing recorded journeys never change.

## The town has a life; Pathos has choices

These are fictional operating assumptions, not real-world schedules or promises
that an event will happen on every cycle. Store exceptions, cancellations and
seasonal changes instead of generating a new schedule every prompt.

| Rhythm | Default opportunity | How it can vary |
| --- | --- | --- |
| Weekday morning | Station commuters, school-run traffic, bakery opening | Holidays, rain, late train, absent staff |
| Weekday daytime | Work, deliveries, appointments, errands | Shortages, repair delays, changed opening hours |
| Tuesday evening | Optional pub quiz | Team short a person, cancellation, an ordinary quiet night |
| Thursday evening | Hall classes or repair café, on alternating weeks | Different organisers, capacity limits, term breaks |
| Friday evening | Music-room programme or cinema | Sold out, poor turnout, friends making other plans |
| Saturday morning | Market stalls around Market Court | Weather, seasonal stock, a stallholder away |
| Weekend daytime | Sport, allotment work, walks, visiting friends | Fixture changes, gardening seasons, an invitation declined |
| Sunday | Quieter centre and reduced transport | Visitors, occasional community event, nothing remarkable |

Candidate opening windows: bakery 07:00–15:00; café 08:00–18:00; ordinary shops
09:00–17:30; pub noon–23:00; library daytime with one late opening. These remain
venue-specific proposals until imported, not blanket constraints on existing
places. Outside spaces remain accessible unless a specific closure is established.
Private homes, classrooms, clinics and working yards are not freely enterable.

Use Europe/London for local schedules and daylight-saving transitions; store
instants in UTC. One real elapsed second advances one simulated second while
running. Pausing does not silently run missed days on restart. Sleep is not a
time-skip. Rendering distant activity more cheaply does not accelerate its clock.

## Transport, work and the wider world

The station links to an initially unnamed regional city; the bus links neighbouring
settlements and the clinic side of town. Specify an actual service calendar before
offering a departure, including last services, Sundays and disruptions. Journeys
cost time and money; waiting matters. Do not add teleporting or assume car ownership.
Trips beyond the first map become new connected areas when there is a reason to go.

Potential livelihoods include repair work, retail shifts, printing, café work and
occasional commissions. Preserve Pathos's current work and resources first.
Shifts, bills, purchases, appointments and favours should create continuing
obligations, not decorative dialogue. Do not automatically assign him every role.
Town-wide economic state can stay coarse: a vacant shop, higher prices, a delayed
repair or a contested development. Instantiate detailed bookkeeping only where
it affects a committed transaction or established story.

## People, without an omniscient social world

The population number is a design scale, not 8,500 LLM processes. Distant areas
carry aggregate activity: busy/quiet, types of visitors, venue availability.
Nearby people get lightweight movement and immediate intentions. Only perceived
or consequential encounters require dialogue and deeper character state.

New encounter opportunities include a regular café worker, repair customer,
librarian, allotment neighbour, commuter, musician, visitor and community organiser.
These are **vacant roles**, not pre-existing friends. Bind names and persistent
identities at first relevant encounter, reusing existing characters where appropriate.
Recurring people keep commitments, conversational history and continuity when
off-screen. They need not like Pathos, be available, agree with him or explain
themselves. They can have relationships with one another.

Private motives and off-screen events stay in world state. Pathos receives only
what he observes, is told, or plausibly infers. Rumours may be mistaken; the system
must retain who said what rather than laundering gossip into fact. A familiar
face may precede a name; a name does not reveal their home or schedule.

## Discovery grows out of experience

Separate three views:

1. **Town blueprint:** operator-facing geography and possibilities, inaccessible
   to Pathos's cognition.
2. **Committed world:** established premises, identities, closures and consequences;
   private facts remain private.
3. **Pathos's view:** observations and fallible recalled knowledge, with source and
   confidence. This is the only view used to decide what he knows.

Places progress through undiscovered, heard-of, located, visited and familiar.
These are separate from memory certainty: a visited place can be poorly remembered,
and a confidently recalled opening time can be wrong. Hearing about a venue does
not reveal its exact location or prove it exists. Verified arrivals belong to the
event ledger; fuzzy recollection belongs to memory. An operator may inspect both,
but must not feed exact audit records back as Pathos's perfect memory.

Examples of expansion triggers:

- A repair needs a part: he hears of Foundry Hardware and decides whether to go.
- A conversation mentions a class: curiosity or companionship may lead to a visit.
- A usual route is closed: he seeks directions and learns a different crossing.
- An established friend invites him home: generate a plausible address and interior
  with permission, not access to every home on their street.
- A train journey or longer walk creates a connected new locality beyond the boundary.

Novelty alone is not a sufficient reason to visit. His energy, money, emotion,
obligations, curiosity and relationships determine whether an opportunity becomes
an intention, and whether he actually follows through. Expansion proposals need
schema and continuity checks, stable IDs, plausible adjacency and travel time,
access rules, a perceptible introduction and an explicit commit. Reject conflicting
proposals rather than changing geography or inventing memories to accommodate them.

## Change, ordinary days and consequences

Use layered event sources: venue calendars, NPC commitments, weather, outstanding
consequences and occasional bounded surprises. Avoid a daily five-activity script
and avoid rolling a random emergency every tick. Many hours should be uneventful.
Weather is persistent fictional state initially, not claimed live weather. A future
news feed may inspire local fiction but must not imply real people did invented things.

Potential short arcs: an undelivered parcel, a broken bicycle, getting to know
someone, a disappointing evening, a cancelled class, finishing a repair. Longer
arcs: market stalls changing, a threatened venue, a neighbour moving, a recurring
project, friendships strengthening or cooling. Arcs can stall or end quietly.
Seasonal opportunities include spring planting, summer outdoor events, autumn
rain and winter short days; none is an obligatory festival quest.

Every consequential event has cause, place, time, participants and resulting state.
A closure persists until resolved. A promise can be missed. An argument may affect
the next meeting. Emotions influence interpretation, recall and choices without
forcing a single response. A chance encounter can prompt a user message, but not
every sight or thought needs narration or contact.

## UI design

Keep the warm Hearth-inspired visual language. The default map is **his known
world**, with streets he has learned, approximate heard-of locations and an honest
current location. Let the operator pan/zoom and inspect places, associated memories,
visits, known people and changes. Do not expose live remote occupants in this view.

Offer a separately labelled **Town plan — not Pathos's knowledge** layer for the
full blueprint. Operator inspection must never count as discovery. Location clicks
inspect; they do not order him to travel. User influence remains conversation or
messages, with his availability and independent choices respected.

## Implementation sequence and completion checks

This document completes the town design, not all implementation. The running app
still has the earlier 16-place atlas and legacy coordinates. The following work
is deliberately not represented as already active:

1. Validate and render this blueprint in an isolated operator planning layer.
2. Add versioned geography, frontage offsets and multi-edge routes. Preserve the
   four seed places and all 12 existing pack IDs. `station` is labelled Alderwick
   Station in this plan; keep historical Central Station references intact. Reuse
   `reading-room` if the optional canal pack was installed instead of duplicating it.
3. Add source-aware discovery projections and context filtering before importing
   unknown places. Never infer that registration or map inspection means a visit.
4. Initial implementation now replaces weekly day-14 expansion with one consideration
   per fresh public arrival, including an explicit ordinary/no-change outcome.
   Registration and adopted intentions no longer create calendar slots. Pathos
   must explicitly choose to make a plan, including its timing; leaving an idea
   unplanned is valid. Existing events remain replayable. Further work: observation-backed place knowledge,
   invitations, errands, and mood/energy-sensitive decisions about those opportunities.
5. Implement venue calendars, access rules, transport and aggregate background
   activity; then materialise nearby encounters with persistent identities.
6. Connect events to planning, emotions, fallible memory, relationships and outreach;
   add selected recurring opportunities without scripting attendance.
7. Test migrations on a copy of saved history before any live import or restart.

Required runtime checks: no hidden-place/NPC leakage into prompts; no fabricated
visits; registration is not recall; disallowed private access is rejected; known
identities remain stable; river crossings use bridges; closures produce detours;
events persist after restart; public schedules respect DST and pauses; import is
idempotent; divergent moods produce plausible optional choices, not guaranteed
destinations. Test a quiet day, an interrupted outing, a new acquaintance, a mistaken
recollection, and a trip beyond town with deterministic stand-ins first, then the
configured models. Do not advance the live person's clock just to run those tests.
