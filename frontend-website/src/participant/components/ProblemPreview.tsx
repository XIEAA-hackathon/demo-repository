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
  return (
    <div className="stack">
      <PageHeading eyebrow={round} title={`Problem #${String(problem.number).padStart(2, '0')}`}>
        Read the challenge. Bid controls unlock when the preview ends.
      </PageHeading>
      <Card className="problem-card">
        <div className="problem-card__timer"><span>Read the challenge</span><Countdown seconds={seconds} timing={timing} /></div>
        <h2>{problem.title}</h2>
        <p>{problem.description}</p>
      </Card>
    </div>
  )
}
