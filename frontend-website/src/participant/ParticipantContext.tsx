import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { participantService } from './services/apiParticipantService'
import type { ParticipantService } from './services/participantService'
import { connectEventSocket } from './services/eventSocket'
import type { ParticipantDashboard } from './types'
import { getStageRoute } from './routeConfig'
import type { ApiStatus } from '../services/realtime/timerReconciliation'

interface ParticipantContextValue {
  dashboard: ParticipantDashboard | null
  loading: boolean
  error: string | null
  socketStatus: string
  apiStatus: ApiStatus
  lastSyncAt: number | null
  documentHidden: boolean
  refreshPending: boolean
  service: ParticipantService
  refresh: () => Promise<ParticipantDashboard | null>
}

const ParticipantContext = createContext<ParticipantContextValue | null>(null)

export function ParticipantProvider({ children }: { children: ReactNode }) {
  const [dashboard, setDashboard] = useState<ParticipantDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [socketStatus, setSocketStatus] = useState('connecting')
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking')
  const [lastSyncAt, setLastSyncAt] = useState<number | null>(null)
  const [documentHidden, setDocumentHidden] = useState(() => document.hidden)
  const [refreshPending, setRefreshPending] = useState(false)
  const refreshInFlight = useRef<Promise<ParticipantDashboard | null> | null>(null)
  const dashboardRef = useRef<ParticipantDashboard | null>(null)
  const lastSuccessfulRefreshStartedAt = useRef(0)
  const navigate = useNavigate()

  const refresh = useCallback(() => {
    if (refreshInFlight.current) return refreshInFlight.current
    const startedAt = Date.now()
    const request = (async () => {
      setRefreshPending(true)
      try {
        setError(null)
        const next = await participantService.getParticipantDashboard()
        setDashboard(next)
        dashboardRef.current = next
        lastSuccessfulRefreshStartedAt.current = startedAt
        setLastSyncAt(Date.now())
        setApiStatus('healthy')
        return next
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Participant data could not be loaded.')
        setApiStatus(dashboardRef.current ? 'degraded' : 'offline')
        return null
      } finally {
        setLoading(false)
        setRefreshPending(false)
      }
    })()
    refreshInFlight.current = request
    void request.finally(() => {
      if (refreshInFlight.current === request) refreshInFlight.current = null
    })
    return request
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
        schedule(document.hidden ? 30_000 : next ? 5_000 : Math.min(30_000, 1_000 * 2 ** failures))
      }, delay)
    }
    const onVisibility = () => {
      setDocumentHidden(document.hidden)
      if (timer !== undefined) window.clearTimeout(timer)
      if (document.hidden) {
        schedule(30_000)
        return
      }
      void (async () => {
        const next = await refresh()
        failures = next ? 0 : failures + 1
        schedule(next ? 5_000 : Math.min(30_000, 1_000 * 2 ** failures))
      })()
    }
    schedule(5_000)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      stopped = true
      if (timer !== undefined) window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [refresh])

  useEffect(() => {
    let timer: number | undefined
    let navigateAfterRefresh = false
    let latestEventAt = 0
    const queueRefresh = (shouldNavigate = false) => {
      navigateAfterRefresh = navigateAfterRefresh || shouldNavigate
      latestEventAt = Date.now()
      if (document.hidden) return
      if (timer !== undefined) window.clearTimeout(timer)
      timer = window.setTimeout(async () => {
        timer = undefined
        const shouldNavigateNow = navigateAfterRefresh
        const eventAt = latestEventAt
        navigateAfterRefresh = false
        latestEventAt = 0
        const next = lastSuccessfulRefreshStartedAt.current >= eventAt
          ? dashboardRef.current
          : await refresh()
        if (next && shouldNavigateNow) navigate(getStageRoute(next.eventState).path, { replace: true })
      }, 300)
    }
    const disconnect = connectEventSocket((message) => {
      // Live bid ranks are already refreshed by BiddingPanel's coalesced poll.
      // A bid from another team must not make every participant fetch the much
      // larger dashboard as well. The bidder still refreshes after its POST.
      if (message.type === 'bid_updated' || message.type === 'wildcard_bid_updated') return
      queueRefresh(message.type === 'event_snapshot' || message.type === 'event_state_changed')
    }, (status) => {
      setSocketStatus(status)
      if (status === 'reconnected') queueRefresh()
    })
    return () => {
      if (timer !== undefined) window.clearTimeout(timer)
      disconnect()
    }
  }, [navigate, refresh])

  const value = useMemo(
    () => ({ dashboard, loading, error, socketStatus, apiStatus, lastSyncAt, documentHidden, refreshPending, service: participantService, refresh }),
    [apiStatus, dashboard, documentHidden, error, lastSyncAt, loading, refresh, refreshPending, socketStatus],
  )
  return <ParticipantContext.Provider value={value}>{children}</ParticipantContext.Provider>
}

export function useParticipant(): ParticipantContextValue {
  const value = useContext(ParticipantContext)
  if (!value) throw new Error('useParticipant must be used within ParticipantProvider.')
  return value
}
