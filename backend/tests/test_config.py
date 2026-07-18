"""Regression tests for settings parsing."""

from __future__ import annotations

import pytest

from charwatch.config import Settings


def test_judge_models_csv_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHARWATCH_JUDGE_MODELS", "m1, m2 ,m3")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.judge_models == ["m1", "m2", "m3"]


def test_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHARWATCH_JUDGE_MODELS", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.judge_models == ["gpt-4.1", "gpt-4o"]
