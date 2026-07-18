"""Composition root: build the fully-wired service from settings.

Used by the API lifespan and the CLI so both share identical wiring.
"""

from __future__ import annotations

from dataclasses import dataclass

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncEngine

from charwatch.benchmarks.loader import load_suite
from charwatch.config import Settings, get_settings
from charwatch.db.base import create_engine, create_session_factory, init_db
from charwatch.db.repository import RunRepository
from charwatch.evaluation.judge import JudgePanel
from charwatch.logging import configure_logging, get_logger
from charwatch.providers.openai_provider import OpenAIProvider
from charwatch.service import CharwatchService

log = get_logger(__name__)

OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(slots=True)
class Container:
    settings: Settings
    engine: AsyncEngine
    service: CharwatchService


def _build_providers(settings: Settings) -> dict[str, OpenAIProvider]:
    providers: dict[str, OpenAIProvider] = {}
    if settings.openai_api_key:
        openai_client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            # Resolve base_url explicitly so an ambient OPENAI_BASE_URL (e.g. a RunPod/proxy
            # endpoint in the shell) can't hijack our requests. Override with
            # CHARWATCH_OPENAI_BASE_URL only when you deliberately want a different endpoint.
            base_url=settings.openai_base_url or OPENAI_DEFAULT_BASE_URL,
            max_retries=settings.max_retries,
            timeout=settings.request_timeout_seconds,
        )
        providers["openai"] = OpenAIProvider(
            openai_client, name="openai", max_concurrency=settings.max_concurrency
        )
    if settings.openrouter_api_key:
        openrouter_client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=OPENROUTER_BASE_URL,
            max_retries=settings.max_retries,
            timeout=settings.request_timeout_seconds,
        )
        providers["openrouter"] = OpenAIProvider(
            openrouter_client, name="openrouter", max_concurrency=settings.max_concurrency
        )
    return providers


async def build_container(settings: Settings | None = None) -> Container:
    """Construct engine, repository, providers, judge panel, and service."""
    settings = settings or get_settings()
    configure_logging(settings.log_format, settings.log_level)

    engine = create_engine(settings.database_url)
    await init_db(engine)
    session_factory = create_session_factory(engine)
    repo = RunRepository(session_factory)
    suite = load_suite(settings.benchmarks_dir)

    providers = _build_providers(settings)
    # The judge panel needs OpenAI structured outputs. Build it when a key is present;
    # otherwise the container still serves read-only queries (report cards, drift, dimensions)
    # and evaluation raises a clear error only when actually invoked.
    judge_panel = (
        JudgePanel(providers["openai"], settings.judge_models)
        if "openai" in providers
        else None
    )
    service = CharwatchService(
        settings=settings,
        repo=repo,
        suite=suite,
        providers=providers,
        judge_panel=judge_panel,
    )
    log.info(
        "container_built",
        providers=sorted(providers),
        dimensions=[d.key for d in suite.dimensions],
        judge_models=settings.judge_models,
    )
    return Container(settings=settings, engine=engine, service=service)


async def dispose_container(container: Container) -> None:
    await container.engine.dispose()
