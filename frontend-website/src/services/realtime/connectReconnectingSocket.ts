export type RealtimeStatus = 'connecting' | 'connected' | 'error' | 'disconnected'

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

  const connect = () => {
    const token = getToken()
    if (!token || stopped) return

    onStatus?.('connecting')
    socket = new WebSocket(`${url}?token=${encodeURIComponent(token)}`)
    socket.onopen = () => {
      attempt = 0
      onStatus?.('connected')
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
      onStatus?.('disconnected')
      if (stopped || event.code === 4401) return
      retryTimer = window.setTimeout(connect, Math.min(30_000, 1_000 * 2 ** attempt++))
    }
  }

  connect()
  return () => {
    stopped = true
    if (retryTimer !== undefined) window.clearTimeout(retryTimer)
    socket?.close()
  }
}
