import http from 'k6/http'
import ws from 'k6/ws'
import { check, sleep } from 'k6'
import { Counter, Rate, Trend } from 'k6/metrics'
import { SharedArray } from 'k6/data'
import exec from 'k6/execution'

const baseUrl = (__ENV.BASE_URL || '').replace(/\/+$/, '')
const credentialsFile = __ENV.CREDENTIALS_FILE || './credentials.json'
const participants = Number(__ENV.USERS || 100)
const bidsPerParticipant = Number(__ENV.BIDS_PER_USER || 10)
const bidDelaySeconds = Number(__ENV.BID_DELAY_SECONDS || 5)
const bidProblemId = Number(__ENV.BID_PROBLEM_ID || 0)
const websocketUsers = Number(__ENV.WS_USERS || 10)

if (!baseUrl) throw new Error('BASE_URL is required (production: https://bidtobuild.dev/api).')
if (!bidProblemId) throw new Error('BID_PROBLEM_ID must identify the disposable active Round 1 auction.')

const credentials = JSON.parse(open(credentialsFile))
const biddingUsers = new SharedArray('round1 bidding users', () => credentials.loginUsers || [])
const websocketAccounts = new SharedArray('round1 WebSocket users', () => credentials.activeWebSocketUsers || [])
if (biddingUsers.length < participants) {
  throw new Error(`loginUsers needs ${participants} unique participant accounts in ${credentialsFile}`)
}
if (websocketAccounts.length < websocketUsers) {
  throw new Error(`activeWebSocketUsers needs ${websocketUsers} accounts not used by loginUsers`)
}

const loginSuccess = new Rate('login_success')
const loginDuration = new Trend('login_successful_duration', true)
const login5xx = new Counter('login_5xx')
const bidSuccess = new Rate('bid_success')
const bidDuration = new Trend('bid_successful_duration', true)
const bidTransactionDuration = new Trend('bid_db_transaction_duration', true)
const bidAuctionLockWait = new Trend('bid_auction_lock_wait_duration', true)
const bidAttempts = new Counter('bid_attempts')
const cooldown429 = new Counter('bid_cooldown_429')
const expectedBusiness4xx = new Counter('bid_expected_business_4xx')
const expectedWallet4xx = new Counter('bid_expected_wallet_4xx')
const expectedAuctionState4xx = new Counter('bid_expected_auction_state_4xx')
const unexpected4xx = new Counter('bid_unexpected_4xx')
const server5xx = new Counter('bid_5xx')
const requestTimeouts = new Counter('request_timeouts')
const websocketMessages = new Counter('websocket_bid_messages')
const websocketFailures = new Counter('websocket_failures')
const websocketLatency = new Trend('websocket_bid_latency', true)

export const options = {
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  // The client waits exactly as long as Uvicorn's default keep-alive timeout.
  // Open a fresh HTTP connection for each request instead of racing reuse of
  // a socket the server is expiring at the five-second boundary.
  noConnectionReuse: true,
  setupTimeout: '5m',
  teardownTimeout: '2m',
  scenarios: {
    round1_bidders: {
      executor: 'per-vu-iterations',
      exec: 'round1Bidder',
      vus: participants,
      iterations: 1,
      maxDuration: __ENV.MAX_DURATION || '4m',
    },
    websocket_observers: {
      executor: 'per-vu-iterations',
      exec: 'websocketObserver',
      vus: websocketUsers,
      iterations: 1,
      maxDuration: __ENV.MAX_DURATION || '4m',
    },
  },
  thresholds: {
    login_success: ['rate>0.99'],
    login_successful_duration: ['p(95)<30000'],
    bid_successful_duration: ['p(95)<2000'],
    bid_5xx: ['count==0'],
    login_5xx: ['count==0'],
    bid_unexpected_4xx: ['count==0'],
    request_timeouts: ['count==0'],
    websocket_failures: ['count==0'],
  },
}

function login(user, scenario) {
  const response = http.post(
    `${baseUrl}/login`,
    { username: user.username, password: user.password },
    { tags: { operation: 'login', scenario }, timeout: __ENV.LOGIN_TIMEOUT || '45s' },
  )
  if (response.status === 200) loginDuration.add(response.timings.duration)
  loginSuccess.add(response.status === 200)
  if (response.status >= 500) login5xx.add(1, { status: String(response.status) })
  if (response.status === 0) requestTimeouts.add(1, { operation: 'login' })
  return response
}

function tokenFrom(response) {
  if (response.status !== 200) return null
  try { return response.json('access_token') || null } catch (_) { return null }
}

function authHeaders(token) {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
}

function logout(token) {
  if (!token) return
  http.post(
    `${baseUrl}/logout`,
    null,
    { headers: { Authorization: `Bearer ${token}` }, tags: { operation: 'logout' }, timeout: '15s' },
  )
}

function responseReason(response) {
  try {
    const detail = response.json('detail')
    return String(detail || 'unknown').slice(0, 80)
  } catch (_) {
    return 'unparseable'
  }
}

function recordExpectedBusinessRejection(reason, tags) {
  const normalized = reason.toLowerCase()
  if (normalized.includes('wallet') || normalized.includes('coins')) {
    expectedBusiness4xx.add(1, tags)
    expectedWallet4xx.add(1, tags)
    return true
  }
  if (
    normalized.includes('bidding is not open')
    || normalized.includes('already has a round 1 problem')
    || normalized.includes('invalid or unavailable problem statement')
  ) {
    expectedBusiness4xx.add(1, tags)
    expectedAuctionState4xx.add(1, tags)
    return true
  }
  return false
}

function serverTimingDuration(response, metricName) {
  const raw = response.headers['Server-Timing'] || response.headers['server-timing'] || ''
  const match = new RegExp(`${metricName};dur=([0-9.]+)`).exec(raw)
  return match ? Number(match[1]) : null
}

export function setup() {
  const websocketTokens = websocketAccounts.slice(0, websocketUsers).map((user) => {
    const response = login(user, 'websocket_setup')
    const token = tokenFrom(response)
    if (!token) throw new Error(`WebSocket observer login failed for ${user.username}: ${response.status}`)
    return token
  })
  return {
    websocketTokens,
    bidAt: Date.now() + Number(__ENV.INITIAL_BID_DELAY_MS || 60_000),
  }
}

export function round1Bidder(data) {
  const user = biddingUsers[exec.scenario.iterationInTest]
  const loginResponse = login(user, 'round1_bidder')
  const token = tokenFrom(loginResponse)
  if (!token) return

  const waitMs = data.bidAt - Date.now()
  if (waitMs > 0) sleep(waitMs / 1000)

  for (let index = 0; index < bidsPerParticipant; index += 1) {
    bidAttempts.add(1)
    const response = http.post(
      `${baseUrl}/bid`,
      JSON.stringify({ ps_id: bidProblemId, increment: Number(__ENV.BID_INCREMENT || 5) }),
      {
        headers: authHeaders(token),
        tags: { operation: 'bid' },
        timeout: __ENV.BID_TIMEOUT || '10s',
      },
    )

    if (response.status === 200) {
      bidSuccess.add(true)
      bidDuration.add(response.timings.duration)
      const transactionMs = serverTimingDuration(response, 'db-transaction')
      const lockWaitMs = serverTimingDuration(response, 'auction-lock')
      if (Number.isFinite(transactionMs)) bidTransactionDuration.add(transactionMs)
      if (Number.isFinite(lockWaitMs)) bidAuctionLockWait.add(lockWaitMs)
    } else {
      bidSuccess.add(false)
      const tags = { status: String(response.status), reason: responseReason(response) }
      if (response.status === 429) cooldown429.add(1, tags)
      else if (response.status >= 400 && response.status < 500) {
        if (!recordExpectedBusinessRejection(tags.reason, tags)) unexpected4xx.add(1, tags)
      }
      else if (response.status >= 500) server5xx.add(1, tags)
      else if (response.status === 0) requestTimeouts.add(1, { operation: 'bid' })
    }

    check(response, {
      'bid returned a classified response': (result) =>
        result.status === 200 || result.status === 429 || [400, 409, 422].includes(result.status),
    })
    if (index < bidsPerParticipant - 1) sleep(bidDelaySeconds)
  }
  logout(token)
}

export function websocketObserver(data) {
  const token = data.websocketTokens[exec.scenario.iterationInTest]
  const wsUrl = `${baseUrl.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:')}/ws/auction?token=${encodeURIComponent(token)}`
  const response = ws.connect(wsUrl, {}, (socket) => {
    socket.on('open', () => socket.setInterval(() => socket.send('heartbeat'), 20_000))
    socket.on('message', (raw) => {
      try {
        const message = JSON.parse(raw)
        if (message.type !== 'bid_updated') return
        websocketMessages.add(1)
        const sentAt = Date.parse(message.server_time || message.timestamp)
        if (Number.isFinite(sentAt)) websocketLatency.add(Math.max(0, Date.now() - sentAt))
      } catch (_) {
        websocketFailures.add(1, { reason: 'invalid_message' })
      }
    })
    socket.on('error', () => websocketFailures.add(1, { reason: 'socket_error' }))
    socket.setTimeout(
      () => socket.close(),
      Number(__ENV.WS_DURATION_MS || (60_000 + bidsPerParticipant * (bidDelaySeconds * 1000 + 3000))),
    )
  })
  if (!check(response, { 'WebSocket handshake succeeds': (result) => result?.status === 101 })) {
    websocketFailures.add(1, { reason: 'handshake' })
  }
}

export function teardown(data) {
  for (const token of data.websocketTokens) logout(token)
}
