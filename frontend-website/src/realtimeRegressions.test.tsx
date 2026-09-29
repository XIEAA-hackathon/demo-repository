import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { LabAdminBoard } from './lab-admin/LabAdminApp'
import { applyLabChange } from './labs/labBoard'
import { applyBidDelta, applyDisplayBidDelta, parseBidDelta } from './participant/services/bidRealtime'

const mocks = vi.hoisted(() => ({ load: vi.fn(), socket: vi.fn(), assign: vi.fn(), move: vi.fn(), options: null as any }))
vi.mock('./services/realtime/connectReconnectingSocket', () => ({ connectReconnectingSocket: mocks.socket }))
vi.mock('./lab-admin/services/api', () => ({
  getLabAllocation: mocks.load, getLabAdminToken: () => 'token',
  hasLabAdminToken: () => false, clearLabAdminToken: vi.fn(), getLabAdminSession: vi.fn(),
  labAdminLogin: vi.fn(), labAdminLogout: vi.fn(), moveLabAssignment: mocks.move, assignConflictTeamLab: mocks.assign,
}))

function board(title = 'Original PS', count = 1) {
  const teams = Array.from({ length: count }, (_, index) => ({
    id: index + 1, team_code: `T-${index + 1}`, team_name: `Team ${index + 1}`, logged_in: false,
    final_problem: { id: index + 100, problem_number: `WC-${index + 1}`, problem_title: title },
    effective_problem: { id: index + 100, number: `WC-${index + 1}`, title },
    wildcard_history: { selected: true, problem_number: `WC-${index + 1}`, problem_title: title },
    assignment_id: index + 1, version: 1, current_lab_id: 1, original_lab_id: 1, assignment_source: 'AUTO',
  }))
  return { teams, labs: [{ id: 1, name: 'Main Lab', capacity: 50, occupancy: count, teams: [...teams] }],
    unassigned_team_ids: [], unassigned_teams: [], assigned_count: count, unassigned_count: 0,
    eligible_team_count: count, team_count: count, can_move: true, message: 'Allocated' }
}

let host: HTMLDivElement
let root: ReturnType<typeof createRoot>
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.useFakeTimers()
  mocks.load.mockReset(); mocks.socket.mockReset(); mocks.assign.mockReset(); mocks.move.mockReset()
  mocks.socket.mockImplementation(options => { mocks.options = options; return vi.fn() })
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(() => { act(() => root.unmount()); host.remove(); vi.useRealTimers() })
const emit = async (type: string, payload = {}) => {
  await act(async () => mocks.options.onMessage({ type, payload }))
  await act(async () => vi.advanceTimersByTimeAsync(150))
}

it('reconciles immediately on visibility resume and keeps awaiting teams distinct', async () => {
  const next = board('Resume PS');
  next.teams.push({ id: 2, team_code: 'T-2', team_name: 'Awaiting Team', final_problem: null, effective_problem: null } as any);
  mocks.load.mockResolvedValueOnce(board()).mockResolvedValue(next);
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />));
  Object.defineProperty(document, 'hidden', { configurable: true, value: true });
  await act(async () => document.dispatchEvent(new Event('visibilitychange')));
  expect(mocks.load).toHaveBeenCalledTimes(1);
  Object.defineProperty(document, 'hidden', { configurable: true, value: false });
  await act(async () => document.dispatchEvent(new Event('visibilitychange')));
  expect(mocks.load).toHaveBeenCalledTimes(2);
  expect(host.textContent).toContain('Awaiting problem');
  expect(mocks.socket).toHaveBeenCalledTimes(1);
});

it('keeps Logged In across socket loss and applies logout through the existing presence event', async () => {
  const loggedIn = board();
  loggedIn.teams[0].logged_in = true;
  mocks.load.mockResolvedValue(loggedIn);
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />));
  await act(async () => mocks.options.onStatus('disconnected'));
  expect(host.querySelector('.team-presence')?.textContent).toBe('YES');
  await emit('participant_presence_changed', { logged_in_team_ids: [], participant_logged_in_count: 0 } as any);
  expect(host.querySelector('.team-presence')?.textContent).toBe('NO');
  expect(mocks.load).toHaveBeenCalledTimes(1);
});

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

it('filters PS allocation independently of labs, including legacy R1 history', async () => {
  const fixture = board()
  fixture.teams[0].team_name = 'Team B'
  fixture.teams.push({ id: 2, team_code: 'T-2', team_name: 'Team A', logged_in: false,
    round1: { id: 20, problem_number: 'R1-2', problem_title: 'R1 history' },
    final_problem: null, effective_problem: null } as any,
    { id: 3, team_code: 'T-3', team_name: 'Team C', logged_in: false, final_problem: null, effective_problem: null } as any)
  mocks.load.mockResolvedValue(fixture)
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  const filter = host.querySelector('.lab-filters select') as HTMLSelectElement
  const select = async (value: string) => { await act(async () => { filter.value = value; filter.dispatchEvent(new Event('change', { bubbles: true })) }) }
  await select('ps_allocated')
  expect([...host.querySelectorAll('.team-identity strong')].map(row => row.textContent)).toEqual(['Team B', 'Team A'])
  expect(host.querySelectorAll('.team-allotment-row')[0].textContent).toContain('PS AllocatedMain Lab')
  expect(host.querySelectorAll('.team-allotment-row')[1].textContent).toContain('Lab pending')
  await act(async () => (host.querySelectorAll('.team-allotment-row button')[1] as HTMLButtonElement).click())
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain('Lab pending')
  await select('ps_not_allocated')
  expect([...host.querySelectorAll('.team-identity strong')].map(row => row.textContent)).toEqual(['Team C'])
  expect(host.querySelector('.team-allotment-row')?.textContent).toContain('Awaiting problem')
})

it('updates R1 PS status immediately through the existing event and retains both histories after Wildcard', async () => {
  const base = { id: 1, team_code: 'T-1', team_name: 'Team Alpha', logged_in: false }
  const initial: any = { ...board(), labs: [], teams: [{ ...base, final_problem: null, problem_assignment_status: 'not_allocated' }] }
  const r1 = { id: 4, problem_number: 'R1-4', problem_title: 'R1 history', winning_bid: 100, place: 1 }
  const assigned: any = { ...initial, teams: [{ ...base, round1: r1, final_problem: r1, problem_assignment_status: 'allocated' }] }
  const wc = { id: 20, problem_number: 'WC-2', problem_title: 'WC history', selected: true, winning_bid: 200, place: 1 }
  const final: any = { ...assigned, teams: [{ ...assigned.teams[0], wildcard_history: wc, final_problem: wc }] }
  mocks.load.mockResolvedValueOnce(initial).mockResolvedValueOnce(assigned).mockResolvedValueOnce(final)
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  expect(host.querySelector('.team-allotment-row')?.textContent).toContain('PS Not Allocated')
  await emit('round_updated', { action: 'winners_assigned' })
  expect(host.querySelector('.team-allotment-row')?.textContent).toContain('PS Allocated')
  expect(host.querySelector('.team-allotment-row')?.textContent).toContain('Lab pending')
  await act(async () => (host.querySelector('.team-allotment-row button') as HTMLButtonElement).click())
  expect(document.querySelector('.team-details-final-problem')?.textContent).toContain('R1-4')
  await emit('wildcard_updated', { action: 'final_problem_confirmed' })
  expect(document.querySelector('.team-details-final-problem')?.textContent).toContain('WC-2')
  expect(document.querySelector('.assignment-history-grid')?.textContent).toContain('R1-4')
  expect(document.querySelector('.assignment-history-grid')?.textContent).toContain('WC-2')
  expect(host.querySelector('.team-allotment-row')?.textContent).toContain('PS Allocated')
  expect(mocks.socket).toHaveBeenCalledTimes(1)
  expect(mocks.load).toHaveBeenCalledTimes(3)
})
it('shows Extra/Grid PS allocation live without inventing R1 history', async () => {
  const empty: any = { ...board(), labs: [], teams: [{ id: 1, team_code: 'T-1', team_name: 'Extra team', final_problem: null, round1: null, problem_assignment_status: 'not_allocated' }] }
  const assigned = { ...empty, teams: [{ ...empty.teams[0], final_problem: { id: 7, problem_number: 'R1-7', problem_title: 'Extra PS' }, problem_assignment_status: 'allocated' }] }
  mocks.load.mockResolvedValueOnce(empty).mockResolvedValue(assigned)
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />))
  await emit('round_updated', { action: 'extra_grid_assigned', team_ids: [1] })
  expect(host.querySelector('.team-allotment-row')?.textContent).toContain('PS Allocated')
  expect(host.querySelector('.team-allotment-row')?.textContent).toContain('Lab pending')
  await act(async () => (host.querySelector('.team-allotment-row button') as HTMLButtonElement).click())
  expect(document.querySelector('.team-details-final-problem')?.textContent).toContain('R1-7')
  expect(document.querySelector('.assignment-history-card')?.textContent).toContain('Not assigned')
  expect(mocks.socket).toHaveBeenCalledTimes(1)
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


function conflictBoard() {
  const data: any = board()
  Object.assign(data.teams[0], { lab_allocation_status: 'assigned', constraint_override: false })
  const conflict = { id: 2, team_code: 'T-2', team_name: 'Conflict Team', final_problem: data.teams[0].final_problem,
    effective_problem: data.teams[0].effective_problem, lab_allocation_status: 'conflict', lab_conflict_reason: 'SAME_PS_CONSTRAINT' }
  const awaiting = { id: 3, team_code: 'T-3', team_name: 'Awaiting Team', final_problem: null, effective_problem: null,
    lab_allocation_status: 'unassigned', lab_unassigned_reason: 'NO_FINAL_PROBLEM' }
  data.teams.push(conflict, awaiting)
  data.labs[0].capacity = 2
  data.labs.push({ id: 2, name: 'Full Lab', capacity: 0, occupancy: 0, teams: [] })
  Object.assign(data, { unassigned_team_ids: [2, 3], unassigned_teams: [conflict], conflict_count: 1, lab_unassigned_count: 1, awaiting_problem_count: 1, team_count: 3 })
  return data
}
const labsPage = async () => {
  const button = [...host.querySelectorAll('button')].find(row => row.textContent === 'Labs')!
  await act(async () => button.click())
}
const allocationFilter = async (value: string) => {
  const select = host.querySelector('.lab-filters select') as HTMLSelectElement
  await act(async () => { select.value = value; select.dispatchEvent(new Event('change', { bubbles: true })) })
}

it('filters Assigned, Unassigned and Conflict using the backend states', async () => {
  mocks.load.mockResolvedValue(conflictBoard())
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />)); await labsPage()
  for (const [filter, name] of [['assigned', 'Team 1'], ['unassigned', 'Awaiting Team'], ['conflict', 'Conflict Team']]) {
    await allocationFilter(filter)
    expect([...host.querySelectorAll('.team-allotment-row .team-identity strong')].map(row => row.textContent)).toEqual([name])
  }
  expect(host.querySelector('.team-allotment-row')?.textContent).toContain('WC-1')
  expect(host.querySelector('.team-allotment-row')?.textContent).not.toContain('PS pending')
})

it('requires Assign Anyway before a same-PS conflict request and updates the counts locally', async () => {
  mocks.load.mockResolvedValue(conflictBoard())
  mocks.assign.mockResolvedValue({ team_id: 2, assignment_id: 2, version: 1, lab: { id: 1, name: 'Main Lab' },
    assignment_source: 'MANUAL_OVERRIDE', constraint_override: true, lab_allocation_status: 'assigned' })
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />)); await labsPage(); await allocationFilter('conflict')
  await act(async () => (host.querySelector('.team-allotment-row button') as HTMLButtonElement).click())
  const picker = host.querySelector('.lab-move-picker select') as HTMLSelectElement
  expect([...picker.options].map(row => row.textContent).join(' ')).not.toContain('Full Lab')
  expect(picker.options[1].textContent).toContain('WC-1 already present')
  await act(async () => { picker.value = '1'; picker.dispatchEvent(new Event('change', { bubbles: true })) })
  await act(async () => (host.querySelector('.lab-move-picker button[type="submit"]') as HTMLButtonElement).click())
  expect(host.querySelector('[role="dialog"]')?.textContent).toContain('Same PS conflict')
  expect(mocks.assign).not.toHaveBeenCalled()
  const confirm = [...host.querySelectorAll('button')].find(row => row.textContent === 'Assign Anyway')!
  await act(async () => confirm.click())
  expect(mocks.assign).toHaveBeenCalledWith(2, { lab_id: 1, allow_constraint_override: true })
  expect(mocks.move).not.toHaveBeenCalled()
  expect(host.querySelectorAll('.team-allotment-row')).toHaveLength(0)
  expect(host.querySelector('.lab-allocation-summary')?.textContent).toContain('Assigned2')
  expect(host.querySelector('.lab-allocation-summary')?.textContent).toContain('Conflict0')
  expect(host.querySelector('.lab-override-badge')?.textContent).toBe('Same PS')
})

it('reconciles conflict resolution through the existing socket without reload or extra listeners', async () => {
  const initial = conflictBoard()
  const next = applyLabChange(initial, { team_id: 2, assignment_id: 2, version: 1, lab: { id: 1, name: 'Main Lab' },
    assignment_source: 'MANUAL_OVERRIDE', constraint_override: true })
  mocks.load.mockResolvedValueOnce(initial).mockResolvedValue(next)
  await act(async () => root.render(<LabAdminBoard onLogout={vi.fn()} />)); await labsPage(); await allocationFilter('conflict')
  expect(host.querySelectorAll('.team-allotment-row')).toHaveLength(1)
  await emit('lab_assignment_changed', { team_id: 2, lab: { id: 1 } } as any)
  expect(host.querySelectorAll('.team-allotment-row')).toHaveLength(0)
  expect(host.querySelector('.lab-allocation-summary')?.textContent).toContain('Assigned2')
  expect(host.querySelector('.lab-allocation-summary')?.textContent).toContain('Conflict0')
  expect(mocks.load).toHaveBeenCalledTimes(2)
  expect(mocks.socket).toHaveBeenCalledTimes(1)
})
