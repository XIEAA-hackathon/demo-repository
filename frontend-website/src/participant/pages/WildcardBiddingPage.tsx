import { useCallback, useEffect, useRef, useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import type { BidIncrement, LeaderboardEntry } from '../types'
import AdvanceButton from '../components/AdvanceButton'
import Countdown from '../components/Countdown'
import Leaderboard from '../components/Leaderboard'
import WaitingState from '../components/WaitingState'
import { Button, Card, CoinBalance, PageHeading, Stat } from '../components/ui'
import { useBidCooldown } from '../useBidCooldown'

const BID_INCREMENTS: BidIncrement[] = [5, 10, 25]

export default function WildcardBiddingPage() {
  const { dashboard, service, refresh } = useParticipant()
  const [entries, setEntries] = useState<LeaderboardEntry[]>([])
  const [working, setWorking] = useState(false)
  const [highSpendConfirmed, setHighSpendConfirmed] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const cooldownRemaining = useBidCooldown(dashboard?.bidCooldownRemainingSeconds ?? 0)
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
        schedule(document.hidden ? 30_000 : 2_000)
      }, delay)
    }
    const onVisibility = () => { if (!document.hidden) schedule(0) }
    schedule(0)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      stopped = true
      if (timer !== undefined) window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [loadLeaderboard])

  if (!dashboard) return null
  const applied = Boolean(dashboard.wildcardApplication) && dashboard.wildcard?.status === 'applied'
  const isLeader = dashboard.team.leaderId === dashboard.currentUserId
  const biddingActive = dashboard.eventState === 'WILDCARD_BIDDING'
  const slots = dashboard.wildcard?.slotCount ?? dashboard.gameConfig.wildcardSlots
  const currentPrice = Math.max(dashboard.gameConfig.wildcardBaseBidPrice, ...entries.map((entry) => entry.amount))
  const canAfford = (increment: BidIncrement) => currentPrice + increment <= dashboard.wallet.balance

  const placeIncrement = async (increment: BidIncrement) => {
    const proposedAmount = currentPrice + increment
    if (
      proposedAmount > dashboard.gameConfig.startingCoins / 2
      && !highSpendConfirmed
      && !window.confirm('High Bid Warning\n\nYou are committing more than half of your starting balance to this auction.\n\nContinue?')
    ) return
    if (proposedAmount > dashboard.gameConfig.startingCoins / 2) setHighSpendConfirmed(true)
    setWorking(true)
    setMessage(null)
    try {
      const accepted = await service.placeWildcardBid(increment)
      await Promise.allSettled([refresh(), loadLeaderboard()])
      setMessage({ type: 'success', text: `Your slot bid was accepted at ${accepted} coins.` })
    } catch (cause) {
      await Promise.allSettled([refresh(), loadLeaderboard()])
      setMessage({ type: 'error', text: cause instanceof Error ? cause.message : 'Bid could not be placed.' })
    } finally {
      setWorking(false)
    }
  }

  if (!applied) return <div className="stack"><PageHeading eyebrow="Wildcard · Slot bidding" title="Your team is not bidding" /><Card className="center-card"><WaitingState text="Only teams that applied can place a wildcard slot bid." /></Card><Card><h2>Live ranking</h2><Leaderboard entries={entries} currentTeamId={dashboard.team.id} cutoff={slots} cutoffLabel="Wildcard cut-off" /></Card></div>

  return <div className="stack wildcard-bidding-page">
    <PageHeading eyebrow="Wildcard · Slot bidding" title="Bid for a selection slot">One team, one live bid. The top {slots} teams qualify to choose problems in rank order.</PageHeading>
    <div className="stats-grid bid-status-grid"><Stat label="Time left" value={<Countdown timing={dashboard.timing} />} /><Stat label="Current bid" value={`${currentPrice} coins`} /><Stat label="Your balance" value={<CoinBalance value={dashboard.wallet.balance} />} /><Stat label="Base price" value={`${dashboard.gameConfig.wildcardBaseBidPrice} coins`} /></div>
    <div className="two-column bid-layout">
      <Card className="leaderboard-panel"><h2>Live slot ranking</h2><Leaderboard entries={entries} currentTeamId={dashboard.team.id} cutoff={slots} cutoffLabel="Wildcard cut-off" /></Card>
      <Card className="bid-panel"><h2>Quick bid</h2><div className="bid-controls"><div className="bid-current"><span>Current auction bid</span><strong>{currentPrice} coins</strong>{dashboard.wildcardBidAmount != null && <small>Your bid: {dashboard.wildcardBidAmount} coins</small>}</div><div className="quick-bid-buttons" aria-label="Quick bid increments">{BID_INCREMENTS.map((increment) => <Button key={increment} type="button" disabled={!biddingActive || !isLeader || working || cooldownRemaining > 0 || !canAfford(increment)} onClick={() => void placeIncrement(increment)}>+{increment}</Button>)}</div></div><p className="muted bid-rules" id="wildcard-bid-rules">The server adds your selected increment to the authoritative current bid. Maximum single increase: 25 coins.</p>{!BID_INCREMENTS.some(canAfford) && <p className="notice">Your balance cannot cover the next available bid.</p>}<p className="notice">Winning bids are deducted only when the organizer closes bidding.</p>{!isLeader && <p className="notice">Only your team leader can place or update the bid.</p>}{cooldownRemaining > 0 && <p className="bid-cooldown" id="wildcard-bid-cooldown" role="status">Next bid available in <strong>{cooldownRemaining}s</strong></p>}{message && <p className={message.type === 'success' ? 'success' : 'error'} role="status">{message.text}</p>}</Card>
    </div>
    <AdvanceButton label="Waiting for slot bidding to close" />
  </div>
}
