"""Command-line interface for charwatch."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import typer

from charwatch.container import build_container, dispose_container
from charwatch.domain.models import DriftResult, ModelReportCard
from charwatch.service import CharwatchService

app = typer.Typer(add_completion=False, help="charwatch — the character-drift observatory.")

T = TypeVar("T")


def _run(func: Callable[[CharwatchService], Awaitable[T]]) -> T:
    """Build the container, run an async use-case, dispose cleanly."""

    async def _main() -> T:
        container = await build_container()
        try:
            return await func(container.service)
        finally:
            await dispose_container(container)

    return asyncio.run(_main())


def _print_report_card(card: ModelReportCard) -> None:
    stamp = card.created_at.strftime("%Y-%m-%d %H:%M")
    typer.echo(f"\nReport card: {card.model}  (run {card.run_id[:8]}, {stamp})")
    typer.echo("-" * 72)
    typer.echo(f"{'dimension':<26}{'rate':>8}{'95% CI':>20}{'n':>6}")
    for d in sorted(card.dimensions, key=lambda r: r.dimension_key):
        ci = f"[{d.ci_low*100:4.1f}, {d.ci_high*100:4.1f}]"
        typer.echo(f"{d.dimension_key:<26}{d.rate_pct:>7.1f}%{ci:>20}{d.n_samples:>6}")


def _drift_flag(result: DriftResult) -> str:
    if not result.significant:
        return ""
    return "SIGNIF ↑" if result.direction == "increased" else "SIGNIF ↓"


def _print_drift(drifts: list[DriftResult]) -> None:
    typer.echo(f"\n{'dimension':<26}{'A':>8}{'B':>8}{'delta':>8}{'p':>10}  verdict")
    typer.echo("-" * 78)
    for d in drifts:
        flag = _drift_flag(d)
        typer.echo(
            f"{d.dimension_key:<26}{d.rate_a*100:>7.1f}%{d.rate_b*100:>7.1f}%"
            f"{d.delta*100:>+7.1f}%{d.p_value:>10.4f}  {flag}"
        )


@app.command()
def dimensions() -> None:
    """List the behavioral dimensions charwatch tracks."""

    async def _do(service: CharwatchService) -> None:
        for d in service.suite.dimensions:
            typer.echo(f"{d.key:<24} [{d.theme}]  {d.name}")

    _run(_do)


@app.command()
def evaluate(
    model: str = typer.Argument(..., help="Target model id."),
    provider: str = typer.Option("openai", help="Provider: openai | openrouter."),
    dimensions_csv: str = typer.Option(None, "--dimensions", help="Comma-separated subset."),
    samples: int = typer.Option(None, "--samples", help="Samples per case."),
    fingerprint: bool = typer.Option(True, help="Also collect the quirk fingerprint."),
) -> None:
    """Run the behavioral battery against a model and print its report card."""
    keys = [d.strip() for d in dimensions_csv.split(",")] if dimensions_csv else None

    async def _do(service: CharwatchService) -> None:
        outcome = await service.evaluate_model(
            model,
            provider=provider,
            dimension_keys=keys,
            samples_per_case=samples,
            with_fingerprint=fingerprint,
        )
        _print_report_card(outcome.report_card)
        typer.echo(f"\nrun_id: {outcome.run_id}")

    _run(_do)


@app.command("report-card")
def report_card(
    model: str,
    run_id: str = typer.Option(None, "--run-id"),
) -> None:
    """Print the latest (or a specific) stored report card for a model."""

    async def _do(service: CharwatchService) -> None:
        card = await service.report_card(model, run_id)
        if card is None:
            typer.echo(f"No completed run for {model!r}.")
            raise typer.Exit(code=1)
        _print_report_card(card)

    _run(_do)


@app.command()
def drift(model_a: str, model_b: str) -> None:
    """Compare two models' latest report cards dimension-by-dimension."""

    async def _do(service: CharwatchService) -> None:
        drifts = await service.compare(model_a, model_b)
        _print_drift(drifts)

    _run(_do)


@app.command()
def fingerprint(model_a: str, model_b: str) -> None:
    """Compare two models' quirk fingerprints (identity tripwire)."""

    async def _do(service: CharwatchService) -> None:
        comparison = await service.compare_fingerprint(model_a, model_b)
        typer.echo(
            f"\nfingerprint distance (mean JSD): {comparison.distance:.3f}  →  "
            f"{comparison.verdict.upper()}"
        )

    _run(_do)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
    reload: bool = typer.Option(False),
) -> None:
    """Run the HTTP API with uvicorn."""
    import uvicorn  # noqa: PLC0415 - lazy: avoid importing the server for other CLI commands

    uvicorn.run("charwatch.api.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
