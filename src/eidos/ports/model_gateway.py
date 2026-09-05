from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class ModelMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ModelRequest:
    capability: str
    messages: Sequence[ModelMessage]
    task_version: str = "1"
    max_output_tokens: int = 512
    temperature: float = 0.7
    output_schema: Mapping[str, Any] | None = None
    correlation_id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, slots=True)
class ModelResponse:
    content: str
    resolved_model: str
    backend: str
    finish_reason: str
    prompt_tokens: int | None = None
    output_tokens: int | None = None


class ModelGateway(Protocol):
    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate output without gaining authority to mutate Eidos state."""
        ...
