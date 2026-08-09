import { useParticipant } from '../ParticipantContext'
import AdvanceButton from '../components/AdvanceButton'
import WaitingState from '../components/WaitingState'
import { Avatar, Card, PageHeading } from '../components/ui'

export default function JudgingWaitPage() {
  const { dashboard } = useParticipant()
  if (!dashboard) return null
  return (
    <div className="hero-state judging-wait">
      <PageHeading eyebrow="Submission complete" title="Your project is locked in">Judging will begin shortly.</PageHeading>
      <Card className="details-list details-list--agent">
        <div><Avatar name={dashboard.team.name} size="lg" /></div>
        <span><small>Team</small><strong>{dashboard.team.name}</strong></span>
        <span><small>Problem</small><strong>{dashboard.currentProblem?.title ?? '—'}</strong></span>
        <span><small>Repository</small><strong>{dashboard.submission?.repositoryUrl ?? 'Submitted'}</strong></span>
        <span><small>Submission time</small><strong>{dashboard.submission ? new Date(dashboard.submission.submittedAt).toLocaleString() : '—'}</strong></span>
      </Card>
      <WaitingState text="Waiting for the judges…" />
      <AdvanceButton label="Waiting for results to be published" />
    </div>
  )
}
