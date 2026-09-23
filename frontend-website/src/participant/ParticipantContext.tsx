import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
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

type RefreshRunner = (showPending?: boolean) => Promise<ParticipantDashboard | null>

export function ParticipantProvider({ children }: { children: ReactNode }) {
  const [dashboard, setDashboard] = useState<ParticipantDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [socketStatus, setSocketStatus] = useState('connecting')
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking')
  const [lastSyncAt, setLastSyncAt] = useState<number | null>(null)
  const [documentHidden, setDocumentHidden] = useState(() => document.hidden)
  const [refreshPending, setRefreshPending] = useState(false)
  const [hasAuthoritativeSocketSnapshot, setHasAuthoritativeSocketSnapshot] = useState(false)

  // Only bidding screens consume realtimeEvent. Keeping every websocket message
  // here caused the entire participant tree (dashboard/layout/navigation) to
  // rerender for timer syncs, presence updates and unrelated broadcasts.
  const [realtimeEvent, setRealtimeEvent] = useState<EventMessage | null>(null)

  const refreshInFlight = useRef<Promise<ParticipantDashboard | null> | null>(null)
  const refreshRunnerRef = useRef<RefreshRunner | null>(null)
  const dashboardRef = useRef<ParticipantDashboard | null>(null)
  const lastSuccessfulRefreshStartedAt = useRef(0)
  const lastEventVersion = useRef(0)

  // This revision only tracks realtime mutations that could make an HTTP
  // response stale. Timer-only sync messages intentionally do not increment it.
  const realtimeRevision = useRef(0)
  const socketStatusRef = useRef('connecting')

  const navigate = useNavigate()
  const location = useLocation()
  const pathnameRef = useRef(location.pathname)

  useEffect(() => {
    pathnameRef.current = location.pathname
  }, [location.pathname])

  const navigateToStageIfAllowed = useCallback(
    (state: ParticipantEventState) => {
      // Dashboard is a persistent participant view. Organizer transitions must
      // not kick a participant out of it.
      if (pathnameRef.current === '/participant/dashboard') return

      const target = getStageRoute(state).path
      if (pathnameRef.current !== target) {
        navigate(target, { replace: true })
      }
    },
    [navigate],
  )

  const runRefresh = useCallback<RefreshRunner>((showPending = false) => {
    if (refreshInFlight.current) return refreshInFlight.current

    const startedAt = Date.now()
    const requestRevision = realtimeRevision.current

    const request = (async () => {
      if (showPending) setRefreshPending(true)

      try {
        setError(null)

        const next = await participantService.getParticipantDashboard()

        if (shouldApplyHttpSnapshot(requestRevision, realtimeRevision.current)) {
          dashboardRef.current = next
          setDashboard(next)
          lastSuccessfulRefreshStartedAt.current = startedAt

          // lastSyncAt is deliberately API-only. Previously websocket timer
          // messages updated it too, which caused unnecessary layout rerenders.
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
        if (showPending) setRefreshPending(false)
      }
    })()

    refreshInFlight.current = request

    void request.finally(() => {
      if (refreshInFlight.current === request) refreshInFlight.current = null

      // If the HTTP snapshot lost a race with an authoritative realtime
      // mutation, silently retry once the in-flight request has been released.
      if (requestRevision !== realtimeRevision.current) {
        queueMicrotask(() => {
          void refreshRunnerRef.current?.(false)
        })
      }
    })

    return request
  }, [])

  refreshRunnerRef.current = runRefresh

  // Public/manual refreshes expose pending state. Automatic background refreshes
  // below are silent so they do not make the participant board flash.
  const refresh = useCallback(
    () => runRefresh(true),
    [runRefresh],
  )

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
  }, [])

  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    let retryDelay = 1_000

    const loadInitialSnapshot = async () => {
      const next = await runRefresh(true)
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
  }, [runRefresh])

  useEffect(() => {
    const resync = () => {
      void runRefresh(false)
    }

    window.addEventListener('participant:resync', resync)
    return () => window.removeEventListener('participant:resync', resync)
  }, [runRefresh])

  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    let failures = 0

    const schedule = (delay: number) => {
      timer = window.setTimeout(async () => {
        if (stopped) return

        const next = await runRefresh(false)
        failures = next ? 0 : failures + 1
        const connected = ['connected', 'reconnected'].includes(socketStatusRef.current)

        schedule(
          connected && next && hasAuthoritativeSocketSnapshot
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
        schedule(
          ['connected', 'reconnected'].includes(socketStatusRef.current)
            ? jitterMilliseconds(60_000, 90_000)
            : jitterMilliseconds(15_000, 25_000),
        )
        return
      }

      void (async () => {
        const next = await runRefresh(false)
        failures = next ? 0 : failures + 1
        const connected = ['connected', 'reconnected'].includes(socketStatusRef.current)

        schedule(
          next && connected && hasAuthoritativeSocketSnapshot
            ? jitterMilliseconds(60_000, 90_000)
            : next
              ? jitterMilliseconds(12_000, 20_000)
              : Math.min(30_000, 1_000 * 2 ** failures),
        )
      })()
    }

    schedule(
      hasAuthoritativeSocketSnapshot && ['connected', 'reconnected'].includes(socketStatusRef.current)
        ? jitterMilliseconds(60_000, 90_000)
        : jitterMilliseconds(12_000, 20_000),
    )
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      stopped = true
      if (timer !== undefined) window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [hasAuthoritativeSocketSnapshot, runRefresh])

  useEffect(() => {
    let timer: number | undefined
    let latestEventAt = 0

    const queueRefresh = () => {
      latestEventAt = Date.now()

      // Hidden tabs reconcile when visible instead of creating background load.
      if (document.hidden) return

      if (timer !== undefined) window.clearTimeout(timer)

      timer = window.setTimeout(async () => {
        timer = undefined

        const eventAt = latestEventAt
        latestEventAt = 0

        if (lastSuccessfulRefreshStartedAt.current < eventAt) {
          await runRefresh(false)
        }
      }, jitterMilliseconds(250, 900))
    }

    const disconnect = connectEventSocket(
      (message) => {
        const previousVersion = lastEventVersion.current

        if (message.version > 0 && previousVersion > 0 && message.version < previousVersion) return
        if (message.version > 0) lastEventVersion.current = message.version

        if (previousVersion > 0 && message.version > previousVersion + 1) {
          queueRefresh()
          window.dispatchEvent(new Event('participant:leaderboard-resync'))
        }

        // Bidding components are the only current consumers of realtimeEvent.
        // Do not invalidate the entire ParticipantContext for every timer,
        // presence, lab or organizer message.
        if (message.type === 'bid_updated' || message.type === 'wildcard_bid_updated') {
          setRealtimeEvent(message)

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

        if (message.type === 'lab_assignment_changed') {
          if (String(message.payload.team_id) !== dashboardRef.current?.team.id) return

          const lab = message.payload.lab as ParticipantDashboard['lab']
          const previousLab = dashboardRef.current?.lab

          if (
            lab?.assignment_id
            && previousLab?.assignment_id
            && (
              lab.assignment_id < previousLab.assignment_id
              || (
                lab.assignment_id === previousLab.assignment_id
                && (lab.version ?? 0) < (previousLab.version ?? 0)
              )
            )
          ) {
            return
          }

          realtimeRevision.current += 1

          setDashboard((current) => {
            if (!current) return current

            const nextReady = message.payload.labAllocationReady == null
              ? current.labAllocationReady
              : Boolean(message.payload.labAllocationReady)

            const nextStatus = lab
              ? 'ASSIGNED' as const
              : nextReady
                ? 'PENDING' as const
                : current.labAllocationStatus

            const sameLab =
              current.lab?.id === lab?.id
              && current.lab?.assignment_id === lab?.assignment_id
              && current.lab?.version === lab?.version

            if (
              sameLab
              && current.labAllocationReady === nextReady
              && current.labAllocationStatus === nextStatus
            ) {
              return current
            }

            const next = {
              ...current,
              lab: lab ?? null,
              labAllocationReady: nextReady,
              labAllocationStatus: nextStatus,
            }

            dashboardRef.current = next
            return next
          })

          return
        }

        if (message.type === 'submission_updated') {
          const action = String(message.payload.action ?? '')
          if (action === 'submissions_opened' || action === 'submissions_closed') {
            const submissionsOpen = action === 'submissions_opened'
            realtimeRevision.current += 1
            setDashboard((current) => {
              if (!current || current.submissionsOpen === submissionsOpen) return current
              const next = { ...current, submissionsOpen }
              dashboardRef.current = next
              return next
            })
            if (!submissionsOpen) queueRefresh()
            return
          }

          if (String(message.payload.team_id ?? '') === dashboardRef.current?.team.id) {
            realtimeRevision.current += 1
            queueRefresh()
          }
          return
        }

        if (
          message.type === 'event_snapshot'
          || message.type === 'event_state_changed'
          || message.type === 'timer_sync'
        ) {
          if (message.type === 'event_snapshot') setHasAuthoritativeSocketSnapshot(true)
          // An initial socket snapshot can arrive before the first dashboard
          // response. Make that response retry instead of accepting a snapshot
          // which started before newer server state was observed.
          if (!dashboardRef.current) realtimeRevision.current += 1
          const rawState = message.payload.event_state
          const normalizedState = rawState === 'SUBMISSION' ? 'CODING' : rawState
          const nextState = typeof normalizedState === 'string'
            && participantEventStates.includes(normalizedState as ParticipantEventState)
            ? normalizedState as ParticipantEventState
            : null

          const rawTiming = message.payload.timing as Record<string, unknown> | undefined
          const rounds = message.payload.rounds as {
            WILDCARD?: {
              applications_open?: boolean | null
              ended?: boolean | null
            }
          } | undefined
          const wildcardRound = rounds?.WILDCARD

          const isAuthoritativeStageChange =
            message.type === 'event_state_changed' && nextState !== null

          // A pure timer sync is useless on the participant dashboard and used
          // to recreate the dashboard object on every sync. Ignore it there.
          if (
            message.type === 'timer_sync'
            && pathnameRef.current === '/participant/dashboard'
          ) {
            return
          }

          if (isAuthoritativeStageChange) {
            realtimeRevision.current += 1
          }

          if (nextState || rawTiming || wildcardRound) {
            setDashboard((current) => {
              if (!current) return current

              // event_snapshot/timer_sync must not change eventState because an
              // EventRoute would then redirect even without event_state_changed.
              const resolvedState = isAuthoritativeStageChange
                ? nextState
                : current.eventState

              const resolvedApplicationsOpen =
                wildcardRound?.applications_open == null
                  ? current.wildcardApplicationsOpen
                  : Boolean(wildcardRound.applications_open)

              const resolvedLabReady =
                wildcardRound?.ended == null
                  ? current.labAllocationReady
                  : Boolean(wildcardRound.ended)

              // The dashboard itself does not render countdown timing. Avoid
              // replacing timing there for snapshot traffic as well.
              const shouldApplyTiming =
                pathnameRef.current !== '/participant/dashboard'
                && Boolean(rawTiming)

              const nextTiming = shouldApplyTiming && rawTiming
                ? {
                    serverTime: String(rawTiming.server_time ?? message.server_time),
                    receivedAt: Number(rawTiming.received_at ?? Date.now()),
                    clockOffsetMs:
                      rawTiming.clock_offset_ms == null
                        ? current.timing.clockOffsetMs
                        : Number(rawTiming.clock_offset_ms),
                    startedAt:
                      rawTiming.started_at == null
                        ? null
                        : String(rawTiming.started_at),
                    endsAt:
                      rawTiming.ends_at == null
                        ? null
                        : String(rawTiming.ends_at),
                    paused: Boolean(rawTiming.paused),
                    pausedRemainingSeconds:
                      rawTiming.paused_remaining_seconds == null
                        ? null
                        : Number(rawTiming.paused_remaining_seconds),
                    remainingSeconds:
                      rawTiming.remaining_seconds == null
                        ? null
                        : Number(rawTiming.remaining_seconds),
                  }
                : current.timing

              const stateChanged = resolvedState !== current.eventState
              const applicationsChanged =
                resolvedApplicationsOpen !== current.wildcardApplicationsOpen
              const labReadyChanged =
                resolvedLabReady !== current.labAllocationReady
              const timingChanged = nextTiming !== current.timing

              if (
                !stateChanged
                && !applicationsChanged
                && !labReadyChanged
                && !timingChanged
              ) {
                return current
              }

              const next = {
                ...current,
                eventState: resolvedState,
                wildcardApplicationsOpen: resolvedApplicationsOpen,
                labAllocationReady: resolvedLabReady,
                timing: nextTiming,
              }

              dashboardRef.current = next
              return next
            })
          }

          if (isAuthoritativeStageChange && nextState) {
            navigateToStageIfAllowed(nextState)
          }

          // When Wildcard is complete, the participant should not wait for the
          // 60–90 second safety poll if their lab-assignment websocket event is
          // delayed or dropped. Recover within the existing 250–900 ms jitter.
          if (
            message.type === 'event_state_changed'
            && wildcardRound?.ended === true
            && !dashboardRef.current?.lab
          ) {
            queueRefresh()
          }

          return
        }

        if (message.type === 'wildcard_updated') {
          const action = String(message.payload.action ?? '')
          const ownTeamId = dashboardRef.current?.team.id

          if (action === 'bidding_closed') return

          if (action === 'bidding_finalized') {
            const winners = Array.isArray(message.payload.winners)
              ? message.payload.winners
              : []

            const ownWinner = winners.find(
              (entry) => String((entry as Record<string, unknown>).team_id) === ownTeamId,
            ) as Record<string, unknown> | undefined

            realtimeRevision.current += 1

            setDashboard((current) => {
              if (!current?.wildcard) return current

              const nextStatus = ownWinner ? 'qualified' : 'eliminated'
              const nextRank = ownWinner ? Number(ownWinner.rank) : null
              const nextWinningBid = ownWinner ? Number(ownWinner.winning_bid) : null

              if (
                current.wildcard.status === nextStatus
                && current.wildcard.rank === nextRank
                && current.wildcard.winningBid === nextWinningBid
              ) {
                return current
              }

              const next = {
                ...current,
                wildcard: {
                  ...current.wildcard,
                  status: nextStatus,
                  rank: nextRank,
                  winningBid: nextWinningBid,
                },
              }

              dashboardRef.current = next
              return next
            })

            if (ownWinner) queueRefresh()
            return
          }

          if (['problem_selected', 'selection_timeout', 'admin_end_turn'].includes(action)) {
            const selectedTeamId = String(message.payload.team_id ?? '')
            const nextTeamId = message.payload.next_team_id == null
              ? null
              : String(message.payload.next_team_id)

            realtimeRevision.current += 1

            setDashboard((current) => {
              if (!current?.wildcard) return current

              const nextRank = message.payload.next_rank == null
                ? null
                : Number(message.payload.next_rank)
              const nextTeam = message.payload.next_team == null
                ? null
                : String(message.payload.next_team)
              const nextStartedAt = message.payload.selection_started_at == null
                ? null
                : String(message.payload.selection_started_at)
              const nextEndsAt = message.payload.selection_ends_at == null
                ? null
                : String(message.payload.selection_ends_at)
              const isSelectionTurn = nextTeamId === current.team.id
              const ownSelectionCompleted = selectedTeamId === current.team.id
              const rawProblem = message.payload.problem as Record<string, unknown> | undefined
              const selectedProblemId = ownSelectionCompleted && rawProblem?.id != null
                ? String(rawProblem.id)
                : current.wildcard.selectedProblemId
              const wildcardProblem = ownSelectionCompleted && rawProblem?.id != null
                ? {
                    id: String(rawProblem.id),
                    number: Number(String(rawProblem.problem_number ?? rawProblem.id).match(/\d+/)?.[0] ?? rawProblem.id),
                    title: String(rawProblem.title ?? ''),
                    summary: String(rawProblem.description ?? ''),
                    description: String(rawProblem.description ?? ''),
                    startingBid: 0,
                    available: false,
                  }
                : current.wildcardProblem

              if (
                current.wildcard.currentSelectionRank === nextRank
                && current.wildcard.currentSelectionTeam === nextTeam
                && current.wildcard.isSelectionTurn === isSelectionTurn
                && current.wildcard.selectionStartedAt === nextStartedAt
                && current.wildcard.selectionEndsAt === nextEndsAt
                && (!ownSelectionCompleted || current.wildcard.status === 'selected')
              ) {
                return current
              }

              const next = {
                ...current,
                wildcard: {
                  ...current.wildcard,
                  status: ownSelectionCompleted ? 'selected' : current.wildcard.status,
                  selectedProblemId,
                  currentSelectionRank: nextRank,
                  currentSelectionTeam: nextTeam,
                  isSelectionTurn,
                  selectionStartedAt: nextStartedAt,
                  selectionEndsAt: nextEndsAt,
                },
                wildcardProblem,
              }

              dashboardRef.current = next
              return next
            })

            if (selectedTeamId === ownTeamId || nextTeamId === ownTeamId) {
              queueRefresh()
            }

            return
          }

          // Test/final-choice branch compatibility. These actions affect fields
          // only present in the full participant dashboard, so reconcile once
          // through the jittered HTTP path rather than constructing partial data.
          if (
            [
              'final_choice_opened',
              'final_problem_confirmed',
              'final_choice_completed',
              'final_choice_ended',
              'final_choice_timeout',
            ].includes(action)
          ) {
            realtimeRevision.current += 1
            queueRefresh()
            return
          }

          return
        }

        if (message.type === 'participant_presence_changed') return

        if (message.type === 'round_updated' && message.payload.action === 'winners_assigned') {
          realtimeRevision.current += 1

          const winners = Array.isArray(message.payload.winners)
            ? message.payload.winners
            : []

          const winner = winners.find(
            (row) => String((row as Record<string, unknown>).team_id) === dashboardRef.current?.team.id,
          ) as Record<string, unknown> | undefined

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
                startingBid: Number(
                  rawProblem.starting_bid ?? current.gameConfig.round1BaseBidPrice,
                ),
              }

              const amount = Number(winner.amount)

              const next = {
                ...current,
                wallet: {
                  ...current.wallet,
                  balance: current.wallet.balance - amount,
                },
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

        // Unknown/low-frequency stateful events are reconciled silently.
        queueRefresh()
      },
      (status) => {
        setSocketStatus((current) => current === status ? current : status)
        socketStatusRef.current = status

        if (status === 'reconnected') {
          setHasAuthoritativeSocketSnapshot(false)
          lastEventVersion.current = 0
          queueRefresh()
          window.dispatchEvent(new Event('participant:leaderboard-resync'))
        }
      },
    )

    return () => {
      if (timer !== undefined) window.clearTimeout(timer)
      disconnect()
    }
  }, [applyOwnBid, navigateToStageIfAllowed, runRefresh])

  const value = useMemo(
    () => ({
      dashboard,
      loading,
      error,
      socketStatus,
      apiStatus,
      lastSyncAt,
      documentHidden,
      refreshPending,
      realtimeEvent,
      service: participantService,
      refresh,
      recordAcceptedBid: applyOwnBid,
    }),
    [
      apiStatus,
      applyOwnBid,
      dashboard,
      documentHidden,
      error,
      lastSyncAt,
      loading,
      realtimeEvent,
      refresh,
      refreshPending,
      socketStatus,
    ],
  )

  return (
    <ParticipantContext.Provider value={value}>
      {children}
    </ParticipantContext.Provider>
  )
}

export function useParticipant(): ParticipantContextValue {
  const value = useContext(ParticipantContext)

  if (!value) {
    throw new Error('useParticipant must be used within ParticipantProvider.')
  }

  return value
}
