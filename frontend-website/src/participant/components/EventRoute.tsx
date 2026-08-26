import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { getStageRoute } from '../routeConfig'
import type { ParticipantEventState } from '../types'
import { useParticipant } from '../ParticipantContext'

export default function EventRoute({ state, children }: { state: ParticipantEventState; children: ReactNode }) {
  const { dashboard, loading, error } = useParticipant()

  if (loading) return <p className="muted">Loading participant panel…</p>
  if (!dashboard) return <p className="error">{error ?? 'Participant data unavailable.'}</p>

  if (dashboard.eventState !== state) {
    const active = getStageRoute(dashboard.eventState)
    return <Navigate to={active.path} replace />
  }

  return children
}
