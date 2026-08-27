import { useEffect, useState } from "react";
import { API_URL } from "../services/api/config";
import { WS_URL } from "../services/api/config";
import { connectReconnectingSocket } from "../services/realtime/connectReconnectingSocket";
import { useReconciledCountdown } from "../services/realtime/useReconciledCountdown";
import "./Dashboard.css";

const formatTime = (seconds) => {
  const safe = Math.max(0, seconds);
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
};

function LeaderboardDisplay({ token, onUnauthorized, onLogout }) {
  const [display, setDisplay] = useState(null);
  const [apiStatus, setApiStatus] = useState("checking");

  useEffect(() => {
    let active = true;
    let timer;
    let failures = 0;
    let hasDisplay = false;
    let inFlight = false;
    let socketConnected = false;
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
        if (!response.ok) throw new Error("Leaderboard unavailable");
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
        if (active) schedule(failures ? Math.min(30_000, 1000 * 2 ** failures) : document.hidden && socketConnected ? 60_000 : socketConnected ? 30_000 : 12_000);
      }
    };
    const onVisibility = () => schedule(document.hidden ? 30_000 : 0);
    const disconnect = connectReconnectingSocket({
      url: `${WS_URL}/ws/auction`,
      getToken: () => token,
      onStatus: (status) => {
        socketConnected = status === "connected" || status === "reconnected";
        if (status === "reconnected") schedule(0);
      },
      onMessage: (message) => {
        if (message.type === "bid_updated" || message.type === "wildcard_bid_updated") {
          const liveRound = message.payload?.round;
          const rows = message.payload?.leaderboard;
          if (!Array.isArray(rows)) return;
          setDisplay((current) => {
            if (!current || (liveRound === "ROUND1" && current.mode !== "ROUND1_LIVE") || (liveRound === "WILDCARD" && current.mode !== "WILDCARD_LIVE")) return current;
            return { ...current, rows: rows.map((row) => ({ rank: row.rank, team_id: row.team_id, team_name: row.team_name, value: row.amount })) };
          });
          return;
        }
        schedule(200);
      },
    });
    void load();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
      disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [onUnauthorized, token]);

  const timing = display?.timing ?? null;
  const remaining = useReconciledCountdown(timing, `${display?.event_state ?? "waiting"}:${timing?.ends_at ? "active" : "inactive"}`);
  const apiLive = apiStatus === "healthy";

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
          {display?.status_label || (apiStatus === "checking" ? "CONNECTING TO EVENT" : apiStatus === "offline" ? "DISPLAY OFFLINE" : "WAITING FOR EVENT")}
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
                {isFinal ? "WINNER" : apiLive ? "CURRENT" : "LAST SYNC"}
              </div>

            </div>

          ))}

          {!rows.length && <div className="leaderboard-empty">
            <strong>{display?.status_label || "Connecting to the event"}</strong>
            <span>{apiLive ? "Live rankings will appear when bidding starts." : "Trying to refresh the event display…"}</span>
          </div>}

        </div>

      </section>


      {(isRoundOne || isWildcard) && timing?.ends_at && <div className="leaderboard-countdown">
        {display?.timing?.paused ? "PAUSED" : "AUCTION TIME"}&nbsp;&nbsp; {formatTime(remaining)}
      </div>}

    </main>
  );
}

export default LeaderboardDisplay;
