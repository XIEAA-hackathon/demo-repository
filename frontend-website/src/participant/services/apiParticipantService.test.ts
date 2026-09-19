import { beforeEach, expect, it, vi } from 'vitest'
import { participantService } from './apiParticipantService'
import { apiRequest } from './apiClient'

vi.mock('./apiClient', () => ({ apiRequest: vi.fn() }))

beforeEach(() => vi.clearAllMocks())

it('leaves one authoritative dashboard refresh to each mutation caller', async () => {
  vi.mocked(apiRequest).mockResolvedValue({ message: 'ok' })

  await participantService.applyForWildcard()
  await participantService.selectWildcardProblem('12')
  await participantService.confirmFinalProblem('WILDCARD')
  await participantService.submitGitHubRepository('https://github.com/team/project')

  expect(vi.mocked(apiRequest).mock.calls.map(([path]) => path)).toEqual([
    '/wildcard/apply',
    '/wildcard/select/12',
    '/wildcard/final-choice',
    '/submissions/me',
  ])
  expect(vi.mocked(apiRequest).mock.calls[2][1]?.body).toBe(JSON.stringify({ choice: 'WILDCARD' }))
})
