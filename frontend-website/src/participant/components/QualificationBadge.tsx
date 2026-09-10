export default function QualificationBadge({ rank, cutoff = 5 }: { rank: number | null; cutoff?: number }) {
  if (rank === null) {
    return (
      <div className="qualification">
        <span className="qualification__label">Current position</span>
        <span className="qualification__value">—</span>
      </div>
    )
  }
  const qualifying = rank <= cutoff
  return (
    <div className="qualification">
      <span className="qualification__label">Current position</span>
      <span className="qualification__value qualification__value--rank">#{rank}</span>
      <span className={`qualification__tag${qualifying ? ' is-qualifying' : ' is-cutoff'}`}>
        {qualifying ? 'Qualifying' : 'Below cut-off'}
      </span>
    </div>
  )
}