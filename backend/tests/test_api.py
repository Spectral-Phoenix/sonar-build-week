from fastapi.testclient import TestClient

from charwatch.api.app import create_app
from charwatch.config import get_settings
from charwatch.domain.models import DimensionResult, Judgment, SampleResponse
from charwatch.evaluation.runner import RunArtifacts


async def _seed_completed_run(service, model: str, positives: int) -> str:
    repo = service._repo
    run_id = await repo.create_run(
        model,
        samples_per_case=2,
        judge_models=["gpt-4.1"],
    )
    artifacts = RunArtifacts(
        model=model,
        dimension_results=[
            DimensionResult(
                dimension_key="warmth",
                model=model,
                n_samples=10,
                n_positive=positives,
                rate=positives / 10,
                ci_low=max(0, positives / 10 - 0.2),
                ci_high=min(1, positives / 10 + 0.2),
            )
        ],
        responses=[
            SampleResponse(
                dimension_key="warmth",
                case_id="warm_breakup",
                sample_index=0,
                model=model,
                text="That sounds deeply painful. I am sorry you are going through this.",
            )
        ],
        judgments=[
            Judgment(
                dimension_key="warmth",
                case_id="warm_breakup",
                sample_index=0,
                judge_model="gpt-4.1",
                criterion_met=True,
                evidence="The response explicitly acknowledges the user's pain.",
            )
        ],
    )
    await repo.finalize_run(run_id, artifacts)
    await repo.save_fingerprint(
        model,
        {"Pick a color": ["red"] * 5 if model == "model-a" else ["blue"] * 5},
        run_id=run_id,
    )
    return run_id


def _assert_monitor_contract(client: TestClient) -> None:
    created = client.post(
        "/monitors",
        json={
            "model": "gpt-next",
            "provider": "openai",
            "interval_hours": 1,
            "samples_per_case": 4,
            "dimension_keys": ["warmth"],
            "with_fingerprint": True,
            "enabled": True,
        },
    )
    assert created.status_code == 201
    monitor = created.json()
    assert monitor["model"] == "gpt-next"
    assert monitor["interval_hours"] == 1
    assert monitor["next_run_at"] is not None

    assert "gpt-next" in client.get("/models").json()

    paused = client.patch(f"/monitors/{monitor['id']}", json={"enabled": False})
    assert paused.status_code == 200
    assert paused.json()["enabled"] is False
    assert paused.json()["next_run_at"] is None

    deleted = client.delete(f"/monitors/{monitor['id']}")
    assert deleted.status_code == 204
    assert client.get("/monitors").json() == []


def test_dashboard_metadata_endpoints(tmp_path, monkeypatch) -> None:
    database = tmp_path / "api-test.db"
    monkeypatch.setenv(
        "CHARWATCH_DATABASE_URL",
        f"sqlite+aiosqlite:///{database}",
    )
    monkeypatch.setenv("CHARWATCH_OPENAI_API_KEY", "")
    monkeypatch.setenv("CHARWATCH_OPENROUTER_API_KEY", "")
    get_settings.cache_clear()

    try:
        with TestClient(create_app()) as client:
            health = client.get("/health")
            assert health.status_code == 200
            assert health.json() == {"status": "ok"}

            dimensions = client.get("/dimensions")
            assert dimensions.status_code == 200
            assert {item["key"] for item in dimensions.json()} == {
                "snitching",
                "paternalism",
                "self_preservation",
                "delusion_reinforcement",
                "warmth",
            }

            benchmarks = client.get("/benchmarks")
            assert benchmarks.status_code == 200
            assert all(item["cases"] for item in benchmarks.json())
            assert all(item["judge"]["question"] for item in benchmarks.json())

            config = client.get("/config")
            assert config.status_code == 200
            assert config.json() == {
                "providers": [],
                "evaluation_enabled": False,
                "judge_models": ["gpt-4.1", "gpt-4o"],
                "samples_per_case": 20,
                "max_concurrency": 8,
                "scheduler_enabled": True,
                "database_dialect": "sqlite",
            }
    finally:
        get_settings.cache_clear()


def test_dashboard_data_contracts(tmp_path, monkeypatch) -> None:
    database = tmp_path / "api-data-test.db"
    monkeypatch.setenv("CHARWATCH_DATABASE_URL", f"sqlite+aiosqlite:///{database}")
    monkeypatch.setenv("CHARWATCH_OPENAI_API_KEY", "")
    monkeypatch.setenv("CHARWATCH_OPENROUTER_API_KEY", "")
    get_settings.cache_clear()

    try:
        with TestClient(create_app()) as client:
            service = client.app.state.service
            assert client.portal is not None
            run_a = client.portal.call(_seed_completed_run, service, "model-a", 2)
            run_b = client.portal.call(_seed_completed_run, service, "model-b", 8)
            slash_run = client.portal.call(_seed_completed_run, service, "vendor/model-c", 5)

            runs = client.get("/runs")
            assert runs.status_code == 200
            assert {item["run_id"] for item in runs.json()} == {run_a, run_b, slash_run}

            card = client.get(f"/models/model-a/report-card?run_id={run_a}")
            assert card.status_code == 200
            assert card.json()["dimensions"][0]["rate"] == 0.2

            history = client.get("/models/model-a/dimensions/warmth/history")
            assert history.status_code == 200
            assert history.json()[0]["run_id"] == run_a

            slash_history = client.get(
                "/models/vendor%2Fmodel-c/dimensions/warmth/history"
            )
            assert slash_history.status_code == 200
            assert slash_history.json()[0]["run_id"] == slash_run

            invalid_history = client.get(
                "/models/model-a/dimensions/warmth/history"
                "?start=2030-01-02T00:00:00Z&end=2030-01-01T00:00:00Z"
            )
            assert invalid_history.status_code == 422

            receipts = client.get(f"/runs/{run_a}/dimensions/warmth/receipts")
            assert receipts.status_code == 200
            assert receipts.json()[0]["votes_met"] == 1

            traces = client.get(f"/runs/{run_a}/traces?dimension_key=warmth")
            assert traces.status_code == 200
            assert traces.json()[0]["text"].startswith("That sounds deeply painful")
            assert traces.json()[0]["judgments"][0]["criterion_met"] is True

            drift = client.get("/drift?model_a=model-a&model_b=model-b")
            assert drift.status_code == 200
            assert drift.json()[0]["significant"] is True
            assert drift.json()[0]["direction"] == "increased"

            fingerprint = client.get("/fingerprint?model_a=model-a&model_b=model-b")
            assert fingerprint.status_code == 200
            assert fingerprint.json()["verdict"] == "different"

            _assert_monitor_contract(client)
    finally:
        get_settings.cache_clear()
