import { createElement } from 'react'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { login as adminLogin } from './admin/services/api'
import { labAdminLogin } from './lab-admin/services/api'
import Dashboard from './leaderboard/Dashboard'
import { validateParticipantSession } from './participant/services/authService'
import { authenticatedRequest } from './services/api/authenticatedClient'

vi.mock('./services/api/authenticatedClient', async (original) => ({
  ...await original(),
  authenticatedRequest: vi.fn(),
}))

let host: HTMLDivElement
let root: ReturnType<typeof createRoot>

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.clearAllMocks()
  localStorage.clear()
  host = document.createElement('div')
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  vi.unstubAllGlobals()
})

it('uses the dedicated admin and lab-admin login endpoints', async () => {
  vi.mocked(authenticatedRequest).mockResolvedValue({ access_token: 'token' })

  await adminLogin('admin@test.example', 'password')
  expect(vi.mocked(authenticatedRequest).mock.calls[0][3]).toBe('/admin/login')

  vi.mocked(authenticatedRequest).mockClear()
  await labAdminLogin('lab@test.example', 'password')
  expect(vi.mocked(authenticatedRequest).mock.calls[0][3]).toBe('/lab-admin/login')
})

it('validates participant tokens through the participant session endpoint', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    headers: new Headers(),
    json: async () => ({ id: 1, name: 'Leader', email: 'leader@test.example', role: 'leader' }),
  })
  vi.stubGlobal('fetch', fetchMock)

  await validateParticipantSession()

  expect(fetchMock.mock.calls[0][0]).toMatch(/\/participant\/session$/)
})

it('keeps leaderboard login on its dedicated endpoint', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    headers: new Headers(),
    json: async () => ({ access_token: 'display-token' }),
  })
  vi.stubGlobal('fetch', fetchMock)
  await act(async () => root.render(createElement(Dashboard)))

  await act(async () => {
    host.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  })

  expect(fetchMock.mock.calls[0][0]).toMatch(/\/leaderboard\/login$/)
})
