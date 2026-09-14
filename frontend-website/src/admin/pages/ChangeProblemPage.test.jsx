import { act, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ChangeProblemPage from './ChangeProblem'
import { changeRoundOneAssignment, getRoundOneAssignments, importExternalProblems } from '../services/api'

vi.mock('../services/api', async (original) => ({
  ...await original(),
  changeRoundOneAssignment: vi.fn(),
  getRoundOneAssignments: vi.fn(),
  importExternalProblems: vi.fn(),
}))

const problem = (id, number, title, source = 'ROUND1') => ({
  id, problem_number: number, title, description: `${title} description`, source,
  source_label: source === 'ROUND1' ? 'Round 1' : 'External', assigned_team_count: 1,
  capacity: 5, capacity_remaining: 4, is_full: false,
})
const initial = {
  message: '', capacity_per_problem: 5, external_problems: [], unassigned_teams: [],
  problems: [problem(4, '4', 'Original'), problem(11, '11', 'Replacement', 'EXTERNAL')],
  teams: [{
    team_id: 1, team_name: 'Team Alpha', leader_name: 'Alpha Leader', leader_email: 'alpha@example.com',
    coins: 5000, current_problem: problem(4, '4', 'Original'), assignment_status: 'ASSIGNED',
  }],
}
const updated = {
  ...initial,
  message: 'Round 1 problem assignment changed. No balance change.',
  teams: [{ ...initial.teams[0], current_problem: problem(11, '11', 'Replacement', 'EXTERNAL') }],
}

let host
let root
const render = async (realtimeEvent = null) => act(async () => root.render(<StrictMode><ChangeProblemPage realtimeEvent={realtimeEvent} /></StrictMode>))
const button = (label) => [...host.querySelectorAll('button')].find((item) => item.textContent === label)

describe('ChangeProblemPage refresh boundaries', () => {
  beforeEach(() => {
    Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
    vi.clearAllMocks()
    getRoundOneAssignments.mockResolvedValue(structuredClone(initial))
    changeRoundOneAssignment.mockResolvedValue(structuredClone(updated))
    importExternalProblems.mockResolvedValue({ ...structuredClone(initial), message: 'Imported 1 external problem.' })
    host = document.createElement('div')
    root = createRoot(host)
  })

  afterEach(() => act(() => root.unmount()))

  it('performs one initial GET and ignores individual assignment/import events', async () => {
    await render()
    expect(getRoundOneAssignments).toHaveBeenCalledTimes(1)
    getRoundOneAssignments.mockClear()

    await render({ type: 'round1_assignment_changed', payload: { team_id: 1 } })
    await render({ type: 'external_problems_imported', payload: { created: 1 } })

    expect(getRoundOneAssignments).not.toHaveBeenCalled()
  })

  it('uses only the initial GET when opened after both boundaries already completed', async () => {
    await render({ type: 'event_snapshot', payload: { event_state: 'CODING', rounds: { ROUND1: { ended: true }, WILDCARD: { ended: true } } } })

    expect(getRoundOneAssignments).toHaveBeenCalledTimes(1)
  })

  it('refreshes once at each authoritative completion boundary and dedupes snapshots', async () => {
    await render()
    getRoundOneAssignments.mockClear()
    const roundOneComplete = { type: 'event_state_changed', payload: { event_state: 'ROUND1_RESULT', rounds: { ROUND1: { ended: true }, WILDCARD: { ended: false } } } }

    await render(roundOneComplete)
    expect(getRoundOneAssignments).toHaveBeenCalledTimes(1)
    await render({ ...roundOneComplete, type: 'event_snapshot' })
    expect(getRoundOneAssignments).toHaveBeenCalledTimes(1)

    await render({ type: 'wildcard_updated', payload: { action: 'problem_selected' } })
    expect(getRoundOneAssignments).toHaveBeenCalledTimes(1)
    const wildcardComplete = { type: 'event_state_changed', payload: { event_state: 'CODING', rounds: { ROUND1: { ended: true }, WILDCARD: { ended: true } } } }
    await render(wildcardComplete)
    expect(getRoundOneAssignments).toHaveBeenCalledTimes(2)
    await render({ ...wildcardComplete, type: 'event_snapshot' })
    expect(getRoundOneAssignments).toHaveBeenCalledTimes(2)
  })

  it('uses the manual assignment response without a subsequent GET', async () => {
    await render()
    getRoundOneAssignments.mockClear()
    const select = host.querySelector('#target-problem-1')
    await act(async () => {
      select.value = '11'
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await act(async () => button('Change').click())
    await act(async () => button('Confirm Change').click())

    expect(changeRoundOneAssignment).toHaveBeenCalledTimes(1)
    expect(changeRoundOneAssignment).toHaveBeenCalledWith(1, 11, null)
    expect(getRoundOneAssignments).not.toHaveBeenCalled()
    expect(host.textContent).toContain('#11 Replacement')
  })

  it('uses the external import response without a subsequent GET', async () => {
    await render()
    getRoundOneAssignments.mockClear()
    const input = host.querySelector('input[type="file"]')
    const file = new File(['Problem Number,Title,Description'], 'external.csv', { type: 'text/csv' })
    Object.defineProperty(input, 'files', { configurable: true, value: [file] })
    await act(async () => input.dispatchEvent(new Event('change', { bubbles: true })))
    await act(async () => button('Import problems').click())

    expect(importExternalProblems).toHaveBeenCalledTimes(1)
    expect(importExternalProblems).toHaveBeenCalledWith(file)
    expect(getRoundOneAssignments).not.toHaveBeenCalled()
  })

  it('performs exactly one GET for the manual refresh button', async () => {
    await render()
    getRoundOneAssignments.mockClear()

    await act(async () => button('Refresh assignments').click())

    expect(getRoundOneAssignments).toHaveBeenCalledTimes(1)
  })
})
