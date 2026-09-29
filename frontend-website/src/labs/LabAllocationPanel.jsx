import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import "./LabAllocationPanel.modal.css";
import { applyLabChange, invalidDrop } from "./labBoard";

const coins = value => value == null ? "Not recorded" : `${Number(value).toLocaleString()} coins`;
export const hasAssignedProblem = team => team.problem_assignment_status
  ? team.problem_assignment_status === "allocated"
  : Boolean(team.final_problem || team.effective_problem || team.round1 || team.wildcard_history?.selected);
const labStatus = team => team.lab_name || (hasAssignedProblem(team) ? "Lab pending" : "Awaiting problem");
const overrideTitle = "This team was manually placed despite another team with the same problem statement being in this lab.";
const problemFor = team => team.final_problem
  ? { number: team.final_problem.problem_number, title: team.final_problem.problem_title }
  : team.effective_problem || { number: "PS pending", title: "Awaiting problem" };
const allocationStatus = team => team.lab_allocation_status || (team.current_lab_id ? "assigned" : "unassigned");

function SegmentedFilter({ options, value, onChange }) {
  return <div className="lab-segments" role="tablist" aria-label="Team filters">
    {options.map(([id, label, count], index) => <button key={id} type="button" role="tab" aria-selected={value === id}
      data-filter={id} tabIndex={value === id ? 0 : -1} onClick={() => onChange(id)}
      onKeyDown={event => {
        const next = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1
          : event.key === "ArrowRight" ? (index + 1) % options.length : event.key === "ArrowLeft" ? (index + options.length - 1) % options.length : null;
        if (next === null) return;
        event.preventDefault(); onChange(options[next][0]); event.currentTarget.parentElement.children[next].focus();
      }}>{label}<span>{count}</span></button>)}
  </div>;
}

function OverrideBadge() {
  return <small className="lab-override-badge" title={overrideTitle}>Same PS</small>;
}
export const ordinal = value => {
  const number = Number(value);
  if (!Number.isInteger(number) || number < 1) return "—";
  const lastTwo = number % 100;
  const suffix = lastTwo >= 11 && lastTwo <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[number % 10] || "th");
  return `${number}${suffix}`;
};

function AssignmentCard({ type, problem, bid, place, assignmentType, selected = true }) {
  const wildcard = type === "Wildcard";
  const placeLabel = assignmentType === "MANUAL_ASSIGNMENT" ? "Manual Assignment" : ordinal(place);
  return <article className="assignment-history-card">
    <header><span>{type}</span></header>
    {selected ? <div className="assignment-history-card__body">
      <div className="assignment-problem"><strong>{problem.problem_number}</strong><span>{problem.problem_title}</span></div>
      <dl className="assignment-stats">
        <div><dt>{wildcard ? "Bid" : "Bid / Cost"}</dt><dd>{coins(bid)}</dd></div>
        <div><dt>Place</dt><dd className={assignmentType === "MANUAL_ASSIGNMENT" ? "assignment-place--manual" : ""}>{placeLabel}</dd></div>
      </dl>
    </div> : <p className="assignment-history-card__empty">{wildcard ? "Not selected" : "Not assigned"}</p>}
  </article>;
}

export default function LabAllocationPanel({ board, loading = false, error = "", onReload, onAllocate, onMove,
  onBoardChange, onAssignConflict, canAllocate = false, canMove = false, view = "all", showHeader = true }) {
  const [working, setWorking] = useState(false);
  const [generating, setGenerating] = useState(false);
  const inFlight = useRef(false);
  const [localError, setLocalError] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState(null);
  const [dragged, setDragged] = useState(null);
  const [picker, setPicker] = useState(null);
  const [target, setTarget] = useState("");
  const [confirmation, setConfirmation] = useState(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [selectedTeamId, setSelectedTeamId] = useState(null);
  const dialog = useRef(null);
  const workspace = useRef(null);
  const shown = pending ? applyLabChange(board, pending) : board;
  const editable = canMove && Boolean(board?.can_move) && !working;
  const assigned = (shown?.labs || []).flatMap(lab => lab.teams.map(team => ({ ...team, lab_name: lab.name })));
  const allocatedTeamIds = new Set(assigned.map(team => team.id));
  const assignedById = new Map(assigned.map(team => [team.id, team]));
  const teams = (shown?.teams || []).map(team => assignedById.get(team.id) || team);
  const unassigned = teams.filter(team => !allocatedTeamIds.has(team.id));
  const problemAssigned = teams.filter(hasAssignedProblem).length;
  const selectedTeam = teams.find(team => team.id === selectedTeamId) || null;

  const overlayKey = picker ? `assignment-${picker.id}` : selectedTeamId ? `details-${selectedTeamId}` : null;
  useEffect(() => {
    if (!overlayKey) return undefined;
    const previousOverflow = document.body.style.overflow;
    let previousFocus = document.activeElement;
    while (previousFocus?.shadowRoot?.activeElement) previousFocus = previousFocus.shadowRoot.activeElement;
    const triggerId = previousFocus?.dataset?.labAction;
    const handleKeyDown = event => {
      if (event.key === "Escape" && !inFlight.current) { setSelectedTeamId(null); setPicker(null); setConfirmation(null); }
      if (event.key !== "Tab") return;
      const controls = [...(dialog.current?.querySelectorAll('button:not(:disabled), input:not(:disabled), [tabindex="0"]') || [])];
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", handleKeyDown);
    dialog.current?.querySelector("button")?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
      const nextFocus = previousFocus?.isConnected ? previousFocus
        : (triggerId && workspace.current?.querySelector(`[data-lab-action="${triggerId}"]`)) || workspace.current?.querySelector('[role="tab"][aria-selected="true"]');
      nextFocus?.focus();
    };
  }, [overlayKey]);
  useEffect(() => { setFilter("all"); setSelectedTeamId(null); setPicker(null); setConfirmation(null); }, [view]);
  useEffect(() => {
    if (confirmation) dialog.current?.querySelector(".lab-drawer__confirmation button")?.focus();
    else dialog.current?.querySelector('input:checked')?.focus();
  }, [confirmation]);

  const move = async (team, lab) => {
    if (!editable || !onMove || inFlight.current) return;
    const reason = invalidDrop(team, lab);
    if (reason) { setLocalError(reason); return; }
    inFlight.current = true; setWorking(true); setLocalError(""); setNotice("");
    setPending({ team_id: team.id, lab: { id: lab.id, name: lab.name }, version: team.version || 0 });
    try {
      const result = await onMove(team.id, { lab_id: lab.id, expected_version: team.version || 0 });
      onBoardChange?.(current => applyLabChange(current, result));
      setNotice("Assignment updated"); setPicker(null); setTarget("");
    } catch (cause) {
      setLocalError(cause.message || "The assignment could not be saved. The team was returned to its original lab.");
    } finally { setPending(null); setWorking(false); inFlight.current = false; }
  };
  const assignConflict = async (team, lab, allowOverride = false) => {
    if (!editable || !onAssignConflict || inFlight.current) return;
    if (!lab) { setLocalError("This lab is no longer available. Choose another destination."); setConfirmation(null); return; }
    const duplicate = lab.teams.some(row => row.effective_problem?.id === team.effective_problem?.id);
    if (duplicate && !allowOverride) { setConfirmation({ team, lab }); return; }
    inFlight.current = true; setWorking(true); setLocalError(""); setNotice("");
    try {
      const result = await onAssignConflict(team.id, { lab_id: lab.id, allow_constraint_override: allowOverride });
      onBoardChange?.(current => applyLabChange(current, result));
      setNotice("Assignment updated"); setPicker(null); setTarget(""); setConfirmation(null);
    } catch (cause) { setLocalError(cause.message || "The conflict assignment could not be saved."); }
    finally { setWorking(false); inFlight.current = false; }
  };
  const generate = async () => {
    if (inFlight.current) return;
    inFlight.current = true; setWorking(true); setGenerating(true); setLocalError(""); setNotice("");
    try { await onAllocate(); await onReload?.(); }
    catch (cause) { setLocalError(cause.message || "Allocation failed."); }
    finally { setWorking(false); setGenerating(false); inFlight.current = false; }
  };
  const openPicker = team => { setSelectedTeamId(null); setPicker(team); setTarget(""); setConfirmation(null); setLocalError(""); };
  const closeOverlay = () => { if (!working) { setPicker(null); setSelectedTeamId(null); setConfirmation(null); } };
  const actionFor = team => {
    if (!editable || !team.effective_problem) return null;
    if (allocationStatus(team) === "conflict" && onAssignConflict) return "Assign lab";
    if (allocationStatus(team) === "assigned" && onMove) return "Move";
    return null;
  };
  const teamEntry = team => <div className="lab-team-row" key={team.id}
    draggable={editable && Boolean(team.effective_problem) && allocationStatus(team) === "assigned"}
    onDragStart={event => { setDragged(team); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", String(team.id)); }}
    onDragEnd={() => setDragged(null)}>
    <b>{team.team_code}</b><strong title={team.team_name}>{team.team_name}</strong>
    <em className="problem-badge" title={problemFor(team).title}>{problemFor(team).number}</em>
    {team.constraint_override && <OverrideBadge />}
    {actionFor(team) && <button type="button" data-lab-action={team.id} aria-label={`${actionFor(team)} ${team.team_name}`} onClick={() => openPicker(team)}>{actionFor(team)}</button>}
  </div>;

  if (loading && !board) return <p className="lab-panel-state">Loading lab allocation…</p>;
  if (!shown) return <p className="lab-inline-error" role="alert">{error || "Lab allocation unavailable."}</p>;
  const assignedCount = shown.assigned_count ?? assigned.length;
  const conflictCount = shown.conflict_count ?? 0;
  const unassignedCount = shown.lab_unassigned_count ?? 0;
  const eligibleCount = shown.allocation_eligible_count ?? shown.eligible_team_count ?? 0;
  const awaitingCount = shown.awaiting_problem_count ?? teams.filter(team => !hasAssignedProblem(team)).length;
  const capacity = shown.labs.reduce((sum, lab) => sum + lab.capacity, 0);
  const used = shown.labs.reduce((sum, lab) => sum + lab.occupancy, 0);
  const options = view === "teams"
    ? [["all", "All", teams.length], ["ps_allocated", "PS Allocated", problemAssigned], ["ps_not_allocated", "PS Not Allocated", teams.length - problemAssigned]]
    : [["all", "All", teams.length], ["assigned", "Assigned", assignedCount], ["conflict", "Conflict", conflictCount], ["unassigned", "Unassigned", unassignedCount]];
  const filtered = teams.filter(team => {
    const searchable = [team.team_name, team.team_code, team.round1?.problem_number, team.round1?.problem_title,
      team.wildcard_history?.problem_number, team.wildcard_history?.problem_title,
      team.final_problem?.problem_number, team.final_problem?.problem_title,
      team.effective_problem?.number, team.effective_problem?.title, team.lab_name].join(" ").toLowerCase();
    return searchable.includes(query.toLowerCase()) && (filter === "all"
      || (view === "teams" ? (filter === "ps_allocated" && hasAssignedProblem(team)) || (filter === "ps_not_allocated" && !hasAssignedProblem(team))
        : team.lab_allocation_status === filter));
  });
  const teamRows = rows => <div className="team-allotment-list">
    <div className="team-allotment-list__head"><span>Team</span><span>Problem</span><span>PS Status</span><span>Lab</span><span>Status</span><span>Action</span></div>
    {rows.map(team => <div className="team-allotment-row" key={team.id}>
      <span className="team-identity"><b>{team.team_code}</b><strong>{team.team_name}</strong><small>Logged in <span className={`team-presence ${team.logged_in ? "team-presence--online" : ""}`}>{team.logged_in ? "YES" : "NO"}</span></small></span>
      <span className="team-problem"><b>{problemFor(team).number}</b><small title={problemFor(team).title}>{problemFor(team).title}</small></span>
      <span><span className={`lab-status-chip ${hasAssignedProblem(team) ? "lab-status-chip--ps" : ""}`}>{hasAssignedProblem(team) ? "PS Allocated" : "PS Pending"}</span></span>
      <span className="team-lab">{labStatus(team)}{team.constraint_override && <OverrideBadge />}</span>
      <span><span className={`lab-status-chip lab-status-chip--${allocationStatus(team)}`}>{allocationStatus(team) === "assigned" ? "Assigned" : allocationStatus(team) === "conflict" ? "Conflict" : "Unassigned"}</span></span>
      <span className="team-action">{view !== "teams" && actionFor(team)
        ? <button type="button" className="secondary-button" data-lab-action={team.id} onClick={() => openPicker(team)}>{actionFor(team)}</button>
        : (view === "teams" || hasAssignedProblem(team)) && <button type="button" className="secondary-button" onClick={() => setSelectedTeamId(team.id)}>View Details</button>}</span>
      {team.lab_allocation_status === "conflict" && <small className="lab-conflict-reason">Same PS already occupies all compatible labs</small>}
    </div>)}
    {!rows.length && <p className="lab-empty-row">No teams match these filters.</p>}
  </div>;
  const showResults = view === "teams" || filter !== "all" || Boolean(query);
  const conflicts = unassigned.filter(team => team.lab_allocation_status === "conflict");
  const awaiting = unassigned.filter(team => team.lab_allocation_status !== "conflict");
  const pickerTeam = picker && (teams.find(team => team.id === picker.id) || picker);
  const destinations = pickerTeam ? shown.labs.filter(lab => lab.id !== pickerTeam.current_lab_id
    && (pickerTeam.lab_allocation_status !== "conflict" || lab.occupancy < lab.capacity)) : [];
  const confirmedLab = confirmation && shown.labs.find(lab => lab.id === confirmation.lab.id);

  return <section ref={workspace} className="lab-workspace" aria-busy={working}>
    {showHeader && <header className="lab-workspace__header"><div><h2>{view === "teams" ? "Teams" : "Lab Allocation"}</h2><p>{view === "teams" ? "Problem and lab assignment status" : "Final placement for participating teams"}</p></div>
      <div className="lab-workspace__actions"><button type="button" className="secondary-button" disabled={working} onClick={() => void onReload?.()}>Refresh</button>
        {canAllocate && shown.can_allocate && <button className="primary-button" disabled={working} onClick={() => void generate()}>{working ? "Generating…" : "Generate allocation"}</button>}</div>
    </header>}
    {canMove && !shown.can_move && <p className="notice">Lab assignments become editable after Wildcard is complete.</p>}
    {(error || localError) && <p className="lab-inline-error" role="alert">{localError || error}</p>}
    <div className="lab-save-status" role="status" aria-live="polite">{generating ? "Generating allocation…" : working ? "Saving assignment…" : notice}</div>
    {view === "teams"
      ? <dl className="lab-allocation-summary lab-allocation-summary--teams"><div><dt>Logged In Teams</dt><dd>{shown.participant_logged_in_count ?? teams.filter(team => team.logged_in).length} <span>/ {shown.team_count ?? teams.length}</span></dd><small>Participant presence</small></div><div><dt>Problem Assigned</dt><dd>{problemAssigned} <span>/ {teams.length}</span></dd><small>Current problem allocation</small></div></dl>
      : <dl className="lab-allocation-summary"><div><dt>Assigned</dt><dd>{assignedCount}</dd><small>{eligibleCount ? Math.round(assignedCount / eligibleCount * 100) : 0}% of eligible teams</small></div><div><dt>Conflict</dt><dd>{conflictCount}</dd><small>Same-PS restriction</small></div><div><dt>Unassigned</dt><dd>{unassignedCount}</dd><small>Awaiting placement{awaitingCount > 0 && <span> · {awaitingCount} awaiting PS</span>}</small></div><div><dt>Capacity</dt><dd>{used} <span>/ {capacity}</span></dd><small>Used / available</small></div></dl>}
    <div className="lab-filters"><SegmentedFilter options={options} value={filter} onChange={setFilter} />
      <label className="lab-search"><span className="lab-sr-only">Search teams or PS</span><input type="search" placeholder="Search teams or PS…" value={query} onChange={event => setQuery(event.target.value)} /></label></div>
    {showResults ? <section className="team-allotment-panel" aria-label={filter === "conflict" ? "Conflict Teams" : "Teams"}>
      {filter === "conflict" && <header className="lab-list-heading"><h3>Conflicts <span>{conflictCount}</span></h3><p>These teams have a valid problem statement but could not be placed while maintaining one team per PS per lab.</p></header>}
      {teamRows(filtered)}
    </section> : <>
      {conflicts.length > 0 && <section className="team-allotment-panel lab-conflicts" aria-label="Conflict Teams"><header className="lab-list-heading"><h3>Conflicts <span>{conflicts.length}</span></h3><p>These teams have a valid problem statement but could not be placed while maintaining one team per PS per lab.</p></header>{teamRows(conflicts)}</section>}
      <div className="lab-grid-heading"><h3>Labs</h3><small>{editable ? "Drag a team to a lab, or choose Move." : "Current team placements"}</small></div>
      <div className="lab-bucket-grid">{shown.labs.map(lab => {
        const reason = dragged ? invalidDrop(dragged, lab) : "";
        return <article key={lab.id} aria-label={lab.name} className={`lab-bucket ${lab.occupancy >= lab.capacity ? "lab-bucket--full" : ""} ${dragged && !reason && editable ? "lab-bucket--target" : ""}`}
          onDragOver={event => { if (editable && dragged && !reason) { event.preventDefault(); event.dataTransfer.dropEffect = "move"; } }}
          onDrop={event => { event.preventDefault(); const team = teams.find(row => row.id === Number(event.dataTransfer.getData("text/plain"))); setDragged(null); if (team) void move(team, lab); }}>
          <header><h4>{lab.name}</h4><span>{lab.occupancy} / {lab.capacity}</span></header>
          <div className="lab-capacity-bar" role="meter" aria-label={`${lab.name} capacity`} aria-valuenow={lab.occupancy} aria-valuemin={0} aria-valuemax={lab.capacity}><span style={{ width: `${lab.capacity ? Math.min(100, lab.occupancy / lab.capacity * 100) : 0}%` }} /></div>
          <p className="lab-slots">{lab.occupancy >= lab.capacity ? "Full" : `${lab.capacity - lab.occupancy} ${lab.capacity - lab.occupancy === 1 ? "seat" : "seats"} available`}{dragged && !reason && editable ? " · Drop here" : ""}</p>
          <div className="lab-team-list">{lab.teams.length ? lab.teams.map(teamEntry) : <p className="lab-bucket-empty">No teams assigned yet<small>Teams will appear here after allocation.</small></p>}</div>
        </article>;
      })}</div>
      {!shown.labs.length && <p className="lab-empty-row">No labs configured. Ask the Event Admin to add labs.</p>}
      {awaiting.length > 0 && <section className="team-allotment-panel lab-unassigned" aria-label="Unassigned Teams"><header className="lab-list-heading"><h3>Unassigned <span>{awaiting.length}</span></h3><p>Teams awaiting a valid problem or lab placement.</p></header>{teamRows(awaiting)}</section>}
    </>}
    {selectedTeam && createPortal(<div className="lab-overlay team-details-modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) closeOverlay(); }}>
      <section ref={dialog} className="team-details-modal" role="dialog" aria-modal="true" aria-labelledby={`team-details-${selectedTeam.id}`}>
        <header><div><span>Team details</span><h2 id={`team-details-${selectedTeam.id}`}>{selectedTeam.team_name}</h2>{selectedTeam.team_code && <small>{selectedTeam.team_code}</small>}</div><button type="button" className="lab-sheet-close" aria-label="Close details" onClick={closeOverlay}>×</button></header>
        <div className="team-details-modal__body">
          <section className="team-details-final-problem"><span>Final / Current Problem</span>{selectedTeam.final_problem
            ? <div><strong>{selectedTeam.final_problem.problem_number}</strong><b>{selectedTeam.final_problem.problem_title}</b></div>
            : <b>Not assigned</b>}</section>
          <div className="assignment-history-grid">
            <AssignmentCard type="Round 1" problem={selectedTeam.round1} bid={selectedTeam.round1?.winning_bid} place={selectedTeam.round1?.place} assignmentType={selectedTeam.round1?.assignment_type} selected={Boolean(selectedTeam.round1)} />
            <AssignmentCard type="Wildcard" problem={selectedTeam.wildcard_history} bid={selectedTeam.wildcard_history?.winning_bid} place={selectedTeam.wildcard_history?.place} selected={Boolean(selectedTeam.wildcard_history?.selected)} />
          </div>
          <section className="team-details-lab"><span>Lab Allocation</span><strong>{labStatus(selectedTeam)}</strong>{selectedTeam.constraint_override && <OverrideBadge />}</section>
        </div>
        <footer><button type="button" className="secondary-button" onClick={closeOverlay}>Close</button></footer>
      </section>
    </div>, document.body)}
    {pickerTeam && createPortal(<div className="lab-overlay lab-drawer-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) closeOverlay(); }}>
      <section ref={dialog} className="lab-drawer" role="dialog" aria-modal="true" aria-labelledby="lab-drawer-title">
        <header><h2 id="lab-drawer-title">{pickerTeam.lab_allocation_status === "conflict" ? "Assign lab" : "Move team"}</h2><button type="button" className="lab-sheet-close" disabled={working} aria-label="Close assignment" onClick={closeOverlay}>×</button></header>
        <div className="lab-drawer__body"><section className="lab-drawer__team"><h3>{pickerTeam.team_name}</h3><small>{pickerTeam.team_code}</small><span>Final Problem</span><b>{problemFor(pickerTeam).number} · {problemFor(pickerTeam).title}</b></section>
          {localError && <p className="lab-inline-error" role="alert">{localError}</p>}
          {confirmation ? <section className="lab-drawer__confirmation"><h3>Same problem already present</h3><p>{confirmation.lab.name} already contains {pickerTeam.effective_problem.number}.</p><p>Assigning this team will intentionally override the one-team-per-PS rule.</p><p>Lab capacity remains enforced: {confirmedLab?.occupancy ?? "—"} / {confirmedLab?.capacity ?? "—"}.</p>
            {(!confirmedLab || confirmedLab.occupancy >= confirmedLab.capacity) && <p role="alert">This destination is no longer available. Go back to choose another lab.</p>}
            <div className="lab-drawer__actions"><button type="button" className="secondary-button" disabled={working} onClick={() => setConfirmation(null)}>Back</button><button type="button" className="primary-button" disabled={working || !editable || !confirmedLab || confirmedLab.occupancy >= confirmedLab.capacity} onClick={() => void assignConflict(pickerTeam, confirmedLab, true)}>{working ? "Saving…" : "Assign anyway"}</button></div>
          </section> : <form onSubmit={event => { event.preventDefault(); const lab = shown.labs.find(row => row.id === Number(target)); if (lab) void (pickerTeam.lab_allocation_status === "conflict" ? assignConflict(pickerTeam, lab) : move(pickerTeam, lab)); }}>
            <fieldset disabled={working}><legend>Available labs</legend>{destinations.map(lab => {
              const reason = pickerTeam.lab_allocation_status === "conflict" ? "" : invalidDrop(pickerTeam, lab);
              const duplicate = lab.teams.some(row => row.effective_problem?.id === pickerTeam.effective_problem?.id);
              return <label className={`lab-destination ${reason ? "lab-destination--unavailable" : ""}`} key={lab.id}><input type="radio" name="destination" value={lab.id} checked={target === String(lab.id)} disabled={Boolean(reason)} onChange={event => setTarget(event.target.value)} /><span><strong>{lab.name}</strong><small>{reason || `${lab.capacity - lab.occupancy} seats available`}</small>{duplicate && <small className="lab-destination__warning">{pickerTeam.effective_problem.number} already present</small>}</span><b>{lab.occupancy} / {lab.capacity}</b></label>;
            })}{!destinations.length && <p>No labs have space available.</p>}</fieldset>
            <div className="lab-drawer__actions"><button type="button" className="secondary-button" disabled={working} onClick={closeOverlay}>Cancel</button><button type="submit" className="primary-button" disabled={!target || !editable}>{working ? "Saving…" : pickerTeam.lab_allocation_status === "conflict" ? "Assign lab" : "Move team"}</button></div>
          </form>}
        </div>
      </section>
    </div>, document.body)}
  </section>;
}
