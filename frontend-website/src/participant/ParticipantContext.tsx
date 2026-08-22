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
  lastSyncAt: number | null
  service: ParticipantService
  refresh: () => Promise<ParticipantDashboard | null>
}

const ParticipantContext = createContext<ParticipantContextValue | null>(null)

export function ParticipantProvider({ children }: { children: ReactNode }) {
  const [dashboard, setDashboard] = useState<ParticipantDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [socketStatus, setSocketStatus] = useState('connecting')
  const [lastSyncAt, setLastSyncAt] = useState<number | null>(null)
  const navigate = useNavigate()

  const refresh = useCallback(async () => {
    try {
      setError(null)
      const next = await participantService.getParticipantDashboard()
      setDashboard(next)
      setLastSyncAt(Date.now())
      setSocketStatus((current) => current === 'reconnected' ? current : 'connected')
      return next
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Participant data could not be loaded.')
      setSocketStatus('reconnecting')
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => {
    const resync = () => { void refresh() }
    window.addEventListener('participant:resync', resync)
    return () => window.removeEventListener('participant:resync', resync)
  }, [refresh])

  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    let failures = 0
    const schedule = (delay: number) => {
      timer = window.setTimeout(async () => {
        if (stopped) return
        const next = await refresh()
        failures = next ? 0 : failures + 1
        schedule(next ? 5_000 : Math.min(30_000, 1_000 * 2 ** failures))
      }, delay)
    }
    const onVisibility = () => {
      if (document.visibilityState === 'visible') void refresh()
    }
    schedule(5_000)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      stopped = true
      if (timer !== undefined) window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [refresh])

  useEffect(() => connectEventSocket(async (message) => {
    const next = await refresh()
    if (next && (message.type === 'event_snapshot' || message.type === 'event_state_changed')) {
      navigate(getStageRoute(next.eventState).path, { replace: true })
    }
  }, (status) => {
    setSocketStatus(status)
    if (status === 'reconnected') void refresh()
  }), [navigate, refresh])

  const value = useMemo(
    () => ({ dashboard, loading, error, socketStatus, lastSyncAt, service: participantService, refresh }),
    [dashboard, error, lastSyncAt, loading, refresh, socketStatus],
  )
  return <ParticipantContext.Provider value={value}>{children}</ParticipantContext.Provider>
}

export function useParticipant(): ParticipantContextValue {
  const value = useContext(ParticipantContext)
  if (!value) throw new Error('useParticipant must be used within ParticipantProvider.')
  return value
}
