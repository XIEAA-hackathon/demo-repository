import type { Problem, WildcardProblem } from '../types'
import type { EventTiming } from '../types'
import Countdown from './Countdown'
import { Card, PageHeading } from './ui'

export default function ProblemPreview({
  problem,
  round,
  seconds,
  timing,
}: {
  problem: Problem | WildcardProblem
  round: string
  seconds: number
  timing?: EventTiming
}) {
  const previewComplete = Boolean(timing && !timing.endsAt && !timing.paused)
  return (
    <div className="stack">
      <PageHeading eyebrow={round} title={`Problem #${String(problem.number).padStart(2, '0')}`}>
        {previewComplete ? 'Preview complete. Waiting for admin to start bidding.' : 'Read the challenge. Bidding begins when the admin starts it.'}
      </PageHeading>
      <Card className="problem-card">
        <div className="problem-card__timer"><span>{previewComplete ? 'Preview complete' : 'Read the challenge'}</span><Countdown seconds={seconds} timing={timing} /></div>
        <h2>{problem.title}</h2>
        <p>{problem.description}</p>
      </Card>
    </div>
  )
}
