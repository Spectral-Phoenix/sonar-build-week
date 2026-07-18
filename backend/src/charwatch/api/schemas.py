"""Request/response schemas for the HTTP API.

Domain result models (``ModelReportCard``, ``DimensionResult``, ``DriftResult``) are already
Pydantic and are returned directly; these schemas cover requests and the DTOs that wrap
non-Pydantic repository dataclasses.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from charwatch.db.repository import HistoryPoint, MonitoredModel, Receipt, Run, TraceRecord
from charwatch.domain.enums import Theme
from charwatch.service import FingerprintComparison


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class EvaluateRequest(BaseModel):
    model: str = Field(description="Target model id, e.g. 'gpt-4o-2024-11-20'.")
    provider: str = Field(default="openai", description="'openai' or 'openrouter'.")
    dimension_keys: list[str] | None = Field(
        default=None, description="Subset of dimensions; null = all."
    )
    samples_per_case: int | None = Field(default=None, ge=1, le=1000)
    with_fingerprint: bool = True


class RunStartedResponse(BaseModel):
    run_id: str
    status: str


class RunStatusResponse(BaseModel):
    run_id: str
    model: str
    status: str
    created_at: datetime
    samples_per_case: int
    judge_models: list[str]
    notes: str | None = None

    @classmethod
    def from_run(cls, run: Run) -> RunStatusResponse:
        return cls(
            run_id=run.id,
            model=run.model,
            status=run.status,
            created_at=_as_utc(run.created_at),
            samples_per_case=run.samples_per_case,
            judge_models=list(run.judge_models),
            notes=run.notes,
        )


class DimensionInfo(BaseModel):
    key: str
    name: str
    theme: Theme
    description: str
    higher_means: str


class RuntimeConfigResponse(BaseModel):
    """Non-secret runtime capabilities safe to expose to the dashboard."""

    providers: list[str]
    evaluation_enabled: bool
    judge_models: list[str]
    samples_per_case: int
    max_concurrency: int
    scheduler_enabled: bool
    database_dialect: str


class HistoryPointResponse(BaseModel):
    created_at: datetime
    run_id: str
    rate: float
    ci_low: float
    ci_high: float
    n_samples: int

    @classmethod
    def from_point(cls, point: HistoryPoint) -> HistoryPointResponse:
        return cls(
            created_at=point.created_at,
            run_id=point.run_id,
            rate=point.result.rate,
            ci_low=point.result.ci_low,
            ci_high=point.result.ci_high,
            n_samples=point.result.n_samples,
        )


class ReceiptResponse(BaseModel):
    dimension_key: str
    case_id: str
    sample_index: int
    model: str
    text: str
    votes_met: int
    votes_total: int
    evidence: list[str]

    @classmethod
    def from_receipt(cls, receipt: Receipt) -> ReceiptResponse:
        return cls(**asdict(receipt))


class FingerprintResponse(BaseModel):
    model_a: str
    model_b: str
    distance: float
    verdict: str

    @classmethod
    def from_comparison(cls, comparison: FingerprintComparison) -> FingerprintResponse:
        return cls(**asdict(comparison))


class MonitorCreateRequest(BaseModel):
    model: str = Field(min_length=1, max_length=128)
    provider: str = Field(default="openai", max_length=32)
    interval_hours: int = Field(default=1, ge=1, le=1)
    samples_per_case: int | None = Field(default=None, ge=1, le=1000)
    dimension_keys: list[str] | None = None
    with_fingerprint: bool = True
    enabled: bool = True


class MonitorUpdateRequest(BaseModel):
    model: str | None = Field(default=None, min_length=1, max_length=128)
    provider: str | None = Field(default=None, max_length=32)
    interval_hours: int | None = Field(default=None, ge=1, le=1)
    samples_per_case: int | None = Field(default=None, ge=1, le=1000)
    dimension_keys: list[str] | None = None
    with_fingerprint: bool | None = None
    enabled: bool | None = None


class MonitorResponse(BaseModel):
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
    next_run_at: datetime | None = None

    @classmethod
    def from_monitor(
        cls, monitor: MonitoredModel, *, next_run_at: datetime | None = None
    ) -> MonitorResponse:
        return cls(**asdict(monitor), next_run_at=next_run_at)


class TraceJudgmentResponse(BaseModel):
    judge_model: str
    criterion_met: bool
    evidence: str


class TraceResponse(BaseModel):
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
    judgments: list[TraceJudgmentResponse]

    @classmethod
    def from_trace(cls, trace: TraceRecord) -> TraceResponse:
        return cls(**asdict(trace))
