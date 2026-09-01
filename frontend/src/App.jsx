import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Compose from './pages/Compose'
import Contacts from './pages/Contacts'
import Dashboard from './pages/Dashboard'
import Followups from './pages/Followups'
import Send from './pages/Send'
import Templates from './pages/Templates'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="contacts" element={<Contacts />} />
          <Route path="templates" element={<Templates />} />
          <Route path="compose" element={<Compose />} />
          <Route path="send" element={<Send />} />
          <Route path="followups" element={<Followups />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
