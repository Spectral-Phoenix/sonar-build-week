"""FastAPI dependencies."""

from __future__ import annotations

from fastapi import Request

from charwatch.config import Settings
from charwatch.scheduler import EvaluationScheduler
from charwatch.service import CharwatchService


def get_service(request: Request) -> CharwatchService:
    """Return the process-wide service built during app startup."""
    return request.app.state.service


def get_runtime_settings(request: Request) -> Settings:
    """Return sanitized-source runtime settings for capability metadata routes."""
    return request.app.state.container.settings


def get_scheduler(request: Request) -> EvaluationScheduler | None:
    """Return the recurring scheduler, or None when explicitly disabled."""
    return getattr(request.app.state, "scheduler", None)
