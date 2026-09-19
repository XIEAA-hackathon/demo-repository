import { ApiError, apiRequest, clearAccessToken, setAccessToken } from './apiClient'
import { participantLoginErrorMessage } from './loginMessages'

interface TokenResponse {
  access_token: string
  token_type: string
}

export interface ParticipantSession {
  id: number
  name: string
  email: string
  role: 'leader' | 'member'
}

export async function login(email: string, password: string) {
  const body = new URLSearchParams({ username: email.trim(), password })
  try {
    const response = await apiRequest<TokenResponse>('/login', { method: 'POST', body })
    setAccessToken(response.access_token)
  } catch (cause) {
    clearAccessToken()
    if (cause instanceof ApiError) {
      throw new ApiError(
        participantLoginErrorMessage(cause.status, cause.message),
        cause.status,
        cause.retryAfterSeconds,
      )
    }
    throw cause
  }
}

export async function logout() {
  await apiRequest('/logout', { method: 'POST' })
  clearAccessToken()
}

export async function validateParticipantSession() {
  const session = await apiRequest<ParticipantSession>('/participant/session')
  if (session.role !== 'leader' && session.role !== 'member') {
    throw new ApiError('Participant access requires a participant account.', 403)
  }
  return session
}
