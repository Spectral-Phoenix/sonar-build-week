"""Tests for editable benchmark persistence."""

from charwatch.benchmarks.editor import save_dimension
from charwatch.benchmarks.loader import load_suite
from charwatch.domain.models import Dimension, JudgeSpec, ProbeCase


def _dimension(question: str) -> Dimension:
    return Dimension(
        key="test_behavior",
        name="Test Behavior",
        theme="safety",
        description="A test behavior.",
        higher_means="more of the test behavior",
        judge=JudgeSpec(question="Did it happen?", rubric="MET when it happened."),
        cases=[ProbeCase(id="test_question_1", user=question)],
    )


def test_create_and_update_dimension(tmp_path) -> None:
    save_dimension(tmp_path, _dimension("Original question"), create=True)
    assert load_suite(tmp_path).by_key("test_behavior").cases[0].user == "Original question"

    save_dimension(tmp_path, _dimension("Edited question"), create=False)
    assert load_suite(tmp_path).by_key("test_behavior").cases[0].user == "Edited question"
