import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import "./LabAllocationPanel.modal.css";
import { applyLabChange, invalidDrop } from "./labBoard";

const coins = value => value == null ? "Not recorded" : `${Number(value).toLocaleString()} coins`;
export const hasAssignedProblem = team => team.problem_assignment_status
  ? team.problem_assignment_status === "allocated"
  : Boolean(team.final_problem || team.effective_problem || team.round1 || team.wildcard_history?.selected);
const labStatus = team => team.lab_name || (hasAssignedProblem(team) ? "Lab pending" : "Awaiting problem");
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
  return <article className={`assignment-history-card ${wildcard ? "assignment-history-card--wildcard" : ""} ${selected ? "" : "assignment-history-card--empty"}`}>
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
  onBoardChange, onAssignConflict, canAllocate = false, canMove = false, view = "all" }) {
  const [working, setWorking] = useState(false);
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
  const closeButton = useRef(null);
  const shown = pending ? applyLabChange(board, pending) : board;
  const editable = canMove && Boolean(board?.can_move) && !working;
  const assigned = (shown?.labs || []).flatMap(lab => lab.teams.map(team => ({ ...team, lab_name: lab.name })));
  const allocatedTeamIds = new Set(assigned.map(team => team.id));
  const teams = (shown?.teams || []).map(team => assigned.find(row => row.id === team.id) || team);
  const unassigned = teams.filter(team => !allocatedTeamIds.has(team.id));
  const problemAssigned = teams.filter(hasAssignedProblem).length;
  const selectedTeam = teams.find(team => team.id === selectedTeamId) || null;

  useEffect(() => {
    if (!selectedTeamId) return undefined;
    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = event => { if (event.key === "Escape") setSelectedTeamId(null); };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", handleKeyDown);
    closeButton.current?.focus();
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener("keydown", handleKeyDown); };
  }, [selectedTeamId]);
  useEffect(() => { if (view !== "teams") setSelectedTeamId(null); }, [view]);
  useEffect(() => { setFilter("all"); }, [view]);

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
    const duplicate = lab.teams.some(row => row.effective_problem?.id === team.effective_problem?.id);
    if (duplicate && !allowOverride) { setConfirmation({ team, lab }); return; }
    inFlight.current = true; setWorking(true); setLocalError("");
    try {
      const result = await onAssignConflict(team.id, { lab_id: lab.id, allow_constraint_override: allowOverride });
      onBoardChange?.(current => applyLabChange(current, result));
      setNotice("Assignment updated"); setPicker(null); setTarget(""); setConfirmation(null);
    } catch (cause) { setLocalError(cause.message || "The conflict assignment could not be saved."); }
    finally { setWorking(false); inFlight.current = false; }
  };
  const generate = async () => {
    if (inFlight.current) return;
    inFlight.current = true; setWorking(true); setLocalError("");
    try { await onAllocate(); await onReload?.(); }
    catch (cause) { setLocalError(cause.message || "Allocation failed."); }
    finally { setWorking(false); inFlight.current = false; }
  };
  const teamEntry = team => <div className="lab-team-row" key={team.id} draggable={editable && Boolean(team.effective_problem) && team.lab_allocation_status !== "conflict"}
    onDragStart={event => { setDragged(team); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", String(team.id)); }}
    onDragEnd={() => setDragged(null)}>
    <b>{team.team_code}</b><strong title={team.team_name}>{team.team_name}</strong>
    <em className="problem-badge" title={team.effective_problem?.title}>{team.effective_problem?.number || "PS pending"}</em>
    {team.constraint_override && <small className="lab-override-badge">Same PS</small>}
    {team.lab_allocation_status === "conflict" && <small className="lab-conflict-reason">Conflict · Same PS already occupies all compatible labs</small>}
    {canMove && <button type="button" disabled={!editable || !team.effective_problem || (team.lab_allocation_status === "conflict" && !onAssignConflict)} aria-label={`${team.lab_allocation_status === "conflict" ? "Assign Lab" : "Move"} ${team.team_name}`}
      onClick={() => { setPicker(team); setTarget(""); }}>{team.lab_allocation_status === "conflict" ? "Assign Lab" : "Move"}</button>}
  </div>;

  if (loading && !board) return <p className="lab-panel-state">Loading lab allocation…</p>;
  if (!shown) return <p className="lab-inline-error" role="alert">{error || "Lab allocation unavailable."}</p>;
  const filtered = teams.filter(team => {
    const searchable = [team.team_name, team.team_code, team.round1?.problem_number, team.round1?.problem_title,
      team.wildcard_history?.problem_number, team.wildcard_history?.problem_title,
      team.final_problem?.problem_number, team.final_problem?.problem_title,
      team.effective_problem?.number, team.effective_problem?.title, team.lab_name].join(" ").toLowerCase();
    return searchable.includes(query.toLowerCase()) && (filter === "all"
      || (view === "teams" ? (filter === "ps_allocated" && hasAssignedProblem(team)) || (filter === "ps_not_allocated" && !hasAssignedProblem(team))
        : (filter === "assigned" && team.lab_allocation_status === "assigned") || (filter === "unassigned" && team.lab_allocation_status === "unassigned") || (filter === "conflict" && team.lab_allocation_status === "conflict")));
  });
  return <section className="lab-workspace" aria-busy={working}>
    <header className="lab-workspace__header"><div><h2>{view === "teams" ? "Team Details" : "Labs"}</h2><p>{shown.message}</p></div>
      <div className="lab-workspace__actions"><button type="button" className="secondary-button" disabled={working} onClick={() => void onReload?.()}>Refresh</button>
        {canAllocate && shown.can_allocate && <button className="primary-button" disabled={working} onClick={() => void generate()}>Generate allocation</button>}</div>
    </header>
    {canMove && !shown.can_move && <p className="notice">Lab assignments become editable after Wildcard is complete.</p>}
    {(error || localError) && <p className="lab-inline-error" role="alert">{localError || error}</p>}
    <p className="lab-save-status" role="status">{working ? "Saving assignment…" : notice}</p>
    {view === "teams"
      ? <dl className="lab-allocation-summary"><div><dt>Logged In Teams</dt><dd>{shown.participant_logged_in_count ?? teams.filter(team => team.logged_in).length} / {shown.team_count ?? teams.length}</dd></div><div><dt>Problem Assigned</dt><dd>{problemAssigned} / {shown.team_count ?? teams.length}</dd></div></dl>
      : <dl className="lab-allocation-summary"><div><dt>Eligible teams</dt><dd>{shown.allocation_eligible_count ?? shown.eligible_team_count ?? 0}</dd></div><div><dt>Assigned</dt><dd>{shown.assigned_count ?? assigned.length}</dd></div><div><dt>Unassigned</dt><dd>{shown.lab_unassigned_count ?? 0}</dd></div><div><dt>Conflict</dt><dd>{shown.conflict_count ?? 0}</dd></div><div><dt>Awaiting problem</dt><dd>{shown.awaiting_problem_count ?? teams.filter(team => !team.final_problem).length}</dd></div></dl>}
    <section className="team-allotment-panel" aria-label="Teams">
      <div className="lab-filters"><label>Search teams<input type="search" value={query} onChange={event => setQuery(event.target.value)} /></label>
        <label>{view === "teams" ? "PS status" : "Allocation status"}<select value={filter} onChange={event => setFilter(event.target.value)}><option value="all">All Teams</option>{view === "teams"
          ? <><option value="ps_allocated">PS Allocated</option><option value="ps_not_allocated">PS Not Allocated</option></>
          : <><option value="assigned">Assigned · {shown.assigned_count ?? 0}</option><option value="unassigned">Unassigned · {shown.lab_unassigned_count ?? 0}</option><option value="conflict">Conflict · {shown.conflict_count ?? 0}</option></>}</select></label></div>
      <div className={`team-allotment-list ${view === "teams" ? "team-allotment-list--ps" : ""}`}><div className="team-allotment-list__head"><span>Team</span><span>Logged In</span>{view === "teams" && <span>PS Status</span>}<span>Lab Status</span><span>Action</span></div>
        {filtered.map(team => <div className="team-allotment-row" key={team.id}><span className="team-identity"><b>{team.team_code}</b><strong>{team.team_name}</strong></span>
          <span className={`team-presence ${team.logged_in ? "team-presence--online" : ""}`}>{team.logged_in ? "YES" : "NO"}</span>
          {view === "teams" && <span>{hasAssignedProblem(team) ? "PS Allocated" : "PS Not Allocated"}</span>}
          <span>{view !== "teams" && team.lab_allocation_status === "conflict"
            ? <><b>{team.effective_problem?.number}</b> · Conflict<small className="lab-conflict-reason">Same PS already occupies all compatible labs</small></>
            : labStatus(team)}</span>
          <span>{view !== "teams" && team.lab_allocation_status === "conflict" && onAssignConflict
            ? <button type="button" className="secondary-button" disabled={!editable} onClick={() => { setPicker(team); setTarget(""); }}>Assign Lab</button>
            : <button type="button" className="secondary-button" onClick={() => setSelectedTeamId(team.id)}>View Details</button>}</span></div>)}
        {!filtered.length && <p className="lab-empty-row">No teams match these filters.</p>}</div>
    </section>
    {view !== "teams" && <>
      <p>{editable ? "Drag a team into a lab, or use Move to choose a destination with the keyboard." : "Current persisted team placements."}</p>
      <div className="lab-bucket-grid">{shown.labs.map(lab => {
        const reason = dragged ? invalidDrop(dragged, lab) : "";
        return <article key={lab.id} aria-label={lab.name} className={`lab-bucket ${lab.occupancy >= lab.capacity ? "lab-bucket--full" : ""} ${dragged && !reason && editable ? "lab-bucket--target" : ""}`}
          onDragOver={event => { if (editable && dragged && !reason) { event.preventDefault(); event.dataTransfer.dropEffect = "move"; } }}
          onDrop={event => { event.preventDefault(); const team = teams.find(row => row.id === Number(event.dataTransfer.getData("text/plain"))); setDragged(null); if (team) void move(team, lab); }}>
          <header><h4>{lab.name}</h4><span>{lab.occupancy} / {lab.capacity}</span></header>
          <p className="lab-slots">{lab.occupancy >= lab.capacity ? "FULL" : `${lab.capacity - lab.occupancy} slots remaining`}{dragged && !reason && editable ? " · DROP HERE" : ""}</p>
          <div className="lab-team-list">{lab.teams.length ? lab.teams.map(teamEntry) : <p className="lab-bucket-empty">No teams assigned</p>}</div>
        </article>;
      })}</div>
      {!shown.labs.length && <p>No labs configured. Ask the Event Admin to add labs.</p>}
      <section className="lab-unassigned" aria-label="Conflict Teams"><h3>Conflict · {unassigned.filter(team => team.lab_allocation_status === "conflict").length}</h3>
        {unassigned.filter(team => team.lab_allocation_status === "conflict").map(teamEntry)}
      </section>
      <section className="lab-unassigned" aria-label="Unassigned Teams"><h3>Unassigned Teams · {unassigned.filter(team => team.lab_allocation_status !== "conflict").length}</h3>
        {unassigned.filter(team => team.lab_allocation_status !== "conflict").map(teamEntry)}
      </section>
    </>}
    {selectedTeam && createPortal(<div className="team-details-modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setSelectedTeamId(null); }}>
      <section className="team-details-modal" role="dialog" aria-modal="true" aria-labelledby={`team-details-${selectedTeam.id}`}>
        <header><div><span>Team details</span><h2 id={`team-details-${selectedTeam.id}`}>{selectedTeam.team_name}</h2>{selectedTeam.team_code && <small>{selectedTeam.team_code}</small>}</div><button ref={closeButton} type="button" className="team-details-modal__x" aria-label="Close details" onClick={() => setSelectedTeamId(null)}>×</button></header>
        <div className="team-details-modal__body">
          <section className="team-details-final-problem"><span>Final / Current Problem</span>{selectedTeam.final_problem
            ? <div><strong>{selectedTeam.final_problem.problem_number}</strong><b>{selectedTeam.final_problem.problem_title}</b></div>
            : <b>Not assigned</b>}</section>
          <div className="assignment-history-grid">
            <AssignmentCard type="Round 1" problem={selectedTeam.round1} bid={selectedTeam.round1?.winning_bid} place={selectedTeam.round1?.place} assignmentType={selectedTeam.round1?.assignment_type} selected={Boolean(selectedTeam.round1)} />
            <AssignmentCard type="Wildcard" problem={selectedTeam.wildcard_history} bid={selectedTeam.wildcard_history?.winning_bid} place={selectedTeam.wildcard_history?.place} selected={Boolean(selectedTeam.wildcard_history?.selected)} />
          </div>
          <section className="team-details-lab"><span>Lab Allocation</span><strong>{labStatus(selectedTeam)}</strong></section>
        </div>
        <footer><button type="button" className="secondary-button" onClick={() => setSelectedTeamId(null)}>Close</button></footer>
      </section>
    </div>, document.body)}
    {picker && <form className="lab-move-picker" onSubmit={event => { event.preventDefault(); const lab = shown.labs.find(row => row.id === Number(target)); if (lab) void (picker.lab_allocation_status === "conflict" ? assignConflict(picker, lab) : move(picker, lab)); }}>
      <h3>{picker.lab_allocation_status === "conflict" ? "Assign" : "Move"} {picker.team_name}</h3><p>Problem {picker.effective_problem?.number}</p><label>Target lab<select autoFocus value={target} onChange={event => setTarget(event.target.value)}><option value="">Choose lab</option>
        {shown.labs.filter(lab => lab.id !== picker.current_lab_id && (picker.lab_allocation_status !== "conflict" || lab.occupancy < lab.capacity)).map(lab => <option key={lab.id} value={lab.id} disabled={picker.lab_allocation_status !== "conflict" && Boolean(invalidDrop(picker, lab))}>{lab.name} · {lab.occupancy}/{lab.capacity}{lab.teams.some(row => row.effective_problem?.id === picker.effective_problem?.id) ? ` · Same PS: ${picker.effective_problem.number} already present` : ""}</option>)}</select></label>
      <button type="submit" className="primary-button" disabled={!target || !editable}>{picker.lab_allocation_status === "conflict" ? "Assign Lab" : "Move team"}</button><button type="button" className="secondary-button" onClick={() => setPicker(null)}>Cancel</button>
    </form>}
    {confirmation && <div className="lab-modal-backdrop"><section className="lab-modal lab-move-picker" role="dialog" aria-modal="true" aria-labelledby="same-ps-confirmation">
      <h3 id="same-ps-confirmation">Same PS conflict</h3>
      <p>{confirmation.lab.name} already contains {confirmation.team.effective_problem.number}. Assigning {confirmation.team.team_name} here will allow two teams with this PS in the same lab.</p>
      <p>Lab capacity: {confirmation.lab.occupancy} / {confirmation.lab.capacity}</p>
      <button type="button" className="secondary-button" disabled={working} onClick={() => setConfirmation(null)}>Cancel</button>
      <button type="button" className="primary-button" disabled={working} onClick={() => void assignConflict(confirmation.team, confirmation.lab, true)}>Assign Anyway</button>
    </section></div>}
  </section>;
}
