import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AdminApplication, RoundControlPage, WildcardControlPage } from './App'

const mocks = vi.hoisted(() => ({ get: vi.fn(), end: vi.fn(), open: vi.fn(), state: vi.fn(), socket: null as any }))
vi.mock('./services/auctionSocket', () => ({ connectAuctionSocket: (options: any) => { mocks.socket = options; return vi.fn() } }))
vi.mock('./components/LabConfiguration', () => ({ default: () => null }))
vi.mock('./services/api', async importOriginal => ({ ...await importOriginal<any>(),
  getRoundControl: mocks.get, endRoundOne: mocks.end, openWildcardApplications: mocks.open,
  getAdminState: mocks.state, getTeams: async () => [], getProblemStatements: async () => [], getBidHistory: async () => [],
  getAdminConfig: async () => null, getAdminHealth: async () => ({ database: 'healthy' }), getLabAllocation: async () => null,
}))
const snapshot = (wildcard = false, status = wildcard ? 'NOT_STARTED' : 'READY', ended = false) => ({
  round_type: wildcard ? 'WILDCARD' : 'ROUND1', status, ended, current_problem: null, problems: [], highest_bid: 0,
  applications: { open: status === 'APPLICATIONS_OPEN', applied: 0, declined: 0, pending: 1, eligible: 1 },
  slots: { count: null, confirmed: false, maximum: 0 }, bidding: { open: false, ranking: [] },
  selection: { qualifications: [], available_problems: [], pool: [] }, final_choice: {}, settings: {},
  remaining_problems: { problems: [], eligible_teams: [], suggested_deduction: 0 },
  event: { event_state: wildcard ? 'WILDCARD_APPLICATION' : 'ROUND1_RESULT', timing: {} },
})
let host: HTMLDivElement
let root: ReturnType<typeof createRoot>
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); vi.useFakeTimers()
  mocks.get.mockReset(); mocks.end.mockReset(); mocks.open.mockReset(); mocks.state.mockReset()
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(() => { act(() => root.unmount()); host.remove(); vi.useRealTimers() })
const renderR1 = (event?: any, state?: any) => root.render(<RoundControlPage round="round-1" config={null} remaining={0} onConfig={vi.fn()} realtimeEvent={event} state={state} />)
const renderWC = (event?: any, state?: any) => root.render(<WildcardControlPage config={null} remaining={0} socketConnected onConfig={vi.fn()} realtimeEvent={event} state={state} />)
const click = async (text: string, scope: ParentNode = host) => {
  const button = [...scope.querySelectorAll('button')].find(button => button.textContent === text)!
  expect(button).toBeTruthy(); await act(async () => button.click())
}
const endR1 = async () => { await click('END ROUND 1'); await click('END ROUND 1', host.querySelector('[role="dialog"]')!) }

it('keeps the successful R1 end response authoritative over an old visibility GET', async () => {
  let resolveOld!: (value: any) => void, resolveFresh!: (value: any) => void
  mocks.get.mockResolvedValueOnce(snapshot()).mockImplementationOnce(() => new Promise(done => { resolveOld = done }))
    .mockImplementationOnce(() => new Promise(done => { resolveFresh = done }))
  mocks.end.mockResolvedValue(snapshot(false, 'CLOSED', true))
  await act(async () => renderR1())
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  await endR1()
  expect(host.textContent).toContain('Round 1 ended')
  await act(async () => resolveOld(snapshot()))
  expect(host.textContent).toContain('Round 1 ended')
  expect(mocks.get).toHaveBeenCalledTimes(3)
  await act(async () => resolveFresh(snapshot(false, 'CLOSED', true)))
  expect(host.textContent).toContain('Round 1 ended')
})

it.each(['round_updated', 'wildcard_updated', 'event_state_changed'])('clears previous Wildcard state on %s reset and protects the second opening', async type => {
  let resolveOld!: (value: any) => void, resolveStart!: (value: any) => void
  mocks.get.mockResolvedValueOnce(snapshot(true, 'COMPLETE', true))
    .mockImplementationOnce(() => new Promise(done => { resolveOld = done }))
    .mockResolvedValueOnce(snapshot(true))
    .mockImplementationOnce(() => new Promise(done => { resolveStart = done }))
    .mockResolvedValue(snapshot(true, 'APPLICATIONS_OPEN'))
  mocks.open.mockResolvedValue(snapshot(true, 'APPLICATIONS_OPEN'))
  await act(async () => renderWC())
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  const reset = { type, payload: { action: 'event_reset', event_state: 'WAITING' } }
  await act(async () => renderWC(reset, { event_state: 'WAITING', rounds: { ROUND1: { ended: false }, WILDCARD: { status: 'NOT_STARTED', ended: false, slot_count: null } } }))
  expect(host.textContent).not.toContain('Wildcard ended')
  await act(async () => resolveOld(snapshot(true, 'COMPLETE', true)))
  expect(host.textContent).toContain('Open applications')
  // Existing visibility refresh starts before the second-run action response.
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  await click('Open applications')
  expect(host.textContent).toContain('Applications are open')
  await act(async () => resolveStart(snapshot(true)))
  expect(host.textContent).toContain('Applications are open')
  expect(mocks.open).toHaveBeenCalledTimes(1)
})

it('resets R1 end state, ends the second run, and retains it on reconnect', async () => {
  mocks.get.mockResolvedValue(snapshot(false, 'CLOSED', true)); mocks.end.mockResolvedValue(snapshot(false, 'CLOSED', true))
  await act(async () => renderR1())
  expect(host.textContent).toContain('Round 1 ended')
  mocks.get.mockResolvedValue(snapshot(false, 'IDLE'))
  const reset = { type: 'round_updated', payload: { action: 'event_reset' } }
  await act(async () => renderR1(reset))
  expect(host.textContent).not.toContain('Round 1 ended')
  await endR1()
  expect(host.textContent).toContain('Round 1 ended')
  mocks.get.mockResolvedValue(snapshot(false, 'CLOSED', true))
  await act(async () => renderR1({ type: 'reconnected' }))
  expect(host.textContent).toContain('Round 1 ended')
})

it('forwards shell reset events and rejects the old global HTTP snapshot', async () => {
  const oldState = { event_state: 'ROUND1_RESULT', timing: {}, rounds: { ROUND1: { status: 'CLOSED', ended: true }, WILDCARD: { status: 'NOT_STARTED', ended: false } } }
  const resetState = { event_state: 'WAITING', timing: {}, rounds: { ROUND1: { status: 'IDLE', ended: false }, WILDCARD: { status: 'NOT_STARTED', ended: false } } }
  let resolveOld!: (value: any) => void
  mocks.state.mockResolvedValueOnce(oldState).mockImplementationOnce(() => new Promise(done => { resolveOld = done })).mockResolvedValue(resetState)
  mocks.get.mockResolvedValue(snapshot(false, 'CLOSED', true))
  await act(async () => root.render(<AdminApplication onLogout={vi.fn()} />))
  await act(async () => vi.advanceTimersByTimeAsync(0))
  await act(async () => (host.querySelector('button[aria-label="Round 1"]') as HTMLButtonElement).click())
  expect(host.textContent).toContain('Round 1 ended')
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  mocks.get.mockResolvedValue(snapshot(false, 'IDLE'))
  await act(async () => {
    mocks.socket.onMessage({ type: 'event_state_changed', payload: resetState, version: 1 })
    mocks.socket.onMessage({ type: 'round_updated', payload: { action: 'event_reset' }, version: 2 })
    mocks.socket.onMessage({ type: 'wildcard_updated', payload: { action: 'event_reset' }, version: 3 })
  })
  await act(async () => resolveOld(oldState))
  expect(host.textContent).not.toContain('Round 1 ended')
  expect(host.querySelector('.event-date')?.textContent).toContain('Waiting')
})

it('serializes repeated Wildcard recovery reads and keeps one existing poll timer', async () => {
  let resolveOld!: (value: any) => void
  mocks.get.mockResolvedValueOnce(snapshot(true)).mockImplementationOnce(() => new Promise(done => { resolveOld = done }))
    .mockResolvedValue(snapshot(true))
  await act(async () => renderWC())
  await act(async () => {
    document.dispatchEvent(new Event('visibilitychange'))
    document.dispatchEvent(new Event('visibilitychange'))
  })
  expect(mocks.get).toHaveBeenCalledTimes(2)
  await act(async () => resolveOld(snapshot(true)))
  expect(mocks.get).toHaveBeenCalledTimes(3)
  await act(async () => vi.advanceTimersByTimeAsync(45000))
  expect(mocks.get).toHaveBeenCalledTimes(4)
})
