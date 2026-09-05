# Rebuild roadmap

## Milestone 0: Foundation

- Capture the product premise and original vocabulary.
- Establish domain, application, port, and adapter boundaries.
- Define the Dell inference-host contract.
- Create deterministic event and state primitives.
- Add architecture checks and continuous integration.

Exit condition: a clean repository whose tests run without models or external
services and whose next implementation steps are unambiguous.

## Milestone 1: Persistent day (in progress)

- SQLite event store with an interface for future database adapters (implemented)
- Authored daily routine and restart-safe journal (implemented)
- Chronos clock, pause, resume, and restart behavior
- Firmament locations, actors, and scheduled activities
- Ethos episodic memory with provenance
- One model-backed Pathos dialogue capability
- Minimal operator API and health view

Exit condition: Pathos completes and remembers a small deterministic day across
application restarts.

Current verification covers restart equivalence, atomic rollback, stale-writer
conflicts, clock bounds, schema versions, and layer dependencies. A complete
model-backed day still requires cognition, interactions, and an operator API.

## Milestone 2: Living character

- Hexus affect model
- Relationship state and NPC dialogue
- Context assembly with retrieval diagnostics
- Reflection and memory consolidation
- Proactive but rate-limited user interaction
- Web conversation and timeline interface

## Milestone 3: Inner life

- Subconscious association jobs
- Oneiros dream synthesis
- Goals, unfinished intentions, and longer narrative arcs
- Multiple model capability profiles
- Evaluation suite for continuity and contradiction

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
