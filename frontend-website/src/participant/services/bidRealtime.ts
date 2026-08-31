import type { Bid, BidIncrement, Id, LeaderboardEntry } from '../types'

export interface BidDelta {
  bidId: Id
  teamId: Id
  teamName: string
  problemId: Id | null
  amount: number
  increment: BidIncrement
  round: Bid['round']
  placedAt: string
  cooldownSeconds: number
}

const teamOrder = (left: Id, right: Id) => {
  const leftNumber = Number(left)
  const rightNumber = Number(right)
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) return leftNumber - rightNumber
  return left.localeCompare(right)
}

export function applyBidDelta(entries: LeaderboardEntry[], delta: BidDelta): LeaderboardEntry[] {
  const changed: LeaderboardEntry = {
    rank: 0,
    teamId: delta.teamId,
    teamName: delta.teamName,
    amount: delta.amount,
    placedAt: delta.placedAt,
  }
  return [...entries.filter((entry) => entry.teamId !== delta.teamId), changed]
    .sort((left, right) => {
      if (left.amount !== right.amount) return right.amount - left.amount
      const leftTime = left.placedAt ? Date.parse(left.placedAt) : Number.POSITIVE_INFINITY
      const rightTime = right.placedAt ? Date.parse(right.placedAt) : Number.POSITIVE_INFINITY
      if (leftTime !== rightTime) return leftTime - rightTime
      return teamOrder(left.teamId, right.teamId)
    })
    .map((entry, index) => ({ ...entry, rank: index + 1 }))
}

export function parseBidDelta(payload: Record<string, unknown>): BidDelta | null {
  const round = payload.round
  const teamId = payload.team_id
  const amount = Number(payload.amount)
  const increment = Number(payload.increment)
  const cooldownSeconds = Number(payload.cooldown_seconds ?? 0)
  const placedAt = payload.timestamp
  if (
    (round !== 'ROUND1' && round !== 'WILDCARD')
    || (typeof teamId !== 'string' && typeof teamId !== 'number')
    || (typeof payload.bid_id !== 'string' && typeof payload.bid_id !== 'number')
    || !Number.isFinite(amount)
    || ![5, 10, 25].includes(increment)
    || !Number.isFinite(cooldownSeconds)
    || typeof placedAt !== 'string'
  ) return null

  return {
    bidId: String(payload.bid_id),
    teamId: String(teamId),
    teamName: String(payload.team_name ?? ''),
    problemId: payload.ps_id == null ? null : String(payload.ps_id),
    amount,
    increment: increment as BidIncrement,
    round,
    placedAt,
    cooldownSeconds,
  }
}

export const jitterMilliseconds = (minimum: number, maximum: number): number => (
  Math.round(minimum + Math.random() * (maximum - minimum))
)
