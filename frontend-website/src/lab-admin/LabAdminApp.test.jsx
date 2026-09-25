import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { LabAdminBoard } from './LabAdminApp'
import { ordinal } from '../labs/LabAllocationPanel'
import { getLabAllocation, moveLabAssignment } from './services/api'
import { connectReconnectingSocket } from '../services/realtime/connectReconnectingSocket'

vi.mock('./services/api', () => ({
  getLabAllocation: vi.fn(), moveLabAssignment: vi.fn(), getLabAdminToken: vi.fn(() => 'token'),
  clearLabAdminToken: vi.fn(), getLabAdminSession: vi.fn(), hasLabAdminToken: vi.fn(),
  labAdminLogin: vi.fn(), labAdminLogout: vi.fn(),
}))
vi.mock('../services/realtime/connectReconnectingSocket', () => ({ connectReconnectingSocket: vi.fn() }))

const detailTeam = (id, name, place, overrides = {}) => ({
  id,
  team_code: `T-00${id}`,
  team_name: name,
  logged_in: ['Alpha', 'Gamma'].includes(name),
  effective_problem: { id: id + 10, number: `PS-0${id}`, title: `${name} Final Problem` },
  final_problem: { id: id + 10, problem_number: `PS-0${id}`, problem_title: `${name} Final Problem` },
  original_problem: { id: id + 10, number: `PS-0${id}`, title: `${name} Round 1` },
  round1: { id: id + 10, problem_number: `PS-0${id}`, problem_title: `${name} Round 1`, winning_bid: 500 - id * 20, assignment_type: 'BID_WINNER', place },
  wildcard: false,
  wildcard_history: { selected: false, winning_bid: null, place: null },
  changed_from: null,
  ...overrides,
})
const alpha = detailTeam(1, 'Alpha', 1, {
  effective_problem: { id: 22, number: 'WC-02', title: 'AI Resource Optimization' },
  final_problem: { id: 22, problem_number: 'WC-02', problem_title: 'AI Resource Optimization' },
  original_problem: { id: 11, number: 'PS-04', title: 'Smart Campus Navigation' },
  round1: { id: 11, problem_number: 'PS-04', problem_title: 'Smart Campus Navigation', winning_bid: 420, assignment_type: 'BID_WINNER', place: 1 },
  wildcard: true,
  wildcard_history: { selected: true, id: 22, problem_number: 'WC-02', problem_title: 'AI Resource Optimization', winning_bid: 300, place: 5 },
})
const beta = detailTeam(2, 'Beta', 2)
const gamma = detailTeam(3, 'Gamma', 3, { wildcard_history: { selected: true, id: 23, problem_number: 'WC-03', problem_title: 'Circular City', winning_bid: 270, place: 1 } })
const delta = detailTeam(4, 'Delta', 4, { wildcard_history: { selected: true, id: 24, problem_number: 'WC-04', problem_title: 'Water Network', winning_bid: 250, place: 2 } })
const epsilon = detailTeam(5, 'Epsilon', 5, { wildcard_history: { selected: true, id: 25, problem_number: 'WC-05', problem_title: 'Transit Flow', winning_bid: 230, place: 3 } })
const zeta = detailTeam(6, 'Zeta', null, {
  round1: { id: 16, problem_number: 'PS-06', problem_title: 'Manual Challenge', winning_bid: null, assignment_type: 'MANUAL_ASSIGNMENT', place: null },
  wildcard_history: { selected: true, id: 26, problem_number: 'WC-06', problem_title: 'Health Access', winning_bid: 210, place: 4 },
})
const teams = [alpha, beta, gamma, delta, epsilon, zeta]
const assigned = (team, labId) => ({ ...team, assignment_id: team.id, version: 1, current_lab_id: labId })
const baseBoard = {
  can_move: false,
  message: 'Waiting for Wildcard.',
  labs: [
    { id: 1, name: 'Software Lab', capacity: 4, occupancy: 2, teams: [assigned(alpha, 1), assigned(gamma, 1)] },
    { id: 2, name: 'Network Lab', capacity: 4, occupancy: 2, teams: [assigned(beta, 2), assigned(delta, 2)] },
    { id: 3, name: 'Database Lab', capacity: 4, occupancy: 2, teams: [assigned(epsilon, 3), assigned(zeta, 3)] },
  ],
  teams,
  unassigned_team_ids: [],
  eligible_team_count: 6,
  assigned_count: 6,
  unassigned_count: 0,
  team_count: 6,
  logged_in_team_ids: [1, 3],
  participant_logged_in_count: 2,
}
const ready = { ...baseBoard, can_move: true, message: 'Final lab allocation is available.' }
const withProblemAssignments = assignedIds => {
  const assignedSet = new Set(assignedIds)
  const update = team => assignedSet.has(team.id) ? team : { ...team, effective_problem: null, final_problem: null }
  return { ...baseBoard, teams: baseBoard.teams.map(update), labs: baseBoard.labs.map(lab => ({ ...lab, teams: lab.teams.map(update) })) }
}

let root, host, socket
const nav = label => Array.from(host.querySelectorAll('.sidebar-nav button')).find(button => button.textContent === label)
const rowFor = name => Array.from(host.querySelectorAll('.team-allotment-row')).find(row => row.querySelector('strong')?.textContent === name)
const summaryValue = label => Array.from(host.querySelectorAll('.lab-allocation-summary > div')).find(card => card.querySelector('dt')?.textContent === label)?.querySelector('dd')?.textContent
const openDetails = name => act(() => rowFor(name).querySelector('button').click())
const setSelect = (select, value) => { Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, value); select.dispatchEvent(new Event('change', { bubbles: true })) }

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.useFakeTimers(); vi.clearAllMocks()
  host = document.createElement('div'); root = createRoot(host)
  vi.mocked(getLabAllocation).mockResolvedValueOnce(baseBoard).mockResolvedValue(ready)
  vi.mocked(moveLabAssignment).mockImplementation(async (id, payload) => ({ team_id: id, assignment_id: id, version: 2, lab: { id: payload.lab_id, name: payload.lab_id === 2 ? 'Network Lab' : 'Software Lab' } }))
  vi.mocked(connectReconnectingSocket).mockImplementation(options => { socket = options; return () => {} })
})
afterEach(() => { act(() => root.unmount()); vi.useRealTimers() })

it('uses Team Details and Labs navigation and renders a lightweight presence-aligned team list', async () => {
  await act(async () => root.render(<LabAdminBoard session={{ name: 'Lab Admin' }} onLogout={vi.fn()} />))
  expect(Array.from(host.querySelectorAll('.sidebar-nav button'), button => button.textContent)).toEqual(['Team Details', 'Labs'])
  expect(host.querySelector('.topbar h1').textContent).toBe('Team Details')
  expect(host.querySelector('.topbar p').textContent).toBe('Team presence, assignment history and current lab allocation')
  expect(host.querySelector('.lab-workspace__header h2').textContent).toBe('Team Details')
  expect(host.textContent).not.toContain('Problem Results')
  expect(host.querySelectorAll('.team-allotment-row')).toHaveLength(6)
  expect(Array.from(host.querySelectorAll('.team-allotment-list__head span'), cell => cell.textContent)).toEqual(['Team', 'Logged In', 'Assigned Lab', 'Action'])
  expect(host.textContent).toContain('Logged In Teams')
  expect(summaryValue('Logged In Teams')).toBe('2 / 6')
  expect(summaryValue('Problem Assigned')).toBe('6 / 6')
  expect(rowFor('Alpha').textContent).toContain('YES')
  expect(rowFor('Beta').textContent).toContain('NO')
  expect(rowFor('Alpha').textContent).toContain('Software Lab')
  expect(rowFor('Alpha').textContent).not.toContain('Smart Campus Navigation')
  expect(getLabAllocation).toHaveBeenCalledTimes(1)
  expect(connectReconnectingSocket).toHaveBeenCalledTimes(1)
})

it.each([
  ['no teams', [], '0 / 6'],
  ['only a Wildcard team and a team retaining Round 1', [1, 2], '2 / 6'],
])('counts canonical final problems for %s', async (_case, assignedIds, expected) => {
  vi.mocked(getLabAllocation).mockReset().mockResolvedValue(withProblemAssignments(assignedIds))
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))

  expect(summaryValue('Problem Assigned')).toBe(expected)
  const board = withProblemAssignments(assignedIds)
  expect(board.teams.find(team => team.id === 1).wildcard_history.selected).toBe(true)
  expect(board.teams.find(team => team.id === 2).wildcard_history.selected).toBe(false)
  if (assignedIds.length) {
    expect(board.teams.find(team => team.id === 1).final_problem).not.toBeNull()
    expect(board.teams.find(team => team.id === 2).final_problem).not.toBeNull()
  }
  expect(board.teams.find(team => team.id === 3).round1).not.toBeNull()
  expect(board.teams.find(team => team.id === 3).final_problem).toBeNull()
  expect(getLabAllocation).toHaveBeenCalledTimes(1)
  expect(connectReconnectingSocket).toHaveBeenCalledTimes(1)
})

it('updates row presence and the logged-in summary locally from the authoritative event', async () => {
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  act(() => socket.onMessage({ type: 'participant_presence_changed', payload: { logged_in_team_ids: [2, 4, 6], participant_logged_in_count: 3 } }))
  expect(host.textContent).toContain('3 / 6')
  expect(rowFor('Alpha').textContent).toContain('NO')
  expect(rowFor('Beta').textContent).toContain('YES')
  expect(rowFor('Zeta').textContent).toContain('YES')
  expect(getLabAllocation).toHaveBeenCalledTimes(1)
})

it('shows complete assignment history, arbitrary ordinals, final problem and lab only in View Details', async () => {
  expect([1, 2, 3, 4, 5, 11, 12, 13, 21, 22, 23].map(ordinal)).toEqual(['1st', '2nd', '3rd', '4th', '5th', '11th', '12th', '13th', '21st', '22nd', '23rd'])
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))

  await openDetails('Alpha')
  let dialog = host.querySelector('[role="dialog"]')
  for (const value of ['Alpha', 'Final / Current Problem', 'WC-02 — AI Resource Optimization', 'Round 1', 'PS-04', 'Smart Campus Navigation', '420 coins', 'Round 1 Place', '1st', 'Wildcard', '300 coins', 'Wildcard Place', '5th', 'Lab Allocation', 'Software Lab']) expect(dialog.textContent).toContain(value)
  for (const forbidden of ['FinalResult', 'Top 3', 'Pending', 'Not Placed', 'overall']) expect(dialog.textContent).not.toContain(forbidden)
  act(() => dialog.querySelector('[aria-label="Close details"]').click())

  for (const [name, place] of [['Beta', '2nd'], ['Gamma', '3rd'], ['Delta', '4th'], ['Epsilon', '5th']]) {
    await openDetails(name)
    dialog = host.querySelector('[role="dialog"]')
    expect(dialog.textContent).toContain(place)
    act(() => dialog.querySelector('[aria-label="Close details"]').click())
  }

  await openDetails('Zeta')
  dialog = host.querySelector('[role="dialog"]')
  expect(dialog.textContent).toContain('Manual Assignment')
  expect(dialog.textContent).toContain('4th')
  act(() => dialog.querySelector('[aria-label="Close details"]').click())

  await openDetails('Beta')
  expect(host.querySelector('[role="dialog"]').textContent).toContain('Not selected')
})

it('closes team details by button, Escape, backdrop, or navigation without leaking another socket', async () => {
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  await openDetails('Alpha')
  act(() => Array.from(host.querySelectorAll('[role="dialog"] button')).find(button => button.textContent === 'Close').click())
  expect(host.querySelector('[role="dialog"]')).toBeNull()

  await openDetails('Alpha')
  act(() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
  expect(host.querySelector('[role="dialog"]')).toBeNull()

  await openDetails('Alpha')
  act(() => host.querySelector('.team-details-modal-backdrop').dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  expect(host.querySelector('[role="dialog"]')).toBeNull()

  await openDetails('Alpha')
  act(() => nav('Labs').click())
  expect(host.querySelector('[role="dialog"]')).toBeNull()
  act(() => nav('Team Details').click())
  expect(connectReconnectingSocket).toHaveBeenCalledTimes(1)
})

it('preserves existing lab moves and applies lab assignment events locally', async () => {
  vi.mocked(getLabAllocation).mockReset().mockResolvedValue(ready)
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  act(() => nav('Labs').click())

  act(() => host.querySelector('button[aria-label="Move Alpha"]').click())
  const picker = host.querySelector('.lab-move-picker')
  act(() => setSelect(picker.querySelector('select'), '2'))
  await act(async () => picker.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  expect(moveLabAssignment).toHaveBeenCalledWith(1, { lab_id: 2, expected_version: 1 })
  expect(host.querySelector('article[aria-label="Network Lab"]').textContent).toContain('Alpha')

  act(() => nav('Team Details').click())
  act(() => socket.onMessage({ type: 'lab_assignment_changed', payload: { team_id: 1, assignment_id: 1, version: 3, lab: { id: 1, name: 'Software Lab' } } }))
  expect(rowFor('Alpha').textContent).toContain('Software Lab')
  expect(getLabAllocation).toHaveBeenCalledTimes(1)
})

it('refreshes after each Round 1 assignment, coalesces duplicates, and ignores non-assignment events', async () => {
  const noneAssigned = withProblemAssignments([])
  const partlyAssigned = withProblemAssignments([1, 2])
  vi.mocked(getLabAllocation).mockReset()
    .mockResolvedValueOnce(noneAssigned)
    .mockResolvedValueOnce(partlyAssigned)
    .mockResolvedValueOnce(baseBoard)
    .mockResolvedValue(baseBoard)
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  expect(getLabAllocation).toHaveBeenCalledTimes(1)
  expect(summaryValue('Problem Assigned')).toBe('0 / 6')
  act(() => {
    for (const type of ['bid_updated', 'wildcard_bid_updated', 'timer_sync', 'session_heartbeat', 'results_published', 'config_updated']) socket.onMessage({ type, payload: {} })
    socket.onMessage({ type: 'wildcard_updated', payload: { action: 'problem_selected' } })
    socket.onMessage({ type: 'round_updated', payload: { action: 'problem_no_bids' } })
    socket.onMessage({ type: 'external_problems_imported', payload: { created: 1 } })
    vi.advanceTimersByTime(200)
  })
  expect(getLabAllocation).toHaveBeenCalledTimes(1)

  act(() => socket.onMessage({ type: 'round_updated', payload: { action: 'winners_assigned' } }))
  await act(async () => vi.advanceTimersByTimeAsync(150))
  expect(getLabAllocation).toHaveBeenCalledTimes(2)
  expect(summaryValue('Problem Assigned')).toBe('2 / 6')

  act(() => socket.onMessage({ type: 'round_updated', payload: { action: 'winners_assigned' } }))
  await act(async () => vi.advanceTimersByTimeAsync(150))
  expect(getLabAllocation).toHaveBeenCalledTimes(3)
  expect(summaryValue('Problem Assigned')).toBe('6 / 6')

  act(() => {
    socket.onMessage({ type: 'round_updated', payload: { action: 'winners_assigned' } })
    socket.onMessage({ type: 'round1_assignment_changed', payload: {} })
  })
  await act(async () => vi.advanceTimersByTimeAsync(150))
  expect(getLabAllocation).toHaveBeenCalledTimes(4)

  act(() => socket.onMessage({ type: 'round1_assignment_changed', payload: { assignment_type: 'MANUAL_ASSIGNMENT' } }))
  await act(async () => vi.advanceTimersByTimeAsync(150))
  expect(getLabAllocation).toHaveBeenCalledTimes(5)

  act(() => socket.onMessage({ type: 'round_updated', payload: { action: 'problem_manually_assigned' } }))
  await act(async () => vi.advanceTimersByTimeAsync(150))
  expect(getLabAllocation).toHaveBeenCalledTimes(6)

  await act(async () => host.querySelector('.lab-workspace__actions .secondary-button').click())
  expect(getLabAllocation).toHaveBeenCalledTimes(7)
  expect(connectReconnectingSocket).toHaveBeenCalledTimes(1)
})

it.each([
  ['wildcard_ended', { type: 'wildcard_ended', payload: {} }],
  ['event_state_changed', { type: 'event_state_changed', payload: { rounds: { WILDCARD: { ended: true } } } }],
])('%s triggers one Wildcard completion refresh', async (_label, message) => {
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  act(() => socket.onMessage(message))
  await act(async () => vi.advanceTimersByTimeAsync(150))
  expect(getLabAllocation).toHaveBeenCalledTimes(2)
})

it('ignores individual Wildcard steps and coalesces duplicate completion signals', async () => {
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  act(() => {
    socket.onMessage({ type: 'wildcard_bid_updated', payload: {} })
    for (const action of ['problem_selected', 'selection_timeout', 'admin_end_turn', 'final_problem_confirmed', 'final_choice_completed', 'final_choice_ended', 'final_choice_timeout']) {
      socket.onMessage({ type: 'wildcard_updated', payload: { action } })
    }
    vi.advanceTimersByTime(200)
  })
  expect(getLabAllocation).toHaveBeenCalledTimes(1)

  act(() => {
    socket.onMessage({ type: 'wildcard_ended', payload: {} })
    socket.onMessage({ type: 'event_state_changed', payload: { rounds: { WILDCARD: { ended: true } } } })
  })
  await act(async () => vi.advanceTimersByTimeAsync(150))
  expect(getLabAllocation).toHaveBeenCalledTimes(2)
  expect(connectReconnectingSocket).toHaveBeenCalledTimes(1)
})

it('rejects a stale in-flight board and performs exactly one queued assignment refresh', async () => {
  let resolveStale
  vi.mocked(getLabAllocation).mockReset()
    .mockImplementationOnce(() => new Promise(resolve => { resolveStale = resolve }))
    .mockResolvedValue(ready)
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  act(() => socket.onMessage({ type: 'round1_assignment_changed', payload: {} }))
  await act(async () => vi.advanceTimersByTimeAsync(150))
  await act(async () => resolveStale({ ...baseBoard, teams: [{ ...alpha, team_name: 'STALE' }], team_count: 1 }))
  expect(getLabAllocation).toHaveBeenCalledTimes(2)
  expect(host.textContent).not.toContain('STALE')
  expect(host.textContent).toContain('Alpha')
})
