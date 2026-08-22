import { API_URL } from '../../services/api/config'

const TOKEN_KEY = 'bid_to_build_participant_token'

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
  }
}

export const getAccessToken = () => localStorage.getItem(TOKEN_KEY)
export const setAccessToken = (token: string) => localStorage.setItem(TOKEN_KEY, token)
export const clearAccessToken = () => localStorage.removeItem(TOKEN_KEY)

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getAccessToken()
  const headers = new Headers(options.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData) && !(options.body instanceof URLSearchParams)) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, { ...options, headers })
  } catch {
    throw new ApiError('Cannot reach the event server. Check your connection and try again.', 0)
  }

  const data = await response.json().catch(() => null) as { detail?: string; message?: string } | null
  if (!response.ok) {
    if (response.status === 401) {
      clearAccessToken()
      window.dispatchEvent(new Event('participant:unauthorized'))
    }
    if (response.status === 409 || response.status === 503) {
      window.dispatchEvent(new Event('participant:resync'))
    }
    throw new ApiError(data?.detail || data?.message || `Request failed (${response.status}).`, response.status)
  }
  return data as T
}
