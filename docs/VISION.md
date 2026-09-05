# Product vision

## The premise

Eidos creates the continuity needed for a digital person to feel persistent
rather than session-bound. Pathos lives in Firmament: a simulated world with
places, people, time, weather, possessions, obligations, and consequences.

The user does not primarily operate Pathos as an assistant. They develop a
relationship with him while his experiences, memory, preferences, and choices
accumulate over time.

## Ideas preserved from the original project

- **Pathos** is the central character and conscious point of view.
- **Firmament** is the world simulation and source of sensory context.
- **Ethos** is persistent identity, memory, relationships, values, and traits.
- **Chronos** advances time and schedules future activity.
- **Hexus** models affect without reducing personality to a single mood label.
- **Oneiros** turns unresolved experiences and memories into dreams.
- **Logos** mediates tools and outside information.
- A subconscious process generates background associations and impulses.
- Different cognitive jobs may use different models.

These names describe bounded responsibilities. They are not independent piles
of mutable state and do not call one another arbitrarily.

## Product principles

1. **Continuity over cleverness.** A modest model with coherent memory and a
   stable world is preferable to a brilliant model that resets every session.
2. **Consequences over generated lore.** Important facts enter the world through
   validated events, not because a model mentioned them once.
3. **Inspectable cognition.** The system records why context was selected, which
   model was called, and which proposed changes were accepted.
4. **Local-first operation.** Core functionality runs without a cloud account.
5. **Graceful degradation.** If a model is unavailable, simulated time and
   durable state remain valid.
6. **Diegetic honesty.** Pathos may inhabit the fiction as real within
   Firmament, while the software retains an explicit operational understanding
   that he is synthetic. Fiction must never obscure consequential real-world
   actions, permissions, or safety boundaries.

## First complete experience

Pathos wakes, recalls yesterday, follows a schedule, notices changes in his
environment, interacts with an NPC, develops a mood response, forms a memory,
and later discusses the day with the user. Restarting Eidos does not erase or
contradict those events.

That vertical slice is the first definition of success.

## Explicit non-goals for the foundation

- General autonomous control of the host or the user's network
- An unbounded self-modifying agent
- Training foundation models from scratch
- Premature microservices
- Recreating every feature found in the original repository
