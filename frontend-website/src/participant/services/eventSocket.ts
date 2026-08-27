import { WS_URL } from '../../services/api/config'
import { connectReconnectingSocket } from '../../services/realtime/connectReconnectingSocket'
import { getAccessToken } from './apiClient'

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
    onMessage,
    onStatus,
  })
}
