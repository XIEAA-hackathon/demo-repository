import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Countdown from '../../participant/components/Countdown'
import { deriveServerRemaining } from './timerReconciliation'
import type { EventTiming } from '../../participant/types'

let host: HTMLDivElement
let root: Root
const now = Date.parse('2026-09-13T10:00:00Z')
const timing: EventTiming = { serverTime: new Date(now).toISOString(), receivedAt: now, startedAt: new Date(now).toISOString(), endsAt: new Date(now + 2000).toISOString(), paused: false, pausedRemainingSeconds: null }
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.useFakeTimers(); vi.setSystemTime(now)
  host = document.createElement('div'); root = createRoot(host)
})
afterEach(() => { act(() => root.unmount()); vi.useRealTimers() })
const render = (next?: EventTiming) => act(() => root.render(<Countdown seconds={60} timing={next} />))

it('keeps an authoritative timer-less preview at zero, then anchors a new bidding timer', () => {
  render(timing)
  expect(host.textContent).toBe('00:02')
  act(() => vi.advanceTimersByTime(2000))
  expect(host.textContent).toBe('00:00')
  render({ ...timing, endsAt: null, remainingSeconds: null })
  expect(host.textContent).toBe('00:00')
  render(undefined)
  expect(host.textContent).toBe('00:00')
  act(() => vi.advanceTimersByTime(5000))
  render({ ...timing, serverTime: new Date().toISOString(), receivedAt: Date.now(), endsAt: null, remainingSeconds: 60 })
  expect(host.textContent).toBe('00:00')
  render({ ...timing, serverTime: new Date().toISOString(), receivedAt: Date.now(), startedAt: new Date().toISOString(), endsAt: new Date(Date.now() + 10000).toISOString() })
  expect(host.textContent).toBe('00:10')
  act(() => vi.advanceTimersByTime(1000))
  expect(host.textContent).toBe('00:09')
})

it('projects zero immediately on visibility restore without waiting for a tick or HTTP', () => {
  render(timing)
  vi.setSystemTime(now + 5000)
  act(() => document.dispatchEvent(new Event('visibilitychange')))
  expect(host.textContent).toBe('00:00')
})

it('uses configured duration only before timing arrives and preserves pause semantics', () => {
  expect(deriveServerRemaining(undefined, now, 60)).toBe(60)
  expect(deriveServerRemaining({ ends_at: null, remaining_seconds: 60 }, now, 60)).toBe(0)
  expect(deriveServerRemaining({ paused: true, paused_remaining_seconds: null, remaining_seconds: 12 }, now, 60)).toBe(12)
  expect(deriveServerRemaining({ ends_at: null, endsAt: timing.endsAt }, now, 60)).toBe(0)
})
