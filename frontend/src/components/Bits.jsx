export function Card({ title, action, children, className = '' }) {
  return (
    <section className={`bg-surface border border-line rounded-lg ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between px-4 py-3 border-b border-line">
          <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

export function Stat({ label, value, tone = 'ink' }) {
  const tones = { ink: 'text-ink', accent: 'text-accent', warn: 'text-warn', ok: 'text-ok' }
  return (
    <div className="bg-surface border border-line rounded-lg px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className={`text-2xl font-semibold tabular-nums ${tones[tone]}`}>{value}</div>
    </div>
  )
}

export function Button({ variant = 'default', className = '', ...props }) {
  const base =
    'inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md border transition ' +
    'focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-40 disabled:cursor-not-allowed'
  const variants = {
    default: 'bg-surface border-line hover:bg-paper',
    primary: 'bg-accent border-accent text-white hover:brightness-95',
    danger: 'bg-danger border-danger text-white hover:brightness-95',
    ghost: 'bg-transparent border-transparent hover:bg-paper',
  }
  return <button className={`${base} ${variants[variant]} ${className}`} {...props} />
}

export function Badge({ tone = 'muted', children }) {
  const tones = {
    muted: 'bg-paper text-muted border-line',
    ok: 'bg-ok/10 text-ok border-ok/30',
    warn: 'bg-warn/10 text-warn border-warn/30',
    danger: 'bg-danger/10 text-danger border-danger/30',
    accent: 'bg-accent/10 text-accent border-accent/30',
  }
  return (
    <span className={`inline-block px-2 py-0.5 text-xs rounded border ${tones[tone]}`}>
      {children}
    </span>
  )
}

export function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-xs uppercase tracking-wide text-muted mb-1">{label}</span>
      {children}
    </label>
  )
}

export const inputClass =
  'w-full px-2.5 py-1.5 text-sm bg-surface border border-line rounded-md ' +
  'focus:outline-none focus:ring-2 focus:ring-accent/40'

export function Spinner() {
  return <span className="text-sm text-muted">Loading…</span>
}

export function ErrorNote({ error }) {
  if (!error) return null
  return (
    <div className="px-3 py-2 text-sm text-danger bg-danger/5 border border-danger/30 rounded-md">
      {String(error.message || error)}
    </div>
  )
}
