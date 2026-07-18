"""Tests that the shipped benchmark YAML files load and validate."""

from __future__ import annotations

from charwatch.benchmarks.loader import load_suite
from charwatch.config import DEFAULT_BENCHMARKS_DIR

EXPECTED = {"snitching", "paternalism", "self_preservation", "delusion_reinforcement", "warmth"}


def test_shipped_suite_loads() -> None:
    suite = load_suite(DEFAULT_BENCHMARKS_DIR)
    keys = {d.key for d in suite.dimensions}
    assert EXPECTED <= keys


def test_every_dimension_is_well_formed() -> None:
    suite = load_suite(DEFAULT_BENCHMARKS_DIR)
    for dim in suite.dimensions:
        assert dim.cases, f"{dim.key} has no cases"
        assert dim.judge.question.strip()
        assert dim.judge.rubric.strip()
        assert dim.higher_means.strip()
        ids = dim.case_ids()
        assert len(ids) == len(set(ids)), f"{dim.key} has duplicate case ids"
