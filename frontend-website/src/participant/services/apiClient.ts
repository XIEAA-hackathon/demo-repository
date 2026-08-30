import { API_URL } from '../../services/api/config'
import { clearAccessToken, getAccessToken } from './participantToken'

export { clearAccessToken, getAccessToken, setAccessToken } from './participantToken'

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly retryAfterSeconds?: number) {
    super(message)
  }
}

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

  const data = await response.json().catch(() => null) as { detail?: string; message?: string; retry_after_seconds?: number } | null
  if (!response.ok) {
    if (response.status === 401) {
      clearAccessToken()
      window.dispatchEvent(new Event('participant:unauthorized'))
    }
    if (response.status === 409 || response.status === 429 || response.status === 503) {
      window.dispatchEvent(new Event('participant:resync'))
    }
    const retryAfterHeader = Number(response.headers.get('Retry-After'))
    throw new ApiError(
      data?.detail || data?.message || `Request failed (${response.status}).`,
      response.status,
      data?.retry_after_seconds || (Number.isFinite(retryAfterHeader) ? retryAfterHeader : undefined),
    )
  }
  return data as T
}
