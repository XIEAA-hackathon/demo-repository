import { act, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ChangeProblemPage from './ChangeProblem'
import StyleBoundary from '../../shared/components/StyleBoundary'
import { changeRoundOneAssignment, getRoundOneAssignments } from '../services/api'

vi.mock('../services/api', async (original) => ({
  ...await original(), changeRoundOneAssignment: vi.fn(), getRoundOneAssignments: vi.fn(),
}))
const problem = (id, number, title, source = 'ROUND1') => ({
  id, problem_number: number, title, description: `${title} description`, source,
  source_label: source === 'ROUND1' ? 'Round 1' : 'Wildcard', assigned_team_count: 1,
})
const initial = {
  unassigned_teams: [],
  problems: [problem(4, '4', 'Original'), problem(11, '18', 'Emergency', 'WILDCARD')],
  teams: [{ team_id: 1, team_name: 'Team Alpha', leader_name: 'Alpha Leader', leader_email: 'alpha@example.com',
    coins: 5000, current_problem: problem(4, '4', 'Original'), assignment_status: 'ASSIGNED' }],
}
const updated = { ...initial, message: 'Current problem assignment changed. No balance change.',
  teams: [{ ...initial.teams[0], current_problem: initial.problems[1] }] }
let host, root
const render = async (realtimeEvent = null) => act(async () => root.render(<StrictMode><ChangeProblemPage realtimeEvent={realtimeEvent} /></StrictMode>))
const button = (label) => [...host.querySelectorAll('button')].find((item) => item.textContent === label)
const click = async (element) => act(async () => element.click())
const input = async (element, value) => act(async () => {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(element, value)
  element.dispatchEvent(new Event('input', { bubbles: true }))
})
const key = async (value, shiftKey = false) => act(async () => document.dispatchEvent(new KeyboardEvent('keydown', { key: value, shiftKey, bubbles: true, cancelable: true })))
const choose = async (title = 'Emergency') => {
  await click(host.querySelector('#target-problem-1'))
  await click([...host.querySelectorAll('.problem-picker__card')].find(card => card.textContent.includes(title)))
  await click(button('Done'))
}

describe('Change Problem current/final correction', () => {
  beforeEach(() => {
    Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
    vi.clearAllMocks()
    getRoundOneAssignments.mockResolvedValue(structuredClone(initial))
    changeRoundOneAssignment.mockResolvedValue(structuredClone(updated))
    host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  })
  afterEach(() => { act(() => root.unmount()); host.remove() })

  it('removes external import, native selectors and auction language; shows operational counts', async () => {
    await render()
    expect(host.querySelector('input[type="file"], select')).toBeNull()
    expect(host.textContent).not.toMatch(/External|Import Problems|Auction capacity|Financial control/)
    expect([...host.querySelectorAll('.change-problem-summary strong')].map(item => item.textContent)).toEqual(['1', '0', '1', '1'])
    expect(host.textContent).toContain('Current assignments')
    expect(host.textContent).toContain('Teams Without a Current Problem')
  })

  it('has an accessible searchable picker with source filters, disabled current and selected feedback', async () => {
    getRoundOneAssignments.mockResolvedValue({ ...initial, problems: [...initial.problems,
      { ...problem(99, '99', 'Legacy', 'EXTERNAL'), source_label: 'External' }] })
    await render()
    const trigger = host.querySelector('#target-problem-1'); trigger.focus()
    await click(trigger)
    const dialog = host.querySelector('[role="dialog"]')
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(document.activeElement.id).toBe('problem-picker-search')
    expect(dialog.textContent).not.toContain('Legacy')
    const current = dialog.querySelector('.is-current')
    expect(current.disabled).toBe(true)
    expect(current.textContent).toContain('CURRENT')
    await input(host.querySelector('#problem-picker-search'), 'description')
    expect(host.querySelectorAll('.problem-picker__card')).toHaveLength(2)
    await input(host.querySelector('#problem-picker-search'), '18')
    expect(host.querySelectorAll('.problem-picker__card')).toHaveLength(1)
    await input(host.querySelector('#problem-picker-search'), '')
    await click(button('Round 1'))
    expect(host.querySelectorAll('.problem-picker__card')).toHaveLength(1)
    await click(button('Wildcard'))
    const target = host.querySelector('.problem-picker__card')
    await click(target)
    expect(target.getAttribute('aria-pressed')).toBe('true')
    expect(target.textContent).toContain('Selected')
    expect(changeRoundOneAssignment).not.toHaveBeenCalled()
    await key('Escape')
    expect(host.querySelector('[role="dialog"]')).toBeNull()
    expect(document.activeElement).toBe(trigger)
    expect(trigger.textContent).toContain('#18 Emergency')
    expect(button('Change').disabled).toBe(false)
  })

  it('traps keyboard focus and restores it; semantic cards support normal keyboard activation', async () => {
    await render()
    await click(host.querySelector('#target-problem-1'))
    const close = host.querySelector('[aria-label="Close problem picker"]')
    close.focus()
    await key('Tab', true)
    expect(document.activeElement).toBe(button('Done'))
    await key('Tab')
    expect(document.activeElement).toBe(close)
    const cards = host.querySelectorAll('.problem-picker__card')
    expect(cards[1].tagName).toBe('BUTTON')
    expect(cards[1].type).toBe('button')
    await key('Escape')
    expect(document.body.style.overflow).toBe('')
  })

  it('only saves after confirmation and uses the mutation response without another GET', async () => {
    await render(); getRoundOneAssignments.mockClear()
    await choose()
    expect(changeRoundOneAssignment).not.toHaveBeenCalled()
    await click(button('Change'))
    const dialog = host.querySelector('[role="dialog"]')
    expect(dialog.textContent).toContain('#4 Original')
    expect(dialog.textContent).toContain('#18 Emergency')
    expect(dialog.textContent).toContain('5,000 → 5,000')
    expect(dialog.querySelector('input')).toBeNull()
    await click(button('Confirm Change'))
    expect(changeRoundOneAssignment).toHaveBeenCalledWith(1, 11, null)
    expect(getRoundOneAssignments).not.toHaveBeenCalled()
    expect(host.querySelector('.change-problem-current').textContent).toContain('#18 Emergency')
    expect(host.querySelector('[role="dialog"]')).toBeNull()
  })

  it('preserves keyboard focus in the real admin shadow style boundary', async () => {
    await act(async () => root.render(<StyleBoundary styles="" rootClassName="admin-root"><ChangeProblemPage /></StyleBoundary>))
    const shadow = host.firstElementChild.shadowRoot
    const trigger = shadow.querySelector('#target-problem-1')
    trigger.focus(); await click(trigger)
    expect(shadow.activeElement.id).toBe('problem-picker-search')
    const close = shadow.querySelector('[aria-label="Close problem picker"]')
    close.focus(); await key('Tab', true)
    expect(shadow.activeElement.textContent).toBe('Done')
    await key('Tab')
    expect(shadow.activeElement).toBe(close)
    await key('Escape')
    expect(shadow.querySelector('[role="dialog"]')).toBeNull()
    expect(shadow.activeElement).toBe(trigger)
  })

  it('retains optional balance editing for unassigned teams', async () => {
    const team = { ...initial.teams[0], current_problem: null, assignment_status: 'NOT_ASSIGNED' }
    getRoundOneAssignments.mockResolvedValue({ ...initial, teams: [team], unassigned_teams: [team] })
    await render()
    await click(button('Assign Problem'))
    await click([...host.querySelectorAll('.problem-picker__card')].find(card => card.textContent.includes('Emergency')))
    await click(button('Done'))
    await click(button('Review assignment'))
    const balance = host.querySelector('#assignment-new-balance')
    await input(balance, '-1')
    expect(button('Confirm Assignment').disabled).toBe(true)
    await input(balance, '1200')
    expect(host.querySelector('#assignment-balance-effect').textContent).toContain('5,000 → 1,200')
    await click(button('Confirm Assignment'))
    expect(changeRoundOneAssignment).toHaveBeenCalledWith(1, 11, 1200)
  })

  it('allows a correction even with more than auction capacity currently assigned', async () => {
    getRoundOneAssignments.mockResolvedValue({ ...initial, problems: [initial.problems[0],
      { ...initial.problems[1], assigned_team_count: 7 }] })
    await render()
    await click(host.querySelector('#target-problem-1'))
    const target = [...host.querySelectorAll('.problem-picker__card')].find(card => card.textContent.includes('Emergency'))
    expect(target.disabled).toBe(false)
    expect(target.textContent).toContain('7 assigned')
    await click(target); await click(button('Done')); await click(button('Change'))
    expect(button('Confirm Change').disabled).toBe(false)
    expect(host.querySelector('[role="dialog"]').textContent).not.toMatch(/capacity|Teams assigned after/i)
  })

  it('does not expose a stale pending selection after refresh changes the current problem', async () => {
    await render(); await choose()
    getRoundOneAssignments.mockResolvedValue(updated)
    await click(button('Refresh assignments'))
    expect(button('Change').disabled).toBe(true)
    expect(host.querySelector('#target-problem-1').textContent).toContain('Select new problem')
  })

  it('performs one initial GET and ignores individual assignment events', async () => {
    await render()
    expect(getRoundOneAssignments).toHaveBeenCalledTimes(1)
    getRoundOneAssignments.mockClear()
    await render({ type: 'round1_assignment_changed', payload: { team_id: 1 } })
    expect(getRoundOneAssignments).not.toHaveBeenCalled()
  })

  it('uses only the initial GET when opened after both boundaries already completed', async () => {
    await render({ type: 'event_snapshot', payload: { event_state: 'CODING', rounds: { ROUND1: { ended: true }, WILDCARD: { ended: true } } } })
    expect(getRoundOneAssignments).toHaveBeenCalledTimes(1)
  })

  it('refreshes once at each authoritative completion boundary and dedupes snapshots', async () => {
    await render(); getRoundOneAssignments.mockClear()
    const roundOneComplete = { type: 'event_state_changed', payload: { event_state: 'ROUND1_RESULT', rounds: { ROUND1: { ended: true }, WILDCARD: { ended: false } } } }
    await render(roundOneComplete)
    expect(getRoundOneAssignments).toHaveBeenCalledTimes(1)
    await render({ ...roundOneComplete, type: 'event_snapshot' })
    await render({ type: 'wildcard_updated', payload: { action: 'problem_selected' } })
    expect(getRoundOneAssignments).toHaveBeenCalledTimes(1)
    const wildcardComplete = { type: 'event_state_changed', payload: { event_state: 'CODING', rounds: { ROUND1: { ended: true }, WILDCARD: { ended: true } } } }
    await render(wildcardComplete); await render({ ...wildcardComplete, type: 'event_snapshot' })
    expect(getRoundOneAssignments).toHaveBeenCalledTimes(2)
  })

  it('performs exactly one GET for the manual refresh button', async () => {
    await render(); getRoundOneAssignments.mockClear()
    await click(button('Refresh assignments'))
    expect(getRoundOneAssignments).toHaveBeenCalledTimes(1)
  })
})
