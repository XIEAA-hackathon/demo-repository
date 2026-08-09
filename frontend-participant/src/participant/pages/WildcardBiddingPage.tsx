import { useEffect, useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import type { WildcardProblem } from '../types'
import AdvanceButton from '../components/AdvanceButton'
import BiddingPanel from '../components/BiddingPanel'

export default function WildcardBiddingPage() {
  const { dashboard, service } = useParticipant()
  const [problem, setProblem] = useState<WildcardProblem | null>(null)
  useEffect(() => { void service.getWildcardProblems().then((items) => setProblem(items[0] ?? null)) }, [service])
  if (!problem) return <p className="muted">Loading wildcard auction…</p>
  return <div className="stack wildcard-bidding-page"><BiddingPanel problem={problem} round="WILDCARD" qualificationSlots={dashboard?.gameConfig.wildcardSlots ?? 0} /><AdvanceButton label="Waiting for wildcard bidding to close" /></div>
}
