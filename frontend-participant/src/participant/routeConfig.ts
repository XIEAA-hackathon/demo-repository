import type { ParticipantEventState } from './types'

export interface ParticipantStageRoute {
  state: ParticipantEventState
  label: string
  path: string
}

export const participantStageRoutes: readonly ParticipantStageRoute[] = [
  { state: 'WAITING', label: 'Waiting for event', path: '/' },
  { state: 'ROUND1_PREVIEW', label: 'Round 1 preview', path: '/problem' },
  { state: 'ROUND1_BIDDING', label: 'Round 1 bidding', path: '/bid' },
  { state: 'ROUND1_RESULT', label: 'Round 1 result', path: '/result' },
  { state: 'WILDCARD_APPLICATION', label: 'Wildcard application', path: '/wildcard' },
  { state: 'WILDCARD_PREVIEW', label: 'Wildcard preview', path: '/wildcard/preview' },
  { state: 'WILDCARD_BIDDING', label: 'Wildcard bidding', path: '/wildcard/bid' },
  { state: 'WILDCARD_SELECTION', label: 'Wildcard selection', path: '/wildcard/select' },
  { state: 'CODING', label: 'Coding round', path: '/coding' },
  { state: 'SUBMISSION', label: 'Final submission', path: '/submission' },
  { state: 'JUDGING_WAIT', label: 'Waiting for judging', path: '/judging' },
  { state: 'RESULTS', label: 'Final results', path: '/results' },
] as const

export function getStageRoute(state: ParticipantEventState): ParticipantStageRoute {
  const route = participantStageRoutes.find((item) => item.state === state)
  if (!route) throw new Error(`Unknown participant event state: ${state}`)
  return route
}
