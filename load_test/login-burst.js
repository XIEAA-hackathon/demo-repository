import { check } from 'k6'
import { Counter, Trend } from 'k6/metrics'
import { credentials, login, logout, requireUsers, tokenFrom } from './lib/auth.js'

const users = Number(__ENV.USERS || 40)
requireUsers(credentials.loginUsers, users, 'loginUsers')

const successfulLogins = new Counter('successful_logins')
const controlledBusy = new Counter('controlled_auth_busy')
const loginLatency = new Trend('login_latency', true)

export const options = {
  scenarios: {
    simultaneous_login_burst: {
      executor: 'per-vu-iterations',
      vus: users,
      iterations: 1,
      maxDuration: __ENV.MAX_DURATION || '90s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.05'],
    login_latency: ['p(95)<45000'],
  },
}

export default function () {
  const response = login(credentials.loginUsers[__VU - 1], { scenario: 'burst' })
  loginLatency.add(response.timings.duration)
  const token = tokenFrom(response)
  if (token) successfulLogins.add(1)
  if (response.status === 503) controlledBusy.add(1)
  check(response, {
    'login succeeds or sheds load cleanly': (result) => result.status === 200 || result.status === 503,
    '503 includes Retry-After': (result) => result.status !== 503 || result.headers['Retry-After'] === '2',
  })
  if (token && (__ENV.LOGOUT_AFTER || 'true').toLowerCase() === 'true') logout(token)
}
