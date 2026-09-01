import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Button, Card, ErrorNote, inputClass } from '../components/Bits'
import DraftCard from '../components/DraftCard'

const GAPS = { 1: '3+ days after the initial email', 2: '4+ days after follow-up #1', 3: '5+ days after follow-up #2' }

export default function Followups() {
  const [domains, setDomains] = useState([])
  const [domain, setDomain] = useState('job')
  const [due, setDue] = useState(null)
  const [round, setRound] = useState(1)
  const [drafts, setDrafts] = useState([])
  const [progress, setProgress] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/api/templates/domains').then(setDomains).catch(setError)
  }, [])

  function loadDue() {
    api.get(`/api/followups/due?domain=${domain}`).then(setDue).catch(setError)
  }

  function loadDrafts() {
    api.get(`/api/drafts?domain=${domain}&round=${round}`)
      .then((rows) => setDrafts(rows.filter((d) => ['pending', 'approved', 'failed'].includes(d.status))))
      .catch(setError)
  }

  useEffect(() => { loadDue() }, [domain])
  useEffect(() => { loadDrafts() }, [domain, round])

  async function generate() {
    const items = due?.[String(round)]?.items ?? []
    if (!items.length) return
    setError(null)
    setProgress({ completed: 0, total: items.length })
    try {
      const { run_id } = await api.post('/api/runs/generate', {
        contact_ids: items.map((c) => c.id),
        domain,
        round: Number(round),
      })
      api.streamRun(run_id, (event) => {
        if (event.type === 'progress') setProgress({ completed: event.completed, total: event.total })
        if (event.type === 'done') { setProgress(null); loadDrafts(); loadDue() }
      })
    } catch (e) { setProgress(null); setError(e) }
  }

  function replaceDraft(updated, replacedId) {
    setDrafts((current) => {
      const withoutOld = current.filter((d) => d.id !== (replacedId ?? updated.id))
      if (['rejected', 'sent'].includes(updated.status)) return withoutOld
      return [updated, ...withoutOld].sort((a, b) => b.id - a.id)
    })
  }

  const current = due?.[String(round)]

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Follow-ups</h1>
        <select className={`${inputClass} w-56`} value={domain}
                onChange={(e) => setDomain(e.target.value)}>
          {domains.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>
      <ErrorNote error={error} />

      <div className="flex gap-2">
        {[1, 2, 3].map((n) => (
          <button key={n} onClick={() => setRound(n)}
                  className={`px-3 py-1.5 text-sm rounded-md border ${
                    n === round ? 'bg-accent/10 border-accent/30 text-accent font-medium'
                                : 'bg-surface border-line text-muted hover:bg-paper'
                  }`}>
            Round {n}
            <span className="ml-2 tabular-nums">{due ? due[String(n)].count : '—'}</span>
          </button>
        ))}
      </div>

      <Card
        title={`Due for follow-up #${round}`}
        action={
          <Button variant="primary" onClick={generate}
                  disabled={!current?.count || progress !== null}>
            {progress ? `Generating ${progress.completed}/${progress.total}…`
                      : `Generate ${current?.count ?? 0} drafts`}
          </Button>
        }
      >
        <p className="text-xs text-muted mb-3">
          {GAPS[round]}. Nothing sends from this screen — generated drafts go to
          the review queue, then to <Link to="/send" className="text-accent hover:underline">Send</Link>.
        </p>
        {!current ? (
          <p className="text-sm text-muted">Loading…</p>
        ) : current.count === 0 ? (
          <p className="text-sm text-muted">Nobody is due yet for this round.</p>
        ) : (
          <ul className="divide-y divide-line text-sm">
            {current.items.map((contact) => (
              <li key={contact.id} className="py-2 flex justify-between gap-3">
                <span>
                  {contact.company_name}
                  <span className="text-muted"> · {contact.founder_name}</span>
                </span>
                <span className="mono text-xs text-muted">
                  last contact {contact.history?.followups?.slice(-1)[0] || contact.history?.sent_at}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {drafts.length > 0 && (
        <>
          <h2 className="text-sm font-semibold tracking-tight">
            Round {round} drafts to review ({drafts.length})
          </h2>
          <div className="grid gap-4 xl:grid-cols-2">
            {drafts.map((draft) => (
              <DraftCard key={draft.id} draft={draft} onChange={replaceDraft} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
