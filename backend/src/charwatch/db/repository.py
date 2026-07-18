"""Repository: owns all database reads/writes. Services/routers never build SQL directly."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from charwatch.db.models import (
    DimensionResultRow,
    FingerprintRow,
    JudgmentRow,
    MonitoredModelRow,
    Run,
    SampleResponseRow,
)
from charwatch.domain.models import DimensionResult, ModelReportCard
from charwatch.evaluation.runner import RunArtifacts


@dataclass(slots=True)
class Receipt:
    """A flagged sample response plus the judge evidence — the 'damning transcript'."""

    dimension_key: str
    case_id: str
    sample_index: int
    model: str
    text: str
    votes_met: int
    votes_total: int
    evidence: list[str]


@dataclass(slots=True)
class HistoryPoint:
    created_at: datetime
    run_id: str
    result: DimensionResult


@dataclass(slots=True)
class MonitoredModel:
    id: str
    model: str
    provider: str
    interval_hours: int
    samples_per_case: int | None
    dimension_keys: list[str] | None
    with_fingerprint: bool
    enabled: bool
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class TraceJudgment:
    judge_model: str
    criterion_met: bool
    evidence: str


@dataclass(slots=True)
class TraceRecord:
    id: int
    run_id: str
    model: str
    dimension_key: str
    case_id: str
    sample_index: int
    text: str
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: float | None
    judgments: list[TraceJudgment]


def _row_to_result(row: DimensionResultRow) -> DimensionResult:
    return DimensionResult(
        dimension_key=row.dimension_key,
        model=row.model,
        n_samples=row.n_samples,
        n_positive=row.n_positive,
        rate=row.rate,
        ci_low=row.ci_low,
        ci_high=row.ci_high,
        ci_method=row.ci_method,
    )


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's timezone-naive datetime round trips to explicit UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _row_to_monitor(row: MonitoredModelRow) -> MonitoredModel:
    return MonitoredModel(
        id=row.id,
        model=row.model,
        provider=row.provider,
        interval_hours=row.interval_hours,
        samples_per_case=row.samples_per_case,
        dimension_keys=list(row.dimension_keys) if row.dimension_keys else None,
        with_fingerprint=row.with_fingerprint,
        enabled=row.enabled,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
    )


class RunRepository:
    """Persistence and queries for evaluation runs."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    # --- writes --------------------------------------------------------- #
    async def create_run(
        self,
        model: str,
        *,
        samples_per_case: int,
        judge_models: list[str],
        status: str = "running",
        notes: str | None = None,
    ) -> str:
        """Insert a run row up-front (status ``running``) so it can be polled while it executes."""
        run_id = uuid.uuid4().hex
        async with self._sf() as session, session.begin():
            session.add(
                Run(
                    id=run_id,
                    model=model,
                    status=status,
                    samples_per_case=samples_per_case,
                    judge_models=judge_models,
                    notes=notes,
                    created_at=datetime.now(UTC),
                )
            )
        return run_id

    async def fail_run(self, run_id: str, error: str) -> None:
        """Mark a run as failed with a truncated error note."""
        async with self._sf() as session, session.begin():
            run = await session.get(Run, run_id)
            if run is not None:
                run.status = "failed"
                run.notes = error[:2000]

    async def finalize_run(
        self, run_id: str, artifacts: RunArtifacts, *, status: str = "completed"
    ) -> None:
        """Persist all records for a run and flip its status. Result rows are append-only."""
        async with self._sf() as session, session.begin():
            run = await session.get(Run, run_id)
            if run is None:
                raise KeyError(run_id)
            run.status = status
            session.add_all(
                DimensionResultRow(
                    run_id=run_id,
                    model=r.model,
                    dimension_key=r.dimension_key,
                    n_samples=r.n_samples,
                    n_positive=r.n_positive,
                    rate=r.rate,
                    ci_low=r.ci_low,
                    ci_high=r.ci_high,
                    ci_method=r.ci_method,
                )
                for r in artifacts.dimension_results
            )
            session.add_all(
                SampleResponseRow(
                    run_id=run_id,
                    model=resp.model,
                    dimension_key=resp.dimension_key,
                    case_id=resp.case_id,
                    sample_index=resp.sample_index,
                    text=resp.text,
                    finish_reason=resp.finish_reason,
                    prompt_tokens=resp.prompt_tokens,
                    completion_tokens=resp.completion_tokens,
                    latency_ms=resp.latency_ms,
                )
                for resp in artifacts.responses
            )
            session.add_all(
                JudgmentRow(
                    run_id=run_id,
                    dimension_key=j.dimension_key,
                    case_id=j.case_id,
                    sample_index=j.sample_index,
                    judge_model=j.judge_model,
                    criterion_met=j.criterion_met,
                    evidence=j.evidence,
                )
                for j in artifacts.judgments
            )

    async def save_fingerprint(
        self, model: str, answers: dict[str, list[str]], run_id: str | None = None
    ) -> None:
        """Persist per-probe fingerprint answer distributions for a model."""
        created_at = datetime.now(UTC)
        async with self._sf() as session, session.begin():
            session.add_all(
                FingerprintRow(
                    run_id=run_id,
                    model=model,
                    created_at=created_at,
                    probe=probe,
                    answers=probe_answers,
                )
                for probe, probe_answers in answers.items()
            )

    async def upsert_monitored_model(
        self,
        *,
        model: str,
        provider: str,
        interval_hours: int,
        samples_per_case: int | None,
        dimension_keys: list[str] | None,
        with_fingerprint: bool,
        enabled: bool,
        monitor_id: str | None = None,
    ) -> MonitoredModel:
        """Create or update a persistent monitor configuration."""
        now = datetime.now(UTC)
        async with self._sf() as session, session.begin():
            row: MonitoredModelRow | None = None
            if monitor_id is not None:
                row = await session.get(MonitoredModelRow, monitor_id)
            if row is None:
                row = (
                    await session.execute(
                        select(MonitoredModelRow).where(MonitoredModelRow.model == model)
                    )
                ).scalar_one_or_none()
            if row is None:
                row = MonitoredModelRow(
                    id=uuid.uuid4().hex,
                    model=model,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            row.model = model
            row.provider = provider
            row.interval_hours = interval_hours
            row.samples_per_case = samples_per_case
            row.dimension_keys = dimension_keys
            row.with_fingerprint = with_fingerprint
            row.enabled = enabled
            row.updated_at = now
        return _row_to_monitor(row)

    async def delete_monitored_model(self, monitor_id: str) -> bool:
        async with self._sf() as session, session.begin():
            result = await session.execute(
                delete(MonitoredModelRow).where(MonitoredModelRow.id == monitor_id)
            )
            return bool(result.rowcount)

    # --- reads ---------------------------------------------------------- #
    async def get_run(self, run_id: str) -> Run | None:
        async with self._sf() as session:
            return await session.get(Run, run_id)

    async def latest_run_id(self, model: str) -> str | None:
        async with self._sf() as session:
            stmt = (
                select(Run.id)
                .where(Run.model == model, Run.status == "completed")
                .order_by(Run.created_at.desc())
                .limit(1)
            )
            return (await session.execute(stmt)).scalar_one_or_none()

    async def latest_run_at(self, model: str) -> datetime | None:
        """Creation time of the latest attempted run, regardless of final status."""
        async with self._sf() as session:
            stmt = (
                select(Run.created_at)
                .where(Run.model == model)
                .order_by(Run.created_at.desc())
                .limit(1)
            )
            value = (await session.execute(stmt)).scalar_one_or_none()
            return _as_utc(value) if value is not None else None

    async def list_runs(self, model: str | None = None, limit: int = 50) -> list[Run]:
        async with self._sf() as session:
            stmt = select(Run).order_by(Run.created_at.desc()).limit(limit)
            if model is not None:
                stmt = stmt.where(Run.model == model)
            return list((await session.execute(stmt)).scalars().all())

    async def list_models(self) -> list[str]:
        async with self._sf() as session:
            run_models = (await session.execute(select(Run.model).distinct())).scalars().all()
            monitored = (
                await session.execute(select(MonitoredModelRow.model).distinct())
            ).scalars().all()
            return sorted(set(run_models) | set(monitored))

    async def list_monitored_models(self) -> list[MonitoredModel]:
        async with self._sf() as session:
            rows = (
                (
                    await session.execute(
                        select(MonitoredModelRow).order_by(MonitoredModelRow.created_at.asc())
                    )
                )
                .scalars()
                .all()
            )
            return [_row_to_monitor(row) for row in rows]

    async def get_monitored_model(self, monitor_id: str) -> MonitoredModel | None:
        async with self._sf() as session:
            row = await session.get(MonitoredModelRow, monitor_id)
            return _row_to_monitor(row) if row is not None else None

    async def get_report_card(
        self, model: str, run_id: str | None = None
    ) -> ModelReportCard | None:
        """Latest (or specific) behavioral profile for a model."""
        async with self._sf() as session:
            if run_id is None:
                run_id = await self.latest_run_id(model)
                if run_id is None:
                    return None
            run = await session.get(Run, run_id)
            if run is None:
                return None
            rows = (
                (
                    await session.execute(
                        select(DimensionResultRow).where(DimensionResultRow.run_id == run_id)
                    )
                )
                .scalars()
                .all()
            )
            return ModelReportCard(
                model=run.model,
                run_id=run_id,
                created_at=_as_utc(run.created_at),
                dimensions=[_row_to_result(r) for r in rows],
            )

    async def get_dimension_history(
        self,
        model: str,
        dimension_key: str,
        limit: int = 100,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[HistoryPoint]:
        """Time series of a single dimension for a model (for drift charts)."""
        async with self._sf() as session:
            stmt = (
                select(Run.created_at, DimensionResultRow)
                .join(DimensionResultRow, DimensionResultRow.run_id == Run.id)
                .where(Run.model == model, DimensionResultRow.dimension_key == dimension_key)
                .order_by(Run.created_at.desc())
                .limit(limit)
            )
            if start is not None:
                stmt = stmt.where(Run.created_at >= start)
            if end is not None:
                stmt = stmt.where(Run.created_at <= end)
            rows = (await session.execute(stmt)).all()
            points = [
                HistoryPoint(
                    created_at=_as_utc(created_at),
                    run_id=row.run_id,
                    result=_row_to_result(row),
                )
                for created_at, row in rows
            ]
            points.reverse()
            return points

    async def get_traces(
        self,
        run_id: str,
        *,
        dimension_key: str | None = None,
        case_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TraceRecord]:
        """Return raw samples and the complete judge panel evidence for a run."""
        async with self._sf() as session:
            stmt = (
                select(SampleResponseRow)
                .where(SampleResponseRow.run_id == run_id)
                .order_by(
                    SampleResponseRow.dimension_key,
                    SampleResponseRow.case_id,
                    SampleResponseRow.sample_index,
                )
                .offset(offset)
                .limit(limit)
            )
            if dimension_key is not None:
                stmt = stmt.where(SampleResponseRow.dimension_key == dimension_key)
            if case_id is not None:
                stmt = stmt.where(SampleResponseRow.case_id == case_id)
            responses = list((await session.execute(stmt)).scalars().all())
            if not responses:
                return []
            judgment_stmt = select(JudgmentRow).where(JudgmentRow.run_id == run_id)
            if dimension_key is not None:
                judgment_stmt = judgment_stmt.where(JudgmentRow.dimension_key == dimension_key)
            if case_id is not None:
                judgment_stmt = judgment_stmt.where(JudgmentRow.case_id == case_id)
            judgments = list((await session.execute(judgment_stmt)).scalars().all())

        panels: dict[tuple[str, str, int], list[TraceJudgment]] = defaultdict(list)
        for item in judgments:
            panels[(item.dimension_key, item.case_id, item.sample_index)].append(
                TraceJudgment(
                    judge_model=item.judge_model,
                    criterion_met=item.criterion_met,
                    evidence=item.evidence,
                )
            )
        return [
            TraceRecord(
                id=response.id,
                run_id=response.run_id,
                model=response.model,
                dimension_key=response.dimension_key,
                case_id=response.case_id,
                sample_index=response.sample_index,
                text=response.text,
                finish_reason=response.finish_reason,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                latency_ms=response.latency_ms,
                judgments=panels[
                    (response.dimension_key, response.case_id, response.sample_index)
                ],
            )
            for response in responses
        ]

    async def get_fingerprint(
        self, model: str, run_id: str | None = None
    ) -> dict[str, list[str]]:
        """Return the latest (or a specific run's) per-probe answer distributions."""
        async with self._sf() as session:
            if run_id is None:
                latest = await session.execute(
                    select(FingerprintRow.run_id, FingerprintRow.created_at)
                    .where(FingerprintRow.model == model)
                    .order_by(FingerprintRow.created_at.desc())
                    .limit(1)
                )
                head = latest.first()
                if head is None:
                    return {}
                run_id = head.run_id
            rows = (
                (
                    await session.execute(
                        select(FingerprintRow).where(
                            FingerprintRow.model == model,
                            FingerprintRow.run_id == run_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            return {row.probe: list(row.answers) for row in rows}

    async def get_receipts(
        self, run_id: str, dimension_key: str, limit: int = 10
    ) -> list[Receipt]:
        """Return responses the judge panel flagged (majority MET) with their evidence."""
        async with self._sf() as session:
            judgments = (
                (
                    await session.execute(
                        select(JudgmentRow).where(
                            JudgmentRow.run_id == run_id,
                            JudgmentRow.dimension_key == dimension_key,
                        )
                    )
                )
                .scalars()
                .all()
            )
            responses = (
                (
                    await session.execute(
                        select(SampleResponseRow).where(
                            SampleResponseRow.run_id == run_id,
                            SampleResponseRow.dimension_key == dimension_key,
                        )
                    )
                )
                .scalars()
                .all()
            )

        votes: dict[tuple[str, int], list[JudgmentRow]] = defaultdict(list)
        for j in judgments:
            votes[(j.case_id, j.sample_index)].append(j)

        receipts: list[Receipt] = []
        for resp in responses:
            panel = votes.get((resp.case_id, resp.sample_index), [])
            if not panel:
                continue
            met = sum(1 for j in panel if j.criterion_met)
            if met * 2 > len(panel):  # majority flagged
                receipts.append(
                    Receipt(
                        dimension_key=dimension_key,
                        case_id=resp.case_id,
                        sample_index=resp.sample_index,
                        model=resp.model,
                        text=resp.text,
                        votes_met=met,
                        votes_total=len(panel),
                        evidence=[j.evidence for j in panel if j.criterion_met],
                    )
                )
        return receipts[:limit]
