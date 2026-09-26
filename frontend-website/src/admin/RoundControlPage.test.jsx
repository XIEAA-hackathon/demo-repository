import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { RoundControlPage } from './App'
import { assignRoundOneProblem, downloadRoundOneAssignments, getRoundControl, startRoundBidding } from './services/api'

vi.mock('./services/api', async (original) => ({
  ...await original(),
  downloadRoundOneAssignments: vi.fn(),
  assignRoundOneProblem: vi.fn(),
  getRoundControl: vi.fn(),
  startRoundBidding: vi.fn(),
}))
const initial = {
  status: 'PREVIEW', ended: false, round_type: 'ROUND1', problems: [], settings: { base_price: 100 },
  current_problem: { id: 1, problem_number: '1', title: 'Preview regression', description: 'Review the challenge' },
  event: { event_state: 'ROUND1_PREVIEW', last_state_update: '2026-09-13T10:00:00Z', timing: { server_time: '2026-09-13T10:00:00Z', ends_at: '2026-09-13T10:00:02Z', paused: false } },
}
let host, root
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.clearAllMocks()
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:round-1-export'), revokeObjectURL: vi.fn() })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  host = document.createElement('div'); root = createRoot(host)
  getRoundControl.mockResolvedValue(initial)
  downloadRoundOneAssignments.mockResolvedValue(new Blob(['round-1']))
})
afterEach(() => { act(() => root.unmount()); vi.restoreAllMocks() })
const render = async (state, remaining = 0) => act(async () => root.render(<RoundControlPage round="round-1" state={state} remaining={remaining} />))
const buttons = () => [...host.querySelectorAll('button')]

it('shows Start bidding immediately on expiry and ignores an older round refresh', async () => {
  await render(initial.event, 2)
  expect(buttons().some(button => button.textContent === 'End preview / start bidding')).toBe(true)
  let resolveRefresh
  getRoundControl.mockImplementation(() => new Promise(resolve => { resolveRefresh = resolve }))
  const expired = { ...initial.event, last_state_update: '2026-09-13T10:00:02Z', timing: { server_time: '2026-09-13T10:00:02Z', ends_at: null, paused: false }, rounds: { ROUND1: { status: 'PREVIEW_EXPIRED' } } }
  await render(expired)
  const verify = () => {
    expect(host.textContent).toContain('Preview complete')
    expect(host.querySelector('.round-live-clock').textContent).toBe('00:00:00')
    expect(buttons().some(button => button.textContent === 'Start bidding' && !button.disabled)).toBe(true)
    expect(buttons().some(button => /^(Start preview|Pause|Resume|\+30|−30|-30)/.test(button.textContent))).toBe(false)
  }
  verify()
  await act(async () => resolveRefresh(initial))
  verify()
  const bidding = { ...initial, status: 'BIDDING', event: { event_state: 'ROUND1_BIDDING', last_state_update: '2026-09-13T10:00:03Z', timing: { server_time: '2026-09-13T10:00:03Z', ends_at: '2026-09-13T10:00:13Z' } } }
  startRoundBidding.mockResolvedValue(bidding)
  getRoundControl.mockResolvedValue(bidding)
  await act(async () => buttons().find(button => button.textContent === 'Start bidding').click())
  expect(startRoundBidding).toHaveBeenCalledTimes(1)
  expect(startRoundBidding).toHaveBeenCalledWith('round-1')
  await render({ ...bidding.event, rounds: { ROUND1: { status: 'BIDDING' } } }, 10)
  expect(host.textContent).toContain('Round 1 — live bidding')
  expect(host.querySelector('.round-live-clock').textContent).toBe('00:00:10')
})

it('distinguishes ready to preview from bidding complete', async () => {
  getRoundControl.mockResolvedValue({ ...initial, status: 'READY', event: { event_state: 'WAITING' } })
  await render(null)
  expect(host.textContent).toContain('Ready to preview')
  expect(buttons().some(button => button.textContent === 'Start preview')).toBe(true)
  getRoundControl.mockResolvedValue({ ...initial, status: 'READY', event: { event_state: 'ROUND1_RESULT' } })
  await render({ event_state: 'ROUND1_RESULT', timing: { server_time: '2026-09-13T10:00:20Z' } })
  expect(host.textContent).toContain('Bidding complete')
  expect(buttons().some(button => button.textContent === 'Start preview')).toBe(false)
})

it('keeps the Round 1 export on demand and disabled until the round ends', async () => {
  await render(initial.event)
  const download = buttons().find(button => button.textContent === 'DOWNLOAD ROUND 1 ASSIGNMENTS')

  expect(download.disabled).toBe(true)
  expect(download.title).toBe('Available after Round 1 ends')
  expect(downloadRoundOneAssignments).not.toHaveBeenCalled()
})

it('generates the Round 1 export exactly once when clicked after completion', async () => {
  getRoundControl.mockResolvedValue({ ...initial, status: 'COMPLETE', ended: true })
  await render({ ...initial.event, rounds: { ROUND1: { status: 'COMPLETE', ended: true } } })
  const download = buttons().find(button => button.textContent === 'DOWNLOAD ROUND 1 ASSIGNMENTS')

  expect(download.disabled).toBe(false)
  await act(async () => download.click())

  expect(downloadRoundOneAssignments).toHaveBeenCalledTimes(1)
})

it('keeps manual assignment unlimited after auction capacity is full', async () => {
  const eligibleTeams = Array.from({ length: 7 }, (_, index) => ({
    team_id: index + 20, team_name: `Eligible ${index + 1}`, coins: 5000,
  }))
  getRoundControl.mockResolvedValue({
    ...initial,
    status: 'READY',
    current_problem: null,
    event: { event_state: 'WAITING' },
    remaining_problems: {
      eligible_teams: eligibleTeams,
      unassigned_team_count: 7,
      suggested_deduction: 100,
      round1_winning_bid_sum: 500,
      round1_winning_bid_count: 1,
      problems: [{
        id: 9, problem_number: '9', title: 'Shared challenge', assigned_team_count: 7,
        assigned_teams: [], assignment_status: 'ASSIGNED', auction_capacity: 5,
        auction_capacity_remaining: 0, auction_full: true, capacity_remaining: 0,
        can_rebid: false, can_assign: true,
      }],
    },
  })
  await render(null)

  const rebid = buttons().find(button => button.textContent === 'Re-bid')
  const assign = buttons().find(button => button.textContent === 'Assign')
  expect(rebid.disabled).toBe(true)
  expect(assign.disabled).toBe(false)
  expect(host.textContent).toContain('7 teams')
  expect(host.textContent).toContain('Auction Full')

  await act(async () => assign.click())
  const checkboxes = [...host.querySelectorAll('.round-team-selector input[type="checkbox"]')]
  expect(checkboxes).toHaveLength(7)
  for (const checkbox of checkboxes) {
    expect(checkbox.disabled).toBe(false)
    await act(async () => checkbox.click())
  }
  expect(host.querySelector('.round-team-selector legend').textContent).toContain('7 selected')
  expect(checkboxes.every(checkbox => !checkbox.disabled)).toBe(true)
  expect(assignRoundOneProblem).not.toHaveBeenCalled()
})
