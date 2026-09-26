import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Countdown from '../../participant/components/Countdown'
import { connectReconnectingSocket } from './connectReconnectingSocket'
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

it('caps an active clock-derived countdown at the authoritative snapshot value', () => {
  const endsAt = new Date(now + 30_000).toISOString()
  expect(deriveServerRemaining({ ends_at: endsAt, remaining_seconds: 30, clock_offset_ms: -2_000 }, now)).toBe(30)
  expect(deriveServerRemaining({ endsAt, remainingSeconds: 30, clockOffsetMs: 1_000 }, now)).toBe(29)
})

it('retains clock-derived behavior without an authoritative remaining value', () => {
  expect(deriveServerRemaining({ ends_at: new Date(now + 30_000).toISOString(), clock_offset_ms: -2_000 }, now)).toBe(32)
})

it('keeps paused precedence and rejects remaining seconds without a deadline', () => {
  expect(deriveServerRemaining({ paused: true, paused_remaining_seconds: 7, remaining_seconds: 9 }, now)).toBe(7)
  expect(deriveServerRemaining({ paused: true, paused_remaining_seconds: null, remaining_seconds: 9 }, now)).toBe(9)
  expect(deriveServerRemaining({ ends_at: null, remaining_seconds: 30, clock_offset_ms: -2_000 }, now)).toBe(0)
})

it('drops the previous connection clock sample when reconnecting', () => {
  const originalWebSocket = globalThis.WebSocket
  class MockWebSocket {
    static OPEN = 1
    static instances: MockWebSocket[] = []
    readyState = MockWebSocket.OPEN
    onopen: ((event: Event) => void) | null = null
    onmessage: ((event: MessageEvent) => void) | null = null
    onerror: ((event: Event) => void) | null = null
    onclose: ((event: CloseEvent) => void) | null = null
    constructor(readonly url: string) { MockWebSocket.instances.push(this) }
    send() {}
    close() {}
  }
  globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket
  type SocketMessage = { payload: { timing: Record<string, unknown> } }
  const messages: SocketMessage[] = []
  const disconnect = connectReconnectingSocket<SocketMessage>({
    url: 'ws://example.test/ws',
    getToken: () => 'token',
    onMessage: (message) => messages.push(message),
  })

  try {
    const first = MockWebSocket.instances[0]
    vi.setSystemTime(now + 100)
    first.onmessage?.({ data: JSON.stringify({ type: 'session_heartbeat', server_time: new Date(now + 150).toISOString(), payload: { client_time: now } }) } as MessageEvent)
    first.onmessage?.({ data: JSON.stringify({ type: 'event_snapshot', payload: { timing: {} } }) } as MessageEvent)
    expect(messages[messages.length - 1]?.payload.timing.clock_offset_ms).toBe(100)

    first.onclose?.({ code: 1006, reason: '', wasClean: false } as CloseEvent)
    vi.advanceTimersByTime(2_000)
    const second = MockWebSocket.instances[1]
    expect(second).toBeDefined()
    second.onmessage?.({ data: JSON.stringify({ type: 'event_snapshot', payload: { timing: {} } }) } as MessageEvent)
    expect(messages[messages.length - 1]?.payload.timing.clock_offset_ms).toBeUndefined()
  } finally {
    disconnect()
    globalThis.WebSocket = originalWebSocket
  }
})
