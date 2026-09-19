import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { WildcardControlPage } from './App'
import { getRoundControl } from './services/api'

vi.mock('./services/api', async (original) => ({ ...await original(), getRoundControl: vi.fn() }))

const snapshot = (status) => ({
  status,
  ended: status === 'COMPLETE',
  applications: { open: false, status: 'COMPLETE', applied: 2, declined: 1, pending: 0, eligible: 3 },
  slots: { count: 2, confirmed: true, maximum: 2 },
  bidding: { open: false, ranking: [] },
  selection: {
    current_rank: null, current_team_id: null, current_team: null, started_at: null, ends_at: null,
    duration_seconds: 30, remaining_seconds: 0, qualifications: [], available_problems: [], pool_frozen: false,
    pool_frozen_at: null, pool: [],
  },
  final_choice: { started_at: null, ends_at: null, duration_seconds: 60, confirmed: 1, pending: 1 },
  problems: [],
  settings: { wildcard_slots: 2 },
  event: { timing: { server_time: '2026-09-19T10:00:00Z', ends_at: null, remaining_seconds: 42 } },
})

let host
let root

describe('WildcardControlPage stages', () => {
  beforeEach(() => {
    Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
    vi.useFakeTimers()
    host = document.createElement('div')
    root = createRoot(host)
  })

  afterEach(() => {
    act(() => root.unmount())
    vi.useRealTimers()
  })

  it('shows exactly four Wildcard stages and activates Final choice', async () => {
    getRoundControl.mockResolvedValue(snapshot('FINAL_CHOICE'))
    await act(async () => root.render(<WildcardControlPage remaining={42} socketConnected />))

    const tabs = [...host.querySelectorAll('[role="tab"]')]
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      '1Application', '2Slot bidding', '3Problem selection', '4Final choice',
    ])
    expect(tabs.map((tab) => tab.getAttribute('aria-selected'))).toEqual(['false', 'false', 'false', 'true'])
    expect(host.textContent).toContain('1 confirmed · 1 pending')
    expect(host.textContent).toContain('Pending teams default to their Round 1 problem')
    expect(host.textContent).toContain('End final choice')
  })

  it('shows COMPLETE in the fourth stage instead of Problem selection', async () => {
    getRoundControl.mockResolvedValue(snapshot('COMPLETE'))
    await act(async () => root.render(<WildcardControlPage remaining={0} socketConnected />))

    const tabs = [...host.querySelectorAll('[role="tab"]')]
    expect(tabs[2].getAttribute('aria-selected')).toBe('false')
    expect(tabs[3].getAttribute('aria-selected')).toBe('true')
    expect(host.textContent).toContain('Wildcard complete')
    expect(host.textContent).toContain('Final choice complete')
  })
})
