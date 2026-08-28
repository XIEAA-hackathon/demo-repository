import type { ParticipantDashboard } from '../types'
import WaitingState from './WaitingState'
import { Card, PageHeading, Stat } from './ui'

export default function RoundOneComplete({ dashboard }: { dashboard: ParticipantDashboard }) {
  return <div className="stack">
    <PageHeading eyebrow="Round 1 complete" title="Your team has secured a problem" />
    <Card className="center-card">
      <span className="confirmation-mark">✓</span>
      <p className="eyebrow">Assigned problem</p>
      {dashboard.round1AssignmentType === 'MANUAL_ASSIGNMENT' &&
        <p className="notice">Assigned by the Round 1 administrator</p>}
      <small>Problem #{dashboard.currentProblem?.number}</small>
      <h2>{dashboard.currentProblem?.title}</h2>
      <p className="muted">{dashboard.currentProblem?.description}</p>
      {dashboard.round1AssignmentType === 'MANUAL_ASSIGNMENT' && <div className="stats-grid">
        <Stat label="Assignment Cost" value={`${dashboard.round1AssignmentCost ?? 0} coins`} />
        <Stat label="Remaining Balance" value={`${dashboard.wallet.balance} coins`} />
      </div>}
      <p className="notice">You cannot participate in additional Round 1 bidding.</p>
      <WaitingState text="Please wait for Round 1 to finish." />
    </Card>
  </div>
}
