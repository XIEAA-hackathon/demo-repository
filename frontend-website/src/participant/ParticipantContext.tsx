import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { participantService } from './services/apiParticipantService'
import type { ParticipantService } from './services/participantService'
import { connectEventSocket } from './services/eventSocket'
import type { EventMessage } from './services/eventSocket'
import { participantEventStates, type ParticipantDashboard, type ParticipantEventState } from './types'
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
  realtimeEvent: EventMessage | null
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
  const [realtimeEvent, setRealtimeEvent] = useState<EventMessage | null>(null)
  const refreshInFlight = useRef<Promise<ParticipantDashboard | null> | null>(null)
  const dashboardRef = useRef<ParticipantDashboard | null>(null)
  const lastSuccessfulRefreshStartedAt = useRef(0)
  const lastEventVersion = useRef(0)
  const socketStatusRef = useRef('connecting')
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
        const connected = ['connected', 'reconnected'].includes(socketStatusRef.current)
        schedule(document.hidden && connected ? 60_000 : connected && next ? 30_000 : next ? 12_000 : Math.min(30_000, 1_000 * 2 ** failures))
      }, delay)
    }
    const onVisibility = () => {
      setDocumentHidden(document.hidden)
      if (timer !== undefined) window.clearTimeout(timer)
      if (document.hidden) {
        schedule(['connected', 'reconnected'].includes(socketStatusRef.current) ? 60_000 : 15_000)
        return
      }
      void (async () => {
        const next = await refresh()
        failures = next ? 0 : failures + 1
        schedule(next ? 30_000 : Math.min(30_000, 1_000 * 2 ** failures))
      })()
    }
    schedule(30_000)
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
      const previousVersion = lastEventVersion.current
      if (message.version > 0) lastEventVersion.current = message.version
      if (previousVersion > 0 && message.version > previousVersion + 1) queueRefresh()
      setRealtimeEvent(message)

      if (message.type === 'event_snapshot' || message.type === 'event_state_changed' || message.type === 'timer_sync') {
        const rawState = message.payload.event_state
        const nextState = typeof rawState === 'string' && participantEventStates.includes(rawState as ParticipantEventState)
          ? rawState as ParticipantEventState
          : null
        const rawTiming = message.payload.timing as Record<string, unknown> | undefined
        if (nextState || rawTiming) {
          setDashboard((current) => {
            if (!current) return current
            const next = {
              ...current,
              eventState: nextState ?? current.eventState,
              timing: rawTiming ? {
                serverTime: String(rawTiming.server_time ?? message.server_time),
                receivedAt: Date.now(),
                startedAt: rawTiming.started_at == null ? null : String(rawTiming.started_at),
                endsAt: rawTiming.ends_at == null ? null : String(rawTiming.ends_at),
                paused: Boolean(rawTiming.paused),
                pausedRemainingSeconds: rawTiming.paused_remaining_seconds == null ? null : Number(rawTiming.paused_remaining_seconds),
              } : current.timing,
            }
            dashboardRef.current = next
            setLastSyncAt(Date.now())
            setApiStatus('healthy')
            return next
          })
          if (nextState) navigate(getStageRoute(nextState).path, { replace: true })
        }
        return
      }

      if (message.type === 'bid_updated' || message.type === 'wildcard_bid_updated') return
      if (message.type === 'round_updated' && message.payload.action === 'winners_assigned') {
        const winners = Array.isArray(message.payload.winners) ? message.payload.winners : []
        const winner = winners.find((row) => String((row as Record<string, unknown>).team_id) === dashboardRef.current?.team.id) as Record<string, unknown> | undefined
        const rawProblem = message.payload.problem as Record<string, unknown> | undefined
        if (winner && rawProblem) {
          setDashboard((current) => {
            if (!current) return current
            const problem = {
              id: String(rawProblem.id),
              number: Number(rawProblem.number),
              title: String(rawProblem.title),
              summary: String(rawProblem.description ?? ''),
              description: String(rawProblem.description ?? ''),
              startingBid: Number(rawProblem.starting_bid ?? current.gameConfig.round1BaseBidPrice),
            }
            const amount = Number(winner.amount)
            const next = {
              ...current,
              wallet: { ...current.wallet, balance: current.wallet.balance - amount },
              currentProblem: problem,
              roundOneProblem: problem,
              finalProblem: problem,
              round1Assigned: true,
              round1AssignmentType: 'BID_WINNER' as const,
              round1AssignmentCost: amount,
            }
            dashboardRef.current = next
            return next
          })
        }
        return
      }
      queueRefresh()
    }, (status) => {
      setSocketStatus(status)
      socketStatusRef.current = status
      if (status === 'reconnected') queueRefresh()
    })
    return () => {
      if (timer !== undefined) window.clearTimeout(timer)
      disconnect()
    }
  }, [navigate, refresh])

  const value = useMemo(
    () => ({ dashboard, loading, error, socketStatus, apiStatus, lastSyncAt, documentHidden, refreshPending, realtimeEvent, service: participantService, refresh }),
    [apiStatus, dashboard, documentHidden, error, lastSyncAt, loading, realtimeEvent, refresh, refreshPending, socketStatus],
  )
  return <ParticipantContext.Provider value={value}>{children}</ParticipantContext.Provider>
}

export function useParticipant(): ParticipantContextValue {
  const value = useContext(ParticipantContext)
  if (!value) throw new Error('useParticipant must be used within ParticipantProvider.')
  return value
}
