import { Link } from 'react-router-dom'
import { useParticipant } from '../ParticipantContext'
import { getStageRoute } from '../routeConfig'
import type { ParticipantEventState } from '../types'
import { Card, PageHeading } from '../components/ui'

const roundLabel: Record<ParticipantEventState, string> = {
  WAITING: 'Not started',
  ROUND1_PREVIEW: 'Round 1',
  ROUND1_BIDDING: 'Round 1',
  ROUND1_RESULT: 'Round 1',
  WILDCARD_APPLICATION: 'Wildcard',
  WILDCARD_PREVIEW: 'Wildcard',
  WILDCARD_BIDDING: 'Wildcard',
  WILDCARD_SELECTION: 'Wildcard',
  CODING: 'Coding',
  SUBMISSION: 'Submission',
  JUDGING_WAIT: 'Judging',
  RESULTS: 'Results',
}

const nextAction: Record<ParticipantEventState, string> = {
  WAITING: 'Problem preview starts when the organizer begins.',
  ROUND1_PREVIEW: 'Review the round one problem before bidding.',
  ROUND1_BIDDING: 'Place your best bid before the auction closes.',
  ROUND1_RESULT: 'See who won the auction and lock the problem.',
  WILDCARD_APPLICATION: 'Apply for a wildcard problem while you still can.',
  WILDCARD_PREVIEW: 'Review the wildcard problem before bidding.',
  WILDCARD_BIDDING: 'Bid to secure your wildcard problem.',
  WILDCARD_SELECTION: 'Choose your team’s wildcard problem.',
  CODING: 'Build and commit your solution now.',
  SUBMISSION: 'Submit the final repository for judging.',
  JUDGING_WAIT: 'Sit tight while judges score your submission.',
  RESULTS: 'The final standings are in.',
}

function KpiCard({ label, value, hint, emoji }: { label: string; value: string; hint?: string; emoji?: string }) {
  return (
    <Card className="kpi">
      <span className="kpi__label">{label}</span>
      <div className="kpi__value">{emoji && <span className="kpi__emoji">{emoji}</span>}<strong>{value}</strong></div>
      {hint && <span className="kpi__hint">{hint}</span>}
    </Card>
  )
}

export default function DashboardPage() {
  const { dashboard, loading } = useParticipant()
  if (loading || !dashboard) return <p className="muted">Loading dashboard…</p>
  const leader = dashboard.team.members.find((member) => member.id === dashboard.team.leaderId)
  const stage = getStageRoute(dashboard.eventState)

  return (
    <div className="stack">
      <PageHeading eyebrow="Participant dashboard" title={dashboard.team.name}>
        {dashboard.currentUser.name} · {dashboard.isLeader ? 'Team leader' : 'Team member · View only'}
      </PageHeading>

      <div className="dashboard-grid">
        <Card className="dash-team">
          <span className="eyebrow">Team status</span>
          <h2>{dashboard.team.name}</h2>
          <p>{dashboard.team.members.length} members · {leader ? `led by ${leader.name}` : 'leader not selected'}</p>
        </Card>

        <KpiCard label="Current stage" value={roundLabel[dashboard.eventState]} emoji="🔁" hint={stage.label} />
        <KpiCard label="Coin balance" value={dashboard.wallet.balance.toLocaleString()} emoji="🪙" hint="coins" />
        <KpiCard label="Team leader" value={leader?.name ?? '—'} emoji="👑" hint={leader ? 'ready to act' : 'not selected'} />
      </div>

      <div className="two-column">
        <Card className="dash-problem">
          <span className="eyebrow">Current problem</span>
          <h2>{dashboard.currentProblem?.title ?? 'Waiting for auction'}</h2>
          {dashboard.currentProblem ? (
            <p>{dashboard.currentProblem.summary}</p>
          ) : (
            <p className="muted">A problem will appear here once the auction for your round begins.</p>
          )}
        </Card>

        <Card className="dash-next">
          <span className="eyebrow">Next action</span>
          <h2>{stage.label}</h2>
          <p className="muted">{dashboard.isLeader ? nextAction[dashboard.eventState] : `Spectator mode: ${nextAction[dashboard.eventState]}`}</p>
          {!dashboard.isLeader && <p className="notice">You see the same live team state; mutation controls remain reserved for the registered team leader.</p>}
          <Link className="button button--primary" to={stage.path}>Open current stage</Link>
        </Card>
      </div>
    </div>
  )
}
