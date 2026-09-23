import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getProblemResults } from "./services/api";

const friendly = value => value ? value.toLowerCase().split("_").map(word => word[0].toUpperCase() + word.slice(1)).join(" ") : "—";
const coins = value => value == null ? "—" : `${Number(value).toLocaleString()} coins`;
const shortProblem = problem => problem ? `${problem.number} — ${problem.title}` : "—";
const placement = value => ({ "1st Place": "🥇 1st Place", "2nd Place": "🥈 2nd Place", "3rd Place": "🥉 3rd Place" }[value] || value);

export default function ProblemResultsPage({ refreshRevision = 0 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState(null);
  const [tab, setTab] = useState("all");
  const [status, setStatus] = useState("all");
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(null);
  const alive = useRef(true);
  const currentRevision = useRef(refreshRevision);
  const inFlight = useRef(null);
  const queued = useRef(false);
  const loadRef = useRef(null);
  const controller = useRef(null);

  const load = useCallback(() => {
    if (inFlight.current) { queued.current = true; return inFlight.current; }
    const startedRevision = currentRevision.current;
    controller.current = new AbortController();
    setLoading(true);
    const request = getProblemResults(controller.current.signal)
      .then(next => {
        if (alive.current && currentRevision.current === startedRevision) {
          setData(next); setUpdatedAt(new Date()); setError("");
        }
      })
      .catch(cause => {
        if (alive.current && currentRevision.current === startedRevision) setError(cause.message || "Problem results could not be loaded.");
      })
      .finally(() => {
        inFlight.current = null;
        controller.current = null;
        if (!alive.current) return;
        setLoading(false);
        if (queued.current || currentRevision.current !== startedRevision) {
          queued.current = false;
          queueMicrotask(() => void loadRef.current?.());
        }
      });
    inFlight.current = request;
    return request;
  }, []);
  loadRef.current = load;

  useEffect(() => {
    alive.current = true;
    void load();
    return () => { alive.current = false; controller.current?.abort(); };
  }, [load]);
  useEffect(() => {
    if (refreshRevision === currentRevision.current) return;
    currentRevision.current = refreshRevision;
    void load();
  }, [refreshRevision, load]);

  const shown = useMemo(() => (data?.problems || []).filter(problem => {
    const searchable = [problem.number, problem.title, ...problem.assignments.map(row => row.team_name)].join(" ").toLowerCase();
    const tabMatch = tab === "all" || problem.problem_type === tab;
    const statusMatch = status === "all"
      || (status === "assigned" && problem.assignments.length > 0)
      || (status === "unassigned" && problem.assignments.length === 0)
      || (status === "changed" && problem.assignments.some(row => row.changed_after_wildcard));
    return tabMatch && statusMatch && searchable.includes(query.trim().toLowerCase());
  }), [data, query, status, tab]);

  if (loading && !data) return <p className="lab-panel-state">Loading problem results…</p>;
  if (!data) return <p className="lab-inline-error" role="alert">{error || "Problem results are unavailable."}</p>;
  return <section className="problem-results" aria-busy={loading}>
    <header className="problem-results__header"><div><h2>Problem Results</h2><p>Read-only event history from persisted problem assignments and final results.</p></div><div className="problem-results__actions"><span>Last updated {updatedAt?.toLocaleTimeString() || "—"}</span><button type="button" className="secondary-button" disabled={loading} onClick={() => void load()}>Refresh</button></div></header>
    {error && <p className="lab-inline-error" role="alert">{error}</p>}
    <dl className="lab-allocation-summary problem-results__summary"><div><dt>Total Problems</dt><dd>{data.summary.total_problems}</dd></div><div><dt>Round 1 Problems</dt><dd>{data.summary.round1_problems}</dd></div><div><dt>Wildcard Problems</dt><dd>{data.summary.wildcard_problems}</dd></div><div><dt>Assigned Teams</dt><dd>{data.summary.assigned_teams}</dd></div></dl>
    <div className="problem-results__tabs" role="tablist" aria-label="Problem type">{[["all", "All Problems"], ["ROUND1", "Round 1"], ["WILDCARD", "Wildcard"]].map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={tab === value} onClick={() => setTab(value)}>{label}</button>)}</div>
    <div className="lab-filters problem-results__filters"><label>Search problems or teams<input type="search" value={query} onChange={event => setQuery(event.target.value)} /></label><label>Status<select value={status} onChange={event => setStatus(event.target.value)}><option value="all">All</option><option value="assigned">Assigned</option><option value="unassigned">Unassigned</option><option value="changed">Changed After Wildcard</option></select></label></div>
    <div className="problem-results__list">{shown.map(problem => {
      const open = expanded === problem.id;
      return <article className="problem-result-card" key={problem.id}>
        <header><div><span className={`problem-result-type problem-result-type--${problem.problem_type.toLowerCase()}`}>{problem.problem_type === "ROUND1" ? "Round 1" : "Wildcard"}</span><h3>{problem.number}</h3><p>{problem.title}</p></div><div><strong>{problem.assignments.length} team{problem.assignments.length === 1 ? "" : "s"} assigned</strong><span className={`problem-result-status ${problem.assignments.length ? "assigned" : ""}`}>{problem.status}</span><button type="button" className="secondary-button" aria-expanded={open} onClick={() => setExpanded(open ? null : problem.id)}>{open ? "Hide Details" : "View Details"}</button></div></header>
        {open && <div className="problem-result-details"><dl><div><dt>DB ID</dt><dd>{problem.id}</dd></div><div><dt>PS number</dt><dd>{problem.number}</dd></div><div><dt>Round</dt><dd>{problem.round}</dd></div><div><dt>Problem status</dt><dd>{friendly(problem.problem_status)}</dd></div></dl><p>{problem.description || "No description stored."}</p>
          {problem.assignments.length ? <div className="problem-result-table-wrap"><table><thead><tr><th>Team</th><th>Assignment source</th><th>Winning bid / cost</th><th>Round 1 problem</th><th>Wildcard outcome</th><th>Final problem</th><th>Final choice</th><th>Final placement</th><th>Status</th></tr></thead><tbody>{problem.assignments.map(row => <tr key={`${row.association}-${row.team_id}`}><td><strong>{row.team_name}</strong><small>Team #{row.team_id}{row.leader_name ? ` · ${row.leader_name}` : ""}</small></td><td>{friendly(row.assignment_source)}</td><td>{row.association === "ROUND1" ? <><span>{coins(row.assignment_cost)}</span>{row.round1_bid_amount != null && <small>Stored bid: {coins(row.round1_bid_amount)}</small>}</> : <><span>Winning bid: {coins(row.wildcard_winning_bid)}</span><small>Coins paid: {coins(row.coins_paid)}</small></>}</td><td>{shortProblem(row.round1_problem)}</td><td>{row.wildcard_problem ? <><span>{shortProblem(row.wildcard_problem)}</span><small>Rank {row.wildcard_rank ? `#${row.wildcard_rank}` : "—"} · {friendly(row.selection_method)}</small></> : "—"}</td><td>{shortProblem(row.final_problem)}</td><td>{friendly(row.final_choice)}{row.final_problem_defaulted ? <small>Defaulted</small> : null}{row.final_problem_confirmed_at ? <small>Confirmed {new Date(row.final_problem_confirmed_at).toLocaleString()}</small> : null}</td><td><span className={`placement-badge placement-badge--${row.placement.replace(/\W/g, "").toLowerCase()}`}>{placement(row.placement)}</span></td><td>{row.changed_after_wildcard ? "Changed After Wildcard" : row.final_problem?.id === problem.id ? "Final Problem" : "Historical"}</td></tr>)}</tbody></table></div> : <p className="lab-empty-row">No teams are associated with this problem.</p>}
        </div>}
      </article>;
    })}{!shown.length && <p className="lab-empty-row">No problems match these filters.</p>}</div>
  </section>;
}
