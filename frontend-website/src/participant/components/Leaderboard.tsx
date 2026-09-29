import type { LeaderboardEntry } from '../types'
import QualificationBadge from './QualificationBadge'

export default function Leaderboard({ entries, currentTeamId, cutoff = 5, cutoffLabel = 'Qualification cut-off', finalRound }: { entries: LeaderboardEntry[]; currentTeamId: string; cutoff?: number; cutoffLabel?: string; finalRound?: 'ROUND1' | 'WILDCARD' }) {
  const teamEntry = entries.find((entry) => entry.teamId === currentTeamId) ?? null
  return (
    <div className="leaderboard">
      <div className="leaderboard__head"><span>Rank · Team</span><span>Bid</span></div>
      <div className="leaderboard__body">
        <ol>
          {entries.map((entry) => {
            const isTeam = entry.teamId === currentTeamId
            const isTop = entry.rank === 1
            const belowCutoff = finalRound ? entry.qualified === false : entry.rank > cutoff
            const className = [
              isTeam ? 'is-team' : '',
              isTop ? 'is-first' : '',
              belowCutoff ? 'is-cutoff' : '',
              (finalRound ? entry.qualified : entry.rank <= cutoff) && !isTeam ? 'is-qualified' : '',
            ].filter(Boolean).join(' ')
            return (
              <li key={entry.teamId} className={className}>
                <span><b>{entry.rank}</b>{isTeam && <i className="leaderboard__you" aria-label="Your team">YOU</i>} {entry.teamName}</span>
                <strong>{entry.amount}{finalRound && <small style={{ display: 'block' }}>{finalRound === 'ROUND1' ? 'WINNER' : entry.qualified ? 'QUALIFIED' : 'NOT QUALIFIED'}</small>}</strong>
              </li>
            )
          })}
        </ol>
      </div>
      {!finalRound && entries.length >= cutoff && (
        <div className="cutoff" role="presentation"><span>{cutoffLabel} · Top {cutoff}</span></div>
      )}
      {!finalRound && <QualificationBadge rank={teamEntry?.rank ?? null} cutoff={cutoff} />}
    </div>
  )
}
