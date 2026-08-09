import type { Id, ParticipantDashboard, Team, TeamMember } from './types'

/**
 * Frontend permission state is for UX only; the backend must enforce leader
 * authorization later. Leadership is a property of the team/member relationship.
 */

export interface ParticipantPermissions {
  isLeader: boolean
  canPlaceBid: boolean
  canPlaceWildcardBid: boolean
  canSelectWildcardProblem: boolean
  canSubmitRepository: boolean
}

export function getLeader(team: Team): TeamMember | null {
  return team.members.find((member) => member.isLeader) ?? null
}

export function isCurrentUserLeader(team: Team, currentUserId: Id): boolean {
  return team.leaderId === currentUserId
}

/**
 * Pure leader-selection transform. Verifies membership, clears any current
 * leader, and marks exactly one member as leader. All mutation flows through
 * this function so "exactly one leader" is guaranteed at the source of truth.
 */
export function applyLeaderSelection(team: Team, memberId: Id): Team {
  const member = team.members.find((item) => item.id === memberId)
  if (!member) throw new Error('Select a valid team member.')
  return {
    ...team,
    leaderId: memberId,
    members: team.members.map((item) => ({ ...item, isLeader: item.id === memberId })),
  }
}

export function getParticipantPermissions(dashboard: ParticipantDashboard): ParticipantPermissions {
  const isLeader = isCurrentUserLeader(dashboard.team, dashboard.currentUserId)
  return {
    isLeader,
    canPlaceBid: isLeader,
    canPlaceWildcardBid: isLeader,
    canSelectWildcardProblem: isLeader,
    canSubmitRepository: isLeader,
  }
}