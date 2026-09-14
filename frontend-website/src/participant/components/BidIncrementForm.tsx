import { useEffect, useId, useRef, useState } from 'react'
import type { AcceptedBid } from '../types'
import { ApiError } from '../services/apiClient'
import { useBidCooldown } from '../useBidCooldown'
import { Button } from './ui'

export default function BidIncrementForm({ currentPrice, balance, startingCoins, disabled, cooldownRemaining, onBid }: {
  currentPrice: number
  balance: number
  startingCoins: number
  disabled: boolean
  cooldownRemaining: number
  onBid: (increment: number) => Promise<AcceptedBid>
}) {
  const id = useId()
  const [value, setValue] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<{ error: boolean; text: string } | null>(null)
  const [cooldown, setCooldown] = useState({ seconds: 0, version: 0 })
  const localRemaining = useBidCooldown(cooldown.seconds, cooldown.version)
  const remaining = Math.max(cooldownRemaining, localRemaining)
  const inFlight = useRef(false)
  const cooldownUntil = useRef(0)
  const highSpendConfirmed = useRef(false)
  const increment = Number(value)
  const valid = /^\d+$/.test(value) && Number.isInteger(increment) && increment >= 1 && increment <= 25
  const estimate = valid ? currentPrice + increment : null
  const affordable = estimate !== null && estimate <= balance

  useEffect(() => {
    if (!message || message.error) return
    const timer = window.setTimeout(() => setMessage(null), 4000)
    return () => window.clearTimeout(timer)
  }, [message])

  const startCooldown = (seconds: number) => {
    cooldownUntil.current = Date.now() + seconds * 1000
    setCooldown((previous) => ({ seconds, version: previous.version + 1 }))
  }

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (inFlight.current || disabled || remaining > 0 || Date.now() < cooldownUntil.current || !valid || !affordable) return
    inFlight.current = true
    try {
      if (estimate! > startingCoins / 2 && !highSpendConfirmed.current) {
        if (!window.confirm('High Bid Warning\n\nYou are committing more than half of your starting balance to this auction.\n\nContinue?')) return
        highSpendConfirmed.current = true
      }
      setSubmitting(true)
      setMessage(null)
      const accepted = await onBid(increment)
      startCooldown(accepted.cooldownSeconds)
      setValue('')
      setMessage({ error: false, text: `✓ Bid accepted at ${accepted.amount} coins` })
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 429) startCooldown(cause.retryAfterSeconds ?? 5)
      setMessage({ error: true, text: cause instanceof Error ? cause.message : 'Bid could not be placed.' })
    } finally {
      inFlight.current = false
      setSubmitting(false)
    }
  }

  return <form className="bid-increment-form" onSubmit={(event) => void submit(event)}>
    <label htmlFor={id}>Bid increment</label>
    <input id={id} type="number" min="1" max="25" step="1" required inputMode="numeric"
      value={value} onChange={(event) => setValue(event.target.value)} disabled={submitting}
      aria-invalid={value !== '' && !valid} aria-describedby={`${id}-hint ${id}-preview`} />
    <small id={`${id}-hint`}>1 ≤ increment ≤ 25. Enter a whole number.</small>
    {value !== '' && !valid && <p className="error">Enter an integer from 1 to 25.</p>}
    <dl className="bid-preview" id={`${id}-preview`}>
      <div><dt>Estimated new bid</dt><dd>{estimate === null ? '—' : `${estimate} coins`}</dd></div>
      <div><dt>Current balance</dt><dd>{balance} coins</dd></div>
      <div><dt>Estimated balance if won</dt><dd>{estimate === null ? '—' : `${balance - estimate} coins`}</dd></div>
    </dl>
    <p className="muted bid-rules">Final amount is calculated by the server when your bid is received. Another team may bid first.</p>
    {estimate !== null && !affordable && <p className="notice">Your balance cannot cover this bid.</p>}
    <Button type="submit" disabled={disabled || submitting || remaining > 0 || !valid || !affordable}>
      {submitting ? 'Placing bid…' : estimate === null ? 'Place bid' : `Place ${estimate} coin bid`}
    </Button>
    {remaining > 0 && <p className="bid-cooldown" role="status">Next bid available in {remaining}s</p>}
    {message && <p className={message.error ? 'error' : 'success'} role="status">{message.text}</p>}
  </form>
}
