import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowClockwise, Info } from '@phosphor-icons/react'
import { Liveline, type LivelinePoint, type LivelineSeries } from 'liveline'
import { api } from '../api'
import { EmptyState, ErrorState, LoadingState } from '../components'
import type { DimensionInfo, HistoryPoint } from '../types'

const MODEL_COLORS = ['#2563eb', '#dc2626', '#16a34a', '#9333ea', '#d97706', '#0891b2']
const WINDOWS = [
  { label: '24h', secs: 86_400 },
  { label: '7d', secs: 604_800 },
  { label: '30d', secs: 2_592_000 },
  { label: '90d', secs: 7_776_000 },
]

const DEFAULT_WINDOW = WINDOWS[2].secs

type HistoryMap = Record<string, Record<string, HistoryPoint[]>>

export function EvalsPage({ dark }: { dark: boolean }) {
  const [dimensions, setDimensions] = useState<DimensionInfo[]>([])
  const [models, setModels] = useState<string[]>([])
  const [histories, setHistories] = useState<HistoryMap>({})
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async (initial = false) => {
    if (initial) setLoading(true)
    else setRefreshing(true)
    setError('')
    try {
      const [dimensionData, modelData] = await Promise.all([
        api.dimensions(),
        api.models(),
      ])
      const orderedModels = [...modelData].sort((a, b) => a.localeCompare(b))
      const historyEntries = await Promise.all(
        orderedModels.flatMap((model) => dimensionData.map(async (dimension) => ({
          model,
          dimension: dimension.key,
          points: await api.history(model, dimension.key, { limit: 1000 }),
        }))),
      )
      const nextHistories: HistoryMap = {}
      for (const entry of historyEntries) {
        nextHistories[entry.model] ??= {}
        nextHistories[entry.model][entry.dimension] = entry.points
      }
      setDimensions(dimensionData)
      setModels(orderedModels)
      setHistories(nextHistories)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load evaluation history.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void load(true)
    const interval = window.setInterval(() => void load(), 15_000)
    return () => window.clearInterval(interval)
  }, [load])

  const colors = useMemo(
    () => new Map(models.map((model, index) => [model, MODEL_COLORS[index % MODEL_COLORS.length]])),
    [models],
  )

  if (loading) return <LoadingState label="Loading evaluation history…" />
  if (error && !models.length) return <ErrorState message={error} onRetry={() => void load(true)} />

  return (
    <div className="page-scroll">
      <div className="page-content wide evals-dashboard">
        <header className="page-heading">
          <div><h1>Evals</h1><p className="page-description">Hourly measurements across every monitored model and version.</p></div>
          <button className="secondary-button icon-only eval-refresh" onClick={() => void load()} aria-label="Refresh evaluation data" disabled={refreshing}><ArrowClockwise size={15} className={refreshing ? 'spin' : ''} /></button>
        </header>

        {error && <div className="inline-alert">{error}</div>}

        {!models.length ? <EmptyState title="No monitored models" description="Add a model or version in Settings to start hourly evaluations." /> : <>
          <section className="property-history-section">
            <div className="eval-section-heading"><h2>Behavioral properties</h2></div>
            <div className="property-list">{dimensions.map((dimension) => <PropertyChart key={dimension.key} dimension={dimension} models={models} histories={histories} colors={colors} dark={dark} />)}</div>
          </section>
        </>}
      </div>
    </div>
  )
}

function PropertyChart({ dimension, models, histories, colors, dark }: { dimension: DimensionInfo; models: string[]; histories: HistoryMap; colors: Map<string, string>; dark: boolean }) {
  const series: LivelineSeries[] = models.map((model) => {
    const points = histories[model]?.[dimension.key] ?? []
    const data = toRenderableLivelineData(points)
    return { id: model, label: model, color: colors.get(model) ?? MODEL_COLORS[0], data, value: data.at(-1)?.value ?? 0 }
  })
  return (
    <article className="property-panel">
      <ChartTitle title={dimension.name} tooltip={`${dimension.description} Higher means ${dimension.higher_means}.`} />
      <div className="property-chart-canvas"><Liveline data={[]} value={0} series={series} theme={dark ? 'dark' : 'light'} window={DEFAULT_WINDOW} windows={WINDOWS} windowStyle="text" grid scrub pulse={false} padding={{ top: 18, right: 14, bottom: 28, left: 8 }} style={{ height: 'calc(100% - 28px)' }} emptyText="Awaiting the first completed evaluation" formatValue={(value) => `${value.toFixed(1)}%`} formatTime={formatChartTime} /></div>
    </article>
  )
}

function ChartTitle({ title, tooltip }: { title: string; tooltip: string }) {
  return <div className="metric-title-row"><h3>{title}</h3><button type="button" className="metric-info" aria-label={tooltip} data-tooltip={tooltip}><Info size={13} weight="regular" /></button></div>
}

function toRenderableLivelineData(points: HistoryPoint[]): LivelinePoint[] {
  const data = points
    .map((point) => ({
      time: new Date(point.created_at).getTime() / 1000,
      value: point.rate * 100,
    }))
    .sort((a, b) => a.time - b.time)

  if (data.length !== 1) return data

  // Liveline intentionally treats fewer than two points as empty. This display-only anchor
  // gives the first real observation a drawable segment and endpoint without inventing a
  // second measured value. It disappears naturally as soon as the next hourly run completes.
  return [{ time: data[0].time - 60, value: data[0].value }, data[0]]
}

const formatChartTime = (time: number) => new Date(time * 1000).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric' })
