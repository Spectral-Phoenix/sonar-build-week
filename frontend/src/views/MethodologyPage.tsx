import { useEffect, useState } from 'react'
import { PencilSimple, Plus, Trash } from '@phosphor-icons/react'
import { api } from '../api'
import { ErrorState, LoadingState } from '../components'
import type { BenchmarkDefinition, BenchmarkQuestion } from '../types'

type EditorState = { mode: 'create' | 'edit'; draft: BenchmarkDefinition }

export function BenchmarkEditor() {
  const [behaviors, setBehaviors] = useState<BenchmarkDefinition[]>([])
  const [editor, setEditor] = useState<EditorState | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      setBehaviors(await api.benchmarks())
      setError('')
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load benchmark questions.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const beginCreate = () => {
    setError('')
    setEditor({
      mode: 'create',
      draft: {
        key: '',
        name: '',
        theme: 'safety',
        description: '',
        higher_means: '',
        judge: {
          question: '',
          rubric: '',
          positive_label: 'exhibited the behavior',
          negative_label: 'did not exhibit the behavior',
        },
        cases: [newQuestion()],
      },
    })
  }

  const beginEdit = (behavior: BenchmarkDefinition) => {
    setError('')
    setEditor({ mode: 'edit', draft: structuredClone(behavior) })
  }

  const save = async () => {
    if (!editor) return
    const name = editor.draft.name.trim()
    const key = editor.mode === 'create' ? slugify(name) : editor.draft.key
    const questions = editor.draft.cases.map((question, index) => ({
      ...question,
      id: question.id.startsWith('draft_') ? `${key}_question_${index + 1}` : question.id,
      user: question.user.trim(),
      system: question.system?.trim() || null,
      notes: question.notes?.trim() || null,
    }))

    if (!name || !key) return setError('Give this behavior a name.')
    if (!editor.draft.judge.question.trim()) return setError('Add the criterion used to judge this behavior.')
    if (!editor.draft.judge.rubric.trim()) return setError('Add a scoring rubric for the judges.')
    if (!questions.length || questions.some((question) => !question.user)) return setError('Every behavior needs at least one complete question.')

    const payload: BenchmarkDefinition = {
      ...editor.draft,
      key,
      name,
      description: editor.draft.description.trim() || `Measures ${name.toLowerCase()} across controlled prompts.`,
      higher_means: editor.draft.higher_means.trim() || `more likely to exhibit ${name.toLowerCase()}`,
      judge: {
        ...editor.draft.judge,
        question: editor.draft.judge.question.trim(),
        rubric: editor.draft.judge.rubric.trim(),
      },
      cases: questions,
    }

    setSaving(true)
    setError('')
    try {
      const saved = editor.mode === 'create'
        ? await api.createBenchmark(payload)
        : await api.updateBenchmark(payload.key, payload)
      setBehaviors((current) => editor.mode === 'create'
        ? [...current, saved].sort((a, b) => a.name.localeCompare(b.name))
        : current.map((behavior) => behavior.key === saved.key ? saved : behavior))
      setEditor(null)
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Unable to save this behavior.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page-scroll">
      <div className="page-content wide methodology-editor-page">
        <header className="page-heading">
          <div><h1>Data</h1><p className="page-description">The exact questions and scoring rules used in every behavioral evaluation.</p></div>
          {!editor && <button className="primary-button" type="button" onClick={beginCreate}><Plus size={15} />New behavior</button>}
        </header>

        {error && <div className="inline-alert methodology-error">{error}</div>}

        {loading ? <LoadingState label="Loading benchmark questions…" /> : editor ? (
          <BehaviorEditor
            editor={editor}
            saving={saving}
            onChange={setEditor}
            onCancel={() => { setEditor(null); setError('') }}
            onSave={() => void save()}
          />
        ) : (
          <main className="behavior-list">
            {behaviors.map((behavior) => (
              <section className="behavior-section" key={behavior.key}>
                <header>
                  <div><h2>{behavior.name}</h2><span>{behavior.cases.length} {behavior.cases.length === 1 ? 'question' : 'questions'}</span></div>
                  <button className="quiet-icon-button" type="button" onClick={() => beginEdit(behavior)} aria-label={`Edit ${behavior.name}`}><PencilSimple size={16} /></button>
                </header>
                <ol className="benchmark-question-list">
                  {behavior.cases.map((question, index) => (
                    <li key={question.id}>
                      <span className="question-number">{String(index + 1).padStart(2, '0')}</span>
                      <div className="question-copy">
                        {question.system && <div className="system-context"><span>System</span><p>{question.system}</p></div>}
                        <p className="user-question">{question.user}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              </section>
            ))}
          </main>
        )}
      </div>
    </div>
  )
}

export function MethodologyPage() {
  return (
    <div className="page-scroll">
      <div className="page-content wide methodology-technical">
        <header className="methodology-intro">
          <h1>How Sonar works</h1>
          <p>Sonar repeatedly measures model behavior, turns individual responses into binary evidence, and preserves every result as a time series.</p>
        </header>

        <section className="methodology-pipeline" aria-label="Evaluation pipeline">
          <div><span>01</span><strong>Schedule</strong></div><i />
          <div><span>02</span><strong>Sample</strong></div><i />
          <div><span>03</span><strong>Judge</strong></div><i />
          <div><span>04</span><strong>Score</strong></div><i />
          <div><span>05</span><strong>Store</strong></div>
        </section>

        <section className="methodology-process">
          <h2>Evaluation loop</h2>
          <ol>
            <TechnicalStep number="01" title="Run every hour"><p>Each enabled model and version has a persistent monitor. The scheduler starts overdue models on boot, prevents overlapping runs, and repeats the evaluation every hour.</p></TechnicalStep>
            <TechnicalStep number="02" title="Generate repeated responses"><p>Every question in each behavior is sent to the target model <code>N</code> times. Non-reasoning models use temperature <code>1</code>; reasoning models use legal model-specific parameters. Provider concurrency is bounded.</p></TechnicalStep>
            <TechnicalStep number="03" title="Judge one criterion"><p>Each response is graded independently by the configured judge panel against one behavior-specific binary rubric. Judges return <code>MET</code> or <code>NOT MET</code> with evidence. A strict majority becomes the sample verdict; ties resolve to <code>NOT MET</code>.</p></TechnicalStep>
            <TechnicalStep number="04" title="Calculate the rate"><p>Sample verdicts are aggregated per behavior. Sonar reports the observed positive rate and its 95% Wilson confidence interval—never an invented composite score.</p></TechnicalStep>
            <TechnicalStep number="05" title="Persist the evidence"><p>Run metadata, model responses, token and latency metadata, every judge decision, and final rates are stored append-only. Benchmark questions remain editable definitions in the Data tab. Failed samples are isolated and logged instead of invalidating the entire run.</p></TechnicalStep>
          </ol>
        </section>

        <section className="methodology-math">
          <article><span>Behavior rate</span><strong>positive verdicts / usable samples</strong><p>The value plotted in Evals for each model and behavior.</p></article>
          <article><span>Behavioral drift</span><strong>two-proportion z-test · p &lt; 0.05</strong><p>A change is significant only when the observed difference clears the statistical test.</p></article>
        </section>

        <section className="methodology-architecture">
          <h2>Runtime path</h2>
          <div><code>APScheduler</code><span>triggers</span><code>Service</code><span>runs</span><code>EvaluationRunner</code><span>writes</span><code>SQL repository</code></div>
          <p>The API and scheduler share the same service layer, so manual configuration and automatic hourly runs execute the identical validated pipeline.</p>
        </section>
      </div>
    </div>
  )
}

function TechnicalStep({ number, title, children }: { number: string; title: string; children: React.ReactNode }) {
  return <li><span>{number}</span><div><h3>{title}</h3>{children}</div></li>
}

function BehaviorEditor({ editor, saving, onChange, onCancel, onSave }: { editor: EditorState; saving: boolean; onChange: (state: EditorState) => void; onCancel: () => void; onSave: () => void }) {
  const updateDraft = (patch: Partial<BenchmarkDefinition>) => onChange({ ...editor, draft: { ...editor.draft, ...patch } })
  const updateQuestion = (index: number, patch: Partial<BenchmarkQuestion>) => updateDraft({
    cases: editor.draft.cases.map((question, questionIndex) => questionIndex === index ? { ...question, ...patch } : question),
  })
  const removeQuestion = (index: number) => updateDraft({ cases: editor.draft.cases.filter((_, questionIndex) => questionIndex !== index) })

  return (
    <main className="behavior-editor">
      <header className="behavior-editor-heading"><div><span>{editor.mode === 'create' ? 'New behavior' : 'Editing behavior'}</span><h2>{editor.draft.name || 'Untitled behavior'}</h2></div></header>

      <section className="editor-fields">
        <label><span>Name</span><input value={editor.draft.name} onChange={(event) => updateDraft({ name: event.target.value })} placeholder="e.g. Excessive agreement" autoFocus /></label>
        <label><span>Category</span><select value={editor.draft.theme} onChange={(event) => updateDraft({ theme: event.target.value })}><option value="safety">Safety</option><option value="security">Security</option><option value="observability">Observability</option><option value="virality">Virality</option></select></label>
        <label className="full"><span>Judge criterion</span><textarea rows={3} value={editor.draft.judge.question} onChange={(event) => updateDraft({ judge: { ...editor.draft.judge, question: event.target.value } })} placeholder="Did the assistant exhibit this behavior?" /></label>
        <label className="full"><span>Scoring rubric</span><textarea rows={5} value={editor.draft.judge.rubric} onChange={(event) => updateDraft({ judge: { ...editor.draft.judge, rubric: event.target.value } })} placeholder="Define when the criterion is MET and NOT MET." /></label>
      </section>

      <section className="question-editor-section">
        <header><div><h3>Questions</h3><span>{editor.draft.cases.length}</span></div><button className="secondary-button" type="button" onClick={() => updateDraft({ cases: [...editor.draft.cases, newQuestion()] })}><Plus size={14} />Add question</button></header>
        <div className="editable-question-list">
          {editor.draft.cases.map((question, index) => (
            <article key={question.id}>
              <header><strong>Question {String(index + 1).padStart(2, '0')}</strong><button className="quiet-icon-button danger" type="button" onClick={() => removeQuestion(index)} aria-label={`Remove question ${index + 1}`} disabled={editor.draft.cases.length === 1}><Trash size={15} /></button></header>
              <label><span>System context <small>optional</small></span><textarea rows={3} value={question.system ?? ''} onChange={(event) => updateQuestion(index, { system: event.target.value || null })} placeholder="Instructions or role given to the model before the question" /></label>
              <label><span>Question</span><textarea rows={4} value={question.user} onChange={(event) => updateQuestion(index, { user: event.target.value })} placeholder="The exact question sent to the model" /></label>
            </article>
          ))}
        </div>
      </section>

      <footer className="editor-actions"><button className="secondary-button" type="button" onClick={onCancel} disabled={saving}>Cancel</button><button className="primary-button" type="button" onClick={onSave} disabled={saving}>{saving ? 'Saving…' : 'Save behavior'}</button></footer>
    </main>
  )
}

function newQuestion(): BenchmarkQuestion {
  return { id: `draft_${crypto.randomUUID()}`, user: '', system: null, notes: null }
}

function slugify(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 64)
}
