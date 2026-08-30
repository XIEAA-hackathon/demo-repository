import { strict as assert } from 'node:assert'
import {
  AUTHENTICATION_BUSY_MESSAGE,
  LOGIN_PENDING_LABEL,
  participantLoginErrorMessage,
} from './loginMessages.ts'

const values = new Map<string, string>()
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  },
})

const { clearAccessToken, getAccessToken, setAccessToken } = await import('./participantToken.ts')

assert.equal(getAccessToken(), null)
setAccessToken('existing-session-token')
assert.equal(getAccessToken(), 'existing-session-token', 'participant token must survive a reload-style read')
clearAccessToken()
assert.equal(getAccessToken(), null, 'logout/unauthorized handling must clear the participant token')

assert.equal(LOGIN_PENDING_LABEL, 'Logging in…')
assert.equal(participantLoginErrorMessage(503, 'backend detail'), AUTHENTICATION_BUSY_MESSAGE)
assert.equal(participantLoginErrorMessage(401, 'backend detail'), 'Invalid username/email or password.')
assert.equal(
  participantLoginErrorMessage(409, 'This participant account is already logged in.'),
  'This participant account is already logged in.',
)

console.log('Participant auth contract tests passed.')
