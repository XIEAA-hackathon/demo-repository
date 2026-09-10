import http from 'k6/http'

export const baseUrl = (__ENV.BASE_URL || '').replace(/\/+$/, '')
export const credentialsFile = __ENV.CREDENTIALS_FILE || './credentials.json'

if (!baseUrl) throw new Error('BASE_URL is required; no production URL is built into these tests.')

export const credentials = JSON.parse(open(credentialsFile))

export function login(user, tags = {}) {
  if (!user?.username || !user?.password) throw new Error(`Missing credentials in ${credentialsFile}`)
  return http.post(
    `${baseUrl}/login`,
    { username: user.username, password: user.password },
    { tags: { operation: 'login', ...tags }, timeout: __ENV.LOGIN_TIMEOUT || '45s' },
  )
}

export function authParams(token, operation) {
  return {
    headers: { Authorization: `Bearer ${token}` },
    tags: { operation },
    timeout: '10s',
  }
}

export function logout(token) {
  return http.post(`${baseUrl}/logout`, null, authParams(token, 'logout'))
}

export function tokenFrom(response) {
  if (response.status !== 200) return null
  try {
    return response.json('access_token') || null
  } catch (_) {
    return null
  }
}

export function requireUsers(group, count, groupName) {
  if (!Array.isArray(group) || group.length < count) {
    throw new Error(`${groupName} needs at least ${count} unique entries in ${credentialsFile}`)
  }
}
