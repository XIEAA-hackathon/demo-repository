import { apiRequest } from './apiClient'
import type {
  Bid, BidIncrement, LeaderboardEntry, ParticipantDashboard, ParticipantEventState, Problem,
  Submission, WildcardApplication, WildcardProblem,
} from '../types'
import type { ParticipantService } from './participantService'

interface RawDashboard {
  user: { id: number; name: string; email: string; role: string }
  team: { id: number; team_name: string; coins: number; leader_id: number; members: Array<{ id: number; member_name: string; email?: string; is_leader: boolean }> }
  eventState: ParticipantEventState
  wallet: { team_id: number; balance: number; currency: 'coins' }
  currentProblem: RawProblem | null
  round1Problem: RawProblem | null
  wildcardProblem: RawProblem | null
  finalProblem: RawProblem | null
  currentBid: { id: number; team_id: number; ps_id: number; amount: number; round: number; timestamp: string } | null
  wildcardBidAmount: number | null
  wildcard: { status: string; rank: number | null; winning_bid: number | null; problem_id: number | null; selection_method: 'manual' | 'timeout' | 'admin_end_turn' | null; current_selection_rank: number | null; current_selection_team: string | null; is_selection_turn: boolean; available_problem_count: number; slot_count: number | null; selection_started_at: string | null; selection_ends_at: string | null; selection_duration_seconds: number | null; selection_remaining_seconds: number | null } | null
  submission: { id: number; problem_id: number; repository_url: string; submitted_at: string; updated_at: string | null; submitted_by_name: string | null } | null
  finalResults: { first_place: RawWinner; second_place: RawWinner; third_place: RawWinner } | null
  bidCooldownRemainingSeconds: number
  isLeader: boolean
  round1Assigned: boolean
  round1AssignmentType: 'BID_WINNER' | 'MANUAL_ASSIGNMENT' | null
  round1AssignmentCost: number | null
  wildcardEligible: boolean
  wildcardApplicationsOpen: boolean
  submissionsOpen: boolean
  gameConfig: {
    starting_coins: number; round1_winner_count: number; round1_minimum_bid: number; round1_bid_increment: number; round1_preview_seconds: number; round1_bid_seconds: number
    wildcard_slots: number; wildcard_application_seconds: number; wildcard_starting_bid: number; wildcard_bid_increment: number; wildcard_preview_seconds: number; wildcard_bid_seconds: number; wildcard_selection_seconds: number; coding_duration_seconds: number
    bid_cooldown_seconds: number
  }
  timing: { server_time: string; started_at: string | null; ends_at: string | null; paused: boolean; paused_remaining_seconds: number | null }
}

interface RawWinner {
  team_id: number
  team_name: string
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
  const roundOneProblem = raw.round1Problem ? mapProblem(raw.round1Problem) : null
  const wildcardProblem = raw.wildcardProblem ? { ...mapProblem(raw.wildcardProblem), available: false } : null
  const finalProblem = raw.finalProblem ? mapProblem(raw.finalProblem) : null
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
    currentProblem, roundOneProblem, wildcardProblem, finalProblem, latestBid, wildcardBidAmount: raw.wildcardBidAmount,
    roundOneSettlement: raw.eventState === 'ROUND1_RESULT' ? {
      status: 'FINALIZED', won: Boolean(roundOneProblem), bidAmount: latestBid?.round === 'ROUND1' ? latestBid.amount : 0,
      finalizedAt: raw.timing.server_time,
    } : null,
    wildcardApplication: raw.wildcard && ['applied', 'qualified', 'selected', 'eliminated'].includes(raw.wildcard.status) ? {
      id: `wildcard-${raw.team.id}`, teamId: String(raw.team.id), appliedAt: raw.timing.server_time, status: 'CONFIRMED',
    } : null,
    wildcard: raw.wildcard ? {
      status: raw.wildcard.status, rank: raw.wildcard.rank, winningBid: raw.wildcard.winning_bid,
      selectedProblemId: raw.wildcard.problem_id == null ? null : String(raw.wildcard.problem_id),
      selectionMethod: raw.wildcard.selection_method,
      currentSelectionRank: raw.wildcard.current_selection_rank, currentSelectionTeam: raw.wildcard.current_selection_team,
      isSelectionTurn: raw.wildcard.is_selection_turn, availableProblemCount: raw.wildcard.available_problem_count,
      slotCount: raw.wildcard.slot_count,
      selectionStartedAt: raw.wildcard.selection_started_at,
      selectionEndsAt: raw.wildcard.selection_ends_at,
      selectionDurationSeconds: raw.wildcard.selection_duration_seconds,
      selectionRemainingSeconds: raw.wildcard.selection_remaining_seconds,
    } : null,
    submission: raw.submission ? {
      id: String(raw.submission.id), teamId: String(raw.team.id), problemId: String(raw.submission.problem_id),
      repositoryUrl: raw.submission.repository_url, submittedAt: raw.submission.submitted_at,
      updatedAt: raw.submission.updated_at, submittedByName: raw.submission.submitted_by_name, status: 'SUBMITTED',
    } : null,
    finalResults: raw.finalResults ? {
      firstPlace: { teamId: String(raw.finalResults.first_place.team_id), teamName: raw.finalResults.first_place.team_name },
      secondPlace: { teamId: String(raw.finalResults.second_place.team_id), teamName: raw.finalResults.second_place.team_name },
      thirdPlace: { teamId: String(raw.finalResults.third_place.team_id), teamName: raw.finalResults.third_place.team_name },
    } : null,
    bidCooldownRemainingSeconds: raw.bidCooldownRemainingSeconds,
    isLeader: raw.isLeader,
    round1Assigned: raw.round1Assigned,
    round1AssignmentType: raw.round1AssignmentType,
    round1AssignmentCost: raw.round1AssignmentCost,
    wildcardEligible: raw.wildcardEligible,
    wildcardApplicationsOpen: raw.wildcardApplicationsOpen,
    submissionsOpen: raw.submissionsOpen,
    gameConfig: {
      startingCoins: raw.gameConfig.starting_coins,
      round1WinnerCount: raw.gameConfig.round1_winner_count, round1BaseBidPrice: raw.gameConfig.round1_minimum_bid,
      round1BidIncrement: raw.gameConfig.round1_bid_increment,
      round1PreviewSeconds: raw.gameConfig.round1_preview_seconds,
      round1BidSeconds: raw.gameConfig.round1_bid_seconds, wildcardSlots: raw.gameConfig.wildcard_slots,
      wildcardBaseBidPrice: raw.gameConfig.wildcard_starting_bid, wildcardBidIncrement: raw.gameConfig.wildcard_bid_increment,
      wildcardApplicationSeconds: raw.gameConfig.wildcard_application_seconds,
      wildcardPreviewSeconds: raw.gameConfig.wildcard_preview_seconds, wildcardBidSeconds: raw.gameConfig.wildcard_bid_seconds,
      wildcardSelectionSeconds: raw.gameConfig.wildcard_selection_seconds,
      codingDurationSeconds: raw.gameConfig.coding_duration_seconds,
      bidCooldownSeconds: raw.gameConfig.bid_cooldown_seconds,
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
  async placeBid(problemId: string, increment: BidIncrement) {
    const result = await apiRequest<{ amount: number }>('/bid', { method: 'POST', body: JSON.stringify({ ps_id: Number(problemId), increment }) })
    return result.amount
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
  async declineWildcard() { await apiRequest('/wildcard/decline', { method: 'POST' }) }
  async getWildcardProblems() { return (await this.getProblems(2)) as WildcardProblem[] }
  async placeWildcardBid(increment: BidIncrement) {
    const result = await apiRequest<{ amount: number }>('/wildcard/bid', { method: 'POST', body: JSON.stringify({ increment }) })
    return result.amount
  }
  async selectWildcardProblem(problemId: string) {
    await apiRequest(`/wildcard/select/${encodeURIComponent(problemId)}`, { method: 'POST' })
    const problem = (await this.getParticipantDashboard()).currentProblem
    if (!problem) throw new Error('The selected problem could not be reloaded.')
    return { ...problem, available: false }
  }
  async submitGitHubRepository(repositoryUrl: string) {
    const raw = await apiRequest<{ id: number; problem_id: number; repository_url: string; submitted_at: string; updated_at: string | null; submitted_by_name: string | null }>('/submissions/me', {
      method: 'PUT', body: JSON.stringify({ repository_url: repositoryUrl.trim() }),
    })
    const dashboard = await this.getParticipantDashboard()
    return {
      id: String(raw.id), teamId: dashboard.team.id, problemId: String(raw.problem_id), repositoryUrl: raw.repository_url,
      submittedAt: raw.submitted_at, updatedAt: raw.updated_at, submittedByName: raw.submitted_by_name ?? dashboard.currentUser.name, status: 'SUBMITTED',
    } as Submission
  }
}

export const participantService = new ApiParticipantService()
