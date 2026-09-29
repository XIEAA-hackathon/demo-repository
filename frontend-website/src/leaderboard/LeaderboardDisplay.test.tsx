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
