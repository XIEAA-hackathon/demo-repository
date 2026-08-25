import { useEffect, useMemo, useState } from "react";
import { API_URL } from "../services/api/config";
import "./Dashboard.css";

const formatTime = (seconds) => {
  const safe = Math.max(0, seconds);
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
};

function LeaderboardDisplay({ token, onUnauthorized, onLogout }) {
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
        if (!response.ok) throw new Error("Leaderboard unavailable");
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
    if (display.timing.paused && display.timing.paused_remaining_seconds != null) {
      return display.timing.paused_remaining_seconds;
    }
    if (!display.timing.ends_at) return null;
    return Math.max(0, Math.ceil((new Date(display.timing.ends_at).getTime() - now) / 1000));
  }, [display, now]);

  const mode = display?.mode;
  const isRoundOne = mode === "ROUND1_LIVE";
  const isWildcard = mode === "WILDCARD_LIVE";
  const isFinal = mode === "RESULTS_PUBLISHED";
  const title = isRoundOne ? "ROUND 1 — LIVE" : isWildcard ? "WILDCARD — LIVE" : isFinal ? "FINAL RESULTS" : "EVENT LEADERBOARD";
  const rows = isFinal && display?.results ? [
    { rank: 1, team_name: display.results.first_place.team_name },
    { rank: 2, team_name: display.results.second_place.team_name },
    { rank: 3, team_name: display.results.third_place.team_name },
  ] : (display?.rows || []);

  return (
    <main className="leaderboard-page">

      <button className="leaderboard-logout" onClick={() => void onLogout()}>LOG OUT</button>

      <header className="leaderboard-header">

        <div className="display-brand">
          BID TO BUILD
        </div>

        <h1>
          {title}
        </h1>

        <div className="auction-status">
          {display?.status_label || (connection === "live" ? "WAITING FOR EVENT" : "RECONNECTING")}
        </div>

      </header>


      {isRoundOne && display?.problem && <section className="leaderboard-problem">
        <span>PROBLEM #{display.problem.problem_number ?? display.problem.number}</span>
        <strong>{display.problem.title}</strong>
        {display.problem.description && <p>{display.problem.description}</p>}
      </section>}

      {isWildcard && <div className="leaderboard-slots">WILDCARD SLOTS: <strong>{display?.slot_count ?? "—"}</strong></div>}

      <section className="leaderboard-card">

        <div className="leaderboard-heading">
          <span>RANK</span>
          <span>TEAM</span>
          <span>{isFinal ? "PLACE" : "BID"}</span>
          <span>STATUS</span>
        </div>


        <div className="leaderboard-list">

          {rows.map((row) => (

            <div
              className={`leaderboard-row ${row.rank <= 5 ? "top-five" : ""}`}
              key={`${row.rank}-${row.team_id || row.team_name}`}
            >

              <div className="rank">
                {row.rank}
              </div>

              <div className="team-name">
                {row.team_name}

                {!isFinal && row.rank <= 5 && (
                  <span className="top-five-badge">
                    {isWildcard && row.rank <= (display?.slot_count || 0) ? "IN SLOT" : "TOP 5"}
                  </span>
                )}
              </div>

              <div className="bid-amount">
                {isFinal ? `${row.rank}${row.rank === 1 ? "st" : row.rank === 2 ? "nd" : "rd"}` : row.value}
                {!isFinal && <small> coins</small>}
              </div>

              <div className="bid-time">
                {isFinal ? "WINNER" : connection === "live" ? "LIVE" : "UPDATING"}
              </div>

            </div>

          ))}

          {!rows.length && <div className="leaderboard-empty">
            <strong>{display?.status_label || "Connecting to the event"}</strong>
            <span>{connection === "live" ? "Live rankings will appear when bidding starts." : "Trying to restore the live display…"}</span>
          </div>}

        </div>

      </section>


      {(isRoundOne || isWildcard) && remaining !== null && <div className="leaderboard-countdown">
        {display?.timing?.paused ? "PAUSED" : "AUCTION TIME"}&nbsp;&nbsp; {formatTime(remaining)}
      </div>}

    </main>
  );
}

export default LeaderboardDisplay;
