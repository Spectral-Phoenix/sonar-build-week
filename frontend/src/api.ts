import type {
  BenchmarkDefinition,
  DimensionInfo,
  DriftResult,
  EvaluateRequest,
  FingerprintComparison,
  HealthResponse,
  HistoryPoint,
  Monitor,
  MonitorCreate,
  MonitorUpdate,
  Receipt,
  ReportCard,
  Run,
  RunStarted,
  RuntimeConfig,
  Trace,
} from './types'

const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim()
export const API_BASE = (configuredBase || '/api').replace(/\/$/, '')

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function queryString(values: Record<string, string | number | undefined>) {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== '') params.set(key, String(value))
  })
  const query = params.toString()
  return query ? `?${query}` : ''
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // Preserve the HTTP status text when the error body is not JSON.
    }
    throw new ApiError(message, response.status)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const segment = (value: string) => encodeURIComponent(value)

export const api = {
  health: () => request<HealthResponse>('/health'),
  config: () => request<RuntimeConfig>('/config'),
  dimensions: () => request<DimensionInfo[]>('/dimensions'),
  benchmarks: () => request<BenchmarkDefinition[]>('/benchmarks'),
  createBenchmark: (payload: BenchmarkDefinition) => request<BenchmarkDefinition>('/benchmarks', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  updateBenchmark: (key: string, payload: BenchmarkDefinition) =>
    request<BenchmarkDefinition>(`/benchmarks/${segment(key)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  models: () => request<string[]>('/models'),
  runs: (model?: string, limit = 50) =>
    request<Run[]>(`/runs${queryString({ model, limit })}`),
  run: (runId: string) => request<Run>(`/runs/${segment(runId)}`),
  startRun: (payload: EvaluateRequest) =>
    request<RunStarted>('/runs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  reportCard: (model: string, runId?: string) =>
    request<ReportCard>(
      `/models/${segment(model)}/report-card${queryString({ run_id: runId })}`,
    ),
  history: (
    model: string,
    dimensionKey: string,
    options: { limit?: number; start?: string; end?: string } = {},
  ) =>
    request<HistoryPoint[]>(
      `/models/${segment(model)}/dimensions/${segment(dimensionKey)}/history${queryString({ limit: options.limit ?? 500, start: options.start, end: options.end })}`,
    ),
  traces: (
    runId: string,
    options: { dimensionKey?: string; caseId?: string; limit?: number; offset?: number } = {},
  ) => request<Trace[]>(
    `/runs/${segment(runId)}/traces${queryString({ dimension_key: options.dimensionKey, case_id: options.caseId, limit: options.limit ?? 100, offset: options.offset ?? 0 })}`,
  ),
  monitors: () => request<Monitor[]>('/monitors'),
  createMonitor: (payload: MonitorCreate) => request<Monitor>('/monitors', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  updateMonitor: (monitorId: string, payload: MonitorUpdate) =>
    request<Monitor>(`/monitors/${segment(monitorId)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteMonitor: (monitorId: string) => request<void>(`/monitors/${segment(monitorId)}`, {
    method: 'DELETE',
  }),
  receipts: (runId: string, dimensionKey: string, limit = 10) =>
    request<Receipt[]>(
      `/runs/${segment(runId)}/dimensions/${segment(dimensionKey)}/receipts${queryString({ limit })}`,
    ),
  drift: (modelA: string, modelB: string, runA?: string, runB?: string) =>
    request<DriftResult[]>(
      `/drift${queryString({ model_a: modelA, model_b: modelB, run_a: runA, run_b: runB })}`,
    ),
  fingerprint: (modelA: string, modelB: string, runA?: string, runB?: string) =>
    request<FingerprintComparison>(
      `/fingerprint${queryString({ model_a: modelA, model_b: modelB, run_a: runA, run_b: runB })}`,
    ),
}
