"""Persistent recurring model monitoring configuration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from charwatch.api.deps import get_scheduler, get_service
from charwatch.api.schemas import (
    MonitorCreateRequest,
    MonitorResponse,
    MonitorUpdateRequest,
)
from charwatch.db.repository import MonitoredModel
from charwatch.scheduler import EvaluationScheduler
from charwatch.service import CharwatchService

router = APIRouter(prefix="/monitors", tags=["monitors"])


def _response(
    monitor: MonitoredModel,
    scheduler: EvaluationScheduler | None,
) -> MonitorResponse:
    next_run = scheduler.next_run_at(monitor.id) if scheduler is not None else None
    return MonitorResponse.from_monitor(monitor, next_run_at=next_run)


@router.get("", response_model=list[MonitorResponse])
async def list_monitors(
    service: CharwatchService = Depends(get_service),
    scheduler: EvaluationScheduler | None = Depends(get_scheduler),
) -> list[MonitorResponse]:
    return [_response(item, scheduler) for item in await service.list_monitors()]


@router.post("", response_model=MonitorResponse, status_code=status.HTTP_201_CREATED)
async def create_monitor(
    request: MonitorCreateRequest,
    service: CharwatchService = Depends(get_service),
    scheduler: EvaluationScheduler | None = Depends(get_scheduler),
) -> MonitorResponse:
    try:
        monitor = await service.save_monitor(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if scheduler is not None:
        scheduler.apply(monitor, run_immediately=True)
    return _response(monitor, scheduler)


@router.patch("/{monitor_id}", response_model=MonitorResponse)
async def update_monitor(
    monitor_id: str,
    request: MonitorUpdateRequest,
    service: CharwatchService = Depends(get_service),
    scheduler: EvaluationScheduler | None = Depends(get_scheduler),
) -> MonitorResponse:
    current = await service.get_monitor(monitor_id)
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="monitor not found")
    values = asdict_monitor(current)
    values.update(request.model_dump(exclude_unset=True))
    current_next_run = scheduler.next_run_at(monitor_id) if scheduler is not None else None
    try:
        monitor = await service.save_monitor(**values, monitor_id=monitor_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if scheduler is not None:
        scheduler.apply(
            monitor,
            run_immediately=not current.enabled and monitor.enabled,
            next_run_at=current_next_run if current.enabled else None,
        )
    return _response(monitor, scheduler)


@router.delete("/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monitor(
    monitor_id: str,
    service: CharwatchService = Depends(get_service),
    scheduler: EvaluationScheduler | None = Depends(get_scheduler),
) -> Response:
    if not await service.delete_monitor(monitor_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="monitor not found")
    if scheduler is not None:
        scheduler.remove(monitor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def asdict_monitor(monitor: MonitoredModel) -> dict[str, object]:
    return {
        "model": monitor.model,
        "provider": monitor.provider,
        "interval_hours": monitor.interval_hours,
        "samples_per_case": monitor.samples_per_case,
        "dimension_keys": monitor.dimension_keys,
        "with_fingerprint": monitor.with_fingerprint,
        "enabled": monitor.enabled,
    }
