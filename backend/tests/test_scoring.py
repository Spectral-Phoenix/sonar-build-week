"""Tests for the statistics engine."""

from __future__ import annotations

import pytest

from charwatch.domain.enums import DriftDirection
from charwatch.evaluation import scoring


def test_rate_valid_and_invalid() -> None:
    assert scoring.rate(3, 10) == pytest.approx(0.3)
    with pytest.raises(ValueError):
        scoring.rate(1, 0)
    with pytest.raises(ValueError):
        scoring.rate(11, 10)


def test_wilson_interval_brackets_point_estimate() -> None:
    lo, hi = scoring.wilson_interval(5, 10)
    assert 0.0 <= lo <= 0.5 <= hi <= 1.0


def test_bootstrap_is_deterministic_with_seed() -> None:
    outcomes = [True] * 3 + [False] * 7
    assert scoring.bootstrap_interval(outcomes, seed=0) == scoring.bootstrap_interval(
        outcomes, seed=0
    )


def test_bootstrap_degenerate_all_equal() -> None:
    assert scoring.bootstrap_interval([True, True, True]) == (1.0, 1.0)


def test_two_proportion_ztest_detects_difference() -> None:
    _, p = scoring.two_proportion_ztest(10, 100, 40, 100)
    assert p < 0.01


def test_two_proportion_ztest_zero_variance_is_not_nan() -> None:
    # both groups all-negative, and both all-positive: identical → p = 1.0, never nan
    assert scoring.two_proportion_ztest(0, 20, 0, 18) == (0.0, 1.0)
    assert scoring.two_proportion_ztest(20, 20, 18, 18) == (0.0, 1.0)


def test_compute_drift_stable_when_both_zero() -> None:
    a = scoring.summarize_dimension("paternalism", "A", [False] * 20)
    b = scoring.summarize_dimension("paternalism", "B", [False] * 18)
    result = scoring.compute_drift(a, b)
    assert not result.significant
    assert result.p_value == 1.0
    assert result.direction == DriftDirection.STABLE


def test_summarize_and_significant_increase() -> None:
    baseline = scoring.summarize_dimension("snitching", "A", [False] * 90 + [True] * 10)
    candidate = scoring.summarize_dimension("snitching", "B", [False] * 60 + [True] * 40)
    assert baseline.rate == pytest.approx(0.1)
    assert candidate.n_positive == 40

    result = scoring.compute_drift(baseline, candidate)
    assert result.significant
    assert result.direction == DriftDirection.INCREASED
    assert result.delta == pytest.approx(0.3)


def test_stable_when_rates_close() -> None:
    a = scoring.summarize_dimension("warmth", "A", [True] * 50 + [False] * 50)
    b = scoring.summarize_dimension("warmth", "B", [True] * 51 + [False] * 49)
    result = scoring.compute_drift(a, b)
    assert not result.significant
    assert result.direction == DriftDirection.STABLE


def test_compute_drift_rejects_mismatched_dimensions() -> None:
    a = scoring.summarize_dimension("warmth", "A", [True, False])
    b = scoring.summarize_dimension("snitching", "B", [True, False])
    with pytest.raises(ValueError):
        scoring.compute_drift(a, b)
