import { Routes, Route } from 'react-router-dom'
import PublicLayout from './layouts/PublicLayout'
import HomePage from './pages/public/HomePage'
import EventsPage from './pages/public/EventsPage'
import LoginPage from './pages/public/LoginPage'
import ParticipantRoute from './participant/ParticipantRoute'
import AdminRoute from './admin/AdminRoute'
import RoundLeaderboard from './pages/RoundLeaderboard'

export default function App() {
  return (
    <Routes>
      <Route path="/participant/*" element={<ParticipantRoute />} />
      <Route path="/admin/*" element={<AdminRoute />} />
      <Route path="/leaderboard/:round" element={<RoundLeaderboard />} />
      <Route element={<PublicLayout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/event" element={<EventsPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<HomePage />} />
      </Route>
    </Routes>
  )
}
