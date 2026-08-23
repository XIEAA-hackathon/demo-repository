import { useEffect, useState } from 'react'

export function useBidCooldown(remainingSeconds: number): number {
  const [remaining, setRemaining] = useState(Math.ceil(Math.max(0, remainingSeconds)))

  useEffect(() => {
    const deadline = Date.now() + Math.max(0, remainingSeconds) * 1000
    const update = () => setRemaining(Math.ceil(Math.max(0, deadline - Date.now()) / 1000))
    update()
    if (remainingSeconds <= 0) return
    const timer = window.setInterval(update, 200)
    return () => window.clearInterval(timer)
  }, [remainingSeconds])

  return remaining
}
