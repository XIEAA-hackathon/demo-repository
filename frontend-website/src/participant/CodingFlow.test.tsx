import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CodingPage from './pages/CodingPage'
import { getStageRoute } from './routeConfig'
import { legacySubmissionRedirect } from './ParticipantApp'
import type { ParticipantDashboard } from './types'

const useParticipant = vi.fn()
vi.mock('./ParticipantContext', () => ({ useParticipant: () => useParticipant() }))

const dashboard = {
  eventState: 'CODING',
  currentUserId: '1',
  isLeader: true,
  team: { id: '7', name: 'Team Seven', leaderId: '1', members: [{ id: '1', name: 'Leader', email: 'leader@test', isLeader: true }] },
  wallet: { teamId: '7', balance: 750, currency: 'coins' },
  finalProblem: { id: '9', number: 9, title: 'Final Build', summary: 'Build it', description: 'Build the final system.', startingBid: 0 },
  currentProblem: null,
  lab: { id: 2, name: 'Lab Aurora', assignment_id: 4, version: 1 },
  labAllocationReady: true,
  labAllocationStatus: 'ASSIGNED',
  submissionsOpen: false,
  submission: { id: '3', teamId: '7', problemId: '9', repositoryUrl: 'https://github.com/team-seven/final', submittedAt: '2026-09-19T09:00:00Z', updatedAt: '2026-09-19T10:00:00Z', submittedByName: 'Leader', status: 'SUBMITTED' },
  timing: { serverTime: '2026-09-19T10:00:00Z', receivedAt: Date.now(), startedAt: null, endsAt: null, paused: true, pausedRemainingSeconds: 3600, remainingSeconds: 3600 },
} as unknown as ParticipantDashboard

let host: HTMLDivElement
let root: ReturnType<typeof createRoot>
let submitGitHubRepository: ReturnType<typeof vi.fn>

describe('merged coding and submission flow', () => {
  beforeEach(() => {
    Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
    host = document.createElement('div')
    root = createRoot(host)
    submitGitHubRepository = vi.fn().mockResolvedValue(undefined)
    useParticipant.mockReturnValue({ dashboard, service: { submitGitHubRepository }, refresh: vi.fn() })
  })

  afterEach(() => act(() => root.unmount()))

  it('enables repository updates for the leader throughout Coding', async () => {
    await act(async () => root.render(<CodingPage />))
    expect(host.textContent).toContain('Final Build')
    expect(host.textContent).toContain('Lab Aurora')
    expect(host.textContent).toContain('01:00:00')
    expect(host.querySelector('a[href="https://github.com/team-seven/final"]')).not.toBeNull()
    expect(host.querySelector<HTMLInputElement>('input[type="url"]')?.disabled).toBe(false)
    const button = host.querySelector<HTMLButtonElement>('button[type="submit"]')
    expect(button?.textContent).toBe('Update repository')
    expect(button?.disabled).toBe(false)
  })

  it('submits an updated repository URL during Coding', async () => {
    await act(async () => root.render(<CodingPage />))
    const input = host.querySelector<HTMLInputElement>('input[type="url"]')!
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
      setter?.call(input, 'https://github.com/team-seven/updated')
      input.dispatchEvent(new Event('input', { bubbles: true }))
      input.form?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })
    expect(submitGitHubRepository).toHaveBeenCalledWith('https://github.com/team-seven/updated')
  })

  it('enables a first submission for a leader even if the legacy flag is false', async () => {
    useParticipant.mockReturnValue({ dashboard: { ...dashboard, submission: null }, service: { submitGitHubRepository }, refresh: vi.fn() })
    await act(async () => root.render(<CodingPage />))
    expect(host.querySelector<HTMLInputElement>('input[type="url"]')?.disabled).toBe(false)
    expect(host.querySelector<HTMLButtonElement>('button[type="submit"]')?.textContent).toBe('Submit repository')
  })

  it('keeps repository controls disabled for ordinary members', async () => {
    const memberDashboard = {
      ...dashboard,
      currentUserId: '2',
      team: { ...dashboard.team, members: [...dashboard.team.members, { id: '2', name: 'Member', email: 'member@test', isLeader: false }] },
    }
    useParticipant.mockReturnValue({ dashboard: memberDashboard, service: { submitGitHubRepository }, refresh: vi.fn() })
    await act(async () => root.render(<CodingPage />))
    expect(host.querySelector<HTMLInputElement>('input[type="url"]')?.disabled).toBe(true)
    expect(host.querySelector<HTMLButtonElement>('button[type="submit"]')?.disabled).toBe(true)
    expect(host.textContent).toContain('Only your team leader can submit or update the final repository.')
  })

  it('normalizes the legacy phase and keeps the old URL as a redirect', () => {
    expect(getStageRoute('SUBMISSION').path).toBe('/participant/coding')
    expect(legacySubmissionRedirect).toBe('/participant/coding')
  })
})
