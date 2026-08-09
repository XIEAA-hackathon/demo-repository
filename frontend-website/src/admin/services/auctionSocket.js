import { WS_URL } from "../../services/api/config";
import { connectReconnectingSocket } from "../../services/realtime/connectReconnectingSocket";
import { getToken } from "./api";

export function connectAuctionSocket({ onMessage, onStatus } = {}) {
  return connectReconnectingSocket({
    url: `${WS_URL}/ws/auction`,
    getToken,
    onMessage,
    onStatus,
  });
}
