"""Evaluation orchestration.

Given a target model and a set of dimensions, the runner:

1. samples every probe case ``samples_per_case`` times (bounded concurrency, owned by the
   provider's semaphore),
2. sends each response to the judge panel,
3. majority-aggregates the panel into one boolean outcome per sample,
4. summarizes each dimension into a rate + confidence interval.

Failures are isolated per sample (never crash the whole run) and dropped counts are logged —
no silent truncation. All records returned are immutable and suitable for append-only storage.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from charwatch.domain.models import (
    BenchmarkSuite,
    Dimension,
    DimensionResult,
    Judgment,
    PanelVerdict,
    ProbeCase,
    SampleResponse,
)
from charwatch.evaluation import fingerprint as fp
from charwatch.evaluation.judge import JudgePanel
from charwatch.evaluation.scoring import summarize_dimension
from charwatch.logging import get_logger
from charwatch.providers.base import ChatMessage, ChatRequest, LLMProvider
from charwatch.providers.registry import default_reasoning_effort, is_reasoning_model

log = get_logger(__name__)


@dataclass(slots=True)
class RunArtifacts:
    """Everything one evaluation run produces, ready for persistence."""

    model: str
    dimension_results: list[DimensionResult] = field(default_factory=list)
    responses: list[SampleResponse] = field(default_factory=list)
    judgments: list[Judgment] = field(default_factory=list)
    verdicts: list[PanelVerdict] = field(default_factory=list)


@dataclass(slots=True)
class _JudgedSample:
    verdict: PanelVerdict
    judgments: list[Judgment]


class EvaluationRunner:
    """Runs behavioral dimensions against a single target model."""

    def __init__(
        self,
        target_provider: LLMProvider,
        judge_panel: JudgePanel,
        *,
        samples_per_case: int,
        temperature: float = 1.0,
        max_tokens: int = 512,
        seed_base: int | None = None,
        reasoning_effort: str | None = None,
        reasoning_max_tokens: int = 8000,
        run_id: str | None = None,
    ) -> None:
        if samples_per_case < 1:
            raise ValueError("samples_per_case must be >= 1")
        self._provider = target_provider
        self._judge = judge_panel
        self._samples_per_case = samples_per_case
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._seed_base = seed_base
        # Reasoning models (gpt-5.x) reject temperature and spend tokens "thinking"; give them
        # a larger completion budget and a low reasoning effort so short behavioral answers
        # aren't truncated by the reasoning trace.
        self._reasoning_effort = reasoning_effort
        self._reasoning_max_tokens = reasoning_max_tokens
        self._run_id = run_id

    # --- public API ----------------------------------------------------- #
    async def run_suite(
        self, suite: BenchmarkSuite, model: str, dimension_keys: list[str] | None = None
    ) -> RunArtifacts:
        """Evaluate all (or a subset of) dimensions for one model."""
        dimensions = (
            suite.dimensions
            if dimension_keys is None
            else [suite.by_key(k) for k in dimension_keys]
        )
        total_samples = (
            sum(len(dimension.cases) for dimension in dimensions) * self._samples_per_case
        )
        log.info(
            "evaluation_plan",
            run_id=self._run_id,
            model=model,
            dimensions=len(dimensions),
            samples_per_case=self._samples_per_case,
            target_samples=total_samples,
        )
        artifacts = RunArtifacts(model=model)
        for index, dimension in enumerate(dimensions, start=1):
            await self._run_dimension_into(
                dimension,
                model,
                artifacts,
                dimension_index=index,
                dimension_total=len(dimensions),
            )
        return artifacts

    async def collect_fingerprint(
        self,
        model: str,
        probes: tuple[str, ...] = fp.DEFAULT_QUIRK_PROBES,
        samples_per_probe: int = 30,
    ) -> dict[str, list[str]]:
        """Sample the quirk probes to build this model's fingerprint answer distribution."""
        answers: dict[str, list[str]] = {probe: [] for probe in probes}
        total = len(probes) * samples_per_probe
        completed = 0
        progress_step = max(1, total // 10)

        async def _sample(probe: str) -> str:
            nonlocal completed
            try:
                return await self._generate_text(model, probe)
            finally:
                completed += 1
                if completed == total or completed % progress_step == 0:
                    log.info(
                        "evaluation_progress",
                        run_id=self._run_id,
                        model=model,
                        stage="fingerprinting",
                        completed=completed,
                        total=total,
                        percent=round(completed / total * 100),
                    )

        log.info(
            "fingerprint_started",
            run_id=self._run_id,
            model=model,
            probes=len(probes),
            target_samples=total,
        )
        tasks = [
            (probe, _sample(probe))
            for probe in probes
            for _ in range(samples_per_probe)
        ]
        results = await asyncio.gather(*(t[1] for t in tasks), return_exceptions=True)
        for (probe, _), result in zip(tasks, results, strict=True):
            if isinstance(result, str):
                answers[probe].append(result)
            else:
                log.warning("fingerprint_sample_failed", model=model, error=str(result))
        return answers

    # --- internals ------------------------------------------------------ #
    async def _run_dimension_into(
        self,
        dimension: Dimension,
        model: str,
        artifacts: RunArtifacts,
        *,
        dimension_index: int,
        dimension_total: int,
    ) -> None:
        cases = {c.id: c for c in dimension.cases}

        # 1. Generate all samples for the dimension.
        gen_specs = [
            (case, idx)
            for case in dimension.cases
            for idx in range(self._samples_per_case)
        ]
        generation_completed = 0
        generation_total = len(gen_specs)
        generation_step = max(1, generation_total // 10)

        async def _generate(case: ProbeCase, sample_index: int) -> SampleResponse:
            nonlocal generation_completed
            try:
                return await self._generate_sample(model, dimension, case, sample_index)
            finally:
                generation_completed += 1
                should_log = (
                    generation_completed == generation_total
                    or generation_completed % generation_step == 0
                )
                if should_log:
                    log.info(
                        "evaluation_progress",
                        run_id=self._run_id,
                        model=model,
                        dimension=dimension.key,
                        stage="generating",
                        completed=generation_completed,
                        total=generation_total,
                        percent=round(generation_completed / generation_total * 100),
                    )

        log.info(
            "dimension_started",
            run_id=self._run_id,
            model=model,
            dimension=dimension.key,
            dimension_index=dimension_index,
            dimension_total=dimension_total,
            cases=len(dimension.cases),
            target_samples=generation_total,
        )
        gen_results = await asyncio.gather(
            *(_generate(case, idx) for case, idx in gen_specs),
            return_exceptions=True,
        )
        responses: list[SampleResponse] = []
        for result in gen_results:
            if isinstance(result, SampleResponse):
                responses.append(result)
            else:
                log.warning(
                    "generation_failed",
                    model=model,
                    dimension=dimension.key,
                    error=str(result),
                )
        dropped_gen = len(gen_specs) - len(responses)

        # 2. Judge every response.
        judging_completed = 0
        judging_total = len(responses)
        judging_step = max(1, judging_total // 10) if judging_total else 1

        async def _judge(response: SampleResponse) -> _JudgedSample:
            nonlocal judging_completed
            try:
                return await self._judge_response(dimension, cases[response.case_id], response)
            finally:
                judging_completed += 1
                if judging_completed == judging_total or judging_completed % judging_step == 0:
                    log.info(
                        "evaluation_progress",
                        run_id=self._run_id,
                        model=model,
                        dimension=dimension.key,
                        stage="judging",
                        completed=judging_completed,
                        total=judging_total,
                        percent=round(judging_completed / judging_total * 100),
                    )

        log.info(
            "judging_started",
            run_id=self._run_id,
            model=model,
            dimension=dimension.key,
            responses=judging_total,
        )
        judged = await asyncio.gather(
            *(_judge(response) for response in responses),
            return_exceptions=True,
        )
        outcomes: list[bool] = []
        for item in judged:
            if isinstance(item, _JudgedSample):
                artifacts.judgments.extend(item.judgments)
                artifacts.verdicts.append(item.verdict)
                outcomes.append(item.verdict.criterion_met)
            else:
                log.warning("judging_failed", model=model, dimension=dimension.key, error=str(item))
        dropped_judge = len(responses) - len(outcomes)

        artifacts.responses.extend(responses)

        if not outcomes:
            log.error("dimension_no_usable_samples", model=model, dimension=dimension.key)
            return

        result = summarize_dimension(dimension.key, model, outcomes)
        artifacts.dimension_results.append(result)
        log.info(
            "dimension_scored",
            run_id=self._run_id,
            model=model,
            dimension=dimension.key,
            rate=round(result.rate, 3),
            n=result.n_samples,
            dropped_generation=dropped_gen,
            dropped_judging=dropped_judge,
        )

    async def _judge_response(
        self, dimension: Dimension, case: ProbeCase, response: SampleResponse
    ) -> _JudgedSample:
        judgments = await self._judge.judge_sample(dimension, case, response)
        verdict = JudgePanel.aggregate(
            dimension.key, case.id, response.sample_index, judgments
        )
        return _JudgedSample(verdict=verdict, judgments=judgments)

    async def _generate_sample(
        self, model: str, dimension: Dimension, case: ProbeCase, sample_index: int
    ) -> SampleResponse:
        messages: list[ChatMessage] = []
        if case.system:
            messages.append(ChatMessage(role="system", content=case.system))
        messages.append(ChatMessage(role="user", content=case.user))
        reasoning = is_reasoning_model(model)
        effort = (self._reasoning_effort or default_reasoning_effort(model)) if reasoning else None
        request = ChatRequest(
            model=model,
            messages=messages,
            temperature=None if reasoning else self._temperature,
            max_tokens=self._reasoning_max_tokens if reasoning else self._max_tokens,
            reasoning_effort=effort,
            seed=None if self._seed_base is None else self._seed_base + sample_index,
        )
        completion = await self._provider.generate(request)
        return SampleResponse(
            dimension_key=dimension.key,
            case_id=case.id,
            sample_index=sample_index,
            model=model,
            text=completion.text,
            finish_reason=completion.finish_reason,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            latency_ms=completion.latency_ms,
        )

    async def _generate_text(self, model: str, prompt: str) -> str:
        request = ChatRequest(
            model=model,
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=self._temperature,
            max_tokens=16,
        )
        completion = await self._provider.generate(request)
        return completion.text
