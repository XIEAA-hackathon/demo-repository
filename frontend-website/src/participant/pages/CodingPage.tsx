import { useParticipant } from '../ParticipantContext'
import AdvanceButton from '../components/AdvanceButton'
import Countdown from '../components/Countdown'
import { Card, CoinBalance, PageHeading, Stat } from '../components/ui'

export default function CodingPage() {
  const { dashboard } = useParticipant()
  if (!dashboard) return null
  const submitted = Boolean(dashboard.submission)
  return (
    <div className="stack coding-page">
      <PageHeading eyebrow="Coding round" title="Build your solution">Stay focused. Submission opens before the coding timer ends.</PageHeading>
      <Card className="challenge-card">
        <p className="eyebrow">Your challenge</p>
        <h2>{dashboard.currentProblem?.title ?? 'Smart Water Distribution System'}</h2>
        <p>{dashboard.currentProblem?.summary}</p>
      </Card>
      <div className="stats-grid">
        <Stat label="Time remaining" value={<Countdown timing={dashboard.timing} showHours />} />
        <Stat label="Team coins" value={<CoinBalance value={dashboard.wallet.balance} />} />
        <Stat label="Submission status" value={submitted ? 'Submitted' : 'Not submitted'} />
      </div>
      <AdvanceButton label="Go to submission" />
    </div>
  )
}
