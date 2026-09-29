import { useCallback, useEffect, useRef, useState } from "react";
import { autoAssignExtraGrid, getExtraGrid } from "../services/api";

/** @param {{realtimeEvent?: any, onAssigned?: ((result: any) => void) | null, selectedProblemId?: number | null, onSelectProblem?: ((id: number | null) => void) | null}} props */
export default function ExtraGrid({ realtimeEvent, onAssigned = null, selectedProblemId = null, onSelectProblem = null }) {
  const [data, setData] = useState(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [deduction, setDeduction] = useState("");
  const priceEdited = useRef(false);
  const revision = useRef(0);
  const inFlight = useRef(null);
  const load = useCallback(() => {
    if (inFlight.current) return inFlight.current;
    const startedRevision = revision.current;
    const request = getExtraGrid().then(next => {
      if (revision.current !== startedRevision) return;
      setData(next);
      if (!priceEdited.current) setDeduction(String(next.suggested_auto_deduction));
      setError("");
    }).catch(cause => { if (revision.current === startedRevision) setError(cause.message); });
    inFlight.current = request;
    void request.finally(() => { inFlight.current = null; if (revision.current !== startedRevision) void load(); });
    return request;
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (realtimeEvent?.payload?.action === "event_reset") { priceEdited.current = false; setResult(null); setData(null); onSelectProblem?.(null); }
    if (["round1_assignment_changed", "round1_ended", "external_problems_imported"].includes(realtimeEvent?.type)
      || (realtimeEvent?.type === "round_updated" && ["extra_grid_assigned", "winners_assigned", "problem_manually_assigned", "problem_no_bids"].includes(realtimeEvent.payload?.action))
      || realtimeEvent?.payload?.action === "event_reset"
      || ["event_snapshot", "event_state_changed"].includes(realtimeEvent?.type)) { revision.current += 1; void load(); }
  }, [load, realtimeEvent, onSelectProblem]);
  const assign = async () => {
    setWorking(true); setError("");
    revision.current += 1;
    try { const next = await autoAssignExtraGrid(selectedProblemId, Number(deduction)); revision.current += 1; setData(next); setResult(next); onAssigned?.(next); }
    catch (cause) { setError(cause.message); }
    finally { setWorking(false); }
  };
  if (!data) return error ? <p role="alert">{error}</p> : null;
  const validDeduction = /^\d+$/.test(deduction) && Number.isSafeInteger(Number(deduction));
  const target = data.problems.find(problem => problem.id === selectedProblemId);
  const availableSlots = data.problems.reduce((total, problem) => total + problem.capacity_remaining, 0);
  return <section className="external-problems-panel extra-grid">
    <header><div><h3>Automatic Extra / Grid Assignment</h3><p>Unassigned teams: {data.unassigned_teams.length} · Available problem slots: {availableSlots}</p></div>
      <button className="primary-button" title={target ? `Auto assign only #${target.problem_number} ${target.title}` : "Select a problem row for automatic assignment"} disabled={working || !data.can_auto_assign || !data.unassigned_teams.length || !validDeduction || !target?.capacity_remaining} onClick={() => void assign()}>{working ? "Assigning…" : "AUTO ASSIGN REMAINING TEAMS"}</button>
    </header>
    <div className="extra-grid-price"><label htmlFor="extra-assignment-deduction">Automatic assignment price<input id="extra-assignment-deduction" type="number" min="0" step="1" inputMode="numeric" value={deduction} disabled={working} onChange={event => { priceEdited.current = true; setDeduction(event.target.value); }} /><span>coins per team</span></label>
      <p>Suggested: {data.suggested_auto_deduction} coins · {data.r1_bid_count ? `${data.automatic_price_source}: ${data.r1_bid_sum} / ${data.r1_bid_count}.` : "No Round 1 bids: Round 1 minimum bid."} Editable before assignment. Teams with insufficient coins remain unassigned.</p></div>
    {!data.can_auto_assign && <p>End Round 1 to enable automatic assignment.</p>}
    {error && <p role="alert">{error}</p>}
    <div className="external-problems-list">{data.problems.map(problem => <article key={problem.id} role="button" tabIndex={0} aria-pressed={problem.id === selectedProblemId} aria-disabled={working || !data.can_auto_assign || !problem.capacity_remaining} onClick={() => { if (!working && data.can_auto_assign && problem.capacity_remaining) onSelectProblem?.(problem.id); }} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.currentTarget.click(); } }}><div><strong>#{problem.problem_number} {problem.title}</strong><span>{problem.source_label}</span></div><span>{problem.assigned_team_count}/{problem.capacity} used · {problem.capacity_remaining} remaining</span></article>)}</div>
    <p>Unassigned: {data.unassigned_teams.map(team => team.team_name).join(", ") || "None"}</p>
    <p>Automatic assignments: {data.teams.filter(team => team.extra_assignment).map(team => `${team.team_name} → #${team.current_problem.problem_number}`).join(", ") || "None"}</p>
    {result && <p role="status">{result.assignments.length} teams assigned at {result.deduction} coins per team.</p>}
    {result?.failures.length > 0 && <ul role="alert">{result.failures.map(row => <li key={row.team_id}>{row.team_name}: {row.reason}{row.required != null ? ` (required ${row.required}, available ${row.available})` : ""}</li>)}</ul>}
  </section>;
}
