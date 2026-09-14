import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminApplication } from './App'
import {
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

    await act(async () => socket.onMessage({ type: 'round1_assignment_changed', payload: { team_id: 1 } }))
    fullLoadMocks.forEach((mock) => expect(mock).not.toHaveBeenCalled())

    await act(async () => socket.onMessage({ type: 'external_problems_imported', payload: { created: 1 } }))
    expect(getProblemStatements).toHaveBeenCalledTimes(1)
    ;[getTeams, getBidHistory, getAdminState, getAdminConfig, getAdminHealth]
      .forEach((mock) => expect(mock).not.toHaveBeenCalled())
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
})
