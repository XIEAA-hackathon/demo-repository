import type { ParticipantEventState } from './types'

export interface ParticipantStageRoute {
  state: ParticipantEventState
  label: string
  path: string
}

export const participantStageRoutes: readonly ParticipantStageRoute[] = [
  { state: 'WAITING', label: 'Waiting for event', path: '/participant' },
  { state: 'ROUND1_PREVIEW', label: 'Round 1 preview', path: '/participant/problem' },
  { state: 'ROUND1_BIDDING', label: 'Round 1 bidding', path: '/participant/bid' },
  { state: 'ROUND1_RESULT', label: 'Round 1 result', path: '/participant/result' },
  { state: 'WILDCARD_APPLICATION', label: 'Wildcard application', path: '/participant/wildcard' },
  { state: 'WILDCARD_BIDDING', label: 'Wildcard slot bidding', path: '/participant/wildcard/bid' },
  { state: 'WILDCARD_SELECTION', label: 'Wildcard selection', path: '/participant/wildcard/select' },
  { state: 'CODING', label: 'Coding round', path: '/participant/coding' },
  { state: 'SUBMISSION', label: 'Final submission', path: '/participant/submission' },
  { state: 'JUDGING_WAIT', label: 'Waiting for judging', path: '/participant/judging' },
  { state: 'RESULTS', label: 'Final results', path: '/participant/results' },
] as const

export function getStageRoute(state: ParticipantEventState): ParticipantStageRoute {
  const route = participantStageRoutes.find((item) => item.state === state)
  if (!route) throw new Error(`Unknown participant event state: ${state}`)
  return route
}
