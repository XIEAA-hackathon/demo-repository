import { useCallback, useEffect, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { API_URL } from "../services/api/config";
import LeaderboardDisplay from "./LeaderboardDisplay";
import ProblemStatementDisplay from "./ProblemStatementDisplay";
import "./Dashboard.css";

const DISPLAY_TOKEN_KEY = "bid_to_build_display_token";
const DEFAULT_LOGIN_ID = "leaderboard@bidtobuild.example.com";

function Dashboard() {
  const [token, setToken] = useState(() => localStorage.getItem(DISPLAY_TOKEN_KEY) || "");
  const [loginId, setLoginId] = useState(DEFAULT_LOGIN_ID);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const clearSession = useCallback(() => {
    localStorage.removeItem(DISPLAY_TOKEN_KEY);
    setToken("");
  }, []);

  useEffect(() => {
    const syncSession = (event) => {
      if (event.key === DISPLAY_TOKEN_KEY) setToken(event.newValue || "");
    };
    window.addEventListener("storage", syncSession);
    return () => window.removeEventListener("storage", syncSession);
  }, []);

  const logout = useCallback(async () => {
    try {
      await fetch(`${API_URL}/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
    } finally {
      clearSession();
    }
  }, [clearSession, token]);

  const login = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const body = new URLSearchParams({ username: loginId.trim(), password });
      const response = await fetch(`${API_URL}/leaderboard/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "Display login failed. Check the login ID and password.");
      }
      const payload = await response.json();
      localStorage.setItem(DISPLAY_TOKEN_KEY, payload.access_token);
      setToken(payload.access_token);
      setPassword("");
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Display login failed.");
    } finally {
      setSubmitting(false);
    }
  };

  if (token) {
    const path = window.location.pathname.replace(/\/+$/, "");
    if (path.endsWith("/problem")) {
      return <ProblemStatementDisplay token={token} onUnauthorized={clearSession} onLogout={logout} />;
    }
    if (path.endsWith("/live")) {
      return <LeaderboardDisplay token={token} onUnauthorized={clearSession} onLogout={logout} />;
    }
    const openDisplay = (route) => window.open(route, "_blank", "noopener,noreferrer");
    return <main className="dashboard-page">
      <button className="leaderboard-logout" onClick={() => void logout()}>LOG OUT</button>
      <header className="dashboard-header">
        <p className="dashboard-label">BID TO BUILD</p>
        <h1>Dashboard</h1>
        <p className="dashboard-subtitle">Select the display mode for the event screen.</p>
      </header>
      <section className="dashboard-options">
        <button className="dashboard-option ps-option" onClick={() => openDisplay("/leaderboard/problem")}>
          <div className="dashboard-option-icon" aria-hidden="true">📺</div>
          <div className="dashboard-option-content">
            <span className="dashboard-option-label">DISPLAY 01</span>
            <h2>Problem Statement</h2>
            <p>Display the current problem statement, auction information and countdown for the audience.</p>
          </div>
          <span className="dashboard-arrow">→</span>
        </button>
        <button className="dashboard-option leaderboard-option" onClick={() => openDisplay("/leaderboard/live")}>
          <div className="dashboard-option-icon" aria-hidden="true">🏆</div>
          <div className="dashboard-option-content">
            <span className="dashboard-option-label">DISPLAY 02</span>
            <h2>Live Leaderboard</h2>
            <p>Display live bidding rankings, bid amounts, bid times and the current auction status.</p>
          </div>
          <span className="dashboard-arrow">→</span>
        </button>
      </section>
      <footer className="dashboard-footer">Bid to Build • Live Event Dashboard</footer>
    </main>;
  }

  return <main className="leaderboard-page leaderboard-login-page">
    <form className="leaderboard-login-card" onSubmit={login}>
      <div className="display-brand">BID TO BUILD</div>
      <h1>Display Login</h1>
      <label htmlFor="leaderboard-login-id">Login ID</label>
      <input
        id="leaderboard-login-id"
        autoComplete="username"
        value={loginId}
        onChange={(event) => setLoginId(event.target.value)}
        required
      />
      <label htmlFor="leaderboard-password">Password</label>
      <div className="leaderboard-password-field">
        <input
          id="leaderboard-password"
          type={showPassword ? "text" : "password"}
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
        <button type="button" aria-label={showPassword ? "Hide password" : "Show password"} title={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword((visible) => !visible)}>
          {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
        </button>
      </div>
      {error && <p className="leaderboard-login-error" role="alert">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? "OPENING…" : "OPEN LEADERBOARD"}
      </button>
    </form>
  </main>;
}

export default Dashboard;
