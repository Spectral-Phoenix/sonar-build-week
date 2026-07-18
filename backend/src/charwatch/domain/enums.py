"""Domain enumerations."""

from __future__ import annotations

from enum import StrEnum


class Theme(StrEnum):
    """High-level hackathon/product theme a dimension speaks to."""

    SECURITY = "security"
    OBSERVABILITY = "observability"
    SAFETY = "safety"
    VIRALITY = "virality"


class DriftDirection(StrEnum):
    """Direction of a statistically significant change between two runs."""

    INCREASED = "increased"
    DECREASED = "decreased"
    STABLE = "stable"


class RunStatus(StrEnum):
    """Lifecycle of an evaluation run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
