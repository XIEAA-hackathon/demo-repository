import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminApplication } from './App'
import {
  downloadRoundOneAssignments,
  downloadWildcardAssignments,
  getAdminConfig,
  getAdminHealth,
  getAdminState,
  getBidHistory,
  getProblemStatements,
  getTeams,
} from './services/api'
import { connectAuctionSocket } from './services/auctionSocket'

vi.mock('./components/LabConfiguration', () => ({ default: () => null }))
vi.mock('./services/auctionSocket', () => ({ connectAuctionSocket: vi.fn() }))
vi.mock('./services/api', async (original) => ({
  ...await original(),
  downloadRoundOneAssignments: vi.fn(),
  downloadWildcardAssignments: vi.fn(),
  getAdminConfig: vi.fn(),
  getAdminHealth: vi.fn(),
  getAdminState: vi.fn(),
  getBidHistory: vi.fn(),
  getProblemStatements: vi.fn(),
  getTeams: vi.fn(),
}))

const fullLoadMocks = [getTeams, getProblemStatements, getBidHistory, getAdminState, getAdminConfig, getAdminHealth]
let host
let root
let hidden
let socket

const render = async () => {
  await act(async () => root.render(<AdminApplication onLogout={vi.fn()} />))
  await act(async () => vi.advanceTimersByTimeAsync(0))
  await act(async () => vi.advanceTimersByTimeAsync(100))
}

describe('AdminApplication reconciliation', () => {
  beforeEach(() => {
    Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
    vi.useFakeTimers()
    vi.clearAllMocks()
    hidden = false
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden })
    getTeams.mockResolvedValue([])
    getProblemStatements.mockResolvedValue([])
    getBidHistory.mockResolvedValue([])
    getAdminState.mockResolvedValue({ event_state: 'WAITING', current_round: 1, timing: { paused: true, remaining_seconds: 0 } })
    getAdminConfig.mockResolvedValue({ starting_coins: 5000 })
    getAdminHealth.mockResolvedValue({ database: 'healthy' })
    connectAuctionSocket.mockImplementation((handlers) => { socket = handlers; return vi.fn() })
    host = document.createElement('div')
    root = createRoot(host)
  })

  afterEach(() => {
    act(() => root.unmount())
    vi.useRealTimers()
  })

  it('runs two periodic full reconciliations during five healthy minutes', async () => {
    await render()
    await act(async () => socket.onStatus('connected'))
    fullLoadMocks.forEach((mock) => mock.mockClear())

    await act(async () => vi.advanceTimersByTimeAsync(300_000))

    fullLoadMocks.forEach((mock) => expect(mock).toHaveBeenCalledTimes(2))
  })

  it('loads teams once at startup and omits the removed management pages', async () => {
    await render()

    expect(getTeams).toHaveBeenCalledTimes(1)
    expect(host.querySelector('button[aria-label="Problems"]')).toBeNull()
    expect(host.querySelector('button[aria-label="Event log"]')).toBeNull()
    expect(connectAuctionSocket).toHaveBeenCalledTimes(1)
  })

  it('uses the 12-second fallback while disconnected', async () => {
    await render()
    await act(async () => socket.onStatus('disconnected'))
    fullLoadMocks.forEach((mock) => mock.mockClear())

    await act(async () => vi.advanceTimersByTimeAsync(11_999))
    expect(getTeams).not.toHaveBeenCalled()
    await act(async () => vi.advanceTimersByTimeAsync(1))
    fullLoadMocks.forEach((mock) => expect(mock).toHaveBeenCalledTimes(1))
  })

  it('does no global reconciliation for assignment events and only refreshes problems after an external import', async () => {
    await render()
    fullLoadMocks.forEach((mock) => mock.mockClear())

    await act(async () => socket.onMessage({ type: 'round1_assignment_changed', payload: { team_id: 1, coins: 4800 } }))
    fullLoadMocks.forEach((mock) => expect(mock).not.toHaveBeenCalled())

    await act(async () => socket.onMessage({ type: 'external_problems_imported', payload: { created: 1 } }))
    expect(getProblemStatements).toHaveBeenCalledTimes(1)
    ;[getTeams, getBidHistory, getAdminState, getAdminConfig, getAdminHealth]
      .forEach((mock) => expect(mock).not.toHaveBeenCalled())
  })

  it('never preloads assignment exports on startup or realtime assignment events', async () => {
    await render()
    expect(downloadRoundOneAssignments).not.toHaveBeenCalled()
    expect(downloadWildcardAssignments).not.toHaveBeenCalled()

    await act(async () => {
      socket.onMessage({ type: 'round_updated', payload: { action: 'winners_assigned' } })
      socket.onMessage({ type: 'round1_assignment_changed', payload: { team_id: 1, coins: 4800 } })
      socket.onMessage({ type: 'wildcard_updated', payload: { action: 'problem_selected' } })
    })

    expect(downloadRoundOneAssignments).not.toHaveBeenCalled()
    expect(downloadWildcardAssignments).not.toHaveBeenCalled()
  })

  it('runs one immediate reconciliation on visibility restore without overlapping requests', async () => {
    hidden = true
    await render()
    await act(async () => socket.onStatus('connected'))
    fullLoadMocks.forEach((mock) => mock.mockClear())

    hidden = false
    await act(async () => document.dispatchEvent(new Event('visibilitychange')))

    fullLoadMocks.forEach((mock) => expect(mock).toHaveBeenCalledTimes(1))
  })

  it('deduplicates overlapping full reconciliation requests', async () => {
    let resolveTeams
    getTeams.mockImplementationOnce(() => new Promise((resolve) => { resolveTeams = resolve }))
    await render()

    await act(async () => {
      window.dispatchEvent(new Event('admin:resync'))
      window.dispatchEvent(new Event('admin:resync'))
    })

    ;[getTeams, getProblemStatements, getBidHistory, getAdminState, getAdminConfig]
      .forEach((mock) => expect(mock).toHaveBeenCalledTimes(1))
    expect(getAdminHealth).not.toHaveBeenCalled()
    await act(async () => resolveTeams([]))
    expect(getAdminHealth).toHaveBeenCalledTimes(1)
  })

  it('summarizes the same logged-in rows and updates from existing presence events', async () => {
    getTeams.mockResolvedValue([
      { id: 1, team_name: 'Alpha', coins: 100, members: [], is_approved: true, logged_in: true },
      { id: 2, team_name: 'Beta', coins: 100, members: [], is_approved: true, logged_in: false },
      { id: 3, team_name: 'Gamma', coins: 100, members: [], is_approved: false, logged_in: false },
    ])
    await render()
    getTeams.mockClear()
    act(() => host.querySelector('button[aria-label="Teams"]').click())

    const summary = host.querySelector('.teams-login-summary')
    expect(summary.textContent).toContain('1 / 3')
    expect(Array.from(host.querySelectorAll('tbody tr')).filter((row) => row.textContent.includes('YES'))).toHaveLength(1)

    await act(async () => socket.onMessage({ type: 'participant_presence_changed', payload: { logged_in_team_ids: [2, 3] } }))

    expect(summary.textContent).toContain('2 / 3')
    expect(Array.from(host.querySelectorAll('tbody tr')).filter((row) => row.textContent.includes('YES'))).toHaveLength(2)
    expect(getTeams).not.toHaveBeenCalled()
  })

  it('does not fetch teams for bids, timer sync, or presence', async () => {
    getTeams.mockResolvedValue([
      { id: 1, team_name: 'Alpha', coins: 100, members: [], is_approved: true, logged_in: true },
      { id: 2, team_name: 'Beta', coins: 100, members: [], is_approved: true, logged_in: false },
    ])
    await render()
    getTeams.mockClear()

    await act(async () => {
      socket.onMessage({ type: 'bid_updated', payload: { bid: { team_id: 1, ps_id: 10, round: 1, amount: 20 } } })
      socket.onMessage({ type: 'wildcard_bid_updated', payload: { bid: { team_id: 1, amount: 20 } } })
      socket.onMessage({ type: 'timer_sync', payload: { event_state: 'ROUND1_BIDDING', timing: { paused: false, remaining_seconds: 20 } } })
      socket.onMessage({ type: 'participant_presence_changed', payload: { logged_in_team_ids: [2] } })
      await vi.advanceTimersByTimeAsync(500)
    })

    expect(getTeams).not.toHaveBeenCalled()
  })

  it('patches authoritative settlement balances without fetching teams', async () => {
    getTeams.mockResolvedValue([
      { id: 1, team_name: 'Alpha', coins: 100, members: [], is_approved: true, logged_in: true },
      { id: 2, team_name: 'Beta', coins: 100, members: [], is_approved: true, logged_in: false },
    ])
    await render()
    getTeams.mockClear()
    act(() => host.querySelector('button[aria-label="Teams"]').click())
    const coinFor = (name) => Array.from(host.querySelectorAll('tbody tr'))
      .find((row) => row.textContent.includes(name))
      .querySelector('.coins').textContent

    await act(async () => socket.onMessage({
      type: 'round_updated',
      payload: { action: 'winners_assigned', winners: [{ team_id: 1, coins: 80 }] },
    }))
    expect(coinFor('Alpha')).toBe('80')

    await act(async () => socket.onMessage({
      type: 'round1_assignment_changed',
      payload: { team_id: 2, coins: 75 },
    }))
    expect(coinFor('Beta')).toBe('75')

    await act(async () => socket.onMessage({
      type: 'wildcard_updated',
      payload: { action: 'bidding_finalized', winners: [{ team_id: 1, coins: 50 }] },
    }))
    expect(coinFor('Alpha')).toBe('50')
    expect(getTeams).not.toHaveBeenCalled()
  })

  it('coalesces settlement events without balances into one teams refresh', async () => {
    await render()
    getTeams.mockClear()

    await act(async () => {
      socket.onMessage({ type: 'round_updated', payload: { action: 'winners_assigned', winners: [{ team_id: 1 }] } })
      socket.onMessage({ type: 'wildcard_updated', payload: { action: 'bidding_finalized', winners: [{ team_id: 2 }] } })
      socket.onMessage({ type: 'team_updated', payload: { action: 'event_reset' } })
      await vi.advanceTimersByTimeAsync(199)
    })
    expect(getTeams).not.toHaveBeenCalled()
    await act(async () => vi.advanceTimersByTimeAsync(1))
    expect(getTeams).toHaveBeenCalledTimes(1)
  })

  it('queues at most one follow-up when a teams refresh is in flight', async () => {
    await render()
    getTeams.mockClear()
    let resolveFirst
    getTeams
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
      .mockResolvedValue([])

    await act(async () => {
      socket.onMessage({ type: 'round_updated', payload: { action: 'winners_assigned', winners: [] } })
      await vi.advanceTimersByTimeAsync(200)
    })
    expect(getTeams).toHaveBeenCalledTimes(1)

    await act(async () => {
      socket.onMessage({ type: 'wildcard_updated', payload: { action: 'bidding_finalized', winners: [] } })
      socket.onMessage({ type: 'team_updated', payload: { action: 'event_reset' } })
      await vi.advanceTimersByTimeAsync(200)
    })
    expect(getTeams).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveFirst([])
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(getTeams).toHaveBeenCalledTimes(2)
  })

  it('retains full reconciliation on websocket reconnect', async () => {
    await render()
    fullLoadMocks.forEach((mock) => mock.mockClear())

    await act(async () => {
      socket.onStatus('reconnected')
      await vi.advanceTimersByTimeAsync(300)
    })

    fullLoadMocks.forEach((mock) => expect(mock).toHaveBeenCalledTimes(1))
  })
})
