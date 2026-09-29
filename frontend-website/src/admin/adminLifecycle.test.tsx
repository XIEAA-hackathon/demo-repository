import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AdminApplication, RoundControlPage, WildcardControlPage } from './App'
import ExtraGrid from './components/ExtraGrid'
import ChangeProblemPage from './pages/ChangeProblem'

const mocks = vi.hoisted(() => ({ get: vi.fn(), end: vi.fn(), open: vi.fn(), state: vi.fn(), extra: vi.fn(), assign: vi.fn(), corrections: vi.fn(), socket: null as any }))
vi.mock('./services/auctionSocket', () => ({ connectAuctionSocket: (options: any) => { mocks.socket = options; return vi.fn() } }))
vi.mock('./components/LabConfiguration', () => ({ default: () => null }))
vi.mock('./services/api', async importOriginal => ({ ...await importOriginal<any>(),
  getRoundControl: mocks.get, endRoundOne: mocks.end, openWildcardApplications: mocks.open,
  getAdminState: mocks.state, getTeams: async () => [], getProblemStatements: async () => [], getBidHistory: async () => [],
  getAdminConfig: async () => null, getAdminHealth: async () => ({ database: 'healthy' }), getLabAllocation: async () => null,
  getExtraGrid: mocks.extra, autoAssignExtraGrid: mocks.assign,
  getRoundOneAssignments: mocks.corrections,
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
  mocks.get.mockReset(); mocks.end.mockReset(); mocks.open.mockReset(); mocks.state.mockReset(); mocks.assign.mockReset(); mocks.extra.mockReset()
  mocks.corrections.mockReset()
  mocks.extra.mockResolvedValue({ problems: [], teams: [], unassigned_teams: [], remaining_team_count: 0, suggested_auto_deduction: 25, r1_bid_count: 0, r1_bid_sum: 0, can_auto_assign: true })
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

const grid = () => ({ problems: [{ id: 20, problem_number: '1', title: 'Extra', source: 'EXTERNAL', source_label: 'External', capacity: 5, assigned_team_count: 0, capacity_remaining: 5 }],
  teams: [{ team_id: 1, team_name: 'Unassigned Participant', extra_assignment: false }], unassigned_teams: [{ team_id: 1, team_name: 'Unassigned Participant' }],
  remaining_team_count: 1, suggested_auto_deduction: 300, r1_bid_sum: 2100, r1_bid_count: 7, automatic_price_source: 'Average of all Round 1 bids', can_auto_assign: true })
const inputPrice = async (value: string) => {
  const input = host.querySelector('#extra-assignment-deduction') as HTMLInputElement
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })) })
}

it('keeps Remaining operations out of Auction and preserves manual assignment and re-bid in their tab', async () => {
  const data: any = snapshot()
  data.remaining_problems.problems = [{ id: 1, problem_number: 1, title: 'Manual PS', assigned_team_count: 0, assigned_teams: [],
    auction_capacity: 5, assignment_status: 'UNASSIGNED', can_assign: true, can_rebid: true }]
  data.remaining_problems.suggested_deduction = 25
  mocks.get.mockResolvedValue(data); mocks.extra.mockResolvedValue(grid())
  await act(async () => renderR1())
  expect(host.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain('Auction')
  expect(host.querySelector('.round-remaining-problems')).toBeNull()
  expect(host.textContent).not.toContain('AUTO ASSIGN')
  await act(async () => (host.querySelectorAll('[role="tab"]')[1] as HTMLButtonElement).click())
  expect(host.querySelector('.round-console__live')).toBeNull()
  expect(host.textContent).toContain('AUTO ASSIGN')
  expect([...host.querySelectorAll('button')].find(row => row.textContent === 'Re-bid')?.disabled).toBe(false)
  await click('Assign')
  expect(host.querySelector('#manual-assignment-deduction')).toBeTruthy()
  expect((host.querySelector('#manual-assignment-deduction') as HTMLInputElement).value).toBe('25')
})

it('switches tabs only after the end response and lets the organizer return to Auction', async () => {
  let end!: (value: any) => void
  mocks.get.mockResolvedValueOnce(snapshot()).mockResolvedValue(snapshot(false, 'CLOSED', true))
  mocks.end.mockImplementation(() => new Promise(done => { end = done }))
  await act(async () => renderR1()); await endR1()
  expect(host.querySelector('[aria-selected="true"]')?.textContent).toContain('Auction')
  await act(async () => end(snapshot(false, 'CLOSED', true)))
  expect(host.querySelector('[aria-selected="true"]')?.textContent).toContain('Remaining / Unassigned')
  await act(async () => (host.querySelectorAll('[role="tab"]')[0] as HTMLButtonElement).click())
  expect(host.querySelector('.round-console__live')).toBeTruthy()
  expect(host.textContent).not.toContain('AUTO ASSIGN')
})
it('disables frozen R1 actions even if old remaining details still advertise them', async () => {
  const data: any = snapshot(false, 'CLOSED', true)
  data.remaining_problems.problems = [{ id: 1, problem_number: 1, title: 'Remaining PS', assigned_team_count: 0,
    assigned_teams: [], assignment_status: 'UNASSIGNED', can_assign: true, can_rebid: true }]
  mocks.get.mockResolvedValue(data)
  await act(async () => renderR1())
  for (const label of ['Re-bid', 'Assign']) expect([...host.querySelectorAll('button')].find(row => row.textContent === label)?.disabled).toBe(true)
})

it('submits the edited automatic price and displays per-team failures', async () => {
  mocks.extra.mockResolvedValue(grid())
  mocks.assign.mockResolvedValue({ ...grid(), assignments: [], deduction: 350,
    failures: [{ team_id: 1, team_name: 'Remaining Team', reason: 'Insufficient coins', required: 350, available: 100 }] })
  await act(async () => root.render(<ExtraGrid realtimeEvent={null} selectedProblemId={20} />))
  expect((host.querySelector('#extra-assignment-deduction') as HTMLInputElement).value).toBe('300')
  await inputPrice('350'); await click('AUTO ASSIGN')
  expect(mocks.assign).toHaveBeenCalledWith(20, 350)
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('required 350, available 100')
})

it.each(['', '-1', '1.5'])('disables automatic assignment for invalid deduction %s', async price => {
  mocks.extra.mockResolvedValue(grid())
  await act(async () => root.render(<ExtraGrid realtimeEvent={null} selectedProblemId={20} />))
  await inputPrice(price)
  expect([...host.querySelectorAll('button')].find(row => row.textContent === 'AUTO ASSIGN')?.disabled).toBe(true)
  expect(mocks.assign).not.toHaveBeenCalled()
})

it('rejects an old Extra/Grid snapshot after the automatic assignment response', async () => {
  let old!: (value: any) => void
  const assigned = { ...grid(), unassigned_teams: [], remaining_team_count: 0, assignments: [{ team_id: 1 }], deduction: 300, failures: [],
    teams: [{ team_id: 1, team_name: 'Remaining Team', extra_assignment: true, current_problem: { problem_number: 'EXT-1' } }] }
  mocks.extra.mockResolvedValueOnce(grid()).mockImplementationOnce(() => new Promise(done => { old = done })).mockResolvedValue(assigned)
  mocks.assign.mockResolvedValue(assigned)
  await act(async () => root.render(<ExtraGrid realtimeEvent={null} selectedProblemId={20} />))
  await act(async () => root.render(<ExtraGrid realtimeEvent={{ type: 'event_state_changed' }} selectedProblemId={20} />))
  await click('AUTO ASSIGN')
  expect(host.textContent).toContain('1 teams assigned at 300 coins')
  await act(async () => old(grid()))
  expect(host.querySelector('#extra-assignment-remaining')?.textContent).toBe('0')
  expect(mocks.extra).toHaveBeenCalledTimes(3)
})
it('refreshes the all-bid price suggestion through the existing event without overwriting an edited price', async () => {
  mocks.extra.mockResolvedValueOnce(grid()).mockResolvedValue({ ...grid(), suggested_auto_deduction: 400, r1_bid_sum: 3200, r1_bid_count: 8 })
  await act(async () => root.render(<ExtraGrid realtimeEvent={null} />))
  await inputPrice('350')
  await act(async () => root.render(<ExtraGrid realtimeEvent={{ type: 'round_updated', payload: { action: 'winners_assigned' } }} />))
  expect(host.querySelector('.extra-grid-summary')?.textContent).toContain('400 coins')
  expect((host.querySelector('#extra-assignment-deduction') as HTMLInputElement).value).toBe('350')
  expect(mocks.extra).toHaveBeenCalledTimes(2)
})

it('requires a selected problem with free capacity before automatic assignment', async () => {
  mocks.extra.mockResolvedValue(grid())
  await act(async () => root.render(<ExtraGrid realtimeEvent={null} />))
  const auto = () => [...host.querySelectorAll('button')].find(row => row.textContent === 'AUTO ASSIGN')!
  expect(auto().disabled).toBe(true)
  await act(async () => root.render(<ExtraGrid realtimeEvent={null} selectedProblemId={999} />))
  expect(auto().disabled).toBe(true)
  await act(async () => root.render(<ExtraGrid realtimeEvent={null} selectedProblemId={20} />))
  expect(auto().disabled).toBe(false)
  expect((host.querySelector('#extra-assignment-problem') as HTMLSelectElement).value).toBe('20')
  mocks.extra.mockResolvedValue({ ...grid(), problems: [{ ...grid().problems[0], capacity_remaining: 0 }] })
  await act(async () => root.render(<ExtraGrid realtimeEvent={{ type: 'event_state_changed' }} selectedProblemId={20} />))
  expect(auto().disabled).toBe(true)
  expect(mocks.assign).not.toHaveBeenCalled()
})

it('uses the existing Remaining problem row for the selected target without triggering manual controls', async () => {
  const data: any = snapshot(false, 'CLOSED', true)
  data.remaining_problems.problems = [{ id: 20, problem_number: 'EXT-1', title: 'Extra', assigned_team_count: 0,
    assigned_teams: [], assignment_status: 'UNASSIGNED', can_assign: true, can_rebid: true }]
  mocks.get.mockResolvedValue(data); mocks.extra.mockResolvedValue(grid())
  mocks.assign.mockResolvedValue({ ...grid(), assignments: [], deduction: 300, failures: [] })
  await act(async () => renderR1())
  const row = host.querySelector('.round-remaining-row') as HTMLElement
  await act(async () => row.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })))
  expect(row.getAttribute('aria-selected')).toBe('true')
  await click('AUTO ASSIGN')
  expect(mocks.assign).toHaveBeenCalledWith(20, 300)
  expect(host.querySelector('[role="dialog"]')).toBeNull()
})

it('shows only free problems in one dropdown with no duplicate grid or team names', async () => {
  const select = vi.fn()
  mocks.extra.mockResolvedValue({ ...grid(), problems: [...grid().problems,
    { id: 21, problem_number: '2', source: 'ROUND1', capacity_remaining: 2 },
    { id: 22, problem_number: '3', source: 'ROUND1', capacity_remaining: 0 }] })
  await act(async () => root.render(<ExtraGrid realtimeEvent={null} onSelectProblem={select} />))
  const dropdown = host.querySelector('#extra-assignment-problem') as HTMLSelectElement
  expect([...dropdown.options].map(option => option.value)).toEqual(['', '20', '21'])
  expect(dropdown.options[2].textContent).toBe('PS-2 — 2 slots remaining')
  await act(async () => { dropdown.value = '20'; dropdown.dispatchEvent(new Event('change', { bubbles: true })) })
  expect(select).toHaveBeenCalledWith(20)
  expect(dropdown.value).toBe('20')
  expect(host.querySelectorAll('select')).toHaveLength(1)
  expect(host.querySelectorAll('.extra-grid article, .extra-grid [role="table"]')).toHaveLength(0)
  expect(host.textContent).not.toContain('Unassigned Participant')
  expect(host.querySelector('#extra-assignment-remaining')?.textContent).toBe('1')
  expect(host.querySelector('.extra-grid-summary')?.textContent).toContain('Average of all Round 1 bids')
})

it.each([{ can_auto_assign: false }, { remaining_team_count: 0 }])('disables Auto Assign when the backend eligibility gates are not satisfied: %j', async gate => {
  mocks.extra.mockResolvedValue({ ...grid(), ...gate })
  await act(async () => root.render(<ExtraGrid realtimeEvent={null} selectedProblemId={20} />))
  expect([...host.querySelectorAll('button')].find(row => row.textContent === 'AUTO ASSIGN')?.disabled).toBe(true)
})

it('updates both panels after assignment and removes the full selected problem immediately', async () => {
  const data: any = snapshot(false, 'CLOSED', true)
  const problem = { id: 20, problem_number: '1', title: 'Target', assigned_team_count: 3, assigned_teams: [],
    assignment_status: 'PARTIAL', auction_capacity: 5, can_assign: false, can_rebid: false }
  data.remaining_problems.problems = [problem]
  const updated = { ...data, remaining_problems: { ...data.remaining_problems, problems: [{ ...problem, assigned_team_count: 5, auction_full: true, assignment_status: 'ASSIGNED' }] } }
  mocks.get.mockResolvedValueOnce(data).mockResolvedValue(updated)
  mocks.extra.mockResolvedValue({ ...grid(), remaining_team_count: 4, problems: [{ ...grid().problems[0], assigned_team_count: 3, capacity_remaining: 2 }] })
  mocks.assign.mockResolvedValue({ ...grid(), remaining_team_count: 2, assignments: [{ team_id: 1 }, { team_id: 2 }], deduction: 300, failures: [],
    problems: [{ ...grid().problems[0], assigned_team_count: 5, capacity_remaining: 0 }] })
  await act(async () => renderR1())
  const dropdown = host.querySelector('#extra-assignment-problem') as HTMLSelectElement
  await act(async () => { dropdown.value = '20'; dropdown.dispatchEvent(new Event('change', { bubbles: true })) })
  await click('AUTO ASSIGN')
  expect(mocks.assign).toHaveBeenCalledWith(20, 300)
  expect(host.querySelector('#extra-assignment-remaining')?.textContent).toBe('2')
  expect(dropdown.options).toHaveLength(1)
  expect(dropdown.value).toBe('')
  expect(host.querySelector('.round-remaining-count')?.textContent).toBe('5 teams')
  expect(host.querySelector('.round-assignment-status')?.textContent).toBe('Auction Full')
  expect(mocks.get).toHaveBeenCalledTimes(2)
  expect(mocks.extra).toHaveBeenCalledTimes(1)
  expect(host.querySelectorAll('.round-remaining-actions button')).toHaveLength(2)
})

it('keeps manual corrections and external import on Change Problem without loading automatic controls', async () => {
  const team = { team_id: 1, team_name: 'Correction Team', coins: 5000, assignment_status: 'NOT_ASSIGNED', current_problem: null }
  mocks.corrections.mockResolvedValue({ capacity_per_problem: 5, problems: [], external_problems: [], teams: [team], unassigned_teams: [team] })
  await act(async () => root.render(<ChangeProblemPage />))
  expect(host.textContent).toContain('Current Round 1 assignments')
  expect(host.textContent).toContain('Import Problems from Excel')
  expect(host.textContent).not.toContain('Automatic Extra')
  expect(host.textContent).not.toContain('AUTO ASSIGN')
  expect(host.querySelector('#extra-assignment-deduction')).toBeNull()
  expect(mocks.extra).not.toHaveBeenCalled()
  await click('Assign Problem')
  expect(host.querySelector('[role="dialog"]')).toBeTruthy()
})
