export const TIMER_SNAPSHOT_TOLERANCE_SECONDS = 2;

export function classifyApiStatus(results, healthFailed = false) {
  const successfulRequests = results.filter((result) => result.status === "fulfilled").length;
  if (successfulRequests === results.length && !healthFailed) return "healthy";
  return successfulRequests > 0 ? "degraded" : "offline";
}

export function isSyncStale({ documentHidden, refreshPending, staleSeconds, thresholdSeconds = 15 }) {
  if (documentHidden || refreshPending) return false;
  return staleSeconds == null || staleSeconds > thresholdSeconds;
}

const finiteSeconds = (value) => {
  const seconds = Number(value);
  return Number.isFinite(seconds) ? Math.max(0, seconds) : null;
};

export function deriveServerRemaining(timing, localNow = Date.now()) {
  if (!timing) return 0;
  if (timing.paused) {
    return finiteSeconds(timing.paused_remaining_seconds) ?? finiteSeconds(timing.remaining_seconds) ?? 0;
  }

  const endsAt = Date.parse(timing.ends_at);
  const serverTime = Date.parse(timing.server_time);
  const receivedAt = Number(timing.received_at);
  if (Number.isFinite(endsAt) && Number.isFinite(serverTime) && Number.isFinite(receivedAt)) {
    const serverOffset = serverTime - receivedAt;
    return Math.max(0, Math.ceil((endsAt - (localNow + serverOffset)) / 1000));
  }

  return finiteSeconds(timing.remaining_seconds) ?? 0;
}

export function projectCountdown(anchor, localNow = Date.now()) {
  if (!anchor) return 0;
  if (anchor.paused) return anchor.remaining;
  const elapsedMilliseconds = Math.max(0, localNow - anchor.localAt);
  return Math.max(0, Math.ceil(anchor.remaining - elapsedMilliseconds / 1000));
}

export function shouldApplyTimerSnapshot({
  previousTiming,
  previousTimerKey,
  nextTiming,
  nextTimerKey,
  expectedRemaining,
  serverRemaining,
}) {
  if (!previousTiming) return true;
  if (previousTimerKey !== nextTimerKey) return true;
  if (Boolean(previousTiming.paused) !== Boolean(nextTiming?.paused)) return true;
  if (previousTiming.started_at !== nextTiming?.started_at) return true;
  if (Boolean(previousTiming.ends_at) !== Boolean(nextTiming?.ends_at)) return true;
  return Math.abs(serverRemaining - expectedRemaining) > TIMER_SNAPSHOT_TOLERANCE_SECONDS;
}
