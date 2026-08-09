import { useCallback, useEffect, useMemo, useState } from "react";
import Login from "./pages/Login";
import {
  addTime, approveTeam, clearToken, confirmRegistrationImport, deleteTeam, finalizeProblem,
  finalizeWildcard, getAdminConfig, getAdminState, getBidHistory, getLeaderboard,
  getProblemStatements, getTeamCredentials, getTeams, hasToken, logout, pauseTimer, previewRegistrationImport,
  removeTime, resetParticipantPassword, resumeTimer, setEventState, setProblemVisibility,
  updateAdminConfig, createTeamCredentials,
} from "./api";
import { connectAuctionSocket } from "./auctionSocket";
import "./App.css";

const EVENT_STATES = [
  "WAITING", "ROUND1_PREVIEW", "ROUND1_BIDDING", "ROUND1_RESULT",
  "WILDCARD_APPLICATION", "WILDCARD_PREVIEW", "WILDCARD_BIDDING",
  "WILDCARD_SELECTION", "CODING", "SUBMISSION", "JUDGING_WAIT", "RESULTS",
];

const labels = {
  WAITING: "Waiting", ROUND1_PREVIEW: "Round 1 preview", ROUND1_BIDDING: "Round 1 bidding",
  ROUND1_RESULT: "Round 1 result", WILDCARD_APPLICATION: "Wildcard applications",
  WILDCARD_PREVIEW: "Wildcard preview", WILDCARD_BIDDING: "Wildcard bidding",
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

function useServerCountdown(timing) {
  const calculate = useCallback((localNow) => {
    if (timing?.paused && timing.paused_remaining_seconds != null) return timing.paused_remaining_seconds;
    if (!timing?.ends_at) return 0;
    const receivedAt = timing.received_at || localNow;
    const offset = Date.parse(timing.server_time) - receivedAt;
    return Math.max(0, Math.ceil((Date.parse(timing.ends_at) - (localNow + offset)) / 1000));
  }, [timing]);
  const [now, setNow] = useState(0);
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const first = setTimeout(tick, 0);
    const interval = setInterval(tick, 1000);
    return () => { clearTimeout(first); clearInterval(interval); };
  }, []);
  return calculate(now || timing?.received_at || 0);
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
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [teamRows, problemRows, bidRows, board, eventState, eventConfig] = await Promise.all([
        getTeams(), getProblemStatements(), getBidHistory(), getLeaderboard(), getAdminState(), getAdminConfig(),
      ]);
      setTeams(teamRows); setProblems(problemRows); setBids(bidRows); setLeaderboard(board.teams || board);
      setState({ ...eventState, timing: { ...eventState.timing, received_at: Date.now() } }); setConfig(eventConfig); setError("");
    } catch (cause) { setError(cause.message || "Unable to load event data."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { const id = setTimeout(() => void load(), 0); return () => clearTimeout(id); }, [load]);
  useEffect(() => connectAuctionSocket({ onStatus: setSocketStatus, onMessage: () => void load() }), [load]);
  const remaining = useServerCountdown(state?.timing);

  const action = async (operation, success) => {
    try { setError(""); setNotice(""); await operation(); setNotice(success); await load(); }
    catch (cause) { setError(cause.message || "Action failed."); }
  };
  const currentIndex = EVENT_STATES.indexOf(state?.event_state || state?.state);
  const bidRows = useMemo(() => [...bids].sort((a, b) => Number(b.amount) - Number(a.amount)), [bids]);

  if (loading) return <div className="loading-screen"><div className="loader" />Loading live control center…</div>;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand"><div className="sidebar-logo">♠</div><div><strong>Bid to Build</strong><span>Admin control</span></div></div>
        <span className="sidebar-section-title">Event operations</span>
        <nav className="sidebar-nav">
          {[["dashboard", "Overview"], ["event", "Event control"], ["teams", "Teams"], ["credentials", "Participant ID"], ["problems", "Problems"], ["imports", "Registration import"], ["bids", "Bidding status"], ["leaderboard", "Leaderboard"]].map(([id, label]) => (
            <button key={id} className={`nav-item ${page === id ? "active" : ""}`} onClick={() => setPage(id)}><span className="nav-icon">◆</span>{label}</button>
          ))}
        </nav>
        <div className="sidebar-bottom"><div className="admin-profile"><div className="admin-avatar">A</div><div><strong>Event Admin</strong><span>Backend verified</span></div></div><button className="logout-button" onClick={onLogout}>Log out</button></div>
      </aside>
      <main className="main-content">
        <header className="topbar"><div><h1>{page === "event" ? "Event Control" : page[0].toUpperCase() + page.slice(1)}</h1><p>Authoritative live event operations</p></div><div className="topbar-right"><div className="connection-status"><span className={`status-dot ${socketStatus === "connected" ? "online" : ""}`} />{socketStatus}</div><div className="event-date">CURRENT STAGE<strong>{labels[state?.event_state] || "—"}</strong></div></div></header>
        <div className="page-content">
          {error && <div className="global-error"><span>{error}</span><button onClick={() => setError("")}>×</button></div>}
          {notice && <div className="admin-notice">{notice}</div>}
          {page === "dashboard" && <Dashboard teams={teams} problems={problems} bids={bids} state={state} remaining={remaining} />}
          {page === "event" && <EventControl state={state} config={config} currentIndex={currentIndex} remaining={remaining} onAction={action} onConfig={setConfig} />}
          {page === "teams" && <Teams teams={teams} onAction={action} />}
          {page === "credentials" && <ParticipantCredentials teams={teams} />}
          {page === "problems" && <Problems problems={problems} state={state} onAction={action} />}
          {page === "imports" && <RegistrationImport onAction={action} />}
          {page === "bids" && <Bids bids={bidRows} teams={teams} problems={problems} />}
          {page === "leaderboard" && <Leaderboard rows={leaderboard} />}
        </div>
      </main>
    </div>
  );
}

function Dashboard({ teams, problems, bids, state, remaining }) {
  return <section className="dashboard"><div className="hero-panel"><div><span className="eyebrow">LIVE EVENT STATE</span><h2>{labels[state?.event_state] || "Waiting"}</h2><p>Every connected participant receives state changes from the backend.</p></div><div className="hero-status"><span className="live-pulse" />{state?.timing?.paused ? "TIMER PAUSED" : remaining ? formatTime(remaining) : "READY"}</div></div><div className="stats-grid"><Stat label="REGISTERED TEAMS" value={teams.length} /><Stat label="PROBLEM STATEMENTS" value={problems.length} /><Stat label="BIDS RECEIVED" value={bids.length} /><Stat label="CURRENT ROUND" value={state?.current_round ?? 1} /></div></section>;
}

function EventControl({ state, config, currentIndex, remaining, onAction, onConfig }) {
  const current = state?.event_state;
  const saveConfig = () => onAction(() => updateAdminConfig(config), "Event configuration saved.");
  return <section className="page-section"><div className="panel"><div className="panel-heading"><div><h3>Lifecycle control</h3><span>Only the valid next transition is enabled.</span></div><strong className="state-pill live">{labels[current]}</strong></div><div className="state-grid">{EVENT_STATES.map((item, index) => <button key={item} className={`state-button ${item === current ? "active" : ""}`} disabled={index !== currentIndex + 1 && !(current === "RESULTS" && item === "WAITING")} onClick={() => onAction(() => setEventState(item), `Event moved to ${labels[item]}.`)}>{index + 1}. {labels[item]}</button>)}</div></div>
    <div className="dashboard-grid"><div className="panel"><div className="panel-heading"><div><h3>Server timer</h3><span>Derived from server timestamps</span></div></div><div className="admin-timer">{formatTime(remaining)}</div><div className="action-strip"><button className="secondary-button" onClick={() => onAction(pauseTimer, "Timer paused.")}>Pause</button><button className="secondary-button" onClick={() => onAction(resumeTimer, "Timer resumed.")}>Resume</button><button className="secondary-button" onClick={() => onAction(() => addTime(60), "Added 60 seconds.")}>+ 60s</button><button className="secondary-button" onClick={() => onAction(() => removeTime(60), "Removed 60 seconds.")}>− 60s</button></div></div>
    <div className="panel"><div className="panel-heading"><div><h3>Core configuration</h3><span>Used by auctions and synchronized timers</span></div></div>{config && <div className="config-grid">{[["starting_coins", "Starting coins"], ["round1_preview_seconds", "Preview seconds"], ["round1_bid_seconds", "Round 1 bid seconds"], ["round1_winner_count", "Round 1 winners"], ["wildcard_slots", "Wildcard slots"], ["wildcard_bid_seconds", "Wildcard bid seconds"], ["coding_duration_seconds", "Coding seconds"]].map(([key, label]) => <label key={key}>{label}<input type="number" min="0" value={config[key]} onChange={(event) => onConfig({ ...config, [key]: Number(event.target.value) })} /></label>)}<button className="primary-button" onClick={saveConfig}>Save configuration</button></div>}</div></div>
    {current === "WILDCARD_BIDDING" && <button className="primary-button" onClick={() => onAction(finalizeWildcard, "Wildcard auction finalized.")}>Finalize wildcard winners</button>}</section>;
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
  const [file, setFile] = useState(null); const [preview, setPreview] = useState(null); const [result, setResult] = useState(null); const [error, setError] = useState(""); const [working, setWorking] = useState(false);
  const run = async (operation) => { setWorking(true); setError(""); try { return await operation(); } catch (cause) { setError(cause.message); } finally { setWorking(false); } };
  return <section className="page-section"><div className="panel import-panel"><div className="panel-heading"><div><h3>Registration CSV/XLSX import</h3><span>Preview is required before confirmation.</span></div></div><input type="file" accept=".csv,.xlsx" onChange={(event) => setFile(event.target.files?.[0] || null)} /><button className="primary-button" disabled={!file || working} onClick={() => void run(async () => setPreview(await previewRegistrationImport(file)))}>Preview import</button>{error && <p className="global-error">{error}</p>}{preview && <div className="import-summary"><p><strong>{preview.teams_detected}</strong> teams · <strong>{preview.members_detected}</strong> members</p><button className="primary-button" disabled={working} onClick={() => void run(async () => setResult(await confirmRegistrationImport(preview.import_id)))}>Confirm import</button></div>}{result && <div className="credentials"><h3>Temporary credentials — save now</h3>{result.credentials.map((item) => <code key={item.email}>{item.team_name} · {item.email} · {item.temporary_password}</code>)}</div>}</div></section>;
}

function Bids({ bids, teams, problems }) {
  const teamName = (id) => teams.find((team) => team.id === id)?.team_name || `Team ${id}`; const problemName = (id) => problems.find((problem) => problem.id === id)?.ps_number || id;
  return <section className="page-section"><div className="table-wrapper"><table><thead><tr><th>RANK</th><th>TEAM</th><th>PROBLEM</th><th>ROUND</th><th>AMOUNT</th><th>RECEIVED</th></tr></thead><tbody>{bids.map((bid, index) => <tr key={bid.id}><td>#{index + 1}</td><td>{teamName(bid.team_id)}</td><td>{problemName(bid.ps_id)}</td><td>{bid.round}</td><td className="coins">{bid.amount}</td><td>{new Date(bid.timestamp).toLocaleTimeString()}</td></tr>)}</tbody></table></div></section>;
}

function Leaderboard({ rows }) { return <section className="page-section leaderboard-page"><div className="table-wrapper"><table><thead><tr><th>RANK</th><th>TEAM</th><th>COINS</th><th>PROBLEM</th></tr></thead><tbody>{rows.map((team, index) => <tr key={team.team_id || team.id}><td><span className={`leader-rank ${index < 3 ? "gold" : ""}`}>{index + 1}</span></td><td><strong>{team.team_name}</strong></td><td className="coins">{team.coins}</td><td>{team.allocated_ps || "—"}</td></tr>)}</tbody></table></div></section>; }
function Stat({ label, value }) { return <div className="stat-card"><span>{label}</span><strong>{value}</strong></div>; }
function formatTime(seconds) { const safe = Math.max(0, Number(seconds) || 0); const h = Math.floor(safe / 3600); const m = Math.floor((safe % 3600) / 60); const s = safe % 60; return [h, m, s].map((value) => String(value).padStart(2, "0")).join(":"); }

export default App;
