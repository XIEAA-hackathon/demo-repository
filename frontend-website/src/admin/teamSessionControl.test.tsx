import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AdminApplication } from './App'

const mocks = vi.hoisted(() => ({ teams: vi.fn(), logout: vi.fn(), approve: vi.fn(), remove: vi.fn(), state: vi.fn(), socket: null as any, connections: vi.fn() }))
vi.mock('./services/auctionSocket', () => ({ connectAuctionSocket: (options: any) => { mocks.socket = options; mocks.connections(); return vi.fn() } }))
vi.mock('./components/LabConfiguration', () => ({ default: () => null }))
vi.mock('./services/api', async importOriginal => ({ ...await importOriginal<any>(),
  getTeams: mocks.teams, forceLogoutTeam: mocks.logout, approveTeam: mocks.approve, deleteTeam: mocks.remove,
  getAdminState: mocks.state, getAdminConfig: async () => null,
  getProblemStatements: async () => [], getBidHistory: async () => [],
  getAdminHealth: async () => ({ database: 'healthy' }), getLabAllocation: async () => null,
}))
const fixture = () => [
  { id: 1, team_name: 'Astella', coins: 5000, members: [{ id: 1 }, { id: 2 }], is_approved: true, logged_in: true },
  { id: 2, team_name: 'Offline team', coins: 4951, members: [], is_approved: false, logged_in: false },
  { id: 3, team_name: 'Other team', coins: 4800, members: [], is_approved: true, logged_in: true },
]
let host: HTMLDivElement
let root: ReturnType<typeof createRoot>
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); vi.useFakeTimers()
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  for (const mock of [mocks.teams, mocks.logout, mocks.approve, mocks.remove, mocks.state, mocks.connections]) mock.mockReset()
  mocks.teams.mockResolvedValue(fixture())
  mocks.state.mockResolvedValue({ event_state: 'WAITING', timing: {}, rounds: {} })
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(() => { act(() => root.unmount()); host.remove(); vi.useRealTimers() })
const row = (name: string) => [...host.querySelectorAll('tbody tr')].find(row => row.querySelector('td')?.textContent === name)!
const click = async (scope: ParentNode, text: string) => {
  const button = [...scope.querySelectorAll('button')].find(button => button.textContent === text) as HTMLButtonElement
  expect(button).toBeTruthy(); await act(async () => button.click())
}
const renderTeams = async () => {
  await act(async () => root.render(<AdminApplication onLogout={vi.fn()} />))
  await act(async () => vi.advanceTimersByTimeAsync(0))
  await act(async () => (host.querySelector('button[aria-label="Teams"]') as HTMLButtonElement).click())
}

it('replaces STATUS with SESSION CONTROL, keeping login presence, approval and deletion', async () => {
  await renderTeams()
  expect([...host.querySelectorAll('th')].map(cell => cell.textContent)).toEqual(['TEAM', 'COINS', 'MEMBERS', 'SESSION CONTROL', 'LOGGED IN', 'ACTIONS'])
  expect(row('Astella').querySelectorAll('td')[3].textContent).toBe('Log out team')
  expect(row('Astella').querySelectorAll('td')[4].textContent).toBe('YES')
  expect(row('Offline team').querySelectorAll('td')[3].textContent).toBe('No active session')
  expect(row('Offline team').querySelectorAll('td')[3].querySelector('button')).toBeNull()
  expect(row('Offline team').querySelectorAll('td')[4].textContent).toBe('NO')
  expect(row('Offline team').querySelectorAll('td')[5].textContent).toContain('ApproveDelete')
  expect(row('Astella').querySelectorAll('td')[5].textContent).toBe('Delete')
})

it('requires confirmation and updates YES to NO and the summary using the authoritative Teams refresh', async () => {
  mocks.logout.mockResolvedValue({ status: 'team_force_logged_out', team_id: 1 })
  mocks.teams.mockResolvedValueOnce(fixture()).mockResolvedValue(fixture().map(team => team.id === 1 ? { ...team, logged_in: false } : team))
  await renderTeams()
  expect(host.querySelector('.teams-login-summary strong')?.textContent).toBe('2 / 3')
  await click(row('Astella'), 'Log out team')
  expect(mocks.logout).not.toHaveBeenCalled()
  const dialog = host.querySelector('[role="dialog"]')!
  expect(dialog.textContent).toContain('Log out Astella?')
  expect(dialog.textContent).toContain('same credentials')
  await click(dialog, 'Log out team')
  expect(mocks.logout).toHaveBeenCalledWith(1)
  expect(row('Astella').querySelectorAll('td')[3].textContent).toBe('No active session')
  expect(row('Astella').querySelectorAll('td')[4].textContent).toBe('NO')
  expect(host.querySelector('.teams-login-summary strong')?.textContent).toBe('1 / 3')
  expect(mocks.teams).toHaveBeenCalledTimes(2)
  expect(mocks.state).toHaveBeenCalledTimes(1)
  expect(mocks.connections).toHaveBeenCalledTimes(1)
})

it('blocks duplicate requests only for the selected team and applies the existing presence event immediately', async () => {
  let finish!: (value: any) => void
  mocks.logout.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  await renderTeams(); await click(row('Astella'), 'Log out team')
  await click(host.querySelector('[role="dialog"]')!, 'Log out team')
  const busy = row('Astella').querySelectorAll('td')[3].querySelector('button')!
  expect(busy.textContent).toBe('Logging out…'); expect(busy.disabled).toBe(true)
  expect(row('Other team').querySelectorAll('td')[3].querySelector('button')?.disabled).toBe(false)
  await act(async () => busy.click())
  expect(mocks.logout).toHaveBeenCalledTimes(1)
  await act(async () => mocks.socket.onMessage({ type: 'participant_presence_changed', payload: { logged_in_team_ids: [3], participant_logged_in_count: 1 }, version: 1 }))
  expect(row('Astella').querySelectorAll('td')[4].textContent).toBe('NO')
  expect(host.querySelector('.teams-login-summary strong')?.textContent).toBe('1 / 3')
  mocks.teams.mockResolvedValue(fixture().map(team => team.id === 1 ? { ...team, logged_in: false } : team))
  await act(async () => finish({ team_id: 1 }))
  expect(mocks.logout).toHaveBeenCalledTimes(1)
  expect(mocks.connections).toHaveBeenCalledTimes(1)
})

it('cancels safely and reports failure without changing the team or credentials', async () => {
  mocks.logout.mockRejectedValue(new Error('Server unavailable'))
  await renderTeams(); await click(row('Astella'), 'Log out team')
  await click(host.querySelector('[role="dialog"]')!, 'Cancel')
  expect(mocks.logout).not.toHaveBeenCalled()
  await click(row('Astella'), 'Log out team')
  await click(host.querySelector('[role="dialog"]')!, 'Log out team')
  expect(host.querySelector('.admin-teams [role="alert"]')?.textContent).toContain('Server unavailable')
  expect(row('Astella').querySelectorAll('td')[4].textContent).toBe('YES')
  expect(row('Astella').querySelectorAll('td')[3].querySelector('button')?.disabled).toBe(false)
  expect(mocks.approve).not.toHaveBeenCalled(); expect(mocks.remove).not.toHaveBeenCalled()
  expect(mocks.teams).toHaveBeenCalledTimes(1)
})
