import { useEffect, useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import type { Problem } from '../types'
import ProblemPreview from '../components/ProblemPreview'
import RoundOneComplete from '../components/RoundOneComplete'

export default function RoundOnePreviewPage() {
  const { dashboard, service } = useParticipant()
  const [problem, setProblem] = useState<Problem | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { void service.getProblems(1).then((items) => setProblem(items[0] ?? null)).catch((cause: Error) => setError(cause.message)) }, [service])
  if (dashboard?.round1Assigned) return <RoundOneComplete dashboard={dashboard} />
  if (error) return <p className="error">{error}</p>
  if (!dashboard || !problem) return <p className="muted">Waiting for a problem to be revealed.</p>
  return <ProblemPreview problem={problem} round="Round 1" seconds={dashboard.gameConfig.round1PreviewSeconds} timing={dashboard.timing} />
}
