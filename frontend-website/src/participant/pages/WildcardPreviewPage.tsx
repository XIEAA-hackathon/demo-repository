import { useEffect, useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import type { WildcardProblem } from '../types'
import AdvanceButton from '../components/AdvanceButton'
import Countdown from '../components/Countdown'
import { Card, PageHeading } from '../components/ui'
import WaitingState from '../components/WaitingState'

export default function WildcardPreviewPage() {
  const { dashboard, service } = useParticipant()
  const [problems, setProblems] = useState<WildcardProblem[]>([])
  useEffect(() => { void service.getWildcardProblems().then(setProblems) }, [service])
  if (!dashboard?.wildcardApplication) return <div className="stack"><PageHeading eyebrow="Wildcard" title="Applications closed" /><Card className="center-card"><WaitingState text="Your team did not enter Wildcard. Please wait for the event to continue." /></Card></div>
  return (
    <div className="stack">
      <PageHeading eyebrow="Wildcard round" title="Wildcard problem pool">Review the available challenges. Selection is not open yet.</PageHeading>
      <Card className="preview-timer"><span>Time to review</span><Countdown seconds={dashboard?.gameConfig.wildcardPreviewSeconds ?? 0} timing={dashboard?.timing} /></Card>
      <div className="problem-grid wildcard-grid">
        {problems.map((problem) => (
          <Card key={problem.id} className="wildcard-card">
            <p className="eyebrow">Problem #{String(problem.number).padStart(2, '0')}</p>
            <h2>{problem.title}</h2>
            <p className="muted">{problem.summary}</p>
          </Card>
        ))}
      </div>
      <AdvanceButton label="Waiting for wildcard bidding" />
    </div>
  )
}
