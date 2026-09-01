import { useEffect, useState } from 'react'
import { api } from '../api'
import { Badge, Button, ErrorNote, inputClass } from './Bits'

const TONE = { pending: 'warn', approved: 'ok', rejected: 'muted', sent: 'ok', failed: 'danger' }

export default function DraftCard({ draft, onChange }) {
  const [subject, setSubject] = useState(draft.subject)
  const [body, setBody] = useState(draft.body)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState(null)

  useEffect(() => {
    setSubject(draft.subject)
    setBody(draft.body)
  }, [draft.id, draft.subject, draft.body])

  const dirty = subject !== draft.subject || body !== draft.body

  async function patch(payload, label) {
    setBusy(label); setError(null)
    try {
      onChange(await api.patch(`/api/drafts/${draft.id}`, payload))
    } catch (e) { setError(e) } finally { setBusy('') }
  }

  async function regenerate() {
    setBusy('regen'); setError(null)
    try {
      onChange(await api.post(`/api/drafts/${draft.id}/regenerate`), draft.id)
    } catch (e) { setError(e) } finally { setBusy('') }
  }

  return (
    <article className="bg-surface border border-line rounded-lg">
      <header className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-line">
        <div className="min-w-0">
          <div className="text-sm font-medium truncate">
            {draft.company_name} <span className="text-muted font-normal">· {draft.founder_name}</span>
          </div>
          <div className="mono text-xs text-muted truncate">{draft.predicted_email}</div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {draft.round > 0 && <Badge>round {draft.round}</Badge>}
          <Badge tone={TONE[draft.status]}>{draft.status}</Badge>
        </div>
      </header>

      <div className="p-4 space-y-3">
        {draft.error && <ErrorNote error={{ message: draft.error }} />}
        <ErrorNote error={error} />
        <input className={`${inputClass} mono`} value={subject}
               onChange={(e) => setSubject(e.target.value)} />
        <textarea className={`${inputClass} mono h-48 leading-relaxed whitespace-pre-wrap`}
                  value={body} spellCheck={false}
                  onChange={(e) => setBody(e.target.value)} />
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" disabled={busy === 'approve'}
                  onClick={() => patch({ subject, body, status: 'approved' }, 'approve')}>
            Approve
          </Button>
          <Button disabled={!dirty || busy === 'save'}
                  onClick={() => patch({ subject, body }, 'save')}>
            {busy === 'save' ? 'Saving…' : 'Save edits'}
          </Button>
          <Button disabled={busy === 'regen'} onClick={regenerate}>
            {busy === 'regen' ? 'Regenerating…' : 'Regenerate'}
          </Button>
          <Button variant="danger" disabled={busy === 'reject'}
                  onClick={() => patch({ status: 'rejected' }, 'reject')}>
            Reject
          </Button>
        </div>
      </div>
    </article>
  )
}
