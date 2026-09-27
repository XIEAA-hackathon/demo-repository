import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import ParticipantLayout from './ParticipantLayout'

const useParticipant = vi.fn()
const logout = vi.fn()
vi.mock('../ParticipantContext', () => ({ useParticipant: () => useParticipant() }))
vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ logout }) }))
vi.mock('./StageNavigation', () => ({ default: () => <nav>Stage navigation</nav> }))

const dashboard = {
  eventState: 'CODING',
  currentUser: { name: 'Team Leader' },
  isLeader: true,
  team: { name: 'Team Alpha' },
  wallet: { balance: 5000 },
}

let host: HTMLDivElement
let root: ReturnType<typeof createRoot>

function renderLayout() {
  return act(async () => root.render(
    <MemoryRouter initialEntries={['/participant']}>
      <Routes>
        <Route path="/participant" element={<ParticipantLayout />}>
          <Route index element={<p>Participant content</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  ))
}

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.clearAllMocks()
  host = document.createElement('div')
  root = createRoot(host)
  useParticipant.mockReturnValue({
    dashboard,
    loading: false,
    error: null,
    socketStatus: 'reconnected',
    apiStatus: 'degraded',
    lastSyncAt: Date.now() - 600_000,
    documentHidden: false,
    refreshPending: false,
    refresh: vi.fn(),
  })
})

afterEach(() => act(() => root.unmount()))

it('hides stale-sync diagnostics while preserving status and participant content', async () => {
  await renderLayout()

  expect(host.textContent).not.toContain('Live state may be stale')
  expect(host.textContent).not.toContain('Last successful API synchronization')
  expect(host.textContent).not.toContain('Dashboard polling is recovering')
  expect(host.textContent).toContain('Reconnected')
  expect(host.textContent).toContain('API degraded')
  expect(host.textContent).toContain('Participant content')
})

it('preserves the logout error warning', async () => {
  logout.mockRejectedValue(new Error('offline'))
  await renderLayout()
  await act(async () => host.querySelector<HTMLButtonElement>('button')?.click())

  const alert = host.querySelector('[role="alert"]')
  expect(alert?.classList.contains('participant-stale-warning')).toBe(true)
  expect(alert?.textContent).toContain('Logout incomplete.')
  expect(alert?.textContent).toContain('Logout could not reach the event server')
})
