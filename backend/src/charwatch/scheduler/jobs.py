"""Recurring model monitoring backed by persistent application configuration.

The editable schedules live in the main database. APScheduler is intentionally an in-process
clock: jobs are rebuilt from those rows at startup, avoiding serialized service objects and
keeping the database as the single source of truth.
"""

from __future__ import annotations

from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from charwatch.db.repository import MonitoredModel
from charwatch.logging import get_logger
from charwatch.service import CharwatchService

log = get_logger(__name__)
MONITOR_INTERVAL_HOURS = 1


class EvaluationScheduler:
    """Run each enabled model monitor without overlapping executions."""

    def __init__(self, service: CharwatchService) -> None:
        self._service = service
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        self._scheduler.start()
        log.info("scheduler_started")

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            log.info("scheduler_stopped")

    def apply(
        self,
        monitor: MonitoredModel,
        *,
        run_immediately: bool = False,
        next_run_at: datetime | None = None,
    ) -> None:
        """Add, replace, or remove the timer matching a saved monitor."""
        self.remove(monitor.id)
        if not monitor.enabled:
            return
        timing: dict[str, datetime] = {}
        if run_immediately:
            timing["next_run_time"] = datetime.now(UTC)
        elif next_run_at is not None:
            timing["next_run_time"] = next_run_at
        self._scheduler.add_job(
            self._run,
            trigger="interval",
            hours=MONITOR_INTERVAL_HOURS,
            args=[monitor.id],
            id=self._job_id(monitor.id),
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
            **timing,
        )
        log.info(
            "scheduled_model",
            model=monitor.model,
            interval_hours=MONITOR_INTERVAL_HOURS,
            run_immediately=run_immediately,
        )

    def remove(self, monitor_id: str) -> None:
        job = self._scheduler.get_job(self._job_id(monitor_id))
        if job is not None:
            self._scheduler.remove_job(job.id)

    def next_run_at(self, monitor_id: str) -> datetime | None:
        job = self._scheduler.get_job(self._job_id(monitor_id))
        return job.next_run_time if job is not None else None

    async def restore(self) -> None:
        monitors = await self._service.list_monitors()
        if not monitors:
            log.warning("scheduler_idle_no_monitored_models")
            return
        enabled = 0
        for monitor in monitors:
            restored = monitor
            if monitor.interval_hours != MONITOR_INTERVAL_HOURS:
                restored = await self._service.save_monitor(
                    monitor_id=monitor.id,
                    model=monitor.model,
                    provider=monitor.provider,
                    interval_hours=MONITOR_INTERVAL_HOURS,
                    samples_per_case=monitor.samples_per_case,
                    dimension_keys=monitor.dimension_keys,
                    with_fingerprint=monitor.with_fingerprint,
                    enabled=monitor.enabled,
                )
            if restored.enabled:
                enabled += 1
            # Starting the backend is an explicit request to resume monitoring now. Previous
            # attempts (including stale/failed rows) must never delay the first fresh run.
            self.apply(restored, run_immediately=True)
        log.info("scheduler_restored", monitors=len(monitors), immediate_evaluations=enabled)

    async def _run(self, monitor_id: str) -> None:
        monitor = await self._service.get_monitor(monitor_id)
        if monitor is None or not monitor.enabled:
            self.remove(monitor_id)
            return
        log.info("scheduled_evaluation_firing", model=monitor.model)
        try:
            await self._service.run_monitor(monitor, background=False)
        except Exception as exc:  # noqa: BLE001 - keep future schedule ticks alive
            log.error("scheduled_evaluation_failed", model=monitor.model, error=repr(exc))

    @staticmethod
    def _job_id(monitor_id: str) -> str:
        return f"monitor:{monitor_id}"
