import { useCallback, useEffect, useRef, useState } from "react";
import Login from "../admin/pages/Login";
import { connectReconnectingSocket } from "../services/realtime/connectReconnectingSocket";
import { WS_URL } from "../services/api/config";
import LabAllocationPanel from "../labs/LabAllocationPanel";
import { applyLabChange } from "../labs/labBoard";
import {
  clearLabAdminToken,
  getLabAdminSession,
  getLabAdminToken,
  getLabAllocation,
  hasLabAdminToken,
  labAdminLogin,
  labAdminLogout,
  moveLabAssignment,
} from "./services/api";

export default function LabAdminApp() {
  const [authenticated, setAuthenticated] = useState(hasLabAdminToken());
  const [checking, setChecking] = useState(hasLabAdminToken());
  const [session, setSession] = useState(null);
  useEffect(() => {
    const unauthorized = () => { clearLabAdminToken(); window.history.replaceState({}, "", "/lab-admin/login"); setAuthenticated(false); };
    window.addEventListener("lab-admin:unauthorized", unauthorized);
    if (hasLabAdminToken()) getLabAdminSession().then(next => { setSession(next); window.history.replaceState({}, "", "/lab-admin"); setAuthenticated(true); }).catch(unauthorized).finally(() => setChecking(false));
    return () => window.removeEventListener("lab-admin:unauthorized", unauthorized);
  }, []);
  if (checking) return <div className="loading-screen"><div className="loader" />Validating Lab Admin session…</div>;
  if (!authenticated) return <Login variant="lab" authenticate={labAdminLogin} onLogin={() => { window.history.replaceState({}, "", "/lab-admin"); setAuthenticated(true); }} />;
  return <LabAdminBoard session={session} onLogout={async () => { await labAdminLogout(); window.history.replaceState({}, "", "/lab-admin/login"); setAuthenticated(false); }} />;
}

export function LabAdminBoard({ onLogout, session = null }) {
  const [page, setPage] = useState("labs");
  const revision = useRef(0);
  const [board, setBoard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [socketStatus, setSocketStatus] = useState("connecting");
  const loadInFlight = useRef(null);
  const load = useCallback(() => {
    if (loadInFlight.current) return loadInFlight.current;
    const startedRevision = revision.current;
    const request = getLabAllocation()
      .then(nextBoard => { if (revision.current === startedRevision) setBoard(nextBoard); setError(""); })
      .catch((cause) => { setError(cause.message || "Lab allocation could not be loaded."); })
      .finally(() => {
        setLoading(false); loadInFlight.current = null;
        // A delta may have arrived before the initial board existed.
        if (revision.current !== startedRevision) void load();
      });
    loadInFlight.current = request;
    return request;
  }, []);
  useEffect(() => { void load(); }, [load]);
  const wildcardReadySeen = useRef(false);
  useEffect(() => { if (board?.can_move) wildcardReadySeen.current = true; }, [board?.can_move]);
  useEffect(() => {
    const disconnect = connectReconnectingSocket({
      url: `${WS_URL}/ws/auction`,
      getToken: getLabAdminToken,
      onStatus: setSocketStatus,
      onMessage: (message) => {
        if (message.type === "lab_assignment_changed") { revision.current += 1; setBoard(current => applyLabChange(current, message.payload)); return; }
        const wildcardEnded = message.type === "wildcard_ended"
          || (message.type === "event_state_changed" && Boolean(message.payload?.rounds?.WILDCARD?.ended));
        if (wildcardEnded && !wildcardReadySeen.current) {
          wildcardReadySeen.current = true;
          revision.current += 1; // discard a pre-completion GET already in flight
          void load();
        }
      },
      heartbeatIntervalMs: 20_000,
      heartbeatMessage: () => JSON.stringify({ type: "heartbeat", client_time: Date.now() }),
    });
    return disconnect;
  }, [load]);
  const connected = socketStatus === "connected" || socketStatus === "reconnected";
  return (
    <div className="app-shell lab-admin-shell">
      <aside className="sidebar lab-admin-sidebar">
        <div className="sidebar-brand"><div className="sidebar-logo">L</div><div><strong>Bid to Build</strong><span>LAB OPERATIONS</span></div></div>
        <nav className="sidebar-nav" aria-label="Lab Admin"><span className="sidebar-section-title">Workspace</span>{["teams", "labs"].map(item => <button key={item} className={`nav-item ${page === item ? "active" : ""}`} type="button" onClick={() => setPage(item)}><span className="nav-label">{item === "teams" ? "Teams" : "Labs"}</span></button>)}</nav>
        <div className="sidebar-bottom"><div className="admin-profile"><div className="admin-avatar">L</div><div><strong>{session?.name || "Lab Admin"}</strong><span>Placement access only</span></div></div><button className="logout-button" onClick={onLogout}>Log out</button></div>
      </aside>
      <main className="main-content">
        <header className="topbar"><div><h1>{page === "teams" ? "Teams" : "Labs"}</h1><p>Final team placement after problem allocation</p></div><div className="lab-connection"><i className={`status-dot ${connected ? "online" : "degraded"}`} /><span>{connected ? "Live" : "Reconnecting"}</span></div></header>
        <div className="page-content"><LabAllocationPanel board={board} loading={loading} error={error} onReload={load} onMove={moveLabAssignment} onBoardChange={change => { revision.current += 1; setBoard(change); }} view={page} canMove /></div>
      </main>
    </div>
  );
}
