import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Badge, Button, Card, ErrorNote, Field, inputClass } from '../components/Bits'

export default function Send() {
  const [drafts, setDrafts] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [config, setConfig] = useState(null)
  const [testMode, setTestMode] = useState(true)
  const [testEmail, setTestEmail] = useState('')
  const [delay, setDelay] = useState(30)
  const [run, setRun] = useState(null)
  const [log, setLog] = useState([])
  const [error, setError] = useState(null)
  const closeStream = useRef(null)

  function loadDrafts() {
    api.get('/api/drafts?status=approved')
      .then((rows) => {
        setDrafts(rows)
        setSelected(new Set(rows.map((d) => d.id)))
      })
      .catch(setError)
  }

  useEffect(() => {
    loadDrafts()
    api.get('/api/runs/config')
      .then((body) => {
        setConfig(body)
        setTestEmail(body.test_email)
        setDelay(body.default_delay)
      })
      .catch(setError)
    return () => closeStream.current?.()
  }, [])

  function toggle(id) {
    setSelected((current) => {
      const next = new Set(current)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  async function start() {
    setError(null); setLog([])
    const draftIds = drafts.filter((d) => selected.has(d.id)).map((d) => d.id)
    try {
      const response = await api.post('/api/runs/send', {
        draft_ids: draftIds,
        test_mode: testMode,
        delay: Number(delay),
        test_email: testEmail,
      })
      setRun({ id: response.run_id, completed: 0, total: response.count, status: 'running' })
      closeStream.current = api.streamRun(response.run_id, (event) => {
        if (event.type === 'progress') {
          setRun((r) => ({ ...r, completed: event.completed, total: event.total }))
        } else if (event.type === 'item') {
          setLog((entries) => [...entries, event])
        } else if (event.type === 'skipped') {
          setLog((entries) => [...entries, { ...event, status: 'skipped' }])
        } else if (event.type === 'done') {
          setRun((r) => ({ ...r, status: event.status }))
          loadDrafts()
        } else if (event.type === 'error') {
          setError(new Error(event.message))
        }
      })
    } catch (e) { setError(e) }
  }

  async function stop() {
    await api.post(`/api/runs/${run.id}/stop`, {})
  }

  const selectedCount = selected.size
  const running = run?.status === 'running'

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold tracking-tight">Send</h1>
      <ErrorNote error={error} />

      {config && !config.gmail_configured && (
        <ErrorNote error={{ message: 'GMAIL_EMAIL / GMAIL_PASSWORD are not set in .env — sending will fail.' }} />
      )}

      {!testMode && (
        <div className="px-4 py-3 rounded-md border border-danger bg-danger/10 text-danger text-sm font-medium">
          LIVE MODE — {selectedCount} real founder{selectedCount === 1 ? '' : 's'} will be emailed.
        </div>
      )}

      <Card title="Run settings">
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex items-center gap-2 text-sm pb-2">
            <input type="checkbox" checked={testMode}
                   onChange={(e) => setTestMode(e.target.checked)} />
            Test mode
          </label>
          <Field label="Test address">
            <input className={`${inputClass} mono w-64`} value={testEmail} disabled={!testMode}
                   onChange={(e) => setTestEmail(e.target.value)} />
          </Field>
          <Field label="Delay (seconds)">
            <input className={inputClass} type="number" min="0" value={delay}
                   onChange={(e) => setDelay(e.target.value)} />
          </Field>
          <Button variant={testMode ? 'primary' : 'danger'} onClick={start}
                  disabled={!selectedCount || running}>
            {running ? `Sending ${run.completed}/${run.total}…`
                     : `Send ${selectedCount} ${testMode ? 'to test inbox' : 'for real'}`}
          </Button>
          {running && <Button onClick={stop}>Stop</Button>}
        </div>
        <p className="mt-3 text-xs text-muted">
          Roughly {Math.round((selectedCount * Number(delay)) / 60)} minute(s) at {delay}s between emails.
        </p>
      </Card>

      {(log.length > 0 || run) && (
        <Card title={`Run ${run?.id ?? ''} — ${run?.status ?? ''}`}>
          <ul className="space-y-1 text-sm mono max-h-72 overflow-y-auto">
            {log.map((entry, index) => (
              <li key={index} className="flex gap-2">
                <Badge tone={entry.status === 'sent' ? 'ok' : entry.status === 'failed' ? 'danger' : 'muted'}>
                  {entry.status}
                </Badge>
                <span className="truncate">
                  {entry.company_name || `draft ${entry.draft_id}`}
                  {entry.to_addr ? ` → ${entry.to_addr}` : ''}
                  {entry.error ? ` — ${entry.error}` : ''}
                  {entry.reason ? ` — ${entry.reason}` : ''}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title={`Approved drafts (${drafts.length})`}>
        {drafts.length === 0 ? (
          <p className="text-sm text-muted">
            Nothing approved yet. Approve drafts on the Compose screen first.
          </p>
        ) : (
          <ul className="divide-y divide-line">
            {drafts.map((draft) => (
              <li key={draft.id} className="py-2 flex gap-3 items-start">
                <input type="checkbox" className="mt-1" checked={selected.has(draft.id)}
                       onChange={() => toggle(draft.id)} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">
                    {draft.company_name}
                    <span className="text-muted font-normal"> · {draft.founder_name}</span>
                    {draft.round > 0 && <span className="ml-2"><Badge>round {draft.round}</Badge></span>}
                  </div>
                  <div className="mono text-xs text-muted">
                    {testMode ? `${testEmail} (test)` : draft.predicted_email}
                  </div>
                  <div className="text-sm mt-1">{draft.subject}</div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
