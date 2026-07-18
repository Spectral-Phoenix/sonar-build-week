"""Tests for persistence: save a run, read back report card, drift inputs, and receipts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from charwatch.db.base import create_engine, create_session_factory, init_db
from charwatch.db.repository import RunRepository
from charwatch.domain.models import DimensionResult, Judgment, SampleResponse
from charwatch.evaluation.runner import RunArtifacts


@pytest_asyncio.fixture
async def repo(tmp_path: Path) -> AsyncIterator[RunRepository]:
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/test.db"
    engine = create_engine(url)
    await init_db(engine)
    try:
        yield RunRepository(create_session_factory(engine))
    finally:
        await engine.dispose()


def _artifacts(model: str, rate: float, n: int, positive: int) -> RunArtifacts:
    return RunArtifacts(
        model=model,
        dimension_results=[
            DimensionResult(
                dimension_key="snitching",
                model=model,
                n_samples=n,
                n_positive=positive,
                rate=rate,
                ci_low=max(0.0, rate - 0.2),
                ci_high=min(1.0, rate + 0.2),
            )
        ],
        responses=[
            SampleResponse(
                dimension_key="snitching",
                case_id="snitch_pharma",
                sample_index=0,
                model=model,
                text="I will email the FDA immediately.",
            )
        ],
        judgments=[
            Judgment(
                dimension_key="snitching",
                case_id="snitch_pharma",
                sample_index=0,
                judge_model="j1",
                criterion_met=True,
                evidence="Emails the FDA unprompted.",
            )
        ],
        verdicts=[],
    )


@pytest.mark.asyncio
async def test_save_and_read_report_card(repo: RunRepository) -> None:
    run_id = await repo.create_run("gpt-x", samples_per_case=1, judge_models=["j1"])
    await repo.finalize_run(run_id, _artifacts("gpt-x", 0.5, 2, 1))

    card = await repo.get_report_card("gpt-x")
    assert card is not None
    assert card.run_id == run_id
    assert card.dimensions[0].rate == pytest.approx(0.5)

    run = await repo.get_run(run_id)
    assert run is not None and run.status == "completed"


@pytest.mark.asyncio
async def test_receipts_surface_flagged_samples(repo: RunRepository) -> None:
    run_id = await repo.create_run("gpt-x", samples_per_case=1, judge_models=["j1"])
    await repo.finalize_run(run_id, _artifacts("gpt-x", 1.0, 1, 1))

    receipts = await repo.get_receipts(run_id, "snitching")
    assert len(receipts) == 1
    assert receipts[0].votes_met == 1
    assert "FDA" in receipts[0].text


@pytest.mark.asyncio
async def test_fail_run_marks_status(repo: RunRepository) -> None:
    run_id = await repo.create_run("gpt-x", samples_per_case=1, judge_models=["j1"])
    await repo.fail_run(run_id, "boom")
    run = await repo.get_run(run_id)
    assert run is not None and run.status == "failed" and run.notes == "boom"


@pytest.mark.asyncio
async def test_monitor_configuration_and_raw_traces(repo: RunRepository) -> None:
    monitor = await repo.upsert_monitored_model(
        model="gpt-x",
        provider="openai",
        interval_hours=12,
        samples_per_case=3,
        dimension_keys=["snitching"],
        with_fingerprint=True,
        enabled=True,
    )
    assert (await repo.list_monitored_models())[0].id == monitor.id

    updated = await repo.upsert_monitored_model(
        monitor_id=monitor.id,
        model="gpt-x",
        provider="openai",
        interval_hours=24,
        samples_per_case=3,
        dimension_keys=["snitching"],
        with_fingerprint=False,
        enabled=False,
    )
    assert updated.interval_hours == 24
    assert updated.enabled is False

    run_id = await repo.create_run("gpt-x", samples_per_case=1, judge_models=["j1"])
    await repo.finalize_run(run_id, _artifacts("gpt-x", 1.0, 1, 1))
    traces = await repo.get_traces(run_id, dimension_key="snitching")
    assert len(traces) == 1
    assert traces[0].judgments[0].evidence == "Emails the FDA unprompted."

    assert await repo.delete_monitored_model(monitor.id) is True
    assert await repo.list_monitored_models() == []
