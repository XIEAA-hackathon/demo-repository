import { useEffect, useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import type { LeaderboardEntry } from '../types'
import { Card } from '../components/ui'

export default function ResultsPage() {
  const { dashboard, service } = useParticipant()
  const [results, setResults] = useState<LeaderboardEntry[]>([])
  useEffect(() => { void service.getLeaderboard().then(setResults) }, [service])
  const myResult = dashboard && results.find((result) => result.teamId === dashboard.team.id)
  return (
    <div className="stack results-page">
      <p className="eyebrow results-page__brand">XIE Alumni Hackathon</p>
      <h1 className="results-page__title">Bid to Build · Final standings</h1>
      {myResult && <p className="results-page__myline">Your team finished <strong>#{myResult.rank}</strong></p>}
      <div className="podium">
        {results.slice(0, 3).map((result) => (
          <Card key={result.teamId} className={`podium__card${dashboard?.team.id === result.teamId ? ' is-team' : ''}`}>
            <span className="podium__rank">#{result.rank}</span>
            <h2>{result.teamName}</h2>
            <p>{result.amount.toLocaleString()} coin bid</p>
            {dashboard?.team.id === result.teamId && <strong className="team-tag">Your team</strong>}
          </Card>
        ))}
      </div>
      {!results.length && <p className="muted results-page__note">Final standings are not available yet.</p>}
    </div>
  )
}
