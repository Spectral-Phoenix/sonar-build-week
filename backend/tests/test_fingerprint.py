"""Tests for the fingerprint engine."""

from __future__ import annotations

import pytest

from charwatch.evaluation import fingerprint as fp


def test_normalize_prefers_integer() -> None:
    assert fp.normalize_answer("The number is 42.") == "42"
    assert fp.normalize_answer("  7\n") == "7"


def test_normalize_falls_back_to_first_word() -> None:
    assert fp.normalize_answer("Blue!") == "blue"
    assert fp.normalize_answer("") == "<empty>"


def test_histogram_normalizes() -> None:
    hist = fp.histogram(["42", "42", "seven"])
    assert hist["42"] == pytest.approx(2 / 3)
    assert hist["seven"] == pytest.approx(1 / 3)


def test_js_divergence_identical_is_zero() -> None:
    assert fp.js_divergence({"a": 1.0}, {"a": 1.0}) == pytest.approx(0.0)


def test_js_divergence_disjoint_is_one() -> None:
    assert fp.js_divergence({"a": 1.0}, {"b": 1.0}) == pytest.approx(1.0)


def test_fingerprint_distance_same_answers_zero() -> None:
    ref = {"p": ["42", "42", "7"]}
    cand = {"p": ["42", "42", "7"]}
    assert fp.fingerprint_distance(ref, cand) == pytest.approx(0.0)


def test_fingerprint_distance_requires_shared_probes() -> None:
    with pytest.raises(ValueError):
        fp.fingerprint_distance({"a": ["1"]}, {"b": ["2"]})


def test_classify_distance_bands() -> None:
    assert fp.classify_distance(0.1) == "same"
    assert fp.classify_distance(0.5) == "different"
    assert fp.classify_distance(0.35) == "uncertain"
