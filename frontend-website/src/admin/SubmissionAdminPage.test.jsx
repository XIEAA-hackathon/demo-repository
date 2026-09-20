import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CodingRoundAdminPage } from './App'
import { getAdminSubmissions, openSubmissions, updateAdminConfig } from './services/api'

vi.mock('./services/api', async (original) => ({
  ...await original(),
  getAdminSubmissions: vi.fn(),
  openSubmissions: vi.fn(),
  updateAdminConfig: vi.fn(),
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
    updateAdminConfig.mockImplementation(async (update) => ({ ...update }))
    host = document.createElement('div')
    root = createRoot(host)
  })

  afterEach(() => {
    act(() => root.unmount())
    vi.useRealTimers()
  })

  it('loads once initially and reconciles connected sockets at 60 seconds', async () => {
    await render({ socketStatus: 'connected' })
    expect(getAdminSubmissions).toHaveBeenCalledTimes(1)
    expect(host.textContent).toContain('CODING TIMER SETTINGS')
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

  it.each([
    ['1', 3600],
    ['2', 7200],
    ['3.5', 12600],
    ['4', 14400],
  ])('saves %s Coding hours as %i seconds only', async (hours, seconds) => {
    getAdminSubmissions.mockResolvedValue({ ...structuredClone(snapshot), open: false })
    const onConfig = vi.fn()
    await render({
      socketStatus: 'connected',
      state: { rounds: { WILDCARD: { status: 'COMPLETE', ended: true } } },
      config: { coding_duration_seconds: 10800, round1_bid_seconds: 99 },
      onConfig,
    })

    expect(host.textContent).toContain('Open Coding Round')
    expect(host.textContent).toContain('Coding duration (hours)')
    const input = host.querySelector('input[type="number"]')
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
      setter?.call(input, hours)
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(onConfig).not.toHaveBeenCalled()
    const save = [...host.querySelectorAll('button')].find((button) => button.textContent === 'Save duration')
    await act(async () => save.click())
    expect(updateAdminConfig).toHaveBeenCalledWith({ coding_duration_seconds: seconds })
    expect(onConfig).toHaveBeenCalledWith({ coding_duration_seconds: seconds })
  })

  it('preserves a dirty local duration across background config refreshes', async () => {
    getAdminSubmissions.mockResolvedValue({ ...structuredClone(snapshot), open: false })
    const props = {
      socketStatus: 'connected',
      state: { rounds: { WILDCARD: { status: 'COMPLETE', ended: true } } },
      config: { coding_duration_seconds: 10800 },
    }
    await render(props)
    const input = host.querySelector('input[type="number"]')
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
      setter?.call(input, '4')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })

    await render({ ...props, config: { coding_duration_seconds: 7200 } })

    expect(host.querySelector('input[type="number"]').value).toBe('4')
  })

  it('saves the visible duration before opening Coding and refreshes authoritative state', async () => {
    getAdminSubmissions.mockResolvedValue({ ...structuredClone(snapshot), open: false })
    const onConfig = vi.fn()
    const onGlobalSync = vi.fn().mockResolvedValue(true)
    await render({
      socketStatus: 'connected',
      state: { rounds: { WILDCARD: { status: 'COMPLETE', ended: true } } },
      config: { coding_duration_seconds: 10800 },
      onConfig,
      onGlobalSync,
    })
    const input = host.querySelector('input[type="number"]')
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
      setter?.call(input, '4')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    const open = [...host.querySelectorAll('button')].find((button) => button.textContent === 'Open Coding Round')

    await act(async () => open.click())

    expect(updateAdminConfig).toHaveBeenCalledWith({ coding_duration_seconds: 14400 })
    expect(openSubmissions).toHaveBeenCalledTimes(1)
    expect(updateAdminConfig.mock.invocationCallOrder[0]).toBeLessThan(openSubmissions.mock.invocationCallOrder[0])
    expect(onConfig).toHaveBeenCalledWith({ coding_duration_seconds: 14400 })
    expect(onGlobalSync).toHaveBeenCalledTimes(1)
    expect(host.textContent).toContain('Coding Round opened.')
  })

  it('does not call either API when the Coding duration is invalid', async () => {
    getAdminSubmissions.mockResolvedValue({ ...structuredClone(snapshot), open: false })
    await render({
      socketStatus: 'connected',
      state: { rounds: { WILDCARD: { status: 'COMPLETE', ended: true } } },
      config: { coding_duration_seconds: 10800 },
    })
    const input = host.querySelector('input[type="number"]')
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
      setter?.call(input, '')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    const open = [...host.querySelectorAll('button')].find((button) => button.textContent === 'Open Coding Round')

    await act(async () => open.click())

    expect(updateAdminConfig).not.toHaveBeenCalled()
    expect(openSubmissions).not.toHaveBeenCalled()
    expect(host.textContent).toContain('Enter a Coding duration of at least 0.25 hours.')
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
