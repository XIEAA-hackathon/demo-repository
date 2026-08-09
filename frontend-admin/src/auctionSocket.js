import { WS_URL } from "./config";
import { getToken } from "./api";

export function connectAuctionSocket({ onMessage, onStatus } = {}) {
  let socket;
  let stopped = false;
  let attempt = 0;
  let retryTimer;
  const connect = () => {
    const token = getToken();
    if (!token || stopped) return;
    onStatus?.("connecting");
    socket = new WebSocket(`${WS_URL}/ws/auction?token=${encodeURIComponent(token)}`);
    socket.onopen = () => { attempt = 0; onStatus?.("connected"); };
    socket.onmessage = (event) => { try { onMessage?.(JSON.parse(event.data)); } catch { /* ignore malformed frame */ } };
    socket.onerror = () => onStatus?.("error");
    socket.onclose = (event) => {
      onStatus?.("disconnected");
      if (stopped || event.code === 4401) return;
      retryTimer = window.setTimeout(connect, Math.min(30000, 1000 * 2 ** attempt++));
    };
  };
  connect();
  return () => { stopped = true; window.clearTimeout(retryTimer); socket?.close(); };
}
