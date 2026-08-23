import { useEffect, useMemo, useState } from 'react'
import { API_URL } from '../services/api/config'
import './RoundLeaderboard.css'

interface LeaderboardRow {
  rank: number
  team_id: number
  team_name: string
  value: number
  qualified?: boolean
}

interface Winner {
  team_id: number
  team_name: string
}

interface PublicDisplay {
  mode: 'ROUND1_LIVE' | 'WILDCARD_LIVE' | 'JUDGING_WAITING' | 'RESULTS_WAITING' | 'RESULTS_PUBLISHED' | 'WAITING'
  event_state: string
  status_label: string
  problem?: { number: string; title: string } | null
  rows: LeaderboardRow[]
  slot_count?: number | null
  results?: {
    first_place: Winner
    second_place: Winner
    third_place: Winner
  } | null
  timing: {
    server_time: string
    ends_at: string | null
    paused: boolean
    paused_remaining_seconds: number | null
  }
}

const formatTime = (seconds: number) => {
  const safe = Math.max(0, seconds)
  const minutes = Math.floor(safe / 60)
  const remainder = safe % 60
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
}

export default function RoundLeaderboard() {
  const [display, setDisplay] = useState<PublicDisplay | null>(null)
  const [connection, setConnection] = useState<'live' | 'reconnecting' | 'reconnected'>('reconnecting')
  const [receivedAt, setReceivedAt] = useState(0)
  const [now, setNow] = useState(Date.now())
  const [page, setPage] = useState(0)

  useEffect(() => {
    let active = true
    let failures = 0
    let timer: number | undefined
    let settledTimer: number | undefined
    const load = async () => {
      try {
        const response = await fetch(`${API_URL}/public/leaderboard`, { cache: 'no-store' })
        if (!response.ok) throw new Error('Public display unavailable')
        const data = await response.json() as PublicDisplay
        if (active) {
          const recovered = failures > 0
          failures = 0
          setDisplay(data)
          setReceivedAt(Date.now())
          setConnection(recovered ? 'reconnected' : 'live')
          if (recovered) settledTimer = window.setTimeout(() => setConnection('live'), 2_000)
        }
      } catch {
        if (active) {
          failures += 1
          setConnection('reconnecting')
        }
      } finally {
        if (active) {
          const baseDelay = document.hidden ? 30_000 : 2_000
          timer = window.setTimeout(load, failures ? Math.min(30_000, 1_000 * 2 ** failures) : baseDelay)
        }
      }
    }
    const onVisibility = () => {
      if (timer !== undefined) window.clearTimeout(timer)
      if (!document.hidden) void load()
    }
    void load()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
      if (settledTimer !== undefined) window.clearTimeout(settledTimer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000)
    return () => window.clearInterval(timer)
  }, [])

  const remaining = useMemo(() => {
    if (!display) return 0
    if (display.timing.paused && display.timing.paused_remaining_seconds != null) return display.timing.paused_remaining_seconds
    if (!display.timing.ends_at) return 0
    const serverOffset = Date.parse(display.timing.server_time) - receivedAt
    return Math.max(0, Math.ceil((Date.parse(display.timing.ends_at) - (now + serverOffset)) / 1_000))
  }, [display, now, receivedAt])

  const rows = display?.rows ?? []
  const pageSize = 6
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize))
  useEffect(() => {
    setPage((current) => Math.min(current, pageCount - 1))
    if (pageCount === 1) return
    const interval = window.setInterval(() => setPage((current) => (current + 1) % pageCount), 8_000)
    return () => window.clearInterval(interval)
  }, [pageCount])
  const visibleRows = rows.slice(page * pageSize, (page + 1) * pageSize)
  const isLiveBidding = display?.mode === 'ROUND1_LIVE' || display?.mode === 'WILDCARD_LIVE'

  return <main className="tv-leaderboard">
    <header className="tv-header">
      <div><span className="tv-brand">Bid to Build</span><h1>{display?.status_label ?? 'Connecting to event'}</h1></div>
      <div className={`tv-live ${connection === 'live' ? '' : 'offline'}`} aria-live="polite"><i />{connection === 'live' ? 'Live' : connection === 'reconnected' ? 'Reconnected' : 'Reconnecting…'}</div>
    </header>

    {isLiveBidding && display && <>
      <section className="tv-stage" aria-label="Current bidding status">
        <div>{display.mode === 'ROUND1_LIVE' && display.problem ? <><small>Current problem</small><strong>Problem #{display.problem.number}</strong><span>{display.problem.title}</span></> : <><small>Wildcard places</small><strong>{display.slot_count ?? 0} slots</strong><span>Highest bids advance</span></>}</div>
        <div className="tv-clock"><small>Time remaining</small><strong>{formatTime(remaining)}</strong></div>
      </section>
      <ol>{visibleRows.map((row) => <li key={row.team_id} className={row.qualified ? 'qualified' : ''}><strong>#{row.rank}</strong><span>{row.team_name}</span><b>{row.value.toLocaleString()} <small>coins</small></b></li>)}</ol>
      {!rows.length && <div className="tv-empty">Waiting for the first bid…</div>}
      {(display.mode === 'WILDCARD_LIVE' && display.slot_count != null || pageCount > 1) && <footer>{display.mode === 'WILDCARD_LIVE' && display.slot_count != null && <>Top {display.slot_count} teams advance.</>}{pageCount > 1 && <span>Page {page + 1} / {pageCount}</span>}</footer>}
    </>}

    {display?.mode === 'RESULTS_PUBLISHED' && display.results && <section className="tv-results" aria-label="Final results">
      {[
        { label: '1st Place', medal: '🥇', winner: display.results.first_place },
        { label: '2nd Place', medal: '🥈', winner: display.results.second_place },
        { label: '3rd Place', medal: '🥉', winner: display.results.third_place },
      ].map((place) => <article key={place.label}><span aria-hidden="true">{place.medal}</span><small>{place.label}</small><strong>{place.winner.team_name}</strong></article>)}
    </section>}

    {display && !isLiveBidding && display.mode !== 'RESULTS_PUBLISHED' && <section className="tv-waiting">
      <strong>{display.mode === 'JUDGING_WAITING' ? 'Judging is currently being conducted offline.' : display.status_label}</strong>
      <span>{display.mode === 'JUDGING_WAITING' ? 'Please wait for the final results.' : 'The display will update automatically when the event advances.'}</span>
    </section>}
  </main>
}
