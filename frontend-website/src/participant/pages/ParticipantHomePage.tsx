import { useParticipant } from '../ParticipantContext'
import DashboardPage from './DashboardPage'
import WaitingPage from './WaitingPage'

export default function ParticipantHomePage() {
  const { dashboard, loading } = useParticipant()
  if (loading || !dashboard) return <p className="muted">Loading participant panel…</p>
  return dashboard.eventState === 'WAITING' ? <WaitingPage /> : <DashboardPage />
}
