import { createElement } from 'react'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'
import ProtectedRoute from './ProtectedRoute'
import { clearAccessToken, getAccessToken } from '../services/apiClient'
import * as authService from '../services/authService'

vi.mock('../services/apiClient', () => ({
  clearAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
}))
vi.mock('../services/authService', () => ({
  login: vi.fn(),
  logout: vi.fn(),
  validateParticipantSession: vi.fn(),
}))

const session = { id: 1, name: 'Leader', email: 'leader@test.example', role: 'leader' as const }
let host: HTMLDivElement
let root: ReturnType<typeof createRoot>

function protectedTree() {
  return createElement(
    MemoryRouter,
    { initialEntries: ['/participant'] },
    createElement(
      AuthProvider,
      null,
      createElement(
        Routes,
        null,
        createElement(Route, {
          path: '/participant',
          element: createElement(ProtectedRoute, null, createElement('div', null, 'Participant home')),
        }),
        createElement(Route, { path: '/participant/login', element: createElement('div', null, 'Participant login') }),
      ),
    ),
  )
}

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.clearAllMocks()
  vi.mocked(getAccessToken).mockReturnValue(null)
  host = document.createElement('div')
  root = createRoot(host)
})

afterEach(() => act(() => root.unmount()))

it('validates an existing token and keeps the protected route in checking state until validation completes', async () => {
  let resolveSession!: (value: typeof session) => void
  vi.mocked(getAccessToken).mockReturnValue('participant-token')
  vi.mocked(authService.validateParticipantSession).mockReturnValue(
    new Promise((resolve) => { resolveSession = resolve }),
  )

  await act(async () => root.render(protectedTree()))

  expect(host.textContent).toContain('Validating participant session…')
  expect(host.textContent).not.toContain('Participant login')

  await act(async () => resolveSession(session))

  expect(authService.validateParticipantSession).toHaveBeenCalledOnce()
  expect(host.textContent).toContain('Participant home')
})

it('clears an invalid participant token and redirects to participant login', async () => {
  vi.mocked(getAccessToken).mockReturnValue('wrong-role-token')
  vi.mocked(authService.validateParticipantSession).mockRejectedValue(new Error('Participant access required'))

  await act(async () => root.render(protectedTree()))

  expect(clearAccessToken).toHaveBeenCalledOnce()
  expect(host.textContent).toContain('Participant login')
})

it('validates the stored token after login before authenticating', async () => {
  vi.mocked(authService.login).mockResolvedValue(undefined)
  vi.mocked(authService.validateParticipantSession).mockResolvedValue(session)

  function LoginProbe() {
    const { authenticated, login } = useAuth()
    return createElement(
      'button',
      { onClick: () => void login('leader@test.example', 'password') },
      authenticated ? 'Authenticated' : 'Log in',
    )
  }

  await act(async () => root.render(createElement(AuthProvider, null, createElement(LoginProbe))))
  await act(async () => host.querySelector('button')?.click())

  expect(authService.login).toHaveBeenCalledWith('leader@test.example', 'password')
  expect(authService.validateParticipantSession).toHaveBeenCalledOnce()
  expect(host.textContent).toBe('Authenticated')
})
