import { useParticipant } from '../ParticipantContext'
import { Card } from '../components/ui'

export default function WaitingPage() {
  const { dashboard } = useParticipant()
  if (!dashboard) return null
  const leader = dashboard.team.members.find((member) => member.id === dashboard.team.leaderId)

  return (
    <div className="waiting-room">
      <p className="waiting-room__brand">Xie Alumni Hackathon</p>
      <h1 className="waiting-room__title">Bid to Build</h1>
      <p className="waiting-room__status">Event has not started</p>

      <div className="waiting-indicator" role="status" aria-label="Waiting for the event to start">
        <span /><span /><span />
      </div>
      <p className="waiting-room__lead">Waiting for the organizers to start the event…</p>

      <Card className="team-summary">
        <h2>{dashboard.team.name}</h2>
        <div className="team-summary__grid">
          <div>
            <span className="team-summary__label">Members</span>
            <ul className="team-summary__members">
              {dashboard.team.members.map((member) => <li key={member.id}>{member.name.split(' ')[0]}</li>)}
            </ul>
          </div>
          <dl>
            <div><dt>Team leader</dt><dd>{leader?.name ?? 'Not selected yet'}</dd></div>
            <div><dt>Coin balance</dt><dd>🪙 {dashboard.wallet.balance.toLocaleString()}</dd></div>
            <div><dt>Event status</dt><dd className="tag-waiting">Waiting</dd></div>
          </dl>
        </div>
      </Card>

      <p className="waiting-room__note">Keep this page open. The event will begin when the organizer starts Round 1.</p>
    </div>
  )
}