import { Link } from 'react-router-dom'
import { participantStageRoutes } from '../routeConfig'
import { useParticipant } from '../ParticipantContext'

export default function StageNavigation() {
  const { dashboard } = useParticipant()
  const current = dashboard?.eventState ?? 'WAITING'
  const currentIndex = participantStageRoutes.findIndex((stage) => stage.state === current)

  return (
    <aside className="stage-nav">
      <Link className="stage-nav__dashboard" to="/participant/dashboard">Participant dashboard</Link>
      <ol>
        {participantStageRoutes.map((stage, index) => (
          <li key={stage.state} className={index === currentIndex ? 'is-current' : index < currentIndex ? 'is-complete' : ''}>
            <span>{String(index + 1).padStart(2, '0')}</span>
            <small>{stage.label}</small>
          </li>
        ))}
      </ol>
      <p className="muted stage-nav__note">Stages are controlled live by the organizer.</p>
    </aside>
  )
}
