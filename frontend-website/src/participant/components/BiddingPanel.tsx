import { useEffect, useState, type FormEvent } from 'react'
import { useParticipant } from '../ParticipantContext'
import type { Bid, LeaderboardEntry, Problem, WildcardProblem } from '../types'
import Countdown from './Countdown'
import Leaderboard from './Leaderboard'
import { Button, Card, CoinBalance, PageHeading, Stat } from './ui'

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

  const loadLeaderboard = async () => setEntries(await service.getLeaderboard(round))
  useEffect(() => { void loadLeaderboard() }, [round, service])

  if (!dashboard) return null
  const isLeader = dashboard.team.leaderId === dashboard.currentUserId
  const currentBid = dashboard.latestBid?.round === round ? dashboard.latestBid.amount : 0
  const isWildcard = round === 'WILDCARD'

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setMessage(null)
    try {
      const numericAmount = Number(amount)
      if (isWildcard) await service.placeWildcardBid(problem.id, numericAmount)
      else await service.placeBid(problem.id, numericAmount)
      await Promise.all([refresh(), loadLeaderboard()])
      setAmount('')
      setMessage({ type: 'success', text: 'Bid accepted. Coins are not deducted until finalization.' })
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
          <h2>Place a new bid</h2>
          <div className="bid-controls">
            <div className="bid-current"><span>Your current bid</span><strong>{currentBid} coins</strong></div>
            <form className="form" onSubmit={submit}>
              <label className={!isLeader ? 'is-locked' : ''}>
                <span>New bid</span>
                <input inputMode="numeric" min={problem.startingBid} max={dashboard.wallet.balance} type="number" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="340" disabled={!isLeader} aria-describedby="bid-note" />
              </label>
              <Button type="submit" disabled={!isLeader || submitting}>{submitting ? 'Placing bid…' : 'Place bid'}</Button>
            </form>
          </div>
          <p className="muted bid-rules">Starting bid: {problem.startingBid} coins · Only the latest bid per team counts.</p>
          {!isLeader && <p className="notice">Only your team leader can place bids.</p>}
          <p className="notice bid-note" id="bid-note">Coins are deducted only after a winning bid is finalized.</p>
          {message && <p className={message.type === 'success' ? 'success' : 'error'} role="status">{message.text}</p>}
        </Card>
      </div>
    </div>
  )
}
