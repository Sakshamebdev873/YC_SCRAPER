import { useEffect, useState } from 'react'
import { api } from '../api'
import { Badge, Button, Card, ErrorNote, inputClass, Spinner } from '../components/Bits'

const ROUND_FOR_KEY = (key) => {
  if (key.startsWith('followup_') && key !== 'followup_subject') {
    return Number(key.split('_')[1])
  }
  return 0
}

const LABELS = {
  bio: 'Bio / pitch',
  system_prompt: 'System prompt',
  user_prompt: 'User prompt',
  subject: 'Subject line',
  followup_subject: 'Follow-up subject',
  followup_1: 'Follow-up #1',
  followup_2: 'Follow-up #2',
  followup_3: 'Follow-up #3',
}

export default function Templates() {
  const [domains, setDomains] = useState([])
  const [domain, setDomain] = useState('job')
  const [keys, setKeys] = useState([])
  const [templates, setTemplates] = useState({})
  const [activeKey, setActiveKey] = useState('system_prompt')
  const [draft, setDraft] = useState('')
  const [versions, setVersions] = useState([])
  const [contacts, setContacts] = useState([])
  const [contactId, setContactId] = useState('')
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.get('/api/templates/domains').then(setDomains).catch(setError)
  }, [])

  useEffect(() => {
    setPreview(null)
    api.get(`/api/templates/${domain}`)
      .then((body) => {
        setKeys(body.keys)
        setTemplates(body.templates)
        setDraft(body.templates[activeKey] ?? '')
      })
      .catch(setError)
    api.get(`/api/contacts?domain=${domain}&status=active&per_page=25`)
      .then((body) => {
        setContacts(body.items)
        setContactId(body.items[0] ? String(body.items[0].id) : '')
      })
      .catch(setError)
  }, [domain])

  // Keyed on the key/domain the editor is pointed at, NOT on `templates`:
  // save() writes templates and then sets the saved badge, so a reset that
  // also fired on `templates` would wipe the badge before it ever rendered.
  useEffect(() => {
    setDraft(templates[activeKey] ?? '')
    setSaved(false)
    setPreview(null)
    api.get(`/api/templates/${domain}/${activeKey}/versions`).then(setVersions).catch(() => setVersions([]))
  }, [activeKey, domain])

  const dirty = draft !== (templates[activeKey] ?? '')

  async function save() {
    setBusy('save'); setError(null)
    try {
      await api.put(`/api/templates/${domain}/${activeKey}`, { content: draft })
      const body = await api.get(`/api/templates/${domain}`)
      setTemplates(body.templates)
      setDraft(body.templates[activeKey] ?? draft)
      setVersions(await api.get(`/api/templates/${domain}/${activeKey}/versions`))
      setSaved(true)
    } catch (e) { setError(e) } finally { setBusy('') }
  }

  async function runPreview() {
    setBusy('preview'); setError(null); setPreview(null)
    try {
      setPreview(await api.post('/api/templates/preview', {
        domain,
        key: activeKey,
        content: draft,
        contact_id: contactId ? Number(contactId) : null,
        round: ROUND_FOR_KEY(activeKey),
      }))
    } catch (e) { setError(e) } finally { setBusy('') }
  }

  async function restore(versionId) {
    setError(null)
    try {
      await api.post(`/api/templates/${domain}/${activeKey}/restore/${versionId}`)
      const body = await api.get(`/api/templates/${domain}`)
      setTemplates(body.templates)
      setDraft(body.templates[activeKey] ?? '')
      setVersions(await api.get(`/api/templates/${domain}/${activeKey}/versions`))
      setSaved(false)
    } catch (e) { setError(e) }
  }

  if (!keys.length) return <Spinner />

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Templates</h1>
        <select className={`${inputClass} w-56`} value={domain}
                onChange={(e) => setDomain(e.target.value)}>
          {domains.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>
      <ErrorNote error={error} />

      <div className="grid grid-cols-[13rem_1fr] gap-5 items-start">
        <nav className="bg-surface border border-line rounded-lg p-2">
          {keys.map((key) => (
            <button key={key} onClick={() => setActiveKey(key)}
                    className={`w-full text-left px-2 py-1.5 text-sm rounded-md ${
                      key === activeKey ? 'bg-accent/10 text-accent font-medium' : 'text-muted hover:bg-paper'
                    }`}>
              {LABELS[key] || key}
            </button>
          ))}
        </nav>

        <div className="space-y-4 min-w-0">
          <Card
            title={LABELS[activeKey] || activeKey}
            action={
              <div className="flex items-center gap-2">
                {dirty && <Badge tone="warn">unsaved</Badge>}
                {saved && !dirty && <Badge tone="ok">saved</Badge>}
                <Button onClick={save} variant="primary" disabled={!dirty || busy === 'save'}>
                  {busy === 'save' ? 'Saving…' : 'Save'}
                </Button>
              </div>
            }
          >
            {activeKey === 'bio' && (
              <p className="mb-3 text-xs text-muted">
                The bio is stored separately from the system prompt. Editing it here does not
                rewrite the system prompt — paste any changes across yourself.
              </p>
            )}
            <textarea
              className={`${inputClass} mono h-80 leading-relaxed`}
              value={draft}
              spellCheck={false}
              onChange={(e) => { setDraft(e.target.value); setSaved(false) }}
            />
          </Card>

          <Card
            title="Preview"
            action={
              <div className="flex items-end gap-2">
                <select className={`${inputClass} w-56`} value={contactId}
                        onChange={(e) => setContactId(e.target.value)}>
                  {contacts.map((c) => (
                    <option key={c.id} value={c.id}>{c.company_name} — {c.founder_name}</option>
                  ))}
                </select>
                <Button onClick={runPreview} disabled={busy === 'preview' || !contacts.length}>
                  {busy === 'preview' ? 'Generating…' : 'Preview'}
                </Button>
              </div>
            }
          >
            <p className="text-xs text-muted mb-3">
              Renders with the text currently in the editor, saved or not.
              {ROUND_FOR_KEY(activeKey) === 0
                ? ' This calls OpenAI.'
                : ' Follow-up rounds render locally — no OpenAI call.'}
            </p>
            {!preview ? (
              <p className="text-sm text-muted">No preview yet.</p>
            ) : (
              <div className="space-y-2">
                <div className="text-sm"><span className="text-muted">Subject: </span>{preview.subject}</div>
                <pre className="mono text-sm whitespace-pre-wrap bg-paper border border-line rounded-md p-3">
                  {preview.body}
                </pre>
              </div>
            )}
          </Card>

          <Card title={`Version history (${versions.length})`}>
            {versions.length === 0 ? (
              <p className="text-sm text-muted">No earlier versions yet.</p>
            ) : (
              <ul className="space-y-2">
                {versions.map((version) => (
                  <li key={version.id} className="flex gap-3 items-start border-t border-line pt-2 first:border-0 first:pt-0">
                    <span className="text-xs text-muted whitespace-nowrap pt-0.5">{version.created_at}</span>
                    <pre className="mono text-xs whitespace-pre-wrap flex-1 max-h-24 overflow-y-auto text-muted">
                      {version.content}
                    </pre>
                    <Button onClick={() => restore(version.id)}>Restore</Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
