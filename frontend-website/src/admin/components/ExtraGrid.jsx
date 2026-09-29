import { useCallback, useEffect, useRef, useState } from "react";
import { autoAssignExtraGrid, getExtraGrid } from "../services/api";

/** @param {{realtimeEvent?: any, onAssigned?: ((result: any) => void) | null, selectedProblemId?: number | null, onSelectProblem?: ((id: number | null) => void) | null}} props */
export default function ExtraGrid({ realtimeEvent, onAssigned = null, selectedProblemId, onSelectProblem = null }) {
  const [data, setData] = useState(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [deduction, setDeduction] = useState("");
  const [localProblemId, setLocalProblemId] = useState(null);
  const problemId = selectedProblemId === undefined ? localProblemId : selectedProblemId;
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
    if (realtimeEvent?.payload?.action === "event_reset") { priceEdited.current = false; setResult(null); setData(null); setLocalProblemId(null); onSelectProblem?.(null); }
    if (["round1_assignment_changed", "round1_ended", "external_problems_imported"].includes(realtimeEvent?.type)
      || (realtimeEvent?.type === "round_updated" && ["extra_grid_assigned", "winners_assigned", "problem_manually_assigned", "problem_no_bids"].includes(realtimeEvent.payload?.action))
      || realtimeEvent?.payload?.action === "event_reset"
      || ["event_snapshot", "event_state_changed"].includes(realtimeEvent?.type)) { revision.current += 1; void load(); }
  }, [load, realtimeEvent, onSelectProblem]);
  useEffect(() => {
    if (data && problemId != null && !data.problems.some(problem => problem.id === problemId && problem.capacity_remaining > 0)) {
      setLocalProblemId(null); onSelectProblem?.(null);
    }
  }, [data, problemId, onSelectProblem]);
  const assign = async () => {
    setWorking(true); setError("");
    revision.current += 1;
    try { const next = await autoAssignExtraGrid(problemId, Number(deduction)); revision.current += 1; setData(next); setResult(next); onAssigned?.(next); }
    catch (cause) { setError(cause.message); }
    finally { setWorking(false); }
  };
  if (!data) return error ? <p role="alert">{error}</p> : null;
  const validDeduction = /^\d+$/.test(deduction) && Number.isSafeInteger(Number(deduction));
  const availableProblems = data.problems.filter(problem => problem.capacity_remaining > 0);
  const target = availableProblems.find(problem => problem.id === problemId);
  return <section className="external-problems-panel extra-grid" aria-label="Auto Assign">
    <header><h3>AUTO ASSIGN</h3></header>
    <dl className="extra-grid-summary">
      <div><dt>Remaining Teams</dt><dd id="extra-assignment-remaining">{data.remaining_team_count}</dd></div>
      <div><dt>Suggested Price</dt><dd>{data.suggested_auto_deduction} coins</dd><small>{data.automatic_price_source}</small></div>
    </dl>
    <div className="extra-grid-controls">
      <label htmlFor="extra-assignment-problem">Problem<select id="extra-assignment-problem" value={target?.id ?? ""} disabled={working} onChange={event => { const id = Number(event.target.value) || null; setLocalProblemId(id); onSelectProblem?.(id); }}>
        <option value="">Select problem</option>
        {availableProblems.map(problem => <option key={problem.id} value={problem.id}>{problem.source === "EXTERNAL" ? `External #${problem.problem_number}` : `PS-${problem.problem_number}`} — {problem.capacity_remaining} {problem.capacity_remaining === 1 ? "slot" : "slots"} remaining</option>)}
      </select></label>
      <label htmlFor="extra-assignment-deduction">Deduction per team<input id="extra-assignment-deduction" type="number" min="0" step="1" inputMode="numeric" value={deduction} disabled={working} onChange={event => { priceEdited.current = true; setDeduction(event.target.value); }} /></label>
      <button className="primary-button" disabled={working || !data.can_auto_assign || !data.remaining_team_count || !validDeduction || !target} onClick={() => void assign()}>{working ? "Assigning…" : "AUTO ASSIGN"}</button>
    </div>
    {error && <p role="alert">{error}</p>}
    {result && <p role="status">{result.assignments.length} teams assigned at {result.deduction} coins per team.</p>}
    {result?.failures.length > 0 && <ul role="alert">{result.failures.map(row => <li key={row.team_id}>{row.team_name}: {row.reason}{row.required != null ? ` (required ${row.required}, available ${row.available})` : ""}</li>)}</ul>}
  </section>;
}
