export type RunStatus = 'running' | 'completed' | 'failed' | string

export interface HealthResponse {
  status: string
}

export interface RuntimeConfig {
  providers: string[]
  evaluation_enabled: boolean
  judge_models: string[]
  samples_per_case: number
  max_concurrency: number
  scheduler_enabled: boolean
  database_dialect: string
}

export interface DimensionInfo {
  key: string
  name: string
  theme: 'safety' | 'security' | 'virality' | string
  description: string
  higher_means: string
}

export interface BenchmarkQuestion {
  id: string
  user: string
  system: string | null
  notes: string | null
}

export interface JudgeDefinition {
  question: string
  rubric: string
  positive_label: string
  negative_label: string
}

export interface BenchmarkDefinition extends DimensionInfo {
  judge: JudgeDefinition
  cases: BenchmarkQuestion[]
}

export interface Run {
  run_id: string
  model: string
  status: RunStatus
  created_at: string
  samples_per_case: number
  judge_models: string[]
  notes: string | null
}

export interface RunStarted {
  run_id: string
  status: string
}

export interface EvaluateRequest {
  model: string
  provider: string
  dimension_keys: string[] | null
  samples_per_case: number | null
  with_fingerprint: boolean
}

export interface DimensionResult {
  dimension_key: string
  model: string
  n_samples: number
  n_positive: number
  rate: number
  ci_low: number
  ci_high: number
  ci_method: string
}

export interface ReportCard {
  model: string
  run_id: string
  created_at: string
  dimensions: DimensionResult[]
}

export interface HistoryPoint {
  created_at: string
  run_id: string
  rate: number
  ci_low: number
  ci_high: number
  n_samples: number
}

export interface Receipt {
  dimension_key: string
  case_id: string
  sample_index: number
  model: string
  text: string
  votes_met: number
  votes_total: number
  evidence: string[]
}

export interface DriftResult {
  dimension_key: string
  model_a: string
  model_b: string
  rate_a: number
  rate_b: number
  n_a: number
  n_b: number
  delta: number
  z_stat: number
  p_value: number
  significant: boolean
  direction: 'increased' | 'decreased' | 'stable' | string
}

export interface FingerprintComparison {
  model_a: string
  model_b: string
  distance: number
  verdict: 'same' | 'uncertain' | 'different' | string
}

export interface Monitor {
  id: string
  model: string
  provider: string
  interval_hours: number
  samples_per_case: number | null
  dimension_keys: string[] | null
  with_fingerprint: boolean
  enabled: boolean
  created_at: string
  updated_at: string
  next_run_at: string | null
}

export interface MonitorCreate {
  model: string
  provider: string
  interval_hours: number
  samples_per_case: number | null
  dimension_keys: string[] | null
  with_fingerprint: boolean
  enabled: boolean
}

export type MonitorUpdate = Partial<MonitorCreate>

export interface TraceJudgment {
  judge_model: string
  criterion_met: boolean
  evidence: string
}

export interface Trace {
  id: number
  run_id: string
  model: string
  dimension_key: string
  case_id: string
  sample_index: number
  text: string
  finish_reason: string | null
  prompt_tokens: number | null
  completion_tokens: number | null
  latency_ms: number | null
  judgments: TraceJudgment[]
}
