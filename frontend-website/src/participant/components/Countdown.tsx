import type { EventTiming } from '../types'
import { useReconciledCountdown } from '../../services/realtime/useReconciledCountdown'

function format(seconds: number, showHours: boolean) {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remainder = seconds % 60
  const parts = showHours ? [hours, minutes, remainder] : [Math.floor(seconds / 60), remainder]
  return parts.map((part) => String(part).padStart(2, '0')).join(':')
}

export default function Countdown({ seconds = 0, showHours = false, timing }: { seconds?: number; showHours?: boolean; timing?: EventTiming }) {
  const timerKey = timing ? `${timing.startedAt ?? ''}:${timing.endsAt ? 'active' : 'inactive'}` : 'fallback'
  const remaining = useReconciledCountdown(timing, timerKey, seconds)

  return <time className="countdown" dateTime={`PT${remaining}S`}>{format(remaining, showHours)}</time>
}
