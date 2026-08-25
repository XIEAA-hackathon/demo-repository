import { useCallback, useEffect, useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import type { Bid, BidIncrement, LeaderboardEntry, Problem, WildcardProblem } from '../types'
import Countdown from './Countdown'
import Leaderboard from './Leaderboard'
import { Button, Card, CoinBalance, PageHeading, Stat } from './ui'
import { useBidCooldown } from '../useBidCooldown'

const BID_INCREMENTS: BidIncrement[] = [5, 10, 25]

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
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [highSpendConfirmed, setHighSpendConfirmed] = useState(false)
  const cooldownRemaining = useBidCooldown(dashboard?.bidCooldownRemainingSeconds ?? 0)
  const loadLeaderboard = useCallback(() => service.getLeaderboard(round).then(setEntries), [round, service])

  useEffect(() => {
    void loadLeaderboard()
    const id = setInterval(() => void loadLeaderboard(), 2000)
    return () => clearInterval(id)
  }, [loadLeaderboard])
  useEffect(() => setHighSpendConfirmed(false), [problem.id])

  if (!dashboard) return null
  const isLeader = dashboard.team.leaderId === dashboard.currentUserId
  const isWildcard = round === 'WILDCARD'
  const currentPrice = Math.max(problem.startingBid, ...entries.map((entry) => entry.amount))
  const ownBid = dashboard.latestBid?.round === round && dashboard.latestBid.problemId === problem.id
    ? dashboard.latestBid.amount
    : null
  const canAfford = (increment: BidIncrement) => currentPrice + increment <= dashboard.wallet.balance

  const placeIncrement = async (increment: BidIncrement) => {
    const proposedAmount = currentPrice + increment
    if (
      proposedAmount > dashboard.gameConfig.startingCoins / 2
      && !highSpendConfirmed
      && !window.confirm('High Bid Warning\n\nYou are committing more than half of your starting balance to this auction.\n\nContinue?')
    ) return
    if (proposedAmount > dashboard.gameConfig.startingCoins / 2) setHighSpendConfirmed(true)
    setSubmitting(true)
    setMessage(null)
    try {
      const accepted = isWildcard
        ? await service.placeWildcardBid(increment)
        : (await service.placeBid(problem.id, increment)).amount
      await Promise.all([refresh(), loadLeaderboard()])
      setMessage({ type: 'success', text: `Bid accepted at ${accepted} coins. Coins are not deducted until finalization.` })
    } catch (cause) {
      await Promise.allSettled([refresh(), loadLeaderboard()])
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

      <Card className="bid-problem-statement"><p>{problem.description}</p></Card>

      <div className="stats-grid bid-status-grid">
        <Stat label="Time left" value={<Countdown timing={dashboard.timing} />} />
        <Stat label="Current bid" value={`${currentPrice} coins`} />
        <Stat label="Your balance" value={<CoinBalance value={dashboard.wallet.balance} />} />
        <Stat label="Base price" value={`${problem.startingBid} coins`} />
      </div>

      <div className="two-column bid-layout">
        <Card className="leaderboard-panel">
          <h2>Live leaderboard</h2>
          <Leaderboard entries={entries} currentTeamId={dashboard.team.id} cutoff={qualificationSlots} cutoffLabel={isWildcard ? 'Wildcard cut-off' : 'Qualification cut-off'} />
        </Card>

        <Card className="bid-panel">
          <h2>Quick bid</h2>
          <div className="bid-controls">
            <div className="bid-current"><span>Current auction bid</span><strong>{currentPrice} coins</strong>{ownBid != null && <small>Your bid: {ownBid} coins</small>}</div>
            <div className="quick-bid-buttons" aria-label="Quick bid increments">
              {BID_INCREMENTS.map((increment) => (
                <Button key={increment} type="button" disabled={!isLeader || submitting || cooldownRemaining > 0 || !canAfford(increment)} onClick={() => void placeIncrement(increment)}>
                  +{increment}
                </Button>
              ))}
            </div>
          </div>
          <p className="muted bid-rules" id="bid-rules">The server adds your selected increment to the authoritative current bid. Maximum single increase: 25 coins.</p>
          {!BID_INCREMENTS.some(canAfford) && <p className="notice">Your balance cannot cover the next available bid.</p>}
          {!isLeader && <p className="notice">Only your team leader can place bids.</p>}
          <p className="notice bid-note" id="bid-note">Coins are deducted only after a winning bid is finalized.</p>
          {cooldownRemaining > 0 && <p className="bid-cooldown" id="bid-cooldown" role="status">Next bid available in <strong>{cooldownRemaining}s</strong></p>}
          {message && <p className={message.type === 'success' ? 'success' : 'error'} role="status">{message.text}</p>}
        </Card>
      </div>
    </div>
  )
}
