import { useCallback, useEffect, useRef, useState } from "react";
import Login from "./pages/Login";
import {
  addTime, approveTeam, clearToken, deleteTeam, downloadRegistrationAssignments, downloadRegistrationCredentials, downloadRegistrationDemo, downloadRegistrationSample, finalizeProblem,
  getAdminConfig, getAdminState, getBidHistory, getLeaderboard,
  getProblemStatements, getTeamCredentials, getTeams, hasToken, logout, pauseTimer,
  importRegistrations, removeTime, resetParticipantPassword, resumeTimer, setProblemVisibility,
  resetRegistrationCredentials, getImportedParticipantAccounts, setImportedParticipantPassword,
  updateAdminConfig, createTeamCredentials, getRoundControl, importRoundProblems, downloadRoundProblemSample,
  downloadRoundOneAssignments, downloadWildcardAssignments,
  selectRoundProblem, startRoundPreview, startRoundBidding, closeRoundBidding, assignRoundWinners,
  confirmRoundOneAutoAllotment, endRoundOne, openWildcardApplications, closeWildcardApplications,
  confirmWildcardSlots, startWildcardSlotBidding, closeWildcardSlotBidding, endWildcardSelectionTurn,
  getAdminSubmissions, openSubmissions, closeSubmissions, ApiError,
  getJudging, saveJudgingWinners, publishJudgingResults,
  getAdminHealth, runPreflight, getRecoveryState, resumeRecoveryTimer, reloadRecoveryState,
  resyncClients, retryCurrentTransition, getActivityLog, developmentReset, resetEventData,
  getManagedAdminUsers, createManagedAdminUser, getManagedLeaderboardUsers,
  createManagedLeaderboardUser, resetManagedUserPassword, resetManagedUsers,
} from "./services/api";
import { connectAuctionSocket } from "./services/auctionSocket";
import { classifyApiStatus, deriveServerRemaining, isSyncStale, projectCountdown, shouldApplyTimerSnapshot } from "../services/realtime/timerReconciliation";

const labels = {
  WAITING: "Waiting", ROUND1_PREVIEW: "Round 1 preview", ROUND1_BIDDING: "Round 1 bidding",
  ROUND1_RESULT: "Round 1 result", WILDCARD_APPLICATION: "Wildcard applications",
  WILDCARD_BIDDING: "Wildcard slot bidding",
  WILDCARD_SELECTION: "Wildcard selection", CODING: "Coding", SUBMISSION: "Submission",
  JUDGING_WAIT: "Judging", RESULTS: "Results",
};

function App() {
  const [authenticated, setAuthenticated] = useState(hasToken());
  const [checking, setChecking] = useState(hasToken());
  useEffect(() => {
    const unauthorized = () => { clearToken(); setAuthenticated(false); };
    window.addEventListener("admin:unauthorized", unauthorized);
    if (hasToken()) getAdminState().then(() => setAuthenticated(true)).catch(unauthorized).finally(() => setChecking(false));
    return () => window.removeEventListener("admin:unauthorized", unauthorized);
  }, []);
  if (checking) return <div className="loading-screen"><div className="loader" />Validating administrator session…</div>;
  if (!authenticated) return <Login onLogin={() => setAuthenticated(true)} />;
  return <AdminApplication onLogout={async () => { await logout(); setAuthenticated(false); }} />;
}

function useServerCountdown(timing, timerKey) {
  const initialNow = Date.now();
  const initialRemaining = deriveServerRemaining(timing, initialNow);
  const anchorRef = useRef({ remaining: initialRemaining, localAt: initialNow, paused: Boolean(timing?.paused) });
  const snapshotRef = useRef({ timing, timerKey });
  const remainingRef = useRef(initialRemaining);
  const [remaining, setRemaining] = useState(initialRemaining);

  useEffect(() => {
    const localNow = Date.now();
    const serverRemaining = deriveServerRemaining(timing, localNow);
    const expectedRemaining = projectCountdown(anchorRef.current, localNow);
    if (shouldApplyTimerSnapshot({
      previousTiming: snapshotRef.current.timing,
      previousTimerKey: snapshotRef.current.timerKey,
      nextTiming: timing,
      nextTimerKey: timerKey,
      expectedRemaining,
      serverRemaining,
    })) {
      anchorRef.current = { remaining: serverRemaining, localAt: localNow, paused: Boolean(timing?.paused) };
      remainingRef.current = serverRemaining;
      setRemaining(serverRemaining);
    }
    snapshotRef.current = { timing, timerKey };
  }, [timing, timerKey]);

  useEffect(() => {
    const tick = () => {
      const next = projectCountdown(anchorRef.current, Date.now());
      if (next !== remainingRef.current) {
        remainingRef.current = next;
        setRemaining(next);
      }
    };
    const first = setTimeout(tick, 0);
    const interval = setInterval(tick, 1000);
    return () => { clearTimeout(first); clearInterval(interval); };
  }, []);
  return remaining;
}

function AdminApplication({ onLogout }) {
  const [page, setPage] = useState("dashboard");
  const [teams, setTeams] = useState([]);
  const [problems, setProblems] = useState([]);
  const [bids, setBids] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [state, setState] = useState(null);
  const [config, setConfig] = useState(null);
  const [socketStatus, setSocketStatus] = useState("connecting");
  const [apiStatus, setApiStatus] = useState("checking");
  const [health, setHealth] = useState(null);
  const [lastSyncAt, setLastSyncAt] = useState(null);
  const [clockNow, setClockNow] = useState(Date.now());
  const [documentHidden, setDocumentHidden] = useState(() => document.hidden);
  const [visibilityRefreshPending, setVisibilityRefreshPending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const loadInFlight = useRef(null);
  const lastSuccessfulLoadStartedAt = useRef(0);

  const load = useCallback(() => {
    if (loadInFlight.current) return loadInFlight.current;
    const startedAt = Date.now();
    const request = (async () => {
      try {
        const results = await Promise.allSettled([
          getTeams(), getProblemStatements(), getBidHistory(), getLeaderboard(), getAdminState(), getAdminConfig(),
        ]);
        const [teamResult, problemResult, bidResult, boardResult, eventStateResult, configResult] = results;
        const fulfilled = (result) => result.status === "fulfilled";
        const eventStateFresh = fulfilled(eventStateResult);

        if (fulfilled(teamResult)) setTeams(teamResult.value);
        if (fulfilled(problemResult)) setProblems(problemResult.value);
        if (fulfilled(bidResult)) setBids(bidResult.value);
        if (fulfilled(boardResult)) setLeaderboard(boardResult.value.teams || boardResult.value);
        if (fulfilled(configResult)) setConfig(configResult.value);

        let healthFailed = false;
        try {
          setHealth({ backend: "connected", database: "healthy", ...await getAdminHealth() });
        } catch {
          healthFailed = true;
        }

        if (eventStateFresh) {
          const syncedAt = Date.now();
          const eventState = eventStateResult.value;
          setState({ ...eventState, timing: { ...eventState.timing, received_at: syncedAt } });
          setLastSyncAt(syncedAt);
          lastSuccessfulLoadStartedAt.current = startedAt;
        }

        setApiStatus(classifyApiStatus(results, healthFailed));
        if (!eventStateFresh) {
          const cause = eventStateResult.reason;
          setError(cause?.message || "Live event state could not be refreshed. The last timer snapshot is being preserved.");
        } else {
          setError("");
        }
        return eventStateFresh;
      } catch (cause) { setApiStatus("offline"); setError(cause.message || "Unable to load event data."); return false; }
      finally { setLoading(false); }
    })();
    loadInFlight.current = request;
    void request.finally(() => { if (loadInFlight.current === request) loadInFlight.current = null; });
    return request;
  }, []);

  useEffect(() => { const id = setTimeout(() => void load(), 0); return () => clearTimeout(id); }, [load]);
  useEffect(() => { const resync = () => { void load(); }; window.addEventListener("admin:resync", resync); return () => window.removeEventListener("admin:resync", resync); }, [load]);
  useEffect(() => {
    let stopped = false; let timer; let failures = 0;
    const schedule = (delay) => {
      clearTimeout(timer);
      timer = window.setTimeout(async () => {
        if (stopped) return;
        const ok = await load();
        if (stopped) return;
        failures = ok ? 0 : failures + 1;
        schedule(ok ? (document.hidden ? 30000 : 5000) : Math.min(30000, 1000 * 2 ** failures));
      }, delay);
    };
    const onVisibility = () => {
      const hidden = document.hidden;
      setDocumentHidden(hidden);
      if (hidden) return;
      clearTimeout(timer);
      setVisibilityRefreshPending(true);
      void load().then((ok) => {
        if (stopped) return;
        failures = ok ? 0 : failures + 1;
        schedule(ok ? 5000 : Math.min(30000, 1000 * 2 ** failures));
      }).finally(() => { if (!stopped) setVisibilityRefreshPending(false); });
    };
    schedule(5000); document.addEventListener("visibilitychange", onVisibility);
    return () => { stopped = true; clearTimeout(timer); document.removeEventListener("visibilitychange", onVisibility); };
  }, [load]);
  useEffect(() => {
    let timer;
    let latestEventAt = 0;
    const queueLoad = () => {
      if (document.hidden) return;
      latestEventAt = Date.now();
      clearTimeout(timer);
      timer = setTimeout(() => {
        if (lastSuccessfulLoadStartedAt.current < latestEventAt) void load();
      }, 300);
    };
    const disconnect = connectAuctionSocket({
      onStatus: (status) => { setSocketStatus(status); if (status === "reconnected") queueLoad(); },
      onMessage: queueLoad,
    });
    return () => { clearTimeout(timer); disconnect(); };
  }, [load]);
  useEffect(() => { const timer = setInterval(() => setClockNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  const remaining = useServerCountdown(state?.timing, state?.event_state);
  const staleSeconds = lastSyncAt ? Math.floor((clockNow - lastSyncAt) / 1000) : null;
  const stale = isSyncStale({ documentHidden, refreshPending: visibilityRefreshPending, staleSeconds });
  const socketConnected = socketStatus === "connected" || socketStatus === "reconnected";
  const socketLabel = socketConnected ? "Connected" : socketStatus === "connecting" ? "Connecting" : socketStatus === "error" || socketStatus === "disconnected" ? "Disconnected" : "Reconnecting";
  const apiLabel = apiStatus === "healthy" ? "Healthy" : apiStatus === "degraded" ? "Degraded" : apiStatus === "offline" ? "Offline" : "Checking";
  const databaseLabel = health?.database === "healthy" ? "Healthy" : apiStatus === "offline" ? "Unavailable" : "Checking";
  const syncLabel = documentHidden ? "Paused while hidden" : visibilityRefreshPending ? "Refreshing" : stale ? "Stale" : "Fresh";

  const action = async (operation, success) => {
    try { setError(""); setNotice(""); await operation(); setNotice(success); await load(); }
    catch (cause) { setError(cause.message || "Action failed."); }
  };
  if (loading) return <div className="loading-screen"><div className="loader" />Loading live control center…</div>;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand"><div className="sidebar-logo">♠</div><div><strong>Bid to Build</strong><span>Admin control</span></div></div>
        <nav className="sidebar-nav">
          <span className="sidebar-section-title">Event</span>
          {[["dashboard", "Overview", "⌂"], ["round1", "Round 1", "1"], ["wildcard", "Wildcard", "W"], ["submission", "Submission", "S"], ["judging", "Judging", "J"], ["recovery", "Recovery", "R"]].map(([id, label, icon]) => (
            <button key={id} aria-label={label} className={`nav-item ${page === id ? "active" : ""}`} onClick={() => setPage(id)}><span className="nav-icon">{icon}</span><span className="nav-label">{label}</span></button>
          ))}
          <span className="sidebar-section-title sidebar-section-title--management">Management</span>
          {[["admin-users", "Admin Users", "A"], ["leaderboard-users", "Leaderboard Users", "D"], ["teams", "Teams", "T"], ["problems", "Problems", "P"], ["imports", "Registration import", "⇧"], ["leaderboard", "Leaderboard", "≡"], ["activity", "Event log", "L"]].map(([id, label, icon]) => (
            <button key={id} aria-label={label} className={`nav-item ${page === id ? "active" : ""}`} onClick={() => setPage(id)}><span className="nav-icon">{icon}</span><span className="nav-label">{label}</span></button>
          ))}
        </nav>
        <div className="sidebar-bottom"><div className="admin-profile"><div className="admin-avatar">A</div><div><strong>Event Admin</strong><span>Backend verified</span></div></div><button className="logout-button" onClick={onLogout}>Log out</button></div>
      </aside>
      <main className="main-content">
        <header className="topbar"><div><h1>{page === "round1" ? "Round 1" : page === "wildcard" ? "Wildcard" : page === "activity" ? "Event log" : page === "admin-users" ? "Admin Users" : page === "leaderboard-users" ? "Leaderboard Users" : page[0].toUpperCase() + page.slice(1)}</h1><p>Authoritative live event operations</p></div><div className="topbar-right"><div className="connection-health" aria-live="polite"><span><i className={`status-dot ${socketConnected ? "online" : socketStatus === "reconnecting" || socketStatus === "connecting" ? "degraded" : "offline"}`} />Live connection <strong>{socketLabel}</strong></span><span><i className={`status-dot ${apiStatus === "healthy" ? "online" : apiStatus === "degraded" || apiStatus === "checking" ? "degraded" : "offline"}`} />Backend/API <strong>{apiLabel}</strong></span><small>Database {databaseLabel} · Last sync {staleSeconds == null ? "pending" : `${staleSeconds}s ago`} · {syncLabel}</small></div><div className="event-date">CURRENT STAGE<strong>{labels[state?.event_state] || "—"}</strong></div></div></header>
        <div className="page-content">
          {stale && <div className="stale-state-warning" role="alert"><strong>LIVE DATA MAY BE STALE</strong><span>Last successful API synchronization: {staleSeconds == null ? "not yet completed" : `${staleSeconds} seconds ago`}. The live connection is tracked separately.</span></div>}
          {error && <div className="global-error"><span>{error}</span><button onClick={() => setError("")}>×</button></div>}
          {notice && <div className="admin-notice">{notice}</div>}
          {page === "dashboard" && <Dashboard teams={teams} problems={problems} bids={bids} state={state} remaining={remaining} />}
          {page === "round1" && <RoundControlPage round="round-1" state={state} config={config} remaining={remaining} onConfig={setConfig} />}
          {page === "wildcard" && <WildcardControlPage state={state} config={config} remaining={remaining} onConfig={setConfig} />}
          {page === "submission" && <SubmissionAdminPage />}
          {page === "judging" && <JudgingAdminPage onGlobalSync={load} />}
          {page === "admin-users" && <ManagedUsersPage kind="admin" />}
          {page === "leaderboard-users" && <ManagedUsersPage kind="leaderboard" />}
          {page === "teams" && <Teams teams={teams} onAction={action} />}
          {page === "problems" && <Problems problems={problems} state={state} onAction={action} />}
          {page === "imports" && <RegistrationImport onAction={action} />}
          {page === "leaderboard" && <Leaderboard rows={leaderboard} />}
          {page === "recovery" && <RecoveryPage onGlobalSync={load} onNavigate={setPage} />}
          {page === "activity" && <ActivityLogPage />}
        </div>
      </main>
    </div>
  );
}

function Dashboard({ teams, problems, bids, state, remaining }) {
  const [preflight, setPreflight] = useState(null);
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState("");
  const check = async () => { setChecking(true); setCheckError(""); try { setPreflight(await runPreflight()); } catch (cause) { setCheckError(cause.message || "Event check failed."); } finally { setChecking(false); } };
  return <section className="dashboard"><div className="hero-panel"><div><span className="eyebrow">LIVE EVENT STATE</span><h2>{labels[state?.event_state] || "Waiting"}</h2><p>Every connected participant receives state changes from the backend.</p></div><div className="hero-status"><span className="live-pulse" />{state?.timing?.paused ? "TIMER PAUSED" : remaining ? formatTime(remaining) : "READY"}</div></div><div className="stats-grid"><Stat label="REGISTERED TEAMS" value={teams.length} /><Stat label="PROBLEM STATEMENTS" value={problems.length} /><Stat label="BIDS RECEIVED" value={bids.length} /><Stat label="CURRENT ROUND" value={state?.current_round ?? 1} /></div><section className="preflight-panel"><div><h3>Event readiness</h3><p>Validate every live-event prerequisite without changing event state.</p></div><button className="primary-button" disabled={checking} onClick={() => void check()}>{checking ? "Running checks…" : "Run event check"}</button>{checkError && <div className="global-error" role="alert">{checkError}</div>}{preflight && <><strong className={`readiness-status readiness-status--${preflight.status.toLowerCase()}`}>{preflight.status}</strong><div className="preflight-list">{preflight.checks.map((item) => <div key={item.name}><span className={`check-mark check-mark--${item.status.toLowerCase()}`}>{item.status === "READY" ? "✓" : item.status === "WARNING" ? "!" : "×"}</span><span><strong>{item.name}</strong><small>{item.detail}</small></span></div>)}</div></>}</section></section>;
}

function RoundControlPage({ round, state, config, remaining, onConfig }) {
  const isWildcard = round === "wildcard";
  const [data, setData] = useState(null);
  const [file, setFile] = useState(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [autoDeduction, setAutoDeduction] = useState("");
  const [autoConfirming, setAutoConfirming] = useState(false);
  const loadRound = useCallback(() => getRoundControl(round).then(setData).catch((cause) => setError(cause.message)), [round]);
  useEffect(() => { void loadRound(); }, [loadRound, state?.timing?.server_time]);
  const run = async (operation, success) => {
    setWorking(true); setError(""); setNotice("");
    try { const result = await operation(); if (result?.round_type) setData(result); setNotice(success); await loadRound(); }
    catch (cause) { setError(cause.message || "Action failed."); if (cause instanceof ApiError && [409, 503].includes(cause.status)) await loadRound(); }
    finally { setWorking(false); }
  };
  const downloadSample = async () => {
    try {
      const blob = await downloadRoundProblemSample(round);
      const url = URL.createObjectURL(blob); const link = document.createElement("a");
      link.href = url; link.download = `${round}-problems-sample.csv`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (cause) { setError(cause.message); }
  };
  const downloadAssignments = async () => {
    setWorking(true); setError("");
    try {
      const blob = await downloadRoundOneAssignments();
      const url = URL.createObjectURL(blob); const link = document.createElement("a");
      link.href = url; link.download = "bid_to_build_round_1_assignments.xlsx"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
      setNotice("Round 1 assignments downloaded.");
    } catch (cause) { setError(cause.message || "Round 1 assignments could not be downloaded."); }
    finally { setWorking(false); }
  };
  const saveSettings = () => run(() => updateAdminConfig(config), `${isWildcard ? "Wildcard" : "Round 1"} timer settings saved.`);
  const current = data?.current_problem;
  const finalAuto = data?.final_auto_assignment;
  useEffect(() => {
    if (finalAuto?.status === "PENDING") setAutoDeduction(String(finalAuto.suggested_deduction));
  }, [finalAuto?.problem?.id, finalAuto?.status, finalAuto?.suggested_deduction]);
  const confirmAutoAllotment = async () => {
    const deduction = Number(autoDeduction);
    if (!Number.isInteger(deduction) || deduction < 0) {
      setError("Deduction per team must be a whole number of zero or greater.");
      return;
    }
    setAutoConfirming(false);
    await run(() => confirmRoundOneAutoAllotment(deduction), "Final Round 1 problem allotted to every remaining team.");
  };
  const eventState = data?.event?.event_state;
  const hasTimer = Boolean(state?.timing?.ends_at || state?.timing?.paused);
  const afterBidding = current && data?.status === "READY" && eventState === (isWildcard ? "WILDCARD_SELECTION" : "ROUND1_RESULT");
  if (!data) return <div className="loading-screen"><div className="loader" />Loading round controls…</div>;

  return <section className="round-console">
    <header className="round-console__header">
      <div><span className="eyebrow">EVENT / {isWildcard ? "WILDCARD" : "ROUND 1"}</span><h2>{isWildcard ? "Wildcard" : "Round 1"}</h2><p>{isWildcard ? "Manage applications, wildcard problems, and bidding." : "Manage problem preview, bidding, and team assignments."}</p></div>
      <a className="round-leaderboard-button" href="/leaderboard" target="_blank" rel="noreferrer">Open public leaderboard ↗</a>
    </header>

    {error && <div className="global-error"><span>{error}</span><button onClick={() => setError("")}>×</button></div>}
    {notice && <div className="admin-notice">{notice}</div>}

    {isWildcard && <section className="round-applications">
      <div><span className="eyebrow">APPLICATIONS</span><h3>{data.applications.applied} / {data.applications.eligible} applied</h3><p>{data.applications.declined} declined · {data.applications.pending} pending</p></div>
      <div className="round-application-clock"><strong>{data.applications.open ? formatTime(remaining) : "00:00:00"}</strong><span>{data.applications.open ? "Applications open" : "Applications closed"}</span></div>
      <div className="round-inline-actions">
        {!data.applications.open ? <button className="primary-button" disabled={working} onClick={() => run(openWildcardApplications, "Wildcard applications opened.")}>Open applications</button> : <button className="danger-button" disabled={working} onClick={() => run(closeWildcardApplications, "Wildcard applications closed.")}>Close applications</button>}
        {data.applications.open && <TimerButtons state={state} remaining={remaining} run={run} />}
      </div>
    </section>}

    <div className="round-console__live">
      <article className="round-current-problem">
        <span className="eyebrow">CURRENT PROBLEM</span>
        {current ? <><strong className="round-problem-number">Problem #{current.problem_number}</strong><h3 className="round-current-title">{current.title}</h3><p className="round-current-description">{current.description}</p><span className={`round-status round-status--${data.status.toLowerCase()}`}>{data.status}</span></> : <div className="round-empty"><strong>No problem selected</strong><p>Choose any available problem from the bank below.</p></div>}
      </article>
      <article className="round-live-controls">
        <div><span className="eyebrow">LIVE CONTROLS</span><h3>{data.status === "PREVIEW" ? "Problem preview" : data.status === "BIDDING" ? `${isWildcard ? "Wildcard" : "Round 1"} — live bidding` : "Ready"}</h3></div>
        <div className="round-live-clock">{hasTimer ? formatTime(remaining) : "00:00:00"}</div>
        {data.status === "BIDDING" && <dl className="round-bid-metrics"><div><dt>Base bid price</dt><dd>{data.settings.base_price} coins</dd></div><div><dt>Current highest bid</dt><dd>{data.highest_bid ?? "—"}</dd></div><div><dt>Current highest team</dt><dd>{data.highest_team ?? "—"}</dd></div></dl>}
        {(data.status === "PREVIEW" || data.status === "BIDDING") && <TimerButtons state={state} remaining={remaining} run={run} />}
        <div className="round-primary-actions">
          {current && data.status === "READY" && !afterBidding && <button className="primary-button" disabled={working} onClick={() => run(() => startRoundPreview(round), "Preview started.")}>Start preview</button>}
          {data.status === "PREVIEW" && <button className="primary-button" disabled={working} onClick={() => run(() => startRoundBidding(round), "Bidding started.")}>End preview / start bidding</button>}
          {data.status === "BIDDING" && <button className="danger-button" disabled={working} onClick={() => run(() => closeRoundBidding(round), "Bidding closed.")}>Close bidding</button>}
          {afterBidding && <button className="primary-button" disabled={working} onClick={() => run(() => assignRoundWinners(round), "Winner assignment completed.")}>Assign winner(s)</button>}
        </div>
      </article>
    </div>

    <section className={`round-problem-bank ${!isWildcard ? "round-problem-bank--round1" : ""}`}>
      <div className="round-section-heading"><div><span className="eyebrow">{isWildcard ? "WILDCARD" : "ROUND 1"} PROBLEMS</span><h3>Problem bank</h3></div><div className="round-inline-actions"><label className="secondary-button round-upload">Upload XLSX / CSV<input type="file" accept=".xlsx,.csv" onChange={(event) => setFile(event.target.files?.[0] || null)} /></label><button className="secondary-button" onClick={() => void downloadSample()}>Download sample CSV</button>{file && <button className="primary-button" disabled={working} onClick={() => run(() => importRoundProblems(round, file), `${file.name} imported.`)}>Import {file.name}</button>}</div></div>
      <div className="round-problem-list">{data.problems.length ? data.problems.map((problem) => <article key={problem.id} className={`round-problem-row round-problem-row--${problem.status.toLowerCase()}`}><strong>#{problem.problem_number}</strong><div className="round-problem-copy"><b>{problem.title}</b><p title={problem.description}>{problem.description}</p></div><span>{problem.status}</span>{problem.status === "AVAILABLE" && !data.ended && !current && !(finalAuto?.status === "PENDING" && finalAuto.problem.id === problem.id) && <button className="secondary-button" onClick={() => run(() => selectRoundProblem(round, problem.id), `Problem #${problem.problem_number} selected.`)}>Select</button>}</article>) : <div className="round-empty"><strong>No problems imported</strong><p>Upload the organizer&apos;s XLSX or CSV problem bank.</p></div>}</div>
    </section>

    <section className={`round-settings ${!isWildcard ? "round-settings--round1" : ""}`}>
      <div><span className="eyebrow">SETTINGS</span><h3>{isWildcard ? "Wildcard configuration" : "Round settings"}</h3><p>Change durations before the corresponding timer starts.</p></div>
      {config && <div className="round-settings__fields">
        {isWildcard && <label>Application duration<input type="number" min="1" value={config.wildcard_application_seconds} onChange={(event) => onConfig({ ...config, wildcard_application_seconds: Number(event.target.value) })} /></label>}
        <label>Preview duration<input type="number" min="1" value={config[isWildcard ? "wildcard_preview_seconds" : "round1_preview_seconds"]} onChange={(event) => onConfig({ ...config, [isWildcard ? "wildcard_preview_seconds" : "round1_preview_seconds"]: Number(event.target.value) })} /></label>
        <label>Bidding duration<input type="number" min="1" value={config[isWildcard ? "wildcard_bid_seconds" : "round1_bid_seconds"]} onChange={(event) => onConfig({ ...config, [isWildcard ? "wildcard_bid_seconds" : "round1_bid_seconds"]: Number(event.target.value) })} /></label>
        {!isWildcard && <label>Participant bid cooldown<input type="number" min="0" max="60" value={config.bid_cooldown_seconds} onChange={(event) => onConfig({ ...config, bid_cooldown_seconds: Number(event.target.value) })} /></label>}
        {!isWildcard && <label>Base bid price<input type="number" min="0" value={config.round1_minimum_bid} onChange={(event) => onConfig({ ...config, round1_minimum_bid: Number(event.target.value) })} /></label>}
        {isWildcard && <label>Wildcard slots<input type="number" min="1" value={config.wildcard_slots} onChange={(event) => onConfig({ ...config, wildcard_slots: Number(event.target.value) })} /></label>}
        <button className={`${isWildcard ? "secondary-button" : "primary-button"} round-settings__save`} disabled={working} onClick={saveSettings}>{working ? "Saving…" : "Save settings"}</button>
      </div>}
      {!isWildcard && <button className="danger-link round-end" disabled={data.ended || working} onClick={() => window.confirm("End Round 1? No further Round 1 selection or bidding will be allowed.") && run(endRoundOne, "Round 1 ended. Wildcard can now be opened.")}>{data.ended ? "Round 1 ended" : "End Round 1"}</button>}
    </section>
    {!isWildcard && <section className="round-auto-allotment">
      {finalAuto ? <>
        <div className="round-auto-allotment__heading"><span className="eyebrow">LAST PROBLEM AUTO ALLOTMENT</span><h3>{finalAuto.status === "COMPLETED" ? "Final allotment completed" : "Confirm final allotment"}</h3></div>
        <dl className="round-auto-allotment__grid">
          <div><dt>Final Problem</dt><dd>#{finalAuto.problem.problem_number} — {finalAuto.problem.title}</dd></div>
          <div><dt>Remaining Teams</dt><dd>{finalAuto.team_count}<span className="round-auto-allotment__team-names">{finalAuto.teams.map((team) => team.team_name).join(", ")}</span></dd></div>
          <div><dt>Suggested Deduction</dt><dd>{finalAuto.suggested_deduction} coins</dd></div>
          <div><dt>Deduction Per Team</dt><dd>{finalAuto.status === "PENDING" ? <input aria-label="Deduction per team" type="number" min="0" step="1" value={autoDeduction} onChange={(event) => setAutoDeduction(event.target.value)} /> : `${finalAuto.deduction_per_team} coins`}</dd></div>
          <div><dt>Completed Auctions</dt><dd>{finalAuto.completed_auctions}</dd></div>
        </dl>
        {finalAuto.status === "PENDING" ? <button className="primary-button" disabled={working || autoDeduction === ""} onClick={() => setAutoConfirming(true)}>CONFIRM AUTO ALLOTMENT</button> : <div className="round-auto-allotment__teams"><strong>Assigned teams</strong><span>{finalAuto.teams.map((team) => team.team_name).join(", ")}</span></div>}
      </> : <>
        <div className="round-auto-allotment__heading"><span className="eyebrow">LAST PROBLEM AUTO ALLOTMENT</span><h3>Available at the final Round 1 problem</h3></div>
        <div className="round-empty"><strong>Waiting for the final allotment state</strong><p>The confirmation grid becomes available when exactly one unused Round 1 problem and at least one eligible unassigned team remain.</p></div>
      </>}
    </section>}
    {!isWildcard && <div className="round-export-action"><button className="secondary-button" disabled={working} onClick={() => void downloadAssignments()}>DOWNLOAD ROUND 1 ASSIGNMENTS</button></div>}
    {autoConfirming && finalAuto?.status === "PENDING" && <div className="judging-confirmation-backdrop"><section className="judging-confirmation" role="dialog" aria-modal="true" aria-labelledby="auto-allotment-title"><h3 id="auto-allotment-title">Confirm final problem auto allotment?</h3><p>Assign Problem #{finalAuto.problem.problem_number} — {finalAuto.problem.title} to all {finalAuto.team_count} remaining teams and deduct up to {autoDeduction} coins from each team?</p><div><button className="secondary-button" disabled={working} onClick={() => setAutoConfirming(false)}>Cancel</button><button className="primary-button" disabled={working} onClick={() => void confirmAutoAllotment()}>{working ? "Assigning…" : "Confirm Auto Allotment"}</button></div></section></div>}
  </section>;
}

function WildcardControlPage({ state, config, remaining, onConfig }) {
  const [data, setData] = useState(null);
  const selectionRemaining = useServerCountdown({ server_time: data?.event?.timing?.server_time, ends_at: data?.selection?.ends_at, received_at: data?.selection?.received_at, remaining_seconds: data?.selection?.remaining_seconds, paused: false }, data?.selection?.current_rank);
  const [tab, setTab] = useState("applications");
  const [slots, setSlots] = useState(1);
  const [file, setFile] = useState(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const load = useCallback(async () => { try { const result = await getRoundControl("wildcard"); result.selection.received_at = Date.now(); setData(result); if (result.slots?.count || result.settings?.wildcard_slots) setSlots(result.slots?.count || result.settings.wildcard_slots); setError(""); return result; } catch (cause) { setError(cause.message); return null; } }, []);
  useEffect(() => {
    let stopped = false; let timer;
    const poll = async () => { const result = await load(); if (stopped) return; const live = ["APPLICATIONS_OPEN", "BIDDING_OPEN", "PROBLEM_SELECTION"].includes(result?.status); timer = setTimeout(poll, document.hidden ? 60000 : live ? 2000 : 15000); };
    void poll();
    const onVisibility = () => { if (!document.hidden) { clearTimeout(timer); void poll(); } };
    document.addEventListener("visibilitychange", onVisibility);
    return () => { stopped = true; clearTimeout(timer); document.removeEventListener("visibilitychange", onVisibility); };
  }, [load]);
  useEffect(() => {
    if (data?.status === "APPLICATIONS_CLOSED" || data?.status === "BIDDING_OPEN" || data?.status === "BIDDING_CLOSED") setTab("bidding");
    if (data?.status === "PROBLEM_SELECTION" || data?.status === "COMPLETE") setTab("selection");
  }, [data?.status]);
  const run = async (operation, success) => {
    setWorking(true); setError(""); setNotice("");
    try { await operation(); setNotice(success); await load(); }
    catch (cause) { setError(cause.message || "Action failed."); if (cause instanceof ApiError && [409, 503].includes(cause.status)) await load(); }
    finally { setWorking(false); }
  };
  const downloadSample = async () => {
    try {
      const blob = await downloadRoundProblemSample("wildcard"); const url = URL.createObjectURL(blob);
      const link = document.createElement("a"); link.href = url; link.download = "wildcard-problems-sample.csv"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (cause) { setError(cause.message); }
  };
  const downloadAssignments = async () => {
    setWorking(true); setError("");
    try {
      const blob = await downloadWildcardAssignments();
      const url = URL.createObjectURL(blob); const link = document.createElement("a");
      link.href = url; link.download = "bid_to_build_wildcard_assignments.xlsx"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
      setNotice("Wildcard assignments downloaded.");
    } catch (cause) { setError(cause.message || "Wildcard assignments could not be downloaded."); }
    finally { setWorking(false); }
  };
  if (!data) return <div className="loading-screen"><div className="loader" />Loading wildcard controls…</div>;
  const maxSlots = data.slots.maximum || 0;
  const canConfirmSlots = data.status === "APPLICATIONS_CLOSED" && maxSlots > 0;
  const stageCopy = {
    NOT_STARTED: "Ready to collect applications",
    APPLICATIONS_OPEN: "Applications are open",
    APPLICATIONS_CLOSED: "Confirm how many teams advance",
    BIDDING_OPEN: "Slot bidding is live",
    BIDDING_CLOSED: "Bidding has closed",
    PROBLEM_SELECTION: "Qualified teams are choosing in rank order",
    COMPLETE: "Wildcard is complete",
  }[data.status] || data.status;
  const nextAutomaticProblem = data.selection.available_problems?.[0];
  const endTurn = () => {
    if (!data.selection.current_rank || !data.selection.current_team_id || !nextAutomaticProblem) return;
    const confirmed = window.confirm(`End ${data.selection.current_team}'s selection turn?\n\nThey will automatically receive:\nProblem #${nextAutomaticProblem.problem_number} — ${nextAutomaticProblem.title}`);
    if (confirmed) void run(() => endWildcardSelectionTurn(data.selection.current_rank, data.selection.current_team_id), `${data.selection.current_team}'s turn ended and Problem #${nextAutomaticProblem.problem_number} was assigned.`);
  };

  return <section className="round-console wildcard-console">
    <header className="round-console__header"><div><span className="eyebrow">EVENT / WILDCARD</span><h2>Wildcard</h2><p>Applications, one slot auction, then ranked problem selection.</p></div><a className="round-leaderboard-button" href="/leaderboard" target="_blank" rel="noreferrer">Open public leaderboard ↗</a></header>
    {error && <div className="global-error" role="alert"><span>{error}</span><button onClick={() => setError("")}>×</button></div>}
    {notice && <div className="admin-notice">{notice}</div>}
    <section className="wildcard-stage-banner"><div><span className="eyebrow">CURRENT STATUS</span><h3>{stageCopy}</h3></div><strong>{data.status.replaceAll("_", " ")}</strong></section>
    <div className="wildcard-tabs" role="tablist" aria-label="Wildcard stages">
      {[["applications", "1", "Applications"], ["bidding", "2", "Slot bidding"], ["selection", "3", "Problem selection"]].map(([id, number, label]) => <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}><span>{number}</span>{label}</button>)}
    </div>

    {config && <section className="wildcard-stage-card wildcard-settings-panel"><div><span className="eyebrow">WILDCARD SETTINGS</span><h3>Timing and auction controls</h3><p>Selection timing applies separately to each ranked team.</p></div><div className="wildcard-settings-grid"><label>Application duration<input type="number" min="1" value={config.wildcard_application_seconds} onChange={(event) => onConfig({ ...config, wildcard_application_seconds: Number(event.target.value) })} /></label><label>Bidding duration<input type="number" min="1" value={config.wildcard_bid_seconds} onChange={(event) => onConfig({ ...config, wildcard_bid_seconds: Number(event.target.value) })} /></label><label>Participant bid cooldown<input type="number" min="0" max="60" value={config.bid_cooldown_seconds} onChange={(event) => onConfig({ ...config, bid_cooldown_seconds: Number(event.target.value) })} /></label><label>Problem selection time<input type="number" min="5" max="300" value={config.wildcard_selection_seconds ?? 30} onChange={(event) => onConfig({ ...config, wildcard_selection_seconds: Number(event.target.value) })} /><small>seconds · 5–300</small></label><label>Wildcard slots<input type="number" min="1" value={config.wildcard_slots} onChange={(event) => { const value = Number(event.target.value); onConfig({ ...config, wildcard_slots: value }); if (!data.slots.confirmed) setSlots(value); }} /></label><label>Wildcard base bid price<input type="number" min="0" value={config.wildcard_starting_bid} onChange={(event) => onConfig({ ...config, wildcard_starting_bid: Number(event.target.value) })} /></label></div><button className="primary-button wildcard-settings-save" disabled={working} onClick={() => run(() => updateAdminConfig(config), "Wildcard settings saved.")}>{working ? "Saving…" : "Save Wildcard settings"}</button></section>}

    {tab === "applications" && <div className="wildcard-panel-grid">
      <section className="round-applications wildcard-stage-card"><div><span className="eyebrow">APPLICATION RESPONSE</span><h3>{data.applications.applied} applied</h3><p>{data.applications.declined} declined · {data.applications.pending} pending · {data.applications.eligible} eligible</p></div><div className="round-application-clock"><strong>{data.applications.open ? formatTime(remaining) : "00:00:00"}</strong><span>{data.applications.open ? "Applications open" : data.applications.status}</span></div><div className="round-inline-actions">{data.status === "NOT_STARTED" && !data.slots.confirmed && <button className="primary-button" disabled={working} onClick={() => run(openWildcardApplications, "Wildcard applications opened.")}>Open applications</button>}{data.applications.open && <><button className="danger-button" disabled={working} onClick={() => run(closeWildcardApplications, "Wildcard applications closed.")}>Close applications</button><TimerButtons state={state} remaining={remaining} run={run} /></>}</div></section>
      <section className="round-settings wildcard-stage-card"><div><span className="eyebrow">APPLICATION TIMER</span><h3>Application window</h3><p>{config?.wildcard_application_seconds ?? 60} seconds configured in Wildcard settings.</p></div></section>
    </div>}

    {tab === "bidding" && <div className="wildcard-panel-grid">
      <section className="wildcard-stage-card wildcard-slots"><div><span className="eyebrow">AVAILABLE SLOTS</span><h3>Choose advancing teams</h3><p>Slots cannot exceed applied teams or available wildcard problems.</p></div><div className="wildcard-slot-control"><label>Slots<input type="number" min="1" max={Math.max(1, maxSlots)} value={slots} onChange={(event) => setSlots(Number(event.target.value))} /></label><span>Maximum now: <strong>{maxSlots}</strong></span><button className="primary-button" disabled={!canConfirmSlots || working || slots < 1 || slots > maxSlots} onClick={() => run(() => confirmWildcardSlots(slots), `${slots} wildcard slot${slots === 1 ? "" : "s"} confirmed.`)}>{data.slots.confirmed ? `Confirmed: ${data.slots.count}` : "Confirm slots"}</button></div></section>
      <section className="wildcard-stage-card wildcard-live-bidding"><div><span className="eyebrow">ONE SLOT AUCTION</span><h3>{data.bidding.open ? "Bidding is live" : data.status === "BIDDING_CLOSED" ? "Bidding expired · ready to finalize" : data.slots.confirmed ? "Ready for slot bidding" : "Confirm slots first"}</h3><p>Each applicant submits one fixed +5, +10, or +25 bid. Higher bid ranks first; equal bids keep the earlier timestamp.</p></div><div>{data.bidding.open ? <div><div className="round-live-clock">{formatTime(remaining)}</div><p>Base bid price: <strong>{config?.wildcard_starting_bid ?? 0} coins</strong> · cooldown: <strong>{config?.bid_cooldown_seconds ?? 5}s</strong></p></div> : <p>Bidding duration: <strong>{config?.wildcard_bid_seconds ?? 180}s</strong> · Base bid: <strong>{config?.wildcard_starting_bid ?? 0} coins</strong></p>}</div><div className="round-inline-actions">{data.status === "APPLICATIONS_CLOSED" && data.slots.confirmed && <button className="primary-button" disabled={working} onClick={() => run(startWildcardSlotBidding, "Wildcard slot bidding started.")}>Start slot bidding</button>}{data.bidding.open && <><button className="danger-button" disabled={working} onClick={() => window.confirm("Close slot bidding and charge the top ranked teams?") && run(closeWildcardSlotBidding, "Slot bidding finalized.")}>Close and rank</button><TimerButtons state={state} remaining={remaining} run={run} /></>}{data.status === "BIDDING_CLOSED" && <button className="primary-button" disabled={working} onClick={() => window.confirm("Finalize the frozen ranking and charge qualified teams?") && run(closeWildcardSlotBidding, "Slot bidding finalized.")}>Finalize ranking</button>}</div></section>
      <section className="wildcard-stage-card wildcard-ranking"><div className="round-section-heading"><div><span className="eyebrow">LIVE RANKING</span><h3>{data.bidding.ranking.length} bids received</h3></div><span className="wildcard-slot-badge">TOP {data.slots.count || "—"} QUALIFY</span></div>{data.bidding.ranking.length ? <div className="wildcard-rank-list">{data.bidding.ranking.map((row) => <div key={row.team_id}><strong>#{row.rank}</strong><span>{row.team_name}</span><b>{row.value} coins</b>{row.qualified && <em>Qualified</em>}</div>)}</div> : <div className="round-empty"><strong>No bids yet</strong><p>The ranking updates live while bidding is open.</p></div>}</section>
    </div>}

    {tab === "selection" && <div className="wildcard-panel-grid">
      <section className="wildcard-stage-card wildcard-selection-progress"><div className="round-section-heading"><div><span className="eyebrow">SEQUENTIAL SELECTION</span><h3>{data.status === "COMPLETE" ? "All problems selected" : data.selection.current_team ? `${data.selection.current_team} is choosing` : "Waiting for selection"}</h3></div>{data.selection.current_rank && <span className="wildcard-slot-badge">RANK #{data.selection.current_rank}</span>}</div>{data.selection.current_team && <div className="wildcard-current-turn"><div><span>Current turn</span><strong>Rank #{data.selection.current_rank}</strong><b>{data.selection.current_team}</b></div><div><span>Time remaining</span><strong>{formatTime(selectionRemaining).slice(3)}</strong></div><div><span>Remaining problems</span><strong>{data.selection.available_problems.length}</strong></div><button className="danger-button" disabled={working || !nextAutomaticProblem} onClick={endTurn}>End turn</button></div>}{data.selection.pool_frozen && <div className="active-pool"><strong>Active pool · {data.selection.pool.length} frozen problems</strong><span>{data.selection.pool.map((entry) => `#${entry.problem.problem_number}${entry.selected ? " selected" : ""}`).join(" · ")}</span><small>Later uploads and refreshes cannot change this selection pool.</small></div>}<div className="wildcard-qualification-list">{data.selection.qualifications.length ? data.selection.qualifications.map((row) => <article key={row.team_id}><strong>#{row.rank}</strong><div><b>{row.team_name}</b><span>{row.problem ? `Selected Problem #${row.problem.problem_number}` : `${row.winning_bid} coin winning bid`}</span></div><em className={`selection-status selection-status--${row.status.toLowerCase()}`}>{row.status === "CHOOSING" ? "CHOOSING NOW" : row.status}</em></article>) : <div className="round-empty"><strong>No qualified teams</strong><p>Close slot bidding to determine the selection order.</p></div>}</div></section>
      <section className="round-problem-bank wildcard-stage-card"><div className="round-section-heading"><div><span className="eyebrow">WILDCARD PROBLEMS</span><h3>Separate problem bank</h3></div><div className="round-inline-actions"><label className="secondary-button round-upload">Upload XLSX / CSV<input type="file" accept=".xlsx,.csv" onChange={(event) => setFile(event.target.files?.[0] || null)} /></label><button className="secondary-button" onClick={() => void downloadSample()}>Download sample CSV</button>{file && <button className="primary-button" disabled={working} onClick={() => run(() => importRoundProblems("wildcard", file), `${file.name} imported.`)}>Import {file.name}</button>}</div></div><div className="round-problem-list">{data.problems.length ? data.problems.map((problem) => <article key={problem.id} className={`round-problem-row round-problem-row--${problem.status.toLowerCase()}`}><strong>#{problem.problem_number}</strong><div className="round-problem-copy"><b>{problem.title}</b><p title={problem.description}>{problem.description}</p></div><span>{problem.status}</span></article>) : <div className="round-empty"><strong>No wildcard problems imported</strong><p>Upload XLSX or CSV before confirming slots.</p></div>}</div></section>
    </div>}
    <div className="round-export-action"><button className="secondary-button" disabled={working} onClick={() => void downloadAssignments()}>DOWNLOAD WILDCARD ASSIGNMENTS</button></div>
  </section>;
}

function SubmissionAdminPage() {
  const [data, setData] = useState(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [working, setWorking] = useState(false);
  const load = useCallback(async () => { try { const result = await getAdminSubmissions(); setData(result); setError(""); return result; } catch (cause) { setError(cause.message); return null; } }, []);
  useEffect(() => { let stopped = false; let timer; const poll = async () => { const result = await load(); if (!stopped) timer = setTimeout(poll, document.hidden ? 60000 : result?.open ? 3000 : 30000); }; void poll(); return () => { stopped = true; clearTimeout(timer); }; }, [load]);
  const run = async (operation, success) => { setWorking(true); setError(""); setNotice(""); try { setData(await operation()); setNotice(success); } catch (cause) { setError(cause.message || "Action failed."); } finally { setWorking(false); } };
  const rows = (data?.rows || []).filter((row) => row.team_name.toLowerCase().includes(query.trim().toLowerCase()));
  if (!data) return <div className="loading-screen"><div className="loader" />Loading submissions…</div>;
  return <section className="submission-admin"><header className="submission-admin__header"><div><span className="eyebrow">EVENT / SUBMISSION</span><h2>Submission monitor</h2><p>Open or close the window and track each team’s final GitHub repository.</p></div><button className={data.open ? "danger-button" : "primary-button"} disabled={working} onClick={() => run(data.open ? closeSubmissions : openSubmissions, data.open ? "Submissions closed." : "Submissions opened.")}>{data.open ? "Close submissions" : "Open submissions"}</button></header>{error && <div className="global-error" role="alert">{error}</div>}{notice && <div className="admin-notice">{notice}</div>}<div className="submission-stats"><Stat label="WINDOW" value={data.open ? "OPEN" : "CLOSED"} /><Stat label="TOTAL TEAMS" value={data.total} /><Stat label="SUBMITTED" value={data.submitted} /><Stat label="PENDING" value={data.pending} /></div><div className="submission-table-panel"><div className="submission-toolbar"><div><h3>Team repositories</h3><span>{data.open ? "Live monitoring every three seconds." : "Closed window checks every thirty seconds."}</span></div><input aria-label="Search teams" placeholder="Search team…" value={query} onChange={(event) => setQuery(event.target.value)} /></div><div className="table-wrapper"><table><thead><tr><th>TEAM</th><th>FINAL PROBLEM</th><th>STATUS</th><th>GITHUB URL</th><th>SUBMITTED BY</th><th>UPDATED</th></tr></thead><tbody>{rows.map((row) => <tr key={row.team_id}><td><strong>{row.team_name}</strong></td><td>{row.final_problem ? `#${row.final_problem.ps_number} · ${row.final_problem.title}` : "—"}</td><td><span className={`table-status ${row.status === "SUBMITTED" ? "active" : "pending"}`}>{row.status}</span></td><td>{row.github_url ? <a href={row.github_url} target="_blank" rel="noreferrer">Open repository ↗</a> : "—"}</td><td>{row.submitted_by || "—"}</td><td>{row.updated_at || row.submitted_at ? new Date(row.updated_at || row.submitted_at).toLocaleString() : "—"}</td></tr>)}</tbody></table></div></div></section>;
}

function SearchableTeamSelector({ label, teams, value, onChange, disabled }) {
  const selected = teams.find((team) => team.team_id === value);
  const [query, setQuery] = useState(selected?.team_name || "");
  useEffect(() => { setQuery(selected?.team_name || ""); }, [selected?.team_name]);
  const listId = `judging-${label.toLowerCase().replaceAll(" ", "-")}`;
  const update = (next) => {
    setQuery(next);
    const exact = teams.find((team) => team.team_name.toLowerCase() === next.trim().toLowerCase());
    onChange(exact?.team_id || null);
  };
  return <label className="judging-selector"><span>{label}</span><input type="search" list={listId} value={query} onChange={(event) => update(event.target.value)} placeholder="Search registered teams…" autoComplete="off" disabled={disabled} aria-invalid={Boolean(query && !value)} /><datalist id={listId}>{teams.map((team) => <option key={team.team_id} value={team.team_name} />)}</datalist>{query && !value && <small>Select an exact registered team from the list.</small>}</label>;
}

function JudgingAdminPage({ onGlobalSync }) {
  const [data, setData] = useState(null);
  const [winners, setWinners] = useState({ first: null, second: null, third: null });
  const [working, setWorking] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const load = useCallback(async () => {
    try {
      const result = await getJudging();
      setData(result);
      setWinners({ first: result.first_place?.team_id || null, second: result.second_place?.team_id || null, third: result.third_place?.team_id || null });
      setError("");
    } catch (cause) { setError(cause.message || "Judging data could not be loaded."); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  if (!data) return <div className="loading-screen"><div className="loader" />Loading judging…</div>;
  const selectedIds = [winners.first, winners.second, winners.third];
  const complete = selectedIds.every(Boolean);
  const unique = complete && new Set(selectedIds).size === 3;
  const published = data.result_status === "PUBLISHED";
  const savedIds = [data.first_place?.team_id, data.second_place?.team_id, data.third_place?.team_id];
  const selectionsMatchSaved = complete && selectedIds.every((id, index) => id === savedIds[index]);
  const teamName = (id) => data.teams.find((team) => team.team_id === id)?.team_name || "—";
  const save = async () => {
    if (!complete || !unique) { setError(complete ? "Each place must use a different registered team." : "Select a registered team for all three places."); return; }
    setWorking(true); setError(""); setNotice("");
    try {
      const result = await saveJudgingWinners({ first_place_team_id: winners.first, second_place_team_id: winners.second, third_place_team_id: winners.third });
      setData((current) => ({ ...current, ...result }));
      setNotice("Winners saved privately. Participants and the public display still show judging in progress.");
    } catch (cause) { setError(cause.message || "Winners could not be saved."); }
    finally { setWorking(false); }
  };
  const publish = async () => {
    setWorking(true); setError(""); setNotice("");
    try {
      const result = await publishJudgingResults();
      setData((current) => ({ ...current, ...result }));
      setConfirming(false);
      setNotice("Final results are now visible to participants and the public leaderboard.");
      await onGlobalSync();
    } catch (cause) { setError(cause.message || "Results could not be displayed."); }
    finally { setWorking(false); }
  };
  return <section className="judging-admin">
    <header className="judging-admin__header"><div><h2>Judging</h2><p>Judging is currently being conducted offline.</p></div><a className="round-leaderboard-button" href="/leaderboard" target="_blank" rel="noreferrer">Open public leaderboard ↗</a></header>
    {error && <div className="global-error" role="alert">{error}</div>}
    {notice && <div className="admin-notice" role="status">{notice}</div>}
    <section className="judging-status"><span>Status</span><strong>{published ? "RESULTS PUBLISHED" : "WAITING FOR JUDGING"}</strong></section>
    <section className="judging-winners"><div><h3>Final winners</h3><p>Save keeps these selections private. Display Results publishes them to every participant and the TV route.</p></div><div className="judging-selector-grid"><SearchableTeamSelector label="1st Place" teams={data.teams} value={winners.first} onChange={(first) => setWinners((current) => ({ ...current, first }))} disabled={published} /><SearchableTeamSelector label="2nd Place" teams={data.teams} value={winners.second} onChange={(second) => setWinners((current) => ({ ...current, second }))} disabled={published} /><SearchableTeamSelector label="3rd Place" teams={data.teams} value={winners.third} onChange={(third) => setWinners((current) => ({ ...current, third }))} disabled={published} /></div><div className="judging-actions"><button className="secondary-button" disabled={working || published || !complete || !unique} onClick={() => void save()}>{working ? "Saving…" : "Save winners"}</button><button className="primary-button" disabled={working || published || !data.saved_at || !selectionsMatchSaved} onClick={() => setConfirming(true)}>{published ? "Results displayed" : "Display results"}</button></div></section>
    {confirming && <div className="judging-confirmation-backdrop"><section className="judging-confirmation" role="dialog" aria-modal="true" aria-labelledby="publish-results-title"><h3 id="publish-results-title">Display final results?</h3><p>This immediately reveals the winners to all participants and the public leaderboard.</p><ol><li><span>1st</span><strong>{teamName(winners.first)}</strong></li><li><span>2nd</span><strong>{teamName(winners.second)}</strong></li><li><span>3rd</span><strong>{teamName(winners.third)}</strong></li></ol><div><button className="secondary-button" disabled={working} onClick={() => setConfirming(false)}>Cancel</button><button className="primary-button" disabled={working} onClick={() => void publish()}>{working ? "Displaying…" : "Display results"}</button></div></section></div>}
  </section>;
}

function RecoveryPage({ onGlobalSync, onNavigate }) {
  const [data, setData] = useState(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [eventResetConfirmation, setEventResetConfirmation] = useState("");
  const [credentialResetConfirmation, setCredentialResetConfirmation] = useState("");
  const [resetSummary, setResetSummary] = useState(null);
  const [credentialResetSummary, setCredentialResetSummary] = useState(null);
  const load = useCallback(async () => { try { setData(await getRecoveryState()); setError(""); return true; } catch (cause) { setError(cause.message || "Recovery state could not be loaded."); return false; } }, []);
  useEffect(() => { void load(); const timer = setInterval(() => { if (!document.hidden) void load(); }, 5000); return () => clearInterval(timer); }, [load]);
  const run = async (operation, success) => { setWorking(true); setError(""); setNotice(""); try { const result = await operation(); setData(result?.current_phase ? result : await getRecoveryState()); setNotice(success); await onGlobalSync(); } catch (cause) { setError(cause.message || "Recovery action failed."); await load(); } finally { setWorking(false); } };
  const resetEvent = async () => { setWorking(true); setError(""); setNotice(""); try { const result = await resetEventData(eventResetConfirmation); setResetSummary(result); setEventResetConfirmation(""); setData(await getRecoveryState()); setNotice("Event data reset successfully. Participant accounts and passwords were preserved."); await onGlobalSync(); } catch (cause) { setError(cause.message || "Event data reset failed."); await load(); } finally { setWorking(false); } };
  const resetCredentials = async () => { setWorking(true); setError(""); setNotice(""); try { const result = await resetRegistrationCredentials(credentialResetConfirmation); setCredentialResetSummary(result); setCredentialResetConfirmation(""); setData(await getRecoveryState()); setNotice("Imported participant credentials reset. Event data was preserved."); await onGlobalSync(); } catch (cause) { setError(cause.message || "Participant credential reset failed."); await load(); } finally { setWorking(false); } };
  if (!data) return <div className="loading-screen"><div className="loader" />Loading recovery state…</div>;
  const fields = [
    ["Current phase", labels[data.current_phase] || data.current_phase], ["Current sub-state", data.current_sub_state],
    ["Current problem", data.current_problem ? `${data.current_problem.number} · ${data.current_problem.title}` : "None"],
    ["Timer", data.timer.paused ? `Paused · ${formatTime(data.timer.remaining_seconds)}` : data.timer.ends_at ? `${formatTime(data.timer.remaining_seconds)} remaining` : "Inactive"],
    ["Round 1 completion", data.round1_complete ? "Complete" : "In progress"], ["Wildcard applications", data.wildcard_applications.status],
    ["Wildcard auction", data.wildcard_auction_state], ["Selection rank", data.wildcard_selection_rank ?? "None"],
    ["Submissions", data.submission_state], ["Last state update", data.last_state_update ? new Date(data.last_state_update).toLocaleString() : "Not recorded"],
  ];
  return <section className="operations-page"><header><div><h2>Safe event recovery</h2><p>Restore and re-synchronize the authoritative server state. Completed stages cannot be reopened here.</p></div></header>{error && <div className="global-error" role="alert">{error}</div>}{notice && <div className="admin-notice">{notice}</div>}<dl className="recovery-grid">{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><div className="recovery-actions"><button className="secondary-button" disabled={working || !data.timer.paused} onClick={() => run(resumeRecoveryTimer, "Current timer resumed from server state.")}>Resume current timer</button><button className="secondary-button" disabled={working} onClick={() => run(reloadRecoveryState, "Server state reloaded.")}>Reload server state</button><button className="secondary-button" disabled={working} onClick={() => run(resyncClients, "Connected clients were asked to re-sync.")}>Re-sync clients</button><button className="secondary-button" disabled={working} onClick={() => run(retryCurrentTransition, "Current transition re-evaluated safely.")}>Retry current transition</button></div><section className="event-data-reset"><div><strong>Reset event data</strong><h3>Prepare a clean event</h3><p>Permanently removes problem uploads, bids, assignments, Wildcard progress, submissions, timers, results, leaderboard event state, and event activity. Team registration, participant accounts, and every account password are preserved.</p><p>This cannot be undone. Reset is available at every event stage.</p></div><label>Type RESET EVENT<input value={eventResetConfirmation} onChange={(event) => setEventResetConfirmation(event.target.value)} /></label><button className="danger-button" disabled={working || eventResetConfirmation !== "RESET EVENT"} onClick={() => window.confirm("Reset current event state and competition data? Team registration and all account credentials will be preserved.") && void resetEvent()}>Reset event data</button>{resetSummary && <div className="reset-summary"><strong>Event data reset complete</strong><span>Teams preserved: {resetSummary.preserved.teams} · Participant accounts preserved: {resetSummary.preserved.participant_accounts} · Problems removed: {resetSummary.deleted.round1_problems + resetSummary.deleted.wildcard_problems} · Bids removed: {resetSummary.deleted.bids} · Submissions removed: {resetSummary.deleted.submissions}</span><button className="primary-button" onClick={() => onNavigate("round1")}>Go to Round 1</button></div>}</section><section className="event-data-reset"><div><strong>Reset credentials</strong><h3>Invalidate imported participant access</h3><p>Invalidates imported participant passwords and active sessions. Teams, assignments, bids, Wildcard progress, submissions, timers, and the current event stage are preserved.</p><p>Use Participant Passwords in Registration Import to assign new passwords. Permanent Admin, demo, and leaderboard display accounts remain available.</p></div><label>Type RESET CREDENTIALS<input value={credentialResetConfirmation} onChange={(event) => setCredentialResetConfirmation(event.target.value)} /></label><button className="danger-button" disabled={working || credentialResetConfirmation !== "RESET CREDENTIALS"} onClick={() => window.confirm("Invalidate imported participant credentials? The current event and all competition data will be preserved.") && void resetCredentials()}>Reset participant credentials</button>{credentialResetSummary && <div className="reset-summary"><strong>Credential reset complete</strong><span>Imported participant accounts reset: {credentialResetSummary.reset.participant_accounts} · Teams and event data preserved</span><button className="primary-button" onClick={() => onNavigate("imports")}>Set participant passwords</button></div>}</section>{data.reset_enabled && <section className="development-reset"><div><strong>Development only</strong><h3>Force-reset rehearsal state</h3><p>Available only when ENABLE_EVENT_RESET is enabled. This keeps registrations and imported problems.</p></div><label>Type RESET DEVELOPMENT EVENT<input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label><button className="danger-button" disabled={working || confirmation !== "RESET DEVELOPMENT EVENT"} onClick={() => window.confirm("Reset this development rehearsal? This cannot be undone.") && run(() => developmentReset(confirmation), "Development rehearsal reset completed.")}>Reset development event</button></section>}</section>;
}

function ActivityLogPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => getActivityLog().then(setData).catch((cause) => setError(cause.message || "Event log could not be loaded.")), []);
  useEffect(() => { void load(); const timer = setInterval(() => { if (!document.hidden) void load(); }, 10000); return () => clearInterval(timer); }, [load]);
  if (!data) return <div className="loading-screen"><div className="loader" />Loading event log…</div>;
  return <section className="operations-page"><header><div><h2>Event activity log</h2><p>Append-only operational history. Passwords, tokens, and credential exports are never recorded.</p></div><button className="secondary-button" onClick={() => void load()}>Refresh log</button></header>{error && <div className="global-error" role="alert">{error}</div>}<div className="table-wrapper"><table><thead><tr><th>TIME</th><th>ACTOR</th><th>ACTION</th><th>ENTITY</th><th>DETAILS</th></tr></thead><tbody>{data.rows.map((row) => <tr key={row.id}><td>{new Date(row.timestamp).toLocaleString()}</td><td>{row.actor_type}{row.actor_id ? ` #${row.actor_id}` : ""}</td><td><strong>{row.action.replaceAll(".", " · ")}</strong></td><td>{row.entity_type ? `${row.entity_type}${row.entity_id ? ` #${row.entity_id}` : ""}` : "—"}</td><td><code>{Object.keys(row.metadata || {}).length ? JSON.stringify(row.metadata) : "—"}</code></td></tr>)}</tbody></table></div></section>;
}

function TimerButtons({ state, remaining, run }) {
  return <div className="round-timer-actions"><button className="secondary-button" disabled={state?.timing?.paused} onClick={() => run(pauseTimer, "Timer paused.")}>Pause</button><button className="secondary-button" disabled={!state?.timing?.paused} onClick={() => run(resumeTimer, "Timer resumed.")}>Resume</button><button className="secondary-button" onClick={() => run(() => addTime(30), "Added 30 seconds.")}>+30 sec</button><button className="secondary-button" disabled={remaining <= 0} onClick={() => run(() => removeTime(30), "Removed up to 30 seconds.")}>−30 sec</button></div>;
}

function Teams({ teams, onAction }) {
  return <section className="page-section"><div className="table-wrapper"><table><thead><tr><th>TEAM</th><th>COINS</th><th>MEMBERS</th><th>STATUS</th><th>ACTIONS</th></tr></thead><tbody>{teams.map((team) => <tr key={team.id}><td><strong>{team.team_name}</strong></td><td className="coins">{team.coins}</td><td>{team.members?.length ?? 0}</td><td><span className={`table-status ${team.is_approved ? "active" : "pending"}`}>{team.is_approved ? "APPROVED" : "PENDING"}</span></td><td className="table-actions">{!team.is_approved && <button onClick={() => onAction(() => approveTeam(team.id), "Team approved.")}>Approve</button>}<button className="danger-link" onClick={() => window.confirm(`Delete ${team.team_name}?`) && onAction(() => deleteTeam(team.id), "Team deleted.")}>Delete</button></td></tr>)}</tbody></table></div></section>;
}

function Problems({ problems, state, onAction }) {
  return <section className="page-section"><div className="problem-grid">{problems.map((problem) => <article className="problem-card" key={problem.id}><span className="problem-number">{problem.ps_number}</span><h3>{problem.title}</h3><p>{problem.description}</p><div className="problem-footer"><select value={problem.status} onChange={(event) => onAction(() => setProblemVisibility(problem.id, event.target.value), "Problem visibility updated.")}><option value="hidden">Hidden</option><option value="visible">Visible</option><option value="allocated">Allocated</option></select>{state?.event_state === "ROUND1_RESULT" && problem.round === 1 && problem.status !== "allocated" && <button className="primary-button" onClick={() => onAction(() => finalizeProblem(problem.id), "Round 1 winners finalized.")}>Finalize bids</button>}</div></article>)}</div></section>;
}

function ParticipantCredentials({ teams }) {
  const emptyMember = () => ({ name: "", email: "" });
  const [form, setForm] = useState({ team_name: "", leader: { name: "", email: "" }, members: [emptyMember()] });
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [working, setWorking] = useState(false);
  const [existingTeamId, setExistingTeamId] = useState("");

  const updateMember = (index, field, value) => setForm((current) => ({
    ...current,
    members: current.members.map((member, memberIndex) => memberIndex === index ? { ...member, [field]: value } : member),
  }));

  const submit = async (event) => {
    event.preventDefault(); setWorking(true); setError(""); setNotice("");
    try {
      const payload = {
        team_name: form.team_name.trim(),
        leader: { name: form.leader.name.trim(), email: form.leader.email.trim() },
        members: form.members.map((member) => ({ name: member.name.trim(), email: member.email.trim() || null })),
      };
      const created = await createTeamCredentials(payload);
      setResult(created); setNotice("Credentials generated. Save or export them now; temporary passwords are not stored.");
    } catch (cause) { setError(cause.message || "Credentials could not be generated."); }
    finally { setWorking(false); }
  };

  const credentialText = () => result.credentials.map((item) => [
    item.role.toUpperCase(), item.name, item.username, item.temporary_password,
  ].join("\t")).join("\n");
  const copyAll = async () => { await navigator.clipboard.writeText(`TEAM: ${result.team_name}\n${credentialText()}`); setNotice("Credentials copied."); };
  const downloadCsv = () => {
    const escape = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
    const rows = [["Team Name", "Participant Name", "Role", "Email", "Participant ID", "Temporary Password"],
      ...result.credentials.map((item) => [result.team_name, item.name, item.role, item.email, item.participant_id || item.username, item.temporary_password])];
    const blob = new Blob([rows.map((row) => row.map(escape).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
    anchor.href = url; anchor.download = `${result.team_name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-credentials.csv`; anchor.click();
    URL.revokeObjectURL(url);
  };
  const resetPassword = async (userId) => {
    setWorking(true); setError("");
    try {
      const updated = await resetParticipantPassword(userId);
      setResult((current) => ({ ...current, credentials: current.credentials.map((item) => item.user_id === userId ? updated : item) }));
      setNotice("Password reset. Save the newly displayed temporary password now.");
    } catch (cause) { setError(cause.message || "Password reset failed."); }
    finally { setWorking(false); }
  };
  const loadExisting = async () => {
    if (!existingTeamId) return;
    setWorking(true); setError(""); setNotice("");
    try {
      const existing = await getTeamCredentials(existingTeamId);
      setResult(existing); setNotice("Existing login IDs loaded. Reset a password to reveal a new temporary value.");
    } catch (cause) { setError(cause.message || "Existing credentials could not be loaded."); }
    finally { setWorking(false); }
  };

  return <section className="page-section credentials-page">
    <div className="panel existing-credentials"><div className="panel-heading"><div><h3>Existing team accounts</h3><span>Load login IDs and reset individual passwords without duplicating accounts.</span></div></div><div className="credential-actions"><select value={existingTeamId} onChange={(event) => setExistingTeamId(event.target.value)}><option value="">Select a team</option>{teams.map((team) => <option key={team.id} value={team.id}>{team.team_name}</option>)}</select><button className="secondary-button" type="button" disabled={!existingTeamId || working} onClick={() => void loadExisting()}>Load accounts</button></div></div>
    <div className="panel"><div className="panel-heading"><div><h3>Participant ID / Team credentials</h3><span>Create one shared team wallet with an individual login for every participant.</span></div></div>
      <form className="credential-form" onSubmit={submit}>
        <label>Team name<input value={form.team_name} onChange={(event) => setForm({ ...form, team_name: event.target.value })} required /></label>
        <fieldset><legend>Team leader</legend><div className="credential-row"><label>Name<input value={form.leader.name} onChange={(event) => setForm({ ...form, leader: { ...form.leader, name: event.target.value } })} required /></label><label>Email<input type="email" value={form.leader.email} onChange={(event) => setForm({ ...form, leader: { ...form.leader, email: event.target.value } })} required /></label></div></fieldset>
        <fieldset><legend>Teammates</legend>{form.members.map((member, index) => <div className="credential-row" key={index}><label>Member {index + 1} name<input value={member.name} onChange={(event) => updateMember(index, "name", event.target.value)} required /></label><label>Email (optional)<input type="email" value={member.email} onChange={(event) => updateMember(index, "email", event.target.value)} placeholder="Generated participant ID when blank" /></label>{form.members.length > 1 && <button className="danger-link remove-member" type="button" onClick={() => setForm({ ...form, members: form.members.filter((_, memberIndex) => memberIndex !== index) })}>Remove</button>}</div>)}</fieldset>
        <div className="credential-actions">{form.members.length < 3 && <button className="secondary-button" type="button" onClick={() => setForm({ ...form, members: [...form.members, emptyMember()] })}>Add teammate</button>}<button className="primary-button" type="submit" disabled={working}>{working ? "Generating…" : "Generate credentials"}</button></div>
      </form>
      {error && <p className="global-error">{error}</p>}{notice && <p className="admin-notice">{notice}</p>}
    </div>
    {result && <div className="panel generated-credentials"><div className="panel-heading"><div><h3>Team: {result.team_name}</h3><span>Passwords are visible only in this response or after reset.</span></div><div className="credential-actions"><button className="secondary-button" onClick={() => void copyAll()}>Copy all</button><button className="secondary-button" onClick={downloadCsv}>Download CSV</button><button className="secondary-button" onClick={() => window.print()}>Print</button></div></div><div className="table-wrapper"><table><thead><tr><th>ROLE</th><th>NAME</th><th>LOGIN ID</th><th>TEMP PASSWORD</th><th>ACTION</th></tr></thead><tbody>{result.credentials.map((item) => <tr key={item.user_id}><td>{item.role}</td><td><strong>{item.name}</strong></td><td><code>{item.username}</code></td><td><code>{item.temporary_password || "Not reset"}</code></td><td><button className="danger-link" disabled={working} onClick={() => void resetPassword(item.user_id)}>Reset password</button></td></tr>)}</tbody></table></div></div>}
  </section>;
}

function RegistrationImport() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const [resetConfirmation, setResetConfirmation] = useState("");
  const [resetResult, setResetResult] = useState(null);
  const [resetError, setResetError] = useState("");
  const [participantAccounts, setParticipantAccounts] = useState([]);
  const [accountsLoading, setAccountsLoading] = useState(true);
  const [accountsError, setAccountsError] = useState("");
  const [passwordTarget, setPasswordTarget] = useState(null);
  const [passwordForm, setPasswordForm] = useState({ new_password: "", confirm_password: "" });
  const [passwordWorking, setPasswordWorking] = useState(false);
  const [passwordNotice, setPasswordNotice] = useState("");
  const loadParticipantAccounts = useCallback(async () => {
    setAccountsLoading(true); setAccountsError("");
    try { setParticipantAccounts((await getImportedParticipantAccounts()).accounts || []); }
    catch (cause) { setAccountsError(cause.message || "Participant accounts could not be loaded."); }
    finally { setAccountsLoading(false); }
  }, []);
  useEffect(() => { void loadParticipantAccounts(); }, [loadParticipantAccounts]);
  const runImport = async () => {
    if (!file) return;
    setWorking(true); setError(""); setResult(null);
    try { setResult(await importRegistrations(file)); await loadParticipantAccounts(); }
    catch (cause) { setError(cause.message || "Registration import failed."); }
    finally { setWorking(false); }
  };
  const download = async () => {
    if (!result?.download_token) return;
    setWorking(true); setError("");
    try {
      const blob = await downloadRegistrationCredentials(result.download_token);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = result.download_filename;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
      setResult({ ...result, download_token: null });
    } catch (cause) { setError(cause.message || "Credential download failed."); }
    finally { setWorking(false); }
  };
  const downloadSample = async () => {
    try {
      const blob = await downloadRegistrationSample(); const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = "registration-import-sample.csv"; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (cause) { setError(cause.message || "Sample download failed."); }
  };
  const downloadDemo = async () => {
    try {
      const blob = await downloadRegistrationDemo(); const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = "bid-to-build-demo-registration.csv"; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (cause) { setError(cause.message || "Demo CSV download failed."); }
  };
  const downloadAssignments = async () => {
    setWorking(true); setError("");
    try {
      const blob = await downloadRegistrationAssignments();
      const suffix = blob.type.includes("spreadsheet") ? "xlsx" : "csv";
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `bid-to-build-updated-registration.${suffix}`; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (cause) { setError(cause.message || "Participant assignment download failed."); }
    finally { setWorking(false); }
  };
  const resetCredentials = async () => {
    setWorking(true); setResetError(""); setResetResult(null);
    try {
      const response = await resetRegistrationCredentials(resetConfirmation);
      setResetResult(response);
      setResetConfirmation(""); setFile(null); setResult(null);
      setPasswordTarget(null); setPasswordForm({ new_password: "", confirm_password: "" });
      await loadParticipantAccounts();
    } catch (cause) { setResetError(cause.message || "Participant credentials could not be reset."); }
    finally { setWorking(false); }
  };
  const saveParticipantPassword = async () => {
    if (!passwordTarget) return;
    setPasswordNotice(""); setAccountsError("");
    if (!passwordForm.new_password) { setAccountsError("Enter a new password."); return; }
    if (passwordForm.new_password !== passwordForm.confirm_password) { setAccountsError("Password confirmation does not match."); return; }
    setPasswordWorking(true);
    try {
      await setImportedParticipantPassword(passwordTarget.user_id, passwordForm);
      setPasswordNotice(`Password ${passwordTarget.credential_status === "SET" ? "changed" : "set"} for ${passwordTarget.login_id}.`);
      setPasswordTarget(null); setPasswordForm({ new_password: "", confirm_password: "" });
      await loadParticipantAccounts();
    } catch (cause) { setAccountsError(cause.message || "Participant password could not be saved."); }
    finally { setPasswordWorking(false); }
  };
  const summaryRows = result ? [
    ["Teams processed", result.teams_processed], ["Teams created", result.teams_created],
    ["Teams updated", result.teams_updated], ["Leader accounts", result.leaders_created],
    ["Existing leaders", result.existing_leaders], ["Members imported", result.members_imported],
    ["Rows failed", result.rows_failed],
  ] : [];

  return <section className="registration-import">
    <div className="registration-import__intro"><div><h2>Registration import</h2><p>Import approved team and participant identities with their initial passwords.</p></div><span className="registration-import__format">XLSX / CSV · MAX 10 MB</span></div>
    <div className="registration-import__grid">
      <section className="registration-upload-panel">
        <div className="event-section-heading"><h3>Upload registration sheet</h3><p>The immediate returned sheet preserves the uploaded passwords and adds login IDs and credential status. Later assignment exports do not expose passwords.</p><div className="round-inline-actions"><button className="secondary-button" onClick={() => void downloadDemo()}>Download demo CSV</button><button className="secondary-button" onClick={() => void downloadSample()}>Download blank sample</button><button className="secondary-button" disabled={working} onClick={() => void downloadAssignments()}>Download updated registration sheet</button></div></div>
        <label className={`registration-dropzone ${file ? "registration-dropzone--ready" : ""}`}>
          <input type="file" accept=".xlsx,.csv" onChange={(event) => { setFile(event.target.files?.[0] || null); setResult(null); setError(""); }} />
          <span className="registration-dropzone__mark" aria-hidden="true" />
          <strong>{file ? file.name : "Choose an XLSX or CSV file"}</strong>
          <small>{file ? `${Math.max(1, Math.round(file.size / 1024))} KB ready to import` : "Original columns and values are preserved in the account-status output file."}</small>
        </label>
        <div className="registration-requirements"><strong>Required registration data</strong><ul><li>Team name</li><li>Leader name and email</li><li>Member names</li><li>Member emails when available</li></ul></div>
        <button className="event-primary-action" disabled={!file || working} onClick={() => void runImport()}>{working ? "Importing registrations…" : "Import registrations"}<span className="action-arrow" aria-hidden="true" /></button>
        {error && <p className="global-error" role="alert">{error}</p>}
      </section>

      <section className="registration-result-panel" aria-live="polite">
        <div className="event-section-heading"><h3>Import summary</h3><p>{result ? "Identity and supplied password data committed. Review rejected rows or manage participant passwords below." : "Summary and account-status download will appear after a completed import."}</p></div>
        {result ? <>
          <dl className="registration-summary">{summaryRows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
          <div className="registration-errors"><h4>Errors</h4>{result.errors.length ? <ul>{result.errors.map((item, index) => <li key={`${item.row_number}-${index}`}><strong>Row {item.row_number}</strong><span>{item.message}</span></li>)}</ul> : <p>No row-level errors.</p>}</div>
          <button className="primary-button registration-download" disabled={!result.download_token || working} onClick={() => void download()}>{result.download_token ? "Download account status sheet" : "Account status sheet downloaded"}</button>
          <small className="registration-security-note">Passwords are not generated, exported, or stored as plaintext during import.</small>
        </> : <div className="registration-result-empty"><span>Import results pending</span><p>Select a registration sheet to begin.</p></div>}
      </section>
    </div>
    <section className="participant-passwords">
      <div className="participant-passwords__heading"><div><h3>PARTICIPANT PASSWORDS</h3><p>Set or change passwords for imported participant accounts. Saving a password invalidates that participant’s current session.</p></div><button className="secondary-button" disabled={accountsLoading || passwordWorking} onClick={() => void loadParticipantAccounts()}>Refresh accounts</button></div>
      {accountsError && <p className="global-error" role="alert">{accountsError}</p>}
      {passwordNotice && <p className="admin-notice" role="status">{passwordNotice}</p>}
      <div className="table-wrapper participant-passwords__table"><table><thead><tr><th>PARTICIPANT / LEADER</th><th>TEAM</th><th>ROLE</th><th>CREDENTIAL STATUS</th><th>ACTION</th></tr></thead><tbody>
        {participantAccounts.map((account) => <tr key={account.user_id}><td><strong>{account.name}</strong><small>{account.login_id}</small></td><td>{account.team_name}</td><td>{account.role}</td><td><span className={`credential-status credential-status--${account.credential_status.toLowerCase()}`}>{account.credential_status === "SET" ? "PASSWORD SET" : "PASSWORD NOT SET"}</span></td><td><button className="secondary-button" disabled={passwordWorking} onClick={() => { setPasswordTarget(account); setPasswordForm({ new_password: "", confirm_password: "" }); setPasswordNotice(""); setAccountsError(""); }}>{account.credential_status === "SET" ? "Change Password" : "Set Password"}</button></td></tr>)}
        {!accountsLoading && !participantAccounts.length && <tr><td colSpan="5"><div className="participant-passwords__empty">No imported participant accounts yet.</div></td></tr>}
        {accountsLoading && <tr><td colSpan="5"><div className="participant-passwords__empty">Loading participant accounts…</div></td></tr>}
      </tbody></table></div>
      {passwordTarget && <div className="participant-password-form">
        <div><strong>{passwordTarget.credential_status === "SET" ? "Change password" : "Set password"}</strong><span>{passwordTarget.login_id} · {passwordTarget.team_name}</span></div>
        <label>New Password<input type="password" value={passwordForm.new_password} onChange={(event) => setPasswordForm({ ...passwordForm, new_password: event.target.value })} autoComplete="new-password" maxLength="72" /></label>
        <label>Confirm Password<input type="password" value={passwordForm.confirm_password} onChange={(event) => setPasswordForm({ ...passwordForm, confirm_password: event.target.value })} autoComplete="new-password" maxLength="72" /></label>
        <div className="round-inline-actions"><button className="secondary-button" disabled={passwordWorking} onClick={() => { setPasswordTarget(null); setPasswordForm({ new_password: "", confirm_password: "" }); }}>Cancel</button><button className="primary-button" disabled={passwordWorking || !passwordForm.new_password || !passwordForm.confirm_password} onClick={() => void saveParticipantPassword()}>{passwordWorking ? "Saving…" : passwordTarget.credential_status === "SET" ? "CHANGE PASSWORD" : "SET PASSWORD"}</button></div>
      </div>}
    </section>
    <section className="participant-credential-reset">
      <div><strong>Participant credential reset</strong><h3>Reset imported participant credentials</h3><p>Invalidate imported participant passwords and sessions, returning each account to Password Not Set.</p><p>Teams, event progress, assignments, bids, submissions, timers, and permanent system accounts remain unchanged.</p></div>
      <label>Type RESET CREDENTIALS<input value={resetConfirmation} onChange={(event) => setResetConfirmation(event.target.value)} autoComplete="off" /></label>
      <button className="danger-button" disabled={working || resetConfirmation !== "RESET CREDENTIALS"} onClick={() => window.confirm("Invalidate imported participant credentials? The current event and all competition data will be preserved.") && void resetCredentials()}>Reset participant credentials</button>
      {resetError && <p className="participant-credential-reset__error" role="alert">{resetError}</p>}
      {resetResult && <div className="participant-credential-reset__result" role="status"><strong>Credential reset complete</strong><span>Imported participant accounts reset: {resetResult.reset.participant_accounts} · Event data and {resetResult.preserved.system_accounts} permanent system accounts preserved</span></div>}
    </section>
  </section>;
}

function Bids({ bids, teams, problems }) {
  const teamName = (id) => teams.find((team) => team.id === id)?.team_name || `Team ${id}`; const problemName = (id) => problems.find((problem) => problem.id === id)?.ps_number || id;
  return <section className="page-section"><div className="table-wrapper"><table><thead><tr><th>RANK</th><th>TEAM</th><th>PROBLEM</th><th>ROUND</th><th>AMOUNT</th><th>RECEIVED</th></tr></thead><tbody>{bids.map((bid, index) => <tr key={bid.id}><td>#{index + 1}</td><td>{teamName(bid.team_id)}</td><td>{problemName(bid.ps_id)}</td><td>{bid.round}</td><td className="coins">{bid.amount}</td><td>{new Date(bid.timestamp).toLocaleTimeString()}</td></tr>)}</tbody></table></div></section>;
}

function ManagedUsersPage({ kind }) {
  const isAdmin = kind === "admin";
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({ login_id: "", password: "", confirm_password: "" });
  const [resetTarget, setResetTarget] = useState(null);
  const [passwordForm, setPasswordForm] = useState({ new_password: "", confirm_password: "" });
  const [resetConfirmation, setResetConfirmation] = useState("");
  const [resetResult, setResetResult] = useState(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    const result = await (isAdmin ? getManagedAdminUsers() : getManagedLeaderboardUsers());
    setUsers(result.users || []);
  }, [isAdmin]);

  useEffect(() => {
    setUsers([]); setError(""); setNotice(""); setResetTarget(null); setResetResult(null);
    void load().catch((cause) => setError(cause.message || "Managed users could not be loaded."));
  }, [load]);

  const createUser = async (event) => {
    event.preventDefault(); setError(""); setNotice("");
    if (form.password !== form.confirm_password) { setError("Password confirmation does not match."); return; }
    setWorking(true);
    try {
      await (isAdmin ? createManagedAdminUser(form) : createManagedLeaderboardUser(form));
      setForm({ login_id: "", password: "", confirm_password: "" });
      setNotice(`${isAdmin ? "Admin" : "Leaderboard"} user created.`);
      await load();
    } catch (cause) { setError(cause.message || "User could not be created."); }
    finally { setWorking(false); }
  };

  const beginPasswordReset = (user) => {
    setResetTarget(user); setPasswordForm({ new_password: "", confirm_password: "" }); setError(""); setNotice("");
  };

  const resetPassword = async (event) => {
    event.preventDefault(); setError(""); setNotice("");
    if (passwordForm.new_password !== passwordForm.confirm_password) { setError("Password confirmation does not match."); return; }
    setWorking(true);
    try {
      await resetManagedUserPassword(resetTarget.id, passwordForm);
      setNotice(`Password reset for ${resetTarget.login_id}. Existing sessions were signed out.`);
      setResetTarget(null); setPasswordForm({ new_password: "", confirm_password: "" });
    } catch (cause) { setError(cause.message || "Password could not be reset."); }
    finally { setWorking(false); }
  };

  const resetAllManaged = async () => {
    setWorking(true); setError(""); setNotice("");
    try {
      const result = await resetManagedUsers(resetConfirmation);
      setResetResult(result); setResetConfirmation(""); setResetTarget(null);
      setNotice("Non-system Admin and Leaderboard users removed.");
      await load();
    } catch (cause) { setError(cause.message || "Managed users could not be reset."); }
    finally { setWorking(false); }
  };

  return <section className="managed-users-page">
    <header className="managed-users-header"><div><h2>{isAdmin ? "Admin users" : "Leaderboard users"}</h2><p>{isAdmin ? "Create event administrators and manage their access." : "Create read-only display logins for the existing public leaderboard."}</p></div><span>{users.length} account{users.length === 1 ? "" : "s"}</span></header>
    {error && <div className="global-error" role="alert">{error}</div>}
    {notice && <div className="admin-notice" role="status">{notice}</div>}
    <form className="managed-user-form" onSubmit={createUser}>
      <div><h3>Create {isAdmin ? "Admin" : "Leaderboard"} user</h3><p>Passwords are hashed by the server and are never shown again.</p></div>
      <label>Login ID<input value={form.login_id} onChange={(event) => setForm({ ...form, login_id: event.target.value })} autoComplete="username" required /></label>
      <label>Password<input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} autoComplete="new-password" required /></label>
      <label>Confirm password<input type="password" value={form.confirm_password} onChange={(event) => setForm({ ...form, confirm_password: event.target.value })} autoComplete="new-password" required /></label>
      <button className="primary-button" type="submit" disabled={working}>{working ? "Creating…" : `Create ${isAdmin ? "Admin" : "Leaderboard"} user`}</button>
    </form>
    <div className="managed-user-table table-wrapper"><table><thead><tr><th>LOGIN ID</th><th>STATUS</th><th>CREATED</th><th>ACTIONS</th></tr></thead><tbody>
      {users.map((user) => <tr key={user.id}><td><strong>{user.login_id}</strong>{user.is_system_account && <span className="system-account-note">Protected permanent account</span>}</td><td><span className={`table-status ${user.is_system_account ? "system" : "active"}`}>{user.status}</span></td><td>{user.created_at ? new Date(user.created_at).toLocaleString() : "—"}</td><td className="table-actions">{(!user.is_system_account || !isAdmin) ? <button type="button" onClick={() => beginPasswordReset(user)}>Reset password</button> : <span>Protected</span>}</td></tr>)}
      {!users.length && <tr><td className="managed-users-empty" colSpan="4">No {isAdmin ? "Admin" : "Leaderboard"} users found.</td></tr>}
    </tbody></table></div>
    {resetTarget && <form className="managed-password-reset" onSubmit={resetPassword}><div><h3>Reset password</h3><p>{resetTarget.login_id} will be signed out of every active session.</p></div><label>New password<input type="password" value={passwordForm.new_password} onChange={(event) => setPasswordForm({ ...passwordForm, new_password: event.target.value })} autoComplete="new-password" required /></label><label>Confirm password<input type="password" value={passwordForm.confirm_password} onChange={(event) => setPasswordForm({ ...passwordForm, confirm_password: event.target.value })} autoComplete="new-password" required /></label><div className="managed-password-actions"><button className="secondary-button" type="button" onClick={() => setResetTarget(null)}>Cancel</button><button className="primary-button" type="submit" disabled={working}>{working ? "Resetting…" : "Reset password"}</button></div></form>}
    {isAdmin && <section className="managed-users-reset"><div><strong>Reset managed users</strong><h3>Remove temporary management access</h3><p>Deletes only non-system Admin and Leaderboard users. Permanent system accounts, Demo Team, participants, and event data remain unchanged.</p></div><label>Type RESET USERS<input value={resetConfirmation} onChange={(event) => setResetConfirmation(event.target.value)} autoComplete="off" /></label><button className="danger-button" disabled={working || resetConfirmation !== "RESET USERS"} onClick={() => window.confirm("Delete every non-system Admin and Leaderboard user? This cannot be undone.") && void resetAllManaged()}>Reset managed users</button>{resetResult && <div className="managed-users-reset__result" role="status"><strong>Managed users reset</strong><span>Admin users: {resetResult.deleted.admin_users} removed · Leaderboard users: {resetResult.deleted.leaderboard_users} removed</span></div>}</section>}
  </section>;
}

function Leaderboard({ rows }) { return <section className="page-section leaderboard-page"><div className="table-wrapper"><table><thead><tr><th>RANK</th><th>TEAM</th><th>COINS</th><th>PROBLEM</th></tr></thead><tbody>{rows.map((team, index) => <tr key={team.team_id || team.id}><td><span className={`leader-rank ${index < 3 ? "gold" : ""}`}>{index + 1}</span></td><td><strong>{team.team_name}</strong></td><td className="coins">{team.coins}</td><td>{team.allocated_ps || "—"}</td></tr>)}</tbody></table></div></section>; }
function Stat({ label, value }) { return <div className="stat-card"><span>{label}</span><strong>{value}</strong></div>; }
function formatTime(seconds) { const safe = Math.max(0, Number(seconds) || 0); const h = Math.floor(safe / 3600); const m = Math.floor((safe % 3600) / 60); const s = safe % 60; return [h, m, s].map((value) => String(value).padStart(2, "0")).join(":"); }

export default App;
