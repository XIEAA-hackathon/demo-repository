import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import BidIncrementForm from './BidIncrementForm'
import { ApiError } from '../services/apiClient'
import { parseBidDelta } from '../services/bidRealtime'
import type { AcceptedBid } from '../types'

let container: HTMLDivElement
let root: Root
const accepted: AcceptedBid = { bidId: '1', problemId: '1', amount: 205, increment: 15, round: 'ROUND1', placedAt: new Date().toISOString(), serverTime: new Date().toISOString(), cooldownSeconds: 5 }
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})
afterEach(() => { act(() => root.unmount()); container.remove(); vi.useRealTimers() })

function render(onBid = vi.fn().mockResolvedValue(accepted), overrides = {}) {
  act(() => root.render(<BidIncrementForm currentPrice={180} balance={900} startingCoins={5000} disabled={false} cooldownRemaining={0} onBid={onBid} {...overrides} />))
  return onBid
}
function type(value: string) {
  const input = container.querySelector('input')!
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
const button = () => container.querySelector('button')!
const submit = () => container.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))

describe('integer bid input', () => {
  it.each(['0', '-1', '-25', '26', '100', '1.5', '10.2', 'abc', '', '1e1'])('rejects %s without posting', async (value) => {
    const onBid = render()
    type(value)
    expect(button().disabled).toBe(true)
    await act(async () => { submit() })
    expect(onBid).not.toHaveBeenCalled()
  })
  it.each(['1', '2', '5', '10', '17', '25'])('accepts %s', (value) => {
    render(); type(value); expect(button().disabled).toBe(false)
  })
  it('posts only the increment once, displays authoritative acceptance, and allows editing during cooldown', async () => {
    vi.useFakeTimers()
    let resolve!: (value: AcceptedBid) => void
    const onBid = render(vi.fn(() => new Promise<AcceptedBid>((done) => { resolve = done })))
    type('15')
    expect(container.textContent).toContain('195 coins')
    expect(container.textContent).toContain('705 coins')
    act(() => { button().click(); submit(); submit() })
    expect(onBid).toHaveBeenCalledTimes(1)
    expect(onBid).toHaveBeenCalledWith(15)
    await act(async () => { resolve(accepted) })
    expect(container.textContent).toContain('Bid accepted at 205 coins')
    expect(container.querySelector('input')!.value).toBe('')
    type('17')
    expect(container.querySelector('input')!.value).toBe('17')
    expect(button().disabled).toBe(true)
    act(() => vi.advanceTimersByTime(5000))
    expect(button().disabled).toBe(false)
  })
  it('honors a server cooldown rejection', async () => {
    vi.useFakeTimers()
    render(vi.fn().mockRejectedValue(new ApiError('Bid cooldown active.', 429, 4)))
    type('1')
    await act(async () => { submit() })
    expect(container.textContent).toContain('Next bid available in 4s')
    expect(button().disabled).toBe(true)
    act(() => vi.advanceTimersByTime(4000))
    expect(button().disabled).toBe(false)
  })
  it('prevents unaffordable and unauthorized bids', async () => {
    const onBid = render(undefined, { balance: 180 })
    type('1')
    await act(async () => { submit() })
    expect(onBid).not.toHaveBeenCalled()
    render(onBid, { disabled: true })
    await act(async () => { submit() })
    expect(onBid).not.toHaveBeenCalled()
  })
  it('accepts typed increments in realtime deltas', () => {
    expect(parseBidDelta({ round: 'ROUND1', team_id: 1, bid_id: 1, amount: 117, increment: 17, timestamp: new Date().toISOString() })?.increment).toBe(17)
  })
})
