import { useCallback, useEffect, useRef, useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import type { Bid, LeaderboardEntry } from '../types'
import { Card } from './ui'
import Leaderboard from './Leaderboard'

export default function FinalizedLeaderboard({ round }: { round: Bid['round'] }) {
  const { dashboard, service, realtimeEvent } = useParticipant()
  const [entries, setEntries] = useState<LeaderboardEntry[]>([])
  const [finalized, setFinalized] = useState(false)
  const [problemNumber, setProblemNumber] = useState<string | null>(null)
  const revision = useRef(0)
  const inFlight = useRef<Promise<void> | null>(null)
  const refreshQueued = useRef(false)
  const eventAtMount = useRef(realtimeEvent)
  const refresh = useCallback(() => {
    if (inFlight.current) return inFlight.current
    const startedRevision = revision.current
    const request = service.getLeaderboard(round).then(rows => {
      if (revision.current !== startedRevision) return
      setEntries(rows.filter(row => row.finalized).slice(0, round === 'WILDCARD' ? 10 : rows.length))
      setFinalized(rows.some(row => row.finalized))
    }).catch(() => { /* Reconnect/visibility will reconcile through the existing resync event. */ })
    inFlight.current = request
    void request.finally(() => {
      if (inFlight.current === request) inFlight.current = null
      if (refreshQueued.current) { refreshQueued.current = false; void refresh() }
    })
    return request
  }, [round, service])
  useEffect(() => {
    const initial = eventAtMount.current
    if (!(round === 'ROUND1' && initial?.type === 'round_updated'
          && ['winners_assigned', 'problem_no_bids'].includes(String(initial.payload.action))
          && Array.isArray(initial.payload.winners))) void refresh()
    const resync = () => { void refresh() }
    const visible = () => { if (!document.hidden) void refresh() }
    window.addEventListener('participant:leaderboard-resync', resync)
    document.addEventListener('visibilitychange', visible)
    return () => {
      refreshQueued.current = false
      window.removeEventListener('participant:leaderboard-resync', resync)
      document.removeEventListener('visibilitychange', visible)
    }
  }, [refresh, round])
  useEffect(() => {
    if (round === 'ROUND1' && realtimeEvent?.type === 'round_updated'
        && ['winners_assigned', 'problem_no_bids'].includes(String(realtimeEvent.payload.action))) {
      const winners = realtimeEvent.payload.winners as Array<{ team_id: number; team_name: string; amount: number }> | undefined
      if (!Array.isArray(winners)) { void refresh(); return }
      revision.current += 1
      setFinalized(true)
      setProblemNumber(String((realtimeEvent.payload.problem as { number?: string })?.number ?? ''))
      setEntries(winners.map((winner, index) => ({ rank: index + 1, teamId: String(winner.team_id), teamName: winner.team_name,
        amount: winner.amount, placedAt: null, finalized: true, qualified: true })))
    } else if (round === 'WILDCARD' && realtimeEvent?.type === 'wildcard_updated'
               && realtimeEvent.payload.action === 'bidding_finalized' && realtimeEvent !== eventAtMount.current) {
      revision.current += 1
      if (inFlight.current) refreshQueued.current = true
      else void refresh()
    }
  }, [realtimeEvent, refresh, round])
  return <Card className="leaderboard-panel">
    <h2>{round === 'ROUND1' ? 'ROUND 1 — FINAL RESULT' : 'WILDCARD — FINAL RANKING'}</h2>
    {problemNumber && <p>Problem #{problemNumber}</p>}
    {!finalized ? <p>Waiting for the organizer to finalize the ranking.</p> : <>
      <Leaderboard entries={entries} currentTeamId={dashboard?.team.id ?? ''} finalRound={round} />
      {!entries.length && <p>No winners assigned.</p>}
    </>}
  </Card>
}
