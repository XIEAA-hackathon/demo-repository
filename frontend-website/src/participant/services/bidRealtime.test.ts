import assert from 'node:assert/strict'

import { applyBidDelta, parseBidDelta } from './bidRealtime.ts'


const first = parseBidDelta({
  bid_id: 9,
  team_id: 3,
  team_name: 'Team Three',
  ps_id: 8,
  amount: 125,
  increment: 25,
  round: 'ROUND1',
  timestamp: '2026-08-31T10:00:00Z',
  cooldown_seconds: 5,
})
assert.ok(first)

const ranked = applyBidDelta([
  { rank: 1, teamId: '2', teamName: 'Team Two', amount: 125, placedAt: '2026-08-31T10:00:00Z' },
  { rank: 2, teamId: '3', teamName: 'Team Three', amount: 100, placedAt: '2026-08-31T09:59:00Z' },
], first)

assert.deepEqual(ranked.map(({ rank, teamId, amount }) => ({ rank, teamId, amount })), [
  { rank: 1, teamId: '2', amount: 125 },
  { rank: 2, teamId: '3', amount: 125 },
])

const updated = applyBidDelta(ranked, { ...first, amount: 150, placedAt: '2026-08-31T10:01:00Z' })
assert.deepEqual(updated.map(({ rank, teamId, amount }) => ({ rank, teamId, amount })), [
  { rank: 1, teamId: '3', amount: 150 },
  { rank: 2, teamId: '2', amount: 125 },
])

assert.equal(parseBidDelta({ round: 'ROUND1' }), null)
console.log('bid realtime delta ranking: all assertions passed')
