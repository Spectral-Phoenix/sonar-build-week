import { useEffect, useState } from 'react'
import {
  ArrowClockwise,
  CheckCircle,
  Plus,
  Trash,
  WarningCircle,
} from '@phosphor-icons/react'
import { api } from '../api'
import { EmptyState, ErrorState, LoadingState } from '../components'
import { formatDate } from '../format'
import type { Monitor, MonitorCreate, RuntimeConfig } from '../types'

const emptyMonitor: MonitorCreate = {
  model: '',
  provider: 'openai',
  interval_hours: 1,
  samples_per_case: null,
  dimension_keys: null,
  with_fingerprint: true,
  enabled: true,
}

export function SettingsPage({ connection, onRetry }: { connection: 'checking' | 'online' | 'offline'; onRetry: () => Promise<void> }) {
  const [config, setConfig] = useState<RuntimeConfig | null>(null)
  const [monitors, setMonitors] = useState<Monitor[]>([])
  const [knownModels, setKnownModels] = useState<string[]>([])
  const [form, setForm] = useState<MonitorCreate>(emptyMonitor)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [runtime, storedMonitors, storedModels] = await Promise.all([
        api.config(),
        api.monitors(),
        api.models(),
      ])
      setConfig(runtime)
      setMonitors(storedMonitors)
      setKnownModels(storedModels)
      if (runtime.providers.length && !runtime.providers.includes(form.provider)) {
        setForm((current) => ({ ...current, provider: runtime.providers[0] }))
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load settings.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const addMonitor = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!form.model.trim()) return
    setSaving(true)
    setError('')
    try {
      await api.createMonitor({ ...form, model: form.model.trim() })
      setForm((current) => ({ ...emptyMonitor, provider: current.provider }))
      setNotice('Model monitor saved.')
      await load()
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Unable to save monitor.')
    } finally {
      setSaving(false)
    }
  }

  const updateMonitor = async (monitor: Monitor, values: Partial<MonitorCreate>) => {
    setBusyId(monitor.id)
    setError('')
    try {
      const updated = await api.updateMonitor(monitor.id, values)
      setMonitors((items) => items.map((item) => item.id === updated.id ? updated : item))
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : 'Unable to update monitor.')
    } finally {
      setBusyId('')
    }
  }

  const removeMonitor = async (monitor: Monitor) => {
    if (!window.confirm(`Stop monitoring ${monitor.model} and remove its schedule? Stored runs will remain.`)) return
    setBusyId(monitor.id)
    try {
      await api.deleteMonitor(monitor.id)
      setMonitors((items) => items.filter((item) => item.id !== monitor.id))
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Unable to remove monitor.')
    } finally {
      setBusyId('')
    }
  }

  return (
    <div className="page-scroll">
      <div className="page-content wide settings-content">
        <header className="page-heading">
          <div><h1>Settings</h1><p className="page-description">Manage the models and versions evaluated by Sonar every hour.</p></div>
          <button className="secondary-button icon-only" aria-label="Refresh settings" onClick={() => { void onRetry(); void load() }}><ArrowClockwise size={14} /></button>
        </header>

        {connection === 'offline' && <div className="inline-alert">Backend unavailable. Start the API and refresh this page.</div>}
        {error && <div className="inline-alert">{error}</div>}

        {loading ? <LoadingState label="Loading monitoring settings…" /> : !config ? <ErrorState message={error || 'Runtime configuration unavailable.'} onRetry={load} /> : (
          <main className="settings-sections">
            <section className="settings-add-model">
              <header><div><h2>Add model</h2><p>Use the exact provider model ID or versioned snapshot.</p></div></header>
              <form className="monitor-form-clean" onSubmit={addMonitor}>
                <div className="monitor-fields">
                  <label className="field-group model-id-field"><span>Model or version ID</span><input list="known-model-ids" value={form.model} onChange={(event) => setForm({ ...form, model: event.target.value })} placeholder="gpt-4o-2024-11-20" required /><datalist id="known-model-ids">{knownModels.map((model) => <option key={model} value={model} />)}</datalist></label>
                  <label className="field-group"><span>Provider</span><select value={form.provider} onChange={(event) => setForm({ ...form, provider: event.target.value })}><option value="openai">OpenAI</option><option value="openrouter">OpenRouter</option></select></label>
                  <label className="field-group"><span>Samples per question</span><input type="number" min="1" max="1000" value={form.samples_per_case ?? ''} placeholder={`Default · ${config.samples_per_case}`} onChange={(event) => setForm({ ...form, samples_per_case: event.target.value ? Number(event.target.value) : null })} /></label>
                </div>
                <div className="monitor-form-footer">
                  <label className="check-row compact-check"><input type="checkbox" checked={form.with_fingerprint} onChange={(event) => setForm({ ...form, with_fingerprint: event.target.checked })} /><span className="check-box">{form.with_fingerprint && <CheckCircle size={12} weight="fill" />}</span><span><strong>Identity fingerprint</strong><small>Detect endpoint or weight changes.</small></span></label>
                  <button className="primary-button" disabled={saving || !form.model.trim()}><Plus size={14} />{saving ? 'Adding…' : 'Add model'}</button>
                </div>
                {notice && <p className="settings-message success">{notice}</p>}
                {!config.evaluation_enabled && <p className="settings-message warning"><WarningCircle size={13} />A provider API key is required before evaluations can run.</p>}
              </form>
            </section>

            <section className="settings-monitoring">
              <header className="settings-section-heading"><div><h2>Monitored models</h2><p>Enabled models run once every hour.</p></div><span>{monitors.length}</span></header>
              {monitors.length ? <div className="monitor-list-clean">{monitors.map((monitor) => (
                <article className={`monitor-row ${monitor.enabled ? '' : 'paused'}`} key={monitor.id}>
                  <div className="monitor-identity"><h3>{monitor.model}</h3><p>{monitor.provider}</p></div>
                  <dl className="monitor-details">
                    <div><dt>Samples</dt><dd>{monitor.samples_per_case ?? config.samples_per_case} / question</dd></div>
                    <div><dt>Behaviors</dt><dd>{monitor.dimension_keys?.length ? monitor.dimension_keys.length : 'All'}</dd></div>
                    <div><dt>Next run</dt><dd>{monitor.next_run_at ? formatDate(monitor.next_run_at) : monitor.enabled ? 'Starting automatically' : 'Paused'}</dd></div>
                  </dl>
                  <div className="monitor-row-actions">
                    <label className="toggle-control" aria-label={`${monitor.enabled ? 'Pause' : 'Enable'} ${monitor.model}`}><input type="checkbox" checked={monitor.enabled} disabled={busyId === monitor.id} onChange={(event) => void updateMonitor(monitor, { enabled: event.target.checked })} /><span /><small>{monitor.enabled ? 'On' : 'Off'}</small></label>
                    <button className="quiet-icon-button danger" type="button" aria-label={`Remove ${monitor.model}`} disabled={busyId === monitor.id} onClick={() => void removeMonitor(monitor)}><Trash size={15} /></button>
                  </div>
                </article>
              ))}</div> : <EmptyState title="No monitored models" description="Add a model above to begin automatic hourly evaluations." />}
            </section>
          </main>
        )}
      </div>
    </div>
  )
}
