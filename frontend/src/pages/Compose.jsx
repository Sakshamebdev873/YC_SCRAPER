import { useEffect, useState } from 'react'
import { api } from '../api'
import { Button, Card, ErrorNote, Field, inputClass } from '../components/Bits'
import DraftCard from '../components/DraftCard'

export default function Compose() {
  const [domains, setDomains] = useState([])
  const [domain, setDomain] = useState('job')
  const [batches, setBatches] = useState([])
  const [batch, setBatch] = useState('')
  const [round, setRound] = useState(0)
  const [limit, setLimit] = useState(10)
  const [queue, setQueue] = useState(null)
  const [drafts, setDrafts] = useState([])
  const [progress, setProgress] = useState(null)
  const [error, setError] = useState(null)
  const [leadCount, setLeadCount] = useState(5)

  const isSales = domain.startsWith('sales')

  useEffect(() => {
    api.get('/api/templates/domains').then(setDomains).catch(setError)
    api.get('/api/contacts/batches').then(setBatches).catch(setError)
  }, [])

  function loadQueue() {
    const params = new URLSearchParams({ domain, round, limit })
    if (batch) params.set('batch', batch)
    api.get(`/api/queue?${params}`).then(setQueue).catch(setError)
  }

  function loadDrafts() {
    api.get(`/api/drafts?domain=${domain}&round=${round}`)
      .then((rows) => setDrafts(rows.filter((d) => ['pending', 'approved', 'failed'].includes(d.status))))
      .catch(setError)
  }

  useEffect(() => { loadQueue(); loadDrafts() }, [domain, batch, round, limit])

  async function generate() {
    if (!queue?.items.length) return
    setError(null)
    setProgress({ completed: 0, total: queue.items.length })
    try {
      const { run_id } = await api.post('/api/runs/generate', {
        contact_ids: queue.items.map((c) => c.id),
        domain,
        round: Number(round),
      })
      api.streamRun(run_id, (event) => {
        if (event.type === 'progress') setProgress({ completed: event.completed, total: event.total })
        if (event.type === 'item') loadDrafts()
        if (event.type === 'done') { setProgress(null); loadDrafts(); loadQueue() }
      })
    } catch (e) { setProgress(null); setError(e) }
  }

  async function makeLeads() {
    setError(null)
    try {
      await api.post('/api/queue/leads', { domain, count: Number(leadCount) })
      loadQueue()
    } catch (e) { setError(e) }
  }

  async function approveAll() {
    const ids = drafts.filter((d) => d.status === 'pending').map((d) => d.id)
    if (!ids.length) return
    setError(null)
    try {
      await api.post('/api/drafts/bulk-status', { draft_ids: ids, status: 'approved' })
      loadDrafts()
    } catch (e) { setError(e) }
  }

  function replaceDraft(updated, replacedId) {
    setDrafts((current) => {
      const withoutOld = current.filter((d) => d.id !== (replacedId ?? updated.id))
      if (['rejected', 'sent'].includes(updated.status)) return withoutOld
      return [updated, ...withoutOld].sort((a, b) => b.id - a.id)
    })
  }

  const pendingCount = drafts.filter((d) => d.status === 'pending').length

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold tracking-tight">Compose</h1>
      <ErrorNote error={error} />

      <Card title="Queue">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Domain">
            <select className={inputClass} value={domain} onChange={(e) => setDomain(e.target.value)}>
              {domains.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </Field>
          <Field label="Batch">
            <select className={inputClass} value={batch} onChange={(e) => setBatch(e.target.value)}
                    disabled={isSales}>
              <option value="">All batches</option>
              {batches.map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </Field>
          <Field label="Round">
            <select className={inputClass} value={round} onChange={(e) => setRound(Number(e.target.value))}>
              <option value={0}>Initial</option>
              <option value={1}>Follow-up 1</option>
              <option value={2}>Follow-up 2</option>
              <option value={3}>Follow-up 3</option>
            </select>
          </Field>
          <Field label="Limit">
            <input className={inputClass} type="number" min="1" value={limit}
                   onChange={(e) => setLimit(Number(e.target.value))} />
          </Field>
          <Button variant="primary" onClick={generate}
                  disabled={!queue?.items.length || progress !== null}>
            {progress ? `Generating ${progress.completed}/${progress.total}…`
                      : `Generate ${queue?.total ?? 0} drafts`}
          </Button>
        </div>

        {isSales && (
          <div className="flex items-end gap-3 mt-4 pt-4 border-t border-line">
            <Field label="Placeholder leads">
              <input className={inputClass} type="number" min="1" value={leadCount}
                     onChange={(e) => setLeadCount(e.target.value)} />
            </Field>
            <Button onClick={makeLeads}>Generate leads</Button>
            <span className="text-xs text-muted pb-2">
              No real sales-lead list yet — these are synthetic companies.
            </span>
          </div>
        )}

        <p className="mt-3 text-sm text-muted">
          {queue ? `${queue.total} eligible contact${queue.total === 1 ? '' : 's'} (one per company, already-contacted excluded).`
                 : 'Loading queue…'}
        </p>
      </Card>

      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-tight">
          Drafts to review ({drafts.length})
        </h2>
        <Button onClick={approveAll} disabled={!pendingCount}>
          Approve all {pendingCount} pending
        </Button>
      </div>

      {drafts.length === 0 ? (
        <p className="text-sm text-muted">No drafts yet — generate some above.</p>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {drafts.map((draft) => (
            <DraftCard key={draft.id} draft={draft} onChange={replaceDraft} />
          ))}
        </div>
      )}
    </div>
  )
}
