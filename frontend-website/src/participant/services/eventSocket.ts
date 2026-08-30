import { WS_URL } from '../../services/api/config'
import { connectReconnectingSocket } from '../../services/realtime/connectReconnectingSocket'
import { clearAccessToken, getAccessToken } from './apiClient'

const configuredHeartbeatSeconds = Number(import.meta.env.VITE_SESSION_HEARTBEAT_SECONDS || 20)
export const PARTICIPANT_HEARTBEAT_INTERVAL_MS = (
  Number.isFinite(configuredHeartbeatSeconds) && configuredHeartbeatSeconds > 0
    ? configuredHeartbeatSeconds
    : 20
) * 1_000

export interface EventMessage {
  type: string
  server_time: string
  version: number
  payload: Record<string, unknown>
}

export function connectEventSocket(onMessage: (message: EventMessage) => void, onStatus?: (status: string) => void) {
  return connectReconnectingSocket<EventMessage>({
    url: `${WS_URL}/ws/auction`,
    getToken: getAccessToken,
    onMessage: (message) => {
      if (message.type !== 'session_heartbeat') onMessage(message)
    },
    onStatus,
    heartbeatIntervalMs: PARTICIPANT_HEARTBEAT_INTERVAL_MS,
    heartbeatMessage: 'heartbeat',
    onUnauthorized: () => {
      clearAccessToken()
      window.dispatchEvent(new Event('participant:unauthorized'))
    },
  })
}
