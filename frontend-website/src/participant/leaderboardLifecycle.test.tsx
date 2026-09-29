import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import BiddingPanel from './components/BiddingPanel'
import WildcardBiddingPage from './pages/WildcardBiddingPage'
import FinalizedLeaderboard from './components/FinalizedLeaderboard'
import { applyBidDelta, parseBidDelta } from './services/bidRealtime'

const mock = vi.hoisted(() => ({ context: null as any }))
vi.mock('./ParticipantContext', () => ({ useParticipant: () => mock.context }))
vi.mock('./components/AdvanceButton', () => ({ default: () => null }))
const rows = () => Array.from({ length: 12 }, (_, i) => ({ rank: i + 1, teamId: String(i + 1), teamName: `Team ${i + 1}`, amount: 1200 - i * 10, placedAt: `2026-09-29T10:00:${String(i).padStart(2, '0')}Z` }))
const bid = (round: string, ps = 10) => ({ round, ps_id: round === 'ROUND1' ? ps : null, team_id: 12, team_name: 'Outside team', bid_id: 12, amount: 2000, increment: 1, timestamp: '2026-09-29T10:01:00Z' })
const problem = { id: '10', number: 4, title: 'Current problem', description: 'Description', summary: '', startingBid: 100 }
let host: HTMLDivElement
let root: ReturnType<typeof createRoot>
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); vi.useFakeTimers()
  mock.context = { dashboard: { team: { id: '12', leaderId: '1' }, currentUserId: '1', wallet: { balance: 5000 }, timing: { endsAt: new Date(Date.now() + 60000).toISOString() },
    eventState: 'ROUND1_BIDDING', wildcardApplication: true, wildcard: { status: 'applied', slotCount: 5 }, gameConfig: { startingCoins: 5000, wildcardBaseBidPrice: 100, wildcardSlots: 5 } },
    service: { getLeaderboard: vi.fn().mockResolvedValue(rows()) }, recordAcceptedBid: vi.fn(), realtimeEvent: null, socketStatus: 'connected' }
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(() => { act(() => root.unmount()); host.remove(); vi.useRealTimers() })
const renderBid = (round: string, id = '10') => round === 'ROUND1' ? <BiddingPanel problem={{ ...problem, id }} round="ROUND1" /> : <WildcardBiddingPage />
it.each(['ROUND1', 'WILDCARD'])('limits participant %s to ten and inserts outside bidders immediately', async round => {
  mock.context.dashboard.eventState = `${round}_BIDDING`
  await act(async () => root.render(renderBid(round)))
  await act(async () => vi.advanceTimersByTimeAsync(0))
  expect(host.querySelectorAll('.leaderboard__body li')).toHaveLength(10)
  expect(host.textContent).not.toContain('YOU')
  mock.context.realtimeEvent = { type: round === 'ROUND1' ? 'bid_updated' : 'wildcard_bid_updated', payload: bid(round) }
  await act(async () => root.render(renderBid(round)))
  expect(host.querySelectorAll('.leaderboard__body li')).toHaveLength(10)
  expect(host.querySelector('.leaderboard__body li')?.textContent).toContain('Outside team')
  expect(mock.context.service.getLeaderboard).toHaveBeenCalledTimes(1)
})
it('clears participant bids for a new R1 problem and rejects old-problem deltas', async () => {
  await act(async () => root.render(renderBid('ROUND1')))
  await act(async () => vi.advanceTimersByTimeAsync(0))
  mock.context.service.getLeaderboard.mockResolvedValue([{ rank: 1, teamId: '20', teamName: 'Next team', amount: 100, placedAt: null }])
  mock.context.realtimeEvent = { type: 'bid_updated', payload: bid('ROUND1', 10) }
  await act(async () => root.render(renderBid('ROUND1', '20')))
  await act(async () => vi.advanceTimersByTimeAsync(0))
  expect(host.textContent).toContain('Next team'); expect(host.textContent).not.toContain('Outside team')
  expect(mock.context.service.getLeaderboard).toHaveBeenLastCalledWith('ROUND1', '20')
})
it('uses complete persisted R1 winner events without an extra read and ignores live deltas', async () => {
  mock.context.service.getLeaderboard.mockResolvedValue([])
  await act(async () => root.render(<FinalizedLeaderboard round="ROUND1" />))
  mock.context.realtimeEvent = { type: 'round_updated', payload: { action: 'winners_assigned', problem: { number: 4 }, winners: [{ team_id: 2, team_name: 'Actual winner', amount: 1100 }] } }
  await act(async () => root.render(<FinalizedLeaderboard round="ROUND1" />))
  expect(host.textContent).toContain('Actual winner'); expect(host.textContent).toContain('WINNER')
  mock.context.realtimeEvent = { type: 'bid_updated', payload: bid('ROUND1') }
  await act(async () => root.render(<FinalizedLeaderboard round="ROUND1" />))
  expect(host.textContent).not.toContain('Outside team')
  expect(mock.context.service.getLeaderboard).toHaveBeenCalledTimes(1)
})
it('shows ten finalized Wildcard rows with backend qualification flags', async () => {
  mock.context.service.getLeaderboard.mockResolvedValue(rows().map(row => ({ ...row, finalized: true, qualified: row.rank <= 3 })))
  await act(async () => root.render(<FinalizedLeaderboard round="WILDCARD" />))
  expect(host.querySelectorAll('li')).toHaveLength(10)
  expect([...host.querySelectorAll('li')].filter(row => !row.textContent?.includes('NOT QUALIFIED'))).toHaveLength(3)
})
it('keeps timestamp then team-ID tie order in the shared Top 10 reducer', () => {
  const entries = rows().map(row => ({ ...row, amount: 100, placedAt: '2026-09-29T10:00:00Z' })).reverse()
  const parsed = parseBidDelta({ ...bid('ROUND1'), team_id: 20, amount: 100, timestamp: '2026-09-29T09:00:00Z' })!
  expect(applyBidDelta(entries, parsed).map(row => row.teamId)).toEqual(['20', '1', '2', '3', '4', '5', '6', '7', '8', '9'])
})
it('renders a complete winner event on mount without requesting the live leaderboard', async () => {
  mock.context.realtimeEvent = { type: 'round_updated', payload: { action: 'winners_assigned', problem: { number: 4 }, winners: [{ team_id: 2, team_name: 'Committed winner', amount: 1100 }] } }
  await act(async () => root.render(<FinalizedLeaderboard round="ROUND1" />))
  expect(host.textContent).toContain('Committed winner')
  expect(mock.context.service.getLeaderboard).not.toHaveBeenCalled()
})
it('rejects an in-flight live snapshot when Wildcard finalization arrives', async () => {
  let resolve!: (value: any) => void
  mock.context.service.getLeaderboard.mockImplementationOnce(() => new Promise(done => { resolve = done }))
    .mockResolvedValue(rows().slice(0, 10).map(row => ({ ...row, finalized: true, qualified: row.rank <= 3 })))
  await act(async () => root.render(<FinalizedLeaderboard round="WILDCARD" />))
  mock.context.realtimeEvent = { type: 'wildcard_updated', payload: { action: 'bidding_finalized' } }
  await act(async () => root.render(<FinalizedLeaderboard round="WILDCARD" />))
  await act(async () => resolve(rows()))
  expect(host.querySelectorAll('li')).toHaveLength(10)
  expect(host.textContent).toContain('NOT QUALIFIED')
  expect(mock.context.service.getLeaderboard).toHaveBeenCalledTimes(2)
})
