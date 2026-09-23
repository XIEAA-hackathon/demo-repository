import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { connectReconnectingSocket } from '../services/realtime/connectReconnectingSocket'
import LeaderboardDisplay from './LeaderboardDisplay'

vi.mock('../services/realtime/connectReconnectingSocket', () => ({ connectReconnectingSocket: vi.fn() }))

const response = (payload) => ({ status: 200, ok: true, json: vi.fn().mockResolvedValue(payload) })
let host, root, socket, fetchMock

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.useFakeTimers(); vi.clearAllMocks()
  host = document.createElement('div'); root = createRoot(host)
  fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock)
  vi.mocked(connectReconnectingSocket).mockImplementation(options => { socket = options; return () => {} })
})

afterEach(() => {
  act(() => root.unmount())
  vi.useRealTimers(); vi.unstubAllGlobals()
})

it('retries a results refresh that fires while the previous request is in flight', async () => {
  let resolveFirst
  fetchMock
    .mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
    .mockResolvedValueOnce(response({
      mode: 'RESULTS_PUBLISHED', status_label: 'Results published',
      results: {
        first_place: { team_name: 'Alpha' },
        second_place: { team_name: 'Beta' },
        third_place: { team_name: 'Gamma' },
      },
    }))
  await act(async () => root.render(<LeaderboardDisplay token="token" onUnauthorized={vi.fn()} onLogout={vi.fn()} />))

  act(() => socket.onMessage({ type: 'results_published', payload: {} }))
  await act(async () => vi.advanceTimersByTimeAsync(200))
  expect(fetchMock).toHaveBeenCalledTimes(1)

  await act(async () => resolveFirst(response({ mode: 'WAITING', status_label: 'Waiting', rows: [] })))
  await act(async () => vi.advanceTimersByTimeAsync(250))

  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(host.textContent).toContain('FINAL RESULTS')
  expect(host.textContent).toContain('Alpha')
  expect(host.textContent).toContain('Beta')
  expect(host.textContent).toContain('Gamma')
})
