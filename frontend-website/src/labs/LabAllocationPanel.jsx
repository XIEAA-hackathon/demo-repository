import { useRef, useState } from "react";
import { applyLabChange, invalidDrop } from "./labBoard";

export default function LabAllocationPanel({ board, loading = false, error = "", onReload, onAllocate, onMove,
  onBoardChange, canAllocate = false, canMove = false, view = "all" }) {
  const [working, setWorking] = useState(false);
  const inFlight = useRef(false);
  const [localError, setLocalError] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState(null);
  const [dragged, setDragged] = useState(null);
  const [picker, setPicker] = useState(null);
  const [target, setTarget] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const shown = pending ? applyLabChange(board, pending) : board;
  const editable = canMove && Boolean(board?.can_move) && !working;
  const assigned = (shown?.labs || []).flatMap(lab => lab.teams.map(team => ({ ...team, lab_name: lab.name })));
  const teams = (shown?.teams || []).map(team => assigned.find(row => row.id === team.id) || team);
  const unassigned = teams.filter(team => shown.unassigned_team_ids.includes(team.id));

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
  const generate = async () => {
    if (inFlight.current) return;
    inFlight.current = true; setWorking(true); setLocalError("");
    try { await onAllocate(); await onReload?.(); }
    catch (cause) { setLocalError(cause.message || "Allocation failed."); }
    finally { setWorking(false); inFlight.current = false; }
  };
  const teamEntry = team => <div className="lab-team-row" key={team.id} draggable={editable && Boolean(team.effective_problem)}
    onDragStart={event => { setDragged(team); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", String(team.id)); }}
    onDragEnd={() => setDragged(null)}>
    <b>{team.team_code}</b><strong title={team.team_name}>{team.team_name}</strong>
    <em className="problem-badge" title={team.effective_problem?.title}>{team.effective_problem?.number || "PS pending"}</em>
    {canMove && <button type="button" disabled={!editable || !team.effective_problem} aria-label={`Move ${team.team_name}`}
      onClick={() => { setPicker(team); setTarget(""); }}>Move</button>}
  </div>;

  if (loading && !board) return <p className="lab-panel-state">Loading lab allocation…</p>;
  if (!shown) return <p className="lab-inline-error" role="alert">{error || "Lab allocation unavailable."}</p>;
  const filtered = teams.filter(team => {
    const allocated = Boolean(team.current_lab_id);
    const searchable = [team.team_name, team.team_code, team.effective_problem?.number, team.effective_problem?.title, team.lab_name].join(" ").toLowerCase();
    return searchable.includes(query.toLowerCase()) && (filter === "all" || (filter === "allocated") === allocated);
  });
  return <section className="lab-workspace" aria-busy={working}>
    <header className="lab-workspace__header"><div><h2>{view === "teams" ? "Teams" : "Labs"}</h2><p>{shown.message}</p></div>
      <div className="lab-workspace__actions"><button type="button" className="secondary-button" disabled={working} onClick={() => void onReload?.()}>Refresh</button>
        {canAllocate && shown.can_allocate && <button className="primary-button" disabled={working} onClick={() => void generate()}>Generate allocation</button>}</div>
    </header>
    {canMove && !shown.can_move && <p className="notice">Lab assignments become editable after Wildcard is complete.</p>}
    {(error || localError) && <p className="lab-inline-error" role="alert">{localError || error}</p>}
    <p className="lab-save-status" role="status">{working ? "Saving assignment…" : notice}</p>
    <dl className="lab-allocation-summary"><div><dt>Eligible teams</dt><dd>{shown.eligible_team_count ?? shown.team_count ?? 0}</dd></div><div><dt>Assigned</dt><dd>{shown.assigned_count ?? assigned.length}</dd></div><div><dt>Unassigned</dt><dd>{shown.unassigned_count ?? unassigned.length}</dd></div></dl>
    {view !== "labs" && <section className="team-allotment-panel" aria-label="Teams">
      <div className="lab-filters"><label>Search teams, PS or lab<input type="search" value={query} onChange={event => setQuery(event.target.value)} /></label>
        <label>Allocation status<select value={filter} onChange={event => setFilter(event.target.value)}><option value="all">All teams</option><option value="allocated">Allocated</option><option value="pending">Unallocated</option></select></label></div>
      <div className="team-allotment-list"><div className="team-allotment-list__head"><span>Team</span><span>Final problem</span><span>Lab / status</span></div>
        {filtered.map(team => <div className="team-allotment-row" key={team.id}><span className="team-identity"><b>{team.team_code}</b><strong>{team.team_name}</strong></span>
          <span>{team.effective_problem ? `${team.effective_problem.number} — ${team.effective_problem.title}` : "Final problem pending"}</span>
          <span>{team.lab_name || "Not assigned"} · {team.current_lab_id ? "ALLOCATED" : "PENDING"}</span></div>)}
        {!filtered.length && <p className="lab-empty-row">No teams match these filters.</p>}</div>
    </section>}
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
      <section className="lab-unassigned" aria-label="Unassigned Teams"><h3>Unassigned Teams · {unassigned.length}</h3>
        {unassigned.length > 0 && <p role="status">These teams still need a lab assignment.</p>}{unassigned.map(teamEntry)}
      </section>
    </>}
    {picker && <form className="lab-move-picker" onSubmit={event => { event.preventDefault(); const lab = shown.labs.find(row => row.id === Number(target)); if (lab) void move(picker, lab); }}>
      <h3>Move {picker.team_name}</h3><label>Target lab<select autoFocus value={target} onChange={event => setTarget(event.target.value)}><option value="">Choose lab</option>
        {shown.labs.filter(lab => lab.id !== picker.current_lab_id).map(lab => <option key={lab.id} value={lab.id} disabled={Boolean(invalidDrop(picker, lab))}>{lab.name} · {invalidDrop(picker, lab) || `${lab.occupancy}/${lab.capacity}`}</option>)}</select></label>
      <button type="submit" className="primary-button" disabled={!target || !editable}>Move team</button><button type="button" className="secondary-button" onClick={() => setPicker(null)}>Cancel</button>
    </form>}
  </section>;
}
