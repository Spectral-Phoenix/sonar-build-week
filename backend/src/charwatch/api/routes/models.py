"""Model report cards, dimension history, and flagged-sample receipts."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from charwatch.api.deps import get_service
from charwatch.api.schemas import HistoryPointResponse
from charwatch.domain.models import ModelReportCard
from charwatch.service import CharwatchService

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[str])
async def list_models(service: CharwatchService = Depends(get_service)) -> list[str]:
    return await service.list_models()


@router.get("/{model:path}/report-card", response_model=ModelReportCard)
async def report_card(
    model: str,
    run_id: str | None = None,
    service: CharwatchService = Depends(get_service),
) -> ModelReportCard:
    card = await service.report_card(model, run_id)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no completed run for model {model!r}",
        )
    return card


@router.get(
    "/{model:path}/dimensions/{dimension_key}/history",
    response_model=list[HistoryPointResponse],
)
async def dimension_history(
    model: str,
    dimension_key: str,
    limit: int = 100,
    start: datetime | None = None,
    end: datetime | None = None,
    service: CharwatchService = Depends(get_service),
) -> list[HistoryPointResponse]:
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start must be before end",
        )
    points = await service.history(model, dimension_key, limit, start, end)
    return [HistoryPointResponse.from_point(p) for p in points]
