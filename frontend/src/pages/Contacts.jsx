import { useEffect, useState } from 'react'
import { api } from '../api'
import { Badge, Button, Card, ErrorNote, Field, inputClass, Spinner } from '../components/Bits'

export default function Contacts() {
  const [search, setSearch] = useState('')
  const [batch, setBatch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [batches, setBatches] = useState([])
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(null)
  const [editValue, setEditValue] = useState('')
  const [scrapeBatch, setScrapeBatch] = useState('W26')
  const [scrapeMax, setScrapeMax] = useState(20)
  const [scrapeNote, setScrapeNote] = useState('')

  const perPage = 50

  function load() {
    const params = new URLSearchParams({ page, per_page: perPage })
    if (search) params.set('search', search)
    if (batch) params.set('batch', batch)
    if (status) params.set('status', status)
    api.get(`/api/contacts?${params}`).then(setData).catch(setError)
  }

  useEffect(load, [search, batch, status, page])
  useEffect(() => {
    api.get('/api/contacts/batches').then(setBatches).catch(setError)
  }, [])

  async function saveEmail(contact) {
    setError(null)
    try {
      await api.patch(`/api/contacts/${contact.id}`, { predicted_email: editValue })
      setEditing(null)
      load()
    } catch (e) {
      setError(e)
    }
  }

  async function toggleSkip(contact) {
    setError(null)
    try {
      await api.patch(`/api/contacts/${contact.id}`, {
        status: contact.status === 'active' ? 'skipped' : 'active',
      })
      load()
    } catch (e) {
      setError(e)
    }
  }

  async function startScrape() {
    setError(null)
    setScrapeNote('Scraping…')
    try {
      const { run_id } = await api.post('/api/runs/scrape', {
        batch: scrapeBatch,
        max: Number(scrapeMax),
      })
      api.streamRun(run_id, (event) => {
        if (event.type === 'done') {
          setScrapeNote(event.status === 'done' ? 'Scrape finished.' : `Scrape ${event.status}: ${event.error || ''}`)
          load()
        }
      })
    } catch (e) {
      setScrapeNote('')
      setError(e)
    }
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / perPage)) : 1

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold tracking-tight">Contacts</h1>
      <ErrorNote error={error} />

      <Card title="Scrape a new batch">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Batch code">
            <input className={inputClass} value={scrapeBatch}
                   onChange={(e) => setScrapeBatch(e.target.value)} placeholder="W26" />
          </Field>
          <Field label="Max companies">
            <input className={inputClass} type="number" min="1" value={scrapeMax}
                   onChange={(e) => setScrapeMax(e.target.value)} />
          </Field>
          <Button variant="primary" onClick={startScrape}>Scrape</Button>
          {scrapeNote && <span className="text-sm text-muted">{scrapeNote}</span>}
        </div>
      </Card>

      <div className="flex flex-wrap gap-3 items-end">
        <Field label="Search">
          <input className={inputClass} value={search} placeholder="company, founder, email"
                 onChange={(e) => { setPage(1); setSearch(e.target.value) }} />
        </Field>
        <Field label="Batch">
          <select className={inputClass} value={batch}
                  onChange={(e) => { setPage(1); setBatch(e.target.value) }}>
            <option value="">All batches</option>
            {batches.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </Field>
        <Field label="Status">
          <select className={inputClass} value={status}
                  onChange={(e) => { setPage(1); setStatus(e.target.value) }}>
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="skipped">Skipped</option>
          </select>
        </Field>
      </div>

      {!data ? <Spinner /> : (
        <Card title={`${data.total} contacts`}>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted text-left">
              <tr>
                <th className="pb-2 font-medium">Founder</th>
                <th className="pb-2 font-medium">Company</th>
                <th className="pb-2 font-medium">Batch</th>
                <th className="pb-2 font-medium">Email</th>
                <th className="pb-2 font-medium">State</th>
                <th className="pb-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((c) => (
                <tr key={c.id} className="border-t border-line align-top">
                  <td className="py-2">{c.founder_name}<div className="text-xs text-muted">{c.founder_title}</div></td>
                  <td className="py-2">{c.company_name}</td>
                  <td className="py-2 text-muted">{c.batch}</td>
                  <td className="py-2">
                    {editing === c.id ? (
                      <div className="flex gap-1.5">
                        <input className={`${inputClass} mono`} value={editValue}
                               onChange={(e) => setEditValue(e.target.value)} />
                        <Button variant="primary" onClick={() => saveEmail(c)}>Save</Button>
                        <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
                      </div>
                    ) : (
                      <button className="mono text-left hover:text-accent"
                              onClick={() => { setEditing(c.id); setEditValue(c.predicted_email) }}>
                        {c.predicted_email}
                      </button>
                    )}
                  </td>
                  <td className="py-2 space-x-1">
                    {c.contacted && <Badge tone="ok">contacted</Badge>}
                    {c.status === 'skipped' && <Badge tone="danger">skipped</Badge>}
                  </td>
                  <td className="py-2 text-right">
                    <Button variant="ghost" onClick={() => toggleSkip(c)}>
                      {c.status === 'active' ? 'Skip' : 'Unskip'}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="flex items-center justify-between pt-3 text-sm text-muted">
            <Button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}>
              Previous
            </Button>
            <span>Page {page} of {totalPages}</span>
            <Button onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}>
              Next
            </Button>
          </div>
        </Card>
      )}
    </div>
  )
}
