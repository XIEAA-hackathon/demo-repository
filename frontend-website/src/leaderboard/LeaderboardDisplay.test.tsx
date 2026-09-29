import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import LeaderboardDisplay from './LeaderboardDisplay'

const mock = vi.hoisted(() => ({ socket: vi.fn(), options: null as any }))
vi.mock('../services/realtime/connectReconnectingSocket', () => ({ connectReconnectingSocket: mock.socket }))
let host: HTMLDivElement
let root: ReturnType<typeof createRoot>
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.useFakeTimers(); mock.socket.mockReset()
  mock.socket.mockImplementation(options => { mock.options = options; return vi.fn() })
  host = document.createElement('div'); root = createRoot(host)
})
afterEach(() => { act(() => root.unmount()); vi.useRealTimers(); vi.unstubAllGlobals() })

it.each(['ROUND1', 'WILDCARD'])('renders %s deltas immediately without extra API calls', async round => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({
    mode: `${round}_LIVE`, event_state: `${round}_BIDDING`, problem: { id: 10, title: 'Problem' },
    rows: [{ rank: 1, team_id: 1, team_name: 'Team One', value: 100, timestamp: '2026-09-29T10:00:00Z' }],
    timing: { ends_at: null },
  }) })
  vi.stubGlobal('fetch', fetchMock)
  await act(async () => root.render(<LeaderboardDisplay token="token" onUnauthorized={vi.fn()} onLogout={vi.fn()} />))
  await act(async () => mock.options.onMessage({ type: round === 'ROUND1' ? 'bid_updated' : 'wildcard_bid_updated', payload: {
    round, ps_id: round === 'ROUND1' ? 10 : null, bid_id: 2, team_id: 2, team_name: 'Team Two', amount: 200, increment: 1, timestamp: '2026-09-29T10:00:01Z',
  } }))
  expect(host.querySelectorAll('.team-name')[0].textContent).toContain('Team Two')
  expect(host.querySelector('.bid-amount')?.textContent).toContain('200')
  expect(fetchMock).toHaveBeenCalledTimes(1)
  expect(mock.socket).toHaveBeenCalledTimes(1)
})

it('ignores a delta for another R1 problem', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ mode: 'ROUND1_LIVE', rows: [], problem: { id: 10 }, timing: { ends_at: null } }) }))
  await act(async () => root.render(<LeaderboardDisplay token="token" onUnauthorized={vi.fn()} onLogout={vi.fn()} />))
  await act(async () => mock.options.onMessage({ type: 'bid_updated', payload: { round: 'ROUND1', ps_id: 99, bid_id: 2, team_id: 2, amount: 200, increment: 1, timestamp: '2026-09-29T10:00:01Z' } }))
  expect(host.querySelectorAll('.leaderboard-row')).toHaveLength(0)
})

it('replays deltas over an older initial HTTP response without another request', async () => {
  let resolve!: (value: any) => void
  const fetchMock = vi.fn().mockImplementation(() => new Promise(done => { resolve = done }))
  vi.stubGlobal('fetch', fetchMock)
  await act(async () => root.render(<LeaderboardDisplay token="token" onUnauthorized={vi.fn()} onLogout={vi.fn()} />))
  await act(async () => mock.options.onMessage({ type: 'bid_updated', payload: { round: 'ROUND1', ps_id: 10, bid_id: 2, team_id: 2, team_name: 'Newest Bid', amount: 200, increment: 1, timestamp: '2026-09-29T10:00:01Z' } }))
  await act(async () => resolve({ ok: true, json: async () => ({ mode: 'ROUND1_LIVE', rows: [], problem: { id: 10 }, timing: { ends_at: null } }) }))
  expect(host.querySelector('.team-name')?.textContent).toContain('Newest Bid')
  await act(async () => vi.advanceTimersByTimeAsync(1_000))
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

it('applies timer frames without fetching a full display snapshot', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ mode: 'WILDCARD_LIVE', rows: [], timing: { ends_at: null } }) })
  vi.stubGlobal('fetch', fetchMock)
  await act(async () => root.render(<LeaderboardDisplay token="token" onUnauthorized={vi.fn()} onLogout={vi.fn()} />))
  await act(async () => mock.options.onMessage({ type: 'timer_sync', payload: { timing: { ends_at: null, paused: true } } }))
  await act(async () => vi.advanceTimersByTimeAsync(1_000))
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

const twelve = () => Array.from({ length: 12 }, (_, i) => ({ rank: i + 1, team_id: i + 1, team_name: `Bidder ${i + 1}`, value: 1200 - i * 10, timestamp: `2026-09-29T10:00:${String(i).padStart(2, '0')}Z` }))
const delta = (round: string, problem = 10) => ({ round, ps_id: round === 'ROUND1' ? problem : null, bid_id: 12, team_id: 12, team_name: 'Outside bidder', amount: 2000, increment: 1, timestamp: '2026-09-29T10:01:00Z' })
it.each(['ROUND1', 'WILDCARD'])('keeps %s Top 10 and inserts an outside bidder without GET', async round => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ mode: `${round}_LIVE`, rows: twelve(), problem: { id: 10 }, slot_count: 7 }) })
  vi.stubGlobal('fetch', fetchMock)
  await act(async () => root.render(<LeaderboardDisplay token="token" onUnauthorized={vi.fn()} onLogout={vi.fn()} />))
  expect(host.querySelectorAll('.leaderboard-row')).toHaveLength(10)
  await act(async () => mock.options.onMessage({ type: round === 'ROUND1' ? 'bid_updated' : 'wildcard_bid_updated', payload: delta(round) }))
  expect(host.querySelectorAll('.leaderboard-row')).toHaveLength(10)
  expect(host.querySelector('.team-name')?.textContent).toContain('Outside bidder')
  expect([...host.querySelectorAll('.team-name')].some(row => row.textContent?.includes('Bidder 10'))).toBe(false)
  expect(fetchMock).toHaveBeenCalledTimes(1)
  if (round === 'WILDCARD') expect(host.querySelectorAll('.top-five-badge')).toHaveLength(7)
})

it('shows committed R1 winners, ignores late bids, and clears them for the next problem', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ mode: 'ROUND1_LIVE', rows: twelve(), problem: { id: 10 } }) })
    .mockResolvedValue({ ok: true, json: async () => ({ mode: 'ROUND1_LIVE', rows: [{ rank: 1, team_id: 20, team_name: 'Next problem bidder', value: 500 }], problem: { id: 20 } }) })
  vi.stubGlobal('fetch', fetchMock)
  await act(async () => root.render(<LeaderboardDisplay token="token" onUnauthorized={vi.fn()} onLogout={vi.fn()} />))
  const winners = twelve().slice(1, 6).map(row => ({ team_id: row.team_id, team_name: row.team_name, amount: row.value }))
  await act(async () => mock.options.onMessage({ type: 'round_updated', payload: { round: 'ROUND1', action: 'winners_assigned', problem: { id: 10, number: 4 }, winners } }))
  expect(host.querySelector('h1')?.textContent).toContain('FINAL RESULT')
  expect(host.querySelectorAll('.leaderboard-row')).toHaveLength(5)
  expect(host.querySelector('.team-name')?.textContent).toContain('Bidder 2')
  expect([...host.querySelectorAll('.bid-time')].every(row => row.textContent?.trim() === 'WINNER')).toBe(true)
  await act(async () => mock.options.onMessage({ type: 'bid_updated', payload: delta('ROUND1') }))
  expect(host.textContent).not.toContain('Outside bidder')
  expect(fetchMock).toHaveBeenCalledTimes(1)
  await act(async () => {
    mock.options.onMessage({ type: 'round_updated', payload: { round: 'ROUND1', action: 'problem_selected', problem_id: 20 } })
    mock.options.onMessage({ type: 'event_state_changed', payload: { event_state: 'ROUND1_BIDDING', rounds: { ROUND1: { current_problem_id: 20 } } } })
  })
  expect(host.querySelectorAll('.leaderboard-row')).toHaveLength(0)
  await act(async () => vi.advanceTimersByTimeAsync(200))
  expect(host.textContent).toContain('Next problem bidder')
  expect(fetchMock).toHaveBeenCalledTimes(2)
  await act(async () => mock.options.onMessage({ type: 'bid_updated', payload: delta('ROUND1', 10) }))
  expect(host.textContent).not.toContain('Outside bidder')
})

it('loads Wildcard final ranking once and trusts persisted qualification over slot arithmetic', async () => {
  const finalRows = twelve().slice(0, 10).map(row => ({ ...row, qualified: row.rank <= 3 }))
  const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ mode: 'WILDCARD_LIVE', rows: twelve(), slot_count: 8 }) })
    .mockResolvedValue({ ok: true, json: async () => ({ mode: 'WILDCARD_FINAL', rows: finalRows, slot_count: 8 }) })
  vi.stubGlobal('fetch', fetchMock)
  await act(async () => root.render(<LeaderboardDisplay token="token" onUnauthorized={vi.fn()} onLogout={vi.fn()} />))
  await act(async () => { mock.options.onMessage({ type: 'wildcard_updated', payload: { action: 'bidding_finalized', winners: [] } }); await vi.advanceTimersByTimeAsync(200) })
  expect(host.querySelector('h1')?.textContent).toContain('FINAL RANKING')
  expect(host.querySelectorAll('.leaderboard-row')).toHaveLength(10)
  expect([...host.querySelectorAll('.bid-time')].filter(row => row.textContent?.trim() === 'QUALIFIED')).toHaveLength(3)
  expect([...host.querySelectorAll('.bid-time')].filter(row => row.textContent?.trim() === 'NOT QUALIFIED')).toHaveLength(7)
  await act(async () => mock.options.onMessage({ type: 'wildcard_bid_updated', payload: delta('WILDCARD') }))
  expect(host.textContent).not.toContain('Outside bidder')
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

it('does not let an old HTTP response overwrite the committed winner event', async () => {
  let resolve!: (value: any) => void
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => new Promise(done => { resolve = done })))
  await act(async () => root.render(<LeaderboardDisplay token="token" onUnauthorized={vi.fn()} onLogout={vi.fn()} />))
  await act(async () => mock.options.onMessage({ type: 'round_updated', payload: { round: 'ROUND1', action: 'winners_assigned', problem: { id: 10 }, winners: [{ team_id: 2, team_name: 'Actual winner', amount: 100 }] } }))
  await act(async () => resolve({ ok: true, json: async () => ({ mode: 'ROUND1_LIVE', rows: twelve(), problem: { id: 10 } }) }))
  expect(host.querySelector('h1')?.textContent).toContain('FINAL RESULT')
  expect(host.querySelector('.team-name')?.textContent).toContain('Actual winner')
})
