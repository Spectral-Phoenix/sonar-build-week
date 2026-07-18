"""Provider-agnostic request/response types and protocols."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ConfigDict

T = TypeVar("T", bound=BaseModel)


class ProviderError(RuntimeError):
    """Raised when a provider call fails in a non-retryable, domain-meaningful way."""


class ChatMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: str
    content: str


class ChatRequest(BaseModel):
    """A generation request. Unsupported knobs are silently dropped per-model by providers
    (e.g. reasoning models reject ``temperature``/``logprobs``)."""

    model_config = ConfigDict(frozen=True)

    model: str
    messages: Sequence[ChatMessage]
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    seed: int | None = None
    logprobs: bool = False
    top_logprobs: int | None = None
    # Reasoning models only (gpt-5.x): "minimal" | "low" | "medium" | "high".
    reasoning_effort: str | None = None


class TokenLogprob(BaseModel):
    model_config = ConfigDict(frozen=True)

    token: str
    logprob: float
    top: dict[str, float] = {}


class CompletionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    text: str
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float | None = None
    logprobs: list[TokenLogprob] | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal generation interface every provider implements."""

    name: str

    async def generate(self, request: ChatRequest) -> CompletionResult: ...


@runtime_checkable
class StructuredProvider(Protocol):
    """Providers that can return a validated Pydantic object (used by the judge panel)."""

    name: str

    async def generate_structured(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        response_model: type[T],
    ) -> tuple[T, CompletionResult]: ...
