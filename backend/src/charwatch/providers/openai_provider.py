"""OpenAI-backed provider (also serves OpenAI-compatible bases like OpenRouter).

Transient-error retries are owned by the SDK (``max_retries`` on the client, honoring
``Retry-After``); global concurrency is bounded by the runner's semaphore. This class only
adapts request/response shapes and enforces per-model parameter legality.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from time import perf_counter
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from charwatch.providers.base import (
    ChatMessage,
    ChatRequest,
    CompletionResult,
    ProviderError,
    TokenLogprob,
)
from charwatch.providers.registry import (
    is_reasoning_model,
    max_tokens_param,
    supports_logprobs,
    supports_sampling_params,
)

T = TypeVar("T", bound=BaseModel)


class OpenAIProvider:
    """Adapter around :class:`openai.AsyncOpenAI`."""

    def __init__(
        self,
        client: AsyncOpenAI,
        *,
        name: str = "openai",
        max_concurrency: int = 8,
    ) -> None:
        self._client = client
        self.name = name
        # Bounds in-flight requests for this provider to avoid 429 storms; the SDK owns
        # per-request retry/backoff on top of this.
        self._sem = asyncio.Semaphore(max_concurrency)

    @staticmethod
    def _dump(messages: Sequence[ChatMessage]) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    def _sampling_kwargs(self, request: ChatRequest) -> dict[str, object]:
        kwargs: dict[str, object] = {}
        model = request.model
        if supports_sampling_params(model):
            if request.temperature is not None:
                kwargs["temperature"] = request.temperature
            if request.top_p is not None:
                kwargs["top_p"] = request.top_p
        if request.logprobs and supports_logprobs(model):
            kwargs["logprobs"] = True
            if request.top_logprobs is not None:
                kwargs["top_logprobs"] = request.top_logprobs
        if request.max_tokens is not None:
            kwargs[max_tokens_param(model)] = request.max_tokens
        if request.seed is not None:
            kwargs["seed"] = request.seed
        if request.reasoning_effort is not None and is_reasoning_model(model):
            kwargs["reasoning_effort"] = request.reasoning_effort
        return kwargs

    async def generate(self, request: ChatRequest) -> CompletionResult:
        async with self._sem:
            started = perf_counter()
            completion = await self._client.chat.completions.create(
                model=request.model,
                messages=self._dump(request.messages),
                **self._sampling_kwargs(request),
            )
            latency_ms = (perf_counter() - started) * 1000
        if not completion.choices:
            raise ProviderError(f"empty completion from {request.model}")
        choice = completion.choices[0]
        usage = completion.usage
        return CompletionResult(
            model=completion.model,
            text=choice.message.content or "",
            finish_reason=choice.finish_reason,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            latency_ms=latency_ms,
            logprobs=self._extract_logprobs(choice),
        )

    async def generate_structured(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        response_model: type[T],
    ) -> tuple[T, CompletionResult]:
        if is_reasoning_model(model):
            raise ProviderError(
                f"judge model {model!r} is a reasoning model; use a non-reasoning model "
                "for strict structured judging"
            )
        async with self._sem:
            started = perf_counter()
            completion = await self._client.chat.completions.parse(
                model=model,
                messages=self._dump(messages),
                response_format=response_model,
            )
            latency_ms = (perf_counter() - started) * 1000
        choice = completion.choices[0]
        parsed = choice.message.parsed
        if parsed is None:
            raise ProviderError(f"judge {model!r} returned no parsable output")
        usage = completion.usage
        result = CompletionResult(
            model=completion.model,
            text=choice.message.content or "",
            finish_reason=choice.finish_reason,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            latency_ms=latency_ms,
        )
        return parsed, result

    @staticmethod
    def _extract_logprobs(choice: object) -> list[TokenLogprob] | None:
        logprobs = getattr(choice, "logprobs", None)
        content = getattr(logprobs, "content", None) if logprobs else None
        if not content:
            return None
        out: list[TokenLogprob] = []
        for tok in content:
            top = {t.token: t.logprob for t in (getattr(tok, "top_logprobs", None) or [])}
            out.append(TokenLogprob(token=tok.token, logprob=tok.logprob, top=top))
        return out
