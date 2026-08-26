export type RealtimeStatus = 'connecting' | 'connected' | 'reconnecting' | 'reconnected' | 'error' | 'disconnected'

interface ReconnectingSocketOptions<T> {
  url: string
  getToken: () => string | null
  onMessage?: (message: T) => void
  onStatus?: (status: RealtimeStatus) => void
}

export function connectReconnectingSocket<T>({
  url,
  getToken,
  onMessage,
  onStatus,
}: ReconnectingSocketOptions<T>) {
  let socket: WebSocket | null = null
  let stopped = false
  let attempt = 0
  let retryTimer: number | undefined
  let settledTimer: number | undefined

  const connect = () => {
    const token = getToken()
    if (!token || stopped) return

    onStatus?.(attempt > 0 ? 'reconnecting' : 'connecting')
    socket = new WebSocket(`${url}?token=${encodeURIComponent(token)}`)
    socket.onopen = () => {
      const recovered = attempt > 0
      attempt = 0
      onStatus?.(recovered ? 'reconnected' : 'connected')
      if (recovered) settledTimer = window.setTimeout(() => onStatus?.('connected'), 2_000)
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
      console.info('[realtime] WebSocket closed', {
        code: event.code,
        reason: (event.reason || '').slice(0, 160),
        timestamp: new Date().toISOString(),
        wasClean: event.wasClean,
      })
      onStatus?.(stopped ? 'disconnected' : 'reconnecting')
      if (stopped || event.code === 4401) return
      retryTimer = window.setTimeout(connect, Math.min(30_000, 1_000 * 2 ** attempt++))
    }
  }

  connect()
  return () => {
    stopped = true
    if (retryTimer !== undefined) window.clearTimeout(retryTimer)
    if (settledTimer !== undefined) window.clearTimeout(settledTimer)
    socket?.close()
  }
}
