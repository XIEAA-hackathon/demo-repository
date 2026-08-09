import { ApiError, apiRequest, clearAccessToken, setAccessToken } from './apiClient'

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
    if (cause instanceof ApiError && cause.status === 401) {
      throw new ApiError('Invalid username/email or password.', 401)
    }
    if (cause instanceof ApiError && cause.status === 403 && cause.message === 'Participant access required') {
      throw new ApiError('Participant access required.', 403)
    }
    if (cause instanceof ApiError && cause.status === 502) {
      throw new ApiError('Authentication service temporarily unavailable.', 502)
    }
    throw cause
  }
}

export async function logout() {
  try {
    await apiRequest('/logout', { method: 'POST' })
  } finally {
    clearAccessToken()
  }
}
