import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getProblemResults } from "./services/api";

const PLACEMENTS = {
  FIRST: { label: "1st Place", icon: "🥇" },
  SECOND: { label: "2nd Place", icon: "🥈" },
  THIRD: { label: "3rd Place", icon: "🥉" },
  NOT_PLACED: { label: "Not Placed", icon: "" },
  PENDING: { label: "Pending", icon: "" },
};

const coins = value => value == null ? "Not recorded" : `${Number(value).toLocaleString()} coins`;
const problemText = problem => problem ? `${problem.problem_number} ${problem.problem_title}` : "";

function PlacementBadge({ value }) {
  const placement = PLACEMENTS[value] || PLACEMENTS.PENDING;
  return <span className={`placement-badge placement-badge--${value?.toLowerCase() || "pending"}`}>
    {placement.icon && <span aria-hidden="true">{placement.icon}</span>}{placement.label}
  </span>;
}

function ProblemSummary({ problem, empty }) {
  if (!problem) return <span className="problem-summary problem-summary--empty">{empty}</span>;
  return <span className="problem-summary"><strong>{problem.problem_number}</strong><small>{problem.problem_title}</small></span>;
}

function HistoryCard({ type, problem, bid, placement, selected = true }) {
  const wildcard = type === "Wildcard";
  return <article className={`competition-history-card ${wildcard ? "competition-history-card--wildcard" : ""}`}>
    <header><span>{type}</span>{!selected && <strong>Not selected</strong>}</header>
    {selected ? <dl>
      <div><dt>Problem Statement</dt><dd><strong>{problem?.problem_number || "Not assigned"}</strong>{problem?.problem_title && <span>{problem.problem_title}</span>}</dd></div>
      <div><dt>{wildcard ? "Wildcard Bid" : "Winning Bid"}</dt><dd><strong>{coins(bid)}</strong></dd></div>
      <div><dt>Final Place</dt><dd><PlacementBadge value={placement} /></dd></div>
    </dl> : <p>This team did not select or receive a Wildcard problem.</p>}
  </article>;
}

export default function ProblemResultsPage({ refreshRevision = 0 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState(null);
  const [query, setQuery] = useState("");
  const [historyFilter, setHistoryFilter] = useState("all");
  const [placementFilter, setPlacementFilter] = useState("all");
  const [selectedTeam, setSelectedTeam] = useState(null);
  const closeButton = useRef(null);
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
  useEffect(() => {
    if (!selectedTeam) return undefined;
    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = event => { if (event.key === "Escape") setSelectedTeam(null); };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", handleKeyDown);
    closeButton.current?.focus();
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener("keydown", handleKeyDown); };
  }, [selectedTeam]);

  const shown = useMemo(() => (data?.teams || []).filter(team => {
    const searchable = [team.team_name, problemText(team.round1), problemText(team.wildcard)].join(" ").toLowerCase();
    const hasWildcard = Boolean(team.wildcard?.selected);
    const historyMatch = historyFilter === "all"
      || (historyFilter === "round1" && !hasWildcard)
      || (historyFilter === "wildcard" && hasWildcard)
      || (historyFilter === "final-round1" && team.final_choice === "ROUND1")
      || (historyFilter === "final-wildcard" && team.final_choice === "WILDCARD");
    const placementMatch = placementFilter === "all"
      || (placementFilter === "top3" && ["FIRST", "SECOND", "THIRD"].includes(team.final_placement))
      || team.final_placement === placementFilter;
    return searchable.includes(query.trim().toLowerCase()) && historyMatch && placementMatch;
  }), [data, historyFilter, placementFilter, query]);

  if (loading && !data) return <p className="lab-panel-state">Loading problem results…</p>;
  if (!data) return <p className="lab-inline-error" role="alert">{error || "Problem results are unavailable."}</p>;
  return <section className="problem-results" aria-busy={loading}>
    <header className="problem-results__header"><div><h2>Problem Results</h2><p>Round 1, Wildcard and final result details by team.</p></div><div className="problem-results__actions"><span>Last updated {updatedAt?.toLocaleTimeString() || "Not yet"}</span><button type="button" className="secondary-button" disabled={loading} onClick={() => void load()}>Refresh</button></div></header>
    {error && <p className="lab-inline-error" role="alert">{error}</p>}
    <dl className="lab-allocation-summary problem-results__summary"><div><dt>Total Teams</dt><dd>{data.summary.total_teams}</dd></div><div><dt>Round 1 Assigned</dt><dd>{data.summary.round1_assigned}</dd></div><div><dt>Wildcard Selected</dt><dd>{data.summary.wildcard_selected}</dd></div><div><dt>Top 3 Finalized</dt><dd>{data.summary.top3_finalized}</dd></div></dl>
    <div className="lab-filters problem-results__filters">
      <label>Search teams or problems<input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Team, number or title" /></label>
      <label>History<select value={historyFilter} onChange={event => setHistoryFilter(event.target.value)}><option value="all">All Teams</option><option value="round1">Round 1 Only</option><option value="wildcard">Used Wildcard</option><option value="final-round1">Final Problem = Round 1</option><option value="final-wildcard">Final Problem = Wildcard</option></select></label>
      <label>Placement<select value={placementFilter} onChange={event => setPlacementFilter(event.target.value)}><option value="all">All Placements</option><option value="top3">Top 3</option><option value="NOT_PLACED">Not Placed</option><option value="PENDING">Pending</option></select></label>
    </div>
    <div className="problem-team-table-wrap"><table className="problem-team-table"><thead><tr><th>Team</th><th>Round 1 Problem</th><th>Wildcard Problem</th><th>Final Problem</th><th>Final Place</th><th>Action</th></tr></thead><tbody>{shown.map(team => <tr className="problem-team-row" key={team.team_id}>
      <td data-label="Team"><strong>{team.team_name}</strong><small>Team #{team.team_id}</small></td>
      <td data-label="Round 1 Problem"><ProblemSummary problem={team.round1} empty="Not assigned" /></td>
      <td data-label="Wildcard Problem"><ProblemSummary problem={team.wildcard?.selected ? team.wildcard : null} empty="Not selected" /></td>
      <td data-label="Final Problem"><ProblemSummary problem={team.final_problem} empty="Not assigned" /></td>
      <td data-label="Final Place"><PlacementBadge value={team.final_placement} /></td>
      <td data-label="Action"><button type="button" className="secondary-button" onClick={() => setSelectedTeam(team)}>View Details</button></td>
    </tr>)}</tbody></table>{!shown.length && <p className="lab-empty-row">No teams match these filters.</p>}</div>
    {selectedTeam && <div className="problem-results-modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setSelectedTeam(null); }}>
      <section className="problem-results-modal" role="dialog" aria-modal="true" aria-labelledby={`team-results-${selectedTeam.team_id}`}>
        <header><div><span>Competition history</span><h2 id={`team-results-${selectedTeam.team_id}`}>{selectedTeam.team_name}</h2></div><button ref={closeButton} type="button" className="problem-results-modal__x" aria-label="Close details" onClick={() => setSelectedTeam(null)}>×</button></header>
        <div className="competition-history-grid">
          <HistoryCard type="Round 1" problem={selectedTeam.round1} bid={selectedTeam.round1?.winning_bid} placement={selectedTeam.final_placement} selected={Boolean(selectedTeam.round1)} />
          <HistoryCard type="Wildcard" problem={selectedTeam.wildcard} bid={selectedTeam.wildcard?.winning_bid} placement={selectedTeam.final_placement} selected={Boolean(selectedTeam.wildcard?.selected)} />
        </div>
        <footer><button type="button" className="secondary-button" onClick={() => setSelectedTeam(null)}>Close</button></footer>
      </section>
    </div>}
  </section>;
}
