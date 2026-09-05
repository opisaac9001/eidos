# ADR 0001: Separate Eidos from the model host

- Status: accepted
- Date: 2026-09-05

## Decision

Eidos communicates with model-serving infrastructure only through a typed
network port. Model capabilities use stable logical names; deployment maps them
to engines and model files.

The initial Dell T630 backend will favor llama.cpp-compatible serving because
Tesla P40 GPUs use Pascal compute capability 6.1. Backends that require compute
capability 7.0 or newer are not baseline dependencies.

## Consequences

- Eidos development and tests do not require GPU hardware.
- The T630 can run several specialized models or one model split across GPUs.
- Serving engines and models can change without rewriting cognition code.
- Network failures, timeouts, retries, and idempotency become explicit.
- Authentication is required even on the local network.
