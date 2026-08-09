import { Link, Outlet } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import { useParticipant } from '../ParticipantContext'
import { getStageRoute } from '../routeConfig'
import StageNavigation from './StageNavigation'

export default function ParticipantLayout() {
  const { dashboard, socketStatus } = useParticipant()
  const { logout } = useAuth()
  const stage = getStageRoute(dashboard?.eventState ?? 'WAITING')

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="brand" to="/participant">
          <span className="brand__mark">X</span>
          <span><strong>Bid to Build</strong><small>Participant portal</small></span>
        </Link>
        <div className="top-status">
          <div className="top-status__stage">
            <span className="live-dot" aria-hidden="true" />
            <span className="top-status__label">{socketStatus === 'connected' ? 'Live stage' : 'Reconnecting'}</span>
            <strong>{stage.label}</strong>
          </div>
          <div className="topbar__team">
            <span className="participant-identity">
              <small>Team: {dashboard?.team.name ?? 'Loading team…'}</small>
              <strong>{dashboard?.currentUser.name ?? 'Loading participant…'}</strong>
              <em>{dashboard?.isLeader ? 'Team leader' : 'Team member · View only'}</em>
            </span>
            <strong>Coins: {dashboard?.wallet.balance.toLocaleString() ?? '—'}</strong>
            <button className="button button--secondary" type="button" onClick={() => void logout()}>Logout</button>
          </div>
        </div>
      </header>
      <div className="workspace">
        <StageNavigation />
        <main className="workspace__main"><Outlet /></main>
      </div>
    </div>
  )
}
