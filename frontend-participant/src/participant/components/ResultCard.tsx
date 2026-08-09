import type { Problem } from '../types'
import { Avatar } from './ui'

export default function ResultCard({ teamName, problem, winningBid, balance }: { teamName: string; problem: Problem | null; winningBid: number; balance: number }) {
  return (
    <div className="result-card" role="status">
      <div className="result-card__glow" aria-hidden="true" />
      <div className="result-card__inner">
        <span className="result-card__badge">🏆 Problem secured</span>
        <Avatar name={teamName} size="lg" />
        <h2 className="result-card__team">{teamName}</h2>
        <div className="result-card__problem">
          <small>Problem #{problem ? String(problem.number).padStart(2, '0') : '—'}</small>
          <strong>{problem?.title ?? 'Assigned problem'}</strong>
        </div>
        <dl className="result-card__stats">
          <div><dt>Winning bid</dt><dd>🪙 {winningBid.toLocaleString()}</dd></div>
          <div><dt>Remaining balance</dt><dd>🪙 {balance.toLocaleString()}</dd></div>
        </dl>
      </div>
    </div>
  )
}