import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Card, ErrorNote, Spinner, Stat } from '../components/Bits'

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/api/stats').then(setStats).catch(setError)
  }, [])

  if (error) return <ErrorNote error={error} />
  if (!stats) return <Spinner />

  const due = stats.followups_due
  const dueTotal = Number(due['1']) + Number(due['2']) + Number(due['3'])

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold tracking-tight">Dashboard</h1>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Stat label="Contacts" value={stats.contacts} />
        <Stat label="Contacted" value={stats.contacted} />
        <Stat label="Drafts pending" value={stats.pending_drafts} tone="warn" />
        <Stat label="Approved" value={stats.approved_drafts} tone="ok" />
        <Stat label="Follow-ups due" value={dueTotal} tone="accent" />
      </div>

      <Card title="Follow-ups due">
        <div className="flex gap-6 text-sm">
          {['1', '2', '3'].map((round) => (
            <Link key={round} to="/followups" className="hover:text-accent">
              Round {round}: <span className="tabular-nums font-medium">{due[round]}</span>
            </Link>
          ))}
        </div>
      </Card>

      <Card title="Recent runs">
        {stats.recent_runs.length === 0 ? (
          <p className="text-sm text-muted">Nothing has run yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted text-left">
              <tr>
                <th className="pb-2 font-medium">Kind</th>
                <th className="pb-2 font-medium">Domain</th>
                <th className="pb-2 font-medium">Status</th>
                <th className="pb-2 font-medium">Progress</th>
                <th className="pb-2 font-medium">Started</th>
              </tr>
            </thead>
            <tbody>
              {stats.recent_runs.map((run) => (
                <tr key={run.id} className="border-t border-line">
                  <td className="py-1.5">{run.kind}</td>
                  <td className="py-1.5 text-muted">{run.domain}</td>
                  <td className="py-1.5">{run.status}</td>
                  <td className="py-1.5 tabular-nums">{run.completed}/{run.total}</td>
                  <td className="py-1.5 text-muted">{run.started_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}
