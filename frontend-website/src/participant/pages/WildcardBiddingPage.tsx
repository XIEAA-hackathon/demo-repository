import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useParticipant } from '../ParticipantContext'
import type { LeaderboardEntry } from '../types'
import AdvanceButton from '../components/AdvanceButton'
import Countdown from '../components/Countdown'
import Leaderboard from '../components/Leaderboard'
import WaitingState from '../components/WaitingState'
import { Button, Card, CoinBalance, PageHeading, Stat } from '../components/ui'
import { useBidCooldown } from '../useBidCooldown'

export default function WildcardBiddingPage() {
  const { dashboard, service, refresh } = useParticipant()
  const [entries, setEntries] = useState<LeaderboardEntry[]>([])
  const [amount, setAmount] = useState('')
  const [working, setWorking] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const cooldownRemaining = useBidCooldown(dashboard?.bidCooldownRemainingSeconds ?? 0)
  const loadLeaderboard = useCallback(() => service.getLeaderboard('WILDCARD').then(setEntries), [service])
  useEffect(() => {
    void loadLeaderboard()
    const id = setInterval(() => void loadLeaderboard(), 2000)
    return () => clearInterval(id)
  }, [loadLeaderboard])

  if (!dashboard) return null
  const applied = Boolean(dashboard.wildcardApplication) && dashboard.wildcard?.status === 'applied'
  const isLeader = dashboard.team.leaderId === dashboard.currentUserId
  const slots = dashboard.wildcard?.slotCount ?? dashboard.gameConfig.wildcardSlots

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setWorking(true); setMessage(null)
    try {
      await service.placeWildcardBid(Number(amount))
      await Promise.all([refresh(), loadLeaderboard()])
      setAmount('')
      setMessage({ type: 'success', text: 'Your slot bid was accepted. You can update it while bidding remains open.' })
    } catch (cause) {
      setMessage({ type: 'error', text: cause instanceof Error ? cause.message : 'Bid could not be placed.' })
    } finally { setWorking(false) }
  }

  if (!applied) return <div className="stack"><PageHeading eyebrow="Wildcard · Slot bidding" title="Your team is not bidding" /><Card className="center-card"><WaitingState text="Only teams that applied can place a wildcard slot bid." /></Card><Card><h2>Live ranking</h2><Leaderboard entries={entries} currentTeamId={dashboard.team.id} cutoff={slots} cutoffLabel="Wildcard cut-off" /></Card></div>

  return <div className="stack wildcard-bidding-page">
    <PageHeading eyebrow="Wildcard · Slot bidding" title="Bid for a selection slot">One team, one live bid. The top {slots} teams qualify to choose problems in rank order.</PageHeading>
    <div className="stats-grid bid-status-grid"><Stat label="Time left" value={<Countdown timing={dashboard.timing} />} /><Stat label="Team balance" value={<CoinBalance value={dashboard.wallet.balance} />} /><Stat label="Your current bid" value={`${dashboard.wildcardBidAmount ?? 0} coins`} /></div>
    <div className="two-column bid-layout">
      <Card className="leaderboard-panel"><h2>Live slot ranking</h2><Leaderboard entries={entries} currentTeamId={dashboard.team.id} cutoff={slots} cutoffLabel="Wildcard cut-off" /></Card>
      <Card className="bid-panel"><h2>Place your slot bid</h2><form className="form" onSubmit={submit}><label className={!isLeader ? 'is-locked' : ''}><span>Bid amount</span><input type="number" inputMode="numeric" min={1} max={dashboard.wallet.balance} value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="250" disabled={!isLeader || cooldownRemaining > 0} aria-describedby="wildcard-bid-cooldown" required /></label><Button type="submit" disabled={!isLeader || working || !amount || cooldownRemaining > 0}>{working ? 'Placing bid…' : cooldownRemaining > 0 ? `Available in ${cooldownRemaining}s` : dashboard.wildcardBidAmount == null ? 'Place slot bid' : 'Update slot bid'}</Button></form><p className="muted bid-rules">Higher bids rank first. For equal bids, the earlier final bid timestamp ranks first.</p><p className="notice">Winning bids are deducted only when the organizer closes bidding.</p>{!isLeader && <p className="notice">Only your team leader can place or update the bid.</p>}{cooldownRemaining > 0 && <p className="bid-cooldown" id="wildcard-bid-cooldown" role="status">Next bid available in <strong>{cooldownRemaining}s</strong></p>}{message && <p className={message.type === 'success' ? 'success' : 'error'} role="status">{message.text}</p>}</Card>
    </div>
    <AdvanceButton label="Waiting for slot bidding to close" />
  </div>
}
