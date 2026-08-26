import { useEffect, useState } from 'react'
import { Link, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useParticipant } from '../ParticipantContext'
import { getStageRoute } from '../routeConfig'
import StageNavigation from './StageNavigation'
import { isSyncStale } from '../../services/realtime/timerReconciliation'

export default function ParticipantLayout() {
  const { dashboard, socketStatus, apiStatus, lastSyncAt, documentHidden, refreshPending } = useParticipant()
  const { logout } = useAuth()
  const stage = getStageRoute(dashboard?.eventState ?? 'WAITING')
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000)
    return () => window.clearInterval(timer)
  }, [])
  const staleSeconds = lastSyncAt ? Math.floor((now - lastSyncAt) / 1_000) : null
  const stale = isSyncStale({ documentHidden, refreshPending, staleSeconds })
  const connectionLabel = socketStatus === 'connected' ? 'Connected' : socketStatus === 'reconnected' ? 'Reconnected' : socketStatus === 'error' ? 'Connection error' : 'Reconnecting…'
  const apiLabel = apiStatus === 'healthy' ? 'API healthy' : apiStatus === 'degraded' ? 'API degraded' : apiStatus === 'offline' ? 'API offline' : 'API checking'

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="brand" to="/participant">
          <span className="brand__mark">X</span>
          <span><strong>Bid to Build</strong><small>Participant portal</small></span>
        </Link>
        <div className="top-status">
          <div className="top-status__stage">
            <span className={`live-dot ${socketStatus === 'connected' || socketStatus === 'reconnected' ? '' : 'is-reconnecting'}`} aria-hidden="true" />
            <span className="top-status__label">{connectionLabel}</span>
            <span className={`top-status__api is-${apiStatus}`}>{apiLabel}</span>
            <strong>{stage.label}</strong>
          </div>
          <div className="topbar__team">
            <span className="participant-identity">
              <small>Team: {dashboard?.team.name ?? 'Loading team…'}</small>
              <strong>{dashboard?.currentUser.name ?? 'Loading participant…'}</strong>
              <em>{dashboard?.isLeader ? 'Team leader' : 'Team member'}</em>
            </span>
            <strong>Coins: {dashboard?.wallet.balance.toLocaleString() ?? '—'}</strong>
            <button className="button button--secondary" type="button" onClick={() => void logout()}>Logout</button>
          </div>
        </div>
      </header>
      {stale && <div className="participant-stale-warning" role="alert"><strong>Live state may be stale.</strong> Last successful API synchronization: {staleSeconds === null ? 'not yet completed' : `${staleSeconds} seconds ago`}. Dashboard polling is recovering; the live connection is tracked separately.</div>}
      <div className="workspace">
        <StageNavigation />
        <main className="workspace__main"><Outlet /></main>
      </div>
    </div>
  )
}
