"""Core domain models (Pydantic v2), pure data with no I/O.

Two families live here:

* **Benchmark definitions** — ``JudgeSpec``, ``ProbeCase``, ``Dimension``, ``BenchmarkSuite`` —
  the maintainable specification of *what* we measure. Loaded from YAML in ``benchmarks/``.
* **Result records** — ``SampleResponse``, ``Judgment``, ``PanelVerdict``, ``DimensionResult``,
  ``ModelReportCard``, ``DriftResult`` — the immutable output of an evaluation run.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from charwatch.domain.enums import DriftDirection, Theme


class _Frozen(BaseModel):
    """Base for immutable value objects."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- #
# Benchmark definitions
# --------------------------------------------------------------------------- #
class JudgeSpec(_Frozen):
    """The binary rubric a judge panel applies to a response.

    We deliberately score a single binary criterion (highest inter-rater reliability)
    and report a *rate* across samples rather than an invented 0-100 score.
    """

    question: str
    rubric: str
    positive_label: str = "exhibited"
    negative_label: str = "did not exhibit"


class ProbeCase(_Frozen):
    """A single elicitation scenario within a dimension."""

    id: str
    user: str
    system: str | None = None
    notes: str | None = None


class Dimension(_Frozen):
    """A behavioral dimension: a named battery of probes plus the judge rubric."""

    key: str
    name: str
    theme: Theme
    description: str
    judge: JudgeSpec
    cases: list[ProbeCase] = Field(min_length=1)
    # Human-readable framing for the dashboard, e.g. "higher = more likely to snitch".
    higher_means: str

    def case_ids(self) -> list[str]:
        return [c.id for c in self.cases]


class BenchmarkSuite(_Frozen):
    """The full set of dimensions charwatch maintains."""

    dimensions: list[Dimension] = Field(min_length=1)

    def by_key(self, key: str) -> Dimension:
        for dim in self.dimensions:
            if dim.key == key:
                return dim
        raise KeyError(key)


# --------------------------------------------------------------------------- #
# Result records (immutable)
# --------------------------------------------------------------------------- #
class SampleResponse(_Frozen):
    """One model response to one probe case (one of N repeated samples)."""

    dimension_key: str
    case_id: str
    sample_index: int
    model: str
    text: str
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float | None = None


class Judgment(_Frozen):
    """One judge's binary verdict on one sample response."""

    dimension_key: str
    case_id: str
    sample_index: int
    judge_model: str
    criterion_met: bool
    evidence: str


class PanelVerdict(_Frozen):
    """Aggregated verdict for a single sample across the judge panel (majority vote)."""

    dimension_key: str
    case_id: str
    sample_index: int
    votes_met: int
    votes_total: int

    @property
    def criterion_met(self) -> bool:
        # Strict majority; ties (even panels) resolve to False to avoid over-flagging.
        return self.votes_met * 2 > self.votes_total


class DimensionResult(_Frozen):
    """Aggregated rate + confidence interval for one dimension on one model."""

    dimension_key: str
    model: str
    n_samples: int
    n_positive: int
    rate: float
    ci_low: float
    ci_high: float
    ci_method: str = "wilson"

    @property
    def rate_pct(self) -> float:
        return round(self.rate * 100, 1)


class ModelReportCard(_Frozen):
    """A model's full behavioral profile at a point in time."""

    model: str
    run_id: str
    created_at: datetime
    dimensions: list[DimensionResult]


class DriftResult(_Frozen):
    """Comparison of one dimension between two models/versions."""

    dimension_key: str
    model_a: str
    model_b: str
    rate_a: float
    rate_b: float
    n_a: int
    n_b: int
    delta: float
    z_stat: float
    p_value: float
    significant: bool
    direction: DriftDirection
