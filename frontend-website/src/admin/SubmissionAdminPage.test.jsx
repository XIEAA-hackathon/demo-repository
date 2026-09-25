import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CodingRoundAdminPage } from './App'
import { closeSubmissions, getAdminSubmissions, openSubmissions } from './services/api'

vi.mock('./services/api', async (original) => ({
  ...await original(),
  closeSubmissions: vi.fn(),
  getAdminSubmissions: vi.fn(),
  openSubmissions: vi.fn(),
}))

const snapshot = {
  open: true,
  export_available: false,
  total: 2,
  submitted: 0,
  pending: 2,
  rows: [
    { team_id: 1, team_name: 'Team Alpha', status: 'PENDING', github_url: null, submitted_at: null, updated_at: null, submitted_by: null, final_problem: null, allocated_lab: { id: 1, name: 'Lab Aurora' } },
    { team_id: 2, team_name: 'Team Beta', status: 'PENDING', github_url: null, submitted_at: null, updated_at: null, submitted_by: null, final_problem: null },
  ],
}

let host
let root
let hidden

const render = async (props) => act(async () => root.render(<CodingRoundAdminPage {...props} />))

describe('CodingRoundAdminPage refresh architecture', () => {
  beforeEach(() => {
    Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
    vi.useFakeTimers()
    vi.clearAllMocks()
    hidden = false
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden })
    getAdminSubmissions.mockResolvedValue(structuredClone(snapshot))
    openSubmissions.mockResolvedValue({ ...structuredClone(snapshot), open: true })
    closeSubmissions.mockResolvedValue({ ...structuredClone(snapshot), open: false })
    host = document.createElement('div')
    root = createRoot(host)
  })

  afterEach(() => {
    act(() => root.unmount())
    vi.useRealTimers()
  })

  it('removes the status banner while preserving Coding controls, submissions, and the untimed layout', async () => {
    await render({ socketStatus: 'connected' })
    expect(getAdminSubmissions).toHaveBeenCalledTimes(1)
    expect(host.querySelector('.coding-status-panel')).toBeNull()
    expect(host.textContent).not.toContain('ACTIVE')
    expect(host.textContent).not.toContain('Coding has no deadline and ends only when an admin closes the round.')
    expect(Array.from(host.querySelectorAll('.stat-card'), card => card.textContent)).not.toContain('REPOSITORY SUBMISSIONSOPEN')
    expect(host.textContent).toContain('Close Coding Round')
    expect(host.textContent).toContain('Repository Submissions')
    expect(host.textContent).toContain('WINDOWOPEN')
    expect(host.textContent).not.toContain('Time remaining')
    expect(host.textContent).not.toContain('Coding duration')
    for (const control of ['Pause', 'Resume', '+30 sec', '−30 sec']) expect(host.textContent).not.toContain(control)
    expect(host.textContent).toContain('Lab Aurora')
    getAdminSubmissions.mockClear()

    await act(async () => vi.advanceTimersByTimeAsync(59_000))
    expect(getAdminSubmissions).not.toHaveBeenCalled()
    await act(async () => vi.advanceTimersByTimeAsync(1_000))
    expect(getAdminSubmissions).toHaveBeenCalledTimes(1)
  })

  it('polls every 30 seconds while the socket is disconnected', async () => {
    await render({ socketStatus: 'disconnected' })
    getAdminSubmissions.mockClear()

    await act(async () => vi.advanceTimersByTimeAsync(29_999))
    expect(getAdminSubmissions).not.toHaveBeenCalled()
    await act(async () => vi.advanceTimersByTimeAsync(1))
    expect(getAdminSubmissions).toHaveBeenCalledTimes(1)
    await act(async () => vi.advanceTimersByTimeAsync(30_000))
    expect(getAdminSubmissions).toHaveBeenCalledTimes(2)
  })

  it('applies a submission WebSocket delta locally without an immediate GET', async () => {
    await render({ socketStatus: 'connected' })
    getAdminSubmissions.mockClear()
    const event = {
      type: 'submission_updated',
      payload: {
        team_id: 1,
        submission: {
          git_url: 'https://github.com/team-alpha/final',
          submitted_at: '2026-09-14T10:00:00Z',
          submitted_by: 'Alpha Leader',
          status: 'SUBMITTED',
        },
      },
    }

    await render({ socketStatus: 'connected', realtimeEvent: event })

    expect(getAdminSubmissions).not.toHaveBeenCalled()
    expect(host.querySelector('a[href="https://github.com/team-alpha/final"]')).not.toBeNull()
    expect(host.textContent).toContain('Alpha Leader')
    expect(host.textContent).toContain('SUBMITTED1')
    expect(host.textContent).toContain('PENDING1')
  })

  it('uses a 60-second fallback while hidden', async () => {
    hidden = true
    await render({ socketStatus: 'disconnected' })
    getAdminSubmissions.mockClear()

    await act(async () => vi.advanceTimersByTimeAsync(59_999))
    expect(getAdminSubmissions).not.toHaveBeenCalled()
    await act(async () => vi.advanceTimersByTimeAsync(1))
    expect(getAdminSubmissions).toHaveBeenCalledTimes(1)
  })

  it('refreshes exactly once when the tab becomes visible', async () => {
    hidden = true
    await render({ socketStatus: 'connected' })
    getAdminSubmissions.mockClear()

    hidden = false
    await act(async () => document.dispatchEvent(new Event('visibilitychange')))

    expect(getAdminSubmissions).toHaveBeenCalledTimes(1)
  })

  it('opens untimed Coding directly and refreshes authoritative state', async () => {
    getAdminSubmissions.mockResolvedValue({ ...structuredClone(snapshot), open: false })
    const onGlobalSync = vi.fn().mockResolvedValue(true)
    await render({
      socketStatus: 'connected',
      state: { rounds: { WILDCARD: { status: 'COMPLETE', ended: true } } },
      onGlobalSync,
    })
    const open = [...host.querySelectorAll('button')].find((button) => button.textContent === 'Open Coding Round')

    await act(async () => open.click())

    expect(openSubmissions).toHaveBeenCalledTimes(1)
    expect(onGlobalSync).toHaveBeenCalledTimes(1)
    expect(host.textContent).toContain('Coding Round opened.')
    expect(host.textContent).toContain('Close Coding Round')
    expect(host.querySelector('input[type="number"]')).toBeNull()
  })

  it('still lets the admin close Coding and enter the Judging wait', async () => {
    await render({ socketStatus: 'connected' })
    const close = [...host.querySelectorAll('button')].find((button) => button.textContent === 'Close Coding Round')

    await act(async () => close.click())

    expect(closeSubmissions).toHaveBeenCalledTimes(1)
    expect(host.textContent).toContain('Coding Round closed. Judging wait started.')
    expect(host.textContent).toContain('Open Coding Round')
  })

  it('coalesces timer, visibility, and reconnect refreshes into one in-flight GET', async () => {
    await render({ socketStatus: 'reconnecting' })
    getAdminSubmissions.mockClear()
    let resolveLoad
    getAdminSubmissions.mockImplementation(() => new Promise((resolve) => { resolveLoad = resolve }))
    await act(async () => vi.advanceTimersByTimeAsync(29_999))
    hidden = true
    hidden = false

    await act(async () => {
      vi.advanceTimersByTime(1)
      document.dispatchEvent(new Event('visibilitychange'))
      root.render(<CodingRoundAdminPage socketStatus="reconnected" />)
    })

    expect(getAdminSubmissions).toHaveBeenCalledTimes(1)
    await act(async () => resolveLoad(structuredClone(snapshot)))
  })
})
