import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, Check, ChevronDown, Search, X } from "lucide-react";
import { changeRoundOneAssignment, getRoundOneAssignments } from "../services/api";

function problemLabel(problem) {
  return `#${problem.problem_number} ${problem.title}`;
}

function SourceBadge({ problem }) {
  return <span className={`problem-picker__source problem-picker__source--${problem.source.toLowerCase()}`}>{problem.source_label}</span>;
}

function ProblemDetails({ problem }) {
  return problem ? <div className="change-problem-details"><strong>{problemLabel(problem)}</strong><SourceBadge problem={problem} /></div>
    : <strong className="change-problem-none">Not assigned</strong>;
}

// Keep focus inside these task dialogs and return it to the invoking control.
function TaskDialog({ titleId, className, onClose, working = false, children }) {
  const panel = useRef(null);
  const close = useRef({ onClose, working });
  close.current = { onClose, working };
  useEffect(() => {
    const root = panel.current.getRootNode();
    const activeElement = () => root.activeElement || document.activeElement;
    const previousFocus = activeElement();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const controls = () => [...panel.current.querySelectorAll('button:not(:disabled), input:not(:disabled), [tabindex="0"]')];
    (panel.current.querySelector("[data-initial-focus]") || controls()[0] || panel.current).focus();
    const onKey = (event) => {
      if (event.key === "Escape" && !close.current.working) {
        event.preventDefault();
        close.current.onClose();
      }
      if (event.key !== "Tab") return;
      const items = controls();
      const first = items[0] || panel.current;
      const last = items.at(-1) || panel.current;
      if (event.shiftKey && (activeElement() === first || !panel.current.contains(activeElement()))) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (activeElement() === last || !panel.current.contains(activeElement()))) {
        event.preventDefault(); first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, []);
  return <div className="judging-confirmation-backdrop problem-picker-backdrop" onClick={(event) => {
    if (event.target === event.currentTarget && !working) onClose();
  }}>
    <section ref={panel} className={`judging-confirmation ${className}`} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
      {children}
    </section>
  </div>;
}

function ProblemPicker({ team, problems, value, onSelect, onClose }) {
  const [search, setSearch] = useState("");
  const [source, setSource] = useState("ALL");
  const query = search.trim().toLowerCase();
  const visible = problems.filter((problem) =>
    (source === "ALL" || problem.source === source)
    && [problem.problem_number, problem.title, problem.description].some((text) => String(text || "").toLowerCase().includes(query)));
  return <TaskDialog titleId="problem-picker-title" className="problem-picker" onClose={onClose}>
    <header className="problem-picker__header">
      <div><span className="problem-picker__eyebrow">{team.team_name}</span><h3 id="problem-picker-title">Select problem</h3>
        <p>Choose the team’s new current problem. Review and confirm before saving.</p></div>
      <button className="problem-picker__close" type="button" aria-label="Close problem picker" onClick={onClose}><X size={18} /></button>
    </header>
    <div className="problem-picker__controls">
      <label className="problem-picker__search" htmlFor="problem-picker-search"><Search size={18} aria-hidden="true" />
        <input id="problem-picker-search" data-initial-focus type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search number, title or description" aria-label="Search problems" />
      </label>
      <div className="problem-picker__filters" role="group" aria-label="Problem source">
        {[["ALL", "All"], ["ROUND1", "Round 1"], ["WILDCARD", "Wildcard"]].map(([key, label]) =>
          <button key={key} type="button" aria-pressed={source === key} onClick={() => setSource(key)}>{label}</button>)}
      </div>
    </div>
    <div className="problem-picker__results">
      {[["ROUND1", "Round 1"], ["WILDCARD", "Wildcard"]].map(([key, label]) => {
        const rows = visible.filter((problem) => problem.source === key);
        return rows.length > 0 && <section className="problem-picker__group" key={key} aria-label={`${label} problems`}>
          <h4>{label} <span>{rows.length}</span></h4>
          {rows.map((problem) => {
            const current = team.current_problem?.id === problem.id;
            const selected = value === problem.id;
            return <button key={problem.id} type="button" disabled={current} aria-pressed={selected}
              className={`problem-picker__card${selected ? " is-selected" : ""}${current ? " is-current" : ""}`}
              onClick={() => onSelect(problem.id)}>
              <span className="problem-picker__number">#{problem.problem_number}</span>
              <span className="problem-picker__card-body"><strong>{problem.title}</strong>
                <span className="problem-picker__metadata"><SourceBadge problem={problem} /><span>{problem.assigned_team_count} assigned</span>
                  {current && <b>CURRENT</b>}{selected && <b className="problem-picker__selected"><Check size={14} /> Selected</b>}</span>
                <span className="problem-picker__description">{problem.description || "No description provided."}</span>
              </span>
            </button>;
          })}
        </section>;
      })}
      {visible.length === 0 && <div className="change-problem-empty" role="status"><strong>No matching problems</strong><p>Try a different search or source.</p></div>}
    </div>
    <footer className="problem-picker__footer"><span>Selection only — no changes saved yet.</span><button className="secondary-button" type="button" onClick={onClose}>Done</button></footer>
  </TaskDialog>;
}

function AssignmentDialog({ team, target, working, onCancel, onConfirm }) {
  const [newBalance, setNewBalance] = useState(String(team.coins));
  const assigned = team.assignment_status === "ASSIGNED";
  const parsedBalance = /^\d+$/.test(newBalance.trim()) ? Number(newBalance.trim()) : null;
  const balanceValid = assigned || (Number.isSafeInteger(parsedBalance) && parsedBalance >= 0 && parsedBalance <= 1_000_000);
  const balanceDelta = balanceValid && !assigned ? parsedBalance - team.coins : 0;
  const balanceEffect = !balanceValid ? "Enter a whole number from 0 to 1,000,000."
    : balanceDelta === 0 ? "No balance change" : `${Math.abs(balanceDelta).toLocaleString()} coin ${balanceDelta > 0 ? "increase" : "decrease"}`;
  return <TaskDialog titleId="change-problem-dialog-title" className="change-problem-dialog" onClose={onCancel} working={working}>
    <header className="problem-picker__header"><div><span className="problem-picker__eyebrow">{team.team_name}</span>
      <h3 id="change-problem-dialog-title">Confirm Problem {assigned ? "Change" : "Assignment"}</h3>
      <p>This updates the current problem only. Auction history stays unchanged.</p></div>
      <button className="problem-picker__close" type="button" aria-label="Close confirmation" disabled={working} onClick={onCancel}><X size={18} /></button>
    </header>
    <div className="change-problem-comparison">
      <section><h4>Current problem</h4><ProblemDetails problem={team.current_problem} /></section>
      <ArrowDown className="change-problem-comparison__arrow" size={20} aria-hidden="true" />
      <section className="change-problem-comparison__new"><h4>New problem</h4><ProblemDetails problem={target} /></section>
    </div>
    <dl className="change-problem-confirmation">
      {assigned ? <div><dt>Coin balance</dt><dd>{team.coins.toLocaleString()} → {team.coins.toLocaleString()} <span>No change</span></dd></div> : <>
        <div><dt>Current balance</dt><dd>{team.coins.toLocaleString()} coins</dd></div>
        <div><dt><label htmlFor="assignment-new-balance">New balance</label></dt><dd><input
          id="assignment-new-balance" type="number" min="0" max="1000000" step="1" inputMode="numeric"
          value={newBalance} disabled={working} aria-invalid={!balanceValid} aria-describedby="assignment-balance-effect"
          onChange={(event) => setNewBalance(event.target.value)} /></dd></div>
        <div className="change-problem-confirmation__effect"><dt>Balance effect</dt><dd id="assignment-balance-effect">
          {balanceValid ? `${team.coins.toLocaleString()} → ${parsedBalance.toLocaleString()}` : "Invalid balance"}
          <span className={balanceDelta === 0 ? "is-unchanged" : "is-changing"}>{balanceEffect}</span>
        </dd></div>
      </>}
    </dl>
    <footer><button className="secondary-button" disabled={working} onClick={onCancel}>Cancel</button>
      <button className="primary-button" disabled={working || !target || !balanceValid} onClick={() => onConfirm(target.id, assigned ? null : parsedBalance)}>
        {working ? "Applying…" : assigned ? "Confirm Change" : "Confirm Assignment"}
      </button></footer>
  </TaskDialog>;
}

function completionBoundaries(event) {
  if (!["event_snapshot", "event_state_changed"].includes(event?.type)) return [];
  const rounds = event.payload?.rounds;
  return [rounds?.ROUND1?.ended ? "ROUND1_COMPLETE" : null, rounds?.WILDCARD?.ended ? "WILDCARD_COMPLETE" : null].filter(Boolean);
}

export default function ChangeProblemPage({ realtimeEvent = null }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [selections, setSelections] = useState({});
  const [pickerTeam, setPickerTeam] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [workingTeamId, setWorkingTeamId] = useState(null);
  const completedBoundaries = useRef(new Set(completionBoundaries(realtimeEvent)));
  const loadInFlight = useRef(null);

  const load = useCallback((quiet = false) => {
    if (loadInFlight.current) return loadInFlight.current;
    const request = (async () => {
      if (!quiet) setLoading(true);
      else setRefreshing(true);
      try {
        setData(await getRoundOneAssignments());
        setError("");
      } catch (cause) {
        setError(cause.message || "Problem assignments could not be loaded.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    })();
    loadInFlight.current = request;
    void request.finally(() => { if (loadInFlight.current === request) loadInFlight.current = null; });
    return request;
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    let refresh = false;
    for (const boundary of completionBoundaries(realtimeEvent)) {
      if (completedBoundaries.current.has(boundary)) continue;
      completedBoundaries.current.add(boundary);
      refresh = true;
    }
    if (refresh) void load(true);
  }, [load, realtimeEvent]);

  // Defensive filtering also excludes legacy targets from older API responses.
  const problems = useMemo(() => (data?.problems || []).filter((problem) => ["ROUND1", "WILDCARD"].includes(problem.source)), [data]);
  const visibleTeams = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return data?.teams || [];
    return (data?.teams || []).filter((team) => [team.team_name, team.leader_name, team.leader_email,
      team.current_problem?.title, team.current_problem?.problem_number].some((value) => String(value || "").toLowerCase().includes(query)));
  }, [data, search]);
  const openDialog = (team, targetProblemId) => {
    const target = problems.find((problem) => problem.id === targetProblemId && problem.id !== team.current_problem?.id);
    if (!target) return;
    setError(""); setNotice(""); setDialog({ team, target });
  };
  const confirmChange = async (targetProblemId, newBalance = null) => {
    if (!dialog) return;
    setWorkingTeamId(dialog.team.team_id); setError(""); setNotice("");
    try {
      const result = await changeRoundOneAssignment(dialog.team.team_id, targetProblemId, newBalance);
      setData(result); setNotice(result.message);
      setSelections((current) => { const next = { ...current }; delete next[dialog.team.team_id]; return next; });
      setDialog(null);
    } catch (cause) {
      setError(cause.message || "The problem assignment could not be changed.");
      await load(true); setDialog(null);
    } finally { setWorkingTeamId(null); }
  };

  if (loading && !data) return <div className="loading-screen"><div className="loader" />Loading problem assignments…</div>;
  if (!data) return <section className="change-problem-page"><div className="global-error" role="alert"><span>{error || "Assignment data is unavailable."}</span><button onClick={() => void load()}>Retry</button></div></section>;

  return <section className="change-problem-page">
    <header className="change-problem-header"><div><h2>Change Problem</h2>
      <p>Correct a team’s current / final problem. Round 1 and Wildcard history stay intact; assigned teams keep their coin balance.</p></div>
      <button className="secondary-button" disabled={refreshing} onClick={() => void load(true)}>{refreshing ? "Refreshing…" : "Refresh assignments"}</button>
    </header>
    {error && <div className="global-error" role="alert"><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError("")}>×</button></div>}
    {notice && <div className="admin-notice" role="status">{notice}</div>}
    <div className="change-problem-summary" aria-label="Current problem assignment summary">
      <div><span>Participant Teams</span><strong>{data.teams.length}</strong></div>
      <div><span>Without Current Problem</span><strong>{data.unassigned_teams.length}</strong></div>
      <div><span>Round 1 Problems</span><strong>{problems.filter((problem) => problem.source === "ROUND1").length}</strong></div>
      <div><span>Wildcard Problems</span><strong>{problems.filter((problem) => problem.source === "WILDCARD").length}</strong></div>
    </div>
    <section className="change-problem-table-panel">
      <div className="change-problem-toolbar"><div><h3>Current assignments</h3><span>{visibleTeams.length} of {data.teams.length} teams shown</span></div>
        <label htmlFor="change-problem-search">Search teams, leaders, or problems</label>
        <input id="change-problem-search" type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search assignment records" />
      </div>
      <div className="change-problem-table" role="table" aria-label="Current problem assignments">
        <div className="change-problem-table__head" role="row">{["Team", "Leader", "Current problem", "New problem", "Status", "Action"].map((label) => <span key={label} role="columnheader">{label}</span>)}</div>
        {visibleTeams.map((team) => {
          const selected = problems.find((problem) => problem.id === selections[team.team_id] && problem.id !== team.current_problem?.id);
          const working = workingTeamId === team.team_id;
          return <div className="change-problem-row" role="row" key={team.team_id}>
            <div role="cell" className="change-problem-team"><strong>{team.team_name}</strong><small>ID {team.team_id}</small></div>
            <div role="cell" className="change-problem-leader"><strong>{team.leader_name || "Not available"}</strong><small>{team.leader_email || "No leader email"}</small></div>
            <div role="cell" className="change-problem-current"><ProblemDetails problem={team.current_problem} /></div>
            <div role="cell" className="change-problem-selection"><button id={`target-problem-${team.team_id}`} type="button"
              className={`problem-picker-trigger${selected ? " has-selection" : ""}`} aria-haspopup="dialog" aria-label={`Select new problem for ${team.team_name}`}
              disabled={working || !problems.length} onClick={() => setPickerTeam(team)}>
              <span>{selected ? <><strong>{problemLabel(selected)}</strong><SourceBadge problem={selected} /></> : "Select new problem"}</span><ChevronDown size={16} aria-hidden="true" />
            </button></div>
            <div role="cell" className="change-problem-row-status"><span className={`change-problem-status change-problem-status--${team.assignment_status.toLowerCase()}`}>{team.assignment_status === "NOT_ASSIGNED" ? "Not assigned" : "Assigned"}</span></div>
            <div role="cell" className="change-problem-action"><button className="secondary-button" disabled={!selected || working} onClick={() => openDialog(team, selected.id)}>{team.assignment_status === "ASSIGNED" ? "Change" : "Assign"}</button></div>
          </div>;
        })}
        {visibleTeams.length === 0 && <div className="change-problem-empty"><strong>No matching teams</strong><p>Try a team name, leader, or current problem.</p></div>}
      </div>
    </section>
    <section className="change-problem-unassigned"><header><div><h3>Teams Without a Current Problem</h3><p>Choose a Round 1 or Wildcard problem, then review the assignment and optional final balance.</p></div><strong>{data.unassigned_teams.length}</strong></header>
      {data.unassigned_teams.length ? <div className="change-problem-unassigned-list">{data.unassigned_teams.map((team) => {
        const selected = problems.find((problem) => problem.id === selections[team.team_id]);
        return <article key={team.team_id}><div><strong>{team.team_name}</strong><span>{team.leader_name || "Leader not available"}</span></div>
          <span className="change-problem-status change-problem-status--not_assigned">Not assigned</span>
          <button className="primary-button" disabled={workingTeamId === team.team_id || !problems.length}
            onClick={() => selected ? openDialog(team, selected.id) : setPickerTeam(team)}>{selected ? "Review assignment" : "Assign Problem"}</button></article>;
      })}</div> : <div className="change-problem-all-assigned"><strong>All participant teams have a current problem.</strong><p>This section updates with the assignment snapshot.</p></div>}
    </section>
    {pickerTeam && <ProblemPicker team={pickerTeam} problems={problems} value={selections[pickerTeam.team_id]}
      onSelect={(id) => setSelections((current) => ({ ...current, [pickerTeam.team_id]: id }))} onClose={() => setPickerTeam(null)} />}
    {dialog && <AssignmentDialog key={`${dialog.team.team_id}-${dialog.target.id}`} team={dialog.team} target={dialog.target}
      working={workingTeamId === dialog.team.team_id} onCancel={() => setDialog(null)} onConfirm={(id, balance) => void confirmChange(id, balance)} />}
  </section>;
}
