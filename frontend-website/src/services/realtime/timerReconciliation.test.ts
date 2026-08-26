import { strict as assert } from 'node:assert'
import {
  deriveServerRemaining,
  isSyncStale,
  shouldApplyTimerSnapshot,
  type TimerTiming,
} from './timerReconciliation.ts'

const localNow = Date.parse('2026-08-26T10:00:00.000Z')
const timing: TimerTiming = {
  serverTime: '2026-08-26T10:00:00.000Z',
  receivedAt: localNow,
  startedAt: '2026-08-26T09:59:30.000Z',
  endsAt: '2026-08-26T10:01:00.000Z',
  paused: false,
}

assert.equal(deriveServerRemaining(timing, localNow), 60)
assert.equal(deriveServerRemaining(timing, localNow + 20_000), 40)

assert.equal(shouldApplyTimerSnapshot({
  previousTiming: timing,
  previousTimerKey: 'same-phase',
  nextTiming: { ...timing, serverTime: '2026-08-26T10:00:05.000Z', receivedAt: localNow + 5_000 },
  nextTimerKey: 'same-phase',
  expectedRemaining: 55,
  serverRemaining: 56,
}), false)

assert.equal(shouldApplyTimerSnapshot({
  previousTiming: timing,
  previousTimerKey: 'same-phase',
  nextTiming: { ...timing, endsAt: '2026-08-26T10:01:30.000Z' },
  nextTimerKey: 'same-phase',
  expectedRemaining: 55,
  serverRemaining: 85,
}), true)

assert.equal(shouldApplyTimerSnapshot({
  previousTiming: timing,
  previousTimerKey: 'same-phase',
  nextTiming: { ...timing, paused: true, pausedRemainingSeconds: 45 },
  nextTimerKey: 'same-phase',
  expectedRemaining: 45,
  serverRemaining: 45,
}), true)

assert.equal(isSyncStale({ documentHidden: true, refreshPending: false, staleSeconds: 45 }), false)
assert.equal(isSyncStale({ documentHidden: false, refreshPending: true, staleSeconds: 45 }), false)
assert.equal(isSyncStale({ documentHidden: false, refreshPending: false, staleSeconds: 16 }), true)

console.log('realtime timer reconciliation: all assertions passed')
