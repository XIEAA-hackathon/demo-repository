import { useEffect, useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import type { Problem } from '../types'
import BiddingPanel from '../components/BiddingPanel'

export default function RoundOneBiddingPage() {
  const { dashboard, service } = useParticipant()
  const [problem, setProblem] = useState<Problem | null>(null)
  useEffect(() => { void service.getProblems(1).then((items) => setProblem(items[0] ?? null)) }, [service])
  if (!dashboard || !problem) return <p className="muted">Problem unavailable.</p>
  return <BiddingPanel problem={problem} round="ROUND1" qualificationSlots={dashboard.gameConfig.round1WinnerCount} />
}
