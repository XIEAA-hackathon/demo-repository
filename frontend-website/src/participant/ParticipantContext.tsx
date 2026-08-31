import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { participantService } from './services/apiParticipantService'
import type { ParticipantService } from './services/participantService'
import { connectEventSocket } from './services/eventSocket'
import type { EventMessage } from './services/eventSocket'
import { participantEventStates, type AcceptedBid, type ParticipantDashboard, type ParticipantEventState } from './types'
import { getStageRoute } from './routeConfig'
import { shouldApplyHttpSnapshot, type ApiStatus } from '../services/realtime/timerReconciliation'
import { jitterMilliseconds, parseBidDelta } from './services/bidRealtime'

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
  recordAcceptedBid: (bid: AcceptedBid) => void
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
  const realtimeRevision = useRef(0)
  const socketStatusRef = useRef('connecting')
  const navigate = useNavigate()

  const refresh = useCallback(() => {
    if (refreshInFlight.current) return refreshInFlight.current
    const startedAt = Date.now()
    const requestRevision = realtimeRevision.current
    const request = (async () => {
      setRefreshPending(true)
      try {
        setError(null)
        const next = await participantService.getParticipantDashboard()
        if (shouldApplyHttpSnapshot(requestRevision, realtimeRevision.current)) {
          setDashboard(next)
          dashboardRef.current = next
          lastSuccessfulRefreshStartedAt.current = startedAt
          setLastSyncAt(Date.now())
        }
        setApiStatus('healthy')
        return dashboardRef.current ?? next
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

  const applyOwnBid = useCallback((bid: AcceptedBid) => {
    realtimeRevision.current += 1
    setDashboard((current) => {
      if (!current) return current
      const next = bid.round === 'ROUND1'
        ? {
            ...current,
            latestBid: {
              id: bid.bidId,
              teamId: current.team.id,
              teamName: current.team.name,
              problemId: bid.problemId ?? String(current.currentProblem?.id ?? ''),
              amount: bid.amount,
              placedAt: bid.placedAt,
              round: 'ROUND1' as const,
            },
            bidCooldownRemainingSeconds: bid.cooldownSeconds,
          }
        : {
            ...current,
            wildcardBidAmount: bid.amount,
            bidCooldownRemainingSeconds: bid.cooldownSeconds,
          }
      dashboardRef.current = next
      return next
    })
    setLastSyncAt(Date.now())
  }, [])

  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    let retryDelay = 1_000
    const loadInitialSnapshot = async () => {
      const next = await refresh()
      if (next || stopped) return
      timer = window.setTimeout(() => {
        retryDelay = Math.min(8_000, retryDelay * 2)
        void loadInitialSnapshot()
      }, retryDelay)
    }
    void loadInitialSnapshot()
    return () => {
      stopped = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [refresh])
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
        schedule(
          connected && next
            ? jitterMilliseconds(60_000, 90_000)
            : next
              ? jitterMilliseconds(12_000, 20_000)
              : Math.min(30_000, 1_000 * 2 ** failures),
        )
      }, delay)
    }
    const onVisibility = () => {
      setDocumentHidden(document.hidden)
      if (timer !== undefined) window.clearTimeout(timer)
      if (document.hidden) {
        schedule(['connected', 'reconnected'].includes(socketStatusRef.current)
          ? jitterMilliseconds(60_000, 90_000)
          : jitterMilliseconds(15_000, 25_000))
        return
      }
      void (async () => {
        const next = await refresh()
        failures = next ? 0 : failures + 1
        const connected = ['connected', 'reconnected'].includes(socketStatusRef.current)
        schedule(next && connected
          ? jitterMilliseconds(60_000, 90_000)
          : next ? jitterMilliseconds(12_000, 20_000) : Math.min(30_000, 1_000 * 2 ** failures))
      })()
    }
    schedule(jitterMilliseconds(12_000, 20_000))
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
      if (message.version > 0 && previousVersion > 0 && message.version < previousVersion) return
      if (message.version > 0) lastEventVersion.current = message.version
      if (previousVersion > 0 && message.version > previousVersion + 1) {
        queueRefresh()
        window.dispatchEvent(new Event('participant:leaderboard-resync'))
      }
      setRealtimeEvent(message)

      if (message.type === 'event_snapshot' || message.type === 'event_state_changed' || message.type === 'timer_sync') {
        realtimeRevision.current += 1
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

      if (message.type === 'bid_updated' || message.type === 'wildcard_bid_updated') {
        const delta = parseBidDelta(message.payload)
        if (delta && delta.teamId === dashboardRef.current?.team.id) {
          applyOwnBid({
            bidId: delta.bidId,
            problemId: delta.problemId,
            amount: delta.amount,
            increment: delta.increment,
            round: delta.round,
            placedAt: delta.placedAt,
            cooldownSeconds: delta.cooldownSeconds,
            serverTime: message.server_time,
          })
        }
        return
      }
      if (message.type === 'participant_presence_changed') return
      if (message.type === 'round_updated' && message.payload.action === 'winners_assigned') {
        realtimeRevision.current += 1
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
      if (message.type === 'round1_assignment_changed') {
        if (String(message.payload.team_id) === dashboardRef.current?.team.id) {
          realtimeRevision.current += 1
          queueRefresh()
        }
        return
      }
      queueRefresh()
    }, (status) => {
      setSocketStatus(status)
      socketStatusRef.current = status
      if (status === 'reconnected') {
        lastEventVersion.current = 0
        queueRefresh()
        window.dispatchEvent(new Event('participant:leaderboard-resync'))
      }
    })
    return () => {
      if (timer !== undefined) window.clearTimeout(timer)
      disconnect()
    }
  }, [applyOwnBid, navigate, refresh])

  const value = useMemo(
    () => ({ dashboard, loading, error, socketStatus, apiStatus, lastSyncAt, documentHidden, refreshPending, realtimeEvent, service: participantService, refresh, recordAcceptedBid: applyOwnBid }),
    [apiStatus, applyOwnBid, dashboard, documentHidden, error, lastSyncAt, loading, realtimeEvent, refresh, refreshPending, socketStatus],
  )
  return <ParticipantContext.Provider value={value}>{children}</ParticipantContext.Provider>
}

export function useParticipant(): ParticipantContextValue {
  const value = useContext(ParticipantContext)
  if (!value) throw new Error('useParticipant must be used within ParticipantProvider.')
  return value
}
