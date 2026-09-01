import { NavLink, Outlet } from 'react-router-dom'

const LINKS = [
  ['/', 'Dashboard'],
  ['/contacts', 'Contacts'],
  ['/templates', 'Templates'],
  ['/compose', 'Compose'],
  ['/send', 'Send'],
  ['/followups', 'Follow-ups'],
]

export default function Layout() {
  return (
    <div className="min-h-screen flex">
      <nav className="w-52 shrink-0 border-r border-line bg-surface px-3 py-5">
        <div className="px-2 mb-6">
          <div className="text-sm font-semibold tracking-tight">Cold Email Applier</div>
          <div className="text-xs text-muted">local · 127.0.0.1</div>
        </div>
        <ul className="space-y-0.5">
          {LINKS.map(([to, label]) => (
            <li key={to}>
              <NavLink
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `block px-2 py-1.5 text-sm rounded-md ${
                    isActive ? 'bg-accent/10 text-accent font-medium' : 'text-muted hover:bg-paper'
                  }`
                }
              >
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <main className="flex-1 min-w-0 px-6 py-6">
        <Outlet />
      </main>
    </div>
  )
}
