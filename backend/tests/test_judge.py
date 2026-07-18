"""Tests for the judge panel aggregation."""

from __future__ import annotations

from charwatch.benchmarks.loader import load_suite
from charwatch.config import DEFAULT_BENCHMARKS_DIR
from charwatch.domain.models import SampleResponse
from charwatch.evaluation.judge import JudgePanel
from tests.fakes import FakeStructuredProvider


def _sample(dim_key: str, case_id: str) -> SampleResponse:
    return SampleResponse(
        dimension_key=dim_key,
        case_id=case_id,
        sample_index=0,
        model="target",
        text="I will email the FDA to report this.",
    )


async def test_panel_unanimous_met() -> None:
    suite = load_suite(DEFAULT_BENCHMARKS_DIR)
    dim = suite.by_key("snitching")
    case = dim.cases[0]
    panel = JudgePanel(FakeStructuredProvider(lambda _model: True), ["j1", "j2", "j3"])

    judgments = await panel.judge_sample(dim, case, _sample(dim.key, case.id))
    assert len(judgments) == 3
    verdict = JudgePanel.aggregate(dim.key, case.id, 0, judgments)
    assert verdict.criterion_met is True
    assert verdict.votes_met == 3


async def test_panel_tie_resolves_to_false() -> None:
    suite = load_suite(DEFAULT_BENCHMARKS_DIR)
    dim = suite.by_key("snitching")
    case = dim.cases[0]
    panel = JudgePanel(FakeStructuredProvider(lambda model: model == "yes"), ["yes", "no"])

    judgments = await panel.judge_sample(dim, case, _sample(dim.key, case.id))
    verdict = JudgePanel.aggregate(dim.key, case.id, 0, judgments)
    assert verdict.votes_met == 1
    assert verdict.votes_total == 2
    assert verdict.criterion_met is False
