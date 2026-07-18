"""SQLAlchemy 2.0 ORM tables.

Evaluation evidence is append-only. Monitored-model rows are mutable runtime configuration.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from charwatch.db.base import Base


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    model: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(16))
    samples_per_case: Mapped[int] = mapped_column(Integer)
    judge_models: Mapped[list[str]] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class DimensionResultRow(Base):
    __tablename__ = "dimension_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("runs.id"), index=True)
    model: Mapped[str] = mapped_column(String(128), index=True)
    dimension_key: Mapped[str] = mapped_column(String(64), index=True)
    n_samples: Mapped[int] = mapped_column(Integer)
    n_positive: Mapped[int] = mapped_column(Integer)
    rate: Mapped[float] = mapped_column(Float)
    ci_low: Mapped[float] = mapped_column(Float)
    ci_high: Mapped[float] = mapped_column(Float)
    ci_method: Mapped[str] = mapped_column(String(16))


class SampleResponseRow(Base):
    __tablename__ = "sample_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("runs.id"), index=True)
    model: Mapped[str] = mapped_column(String(128), index=True)
    dimension_key: Mapped[str] = mapped_column(String(64), index=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True)
    sample_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    finish_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)


class JudgmentRow(Base):
    __tablename__ = "judgments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("runs.id"), index=True)
    dimension_key: Mapped[str] = mapped_column(String(64), index=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True)
    sample_index: Mapped[int] = mapped_column(Integer)
    judge_model: Mapped[str] = mapped_column(String(128))
    criterion_met: Mapped[bool] = mapped_column(Boolean)
    evidence: Mapped[str] = mapped_column(Text)


class FingerprintRow(Base):
    __tablename__ = "fingerprints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("runs.id"), index=True, nullable=True
    )
    model: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    probe: Mapped[str] = mapped_column(Text)
    answers: Mapped[list[str]] = mapped_column(JSON)


class MonitoredModelRow(Base):
    """A persistent recurring-evaluation configuration managed from the dashboard."""

    __tablename__ = "monitored_models"
    __table_args__ = (UniqueConstraint("model", name="uq_monitored_models_model"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    model: Mapped[str] = mapped_column(String(128), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="openai")
    interval_hours: Mapped[int] = mapped_column(Integer, default=1)
    samples_per_case: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dimension_keys: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    with_fingerprint: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
