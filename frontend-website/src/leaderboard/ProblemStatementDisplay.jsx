import { useEffect, useMemo, useState } from "react";
import { API_URL } from "../services/api/config";
import "./Dashboard.css";

const formatTime = (seconds) => {
  const safe = Math.max(0, seconds);
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
};

function ProblemStatementDisplay({ token, onUnauthorized, onLogout }) {
  const [display, setDisplay] = useState(null);
  const [connection, setConnection] = useState("reconnecting");
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    let active = true;
    let timer;
    let failures = 0;
    const schedule = (delay) => {
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(load, delay);
    };
    const load = async () => {
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
        if (active) {
          failures = 0;
          setDisplay(payload);
          setConnection("live");
        }
      } catch {
        if (active) {
          failures += 1;
          setConnection("reconnecting");
        }
      } finally {
        if (active) schedule(failures ? Math.min(30_000, 1000 * 2 ** failures) : document.hidden ? 30_000 : 2000);
      }
    };
    const onVisibility = () => { if (!document.hidden) schedule(0); };
    void load();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [onUnauthorized, token]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const remaining = useMemo(() => {
    if (!display?.timing) return null;
    if (display.timing.paused && display.timing.paused_remaining_seconds != null) return display.timing.paused_remaining_seconds;
    if (!display.timing.ends_at) return null;
    return Math.max(0, Math.ceil((new Date(display.timing.ends_at).getTime() - now) / 1000));
  }, [display, now]);

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
              {connection === "live" ? display.status_label : "RECONNECTING"}
            </strong>
          </div>

        </div></> : <>
          <div className="problem-number">CURRENT PROBLEM</div>
          <h1>{connection === "live" ? "Waiting for the current problem" : "Reconnecting to the event"}</h1>
          <p className="problem-description">{connection === "live" ? "The selected problem will appear here automatically." : "The display will recover without a refresh."}</p>
        </>}

      </section>

    </main>
  );
}

export default ProblemStatementDisplay;
