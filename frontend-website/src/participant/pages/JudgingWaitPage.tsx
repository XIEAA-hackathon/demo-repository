import WaitingState from '../components/WaitingState'
import { Card, PageHeading } from '../components/ui'

export default function JudgingWaitPage() {
  return (
    <div className="hero-state judging-wait">
      <PageHeading eyebrow="Final stage" title="Judging in progress">Please wait for the final results.</PageHeading>
      <Card className="center-card">
        <WaitingState text="Judging is currently being conducted offline." />
      </Card>
    </div>
  )
}
