import { useCallback, useEffect, useRef, useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import type { BidIncrement, LeaderboardEntry } from '../types'
import AdvanceButton from '../components/AdvanceButton'
import Countdown from '../components/Countdown'
import Leaderboard from '../components/Leaderboard'
import WaitingState from '../components/WaitingState'
import { Card, CoinBalance, PageHeading, Stat } from '../components/ui'
import BidIncrementForm from '../components/BidIncrementForm'
import { useBidCooldown } from '../useBidCooldown'
import { ApiError } from '../services/apiClient'
import { applyBidDelta, jitterMilliseconds, parseBidDelta } from '../services/bidRealtime'

export default function WildcardBiddingPage() {
  const { dashboard, service, recordAcceptedBid, realtimeEvent, socketStatus } = useParticipant()
  const [entries, setEntries] = useState<LeaderboardEntry[]>([])
  const cooldownRemaining = useBidCooldown(
    dashboard?.bidCooldownRemainingSeconds ?? 0,
    dashboard?.wildcardBidAmount,
  )
  const leaderboardInFlight = useRef<Promise<void> | null>(null)
  const loadLeaderboard = useCallback(() => {
    if (leaderboardInFlight.current) return leaderboardInFlight.current
    const request = service.getLeaderboard('WILDCARD').then(setEntries)
    leaderboardInFlight.current = request
    const release = () => {
      if (leaderboardInFlight.current === request) leaderboardInFlight.current = null
    }
    void request.then(release, release)
    return request
  }, [service])
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
    if (!realtimeEvent || realtimeEvent.type !== 'wildcard_bid_updated') return
    const delta = parseBidDelta(realtimeEvent.payload)
    if (!delta || delta.round !== 'WILDCARD') return
    setEntries((current) => applyBidDelta(current, delta))
  }, [realtimeEvent])

  if (!dashboard) return null
  const applied = Boolean(dashboard.wildcardApplication) && dashboard.wildcard?.status === 'applied'
  const isLeader = dashboard.team.leaderId === dashboard.currentUserId
  const biddingActive = dashboard.eventState === 'WILDCARD_BIDDING'
    && (dashboard.timing.paused || Boolean(dashboard.timing.endsAt))
  const slots = dashboard.wildcard?.slotCount ?? dashboard.gameConfig.wildcardSlots
  const currentPrice = Math.max(dashboard.gameConfig.wildcardBaseBidPrice, ...entries.map((entry) => entry.amount))

  const placeIncrement = async (increment: BidIncrement) => {
    try {
      const accepted = await service.placeWildcardBid(increment)
      recordAcceptedBid(accepted)
      setEntries((current) => applyBidDelta(current, {
        bidId: accepted.bidId,
        teamId: dashboard.team.id,
        teamName: dashboard.team.name,
        problemId: null,
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

  if (!applied) return <div className="stack"><PageHeading eyebrow="Wildcard · Slot bidding" title="Your team is not bidding" /><Card className="center-card"><WaitingState text="Only teams that applied can place a wildcard slot bid." /></Card><Card><h2>Live ranking</h2><Leaderboard entries={entries} currentTeamId={dashboard.team.id} cutoff={slots} cutoffLabel="Wildcard cut-off" /></Card></div>

  return <div className="stack wildcard-bidding-page">
    <PageHeading eyebrow="Wildcard · Slot bidding" title="Bid for a selection slot">One team, one live bid. The top {slots} teams qualify to choose problems in rank order.</PageHeading>
    <div className="stats-grid bid-status-grid"><Stat label="Time left" value={<Countdown timing={dashboard.timing} />} /><Stat label="Current bid" value={`${currentPrice} coins`} /><Stat label="Your balance" value={<CoinBalance value={dashboard.wallet.balance} />} /><Stat label="Base price" value={`${dashboard.gameConfig.wildcardBaseBidPrice} coins`} /></div>
    <div className="two-column bid-layout">
      <Card className="leaderboard-panel"><h2>Live slot ranking</h2><Leaderboard entries={entries} currentTeamId={dashboard.team.id} cutoff={slots} cutoffLabel="Wildcard cut-off" /></Card>
      <Card className="bid-panel"><h2>Place a bid</h2>
        <div className="bid-controls"><div className="bid-current"><span>Current auction bid</span><strong>{currentPrice} coins</strong>{dashboard.wildcardBidAmount != null && <small>Your bid: {dashboard.wildcardBidAmount} coins</small>}</div>
          <BidIncrementForm currentPrice={currentPrice} balance={dashboard.wallet.balance}
            startingCoins={dashboard.gameConfig.startingCoins} disabled={!biddingActive || !isLeader}
            cooldownRemaining={cooldownRemaining} onBid={placeIncrement} />
        </div>
        <p className="notice">Winning bids are deducted only when the organizer closes bidding.</p>
        {!isLeader && <p className="notice">Only your team leader can place or update the bid.</p>}
      </Card>
    </div>
    <AdvanceButton label="Waiting for slot bidding to close" />
  </div>
}
