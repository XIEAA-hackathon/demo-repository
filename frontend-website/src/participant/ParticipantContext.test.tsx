import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ParticipantProvider, useParticipant } from './ParticipantContext'

const mocks = vi.hoisted(() => ({ load: vi.fn(), connect: vi.fn(), message: null as any, status: null as any }))
vi.mock('./services/apiParticipantService', () => ({ participantService: { getParticipantDashboard: mocks.load } }))
vi.mock('./services/eventSocket', () => ({ connectEventSocket: mocks.connect }))
const snapshot = (title = 'Old problem', lab = 'Old lab') => ({ team: { id: '1', name: 'Team' },
  eventState: 'CODING', finalProblem: { id: '1', title }, lab: { id: 1, name: lab }, labAllocationReady: true,
  wildcard: { status: 'selected' }, gameConfig: {}, timing: {}, wallet: { balance: 5000 } })
function Probe() { const { dashboard } = useParticipant(); return <div>{dashboard?.finalProblem?.title} · {dashboard?.lab?.name} · {dashboard?.wallet.balance} coins</div> }
let host: HTMLDivElement
let root: ReturnType<typeof createRoot>
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); vi.useFakeTimers()
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  mocks.load.mockReset(); mocks.connect.mockReset()
  mocks.connect.mockImplementation((message, status) => { mocks.message = message; mocks.status = status; return vi.fn() })
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(() => { act(() => root.unmount()); host.remove(); vi.useRealTimers() })
async function mount() { await act(async () => root.render(<MemoryRouter initialEntries={['/participant/dashboard']}><ParticipantProvider><Probe /></ParticipantProvider></MemoryRouter>)) }
it('applies live lab changes locally and reconciles final problem confirmation once', async () => {
  mocks.load.mockResolvedValueOnce(snapshot()).mockResolvedValue(snapshot('Final wildcard', 'New lab'))
  await mount()
  await act(async () => mocks.message({ type: 'lab_assignment_changed', version: 1, payload: { team_id: 1, lab: { id: 2, name: 'Live lab' } } }))
  expect(host.textContent).toContain('Live lab'); expect(mocks.load).toHaveBeenCalledTimes(1)
  await act(async () => { mocks.message({ type: 'wildcard_updated', version: 2, payload: { action: 'final_problem_confirmed', team_id: 1 } }); await vi.advanceTimersByTimeAsync(1000) })
  expect(host.textContent).toContain('Final wildcard'); expect(mocks.load).toHaveBeenCalledTimes(2)
  expect(mocks.connect).toHaveBeenCalledTimes(1)
})
it('recovers missed problem and lab changes immediately on reconnect and visibility resume', async () => {
  mocks.load.mockResolvedValueOnce(snapshot()).mockResolvedValueOnce(snapshot('Reconnect problem', 'Reconnect lab')).mockResolvedValue(snapshot('Resume problem', 'Resume lab'))
  await mount()
  await act(async () => mocks.status('reconnected'))
  expect(mocks.load).toHaveBeenCalledTimes(2); expect(host.textContent).toContain('Reconnect problem')
  Object.defineProperty(document, 'hidden', { configurable: true, value: true })
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  expect(mocks.load).toHaveBeenCalledTimes(3); expect(host.textContent).toContain('Resume lab')
  expect(mocks.connect).toHaveBeenCalledTimes(1)
})
it('handles bid and timer traffic without fetching the full dashboard', async () => {
  mocks.load.mockResolvedValue(snapshot()); await mount()
  await act(async () => {
    mocks.message({ type: 'wildcard_bid_updated', version: 1, payload: { team_id: 2, team_name: 'Other', amount: 102, increment: 1, round: 'WILDCARD', bid_id: 1, timestamp: new Date().toISOString() } })
    mocks.message({ type: 'timer_sync', version: 2, payload: { event_state: 'CODING', timing: { remaining_seconds: 30 } } })
    await vi.advanceTimersByTimeAsync(1000)
  })
  expect(mocks.load).toHaveBeenCalledTimes(1); expect(mocks.connect).toHaveBeenCalledTimes(1)
})
it('applies committed Extra/Grid coins and reconciles only the affected participant', async () => {
  const assigned = { ...snapshot('Extra problem'), wallet: { balance: 4700 } }
  mocks.load.mockResolvedValueOnce(snapshot()).mockResolvedValue(assigned)
  await mount()
  await act(async () => {
    mocks.message({ type: 'round_updated', version: 1, payload: { action: 'extra_grid_assigned', team_ids: [2], assignments: [{ team_id: 2, coins: 4700 }] } })
    await vi.advanceTimersByTimeAsync(1000)
  })
  expect(mocks.load).toHaveBeenCalledTimes(1)
  await act(async () => mocks.message({ type: 'round_updated', version: 2, payload: { action: 'extra_grid_assigned', team_ids: [1], assignments: [{ team_id: 1, coins: 4700 }] } }))
  expect(host.textContent).toContain('4700 coins')
  await act(async () => vi.advanceTimersByTimeAsync(1000))
  expect(host.textContent).toContain('Extra problem')
  expect(mocks.load).toHaveBeenCalledTimes(2); expect(mocks.connect).toHaveBeenCalledTimes(1)
})
