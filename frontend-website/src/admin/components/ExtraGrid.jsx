import { useCallback, useEffect, useRef, useState } from "react";
import { autoAssignExtraGrid, getExtraGrid } from "../services/api";

export default function ExtraGrid({ realtimeEvent }) {
  const [data, setData] = useState(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const inFlight = useRef(null);
  const load = useCallback(() => {
    if (inFlight.current) return inFlight.current;
    const request = getExtraGrid().then(setData).catch(cause => setError(cause.message));
    inFlight.current = request;
    void request.finally(() => { inFlight.current = null; });
    return request;
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (["round1_assignment_changed", "round1_ended", "external_problems_imported"].includes(realtimeEvent?.type)
      || (realtimeEvent?.type === "round_updated" && realtimeEvent.payload?.action === "extra_grid_assigned")
      || ["event_snapshot", "event_state_changed"].includes(realtimeEvent?.type)) void load();
  }, [load, realtimeEvent]);
  const assign = async () => {
    setWorking(true); setError("");
    try { const next = await autoAssignExtraGrid(); setData(next); setResult(next); }
    catch (cause) { setError(cause.message); }
    finally { setWorking(false); }
  };
  if (!data) return error ? <p role="alert">{error}</p> : null;
  return <section className="external-problems-panel extra-grid">
    <header><div><h3>Post-R1 Extra / Grid</h3><p>{data.unassigned_teams.length} unassigned teams · capacity {data.capacity_per_problem} per problem</p></div>
      <button className="primary-button" disabled={working || !data.can_auto_assign || !data.unassigned_teams.length} onClick={() => void assign()}>{working ? "Assigning…" : "Auto assign remaining teams"}</button>
    </header>
    {!data.can_auto_assign && <p>End Round 1 to enable automatic assignment.</p>}
    {error && <p role="alert">{error}</p>}
    <div className="external-problems-list">{data.problems.map(problem => <article key={problem.id}><div><strong>#{problem.problem_number} {problem.title}</strong><span>{problem.source_label}</span></div><span>{problem.assigned_team_count}/{problem.capacity} used · {problem.capacity_remaining} remaining</span></article>)}</div>
    <p>Unassigned: {data.unassigned_teams.map(team => team.team_name).join(", ") || "None"}</p>
    <p>Automatic assignments: {data.teams.filter(team => team.extra_assignment).map(team => `${team.team_name} → #${team.current_problem.problem_number}`).join(", ") || "None"}</p>
    {result?.failures.length > 0 && <ul role="alert">{result.failures.map(row => <li key={row.team_id}>{row.team_name}: {row.reason}</li>)}</ul>}
  </section>;
}
