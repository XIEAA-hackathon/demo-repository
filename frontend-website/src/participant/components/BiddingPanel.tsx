import { useCallback, useEffect, useRef, useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import type { Bid, BidIncrement, LeaderboardEntry, Problem, WildcardProblem } from '../types'
import Countdown from './Countdown'
import Leaderboard from './Leaderboard'
import { Card, CoinBalance, PageHeading, Stat } from './ui'
import BidIncrementForm from './BidIncrementForm'
import { useBidCooldown } from '../useBidCooldown'
import { ApiError } from '../services/apiClient'
import { applyBidDelta, jitterMilliseconds, parseBidDelta } from '../services/bidRealtime'

export default function BiddingPanel({
  problem,
  round,
  qualificationSlots = 5,
}: {
  problem: Problem | WildcardProblem
  round: Bid['round']
  qualificationSlots?: number
}) {
  const { dashboard, service, recordAcceptedBid, realtimeEvent, socketStatus } = useParticipant()
  const [entries, setEntries] = useState<LeaderboardEntry[]>([])
  const cooldownResetKey = round === 'WILDCARD'
    ? dashboard?.wildcardBidAmount
    : dashboard?.latestBid?.round === round ? dashboard.latestBid.amount : null
  const cooldownRemaining = useBidCooldown(dashboard?.bidCooldownRemainingSeconds ?? 0, cooldownResetKey)
  const leaderboardInFlight = useRef<Promise<void> | null>(null)
  const loadLeaderboard = useCallback(() => {
    if (leaderboardInFlight.current) return leaderboardInFlight.current
    const request = service.getLeaderboard(round).then(setEntries)
    leaderboardInFlight.current = request
    const release = () => {
      if (leaderboardInFlight.current === request) leaderboardInFlight.current = null
    }
    void request.then(release, release)
    return request
  }, [round, service])

  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    const schedule = (delay: number) => {
      if (timer !== undefined) window.clearTimeout(timer)
      timer = window.setTimeout(async () => {
        if (stopped) return
        try { await loadLeaderboard() } catch { /* The next fallback poll retries. */ }
        const connected = ['connected', 'reconnected'].includes(socketStatus)
        schedule(document.hidden
          ? jitterMilliseconds(60_000, 90_000)
          : connected ? jitterMilliseconds(45_000, 60_000) : jitterMilliseconds(10_000, 15_000))
      }, delay)
    }
    const onVisibility = () => { if (!document.hidden) schedule(0) }
    const onResync = () => schedule(0)
    schedule(0)
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('participant:leaderboard-resync', onResync)
    return () => {
      stopped = true
      if (timer !== undefined) window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('participant:leaderboard-resync', onResync)
    }
  }, [loadLeaderboard, socketStatus])
  useEffect(() => {
    if (!realtimeEvent || !['bid_updated', 'wildcard_bid_updated'].includes(realtimeEvent.type)) return
    const delta = parseBidDelta(realtimeEvent.payload)
    if (!delta || delta.round !== round) return
    if (delta.problemId !== null && delta.problemId !== String(problem.id)) return
    setEntries((current) => applyBidDelta(current, delta))
  }, [problem.id, realtimeEvent, round])

  if (!dashboard) return null
  const isLeader = dashboard.team.leaderId === dashboard.currentUserId
  const isWildcard = round === 'WILDCARD'
  const biddingActive = dashboard.eventState === (isWildcard ? 'WILDCARD_BIDDING' : 'ROUND1_BIDDING')
    && (dashboard.timing.paused || Boolean(dashboard.timing.endsAt))
  const currentPrice = Math.max(problem.startingBid, ...entries.map((entry) => entry.amount))
  const ownBid = dashboard.latestBid?.round === round && dashboard.latestBid.problemId === problem.id
    ? dashboard.latestBid.amount
    : null

  const placeIncrement = async (increment: BidIncrement) => {
    try {
      const accepted = isWildcard
        ? await service.placeWildcardBid(increment)
        : await service.placeBid(problem.id, increment)
      recordAcceptedBid(accepted)
      setEntries((current) => applyBidDelta(current, {
        bidId: accepted.bidId,
        teamId: dashboard.team.id,
        teamName: dashboard.team.name,
        problemId: accepted.problemId,
        amount: accepted.amount,
        increment: accepted.increment,
        round: accepted.round,
        placedAt: accepted.placedAt,
        cooldownSeconds: accepted.cooldownSeconds,
      }))
      if (!['connected', 'reconnected'].includes(socketStatus)) void loadLeaderboard().catch(() => undefined)
      return accepted
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) await loadLeaderboard().catch(() => undefined)
      throw cause
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
          <h2>Place a bid</h2>
          <div className="bid-controls">
            <div className="bid-current"><span>Current auction bid</span><strong>{currentPrice} coins</strong>{ownBid != null && <small>Your bid: {ownBid} coins</small>}</div>
            <BidIncrementForm key={`${round}-${problem.id}`} currentPrice={currentPrice} balance={dashboard.wallet.balance}
              startingCoins={dashboard.gameConfig.startingCoins} disabled={!biddingActive || !isLeader}
              cooldownRemaining={cooldownRemaining} onBid={placeIncrement} />
          </div>
          {!isLeader && <p className="notice">Only your team leader can place bids.</p>}
          <p className="notice bid-note" id="bid-note">Coins are deducted only after a winning bid is finalized.</p>
        </Card>
      </div>
    </div>
  )
}
