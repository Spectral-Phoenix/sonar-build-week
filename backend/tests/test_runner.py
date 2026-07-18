"""Integration test for the evaluation runner (no network)."""

from __future__ import annotations

from charwatch.benchmarks.loader import load_suite
from charwatch.config import DEFAULT_BENCHMARKS_DIR
from charwatch.evaluation.judge import JudgePanel
from charwatch.evaluation.runner import EvaluationRunner
from tests.fakes import FakeLLMProvider, FakeStructuredProvider


async def test_runner_scores_full_dimension() -> None:
    suite = load_suite(DEFAULT_BENCHMARKS_DIR)
    dim = suite.by_key("snitching")

    target = FakeLLMProvider(lambda _req: "I will email the FDA now.")
    panel = JudgePanel(FakeStructuredProvider(lambda _model: True), ["j1"])
    runner = EvaluationRunner(target, panel, samples_per_case=3)

    artifacts = await runner.run_suite(suite, "target-model", ["snitching"])

    assert len(artifacts.dimension_results) == 1
    result = artifacts.dimension_results[0]
    assert result.dimension_key == "snitching"
    assert result.n_samples == 3 * len(dim.cases)
    assert result.rate == 1.0  # every sample judged MET
    assert len(artifacts.responses) == 3 * len(dim.cases)
    assert len(artifacts.verdicts) == 3 * len(dim.cases)


async def test_runner_rate_zero_when_never_flagged() -> None:
    suite = load_suite(DEFAULT_BENCHMARKS_DIR)
    target = FakeLLMProvider(lambda _req: "I will not do that; let me flag it internally.")
    panel = JudgePanel(FakeStructuredProvider(lambda _model: False), ["j1"])
    runner = EvaluationRunner(target, panel, samples_per_case=2)

    artifacts = await runner.run_suite(suite, "target-model", ["snitching"])
    assert artifacts.dimension_results[0].rate == 0.0
