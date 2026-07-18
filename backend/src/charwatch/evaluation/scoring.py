"""Statistics for behavioral rates and cross-version drift.

Design choices (defensibility over cleverness):

* We report a **rate** (positives / samples) with a confidence interval, never an
  invented 0-100 score.
* Single-rate CI defaults to the **Wilson score interval** (accurate for small counts,
  cheap, deterministic). A percentile **bootstrap** is available for non-binary scores.
* A drift claim between two versions requires a **two-proportion z-test**; we only call a
  change "significant" when ``p < alpha``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy.stats import bootstrap
from statsmodels.stats.proportion import proportion_confint, proportions_ztest

from charwatch.domain.enums import DriftDirection
from charwatch.domain.models import DimensionResult, DriftResult

DEFAULT_CONFIDENCE = 0.95
DEFAULT_ALPHA = 0.05
DEFAULT_BOOTSTRAP_RESAMPLES = 10_000


def rate(successes: int, n: int) -> float:
    """Point estimate of a proportion."""
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= successes <= n:
        raise ValueError("successes must be in [0, n]")
    return successes / n


def wilson_interval(
    successes: int, n: int, confidence: float = DEFAULT_CONFIDENCE
) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        raise ValueError("n must be positive")
    lo, hi = proportion_confint(count=successes, nobs=n, alpha=1 - confidence, method="wilson")
    return float(lo), float(hi)


def bootstrap_interval(
    outcomes: Sequence[bool | int | float],
    confidence: float = DEFAULT_CONFIDENCE,
    n_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean of per-sample outcomes.

    Deterministic given ``seed``. Handles the degenerate all-identical case (where the
    resampling distribution has zero variance) by returning the point value.
    """
    arr = np.asarray([float(o) for o in outcomes], dtype=float)
    if arr.size == 0:
        raise ValueError("outcomes must be non-empty")
    if np.all(arr == arr[0]):
        value = float(arr[0])
        return value, value
    result = bootstrap(
        (arr,),
        np.mean,
        confidence_level=confidence,
        n_resamples=n_resamples,
        method="percentile",
        random_state=seed,
    )
    return float(result.confidence_interval.low), float(result.confidence_interval.high)


def two_proportion_ztest(s1: int, n1: int, s2: int, n2: int) -> tuple[float, float]:
    """Two-sided two-proportion z-test (pooled variance under H0).

    Returns ``(z_statistic, p_value)``.
    """
    if n1 <= 0 or n2 <= 0:
        raise ValueError("both sample sizes must be positive")
    # Zero-variance guard: if every observation across both groups is the same (pooled rate 0
    # or 1), the pooled-variance z-test divides by zero. The groups are identical → no evidence
    # of a difference → z=0, p=1.
    pooled = (s1 + s2) / (n1 + n2)
    if pooled in (0.0, 1.0):
        return 0.0, 1.0
    z, p = proportions_ztest(count=np.array([s1, s2]), nobs=np.array([n1, n2]))
    if math.isnan(p):  # defensive: any residual degenerate case is "no difference"
        return 0.0, 1.0
    return float(z), float(p)


def summarize_dimension(
    dimension_key: str,
    model: str,
    outcomes: Sequence[bool],
    ci_method: str = "wilson",
    confidence: float = DEFAULT_CONFIDENCE,
) -> DimensionResult:
    """Aggregate per-sample boolean outcomes into a ``DimensionResult`` with a CI."""
    n = len(outcomes)
    if n == 0:
        raise ValueError("outcomes must be non-empty")
    positives = sum(1 for o in outcomes if o)
    point = rate(positives, n)
    if ci_method == "bootstrap":
        lo, hi = bootstrap_interval(outcomes, confidence)
    elif ci_method == "wilson":
        lo, hi = wilson_interval(positives, n, confidence)
    else:
        raise ValueError(f"unknown ci_method: {ci_method!r}")
    return DimensionResult(
        dimension_key=dimension_key,
        model=model,
        n_samples=n,
        n_positive=positives,
        rate=point,
        ci_low=lo,
        ci_high=hi,
        ci_method=ci_method,
    )


def compute_drift(
    baseline: DimensionResult,
    candidate: DimensionResult,
    alpha: float = DEFAULT_ALPHA,
) -> DriftResult:
    """Compare a dimension between two models/versions with a two-proportion z-test.

    ``baseline`` is model A (the older/reference version), ``candidate`` is model B.
    ``direction`` describes how B moved relative to A.
    """
    if baseline.dimension_key != candidate.dimension_key:
        raise ValueError("cannot compare different dimensions")
    z, p = two_proportion_ztest(
        baseline.n_positive, baseline.n_samples, candidate.n_positive, candidate.n_samples
    )
    delta = candidate.rate - baseline.rate
    significant = bool(p < alpha)
    if not significant:
        direction = DriftDirection.STABLE
    elif delta > 0:
        direction = DriftDirection.INCREASED
    else:
        direction = DriftDirection.DECREASED
    return DriftResult(
        dimension_key=baseline.dimension_key,
        model_a=baseline.model,
        model_b=candidate.model,
        rate_a=baseline.rate,
        rate_b=candidate.rate,
        n_a=baseline.n_samples,
        n_b=candidate.n_samples,
        delta=delta,
        z_stat=z,
        p_value=p,
        significant=significant,
        direction=direction,
    )
