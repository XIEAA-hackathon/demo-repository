import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  changeRoundOneAssignment,
  downloadExternalProblemSample,
  getRoundOneAssignments,
  importExternalProblems,
} from "../services/api";

function problemLabel(problem) {
  return `#${problem.problem_number} ${problem.title}`;
}

function ProblemSelect({ problems, currentProblemId, value, onChange, id, disabled = false }) {
  const groups = [
    ["ROUND1", "Round 1 problems"],
    ["EXTERNAL", "External problems"],
  ];
  return (
    <select id={id} value={value || ""} disabled={disabled} onChange={(event) => onChange(Number(event.target.value) || null)}>
      <option value="">Select problem</option>
      {groups.map(([source, label]) => {
        const options = problems.filter((problem) => problem.source === source && problem.id !== currentProblemId);
        return options.length ? <optgroup key={source} label={label}>
          {options.map((problem) => (
            <option key={problem.id} value={problem.id} disabled={problem.is_full}>
              {problemLabel(problem)} — {problem.assigned_team_count}/{problem.capacity}{problem.is_full ? " · FULL" : ""}
            </option>
          ))}
        </optgroup> : null;
      })}
    </select>
  );
}

function AssignmentDialog({ team, problems, initialProblemId, working, onCancel, onConfirm }) {
  const [targetProblemId, setTargetProblemId] = useState(initialProblemId || null);
  const [newBalance, setNewBalance] = useState(String(team.coins));
  const target = problems.find((problem) => problem.id === targetProblemId);
  const current = team.current_problem;
  const action = current ? "change" : "assignment";
  const normalizedBalance = newBalance.trim();
  const parsedBalance = /^\d+$/.test(normalizedBalance) ? Number(normalizedBalance) : null;
  const balanceValid = current || (
    Number.isSafeInteger(parsedBalance)
    && parsedBalance >= 0
    && parsedBalance <= 1_000_000
  );
  const balanceDelta = balanceValid && !current ? parsedBalance - team.coins : 0;
  const balanceEffect = !balanceValid
    ? "Enter a whole number from 0 to 1,000,000."
    : balanceDelta === 0
      ? "No balance change"
      : `${Math.abs(balanceDelta).toLocaleString()} coin ${balanceDelta > 0 ? "increase" : "decrease"}`;

  return (
    <div className="judging-confirmation-backdrop">
      <section className="judging-confirmation change-problem-dialog" role="dialog" aria-modal="true" aria-labelledby="change-problem-dialog-title">
        <header>
          <h3 id="change-problem-dialog-title">Confirm Problem {current ? "Change" : "Assignment"}</h3>
          <p>{current
            ? "This updates the current problem only. Auction history and coins stay unchanged."
            : "The problem assignment and optional final balance are saved together. Auction history stays unchanged."}</p>
        </header>
        <dl className="change-problem-confirmation">
          <div><dt>Team</dt><dd>{team.team_name}</dd></div>
          <div><dt>Current problem</dt><dd>{current ? problemLabel(current) : "None"}</dd></div>
          <div className="change-problem-confirmation__target">
            <dt>New problem</dt>
            <dd>
              {initialProblemId ? (target ? problemLabel(target) : "Select a problem") : (
                <ProblemSelect
                  id="confirmation-target-problem"
                  problems={problems}
                  currentProblemId={current?.id}
                  value={targetProblemId}
                  onChange={setTargetProblemId}
                  disabled={working}
                />
              )}
            </dd>
          </div>
          <div><dt>Source</dt><dd>{target?.source_label || "Select a problem"}</dd></div>
          {current ? <div><dt>Coin balance</dt><dd>{team.coins.toLocaleString()} → {team.coins.toLocaleString()} <span>No change</span></dd></div> : <>
            <div><dt>Current balance</dt><dd>{team.coins.toLocaleString()} coins</dd></div>
            <div className="change-problem-confirmation__balance">
              <dt><label htmlFor="assignment-new-balance">New balance</label></dt>
              <dd>
                <input
                  id="assignment-new-balance"
                  type="number"
                  min="0"
                  max="1000000"
                  step="1"
                  inputMode="numeric"
                  value={newBalance}
                  disabled={working}
                  aria-invalid={!balanceValid}
                  aria-describedby="assignment-balance-effect"
                  onChange={(event) => setNewBalance(event.target.value)}
                />
              </dd>
            </div>
            <div className="change-problem-confirmation__effect">
              <dt>Balance effect</dt>
              <dd id="assignment-balance-effect">
                {balanceValid ? `${team.coins.toLocaleString()} → ${parsedBalance.toLocaleString()}` : "Invalid balance"}
                <span className={balanceDelta === 0 ? "is-unchanged" : "is-changing"}>{balanceEffect}</span>
              </dd>
            </div>
          </>}
        </dl>
        {target && <p className="change-problem-capacity-note">Target capacity after this {action}: <strong>{target.assigned_team_count + 1} / {target.capacity}</strong></p>}
        <footer>
          <button className="secondary-button" disabled={working} onClick={onCancel}>Cancel</button>
          <button className="primary-button" disabled={working || !targetProblemId || target?.is_full || !balanceValid} onClick={() => onConfirm(targetProblemId, current ? null : parsedBalance)}>
            {working ? "Applying…" : current ? "Confirm Change" : "Confirm Assignment"}
          </button>
        </footer>
      </section>
    </div>
  );
}

export default function ChangeProblemPage({ revision = 0 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [selections, setSelections] = useState({});
  const [dialog, setDialog] = useState(null);
  const [workingTeamId, setWorkingTeamId] = useState(null);
  const [importFile, setImportFile] = useState(null);
  const [importing, setImporting] = useState(false);
  const importInputRef = useRef(null);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    else setRefreshing(true);
    try {
      setData(await getRoundOneAssignments());
      setError("");
    } catch (cause) {
      setError(cause.message || "Round 1 assignments could not be loaded.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { void load(Boolean(data)); }, [load, revision]);

  const visibleTeams = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return data?.teams || [];
    return (data?.teams || []).filter((team) => [
      team.team_name,
      team.leader_name,
      team.leader_email,
      team.current_problem?.title,
      team.current_problem?.problem_number,
    ].some((value) => String(value || "").toLowerCase().includes(query)));
  }, [data, search]);

  const openDialog = (team, targetProblemId = null) => {
    setError("");
    setNotice("");
    setDialog({ team, targetProblemId });
  };

  const confirmChange = async (targetProblemId, newBalance = null) => {
    if (!dialog) return;
    setWorkingTeamId(dialog.team.team_id);
    setError("");
    setNotice("");
    try {
      const result = await changeRoundOneAssignment(dialog.team.team_id, targetProblemId, newBalance);
      setData(result);
      setNotice(result.message);
      setSelections((current) => {
        const next = { ...current };
        delete next[dialog.team.team_id];
        return next;
      });
      setDialog(null);
    } catch (cause) {
      setError(cause.message || "The problem assignment could not be changed.");
      await load(true);
      setDialog(null);
    } finally {
      setWorkingTeamId(null);
    }
  };

  const importProblems = async () => {
    if (!importFile) return;
    setImporting(true);
    setError("");
    setNotice("");
    try {
      const result = await importExternalProblems(importFile);
      setData(result);
      setNotice(result.message);
      setImportFile(null);
      if (importInputRef.current) importInputRef.current.value = "";
    } catch (cause) {
      setError(cause.message || "The external problems could not be imported.");
    } finally {
      setImporting(false);
    }
  };

  const downloadSample = async () => {
    setError("");
    try {
      const blob = await downloadExternalProblemSample();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "external-problems-sample.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause.message || "The sample file could not be downloaded.");
    }
  };

  if (loading && !data) return <div className="loading-screen"><div className="loader" />Loading Round 1 assignments…</div>;
  if (!data) return <section className="change-problem-page"><div className="global-error" role="alert"><span>{error || "Assignment data is unavailable."}</span><button onClick={() => void load()}>Retry</button></div></section>;

  return (
    <section className="change-problem-page">
      <header className="change-problem-header">
        <div>
          <h2>Change Problem</h2>
          <p>Assign or change a team&apos;s current problem without rewriting auction history. New assignments can also set the final team balance.</p>
        </div>
        <button className="secondary-button" disabled={refreshing} onClick={() => void load(true)}>{refreshing ? "Refreshing…" : "Refresh assignments"}</button>
      </header>

      {error && <div className="global-error" role="alert"><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError("")}>×</button></div>}
      {notice && <div className="admin-notice" role="status">{notice}</div>}

      <section className="external-problems-panel">
        <header>
          <div>
            <span>Manual assignment bank</span>
            <h3>External Problem Statements</h3>
            <p>Import the same Problem Number, Title, and Description format used by Round 1. These problems never enter bidding.</p>
          </div>
          <strong>{data.external_problems.length} external</strong>
        </header>
        <div className="external-problems-actions">
          <label className="secondary-button external-problems-upload">
            {importFile ? "Choose another file" : "Import Problems from Excel"}
            <input
              ref={importInputRef}
              type="file"
              accept=".xlsx,.csv"
              onChange={(event) => setImportFile(event.target.files?.[0] || null)}
            />
          </label>
          <button className="secondary-button" type="button" onClick={() => void downloadSample()}>Download sample CSV</button>
          {importFile && <div className="external-problems-file">
            <span>Ready to import</span>
            <strong title={importFile.name}>{importFile.name}</strong>
          </div>}
          {importFile && <button className="primary-button" type="button" disabled={importing} onClick={() => void importProblems()}>
            {importing ? "Importing…" : "Import problems"}
          </button>}
        </div>
        {data.external_problems.length ? <div className="external-problems-list">
          {data.external_problems.map((problem) => <article key={problem.id}>
            <div><strong>{problemLabel(problem)}</strong><span>{problem.description}</span></div>
            <span>{problem.assigned_team_count} / {problem.capacity} assigned</span>
            <b className={problem.is_full ? "is-full" : ""}>{problem.is_full ? "Full" : `${problem.capacity_remaining} available`}</b>
          </article>)}
        </div> : <div className="external-problems-empty">
          <strong>No external problems imported</strong>
          <span>Upload an XLSX or CSV problem bank to make manual-only targets available.</span>
        </div>}
      </section>

      <div className="change-problem-summary" aria-label="Round 1 assignment summary">
        <div><span>Participant teams</span><strong>{data.teams.length}</strong></div>
        <div><span>Without a problem</span><strong>{data.unassigned_teams.length}</strong></div>
        <div><span>Capacity rule</span><strong>{data.capacity_per_problem} per problem</strong></div>
        <div><span>Financial control</span><strong>Optional final balance</strong></div>
      </div>

      <section className="change-problem-table-panel">
        <div className="change-problem-toolbar">
          <div><h3>Current Round 1 assignments</h3><span>{visibleTeams.length} of {data.teams.length} teams shown</span></div>
          <label htmlFor="change-problem-search">Search teams, leaders, or problems</label>
          <input id="change-problem-search" type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search assignment records" />
        </div>
        <div className="change-problem-table" role="table" aria-label="Round 1 problem assignments">
          <div className="change-problem-table__head" role="row">
            <span>Team</span><span>Leader</span><span>Current problem</span><span>New problem</span><span>Status</span><span>Action</span>
          </div>
          {visibleTeams.map((team) => {
            const selected = selections[team.team_id] || null;
            return <div className="change-problem-row" role="row" key={team.team_id}>
              <div className="change-problem-team"><strong>{team.team_name}</strong><small>ID {team.team_id}</small></div>
              <div className="change-problem-leader"><strong>{team.leader_name || "Not available"}</strong><small>{team.leader_email || "No leader email"}</small></div>
              <div className="change-problem-current">{team.current_problem ? <><strong>{problemLabel(team.current_problem)}</strong><small>{team.current_problem.source_label} · {team.current_problem.description}</small></> : <strong className="change-problem-none">Not assigned</strong>}</div>
              <ProblemSelect
                id={`target-problem-${team.team_id}`}
                problems={data.problems}
                currentProblemId={team.current_problem?.id}
                value={selected}
                onChange={(value) => setSelections((current) => ({ ...current, [team.team_id]: value }))}
                disabled={workingTeamId === team.team_id || data.problems.length === 0}
              />
              <span className={`change-problem-status change-problem-status--${team.assignment_status.toLowerCase()}`}>{team.assignment_status === "NOT_ASSIGNED" ? "Not assigned" : "Assigned"}</span>
              <button className="secondary-button" disabled={!selected || workingTeamId === team.team_id} onClick={() => openDialog(team, selected)}>{team.current_problem ? "Change" : "Assign"}</button>
            </div>;
          })}
          {visibleTeams.length === 0 && <div className="change-problem-empty"><strong>No matching teams</strong><p>Try a team name, leader, or current problem.</p></div>}
        </div>
      </section>

      <section className="change-problem-unassigned">
        <header><div><h3>Teams Without Round 1 Problem</h3><p>Authoritative participant teams with no current Round 1 assignment.</p></div><strong>{data.unassigned_teams.length}</strong></header>
        {data.unassigned_teams.length ? <div className="change-problem-unassigned-list">
          {data.unassigned_teams.map((team) => <article key={team.team_id}>
            <div><strong>{team.team_name}</strong><span>{team.leader_name || "Leader not available"}</span></div>
            <span className="change-problem-status change-problem-status--not_assigned">Not assigned</span>
            <button className="primary-button" onClick={() => openDialog(team)}>Assign Problem</button>
          </article>)}
        </div> : <div className="change-problem-all-assigned"><strong>All participants have received a Round 1 problem statement.</strong><p>This section stays visible and will update automatically if assignment data changes.</p></div>}
      </section>

      {dialog && <AssignmentDialog
        key={`${dialog.team.team_id}-${dialog.targetProblemId || "select"}`}
        team={dialog.team}
        problems={data.problems}
        initialProblemId={dialog.targetProblemId}
        working={workingTeamId === dialog.team.team_id}
        onCancel={() => setDialog(null)}
        onConfirm={(targetProblemId, newBalance) => void confirmChange(targetProblemId, newBalance)}
      />}
    </section>
  );
}
