import type { ParticipantDashboard } from '../types'
import WaitingState from './WaitingState'
import { Card, PageHeading } from './ui'

export default function RoundOneComplete({ dashboard }: { dashboard: ParticipantDashboard }) {
  return <div className="stack">
    <PageHeading eyebrow="Round 1 complete" title="Your team has secured a problem" />
    <Card className="center-card">
      <span className="confirmation-mark">✓</span>
      <p className="eyebrow">Assigned problem</p>
      <h2>Problem #{dashboard.currentProblem?.number}</h2>
      <p>{dashboard.currentProblem?.description}</p>
      <p className="notice">You cannot participate in additional Round 1 bidding.</p>
      <WaitingState text="Please wait for Round 1 to finish." />
    </Card>
  </div>
}
