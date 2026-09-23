import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ParticipantProvider, useParticipant } from './ParticipantContext'
import AllocatedLab from './components/AllocatedLab'
import RoundOnePreviewPage from './pages/RoundOnePreviewPage'
import RoundOneBiddingPage from './pages/RoundOneBiddingPage'
import WildcardSelectionPage from './pages/WildcardSelectionPage'
import { participantService } from './services/apiParticipantService'
import { connectEventSocket, type EventMessage } from './services/eventSocket'
import type { ParticipantDashboard } from './types'

vi.mock('./services/apiParticipantService', () => ({ participantService: { getParticipantDashboard: vi.fn(), getProblems: vi.fn(), getLeaderboard: vi.fn(), getWildcardProblems: vi.fn(), selectWildcardProblem: vi.fn() } }))
vi.mock('./services/eventSocket', () => ({ connectEventSocket: vi.fn() }))
let host: HTMLDivElement, root: Root, receive: (message: EventMessage) => void, socketStatus: (status: string) => void
const now = Date.parse('2026-09-13T10:00:00Z')
const problem = { id: '1', number: 1, title: 'Preview regression', summary: 'Read this challenge', description: 'Read this challenge', startingBid: 100, available: true }
const initial = {
  eventState: 'ROUND1_PREVIEW', currentUserId: '1', team: { id: '1', leaderId: '1', name: 'Preview team' }, wallet: { balance: 5000 },
  gameConfig: { round1PreviewSeconds: 5, round1BidSeconds: 10, round1WinnerCount: 5, startingCoins: 5000 },
  timing: { startedAt: new Date(now).toISOString(), endsAt: new Date(now + 2000).toISOString(), serverTime: new Date(now).toISOString(), receivedAt: now, paused: false, pausedRemainingSeconds: null },
} as ParticipantDashboard
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.useFakeTimers(); vi.setSystemTime(now); vi.clearAllMocks()
  vi.mocked(participantService.getParticipantDashboard).mockResolvedValue(initial)
  vi.mocked(participantService.getProblems).mockResolvedValue([problem])
  vi.mocked(participantService.getLeaderboard).mockResolvedValue([])
  vi.mocked(participantService.getWildcardProblems).mockResolvedValue([{ ...problem, available: true }])
  vi.mocked(connectEventSocket).mockImplementation((callback, onStatus) => {
    receive = callback
    socketStatus = onStatus ?? (() => {})
    return () => {}
  })
  host = document.createElement('div'); root = createRoot(host)
})
afterEach(() => { act(() => root.unmount()); vi.useRealTimers() })
const send = async (version: number, eventState: string, endsAt: string | null, type = 'event_state_changed') => act(async () => receive({
  type, version, server_time: new Date().toISOString(), payload: { event_state: eventState, timing: {
    server_time: new Date().toISOString(), started_at: eventState === 'ROUND1_BIDDING' ? new Date().toISOString() : initial.timing.startedAt,
    ends_at: endsAt, paused: false, remaining_seconds: endsAt ? 10 : null,
  }, rounds: { ROUND1: { status: endsAt ? 'BIDDING' : 'PREVIEW_EXPIRED' } } },
}))

it('recovers the initial dashboard when a socket snapshot overtakes its HTTP response', async () => {
  let resolveFirst!: (value: ParticipantDashboard) => void
  vi.mocked(participantService.getParticipantDashboard)
    .mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
    .mockResolvedValue({ ...initial, labAllocationReady: true, lab: { id: 2, name: 'Lab B' } })
  function Probe() { const { dashboard } = useParticipant(); return dashboard ? <AllocatedLab dashboard={dashboard} /> : <p>Loading</p> }
  await act(async () => root.render(<MemoryRouter><ParticipantProvider><Probe /></ParticipantProvider></MemoryRouter>))
  await send(1, 'CODING', null, 'event_snapshot')
  await act(async () => resolveFirst(initial))
  expect(host.textContent).toContain('Lab B')
  expect(participantService.getParticipantDashboard).toHaveBeenCalledTimes(2)
})

it('reconciles a Wildcard turn after realtime overtakes an in-flight dashboard refresh', async () => {
  const waiting = {
    ...initial,
    eventState: 'WILDCARD_SELECTION',
    isLeader: true,
    wildcard: {
      status: 'qualified', rank: 1, winningBid: 500, selectedProblemId: null, selectionMethod: null,
      currentSelectionRank: 2, currentSelectionTeam: 'Other team', isSelectionTurn: false,
      availableProblemCount: 1, slotCount: 3, selectionStartedAt: null, selectionEndsAt: null,
      selectionDurationSeconds: 30, selectionRemainingSeconds: 30,
    },
  } as ParticipantDashboard
  const stale = { ...waiting, wildcard: { ...waiting.wildcard!, currentSelectionTeam: 'Stale team' } }
  const activeTurn = {
    ...waiting,
    wildcard: {
      ...waiting.wildcard!, currentSelectionRank: 1, currentSelectionTeam: waiting.team.name,
      isSelectionTurn: true, selectionStartedAt: new Date(now).toISOString(),
      selectionEndsAt: new Date(now + 30_000).toISOString(),
    },
  }
  let resolveStale!: (value: ParticipantDashboard) => void
  let resolveTurn!: (value: ParticipantDashboard) => void
  vi.mocked(participantService.getParticipantDashboard)
    .mockReset()
    .mockResolvedValueOnce(waiting)
    .mockImplementationOnce(() => new Promise(resolve => { resolveStale = resolve }))
    .mockImplementationOnce(() => new Promise(resolve => { resolveTurn = resolve }))
  function Probe() {
    const { refresh } = useParticipant()
    return <><button id="refresh" onClick={() => void refresh()}>Refresh</button><WildcardSelectionPage /></>
  }
  await act(async () => root.render(<MemoryRouter><ParticipantProvider><Probe /></ParticipantProvider></MemoryRouter>))
  act(() => host.querySelector<HTMLButtonElement>('#refresh')!.click())
  await act(async () => receive({
    type: 'wildcard_updated', version: 2, server_time: new Date().toISOString(),
    payload: { action: 'bidding_finalized', winners: [{ team_id: 1, rank: 1, winning_bid: 500 }] },
  }))
  await act(async () => vi.advanceTimersByTimeAsync(900))
  expect(participantService.getParticipantDashboard).toHaveBeenCalledTimes(2)

  await act(async () => resolveStale(stale))
  expect(participantService.getParticipantDashboard).toHaveBeenCalledTimes(3)
  expect(host.textContent).not.toContain('Stale team')

  await act(async () => resolveTurn(activeTurn))
  expect(host.textContent).toContain('Choose your final problem')
  const radio = host.querySelector<HTMLInputElement>('input[type="radio"]')!
  expect(radio.disabled).toBe(false)
  act(() => radio.click())
  expect(Array.from(host.querySelectorAll<HTMLButtonElement>('button')).find(button => button.textContent === 'Choose final problem')?.disabled).toBe(false)
})

it('updates only the affected team lab without reloading the dashboard', async () => {
  function Probe() { const { dashboard } = useParticipant(); return dashboard ? <AllocatedLab dashboard={dashboard} /> : null }
  vi.mocked(participantService.getParticipantDashboard).mockResolvedValue({ ...initial, labAllocationReady: true, lab: { id: 1, name: 'Lab A', assignment_id: 1, version: 1 } })
  await act(async () => root.render(<MemoryRouter><ParticipantProvider><Probe /></ParticipantProvider></MemoryRouter>))
  expect(host.textContent).toContain('Lab A')
  const delta = async (teamId: number, labId: number, version: number) => act(async () => receive({ type: 'lab_assignment_changed', version: 0, server_time: new Date().toISOString(), payload: { team_id: teamId, labAllocationReady: true, lab: { id: labId, name: `Lab ${labId}`, assignment_id: 1, version } } }))
  await delta(2, 2, 2); expect(host.textContent).toContain('Lab A')
  await delta(1, 2, 2); expect(host.textContent).toContain('Lab 2')
  await delta(1, 3, 3); expect(host.textContent).toContain('Lab 3')
  await delta(1, 2, 2); expect(host.textContent).toContain('Lab 3')
  expect(participantService.getParticipantDashboard).toHaveBeenCalledTimes(1)
})

it('defers background reconciliation after a connected authoritative snapshot', async () => {
  const random = vi.spyOn(Math, 'random').mockReturnValue(0)
  await act(async () => root.render(<MemoryRouter><ParticipantProvider><div /></ParticipantProvider></MemoryRouter>))
  await act(async () => socketStatus('connected'))
  await send(1, 'ROUND1_PREVIEW', new Date(now + 2_000).toISOString(), 'event_snapshot')

  await act(async () => vi.advanceTimersByTimeAsync(20_000))
  expect(participantService.getParticipantDashboard).toHaveBeenCalledTimes(1)
  await act(async () => vi.advanceTimersByTimeAsync(40_000))
  expect(participantService.getParticipantDashboard).toHaveBeenCalledTimes(2)
  random.mockRestore()
})

it('keeps the faster reconciliation fallback until a socket snapshot arrives', async () => {
  const random = vi.spyOn(Math, 'random').mockReturnValue(0)
  await act(async () => root.render(<MemoryRouter><ParticipantProvider><div /></ParticipantProvider></MemoryRouter>))
  await act(async () => socketStatus('connected'))

  await act(async () => vi.advanceTimersByTimeAsync(12_000))
  expect(participantService.getParticipantDashboard).toHaveBeenCalledTimes(2)
  random.mockRestore()
})

it('makes a completed-allocation inconsistency visible', async () => {
  function Probe() { const { dashboard } = useParticipant(); return dashboard ? <AllocatedLab dashboard={dashboard} /> : null }
  vi.mocked(participantService.getParticipantDashboard).mockResolvedValue({ ...initial, labAllocationReady: true, labAllocationStatus: 'UNAVAILABLE', lab: null })
  await act(async () => root.render(<MemoryRouter><ParticipantProvider><Probe /></ParticipantProvider></MemoryRouter>))
  expect(host.textContent).toContain('Lab assignment unavailable')
})

it('applies expiry, rejects an older timer_sync, and enables bidding on the new server timer without a reload', async () => {
  await act(async () => root.render(<MemoryRouter initialEntries={['/participant/problem']}><ParticipantProvider><Routes>
    <Route path="/participant/problem" element={<RoundOnePreviewPage />} />
    <Route path="/participant/bid" element={<RoundOneBiddingPage />} />
  </Routes></ParticipantProvider></MemoryRouter>))
  expect(host.querySelector('time')?.textContent).toBe('00:02')
  act(() => vi.advanceTimersByTime(2000))
  await send(2, 'ROUND1_PREVIEW', null)
  expect(host.textContent).toContain('Preview complete')
  expect(host.textContent).toContain('Waiting for admin to start bidding')
  expect(host.querySelector('time')?.textContent).toBe('00:00')
  expect(host.querySelector('form')).toBeNull()
  await send(1, 'ROUND1_PREVIEW', new Date(Date.now() + 5000).toISOString(), 'timer_sync')
  expect(host.querySelector('time')?.textContent).toBe('00:00')
  act(() => vi.advanceTimersByTime(5000))
  expect(host.querySelector('time')?.textContent).toBe('00:00')
  await send(3, 'ROUND1_BIDDING', new Date(Date.now() + 10000).toISOString())
  expect(host.querySelector('time')?.textContent).toBe('00:10')
  const input = host.querySelector('input')!
  expect(input).not.toBeNull()
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '5')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  expect(host.querySelector<HTMLButtonElement>('form button')?.disabled).toBe(false)
  expect(participantService.getParticipantDashboard).toHaveBeenCalledTimes(1)
})
