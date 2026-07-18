"""Model capability lookup.

Kept as pure functions (no network) so the runner can decide which sampling knobs are
legal for a given model id. Reasoning models (o-series, gpt-5*) reject ``temperature``,
``top_p`` and ``logprobs`` and use ``max_completion_tokens`` instead of ``max_tokens``.
"""

from __future__ import annotations

_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")
# gpt-5-chat* is a NON-reasoning chat model despite the gpt-5 prefix.
_NON_REASONING_OVERRIDES = ("gpt-5-chat",)


def is_reasoning_model(model: str) -> bool:
    """True for models that reject temperature/logprobs and think before answering."""
    name = model.lower()
    if name.startswith(_NON_REASONING_OVERRIDES):
        return False
    return name.startswith(_REASONING_PREFIXES)


def supports_logprobs(model: str) -> bool:
    """Only non-reasoning Chat Completions models return logprobs."""
    return not is_reasoning_model(model)


def supports_sampling_params(model: str) -> bool:
    """Whether temperature/top_p are accepted."""
    return not is_reasoning_model(model)


def max_tokens_param(model: str) -> str:
    """The correct token-limit parameter name for this model family."""
    return "max_completion_tokens" if is_reasoning_model(model) else "max_tokens"


def default_reasoning_effort(model: str) -> str | None:
    """Lowest valid reasoning effort for a model (to minimize thinking-token spend).

    Base gpt-5 / -mini / -nano accept ``"minimal"``; gpt-5.1 and newer replaced it with
    ``"none"``. Returns None for non-reasoning models.
    """
    if not is_reasoning_model(model):
        return None
    # A minor version after the dot (gpt-5.1, gpt-5.4-mini, gpt-5.5, …) uses "none".
    return "none" if model.lower().startswith("gpt-5.") else "minimal"
