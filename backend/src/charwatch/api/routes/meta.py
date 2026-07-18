"""Health and benchmark metadata endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from charwatch.api.deps import get_runtime_settings, get_service
from charwatch.api.schemas import DimensionInfo, RuntimeConfigResponse
from charwatch.config import Settings
from charwatch.domain.models import Dimension
from charwatch.service import CharwatchService

router = APIRouter(tags=["meta"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/config", response_model=RuntimeConfigResponse)
async def runtime_config(
    settings: Settings = Depends(get_runtime_settings),
) -> RuntimeConfigResponse:
    """Dashboard-safe runtime configuration; never includes credentials or URLs."""
    providers: list[str] = []
    if settings.openai_api_key:
        providers.append("openai")
    if settings.openrouter_api_key:
        providers.append("openrouter")
    return RuntimeConfigResponse(
        providers=providers,
        evaluation_enabled=bool(settings.openai_api_key),
        judge_models=settings.judge_models,
        samples_per_case=settings.samples_per_case,
        max_concurrency=settings.max_concurrency,
        scheduler_enabled=settings.enable_scheduler,
        database_dialect="sqlite" if settings.is_sqlite else "postgresql",
    )


@router.get("/dimensions", response_model=list[DimensionInfo])
async def list_dimensions(
    service: CharwatchService = Depends(get_service),
) -> list[DimensionInfo]:
    return [
        DimensionInfo(
            key=d.key,
            name=d.name,
            theme=d.theme,
            description=d.description,
            higher_means=d.higher_means,
        )
        for d in service.suite.dimensions
    ]


@router.get("/benchmarks", response_model=list[Dimension])
async def list_benchmarks(
    service: CharwatchService = Depends(get_service),
) -> list[Dimension]:
    """Return the exact prompts and judging definitions used by evaluations."""
    return service.suite.dimensions


@router.post("/benchmarks", response_model=Dimension, status_code=status.HTTP_201_CREATED)
async def create_benchmark(
    dimension: Dimension,
    service: CharwatchService = Depends(get_service),
) -> Dimension:
    try:
        return service.create_dimension(dimension)
    except FileExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.put("/benchmarks/{key}", response_model=Dimension)
async def update_benchmark(
    key: str,
    dimension: Dimension,
    service: CharwatchService = Depends(get_service),
) -> Dimension:
    try:
        return service.update_dimension(key, dimension)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
