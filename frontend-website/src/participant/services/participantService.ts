import type {
  AcceptedBid, Bid, BidIncrement,
  Id,
  LeaderboardEntry,
  ParticipantDashboard,
  Problem,
  WildcardProblem,
} from '../types'

export interface ParticipantService {
  getParticipantDashboard(): Promise<ParticipantDashboard>
  getCurrentProblem(): Promise<Problem | WildcardProblem | null>
  getProblems(round: 1 | 2): Promise<WildcardProblem[]>
  placeBid(problemId: Id, increment: BidIncrement): Promise<AcceptedBid>
  getLeaderboard(round?: Bid['round']): Promise<LeaderboardEntry[]>
  applyForWildcard(): Promise<void>
  declineWildcard(): Promise<void>
  getWildcardProblems(): Promise<WildcardProblem[]>
  placeWildcardBid(increment: BidIncrement): Promise<AcceptedBid>
  selectWildcardProblem(problemId: Id): Promise<void>
  confirmFinalProblem(choice: 'ROUND1' | 'WILDCARD'): Promise<void>
  submitGitHubRepository(repositoryUrl: string): Promise<void>
}
