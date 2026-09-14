import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { LabAdminBoard } from './LabAdminApp'
import { getLabAllocation, moveLabAssignment } from './services/api'
import { connectReconnectingSocket } from '../services/realtime/connectReconnectingSocket'

vi.mock('./services/api', () => ({
  getLabAllocation: vi.fn(), moveLabAssignment: vi.fn(), getLabAdminToken: vi.fn(() => 'token'),
  clearLabAdminToken: vi.fn(), getLabAdminSession: vi.fn(), hasLabAdminToken: vi.fn(),
  labAdminLogin: vi.fn(), labAdminLogout: vi.fn(),
}))
vi.mock('../services/realtime/connectReconnectingSocket', () => ({ connectReconnectingSocket: vi.fn() }))

const team = { id: 1, team_code: 'T-001', team_name: 'Alpha', effective_problem: { id: 1, number: 'PS-01', title: 'Final PS' }, assignment_id: 1, version: 1, current_lab_id: 1 }
const waiting = { can_move: false, message: 'Waiting for Wildcard.', labs: [{ id: 1, name: 'Lab A', capacity: 1, occupancy: 0, teams: [] }, { id: 2, name: 'Lab B', capacity: 1, occupancy: 0, teams: [] }], teams: [team], unassigned_team_ids: [1], eligible_team_count: 1, assigned_count: 0, unassigned_count: 1 }
const ready = { ...waiting, can_move: true, message: 'Final lab allocation is available.', labs: [{ ...waiting.labs[0], occupancy: 1, teams: [team] }, waiting.labs[1]], unassigned_team_ids: [], assigned_count: 1, unassigned_count: 0 }

let root, host, socket
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.useFakeTimers(); vi.clearAllMocks()
  host = document.createElement('div'); root = createRoot(host)
  vi.mocked(getLabAllocation).mockResolvedValueOnce(waiting).mockResolvedValue(ready)
  vi.mocked(moveLabAssignment).mockResolvedValue({ team_id: 1, assignment_id: 1, version: 2, lab: { id: 2, name: 'Lab B' } })
  vi.mocked(connectReconnectingSocket).mockImplementation(options => { socket = options; return () => {} })
})
afterEach(() => { act(() => root.unmount()); vi.useRealTimers() })

it('does not poll, refreshes once on Wildcard completion, ignores noise, and moves locally', async () => {
  await act(async () => root.render(<LabAdminBoard session={{ name: 'Lab Admin' }} onLogout={vi.fn()} />))
  expect(getLabAllocation).toHaveBeenCalledTimes(1)
  act(() => vi.advanceTimersByTime(5 * 60_000))
  expect(getLabAllocation).toHaveBeenCalledTimes(1)

  act(() => ['bid_updated', 'timer_sync', 'leaderboard_updated', 'wildcard_updated'].forEach(type => socket.onMessage({ type, version: 2, payload: {} })))
  expect(getLabAllocation).toHaveBeenCalledTimes(1)
  await act(async () => {
    const completion = { type: 'event_state_changed', version: 3, payload: { rounds: { WILDCARD: { ended: true } } } }
    socket.onMessage(completion); socket.onMessage(completion)
  })
  expect(getLabAllocation).toHaveBeenCalledTimes(2)

  const drop = new Event('drop', { bubbles: true, cancelable: true })
  Object.defineProperty(drop, 'dataTransfer', { value: { getData: () => '1' } })
  await act(async () => host.querySelector('article[aria-label="Lab B"]').dispatchEvent(drop))
  expect(moveLabAssignment).toHaveBeenCalledTimes(1)
  expect(getLabAllocation).toHaveBeenCalledTimes(2)
  expect(host.querySelector('article[aria-label="Lab B"]').textContent).toContain('Alpha')

  await act(async () => host.querySelector('.lab-workspace__actions .secondary-button').click())
  expect(getLabAllocation).toHaveBeenCalledTimes(3)
})

it('discards a pre-completion response and makes one authoritative post-Wildcard refresh', async () => {
  let resolveInitial
  vi.mocked(getLabAllocation).mockReset()
    .mockImplementationOnce(() => new Promise(resolve => { resolveInitial = resolve }))
    .mockResolvedValue(ready)
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  expect(getLabAllocation).toHaveBeenCalledTimes(1)
  act(() => socket.onMessage({ type: 'wildcard_ended', version: 4, payload: {} }))
  await act(async () => resolveInitial(waiting))
  expect(getLabAllocation).toHaveBeenCalledTimes(2)
  expect(host.textContent).toContain('Final lab allocation is available.')
})
