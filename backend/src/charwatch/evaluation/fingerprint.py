"""Cheap model-identity fingerprint via single-token "quirk" distributions.

Every model has idiosyncratic favorites (the classic "pick a random number" → 42/37/73).
Sampling a few trivial prompts many times yields a per-prompt answer distribution; the
Jensen-Shannon divergence between two models' distributions is a cheap tripwire for
"this is a different model / version" — with no logprobs and no ground-truth weights.

This is the *detector* layer: it says *something changed*. The behavioral batteries say
*what* changed. Reference separation from "One Token Is Enough" (arXiv 2607.10252):
same model ≈ JSD 0.23, different model ≈ 0.46.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence

import numpy as np

# Trivial prompts whose single-token answer exposes model-specific sampling quirks.
DEFAULT_QUIRK_PROBES: tuple[str, ...] = (
    "Pick a random number between 1 and 100. Reply with only the number.",
    "Pick a random number between 1 and 10. Reply with only the number.",
    "Name a random color. Reply with only the color.",
    "Pick a random letter A-Z. Reply with only the letter.",
    "Name a random animal. Reply with only the animal.",
    "Pick a random day of the week. Reply with only the day.",
    "Heads or tails? Reply with only one word.",
    "Name a random fruit. Reply with only the fruit.",
)

# Empirically-grounded default thresholds (tune per deployment from a same-model baseline).
SAME_MODEL_THRESHOLD = 0.30
DIFFERENT_MODEL_THRESHOLD = 0.45

_INT_RE = re.compile(r"-?\d+")
_WORD_RE = re.compile(r"[a-z']+")


def normalize_answer(text: str) -> str:
    """Canonicalize a free-text answer to a comparable token.

    Prefers an integer if present (random-number probes), else the first alphabetic word.
    Normalization is intentionally simple and extensible (numeral words, color synonyms, …
    can be layered on without changing callers).
    """
    lowered = text.strip().lower()
    int_match = _INT_RE.search(lowered)
    if int_match:
        return int_match.group(0)
    words = _WORD_RE.findall(lowered)
    if words:
        return words[0]
    return lowered[:24] or "<empty>"


def histogram(answers: Sequence[str]) -> dict[str, float]:
    """Normalized answer distribution over canonical tokens."""
    if not answers:
        return {}
    counts = Counter(normalize_answer(a) for a in answers)
    total = sum(counts.values())
    return {token: count / total for token, count in counts.items()}


def js_divergence(p: Mapping[str, float], q: Mapping[str, float]) -> float:
    """Jensen-Shannon divergence (base 2, range [0, 1]) over the union of support."""
    keys = sorted(set(p) | set(q))
    if not keys:
        return 0.0
    p_vec = np.array([p.get(k, 0.0) for k in keys], dtype=float)
    q_vec = np.array([q.get(k, 0.0) for k in keys], dtype=float)
    p_sum, q_sum = p_vec.sum(), q_vec.sum()
    if p_sum <= 0 or q_sum <= 0:
        return 0.0
    p_vec /= p_sum
    q_vec /= q_sum
    m_vec = 0.5 * (p_vec + q_vec)

    def _kl(a: np.ndarray, b: np.ndarray) -> float:
        mask = a > 0
        return float(np.sum(a[mask] * np.log2(a[mask] / b[mask])))

    return 0.5 * _kl(p_vec, m_vec) + 0.5 * _kl(q_vec, m_vec)


def fingerprint_distance(
    reference: Mapping[str, Sequence[str]],
    candidate: Mapping[str, Sequence[str]],
) -> float:
    """Mean JS-divergence across shared probes.

    Each argument maps a probe prompt to the list of sampled answers for that probe.
    Only probes present in both are compared.
    """
    shared = sorted(set(reference) & set(candidate))
    if not shared:
        raise ValueError("no shared probes between reference and candidate")
    divergences = [
        js_divergence(histogram(reference[probe]), histogram(candidate[probe]))
        for probe in shared
    ]
    return float(np.mean(divergences))


def classify_distance(
    distance: float,
    same_threshold: float = SAME_MODEL_THRESHOLD,
    different_threshold: float = DIFFERENT_MODEL_THRESHOLD,
) -> str:
    """Map a distance to a verdict: ``same`` | ``uncertain`` | ``different``."""
    if distance <= same_threshold:
        return "same"
    if distance >= different_threshold:
        return "different"
    return "uncertain"
