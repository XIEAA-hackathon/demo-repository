import { apiRequest, clearAccessToken, setAccessToken } from './apiClient'

interface TokenResponse {
  access_token: string
  token_type: string
}

export async function login(email: string, password: string) {
  const body = new URLSearchParams({ username: email.trim(), password })
  const response = await apiRequest<TokenResponse>('/login', { method: 'POST', body })
  setAccessToken(response.access_token)
}

export async function logout() {
  try {
    await apiRequest('/logout', { method: 'POST' })
  } finally {
    clearAccessToken()
  }
}
