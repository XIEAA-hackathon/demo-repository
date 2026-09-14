import { useEffect, useRef, useState } from 'react'
import {
  deriveServerRemaining,
  projectCountdown,
  shouldApplyTimerSnapshot,
  type CountdownAnchor,
  type TimerTiming,
} from './timerReconciliation'

export function useReconciledCountdown(
  timing: TimerTiming | null | undefined,
  timerKey: unknown,
  fallbackSeconds = 0,
) {
  const receivedTimingRef = useRef(Boolean(timing))
  if (timing) receivedTimingRef.current = true
  const initialFallback = receivedTimingRef.current ? 0 : fallbackSeconds
  const initialNow = Date.now()
  const initialRemaining = deriveServerRemaining(timing, initialNow, initialFallback)
  const anchorRef = useRef<CountdownAnchor>({
    remaining: initialRemaining,
    localAt: initialNow,
    paused: timing ? Boolean(timing.paused) : true,
  })
  const snapshotRef = useRef({ timing, timerKey })
  const [remaining, setRemaining] = useState(initialRemaining)

  useEffect(() => {
    const localNow = Date.now()
    const serverRemaining = deriveServerRemaining(timing, localNow, initialFallback)
    const expectedRemaining = projectCountdown(anchorRef.current, localNow)
    if (shouldApplyTimerSnapshot({
      previousTiming: snapshotRef.current.timing,
      previousTimerKey: snapshotRef.current.timerKey,
      nextTiming: timing,
      nextTimerKey: timerKey,
      expectedRemaining,
      serverRemaining,
    })) {
      anchorRef.current = {
        remaining: serverRemaining,
        localAt: localNow,
        paused: timing ? Boolean(timing.paused) : true,
      }
      setRemaining(serverRemaining)
    }
    snapshotRef.current = { timing, timerKey }
  }, [initialFallback, timerKey, timing])

  useEffect(() => {
    const tick = () => {
      const next = projectCountdown(anchorRef.current, Date.now())
      setRemaining((current) => current === next ? current : next)
    }
    const timer = window.setInterval(tick, 1_000)
    document.addEventListener('visibilitychange', tick)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [])

  return remaining
}
