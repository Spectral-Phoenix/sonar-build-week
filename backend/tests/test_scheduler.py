"""Scheduler startup behavior."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from charwatch.db.repository import MonitoredModel
from charwatch.scheduler.jobs import EvaluationScheduler


class _Service:
    def __init__(self, monitor: MonitoredModel) -> None:
        self.monitor = monitor
        self.fired = asyncio.Event()

    async def list_monitors(self) -> list[MonitoredModel]:
        return [self.monitor]

    async def get_monitor(self, monitor_id: str) -> MonitoredModel | None:
        return self.monitor if monitor_id == self.monitor.id else None

    async def run_monitor(self, monitor: MonitoredModel, *, background: bool) -> str:
        assert background is False
        self.fired.set()
        return "startup-run"


async def test_restore_runs_enabled_monitor_immediately() -> None:
    now = datetime.now(UTC)
    monitor = MonitoredModel(
        id="monitor-1",
        model="gpt-test",
        provider="openai",
        interval_hours=1,
        samples_per_case=1,
        dimension_keys=None,
        with_fingerprint=False,
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    service = _Service(monitor)
    scheduler = EvaluationScheduler(service)  # type: ignore[arg-type]
    scheduler.start()
    try:
        await scheduler.restore()
        await asyncio.wait_for(service.fired.wait(), timeout=1)
    finally:
        scheduler.shutdown()
