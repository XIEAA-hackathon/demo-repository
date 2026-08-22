import { strict as assert } from 'node:assert'
import { applyLeaderSelection, getLeader, getParticipantPermissions } from './permissions.ts'
import type { ParticipantDashboard, Team, TeamMember } from './types.ts'

const aarav: TeamMember = { id: 'A', name: 'Aarav', email: '', isLeader: false }
const riya: TeamMember = { id: 'B', name: 'Riya', email: '', isLeader: false }
const emptyTeam: Team = { id: 'team', name: 'Team Phoenix', members: [aarav, riya], leaderId: null }

function dashboard(team: Team, currentUserId: string): ParticipantDashboard {
  return {
    team,
    currentUserId,
    currentUser: { id: currentUserId, name: currentUserId, loginId: `${currentUserId}@test.local`, role: team.leaderId === currentUserId ? 'leader' : 'member' },
    eventState: 'WAITING',
    wallet: { teamId: team.id, balance: 1000, currency: 'coins' },
    currentProblem: null,
    roundOneProblem: null,
    wildcardProblem: null,
    finalProblem: null,
    latestBid: null,
    wildcardBidAmount: null,
    roundOneSettlement: null,
    wildcardApplication: null,
    wildcard: null,
    submission: null,
    isLeader: team.leaderId === currentUserId,
    round1Assigned: false,
    wildcardEligible: true,
    wildcardApplicationsOpen: false,
    submissionsOpen: true,
    gameConfig: {
      round1WinnerCount: 5, round1PreviewSeconds: 120, round1BidSeconds: 300,
      wildcardSlots: 3, wildcardApplicationSeconds: 60, wildcardPreviewSeconds: 120, wildcardBidSeconds: 180,
      codingDurationSeconds: 10800,
    },
    timing: { serverTime: new Date(0).toISOString(), receivedAt: 0, startedAt: null, endsAt: null, paused: false, pausedRemainingSeconds: null },
  }
}

// 1. Team can start with zero leaders
assert.equal(getLeader(emptyTeam), null)
assert.equal(emptyTeam.members.filter((m) => m.isLeader).length, 0)

// 2. Selecting Member A makes Member A leader
const teamA = applyLeaderSelection(emptyTeam, 'A')
assert.equal(getLeader(teamA)?.id, 'A')
assert.equal(teamA.members.filter((m) => m.isLeader).length, 1)

// 3 & 4. Selecting Member B removes leadership from A; exactly one leader remains
const teamB = applyLeaderSelection(teamA, 'B')
assert.equal(getLeader(teamB)?.id, 'B')
assert.equal(teamB.members.find((m) => m.id === 'A')?.isLeader, false)
assert.equal(teamB.members.filter((m) => m.isLeader).length, 1)

// 5. Non-team member cannot be selected
assert.throws(() => applyLeaderSelection(emptyTeam, 'outcast'))

// 6. Current leader receives leader-only permissions
const leaderPerms = getParticipantPermissions(dashboard(teamB, 'B'))
assert.equal(leaderPerms.isLeader, true)
for (const key of ['canPlaceBid', 'canPlaceWildcardBid', 'canSelectWildcardProblem', 'canSubmitRepository']) {
  assert.equal(leaderPerms[key], true, key)
}

// 7. Non-leader does not receive leader-only permissions
const memberPerms = getParticipantPermissions(dashboard(teamB, 'A'))
assert.equal(memberPerms.isLeader, false)
for (const key of ['canPlaceBid', 'canPlaceWildcardBid', 'canSelectWildcardProblem', 'canSubmitRepository']) {
  assert.equal(memberPerms[key], false, key)
}

console.log('leader permissions: all assertions passed')
