import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { LabAdminBoard } from './lab-admin/LabAdminApp'
import { applyLabChange } from './labs/labBoard'
import { applyBidDelta, applyDisplayBidDelta, parseBidDelta } from './participant/services/bidRealtime'

const mocks = vi.hoisted(() => ({ load: vi.fn(), socket: vi.fn(), options: null as any }))
vi.mock('./services/realtime/connectReconnectingSocket', () => ({ connectReconnectingSocket: mocks.socket }))
vi.mock('./lab-admin/services/api', () => ({
  getLabAllocation: mocks.load, getLabAdminToken: () => 'token',
  hasLabAdminToken: () => false, clearLabAdminToken: vi.fn(), getLabAdminSession: vi.fn(),
  labAdminLogin: vi.fn(), labAdminLogout: vi.fn(), moveLabAssignment: vi.fn(),
}))

function board(title = 'Original PS', count = 1) {
  const teams = Array.from({ length: count }, (_, index) => ({
    id: index + 1, team_code: `T-${index + 1}`, team_name: `Team ${index + 1}`,
    final_problem: { id: index + 100, problem_number: `WC-${index + 1}`, problem_title: title },
    effective_problem: { id: index + 100, number: `WC-${index + 1}`, title },
    wildcard_history: { selected: true, problem_number: `WC-${index + 1}`, problem_title: title },
    assignment_id: index + 1, version: 1, current_lab_id: 1, original_lab_id: 1, assignment_source: 'AUTO',
  }))
  return { teams, labs: [{ id: 1, name: 'Main Lab', capacity: 50, occupancy: count, teams }],
    unassigned_team_ids: [], unassigned_teams: [], assigned_count: count, unassigned_count: 0,
    eligible_team_count: count, team_count: count, can_move: true, message: 'Allocated' }
}

let host: HTMLDivElement
let root: ReturnType<typeof createRoot>
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.useFakeTimers()
  mocks.load.mockReset(); mocks.socket.mockReset()
  mocks.socket.mockImplementation(options => { mocks.options = options; return vi.fn() })
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(() => { act(() => root.unmount()); host.remove(); vi.useRealTimers() })
const emit = async (type: string, payload = {}) => {
  await act(async () => mocks.options.onMessage({ type, payload }))
  await act(async () => vi.advanceTimersByTimeAsync(150))
}

it('reloads authoritative PS and team details even when a single event has only IDs', async () => {
  mocks.load.mockResolvedValueOnce(board()).mockResolvedValue(board('Latest PS'))
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  await act(async () => (host.querySelector('.team-allotment-row button') as HTMLButtonElement).click())
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain('Original PS')
  await emit('lab_assignment_changed', { team_id: 1, effective_ps_id: 101 })
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain('Latest PS')
  expect(document.querySelector('[role="dialog"]')?.textContent).not.toContain('Original PS')
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain('Main Lab')
  expect(mocks.load).toHaveBeenCalledTimes(2)
  expect(mocks.socket).toHaveBeenCalledTimes(1)
})

it('coalesces 35 transformed assignment events and the bulk event into one current board', async () => {
  mocks.load.mockResolvedValueOnce(board('Old PS', 35)).mockResolvedValue(board('Current PS', 35))
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  await act(async () => {
    for (let id = 1; id <= 35; id++) mocks.options.onMessage({ type: 'lab_assignment_changed', payload: { team_id: id } })
    mocks.options.onMessage({ type: 'lab_allocation_updated', payload: { team_count: 35 } })
    await vi.advanceTimersByTimeAsync(150)
  })
  expect(mocks.load).toHaveBeenCalledTimes(2)
  expect(host.querySelectorAll('.team-allotment-row')).toHaveLength(35)
  for (const button of host.querySelectorAll('.team-allotment-row button')) {
    await act(async () => (button as HTMLButtonElement).click())
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain('Current PS')
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain('Main Lab')
  }
})

it('serializes rapid changes and rejects an old in-flight response', async () => {
  let resolveOld!: (value: ReturnType<typeof board>) => void
  mocks.load.mockResolvedValueOnce(board())
    .mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    .mockResolvedValue(board('Newest PS'))
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  await emit('round1_assignment_changed')
  await emit('wildcard_updated', { action: 'final_problem_confirmed' } as any)
  expect(mocks.load).toHaveBeenCalledTimes(2)
  await act(async () => resolveOld(board('Stale PS')))
  expect(mocks.load).toHaveBeenCalledTimes(3)
  await act(async () => (host.querySelector('.team-allotment-row button') as HTMLButtonElement).click())
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain('Newest PS')
  expect(document.querySelector('[role="dialog"]')?.textContent).not.toContain('Stale PS')
})

it('reconciles on socket reconnect without adding a listener or polling', async () => {
  mocks.load.mockResolvedValueOnce(board()).mockResolvedValue(board('Reconnect PS'))
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  await act(async () => mocks.options.onStatus('reconnected'))
  expect(mocks.load).toHaveBeenCalledTimes(2)
  expect(mocks.socket).toHaveBeenCalledTimes(1)
  await act(async () => vi.advanceTimersByTimeAsync(60_000))
  expect(mocks.load).toHaveBeenCalledTimes(2)
})

it('updates shared lab buckets and team details together for manual moves', () => {
  const original = board()
  const changed = applyLabChange(original, { team_id: 1, lab: { id: 1 }, assignment_id: 1, version: 2, assignment_source: 'MANUAL_OVERRIDE' })
  expect(changed.teams[0].version).toBe(2)
  expect(changed.labs[0].teams[0].version).toBe(2)
})

it.each(['ROUND1', 'WILDCARD'])('uses the Wildcard delta ordering for %s display rows', round => {
  const payload = { round, bid_id: 5, team_id: 2, team_name: 'Team 2', amount: 150, increment: 1, timestamp: '2026-09-29T10:00:01Z' }
  const delta = parseBidDelta(payload)!
  const rows = [{ rank: 1, team_id: 1, team_name: 'Team 1', value: 100, timestamp: '2026-09-29T10:00:00Z' }]
  const result = applyDisplayBidDelta(rows, delta)
  expect(result.map(row => row.team_id)).toEqual([2, 1])
  expect(result.map(row => row.rank)).toEqual([1, 2])
  const participant = applyBidDelta(rows.map(row => ({ rank: row.rank, teamId: String(row.team_id), teamName: row.team_name, amount: row.value, placedAt: row.timestamp })), delta)
  expect(result.map(row => String(row.team_id))).toEqual(participant.map(row => row.teamId))
})
