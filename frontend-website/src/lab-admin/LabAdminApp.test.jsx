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
const problem = (id, number, type, assignments = []) => ({ id, number, title: `${number} title`, description: `${number} description`, round: type === 'ROUND1' ? 1 : 2, problem_status: 'allocated', problem_type: type, status: assignments.length ? 'Assigned' : 'Unassigned', assignments })
const assignment = (id, name, placement, overrides = {}) => ({
  team_id: id, team_name: name, leader_name: `${name} Leader`, association: 'ROUND1', assignment_source: 'BID_WINNER', assignment_cost: 420,
  round1_bid_amount: 420, round1_problem: { id: 1, number: 'PS-04', title: 'PS-04 title' }, wildcard_problem: null,
  final_problem: { id: 1, number: 'PS-04', title: 'PS-04 title' }, final_choice: 'ROUND1', final_problem_defaulted: false,
  changed_after_wildcard: false, placement, wildcard_rank: null, wildcard_winning_bid: null, coins_paid: null, selection_method: null, ...overrides,
})
const alpha = assignment(1, 'Alpha', '1st Place', { changed_after_wildcard: true, final_choice: 'WILDCARD', wildcard_problem: { id: 2, number: 'WC-02', title: 'WC-02 title' }, final_problem: { id: 2, number: 'WC-02', title: 'WC-02 title' }, wildcard_rank: 1, wildcard_winning_bid: 300, coins_paid: 300, selection_method: 'manual' })
const results = {
  result_status: 'PUBLISHED', published_at: '2026-09-24T10:00:00Z', summary: { total_problems: 3, round1_problems: 2, wildcard_problems: 1, assigned_teams: 4 },
  problems: [
    problem(1, 'PS-04', 'ROUND1', [alpha, assignment(2, 'Beta', '2nd Place'), assignment(3, 'Gamma', '3rd Place'), assignment(4, 'Delta', 'Not Placed')]),
    problem(3, 'PS-06', 'ROUND1'),
    problem(2, 'WC-02', 'WILDCARD', [{ ...alpha, association: 'WILDCARD', assignment_source: 'manual' }]),
  ],
}

let root, host, socket
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

it('keeps Teams and Labs navigation and renders the read-only Problem Results workflow', async () => {
  await act(async () => root.render(<LabAdminBoard session={{ name: 'Lab Admin' }} onLogout={vi.fn()} />))
  const nav = label => Array.from(host.querySelectorAll('.sidebar-nav button')).find(button => button.textContent === label)
  expect(nav('Teams')).toBeTruthy()
  expect(nav('Labs')).toBeTruthy()
  expect(nav('Problem Results')).toBeTruthy()

  act(() => nav('Teams').click())
  expect(host.querySelector('.topbar h1').textContent).toBe('Teams')
  act(() => nav('Labs').click())
  expect(host.querySelector('.topbar h1').textContent).toBe('Labs')
  await act(async () => nav('Problem Results').click())
  expect(getProblemResults).toHaveBeenCalledTimes(1)
  expect(host.textContent).toContain('PS-04 title')
  expect(host.textContent).toContain('WC-02 title')
  expect(host.textContent).toContain('4 teams assigned')

  const viewDetails = Array.from(host.querySelectorAll('button')).find(button => button.textContent === 'View Details')
  act(() => viewDetails.click())
  for (const value of ['Alpha', 'Beta', 'Gamma', 'Delta', '420 coins', 'WC-02 — WC-02 title', 'Changed After Wildcard', '1st Place', '2nd Place', '3rd Place', 'Not Placed']) expect(host.textContent).toContain(value)
  for (const mutation of ['Save', 'Delete', 'Edit placement']) expect(Array.from(host.querySelectorAll('button')).some(button => button.textContent.includes(mutation))).toBe(false)

  const wildcardTab = Array.from(host.querySelectorAll('[role="tab"]')).find(button => button.textContent === 'Wildcard')
  act(() => wildcardTab.click())
  expect(host.querySelectorAll('.problem-result-card')).toHaveLength(1)
  expect(host.textContent).toContain('WC-02 title')
  act(() => Array.from(host.querySelectorAll('[role="tab"]')).find(button => button.textContent === 'All Problems').click())

  const search = host.querySelector('input[type="search"]')
  const setSearch = value => Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(search, value)
  act(() => { setSearch('Beta'); search.dispatchEvent(new Event('input', { bubbles: true })) })
  expect(host.querySelectorAll('.problem-result-card')).toHaveLength(1)
  const status = host.querySelector('.problem-results__filters select')
  act(() => { setSearch(''); search.dispatchEvent(new Event('input', { bubbles: true })); status.value = 'unassigned'; status.dispatchEvent(new Event('change', { bubbles: true })) })
  expect(host.querySelectorAll('.problem-result-card')).toHaveLength(1)
  expect(host.textContent).toContain('PS-06 title')

  act(() => nav('Teams').click())
  await act(async () => nav('Problem Results').click())
  expect(getProblemResults).toHaveBeenCalledTimes(2)
  expect(connectReconnectingSocket).toHaveBeenCalledTimes(1)
})

it('coalesces meaningful result events, ignores bid/timer noise, and supports manual refresh', async () => {
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  await act(async () => Array.from(host.querySelectorAll('.sidebar-nav button')).find(button => button.textContent === 'Problem Results').click())
  expect(getProblemResults).toHaveBeenCalledTimes(1)

  await act(async () => {
    socket.onMessage({ type: 'bid_updated', payload: {} })
    socket.onMessage({ type: 'timer_sync', payload: {} })
  })
  expect(getProblemResults).toHaveBeenCalledTimes(1)
  act(() => {
    socket.onMessage({ type: 'results_published', payload: { result_status: 'PUBLISHED' } })
    socket.onMessage({ type: 'wildcard_updated', payload: { action: 'final_choice_completed' } })
    socket.onMessage({ type: 'event_state_changed', payload: { rounds: { WILDCARD: { ended: true } } } })
    vi.advanceTimersByTime(149)
  })
  expect(getProblemResults).toHaveBeenCalledTimes(1)
  await act(async () => vi.advanceTimersByTimeAsync(1))
  expect(getProblemResults).toHaveBeenCalledTimes(2)
  await act(async () => Array.from(host.querySelectorAll('button')).find(button => button.textContent === 'Refresh').click())
  expect(getProblemResults).toHaveBeenCalledTimes(3)
})

it('discards stale Problem Results data and refetches after realtime overtakes the request', async () => {
  let resolveStale
  vi.mocked(getProblemResults).mockReset()
    .mockImplementationOnce(() => new Promise(resolve => { resolveStale = resolve }))
    .mockResolvedValue(results)
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  act(() => Array.from(host.querySelectorAll('.sidebar-nav button')).find(button => button.textContent === 'Problem Results').click())
  expect(getProblemResults).toHaveBeenCalledTimes(1)
  act(() => socket.onMessage({ type: 'round1_assignment_changed', payload: {} }))
  await act(async () => vi.advanceTimersByTimeAsync(150))
  await act(async () => resolveStale({ ...results, problems: [problem(99, 'STALE', 'ROUND1')] }))
  expect(getProblemResults).toHaveBeenCalledTimes(2)
  expect(host.textContent).not.toContain('STALE title')
  expect(host.textContent).toContain('PS-04 title')
})

it('shows Pending before results are published', async () => {
  vi.mocked(getProblemResults).mockResolvedValue({
    ...results,
    result_status: 'WAITING',
    problems: [problem(1, 'PS-04', 'ROUND1', [assignment(1, 'Alpha', 'Pending')])],
  })
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  await act(async () => Array.from(host.querySelectorAll('.sidebar-nav button')).find(button => button.textContent === 'Problem Results').click())
  act(() => Array.from(host.querySelectorAll('button')).find(button => button.textContent === 'View Details').click())
  expect(host.textContent).toContain('Pending')
  expect(host.textContent).not.toContain('Not Placed')
})

it('aborts an outstanding results request on navigation without creating another socket', async () => {
  let aborted = false
  vi.mocked(getProblemResults).mockReset()
    .mockImplementationOnce(signal => new Promise((_resolve, reject) => signal.addEventListener('abort', () => { aborted = true; reject(new DOMException('Aborted', 'AbortError')) })))
    .mockResolvedValue(results)
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  const nav = label => Array.from(host.querySelectorAll('.sidebar-nav button')).find(button => button.textContent === label)
  act(() => nav('Problem Results').click())
  expect(getProblemResults).toHaveBeenCalledTimes(1)
  await act(async () => nav('Teams').click())
  expect(aborted).toBe(true)
  await act(async () => nav('Problem Results').click())
  expect(getProblemResults).toHaveBeenCalledTimes(2)
  expect(connectReconnectingSocket).toHaveBeenCalledTimes(1)
})
