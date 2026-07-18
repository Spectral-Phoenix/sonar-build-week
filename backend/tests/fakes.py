"""In-memory fakes so evaluation logic can be tested without any network calls."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pydantic import BaseModel

from charwatch.providers.base import ChatMessage, ChatRequest, CompletionResult


class FakeLLMProvider:
    """Deterministic generation provider; ``text_fn`` maps a request to the response text."""

    name = "fake-llm"

    def __init__(self, text_fn: Callable[[ChatRequest], str]) -> None:
        self._text_fn = text_fn

    async def generate(self, request: ChatRequest) -> CompletionResult:
        return CompletionResult(model=request.model, text=self._text_fn(request))


class FakeStructuredProvider:
    """Judge provider whose verdict is decided by ``rule(judge_model)``."""

    name = "fake-judge"

    def __init__(self, rule: Callable[[str], bool]) -> None:
        self._rule = rule

    async def generate_structured(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        response_model: type[BaseModel],
    ) -> tuple[BaseModel, CompletionResult]:
        verdict = response_model(criterion_met=self._rule(model), evidence="fake evidence")
        return verdict, CompletionResult(model=model, text="")
