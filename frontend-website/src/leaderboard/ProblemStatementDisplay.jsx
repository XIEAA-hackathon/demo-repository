import { useEffect, useState } from "react";
import { API_URL } from "../services/api/config";
import { useReconciledCountdown } from "../services/realtime/useReconciledCountdown";
import "./Dashboard.css";

const formatTime = (seconds) => {
  const safe = Math.max(0, seconds);
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
};

function ProblemStatementDisplay({ token, onUnauthorized, onLogout }) {
  const [display, setDisplay] = useState(null);
  const [apiStatus, setApiStatus] = useState("checking");

  useEffect(() => {
    let active = true;
    let timer;
    let failures = 0;
    let hasDisplay = false;
    let inFlight = false;
    const schedule = (delay) => {
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(load, delay);
    };
    const load = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const response = await fetch(`${API_URL}/public/leaderboard`, {
          cache: "no-store",
          headers: { Authorization: `Bearer ${token}` },
        });
        if (response.status === 401) {
          onUnauthorized();
          return;
        }
        if (!response.ok) throw new Error("Problem display unavailable");
        const payload = await response.json();
        if (payload.timing) payload.timing = { ...payload.timing, received_at: Date.now() };
        if (active) {
          failures = 0;
          hasDisplay = true;
          setDisplay(payload);
          setApiStatus("healthy");
        }
      } catch {
        if (active) {
          failures += 1;
          setApiStatus(hasDisplay ? "degraded" : "offline");
        }
      } finally {
        inFlight = false;
        if (active) schedule(failures ? Math.min(30_000, 1000 * 2 ** failures) : document.hidden ? 30_000 : 2000);
      }
    };
    const onVisibility = () => schedule(document.hidden ? 30_000 : 0);
    void load();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [onUnauthorized, token]);

  const timing = display?.timing ?? null;
  const remaining = useReconciledCountdown(timing, `${display?.event_state ?? "waiting"}:${timing?.ends_at ? "active" : "inactive"}`);
  const apiLive = apiStatus === "healthy";

  const problem = display?.problem;

  return (
    <main className="problem-statement-page">

      <button className="leaderboard-logout" onClick={() => void onLogout()}>LOG OUT</button>

      <div className="display-brand">
        BID TO BUILD
      </div>

      <section className="problem-display-card" aria-live="polite">
        {problem ? <>

        <div className="problem-number">
          PROBLEM #{problem.problem_number ?? problem.number}
        </div>

        <h1>
          {problem.title}
        </h1>

        <p className="problem-description">
          {problem.description}
        </p>

        <div className="problem-info">

          <div className="problem-info-item">
            <span>TIME REMAINING</span>
            <strong>{remaining === null ? "—" : formatTime(remaining)}</strong>
          </div>

          <div className="problem-info-item">
            <span>STATUS</span>
            <strong>
              {apiLive ? display.status_label : apiStatus === "degraded" ? "SYNC DEGRADED" : "DISPLAY OFFLINE"}
            </strong>
          </div>

        </div></> : <>
          <div className="problem-number">CURRENT PROBLEM</div>
          <h1>{apiLive ? "Waiting for the current problem" : "Refreshing the event display"}</h1>
          <p className="problem-description">{apiLive ? "The selected problem will appear here automatically." : "The last display state is preserved while polling recovers."}</p>
        </>}

      </section>

    </main>
  );
}

export default ProblemStatementDisplay;
