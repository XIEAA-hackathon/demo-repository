import { useEffect, useState, type FormEvent } from 'react'
import { useParticipant } from '../ParticipantContext'
import type { Bid, LeaderboardEntry, Problem, WildcardProblem } from '../types'
import Countdown from './Countdown'
import Leaderboard from './Leaderboard'
import { Button, Card, CoinBalance, PageHeading, Stat } from './ui'
import { useBidCooldown } from '../useBidCooldown'

export default function BiddingPanel({
  problem,
  round,
  qualificationSlots = 5,
}: {
  problem: Problem | WildcardProblem
  round: Bid['round']
  qualificationSlots?: number
}) {
  const { dashboard, service, refresh } = useParticipant()
  const [entries, setEntries] = useState<LeaderboardEntry[]>([])
  const [amount, setAmount] = useState('')
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const cooldownRemaining = useBidCooldown(dashboard?.bidCooldownRemainingSeconds ?? 0)

  const loadLeaderboard = async () => setEntries(await service.getLeaderboard(round))
  useEffect(() => { void loadLeaderboard() }, [round, service])

  if (!dashboard) return null
  const isLeader = dashboard.team.leaderId === dashboard.currentUserId
  const currentBid = dashboard.latestBid?.round === round && dashboard.latestBid.problemId === problem.id
    ? dashboard.latestBid.amount
    : 0
  const isWildcard = round === 'WILDCARD'
  const isOpeningBid = !isWildcard && currentBid === 0
  const minimumEntry = isOpeningBid ? problem.startingBid : dashboard.gameConfig.round1BidIncrement
  const maximumEntry = isOpeningBid ? dashboard.wallet.balance : dashboard.wallet.balance - currentBid
  const numericAmount = amount.trim() === '' ? Number.NaN : Number(amount)
  const newBidTotal = isOpeningBid ? numericAmount : currentBid + numericAmount
  const cannotAffordMinimum = maximumEntry < minimumEntry

  const amountError = (() => {
    if (!amount) return null
    if (!Number.isInteger(numericAmount) || numericAmount <= 0) return 'Enter a whole number of coins.'
    if (numericAmount < minimumEntry) {
      return isOpeningBid
        ? `Opening bid must be at least ${minimumEntry} coins.`
        : `Increase must be at least ${minimumEntry} coins.`
    }
    if (numericAmount > maximumEntry) return `New total cannot exceed your ${dashboard.wallet.balance}-coin balance.`
    return null
  })()

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setMessage(null)
    try {
      if (!amount || amountError) throw new Error(amountError ?? 'Enter a bid amount.')
      if (isWildcard) await service.placeWildcardBid(numericAmount)
      else await service.placeBid(problem.id, newBidTotal)
      await Promise.all([refresh(), loadLeaderboard()])
      setAmount('')
      setMessage({ type: 'success', text: `Bid accepted at ${newBidTotal} coins. Coins are not deducted until finalization.` })
    } catch (cause) {
      const text = cause instanceof Error ? cause.message : 'Bid could not be placed.'
      setMessage({ type: 'error', text })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="stack bidding-console">
      <PageHeading eyebrow={isWildcard ? 'Wildcard · Live auction' : 'Round 1 · Live auction'} title={`Problem #${String(problem.number).padStart(2, '0')}`}>
        <span className="page-heading__row">
          {problem.title}
          {isWildcard && <small className="auction-slots">{qualificationSlots} wildcard slots</small>}
        </span>
      </PageHeading>

      <Card className="bid-problem-statement">
        <p>{problem.description}</p>
      </Card>

      <div className="stats-grid bid-status-grid">
        <Stat label="Time left" value={<Countdown timing={dashboard.timing} />} />
        <Stat label="Team balance" value={<CoinBalance value={dashboard.wallet.balance} />} />
      </div>

      <div className="two-column bid-layout">
        <Card className="leaderboard-panel">
          <h2>Live leaderboard</h2>
          <Leaderboard
            entries={entries}
            currentTeamId={dashboard.team.id}
            cutoff={qualificationSlots}
            cutoffLabel={isWildcard ? 'Wildcard cut-off' : 'Qualification cut-off'}
          />
        </Card>

        <Card className="bid-panel">
          <h2>{isOpeningBid ? 'Place your opening bid' : 'Increase your bid'}</h2>
          <div className="bid-controls">
            <div className="bid-current"><span>Your current bid</span><strong>{currentBid} coins</strong></div>
            <form className="form" onSubmit={submit}>
              <label className={!isLeader ? 'is-locked' : ''}>
                <span>{isOpeningBid ? 'Opening bid' : 'Increase by'}</span>
                <input inputMode="numeric" min={minimumEntry} max={maximumEntry} step={1} type="number" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder={String(minimumEntry)} disabled={!isLeader || cannotAffordMinimum || cooldownRemaining > 0} aria-describedby="bid-rules bid-note bid-cooldown" aria-invalid={Boolean(amountError)} required />
              </label>
              <Button type="submit" disabled={!isLeader || submitting || !amount || Boolean(amountError) || cannotAffordMinimum || cooldownRemaining > 0}>{submitting ? 'Placing bid…' : cooldownRemaining > 0 ? `Available in ${cooldownRemaining}s` : isOpeningBid ? 'Place opening bid' : 'Increase bid'}</Button>
              {!isOpeningBid && (
                <p className="bid-total-preview" aria-live="polite">
                  <span>New total</span>
                  <strong>{Number.isFinite(newBidTotal) ? `${newBidTotal} coins` : 'Enter an increase'}</strong>
                </p>
              )}
            </form>
          </div>
          <p className="muted bid-rules" id="bid-rules">
            {isOpeningBid
              ? `Minimum opening bid: ${minimumEntry} coins.`
              : `Enter the coins to add · Minimum increase: ${minimumEntry} coins · Maximum total: ${dashboard.wallet.balance} coins.`}
          </p>
          {amountError && <p className="error" role="status">{amountError}</p>}
          {cannotAffordMinimum && <p className="notice">Your balance cannot cover the minimum {isOpeningBid ? 'opening bid' : 'increase'}.</p>}
          {!isLeader && <p className="notice">Only your team leader can place bids.</p>}
          <p className="notice bid-note" id="bid-note">Coins are deducted only after a winning bid is finalized.</p>
          {cooldownRemaining > 0 && <p className="bid-cooldown" id="bid-cooldown" role="status">Next bid available in <strong>{cooldownRemaining}s</strong></p>}
          {message && <p className={message.type === 'success' ? 'success' : 'error'} role="status">{message.text}</p>}
        </Card>
      </div>
    </div>
  )
}
