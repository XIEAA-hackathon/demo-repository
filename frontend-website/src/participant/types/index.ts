export type Id = string

export const participantEventStates = [
  'WAITING',
  'ROUND1_PREVIEW',
  'ROUND1_BIDDING',
  'ROUND1_RESULT',
  'WILDCARD_APPLICATION',
  'WILDCARD_BIDDING',
  'WILDCARD_SELECTION',
  'CODING',
  'SUBMISSION',
  'JUDGING_WAIT',
  'RESULTS',
] as const

export type ParticipantEventState = (typeof participantEventStates)[number]
export type EventState = ParticipantEventState

export interface TeamMember {
  id: Id
  name: string
  email: string
  isLeader: boolean
}

export interface Team {
  id: Id
  name: string
  members: TeamMember[]
  leaderId: Id | null
}

export interface Problem {
  id: Id
  number: number
  title: string
  summary: string
  description: string
  startingBid: number
}

export interface Bid {
  id: Id
  teamId: Id
  teamName: string
  problemId: Id
  amount: number
  placedAt: string
  round: 'ROUND1' | 'WILDCARD'
}

export interface Wallet {
  teamId: Id
  balance: number
  currency: 'coins'
}

export interface Submission {
  id: Id
  teamId: Id
  problemId: Id
  repositoryUrl: string
  submittedAt: string
  updatedAt: string | null
  submittedByName: string | null
  status: 'SUBMITTED'
}

export interface WildcardApplication {
  id: Id
  teamId: Id
  appliedAt: string
  status: 'CONFIRMED'
}

export interface WildcardProblem extends Problem {
  available: boolean
}

export interface WildcardState {
  status: 'applied' | 'declined' | 'qualified' | 'selected' | 'eliminated' | string
  rank: number | null
  winningBid: number | null
  selectedProblemId: Id | null
  selectionMethod: 'manual' | 'timeout' | 'admin_end_turn' | null
  currentSelectionRank: number | null
  currentSelectionTeam: string | null
  isSelectionTurn: boolean
  availableProblemCount: number
  slotCount: number | null
  selectionStartedAt: string | null
  selectionEndsAt: string | null
  selectionDurationSeconds: number | null
  selectionRemainingSeconds: number | null
}

export interface LeaderboardEntry {
  rank: number
  teamId: Id
  teamName: string
  amount: number
}

export interface RoundOneSettlement {
  status: 'PROVISIONAL' | 'FINALIZED'
  won: boolean
  bidAmount: number
  finalizedAt: string | null
}

export interface FinalWinner {
  teamId: Id
  teamName: string
}

export interface FinalResults {
  firstPlace: FinalWinner
  secondPlace: FinalWinner
  thirdPlace: FinalWinner
}

export interface ParticipantDashboard {
  team: Team
  currentUserId: Id
  currentUser: {
    id: Id
    name: string
    loginId: string
    role: 'leader' | 'member'
  }
  eventState: ParticipantEventState
  wallet: Wallet
  currentProblem: Problem | WildcardProblem | null
  roundOneProblem: Problem | null
  wildcardProblem: WildcardProblem | null
  finalProblem: Problem | WildcardProblem | null
  latestBid: Bid | null
  wildcardBidAmount: number | null
  roundOneSettlement: RoundOneSettlement | null
  wildcardApplication: WildcardApplication | null
  wildcard: WildcardState | null
  submission: Submission | null
  finalResults: FinalResults | null
  bidCooldownRemainingSeconds: number
  isLeader: boolean
  round1Assigned: boolean
  round1AssignmentType: 'BID_WINNER' | 'AUTO_FINAL_PROBLEM' | null
  round1AssignmentCost: number | null
  wildcardEligible: boolean
  wildcardApplicationsOpen: boolean
  submissionsOpen: boolean
  gameConfig: {
    startingCoins: number
    round1WinnerCount: number
    round1BaseBidPrice: number
    round1BidIncrement: number
    round1PreviewSeconds: number
    round1BidSeconds: number
    wildcardSlots: number
    wildcardBaseBidPrice: number
    wildcardBidIncrement: number
    wildcardApplicationSeconds: number
    wildcardPreviewSeconds: number
    wildcardBidSeconds: number
    wildcardSelectionSeconds: number
    codingDurationSeconds: number
    bidCooldownSeconds: number
  }
  timing: EventTiming
}

export interface EventTiming {
  serverTime: string
  receivedAt: number
  startedAt: string | null
  endsAt: string | null
  paused: boolean
  pausedRemainingSeconds: number | null
}

export type BidIncrement = 5 | 10 | 25
