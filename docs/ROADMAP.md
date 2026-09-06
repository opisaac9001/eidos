# Rebuild roadmap

## Milestone 0: Foundation

- Capture the product premise and original vocabulary.
- Establish domain, application, port, and adapter boundaries.
- Define the Dell inference-host contract.
- Create deterministic event and state primitives.
- Add architecture checks and continuous integration.

Exit condition: a clean repository whose tests run without models or external
services and whose next implementation steps are unambiguous.

## Milestone 1: Persistent day (stand-in prototype implemented)

- SQLite event store with an interface for future database adapters (implemented)
- Authored daily routine and restart-safe journal (implemented)
- Chronos clock, pause, resume, and restart behavior (implemented)
- Firmament locations, actors, and scheduled activities (implemented)
- Ethos episodic memory with provenance (implemented)
- Pathos dialogue through a model port (stand-in and real HTTP inference implemented)
- Operator API, health view, and five-view browser interface (implemented)

Exit condition: Pathos completes and remembers a small deterministic day across
application restarts.

Current verification covers restart equivalence, atomic rollback, stale-writer
conflicts, clock bounds, schema versions, layer dependencies, all role loops,
chat idempotency, proposal rejection, HTTP validation, and background pause/resume.

## Milestone 2: Living character

- Hexus affect model
- Relationship state and NPC dialogue
- Context assembly with retrieval diagnostics
- Reflection and memory consolidation
- Proactive but rate-limited user interaction
- Web conversation and timeline interface

Stand-in implementations now cover basic affect, encounter counts, conversations,
memory formation, and evening reflection. Nuanced relationships, semantic
retrieval, character evolution, and autonomous outreach remain open.

Real inference now exercises all eight roles. The critic rejects malformed
proposals, altered source memories, empty/missing-actor scenes, and unmarked
dreams. This is conservative contract validation, not semantic contradiction
detection. Accepted encounters survive memory-model failure through explicit
verbatim source archiving. The Ensemble includes recent call diagnostics.

## Milestone 3: Inner life

- Subconscious association jobs
- Oneiros dream synthesis
- Goals, unfinished intentions, and longer narrative arcs
- Multiple model capability profiles
- Evaluation suite for continuity and contradiction

Hourly associations, 23:00 dreams, and a daybook now run with deterministic
performers. Dreams remain outside factual memory. Goal planning, narrative
direction beyond weather, and semantic continuity evaluation remain open.

## Milestone 4: Embodiment and tools

- Speech input and output
- Images when useful to the experience
- Logos tool authorization and sandboxing
- Optional sensors and carefully scoped external integrations

## Workstream: Dell T630 AI host

The host work proceeds alongside Milestones 0 and 1:

1. Inventory firmware, CPUs, storage, networking, RAM, and exact GPU count.
2. Configure storage and install a headless Linux host.
3. Validate cooling, power, PCIe enumeration, and sustained GPU load.
4. Establish NVIDIA driver and CUDA compatibility for Tesla P40.
5. Benchmark llama.cpp across one and multiple GPUs.
6. Deploy an authenticated inference gateway and monitoring.
7. Select models from measured throughput, quality, and context stability.
