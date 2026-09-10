import { useEffect, useState } from 'react'
import { Link, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useParticipant } from '../ParticipantContext'
import { getStageRoute } from '../routeConfig'
import StageNavigation from './StageNavigation'
import { isSyncStale } from '../../services/realtime/timerReconciliation'

export default function ParticipantLayout() {
  const { dashboard, loading, error, socketStatus, apiStatus, lastSyncAt, documentHidden, refreshPending, refresh } = useParticipant()
  const { logout } = useAuth()
  const stage = getStageRoute(dashboard?.eventState ?? 'WAITING')
  const [now, setNow] = useState(Date.now())
  const [logoutWorking, setLogoutWorking] = useState(false)
  const [logoutError, setLogoutError] = useState('')
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000)
    return () => window.clearInterval(timer)
  }, [])
  const staleSeconds = lastSyncAt ? Math.floor((now - lastSyncAt) / 1_000) : null
  const stale = isSyncStale({ documentHidden, refreshPending, staleSeconds })
  const connectionLabel = socketStatus === 'connected' ? 'Connected' : socketStatus === 'reconnected' ? 'Reconnected' : socketStatus === 'error' ? 'Connection error' : 'Reconnecting…'
  const apiLabel = apiStatus === 'healthy' ? 'API healthy' : apiStatus === 'degraded' ? 'API degraded' : apiStatus === 'offline' ? 'API offline' : 'API checking'
  const handleLogout = async () => {
    setLogoutWorking(true)
    setLogoutError('')
    try {
      await logout()
    } catch {
      setLogoutError('Logout could not reach the event server. You remain signed in; check your connection and try again.')
    } finally {
      setLogoutWorking(false)
    }
  }

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
            <button className="button button--secondary" type="button" disabled={logoutWorking} onClick={() => void handleLogout()}>{logoutWorking ? 'Logging out…' : 'Logout'}</button>
          </div>
        </div>
      </header>
      {logoutError && <div className="participant-stale-warning" role="alert"><strong>Logout incomplete.</strong> {logoutError}</div>}
      {stale && <div className="participant-stale-warning" role="alert"><strong>Live state may be stale.</strong> Last successful API synchronization: {staleSeconds === null ? 'not yet completed' : `${staleSeconds} seconds ago`}. Dashboard polling is recovering; the live connection is tracked separately.</div>}
      <div className="workspace">
        <StageNavigation />
        <main className="workspace__main">
          {loading && !dashboard
            ? <p className="muted">Loading participant panel…</p>
            : !dashboard
              ? <div role="alert"><p className="error">{error ?? 'Unable to load event data. Retrying automatically…'}</p><button className="button button--secondary" disabled={refreshPending} onClick={() => void refresh()}>{refreshPending ? 'Retrying…' : 'Retry now'}</button></div>
              : <Outlet />}
        </main>
      </div>
    </div>
  )
}
