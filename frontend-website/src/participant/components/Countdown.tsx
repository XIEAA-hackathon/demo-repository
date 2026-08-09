import { useEffect, useState } from 'react'
import type { EventTiming } from '../types'

function format(seconds: number, showHours: boolean) {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remainder = seconds % 60
  const parts = showHours ? [hours, minutes, remainder] : [Math.floor(seconds / 60), remainder]
  return parts.map((part) => String(part).padStart(2, '0')).join(':')
}

export default function Countdown({ seconds = 0, showHours = false, timing }: { seconds?: number; showHours?: boolean; timing?: EventTiming }) {
  const calculate = () => {
    if (timing?.paused && timing.pausedRemainingSeconds !== null) return timing.pausedRemainingSeconds
    if (!timing?.endsAt) return seconds
    const serverOffset = Date.parse(timing.serverTime) - timing.receivedAt
    return Math.max(0, Math.ceil((Date.parse(timing.endsAt) - (Date.now() + serverOffset)) / 1000))
  }
  const [remaining, setRemaining] = useState(calculate)

  useEffect(() => {
    setRemaining(calculate())
    const timer = window.setInterval(() => setRemaining(calculate()), 1_000)
    return () => window.clearInterval(timer)
  }, [seconds, timing?.endsAt, timing?.paused, timing?.pausedRemainingSeconds, timing?.receivedAt, timing?.serverTime])

  return <time className="countdown" dateTime={`PT${remaining}S`}>{format(remaining, showHours)}</time>
}
