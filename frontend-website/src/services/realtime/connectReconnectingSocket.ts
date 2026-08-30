export type RealtimeStatus = 'connecting' | 'connected' | 'reconnecting' | 'reconnected' | 'error' | 'disconnected'

interface ReconnectingSocketOptions<T> {
  url: string
  getToken: () => string | null
  onMessage?: (message: T) => void
  onStatus?: (status: RealtimeStatus) => void
  onUnauthorized?: () => void
  heartbeatIntervalMs?: number
  heartbeatMessage?: string
}

export function connectReconnectingSocket<T>({
  url,
  getToken,
  onMessage,
  onStatus,
  onUnauthorized,
  heartbeatIntervalMs,
  heartbeatMessage = 'heartbeat',
}: ReconnectingSocketOptions<T>) {
  let socket: WebSocket | null = null
  let stopped = false
  let attempt = 0
  let retryTimer: number | undefined
  let settledTimer: number | undefined
  let heartbeatTimer: number | undefined

  const stopHeartbeat = () => {
    if (heartbeatTimer !== undefined) {
      window.clearInterval(heartbeatTimer)
      heartbeatTimer = undefined
    }
  }

  const connect = () => {
    const token = getToken()
    if (!token || stopped) return

    onStatus?.(attempt > 0 ? 'reconnecting' : 'connecting')
    socket = new WebSocket(`${url}?token=${encodeURIComponent(token)}`)
    socket.onopen = () => {
      const recovered = attempt > 0
      attempt = 0
      if (settledTimer !== undefined) window.clearTimeout(settledTimer)
      onStatus?.(recovered ? 'reconnected' : 'connected')
      if (recovered) settledTimer = window.setTimeout(() => onStatus?.('connected'), 2_000)
      stopHeartbeat()
      if (heartbeatIntervalMs && heartbeatIntervalMs > 0) {
        heartbeatTimer = window.setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) socket.send(heartbeatMessage)
        }, heartbeatIntervalMs)
      }
    }
    socket.onmessage = (event) => {
      try {
        onMessage?.(JSON.parse(event.data) as T)
      } catch {
        // Ignore malformed frames and keep the live connection open.
      }
    }
    socket.onerror = () => onStatus?.('error')
    socket.onclose = (event) => {
      stopHeartbeat()
      if (settledTimer !== undefined) {
        window.clearTimeout(settledTimer)
        settledTimer = undefined
      }
      console.info('[realtime] WebSocket closed', {
        code: event.code,
        reason: (event.reason || '').slice(0, 160),
        timestamp: new Date().toISOString(),
        wasClean: event.wasClean,
      })
      if (stopped || event.code === 4401) {
        onStatus?.('disconnected')
        if (!stopped && event.code === 4401) onUnauthorized?.()
        return
      }
      onStatus?.('reconnecting')
      const baseDelay = Math.min(30_000, 1_000 * 2 ** attempt++)
      const jitteredDelay = Math.round(baseDelay * (0.85 + Math.random() * 0.3))
      retryTimer = window.setTimeout(connect, jitteredDelay)
    }
  }

  connect()
  return () => {
    stopped = true
    if (retryTimer !== undefined) window.clearTimeout(retryTimer)
    if (settledTimer !== undefined) window.clearTimeout(settledTimer)
    stopHeartbeat()
    socket?.close()
  }
}
