"""Trigger evaluations and inspect run status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from charwatch.api.deps import get_service
from charwatch.api.schemas import (
    EvaluateRequest,
    ReceiptResponse,
    RunStartedResponse,
    RunStatusResponse,
    TraceResponse,
)
from charwatch.service import CharwatchService

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunStartedResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    request: EvaluateRequest,
    service: CharwatchService = Depends(get_service),
) -> RunStartedResponse:
    """Kick off an evaluation in the background; poll GET /runs/{run_id} for progress."""
    try:
        run_id = await service.start_evaluation(
            request.model,
            provider=request.provider,
            dimension_keys=request.dimension_keys,
            samples_per_case=request.samples_per_case,
            with_fingerprint=request.with_fingerprint,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RunStartedResponse(run_id=run_id, status="running")


@router.get("", response_model=list[RunStatusResponse])
async def list_runs(
    model: str | None = None,
    limit: int = 50,
    service: CharwatchService = Depends(get_service),
) -> list[RunStatusResponse]:
    runs = await service.list_runs(model, limit)
    return [RunStatusResponse.from_run(r) for r in runs]


@router.get("/{run_id}", response_model=RunStatusResponse)
async def get_run(
    run_id: str,
    service: CharwatchService = Depends(get_service),
) -> RunStatusResponse:
    run = await service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    return RunStatusResponse.from_run(run)


@router.get(
    "/{run_id}/dimensions/{dimension_key}/receipts",
    response_model=list[ReceiptResponse],
    tags=["receipts"],
)
async def receipts(
    run_id: str,
    dimension_key: str,
    limit: int = 10,
    service: CharwatchService = Depends(get_service),
) -> list[ReceiptResponse]:
    """The 'damning transcripts': responses the judge panel flagged, with evidence."""
    items = await service.receipts(run_id, dimension_key, limit)
    return [ReceiptResponse.from_receipt(r) for r in items]


@router.get("/{run_id}/traces", response_model=list[TraceResponse], tags=["traces"])
async def traces(
    run_id: str,
    dimension_key: str | None = None,
    case_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    service: CharwatchService = Depends(get_service),
) -> list[TraceResponse]:
    """Raw generated samples plus every judge verdict and evidence string."""
    if await service.get_run(run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    items = await service.traces(
        run_id,
        dimension_key=dimension_key,
        case_id=case_id,
        limit=min(max(limit, 1), 500),
        offset=max(offset, 0),
    )
    return [TraceResponse.from_trace(item) for item in items]
