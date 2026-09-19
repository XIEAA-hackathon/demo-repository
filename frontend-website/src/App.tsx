import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import PublicLayout from './layouts/PublicLayout'
import HomePage from './pages/public/HomePage'
import EventsPage from './pages/public/EventsPage'
import LoginPage from './pages/public/LoginPage'

const ParticipantRoute = lazy(() => import('./participant/ParticipantRoute'))
const AdminRoute = lazy(() => import('./admin/AdminRoute'))
const LeaderboardDashboard = lazy(() => import('./leaderboard/Dashboard'))
const LabAdminRoute = lazy(() => import('./lab-admin/LabAdminRoute'))

export default function App() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-void p-6 text-ink-muted">Loading portal…</main>}>
      <Routes>
        <Route path="/participant/*" element={<ParticipantRoute />} />
        <Route path="/admin/*" element={<AdminRoute />} />
        <Route path="/lab-admin/*" element={<LabAdminRoute />} />
        <Route path="/leaderboard" element={<LeaderboardDashboard />} />
        <Route path="/leaderboard/:round" element={<LeaderboardDashboard />} />
        <Route element={<PublicLayout />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/event" element={<EventsPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<HomePage />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
