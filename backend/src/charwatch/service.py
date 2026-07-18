"""Application service: composes providers + runner + repository into use-cases.

This is the single entry point used by both the HTTP API and the CLI, so behavior stays
identical across surfaces.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime

from charwatch.benchmarks.editor import save_dimension
from charwatch.benchmarks.loader import load_suite
from charwatch.config import Settings
from charwatch.db.repository import (
    HistoryPoint,
    MonitoredModel,
    Receipt,
    Run,
    RunRepository,
    TraceRecord,
)
from charwatch.domain.models import BenchmarkSuite, Dimension, DriftResult, ModelReportCard
from charwatch.evaluation import fingerprint as fp
from charwatch.evaluation.judge import JudgePanel
from charwatch.evaluation.runner import EvaluationRunner
from charwatch.evaluation.scoring import compute_drift
from charwatch.logging import get_logger
from charwatch.providers.openai_provider import OpenAIProvider

log = get_logger(__name__)


@dataclass(slots=True)
class EvaluationOutcome:
    run_id: str
    report_card: ModelReportCard


@dataclass(slots=True)
class FingerprintComparison:
    model_a: str
    model_b: str
    distance: float
    verdict: str


class CharwatchService:
    """Behavioral evaluation, drift comparison, and fingerprinting use-cases."""

    def __init__(
        self,
        *,
        settings: Settings,
        repo: RunRepository,
        suite: BenchmarkSuite,
        providers: dict[str, OpenAIProvider],
        judge_panel: JudgePanel | None,
    ) -> None:
        self._settings = settings
        self._repo = repo
        self._suite = suite
        self._providers = providers
        self._judge = judge_panel
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def suite(self) -> BenchmarkSuite:
        return self._suite

    def create_dimension(self, dimension: Dimension) -> Dimension:
        """Persist a new behavior and make it available to future evaluations immediately."""
        save_dimension(self._settings.benchmarks_dir, dimension, create=True)
        self._suite = load_suite(self._settings.benchmarks_dir)
        log.info("behavior_created", behavior=dimension.key, questions=len(dimension.cases))
        return self._suite.by_key(dimension.key)

    def update_dimension(self, key: str, dimension: Dimension) -> Dimension:
        """Replace one behavior definition and hot-reload the validated benchmark suite."""
        if key != dimension.key:
            raise ValueError("behavior keys cannot be changed after creation")
        save_dimension(self._settings.benchmarks_dir, dimension, create=False)
        self._suite = load_suite(self._settings.benchmarks_dir)
        log.info("behavior_updated", behavior=dimension.key, questions=len(dimension.cases))
        return self._suite.by_key(dimension.key)

    def _provider(self, name: str) -> OpenAIProvider:
        provider = self._providers.get(name)
        if provider is None:
            raise ValueError(f"unknown or unconfigured provider: {name!r}")
        return provider

    def _require_judge(self) -> JudgePanel:
        if self._judge is None:
            raise ValueError(
                "no judge panel configured — set CHARWATCH_OPENAI_API_KEY to run evaluations"
            )
        return self._judge

    async def _execute(
        self,
        run_id: str,
        model: str,
        provider: str,
        dimension_keys: list[str] | None,
        samples_per_case: int,
        with_fingerprint: bool,
    ) -> None:
        """Run + persist one evaluation into a pre-created run row. Raises on failure."""
        target = self._provider(provider)
        runner = EvaluationRunner(
            target,
            self._require_judge(),
            samples_per_case=samples_per_case,
            run_id=run_id,
        )
        started_at = time.perf_counter()
        log.info(
            "evaluation_started",
            run_id=run_id,
            model=model,
            provider=provider,
            samples_per_case=samples_per_case,
            dimensions=dimension_keys or [dimension.key for dimension in self._suite.dimensions],
        )
        artifacts = await runner.run_suite(self._suite, model, dimension_keys)
        log.info(
            "evaluation_persisting",
            run_id=run_id,
            model=model,
            responses=len(artifacts.responses),
            judgments=len(artifacts.judgments),
            dimensions=len(artifacts.dimension_results),
        )
        await self._repo.finalize_run(run_id, artifacts)
        if with_fingerprint:
            answers = await runner.collect_fingerprint(model)
            await self._repo.save_fingerprint(model, answers, run_id=run_id)
            log.info(
                "fingerprint_persisted",
                run_id=run_id,
                model=model,
                answers=sum(len(values) for values in answers.values()),
            )
        log.info(
            "evaluation_completed",
            run_id=run_id,
            model=model,
            duration_seconds=round(time.perf_counter() - started_at, 1),
        )

    async def _safe_execute(self, run_id: str, *args: object) -> None:
        """Background wrapper: records failure instead of propagating to a lost task."""
        try:
            await self._execute(run_id, *args)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - persist failure, keep the worker alive
            log.exception("evaluation_failed", run_id=run_id, error=repr(exc))
            await self._repo.fail_run(run_id, repr(exc))

    async def evaluate_model(
        self,
        model: str,
        *,
        provider: str = "openai",
        dimension_keys: list[str] | None = None,
        samples_per_case: int | None = None,
        with_fingerprint: bool = True,
    ) -> EvaluationOutcome:
        """Run the battery synchronously (used by the CLI); raises on failure."""
        spc = samples_per_case or self._settings.samples_per_case
        self._provider(provider)  # validate before creating a run row
        self._require_judge()
        run_id = await self._repo.create_run(
            model, samples_per_case=spc, judge_models=self._settings.judge_models
        )
        try:
            await self._execute(run_id, model, provider, dimension_keys, spc, with_fingerprint)
        except Exception as exc:  # noqa: BLE001 - mark run failed, then surface to caller
            await self._repo.fail_run(run_id, repr(exc))
            raise
        card = await self._repo.get_report_card(model, run_id)
        if card is None:  # pragma: no cover - just-written run must exist
            raise RuntimeError(f"report card missing for freshly saved run {run_id}")
        return EvaluationOutcome(run_id=run_id, report_card=card)

    async def start_evaluation(
        self,
        model: str,
        *,
        provider: str = "openai",
        dimension_keys: list[str] | None = None,
        samples_per_case: int | None = None,
        with_fingerprint: bool = True,
    ) -> str:
        """Kick off an evaluation in the background (used by the API); returns the run id."""
        spc = samples_per_case or self._settings.samples_per_case
        self._provider(provider)  # validate now so the caller gets an immediate error
        self._require_judge()
        run_id = await self._repo.create_run(
            model, samples_per_case=spc, judge_models=self._settings.judge_models
        )
        task = asyncio.create_task(
            self._safe_execute(run_id, model, provider, dimension_keys, spc, with_fingerprint)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run_id

    async def get_run(self, run_id: str) -> Run | None:
        return await self._repo.get_run(run_id)

    async def report_card(self, model: str, run_id: str | None = None) -> ModelReportCard | None:
        return await self._repo.get_report_card(model, run_id)

    async def history(
        self,
        model: str,
        dimension_key: str,
        limit: int = 100,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[HistoryPoint]:
        return await self._repo.get_dimension_history(model, dimension_key, limit, start, end)

    async def receipts(self, run_id: str, dimension_key: str, limit: int = 10) -> list[Receipt]:
        return await self._repo.get_receipts(run_id, dimension_key, limit)

    async def list_models(self) -> list[str]:
        return await self._repo.list_models()

    async def list_runs(self, model: str | None = None, limit: int = 50) -> list[Run]:
        return await self._repo.list_runs(model, limit)

    async def latest_run_at(self, model: str) -> datetime | None:
        return await self._repo.latest_run_at(model)

    async def traces(
        self,
        run_id: str,
        *,
        dimension_key: str | None = None,
        case_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TraceRecord]:
        return await self._repo.get_traces(
            run_id,
            dimension_key=dimension_key,
            case_id=case_id,
            limit=limit,
            offset=offset,
        )

    async def list_monitors(self) -> list[MonitoredModel]:
        return await self._repo.list_monitored_models()

    async def get_monitor(self, monitor_id: str) -> MonitoredModel | None:
        return await self._repo.get_monitored_model(monitor_id)

    async def save_monitor(
        self,
        *,
        model: str,
        provider: str = "openai",
        interval_hours: int = 1,
        samples_per_case: int | None = None,
        dimension_keys: list[str] | None = None,
        with_fingerprint: bool = True,
        enabled: bool = True,
        monitor_id: str | None = None,
    ) -> MonitoredModel:
        if provider not in {"openai", "openrouter"}:
            raise ValueError(f"unknown provider: {provider!r}")
        known_dimensions = {dimension.key for dimension in self._suite.dimensions}
        unknown = set(dimension_keys or []) - known_dimensions
        if unknown:
            raise ValueError(f"unknown dimensions: {', '.join(sorted(unknown))}")
        return await self._repo.upsert_monitored_model(
            model=model,
            provider=provider,
            interval_hours=interval_hours,
            samples_per_case=samples_per_case,
            dimension_keys=dimension_keys,
            with_fingerprint=with_fingerprint,
            enabled=enabled,
            monitor_id=monitor_id,
        )

    async def delete_monitor(self, monitor_id: str) -> bool:
        return await self._repo.delete_monitored_model(monitor_id)

    async def run_monitor(self, monitor: MonitoredModel, *, background: bool = True) -> str:
        kwargs = {
            "provider": monitor.provider,
            "dimension_keys": monitor.dimension_keys,
            "samples_per_case": monitor.samples_per_case,
            "with_fingerprint": monitor.with_fingerprint,
        }
        if background:
            return await self.start_evaluation(monitor.model, **kwargs)
        outcome = await self.evaluate_model(monitor.model, **kwargs)
        return outcome.run_id

    async def compare(
        self,
        model_a: str,
        model_b: str,
        *,
        run_a: str | None = None,
        run_b: str | None = None,
    ) -> list[DriftResult]:
        """Two-proportion drift test on every shared dimension between two models/runs."""
        card_a = await self._repo.get_report_card(model_a, run_a)
        card_b = await self._repo.get_report_card(model_b, run_b)
        if card_a is None or card_b is None:
            raise ValueError("both models must have at least one completed run")
        by_key_a = {r.dimension_key: r for r in card_a.dimensions}
        by_key_b = {r.dimension_key: r for r in card_b.dimensions}
        return [
            compute_drift(by_key_a[key], by_key_b[key])
            for key in sorted(set(by_key_a) & set(by_key_b))
        ]

    async def compare_fingerprint(
        self,
        model_a: str,
        model_b: str,
        *,
        run_a: str | None = None,
        run_b: str | None = None,
    ) -> FingerprintComparison:
        """Cheap identity-divergence check between two models' quirk fingerprints."""
        fa = await self._repo.get_fingerprint(model_a, run_a)
        fb = await self._repo.get_fingerprint(model_b, run_b)
        if not fa or not fb:
            raise ValueError("both models must have a stored fingerprint")
        distance = fp.fingerprint_distance(fa, fb)
        return FingerprintComparison(
            model_a=model_a,
            model_b=model_b,
            distance=distance,
            verdict=fp.classify_distance(distance),
        )
