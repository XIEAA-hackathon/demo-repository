import StyleBoundary from '../shared/components/StyleBoundary'
import ParticipantApp from './ParticipantApp'
import participantStyles from './styles/participant.css?inline'

export default function ParticipantRoute() {
  return (
    <StyleBoundary rootClassName="participant-root" styles={participantStyles}>
      <ParticipantApp />
    </StyleBoundary>
  )
}
