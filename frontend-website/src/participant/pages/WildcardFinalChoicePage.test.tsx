import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import WildcardFinalChoicePage from './WildcardFinalChoicePage'
import { useParticipant } from '../ParticipantContext'
import { getStageRoute } from '../routeConfig'
import type { ParticipantDashboard } from '../types'

vi.mock('../ParticipantContext', () => ({ useParticipant: vi.fn() }))

const roundOne = { id: '11', number: 2, title: 'Round 1 keeper', summary: 'r1', description: 'r1', startingBid: 0 }
const wildcard = { id: '22', number: 7, title: 'Wildcard flyer', summary: 'wc', description: 'wc', startingBid: 0, available: false }
const base = {
  eventState: 'WILDCARD_FINAL_CHOICE',
  isLeader: true,
  currentUserId: '1',
  currentUser: { id: '1', name: 'Lead', loginId: 'lead@test', role: 'leader' },
  team: { id: '9', name: 'Finalists', leaderId: '1', members: [{ id: '1', name: 'Lead', email: '', isLeader: true }] },
  wallet: { teamId: '9', balance: 750, currency: 'coins' },
  roundOneProblem: roundOne,
  wildcardProblem: wildcard,
  finalProblem: null,
  finalProblemChoice: null,
  finalProblemConfirmedAt: null,
  wildcardWinningBid: 250,
  wildcardCoinsPaid: 250,
  wildcard: { status: 'selected', rank: 1, winningBid: 250 },
  gameConfig: {},
  timing: {},
  bidCooldownRemainingSeconds: 0,
} as unknown as ParticipantDashboard

let host: HTMLDivElement
let root: Root
const confirmFinalProblemChoice = vi.fn()
const refresh = vi.fn()

const renderPage = async (dashboard: ParticipantDashboard = base) => {
  vi.mocked(useParticipant).mockReturnValue({ dashboard, service: { confirmFinalProblemChoice }, refresh } as never)
  await act(async () => {
    root.render(<WildcardFinalChoicePage />)
  })
}

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.clearAllMocks()
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
})

it('registers the final-choice stage route', () => {
  expect(getStageRoute('WILDCARD_FINAL_CHOICE').path).toBe('/participant/wildcard/choose')
})

it('renders both problems with the already-deducted cost and no new charge or refund', async () => {
  await renderPage()
  const text = host.textContent ?? ''
  expect(text).toContain('Round 1 keeper')
  expect(text).toContain('Wildcard flyer')
  expect(text).toContain('already deducted')
  expect(text).toContain('does not change that cost')
  expect(text).not.toMatch(/refund/i)
  expect(text).not.toMatch(/extra charge|additional payment/i)
})

it('selects on first click and confirms on second click, then locks', async () => {
  await renderPage()
  const radios = host.querySelectorAll('input[name="final-problem"]')
  expect(radios.length).toBe(2)
  await act(async () => {
    ;(radios[0] as HTMLInputElement).click()
  })
  const buttons = [...host.querySelectorAll('button')].map((button) => button.textContent)
  expect(buttons).toContain('Confirm final problem')
  await act(async () => {
    host.querySelector('.action-row button')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
  expect(host.textContent).toContain('irreversible')
  await act(async () => {
    const confirmButton = [...host.querySelectorAll('.modal__actions button')].find((button) => button.textContent === 'Confirm final problem')
    confirmButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
  expect(confirmFinalProblemChoice).toHaveBeenCalledWith('ROUND1')
  expect(refresh).toHaveBeenCalled()

  await renderPage({ ...base, finalProblemChoice: 'ROUND1', finalProblem: roundOne } as ParticipantDashboard)
  expect(host.textContent).toContain('Final problem confirmed')
  expect(host.querySelector('input[name="final-problem"]')).toBeNull()
})
