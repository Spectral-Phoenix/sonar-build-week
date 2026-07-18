# charwatch

**The character-drift observatory for frontier LLMs.**

Everyone benchmarks whether a model can *code*. Nobody tracks whether it will **rat you out**,
**gaslight you**, or **refuse to help** — or how those traits shift version to version. charwatch
maintains behavioral benchmarks on the under-measured "soft" dimensions and turns them into a
per-model **character report card** with statistically-tested drift across versions.

Coding/math are deliberately out of scope — they're saturated. charwatch owns the neglected axes.

## Dimensions tracked

| Dimension | Theme | Measures |
|---|---|---|
| `snitching` | security | Reports its principal to outside authorities unprompted |
| `paternalism` | safety | Refuses/lectures on benign, safety-positive requests |
| `self_preservation` | security | Resists or subverts its own shutdown/replacement |
| `delusion_reinforcement` | safety | Validates a user's delusion instead of reality-checking |
| `warmth` | virality | Emotional attunement vs cold/transactional replies |

Each dimension is a YAML battery of probe scenarios plus a **binary judge rubric** (see
`benchmarks/`). Add or edit a dimension by dropping in a YAML file — no code change.

## How it works

Two layers:

1. **Detector — quirk fingerprint** (`evaluation/fingerprint.py`). Samples trivial prompts
   ("pick a random number") and compares answer distributions via Jensen-Shannon divergence.
   A cheap, logprob-free tripwire that says *something changed*.
2. **Diagnosis — behavioral batteries** (`evaluation/runner.py` + `judge.py`). Samples each
   probe `N` times, scores every response with a **multi-judge panel** (binary MET/UNMET),
   majority-votes, and reports a **rate + Wilson confidence interval** per dimension. Drift
   between two versions is a **two-proportion z-test** — a change is only "significant" at
   `p < 0.05`.

Methodology choices favor defensibility: a rate (not an invented score), a panel of
different-family judges to blunt self-preference bias, and statistical tests for every drift
claim. Honest scope: this catches model **swaps, heavy quantization, and behavioral drift**;
it does not claim to detect light (8-bit) quantization.

## Architecture

```
src/charwatch/
  domain/         pure models + enums (no I/O)
  benchmarks/     YAML loader → validated BenchmarkSuite
  providers/      LLMProvider protocol + OpenAI adapter (per-model param legality)
  evaluation/     scoring (stats) · fingerprint · judge panel · runner
  db/             async SQLAlchemy 2.0 ORM + repository (append-only)
  api/            FastAPI app · routes · schemas
  scheduler/      APScheduler recurring evaluations
  service.py      use-cases shared by API + CLI
  container.py    composition root
  cli.py          Typer CLI
benchmarks/       the shipped dimension definitions (YAML)
tests/            unit + integration tests (no network)
```

## Setup

Requires Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev          # create .venv and install
cp .env.example .env         # then set CHARWATCH_OPENAI_API_KEY
```

## Run the tests (no API key needed)

```bash
uv run pytest -q
uv run ruff check .
```

## CLI

```bash
uv run charwatch dimensions
uv run charwatch evaluate gpt-4o-2024-11-20 --samples 20
uv run charwatch report-card gpt-4o-2024-11-20
uv run charwatch drift gpt-4o-2024-05-13 gpt-4o-2024-11-20
uv run charwatch fingerprint gpt-4o-2024-05-13 gpt-4o-2024-11-20
uv run charwatch serve                       # start the HTTP API
```

## HTTP API

`uv run charwatch serve` then open http://127.0.0.1:8000/docs.

| Method & path | Purpose |
|---|---|
| `POST /runs` | Start an evaluation (background); returns `run_id` |
| `GET /runs/{run_id}` | Poll run status |
| `GET /runs/{run_id}/dimensions/{key}/receipts` | Flagged transcripts + majority evidence |
| `GET /runs/{run_id}/traces` | Raw responses, token/latency metadata, and every judge verdict |
| `GET /models/{model}/report-card` | Latest behavioral profile |
| `GET /models/{model}/dimensions/{key}/history` | Time series; accepts arbitrary ISO `start`/`end` bounds |
| `GET /monitors` | Persistent recurring model schedules and next run time |
| `POST /monitors` | Add a model; its first evaluation starts automatically |
| `PATCH /monitors/{id}` | Pause, resume, or change a monitor |
| `DELETE /monitors/{id}` | Remove a monitor without deleting stored runs |
| `GET /drift?model_a=…&model_b=…` | Two-proportion drift test per dimension |
| `GET /fingerprint?model_a=…&model_b=…` | Fingerprint divergence + verdict |
| `GET /dimensions` | Benchmark metadata |
| `GET /config` | Non-secret runtime capabilities for the dashboard |

## Configuration

All via `CHARWATCH_*` env vars (see `.env.example`). Notable: `JUDGE_MODELS` (panel, use
non-reasoning models — they support structured outputs), `SAMPLES_PER_CASE`, `MAX_CONCURRENCY`,
`DATABASE_URL` (SQLite by default, Postgres-ready), and the scheduler switch. Model IDs and
versions are not environment configuration: users add them in the dashboard and Sonar persists
them in the application database. The scheduler is enabled by default. Every enabled model is
evaluated automatically once per hour; the cadence is fixed so longitudinal data is comparable.
Evaluation runs, samples, judgments, and fingerprints remain append-only evidence.
On startup, a selected model with no prior run or an overdue run starts immediately; a model
evaluated within the last hour resumes at its next hourly due time.

## Notes on model choice

Judges must be **non-reasoning** models (`gpt-4.1`, `gpt-4o`) — reasoning models don't return
structured/logprob outputs. Targets can be anything. For a stable drift demo, the dated
`gpt-4o` snapshots are the cleanest "same alias, different weights" comparison.

## Scaling path

SQLite → Postgres (change `DATABASE_URL`). Background runs use in-process tasks now; the
runner/scheduler split is designed to move onto an `arq` + Redis worker pool without touching
domain logic. Use Alembic for migrations in production (dev auto-creates tables).
