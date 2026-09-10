import { check, sleep } from 'k6'
import { credentials, login, logout, requireUsers, tokenFrom } from './lib/auth.js'

const users = Number(__ENV.USERS || 25)
requireUsers(credentials.cycleUsers, users, 'cycleUsers')

export const options = {
  scenarios: {
    repeated_login_activity_logout: {
      executor: 'per-vu-iterations',
      vus: users,
      iterations: Number(__ENV.ITERATIONS || 3),
      maxDuration: __ENV.MAX_DURATION || '5m',
    },
  },
}

export default function () {
  const response = login(credentials.cycleUsers[__VU - 1], { scenario: 'login_logout_cycle' })
  const token = tokenFrom(response)
  check(response, { 'cycle login succeeds': (result) => result.status === 200 })
  if (!token) return
  sleep(Number(__ENV.ACTIVITY_SECONDS || 2))
  const loggedOut = logout(token)
  check(loggedOut, { 'cycle logout succeeds': (result) => result.status === 200 })
}
