import { WS_URL } from "../../services/api/config";
import { connectReconnectingSocket } from "../../services/realtime/connectReconnectingSocket";
import { getToken } from "./api";

export function connectAuctionSocket({ onMessage, onStatus } = {}) {
  return connectReconnectingSocket({
    url: `${WS_URL}/ws/auction`,
    getToken,
    onMessage,
    onStatus,
    heartbeatIntervalMs: 20_000,
    heartbeatMessage: () => JSON.stringify({ type: "heartbeat", client_time: Date.now() }),
  });
}
