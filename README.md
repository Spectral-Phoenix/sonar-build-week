# Sonar

Sonar is split into a React frontend and a Python/FastAPI evaluation backend.

## Demo

[Watch the Sonar product walkthrough on Loom](https://www.loom.com/share/0372e7aa51404affbd1cf6a1f42ceb68)

The backend automatically evaluates every enabled model once per hour using schedules saved from
**Settings**. The first run starts when a model is added—there is no manual evaluation button. Results are
stored as append-only runs, samples, judge decisions, and fingerprints. **Data** supports preset
or custom time ranges and exposes the raw trace behind each run; **Methodology** explains the
rate, confidence interval, and drift test in plain language.

Model and version IDs are selected or entered by users in **Settings** and stored in the database;
they are not configured through environment variables.

## Local development

Start the backend in one terminal:

```bash
cd backend
uv sync --extra dev
cp .env.example .env
# Set CHARWATCH_OPENAI_API_KEY in .env to enable evaluation runs.
uv run charwatch serve --reload
```

Start the frontend in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:3016`. Vite forwards `/api/*` to the backend at
`http://127.0.0.1:8000` and removes the `/api` prefix.

For a separately hosted API, set `VITE_API_BASE_URL` in the frontend environment. In a
same-origin production deployment, configure the reverse proxy to forward `/api/*` to FastAPI
with the prefix removed.

## Verification

```bash
cd backend && uv run pytest -q && uv run ruff check .
cd frontend && npm run build
```
