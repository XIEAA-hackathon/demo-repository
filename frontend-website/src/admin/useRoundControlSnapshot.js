import { useCallback, useRef, useState } from "react";
import { getRoundControl } from "./services/api";

// Match Lab Admin: serialize reads, reject snapshots invalidated by a lifecycle
// change, and reconcile once after the old request releases the in-flight slot.
export function useRoundControlSnapshot(round, onError) {
  const [data, setData] = useState(null);
  const revision = useRef(0);
  const inFlight = useRef(null);
  const load = useCallback(() => {
    if (inFlight.current) return inFlight.current;
    const startedRevision = revision.current;
    const request = getRoundControl(round).then(result => {
      if (revision.current !== startedRevision) return true; // Stale success is not a network failure/retry.
      if (result.selection) result.selection = { ...result.selection, received_at: Date.now() };
      setData(current => result.status === "BIDDING" && current?.status === "BIDDING"
        && current.current_problem?.id === result.current_problem?.id && current.highest_bid > (result.highest_bid || 0)
        ? { ...result, highest_bid: current.highest_bid, highest_team: current.highest_team } : result);
      onError("");
      return true;
    }).catch(cause => {
      if (revision.current === startedRevision) onError(cause.message || "Round controls could not be loaded.");
      return false;
    });
    inFlight.current = request;
    void request.finally(() => {
      if (inFlight.current === request) inFlight.current = null;
      if (revision.current !== startedRevision) void load();
    });
    return request;
  }, [round, onError]);
  const invalidate = useCallback(() => { revision.current += 1; }, []);
  const commit = useCallback(result => {
    revision.current += 1;
    if (result?.round_type) {
      setData(result.selection ? { ...result, selection: { ...result.selection, received_at: Date.now() } } : result);
    }
  }, []);
  return { data, setData, load, invalidate, commit };
}
