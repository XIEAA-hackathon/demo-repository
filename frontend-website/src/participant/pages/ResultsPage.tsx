import { useParticipant } from '../ParticipantContext'
import { Card } from '../components/ui'

export default function ResultsPage() {
  const { dashboard } = useParticipant()
  const results = dashboard?.finalResults
  const places = results ? [
    { label: '1st Place', medal: '🥇', winner: results.firstPlace, tone: 'gold' },
    { label: '2nd Place', medal: '🥈', winner: results.secondPlace, tone: 'silver' },
    { label: '3rd Place', medal: '🥉', winner: results.thirdPlace, tone: 'bronze' },
  ] : []
  return (
    <div className="stack results-page">
      <p className="eyebrow results-page__brand">XIE Alumni Hackathon</p>
      <h1 className="results-page__title">Final Results</h1>
      <div className="podium">
        {places.map((place) => (
          <Card key={place.label} className={`podium__card podium__card--${place.tone}${dashboard?.team.id === place.winner.teamId ? ' is-team' : ''}`}>
            <span className="podium__medal" aria-hidden="true">{place.medal}</span>
            <span className="podium__rank">{place.label}</span>
            <h2>{place.winner.teamName}</h2>
            {dashboard?.team.id === place.winner.teamId && <strong className="team-tag">Your team</strong>}
          </Card>
        ))}
      </div>
      {!results && <p className="muted results-page__note">Final results have not been published yet.</p>}
    </div>
  )
}
