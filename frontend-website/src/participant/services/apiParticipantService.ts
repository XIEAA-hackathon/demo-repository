import { apiRequest } from './apiClient'
import type {
  Bid, LeaderboardEntry, ParticipantDashboard, ParticipantEventState, Problem,
  Submission, WildcardApplication, WildcardProblem,
} from '../types'
import type { ParticipantService } from './participantService'

interface RawDashboard {
  user: { id: number; name: string; email: string; role: string }
  team: { id: number; team_name: string; coins: number; leader_id: number; members: Array<{ id: number; member_name: string; email?: string; is_leader: boolean }> }
  eventState: ParticipantEventState
  wallet: { team_id: number; balance: number; currency: 'coins' }
  currentProblem: RawProblem | null
  currentBid: { id: number; team_id: number; ps_id: number; amount: number; round: number; timestamp: string } | null
  wildcard: { status?: string; coins_paid: number; used: boolean } | null
  submission: { id: number; problem_id: number; repository_url: string; submitted_at: string } | null
  isLeader: boolean
  gameConfig: {
    round1_winner_count: number; round1_preview_seconds: number; round1_bid_seconds: number
    wildcard_slots: number; wildcard_preview_seconds: number; wildcard_bid_seconds: number; coding_duration_seconds: number
  }
  timing: { server_time: string; started_at: string | null; ends_at: string | null; paused: boolean; paused_remaining_seconds: number | null }
}

interface RawProblem {
  id: number
  ps_number?: string
  number?: number
  title: string
  description?: string
  summary?: string
  startingBid?: number
  available?: boolean
}

const problemNumber = (problem: RawProblem) => problem.number ?? Number(problem.ps_number?.match(/\d+/)?.[0] || problem.id)
const mapProblem = (problem: RawProblem): Problem => ({
  id: String(problem.id), number: problemNumber(problem), title: problem.title,
  summary: problem.summary ?? problem.description ?? '', description: problem.description ?? problem.summary ?? '',
  startingBid: problem.startingBid ?? 0,
})

function mapDashboard(raw: RawDashboard): ParticipantDashboard {
  const latestBid: Bid | null = raw.currentBid ? {
    id: String(raw.currentBid.id), teamId: String(raw.currentBid.team_id), teamName: raw.team.team_name,
    problemId: String(raw.currentBid.ps_id), amount: raw.currentBid.amount, placedAt: raw.currentBid.timestamp,
    round: raw.currentBid.round === 2 ? 'WILDCARD' : 'ROUND1',
  } : null
  const currentProblem = raw.currentProblem ? mapProblem(raw.currentProblem) : null
  return {
    team: {
      id: String(raw.team.id), name: raw.team.team_name, leaderId: String(raw.team.leader_id),
      members: raw.team.members.map((member) => ({
        id: member.is_leader ? String(member.id) : `member-${member.id}`,
        name: member.member_name, email: member.email ?? '', isLeader: member.is_leader,
      })),
    },
    currentUserId: String(raw.user.id),
    currentUser: {
      id: String(raw.user.id), name: raw.user.name, loginId: raw.user.email,
      role: raw.isLeader ? 'leader' : 'member',
    },
    eventState: raw.eventState,
    wallet: { teamId: String(raw.wallet.team_id), balance: raw.wallet.balance, currency: 'coins' },
    currentProblem, latestBid,
    roundOneSettlement: raw.eventState === 'ROUND1_RESULT' ? {
      status: 'FINALIZED', won: Boolean(currentProblem), bidAmount: latestBid?.round === 'ROUND1' ? latestBid.amount : 0,
      finalizedAt: raw.timing.server_time,
    } : null,
    wildcardApplication: raw.wildcard ? {
      id: `wildcard-${raw.team.id}`, teamId: String(raw.team.id), appliedAt: raw.timing.server_time, status: 'CONFIRMED',
    } : null,
    submission: raw.submission ? {
      id: String(raw.submission.id), teamId: String(raw.team.id), problemId: String(raw.submission.problem_id),
      repositoryUrl: raw.submission.repository_url, submittedAt: raw.submission.submitted_at, status: 'SUBMITTED',
    } : null,
    isLeader: raw.isLeader,
    gameConfig: {
      round1WinnerCount: raw.gameConfig.round1_winner_count, round1PreviewSeconds: raw.gameConfig.round1_preview_seconds,
      round1BidSeconds: raw.gameConfig.round1_bid_seconds, wildcardSlots: raw.gameConfig.wildcard_slots,
      wildcardPreviewSeconds: raw.gameConfig.wildcard_preview_seconds, wildcardBidSeconds: raw.gameConfig.wildcard_bid_seconds,
      codingDurationSeconds: raw.gameConfig.coding_duration_seconds,
    },
    timing: {
      serverTime: raw.timing.server_time, receivedAt: Date.now(), startedAt: raw.timing.started_at, endsAt: raw.timing.ends_at,
      paused: raw.timing.paused, pausedRemainingSeconds: raw.timing.paused_remaining_seconds,
    },
  }
}

class ApiParticipantService implements ParticipantService {
  async getParticipantDashboard() { return mapDashboard(await apiRequest<RawDashboard>('/participant/dashboard')) }
  async getCurrentProblem() { return (await this.getParticipantDashboard()).currentProblem }
  async getProblems(round: 1 | 2) {
    const raw = await apiRequest<RawProblem[]>(`/participant/problems?round=${round}`)
    return raw.map((problem) => ({ ...mapProblem(problem), available: problem.available ?? true }))
  }
  async placeBid(problemId: string, amount: number) {
    await apiRequest('/bid', { method: 'POST', body: JSON.stringify({ ps_id: Number(problemId), amount }) })
    const bid = (await this.getParticipantDashboard()).latestBid
    if (!bid) throw new Error('The bid was accepted but could not be reloaded.')
    return bid
  }
  async getLeaderboard() {
    const rows = await apiRequest<Array<{ rank: number; team_id: number; team_name: string; bid_amount: number | null }>>('/participant/leaderboard')
    return rows.map<LeaderboardEntry>((row) => ({ rank: row.rank, teamId: String(row.team_id), teamName: row.team_name, amount: row.bid_amount ?? 0 }))
  }
  async applyForWildcard() {
    await apiRequest('/wildcard/apply', { method: 'POST' })
    const dashboard = await this.getParticipantDashboard()
    return dashboard.wildcardApplication as WildcardApplication
  }
  async getWildcardProblems() { return (await this.getProblems(2)) as WildcardProblem[] }
  async placeWildcardBid(problemId: string, amount: number) {
    await apiRequest(`/wildcard/bid?ps_id=${encodeURIComponent(problemId)}&amount=${amount}`, { method: 'POST' })
    const bid = (await this.getParticipantDashboard()).latestBid
    if (!bid) throw new Error('The wildcard bid was accepted but could not be reloaded.')
    return bid
  }
  async selectWildcardProblem(problemId: string) {
    await apiRequest(`/wildcard/select/${encodeURIComponent(problemId)}`, { method: 'POST' })
    const problem = (await this.getParticipantDashboard()).currentProblem
    if (!problem) throw new Error('The selected problem could not be reloaded.')
    return { ...problem, available: false }
  }
  async submitGitHubRepository(repositoryUrl: string) {
    const raw = await apiRequest<{ id: number; problem_id: number; repository_url: string; submitted_at: string }>('/submissions/me', {
      method: 'PUT', body: JSON.stringify({ repository_url: repositoryUrl.trim() }),
    })
    const dashboard = await this.getParticipantDashboard()
    return {
      id: String(raw.id), teamId: dashboard.team.id, problemId: String(raw.problem_id), repositoryUrl: raw.repository_url,
      submittedAt: raw.submitted_at, status: 'SUBMITTED',
    } as Submission
  }
}

export const participantService = new ApiParticipantService()
