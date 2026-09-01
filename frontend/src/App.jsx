import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'

function Soon({ name }) {
  return <p className="text-sm text-muted">{name} — not built yet.</p>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="contacts" element={<Soon name="Contacts" />} />
          <Route path="templates" element={<Soon name="Templates" />} />
          <Route path="compose" element={<Soon name="Compose" />} />
          <Route path="send" element={<Soon name="Send" />} />
          <Route path="followups" element={<Soon name="Follow-ups" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
