import http from 'k6/http'
import ws from 'k6/ws'
import { check, sleep } from 'k6'
import { baseUrl, authParams, credentials, login, logout, requireUsers, tokenFrom } from './lib/auth.js'

const activeApiUsers = Number(__ENV.ACTIVE_API_USERS || 15)
const activeWebSocketUsers = Number(__ENV.ACTIVE_WS_USERS || 10)
const burstUsers = Number(__ENV.BURST_USERS || 40)
requireUsers(credentials.activeApiUsers, activeApiUsers, 'activeApiUsers')
requireUsers(credentials.activeWebSocketUsers, activeWebSocketUsers, 'activeWebSocketUsers')
requireUsers(credentials.loginUsers, burstUsers, 'loginUsers')

export const options = {
  setupTimeout: '5m',
  teardownTimeout: '2m',
  scenarios: {
    authenticated_api_traffic: {
      executor: 'constant-vus',
      exec: 'activeApiTraffic',
      vus: activeApiUsers,
      duration: __ENV.DURATION || '60s',
    },
    authenticated_websockets: {
      executor: 'per-vu-iterations',
      exec: 'activeWebSocket',
      vus: activeWebSocketUsers,
      iterations: 1,
      maxDuration: __ENV.DURATION || '60s',
    },
    login_burst: {
      executor: 'per-vu-iterations',
      exec: 'burstLogin',
      vus: burstUsers,
      iterations: 1,
      startTime: '5s',
      maxDuration: __ENV.DURATION || '60s',
    },
  },
  thresholds: {
    'http_req_duration{operation:dashboard}': ['p(95)<500'],
    'http_req_duration{operation:bid}': ['p(95)<500'],
    'http_req_failed{operation:dashboard}': ['rate<0.01'],
  },
}

const selectItem = (group) => group[(__VU - 1) % group.length]

export function setup() {
  const apiTokens = credentials.activeApiUsers.slice(0, activeApiUsers).map((user) => tokenFrom(login(user, { scenario: 'setup_api' })))
  const webSocketTokens = credentials.activeWebSocketUsers.slice(0, activeWebSocketUsers).map((user) => tokenFrom(login(user, { scenario: 'setup_ws' })))
  if (apiTokens.some((token) => !token) || webSocketTokens.some((token) => !token)) {
    throw new Error('Unable to pre-authenticate all active mixed-workload users')
  }
  return { apiTokens, webSocketTokens }
}

export function activeApiTraffic(data) {
  const token = selectItem(data.apiTokens)
  const dashboard = http.get(`${baseUrl}/participant/dashboard`, authParams(token, 'dashboard'))
  check(dashboard, { 'authenticated dashboard remains responsive': (result) => result.status === 200 })

  const problemId = Number(__ENV.BID_PROBLEM_ID || 0)
  if (problemId > 0 && __ITER % Number(__ENV.BID_EVERY_ITERATIONS || 10) === 0) {
    const params = authParams(token, 'bid')
    const bid = http.post(
      `${baseUrl}/bid`,
      JSON.stringify({ ps_id: problemId, increment: Number(__ENV.BID_INCREMENT || 10) }),
      { ...params, headers: { ...params.headers, 'Content-Type': 'application/json' } },
    )
    check(bid, { 'bid has an expected event response': (result) => [200, 400, 409, 422].includes(result.status) })
  }
  sleep(1)
}

export function activeWebSocket(data) {
  const token = selectItem(data.webSocketTokens)
  const wsUrl = `${baseUrl.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:')}/ws/auction?token=${encodeURIComponent(token)}`
  const response = ws.connect(wsUrl, {}, (socket) => {
    socket.on('open', () => socket.setInterval(() => socket.send('heartbeat'), 20_000))
    socket.setTimeout(() => socket.close(), Number(__ENV.WS_DURATION_MS || 50_000))
  })
  check(response, { 'WebSocket handshake succeeds': (result) => result?.status === 101 })
}

export function burstLogin() {
  const response = login(selectItem(credentials.loginUsers), { scenario: 'mixed_burst' })
  check(response, { 'burst login is bounded': (result) => result.status === 200 || result.status === 503 })
  const token = tokenFrom(response)
  if (token) logout(token)
}

export function teardown(data) {
  for (const token of [...data.apiTokens, ...data.webSocketTokens]) logout(token)
}
