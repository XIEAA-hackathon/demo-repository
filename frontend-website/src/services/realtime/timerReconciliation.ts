export const TIMER_SNAPSHOT_TOLERANCE_SECONDS = 2

export type ApiStatus = 'checking' | 'healthy' | 'degraded' | 'offline'

export interface TimerTiming {
  server_time?: string | null
  serverTime?: string | null
  received_at?: number | null
  receivedAt?: number | null
  started_at?: string | null
  startedAt?: string | null
  ends_at?: string | null
  endsAt?: string | null
  paused?: boolean
  paused_remaining_seconds?: number | null
  pausedRemainingSeconds?: number | null
  remaining_seconds?: number | null
  remainingSeconds?: number | null
}

export interface CountdownAnchor {
  remaining: number
  localAt: number
  paused: boolean
}

const valueFrom = <T>(timing: TimerTiming | null | undefined, snakeKey: keyof TimerTiming, camelKey: keyof TimerTiming): T | null | undefined => {
  const snakeValue = timing?.[snakeKey]
  return (snakeValue ?? timing?.[camelKey]) as T | null | undefined
}

const finiteSeconds = (value: unknown) => {
  const seconds = Number(value)
  return Number.isFinite(seconds) ? Math.max(0, seconds) : null
}

export function classifyApiStatus(results: Array<{ status: string }>, healthFailed = false): ApiStatus {
  const successfulRequests = results.filter((result) => result.status === 'fulfilled').length
  if (successfulRequests === results.length && !healthFailed) return 'healthy'
  return successfulRequests > 0 ? 'degraded' : 'offline'
}

export function isSyncStale({
  documentHidden,
  refreshPending,
  staleSeconds,
  thresholdSeconds = 45,
}: {
  documentHidden: boolean
  refreshPending: boolean
  staleSeconds: number | null
  thresholdSeconds?: number
}) {
  if (documentHidden || refreshPending) return false
  return staleSeconds == null || staleSeconds > thresholdSeconds
}

export function shouldApplyHttpSnapshot(requestRevision: number, currentRevision: number) {
  return requestRevision === currentRevision
}

export function deriveServerRemaining(timing: TimerTiming | null | undefined, localNow = Date.now(), fallbackSeconds = 0) {
  if (!timing) return finiteSeconds(fallbackSeconds) ?? 0
  if (timing.paused) {
    return finiteSeconds(valueFrom(timing, 'paused_remaining_seconds', 'pausedRemainingSeconds'))
      ?? finiteSeconds(valueFrom(timing, 'remaining_seconds', 'remainingSeconds'))
      ?? 0
  }

  const endsAt = Date.parse(valueFrom<string>(timing, 'ends_at', 'endsAt') ?? '')
  const serverTime = Date.parse(valueFrom<string>(timing, 'server_time', 'serverTime') ?? '')
  const receivedAt = Number(valueFrom<number>(timing, 'received_at', 'receivedAt'))
  if (Number.isFinite(endsAt) && Number.isFinite(serverTime) && Number.isFinite(receivedAt)) {
    const serverOffset = serverTime - receivedAt
    return Math.max(0, Math.ceil((endsAt - (localNow + serverOffset)) / 1000))
  }

  return finiteSeconds(valueFrom(timing, 'remaining_seconds', 'remainingSeconds'))
    ?? finiteSeconds(fallbackSeconds)
    ?? 0
}

export function projectCountdown(anchor: CountdownAnchor | null, localNow = Date.now()) {
  if (!anchor) return 0
  if (anchor.paused) return anchor.remaining
  const elapsedMilliseconds = Math.max(0, localNow - anchor.localAt)
  return Math.max(0, Math.ceil(anchor.remaining - elapsedMilliseconds / 1000))
}

export function shouldApplyTimerSnapshot({
  previousTiming,
  previousTimerKey,
  nextTiming,
  nextTimerKey,
  expectedRemaining,
  serverRemaining,
}: {
  previousTiming: TimerTiming | null | undefined
  previousTimerKey: unknown
  nextTiming: TimerTiming | null | undefined
  nextTimerKey: unknown
  expectedRemaining: number
  serverRemaining: number
}) {
  if (!previousTiming) return true
  if (previousTimerKey !== nextTimerKey) return true
  if (Boolean(previousTiming.paused) !== Boolean(nextTiming?.paused)) return true
  if (valueFrom(previousTiming, 'started_at', 'startedAt') !== valueFrom(nextTiming, 'started_at', 'startedAt')) return true
  if (valueFrom(previousTiming, 'ends_at', 'endsAt') !== valueFrom(nextTiming, 'ends_at', 'endsAt')) return true
  return Math.abs(serverRemaining - expectedRemaining) > TIMER_SNAPSHOT_TOLERANCE_SECONDS
}
