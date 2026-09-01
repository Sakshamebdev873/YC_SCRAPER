import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Contacts from './pages/Contacts'
import Dashboard from './pages/Dashboard'
import Templates from './pages/Templates'

function Soon({ name }) {
  return <p className="text-sm text-muted">{name} — not built yet.</p>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="contacts" element={<Contacts />} />
          <Route path="templates" element={<Templates />} />
          <Route path="compose" element={<Soon name="Compose" />} />
          <Route path="send" element={<Soon name="Send" />} />
          <Route path="followups" element={<Soon name="Follow-ups" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
