import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { participantService } from './services/apiParticipantService'
import type { ParticipantService } from './services/participantService'
import { connectEventSocket } from './services/eventSocket'
import type { ParticipantDashboard } from './types'
import { getStageRoute } from './routeConfig'

interface ParticipantContextValue {
  dashboard: ParticipantDashboard | null
  loading: boolean
  error: string | null
  socketStatus: string
  service: ParticipantService
  refresh: () => Promise<ParticipantDashboard | null>
}

const ParticipantContext = createContext<ParticipantContextValue | null>(null)

export function ParticipantProvider({ children }: { children: ReactNode }) {
  const [dashboard, setDashboard] = useState<ParticipantDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [socketStatus, setSocketStatus] = useState('connecting')
  const navigate = useNavigate()

  const refresh = useCallback(async () => {
    try {
      setError(null)
      const next = await participantService.getParticipantDashboard()
      setDashboard(next)
      return next
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Participant data could not be loaded.')
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  useEffect(() => connectEventSocket(async (message) => {
    const next = await refresh()
    if (next && (message.type === 'event_snapshot' || message.type === 'event_state_changed')) {
      navigate(getStageRoute(next.eventState).path, { replace: true })
    }
  }, setSocketStatus), [navigate, refresh])

  const value = useMemo(
    () => ({ dashboard, loading, error, socketStatus, service: participantService, refresh }),
    [dashboard, error, loading, refresh, socketStatus],
  )
  return <ParticipantContext.Provider value={value}>{children}</ParticipantContext.Provider>
}

export function useParticipant(): ParticipantContextValue {
  const value = useContext(ParticipantContext)
  if (!value) throw new Error('useParticipant must be used within ParticipantProvider.')
  return value
}
