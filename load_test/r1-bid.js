import http from 'k6/http'
import ws from 'k6/ws'
import { check, sleep } from 'k6'
import { Counter, Trend } from 'k6/metrics'
import exec from 'k6/execution'
import { authParams, baseUrl, credentials, login, logout, requireUsers, tokenFrom } from './lib/auth.js'

const users = Number(__ENV.USERS || 100)
const websocketUsers = Number(__ENV.WS_USERS || 10)
const attempts = Number(__ENV.BIDS_PER_USER || 10)
const problemId = Number(__ENV.BID_PROBLEM_ID || 0)
const bidIncrement = Number(__ENV.BID_INCREMENT || 5)
const synchronizedDelayMs = Number(__ENV.SYNCHRONIZED_DELAY_MS || 60_000)

if (problemId < 1) throw new Error('BID_PROBLEM_ID is required for a disposable active Round 1 auction.')
requireUsers(credentials.loginUsers, users, 'loginUsers')
if (websocketUsers > 0) requireUsers(credentials.activeWebSocketUsers, websocketUsers, 'activeWebSocketUsers')

const loginLatency = new Trend('login_latency', true)
const bidLatency = new Trend('successful_bid_latency', true)
const websocketLatency = new Trend('websocket_bid_latency', true)
const successfulLogins = new Counter('successful_logins')
const successfulBids = new Counter('successful_bids')
const cooldownResponses = new Counter('cooldown_429')
const expectedBusinessRejections = new Counter('expected_business_4xx')
const unexpectedClientErrors = new Counter('unexpected_4xx')
const serverErrors = new Counter('http_5xx')
const requestTimeouts = new Counter('request_timeouts')
const websocketFailures = new Counter('websocket_failures')

export const options = {
  setupTimeout: '5m',
  teardownTimeout: '2m',
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  scenarios: {
    synchronized_bidders: {
      executor: 'per-vu-iterations',
      exec: 'bidder',
      vus: users,
      iterations: 1,
      maxDuration: __ENV.MAX_DURATION || '3m',
    },
    websocket_observers: {
      executor: 'per-vu-iterations',
      exec: 'websocketObserver',
      vus: websocketUsers,
      iterations: 1,
      maxDuration: __ENV.MAX_DURATION || '3m',
    },
  },
  thresholds: {
    login_latency: ['p(95)<45000'],
    successful_bid_latency: ['p(95)<2000', 'p(99)<4000'],
    http_5xx: ['count==0'],
    request_timeouts: ['count==0'],
    unexpected_4xx: ['count==0'],
    websocket_failures: ['count==0'],
  },
}

export function setup() {
  return { synchronizedAt: Date.now() + synchronizedDelayMs }
}

function waitUntil(timestamp) {
  const remaining = timestamp - Date.now()
  if (remaining > 0) sleep(remaining / 1000)
}

function recordResponse(response, operation) {
  if (response.error_code === 1050 || response.status === 0) requestTimeouts.add(1, { operation })
  if (response.status >= 500) serverErrors.add(1, { operation, status: String(response.status) })
}

export function bidder(data) {
  const user = credentials.loginUsers[exec.scenario.iterationInTest]
  const loginResponse = login(user, { scenario: 'r1_bidder' })
  loginLatency.add(loginResponse.timings.duration)
  recordResponse(loginResponse, 'login')
  const token = tokenFrom(loginResponse)
  if (token) successfulLogins.add(1)
  check(loginResponse, { 'bidder login succeeds': () => Boolean(token) })
  if (!token) return

  waitUntil(data.synchronizedAt)
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const params = authParams(token, 'round1_bid')
    const response = http.post(
      `${baseUrl}/bid`,
      JSON.stringify({ ps_id: problemId, increment: bidIncrement }),
      { ...params, headers: { ...params.headers, 'Content-Type': 'application/json' } },
    )
    recordResponse(response, 'round1_bid')
    if (response.status === 200) {
      successfulBids.add(1)
      bidLatency.add(response.timings.duration)
    } else if (response.status === 429) {
      cooldownResponses.add(1)
    } else if ([400, 409, 422].includes(response.status)) {
      let reason = 'business_rule'
      try { reason = String(response.json('detail') || reason).slice(0, 80) } catch (_) { /* keep bounded fallback */ }
      expectedBusinessRejections.add(1, { reason })
    } else if (response.status >= 400 && response.status < 500) {
      unexpectedClientErrors.add(1, { status: String(response.status) })
    }
    if (attempt + 1 < attempts) sleep(5.1)
  }
  logout(token)
}

export function websocketObserver(data) {
  if (websocketUsers < 1) return
  const user = credentials.activeWebSocketUsers[exec.scenario.iterationInTest]
  const loginResponse = login(user, { scenario: 'r1_websocket' })
  recordResponse(loginResponse, 'websocket_login')
  const token = tokenFrom(loginResponse)
  if (!token) {
    websocketFailures.add(1, { phase: 'login' })
    return
  }
  const socketUrl = `${baseUrl.replace(/^http/, 'ws')}/ws/auction?token=${encodeURIComponent(token)}`
  let intentionallyClosed = false
  const response = ws.connect(socketUrl, { tags: { operation: 'r1_websocket' } }, (socket) => {
    socket.on('open', () => {
      socket.setInterval(() => socket.send(JSON.stringify({ type: 'heartbeat', client_time: Date.now() })), 20_000)
      const closeAt = data.synchronizedAt + attempts * 5_100 + 10_000
      socket.setTimeout(() => { intentionallyClosed = true; socket.close() }, Math.max(1_000, closeAt - Date.now()))
    })
    socket.on('message', (raw) => {
      try {
        const message = JSON.parse(raw)
        if (message.type !== 'bid_updated') return
        const placedAt = Date.parse(String(message.payload?.timestamp || message.timestamp || ''))
        if (Number.isFinite(placedAt)) websocketLatency.add(Math.max(0, Date.now() - placedAt))
      } catch (_) { /* malformed frames are not transport failures */ }
    })
    socket.on('close', () => { if (!intentionallyClosed) websocketFailures.add(1, { phase: 'close' }) })
    socket.on('error', () => websocketFailures.add(1, { phase: 'error' }))
  })
  if (response?.status !== 101) websocketFailures.add(1, { phase: 'handshake' })
  logout(token)
}
