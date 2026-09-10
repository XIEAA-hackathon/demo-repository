import { check, sleep } from 'k6'
import { Counter } from 'k6/metrics'
import { credentials, login, logout, tokenFrom } from './lib/auth.js'

if (!credentials.sameAccount?.username || !credentials.sameAccount?.password) {
  throw new Error('sameAccount credentials are required')
}

const successes = new Counter('same_account_successes')
const conflicts = new Counter('same_account_conflicts')

export const options = {
  scenarios: {
    same_account_race: {
      executor: 'per-vu-iterations',
      vus: 2,
      iterations: 1,
      maxDuration: '45s',
    },
  },
  thresholds: {
    same_account_successes: ['count==1'],
    same_account_conflicts: ['count==1'],
  },
}

export default function () {
  const response = login(credentials.sameAccount, { scenario: 'same_account' })
  const token = tokenFrom(response)
  if (response.status === 200) successes.add(1)
  if (response.status === 409) conflicts.add(1)
  check(response, { 'one request succeeds and the other conflicts': (result) => [200, 409].includes(result.status) })
  if (token) {
    sleep(2)
    logout(token)
  }
}
