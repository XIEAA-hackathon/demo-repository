import type {
  Bid, BidIncrement,
  Id,
  LeaderboardEntry,
  ParticipantDashboard,
  Problem,
  Submission,
  WildcardApplication,
  WildcardProblem,
} from '../types'

export interface ParticipantService {
  getParticipantDashboard(): Promise<ParticipantDashboard>
  getCurrentProblem(): Promise<Problem | WildcardProblem | null>
  getProblems(round: 1 | 2): Promise<WildcardProblem[]>
  placeBid(problemId: Id, increment: BidIncrement): Promise<Bid>
  getLeaderboard(round?: Bid['round']): Promise<LeaderboardEntry[]>
  applyForWildcard(): Promise<WildcardApplication>
  declineWildcard(): Promise<void>
  getWildcardProblems(): Promise<WildcardProblem[]>
  placeWildcardBid(increment: BidIncrement): Promise<number>
  selectWildcardProblem(problemId: Id): Promise<WildcardProblem>
  submitGitHubRepository(repositoryUrl: string): Promise<Submission>
}
