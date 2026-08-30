import { ApiError, apiRequest, clearAccessToken, setAccessToken } from './apiClient'
import { participantLoginErrorMessage } from './loginMessages'

interface TokenResponse {
  access_token: string
  token_type: string
}

export async function login(email: string, password: string) {
  const body = new URLSearchParams({ username: email.trim(), password })
  try {
    const response = await apiRequest<TokenResponse>('/login', { method: 'POST', body })
    setAccessToken(response.access_token)
    await apiRequest('/participant/dashboard')
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
