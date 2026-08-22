import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { API_URL } from '../services/api/config'
import './RoundLeaderboard.css'

interface LeaderboardRow {
  rank: number
  team_id: number
  team_name: string
  value: number
  qualified?: boolean
}

export default function RoundLeaderboard() {
  const { round } = useParams()
  const validRound = round === 'wildcard' ? 'wildcard' : 'round-1'
  const [rows, setRows] = useState<LeaderboardRow[]>([])
  const [connection, setConnection] = useState<'live' | 'reconnecting' | 'reconnected'>('reconnecting')
  const [slots, setSlots] = useState<number | null>(null)
  const [page, setPage] = useState(0)

  useEffect(() => {
    let active = true
    let phaseActive = true
    let failures = 0
    let timer: number | undefined
    let settledTimer: number | undefined
    const schedule = () => {
      if (!active) return
      const delay = document.visibilityState === 'hidden' ? 60_000 : phaseActive ? 2_000 : 30_000
      timer = window.setTimeout(load, failures ? Math.min(30_000, 1_000 * 2 ** failures) : delay)
    }
    const load = async () => {
      try {
        const response = await fetch(`${API_URL}/leaderboard/${validRound}`, { cache: 'no-store' })
        if (!response.ok) throw new Error('Leaderboard unavailable')
        const data = await response.json()
        if (active) {
          const recovered = failures > 0
          failures = 0
          phaseActive = Boolean(data.active)
          setRows(data.rows || [])
          setSlots(data.slot_count ?? null)
          setConnection(recovered ? 'reconnected' : 'live')
          if (recovered) settledTimer = window.setTimeout(() => setConnection('live'), 2_000)
        }
      } catch {
        if (active) { failures += 1; setConnection('reconnecting') }
      } finally { schedule() }
    }
    const onVisibility = () => {
      if (timer !== undefined) window.clearTimeout(timer)
      if (document.visibilityState === 'visible') void load()
      else schedule()
    }
    void load()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
      if (settledTimer !== undefined) window.clearTimeout(settledTimer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [validRound])

  // Six rows keep every page inside a 1440×900 event display, including the
  // header, page indicator, and safe outer spacing.
  const pageSize = 6
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize))
  useEffect(() => {
    setPage((current) => Math.min(current, pageCount - 1))
    if (pageCount === 1) return
    const interval = window.setInterval(() => setPage((current) => (current + 1) % pageCount), 8000)
    return () => window.clearInterval(interval)
  }, [pageCount])
  const visibleRows = rows.slice(page * pageSize, (page + 1) * pageSize)

  const label = validRound === 'wildcard' ? 'Wildcard' : 'Round 1'
  return <main className="tv-leaderboard">
    <header><div><span>Bid to Build</span><h1>{label} — Live Leaderboard</h1></div><div className={`tv-live ${connection === 'live' ? '' : 'offline'}`}><i />{connection === 'live' ? 'Live' : connection === 'reconnected' ? 'Reconnected' : 'Reconnecting…'}</div></header>
    <ol>{visibleRows.map((row) => <li key={row.team_id} className={row.qualified ? 'qualified' : ''}><strong>#{row.rank}</strong><span>{row.team_name}{validRound === 'wildcard' && row.qualified && <em>Qualified</em>}</span><b>{row.value.toLocaleString()} <small>coins</small></b></li>)}</ol>
    {!rows.length && <div className="tv-empty">Waiting for the first {label.toLowerCase()} bid…</div>}
    {(validRound === 'wildcard' && slots != null || pageCount > 1) && <footer>{validRound === 'wildcard' && slots != null && <>Top {slots} teams advance to ranked problem selection.</>}{pageCount > 1 && <span>Page {page + 1} / {pageCount}</span>}</footer>}
  </main>
}
