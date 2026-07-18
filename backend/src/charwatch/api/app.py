"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from charwatch import __version__
from charwatch.api.routes import drift, meta, models, monitors, runs
from charwatch.container import build_container, dispose_container
from charwatch.scheduler import EvaluationScheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = await build_container()
    app.state.container = container
    app.state.service = container.service

    scheduler: EvaluationScheduler | None = None
    settings = container.settings
    if settings.enable_scheduler:
        scheduler = EvaluationScheduler(container.service)
        scheduler.start()
        await scheduler.restore()
        app.state.scheduler = scheduler

    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown()
        await dispose_container(container)


def create_app() -> FastAPI:
    app = FastAPI(
        title="charwatch",
        description="Character-drift observatory: track how frontier LLMs shift on "
        "behavioral/values dimensions across versions.",
        version=__version__,
        lifespan=lifespan,
    )
    # Permissive CORS for the dashboard; tighten allow_origins for production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(meta.router)
    app.include_router(runs.router)
    app.include_router(models.router)
    app.include_router(monitors.router)
    app.include_router(drift.router)
    return app


app = create_app()
