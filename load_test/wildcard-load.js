import http from 'k6/http'
import ws from 'k6/ws'
import { check, sleep } from 'k6'
import { Counter, Rate, Trend } from 'k6/metrics'
import exec from 'k6/execution'
import { authParams, baseUrl, credentials, login, logout, requireUsers, tokenFrom } from './lib/auth.js'

const socketUsers = Number(__ENV.SOCKETS || 80)
const bidderUsers = Number(__ENV.BIDDERS || 10)
const dashboardUsers = Number(__ENV.DASHBOARD_USERS || 20)
const bidAttempts = Number(__ENV.BID_ATTEMPTS || 3)
const testSeconds = Number(__ENV.TEST_SECONDS || 45)

if (socketUsers < 1) throw new Error('SOCKETS must be positive.')
if (bidderUsers < 5 || bidderUsers > 15) throw new Error('BIDDERS must be between 5 and 15.')
requireUsers(credentials.activeWebSocketUsers, socketUsers, 'activeWebSocketUsers')
requireUsers(credentials.loginUsers, bidderUsers, 'loginUsers')
requireUsers(credentials.activeApiUsers, dashboardUsers, 'activeApiUsers')

const requestSuccess = new Rate('wildcard_request_success')
const bidLatency = new Trend('wildcard_bid_latency', true)
const dashboardLatency = new Trend('participant_dashboard_latency', true)
const unexpected401 = new Counter('unexpected_401')
const serverErrors = new Counter('http_5xx')
const websocketDisconnects = new Counter('websocket_unexpected_disconnects')
const websocketMessages = new Counter('websocket_messages')

export const options = {
  scenarios: {
    participant_sockets: {
      executor: 'per-vu-iterations',
      exec: 'participantSocket',
      vus: socketUsers,
      iterations: 1,
      maxDuration: `${testSeconds + 30}s`,
    },
    wildcard_bidders: {
      executor: 'per-vu-iterations',
      exec: 'wildcardBidder',
      vus: bidderUsers,
      iterations: 1,
      startTime: '5s',
      maxDuration: `${testSeconds + 30}s`,
    },
    synchronized_dashboards: {
      executor: 'per-vu-iterations',
      exec: 'dashboardObserver',
      vus: dashboardUsers,
      iterations: 1,
      startTime: '5s',
      maxDuration: `${testSeconds + 30}s`,
    },
  },
  thresholds: {
    wildcard_request_success: ['rate>0.99'],
    'wildcard_bid_latency': ['p(95)<2000', 'p(99)<4000'],
    'participant_dashboard_latency': ['p(95)<1500', 'p(99)<3000'],
    unexpected_401: ['count==0'],
    http_5xx: ['count==0'],
    websocket_unexpected_disconnects: ['count==0'],
  },
}

export function setup() {
  // All API scenarios converge on the same instant to expose refresh herds.
  return { synchronizedAt: Date.now() + 15_000 }
}

function authenticate(user, scenario) {
  const response = login(user, { scenario })
  recordResponse(response, 'login')
  const token = tokenFrom(response)
  check(response, { [`${scenario} login succeeded`]: () => Boolean(token) })
  return token
}

function recordResponse(response, operation) {
  const ok = response.status >= 200 && response.status < 300
  requestSuccess.add(ok, { operation })
  if (response.status === 401) unexpected401.add(1, { operation })
  if (response.status >= 500) serverErrors.add(1, { operation, status: String(response.status) })
  return ok
}

function waitUntil(timestamp) {
  const remaining = timestamp - Date.now()
  if (remaining > 0) sleep(remaining / 1000)
}

export function participantSocket() {
  const user = credentials.activeWebSocketUsers[exec.scenario.iterationInTest]
  const token = authenticate(user, 'participant_socket')
  if (!token) return
  const socketUrl = `${baseUrl.replace(/^http/, 'ws')}/ws/auction?token=${encodeURIComponent(token)}`
  let opened = false
  let intentionallyClosed = false
  const response = ws.connect(socketUrl, { tags: { operation: 'participant_socket' } }, (socket) => {
    socket.on('open', () => {
      opened = true
      socket.send(JSON.stringify({ type: 'heartbeat', client_time: Date.now() }))
      socket.setInterval(() => socket.send(JSON.stringify({ type: 'heartbeat', client_time: Date.now() })), 20_000)
      socket.setTimeout(() => { intentionallyClosed = true; socket.close() }, testSeconds * 1000)
    })
    socket.on('message', () => websocketMessages.add(1))
    socket.on('close', () => { if (!intentionallyClosed) websocketDisconnects.add(1) })
    socket.on('error', () => websocketDisconnects.add(1))
  })
  check(response, { 'websocket upgraded': (result) => result?.status === 101 && opened })
  logout(token)
}

export function wildcardBidder(data) {
  const user = credentials.loginUsers[exec.scenario.iterationInTest]
  const token = authenticate(user, 'wildcard_bidder')
  if (!token) return
  waitUntil(data.synchronizedAt)
  for (let attempt = 0; attempt < bidAttempts; attempt += 1) {
    const response = http.post(
      `${baseUrl}/wildcard/bid`,
      JSON.stringify({ increment: [5, 10, 25][(__VU + attempt) % 3] }),
      { ...authParams(token, 'wildcard_bid'), headers: { ...authParams(token, 'wildcard_bid').headers, 'Content-Type': 'application/json' } },
    )
    if (response.status === 200) bidLatency.add(response.timings.duration)
    recordResponse(response, 'wildcard_bid')
    check(response, { 'wildcard bid accepted': (result) => result.status === 200 })
    if (attempt + 1 < bidAttempts) sleep(5.1)
  }
  logout(token)
}

export function dashboardObserver(data) {
  const user = credentials.activeApiUsers[exec.scenario.iterationInTest]
  const token = authenticate(user, 'dashboard_observer')
  if (!token) return
  waitUntil(data.synchronizedAt)
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const response = http.get(`${baseUrl}/participant/dashboard`, authParams(token, 'participant_dashboard'))
    if (response.status === 200) dashboardLatency.add(response.timings.duration)
    recordResponse(response, 'participant_dashboard')
    check(response, { 'dashboard returned authoritative state': (result) => result.status === 200 && Boolean(result.json('eventState')) })
    sleep(1)
  }
  logout(token)
}
