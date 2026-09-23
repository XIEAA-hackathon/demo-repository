import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { LabAdminBoard } from './LabAdminApp'
import { getLabAllocation, getProblemResults, moveLabAssignment } from './services/api'
import { connectReconnectingSocket } from '../services/realtime/connectReconnectingSocket'

vi.mock('./services/api', () => ({
  getLabAllocation: vi.fn(), getProblemResults: vi.fn(), moveLabAssignment: vi.fn(), getLabAdminToken: vi.fn(() => 'token'),
  clearLabAdminToken: vi.fn(), getLabAdminSession: vi.fn(), hasLabAdminToken: vi.fn(),
  labAdminLogin: vi.fn(), labAdminLogout: vi.fn(),
}))
vi.mock('../services/realtime/connectReconnectingSocket', () => ({ connectReconnectingSocket: vi.fn() }))

const team = { id: 1, team_code: 'T-001', team_name: 'Alpha', effective_problem: { id: 1, number: 'PS-01', title: 'Final PS' }, assignment_id: 1, version: 1, current_lab_id: 1 }
const waiting = { can_move: false, message: 'Waiting for Wildcard.', labs: [{ id: 1, name: 'Lab A', capacity: 1, occupancy: 0, teams: [] }, { id: 2, name: 'Lab B', capacity: 1, occupancy: 0, teams: [] }], teams: [team], unassigned_team_ids: [1], eligible_team_count: 1, assigned_count: 0, unassigned_count: 1 }
const ready = { ...waiting, can_move: true, message: 'Final lab allocation is available.', labs: [{ ...waiting.labs[0], occupancy: 1, teams: [team] }, waiting.labs[1]], unassigned_team_ids: [], assigned_count: 1, unassigned_count: 0 }
const resultTeam = (id, teamName, finalPlacement, overrides = {}) => ({
  team_id: id,
  team_name: teamName,
  round1: { id: id + 10, problem_number: `PS-0${id}`, problem_title: `${teamName} Round 1`, winning_bid: 420 - id * 10, description: 'ROUND ONE DESCRIPTION MUST STAY HIDDEN' },
  wildcard: { selected: false, winning_bid: null },
  final_problem: { id: id + 10, problem_number: `PS-0${id}`, problem_title: `${teamName} Round 1` },
  final_choice: 'ROUND1',
  final_placement: finalPlacement,
  ...overrides,
})
const alpha = resultTeam(1, 'Alpha', 'FIRST', {
  round1: { id: 11, problem_number: 'PS-04', problem_title: 'Smart Campus Navigation', winning_bid: 420, description: 'ROUND ONE DESCRIPTION MUST STAY HIDDEN' },
  wildcard: { selected: true, id: 22, problem_number: 'WC-02', problem_title: 'AI Resource Optimization', winning_bid: 300, description: 'WILDCARD DESCRIPTION MUST STAY HIDDEN' },
  final_problem: { id: 22, problem_number: 'WC-02', problem_title: 'AI Resource Optimization' },
  final_choice: 'WILDCARD',
})
const beta = resultTeam(2, 'Beta', 'SECOND')
const gamma = resultTeam(3, 'Gamma', 'THIRD', {
  wildcard: { selected: true, id: 23, problem_number: 'WC-01', problem_title: 'Circular City', winning_bid: 260 },
})
const delta = resultTeam(4, 'Delta', 'NOT_PLACED')
const results = {
  result_status: 'PUBLISHED',
  published_at: '2026-09-24T10:00:00Z',
  summary: { total_teams: 4, round1_assigned: 4, wildcard_selected: 2, top3_finalized: 3 },
  teams: [alpha, beta, gamma, delta],
}

let root, host, socket
const nav = label => Array.from(host.querySelectorAll('.sidebar-nav button')).find(button => button.textContent === label)
const openResults = async () => { await act(async () => nav('Problem Results').click()) }
const rowFor = name => Array.from(host.querySelectorAll('.problem-team-row')).find(row => row.querySelector('td strong')?.textContent === name)
const setInput = (input, value) => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })) }
const setSelect = (select, value) => { Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, value); select.dispatchEvent(new Event('change', { bubbles: true })) }

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.useFakeTimers(); vi.clearAllMocks()
  host = document.createElement('div'); root = createRoot(host)
  vi.mocked(getLabAllocation).mockResolvedValueOnce(waiting).mockResolvedValue(ready)
  vi.mocked(getProblemResults).mockResolvedValue(results)
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

it('lists every team once with searchable history, placement badges, and no mutation controls', async () => {
  await act(async () => root.render(<LabAdminBoard session={{ name: 'Lab Admin' }} onLogout={vi.fn()} />))
  expect(nav('Teams')).toBeTruthy()
  expect(nav('Labs')).toBeTruthy()
  await openResults()

  expect(getProblemResults).toHaveBeenCalledTimes(1)
  expect(host.textContent).toContain('Round 1, Wildcard and final result details by team.')
  expect(host.querySelectorAll('.problem-team-row')).toHaveLength(4)
  expect(new Set(Array.from(host.querySelectorAll('.problem-team-row td:first-child strong'), cell => cell.textContent)).size).toBe(4)
  for (const value of ['Alpha', 'Beta', 'Gamma', 'Delta', 'Smart Campus Navigation', 'AI Resource Optimization', '1st Place', '2nd Place', '3rd Place', 'Not Placed']) expect(host.textContent).toContain(value)
  expect(host.textContent).not.toContain('DESCRIPTION MUST STAY HIDDEN')
  for (const mutation of ['Save', 'Delete', 'Edit Team', 'Change Winner', 'Change Placement', 'Change Bid']) expect(Array.from(host.querySelectorAll('button')).some(button => button.textContent.includes(mutation))).toBe(false)

  const search = host.querySelector('input[type="search"]')
  act(() => setInput(search, 'Beta'))
  expect(host.querySelectorAll('.problem-team-row')).toHaveLength(1)
  expect(rowFor('Beta')).toBeTruthy()
  act(() => setInput(search, 'AI Resource'))
  expect(host.querySelectorAll('.problem-team-row')).toHaveLength(1)
  expect(rowFor('Alpha')).toBeTruthy()
  act(() => setInput(search, 'WC-01'))
  expect(host.querySelectorAll('.problem-team-row')).toHaveLength(1)
  expect(rowFor('Gamma')).toBeTruthy()

  act(() => setInput(search, ''))
  const [history, placement] = host.querySelectorAll('.problem-results__filters select')
  act(() => setSelect(history, 'wildcard'))
  expect(host.querySelectorAll('.problem-team-row')).toHaveLength(2)
  act(() => { setSelect(history, 'all'); setSelect(placement, 'NOT_PLACED') })
  expect(host.querySelectorAll('.problem-team-row')).toHaveLength(1)
  expect(rowFor('Delta')).toBeTruthy()
})

it('opens a responsive team history modal and closes it by button, Escape, or backdrop', async () => {
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  await openResults()

  act(() => rowFor('Alpha').querySelector('button').click())
  let dialog = host.querySelector('[role="dialog"]')
  expect(dialog).toBeTruthy()
  for (const value of ['Alpha', 'Round 1', 'PS-04', 'Smart Campus Navigation', 'Winning Bid', '420 coins', 'Wildcard', 'WC-02', 'AI Resource Optimization', 'Wildcard Bid', '300 coins', '1st Place']) expect(dialog.textContent).toContain(value)
  expect(dialog.textContent).not.toContain('DESCRIPTION MUST STAY HIDDEN')
  act(() => Array.from(dialog.querySelectorAll('button')).find(button => button.textContent === 'Close').click())
  expect(host.querySelector('[role="dialog"]')).toBeNull()

  act(() => rowFor('Beta').querySelector('button').click())
  dialog = host.querySelector('[role="dialog"]')
  expect(dialog.textContent).toContain('Not selected')
  expect(dialog.textContent).not.toContain('Wildcard Bid')
  act(() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
  expect(host.querySelector('[role="dialog"]')).toBeNull()

  act(() => rowFor('Gamma').querySelector('button').click())
  const backdrop = host.querySelector('.problem-results-modal-backdrop')
  act(() => backdrop.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  expect(host.querySelector('[role="dialog"]')).toBeNull()
})

it('shows Pending before publication and Not Placed only after publication', async () => {
  vi.mocked(getProblemResults).mockResolvedValue({
    ...results,
    result_status: 'WAITING',
    summary: { ...results.summary, top3_finalized: 0 },
    teams: [{ ...alpha, final_placement: 'PENDING' }],
  })
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  await openResults()
  act(() => rowFor('Alpha').querySelector('button').click())
  expect(host.querySelector('[role="dialog"]').textContent).toContain('Pending')
  expect(rowFor('Alpha').textContent).not.toContain('Not Placed')
})

it('coalesces meaningful result events while bid and timer events do not reload or add a socket', async () => {
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  await openResults()
  expect(getProblemResults).toHaveBeenCalledTimes(1)

  await act(async () => {
    socket.onMessage({ type: 'bid_updated', payload: {} })
    socket.onMessage({ type: 'timer_sync', payload: {} })
  })
  expect(getProblemResults).toHaveBeenCalledTimes(1)
  act(() => {
    socket.onMessage({ type: 'results_published', payload: { result_status: 'PUBLISHED' } })
    socket.onMessage({ type: 'wildcard_updated', payload: { action: 'final_choice_completed' } })
    vi.advanceTimersByTime(149)
  })
  expect(getProblemResults).toHaveBeenCalledTimes(1)
  await act(async () => vi.advanceTimersByTimeAsync(1))
  expect(getProblemResults).toHaveBeenCalledTimes(2)
  await act(async () => Array.from(host.querySelectorAll('button')).find(button => button.textContent === 'Refresh').click())
  expect(getProblemResults).toHaveBeenCalledTimes(3)
  expect(connectReconnectingSocket).toHaveBeenCalledTimes(1)
})

it('discards stale Problem Results data and refetches after realtime overtakes the request', async () => {
  let resolveStale
  vi.mocked(getProblemResults).mockReset()
    .mockImplementationOnce(() => new Promise(resolve => { resolveStale = resolve }))
    .mockResolvedValue(results)
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  act(() => nav('Problem Results').click())
  expect(getProblemResults).toHaveBeenCalledTimes(1)
  act(() => socket.onMessage({ type: 'round1_assignment_changed', payload: {} }))
  await act(async () => vi.advanceTimersByTimeAsync(150))
  await act(async () => resolveStale({ ...results, summary: { ...results.summary, total_teams: 1 }, teams: [{ ...alpha, team_id: 99, team_name: 'STALE' }] }))
  expect(getProblemResults).toHaveBeenCalledTimes(2)
  expect(host.textContent).not.toContain('STALE')
  expect(host.textContent).toContain('Smart Campus Navigation')
})

it('aborts an outstanding results request on navigation without creating another socket', async () => {
  let aborted = false
  vi.mocked(getProblemResults).mockReset()
    .mockImplementationOnce(signal => new Promise((_resolve, reject) => signal.addEventListener('abort', () => { aborted = true; reject(new DOMException('Aborted', 'AbortError')) })))
    .mockResolvedValue(results)
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  act(() => nav('Problem Results').click())
  expect(getProblemResults).toHaveBeenCalledTimes(1)
  await act(async () => nav('Teams').click())
  expect(aborted).toBe(true)
  await openResults()
  expect(getProblemResults).toHaveBeenCalledTimes(2)
  expect(connectReconnectingSocket).toHaveBeenCalledTimes(1)
})
