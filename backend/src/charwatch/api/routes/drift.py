"""Cross-version drift and fingerprint comparison."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from charwatch.api.deps import get_service
from charwatch.api.schemas import FingerprintResponse
from charwatch.domain.models import DriftResult
from charwatch.service import CharwatchService

router = APIRouter(tags=["drift"])


@router.get("/drift", response_model=list[DriftResult])
async def drift(
    model_a: str,
    model_b: str,
    run_a: str | None = None,
    run_b: str | None = None,
    service: CharwatchService = Depends(get_service),
) -> list[DriftResult]:
    """Two-proportion drift test on every shared dimension between two models/versions."""
    try:
        return await service.compare(model_a, model_b, run_a=run_a, run_b=run_b)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/fingerprint", response_model=FingerprintResponse)
async def fingerprint(
    model_a: str,
    model_b: str,
    run_a: str | None = None,
    run_b: str | None = None,
    service: CharwatchService = Depends(get_service),
) -> FingerprintResponse:
    """Cheap identity-divergence tripwire between two models' quirk fingerprints."""
    try:
        comparison = await service.compare_fingerprint(
            model_a, model_b, run_a=run_a, run_b=run_b
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return FingerprintResponse.from_comparison(comparison)
