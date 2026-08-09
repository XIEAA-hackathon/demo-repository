import { WS_URL } from '../../config/env'
import { getAccessToken } from '../../services/apiClient'

export interface EventMessage {
  type: string
  server_time: string
  payload: Record<string, unknown>
}

export function connectEventSocket(onMessage: (message: EventMessage) => void, onStatus?: (status: string) => void) {
  let socket: WebSocket | null = null
  let stopped = false
  let attempt = 0
  let retryTimer: number | undefined

  const connect = () => {
    const token = getAccessToken()
    if (!token || stopped) return
    onStatus?.('connecting')
    socket = new WebSocket(`${WS_URL}/ws/auction?token=${encodeURIComponent(token)}`)
    socket.onopen = () => { attempt = 0; onStatus?.('connected') }
    socket.onmessage = (event) => {
      try { onMessage(JSON.parse(event.data) as EventMessage) } catch { /* Ignore malformed frames. */ }
    }
    socket.onerror = () => onStatus?.('error')
    socket.onclose = (event) => {
      onStatus?.('disconnected')
      if (stopped || event.code === 4401) return
      const delay = Math.min(30_000, 1_000 * 2 ** attempt++)
      retryTimer = window.setTimeout(connect, delay)
    }
  }
  connect()
  return () => {
    stopped = true
    if (retryTimer) window.clearTimeout(retryTimer)
    socket?.close()
  }
}
