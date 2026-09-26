import http from 'k6/http';
import ws from 'k6/ws';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter, Rate, Trend } from 'k6/metrics';

const API_BASE = (__ENV.API_BASE || 'https://bidtobuild.dev/api').replace(/\/+$/, '');
const WS_URL = __ENV.WS_URL || 'wss://bidtobuild.dev/ws/auction';

const USER_COUNT = Number(__ENV.USERS || 100);
const BIDDERS = Math.min(Number(__ENV.BIDDERS || 50), USER_COUNT);
const BID_WINDOW_MS = Number(__ENV.BID_WINDOW_MS ?? 1000);
const BID_INCREMENT = Number(__ENV.BID_INCREMENT ?? 1);
const LOGIN_SPREAD_SECONDS = Number(__ENV.LOGIN_SPREAD_SECONDS ?? 5);
const HEARTBEAT_SECONDS = Number(__ENV.HEARTBEAT_SECONDS ?? 20);

const WAIT_FOR_BIDDING_SECONDS = Number(__ENV.WAIT_FOR_BIDDING_SECONDS ?? 120);
const WAIT_FOR_FINALIZATION_SECONDS = Number(__ENV.WAIT_FOR_FINALIZATION_SECONDS ?? 180);
const POST_FINALIZE_HOLD_SECONDS = Number(__ENV.POST_FINALIZE_HOLD_SECONDS ?? 5);
const EXPECTED_WINNERS = Number(__ENV.EXPECTED_WINNERS ?? 5);
const LOGOUT_AFTER_TEST = (__ENV.LOGOUT_AFTER_TEST ?? '1') !== '0';

if (BID_INCREMENT < 1 || BID_INCREMENT > 25) {
  throw new Error('BID_INCREMENT must be between 1 and 25.');
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let quoted = false;

  text = text.replace(/^\uFEFF/, '');

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];

    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        field += ch;
      }
      continue;
    }

    if (ch === '"') quoted = true;
    else if (ch === ',') {
      row.push(field);
      field = '';
    } else if (ch === '\n') {
      row.push(field.replace(/\r$/, ''));
      rows.push(row);
      row = [];
      field = '';
    } else {
      field += ch;
    }
  }

  if (field.length || row.length) {
    row.push(field.replace(/\r$/, ''));
    rows.push(row);
  }

  if (rows.length < 2) throw new Error('CSV must contain a header and participant rows.');

  const headers = rows[0].map((value) => value.trim());

  return rows
    .slice(1)
    .filter((values) => values.some((value) => value.trim() !== ''))
    .map((values) => {
      const item = {};
      headers.forEach((header, index) => {
        item[header] = (values[index] ?? '').trim();
      });
      return item;
    });
}

const participants = new SharedArray('participants', () => {
  const rows = parseCsv(open('./bidtobuild_100_participants.csv'));

  const mapped = rows.map((row, index) => {
    const login = row['Leader Login Email'];
    const password = row['Leader Password'];
    const teamName = row['Team Name'];

    if (!login || !password || !teamName) {
      throw new Error(
        `CSV row ${index + 2} is missing Team Name, Leader Login Email, or Leader Password.`,
      );
    }

    return { teamName, login, password };
  });

  if (mapped.length < USER_COUNT) {
    throw new Error(`CSV has ${mapped.length} participants but USERS=${USER_COUNT}.`);
  }

  return mapped.slice(0, USER_COUNT);
});

// -------------------- Metrics

const loginSuccess = new Rate('participant_login_success');
const sessionSuccess = new Rate('participant_session_validation_success');
const cleanPrecondition = new Rate('round1_clean_precondition');
const wsHandshakeSuccess = new Rate('participant_ws_handshake_success');
const wsSnapshotSuccess = new Rate('participant_ws_snapshot_success');
const wsCleanClose = new Rate('participant_ws_clean_close');

const biddingSeen = new Rate('round1_bidding_seen');
const bidAttempted = new Counter('round1_finalize_test_bid_attempted');
const bid200 = new Counter('round1_finalize_test_bid_200');
const bidSuccess = new Rate('round1_finalize_test_bid_success');
const bidDuration = new Trend('round1_finalize_test_bid_duration', true);

const bidUpdatedReceived = new Counter('round1_bid_updated_received');

const finalizationEventReceived = new Rate('round1_winners_assigned_event_received');
const finalizationWinnerCountValid = new Rate('round1_winners_assigned_count_valid');
const round1ResultAfterFinalize = new Rate('round1_result_after_close_seen');

const winnerDetected = new Counter('round1_winner_participants_detected');
const loserDetected = new Counter('round1_nonwinner_participants_detected');
const walletValidationSuccess = new Rate('round1_wallet_validation_success');
const assignmentValidationSuccess = new Rate('round1_assignment_validation_success');
const postFinalizeDashboardSuccess = new Rate('round1_post_finalize_dashboard_success');

const heartbeatsSent = new Counter('participant_ws_heartbeats_sent');
const heartbeatAcks = new Counter('participant_ws_heartbeat_acks');
const wsUnexpectedCloses = new Counter('participant_ws_unexpected_closes');
const wsErrors = new Counter('participant_ws_errors');

export const options = {
  scenarios: {
    round1_finalize: {
      executor: 'per-vu-iterations',
      vus: USER_COUNT,
      iterations: 1,
      maxDuration: `${WAIT_FOR_BIDDING_SECONDS + WAIT_FOR_FINALIZATION_SECONDS + LOGIN_SPREAD_SECONDS + 90}s`,
      gracefulStop: '30s',
    },
  },

  thresholds: {
    participant_login_success: ['rate==1'],
    participant_session_validation_success: ['rate==1'],
    round1_clean_precondition: ['rate==1'],

    participant_ws_handshake_success: ['rate==1'],
    participant_ws_snapshot_success: ['rate==1'],
    participant_ws_clean_close: ['rate==1'],
    participant_ws_unexpected_closes: ['count==0'],
    participant_ws_errors: ['count==0'],

    round1_finalize_test_bid_success: ['rate==1'],
    round1_finalize_test_bid_duration: ['p(95)<2500'],

    round1_winners_assigned_event_received: ['rate==1'],
    round1_winners_assigned_count_valid: ['rate==1'],
    round1_result_after_close_seen: ['rate==1'],

    round1_post_finalize_dashboard_success: ['rate==1'],
    round1_wallet_validation_success: ['rate==1'],
    round1_assignment_validation_success: ['rate==1'],

    round1_winner_participants_detected: [`count==${EXPECTED_WINNERS}`],
    round1_nonwinner_participants_detected: [`count==${USER_COUNT - EXPECTED_WINNERS}`],
  },
};

export default function () {
  const user = participants[__VU - 1];
  const shouldBid = __VU <= BIDDERS;

  if (LOGIN_SPREAD_SECONDS > 0 && USER_COUNT > 1) {
    sleep(((__VU - 1) / (USER_COUNT - 1)) * LOGIN_SPREAD_SECONDS);
  }

  // -------------------- Login

  const loginResponse = http.post(
    `${API_BASE}/login`,
    {
      username: user.login,
      password: user.password,
    },
    {
      tags: { endpoint: 'login', team: user.teamName },
      timeout: '15s',
    },
  );

  let token = null;
  try {
    token = loginResponse.json('access_token');
  } catch (_) {
    token = null;
  }

  const loginOk = check(loginResponse, {
    'login returned 200': (r) => r.status === 200,
    'login returned access token': () => typeof token === 'string' && token.length > 0,
  });
  loginSuccess.add(loginOk);

  if (!loginOk || !token) {
    console.error(`[LOGIN FAILED] team="${user.teamName}" status=${loginResponse.status}`);
    return;
  }

  const authHeaders = { Authorization: `Bearer ${token}` };

  const sessionResponse = http.get(`${API_BASE}/participant/session`, {
    headers: authHeaders,
    tags: { endpoint: 'participant_session', team: user.teamName },
    timeout: '15s',
  });

  const sessionOk = check(sessionResponse, {
    'participant session returned 200': (r) => r.status === 200,
  });
  sessionSuccess.add(sessionOk);

  if (!sessionOk) {
    console.error(`[SESSION FAILED] team="${user.teamName}" status=${sessionResponse.status}`);
    return;
  }

  // -------------------- Baseline dashboard
  // This lets Step 5 prove exactly-once wallet deduction after finalization.

  const baselineResponse = http.get(`${API_BASE}/participant/dashboard`, {
    headers: authHeaders,
    tags: { endpoint: 'dashboard_before_finalize', team: user.teamName },
    timeout: '15s',
  });

  let baseline = null;
  try {
    baseline = baselineResponse.json();
  } catch (_) {
    baseline = null;
  }

  const preconditionOk = check(baselineResponse, {
    'baseline dashboard returned 200': (r) => r.status === 200,
    'test starts in ROUND1_PREVIEW': () => baseline?.eventState === 'ROUND1_PREVIEW',
    'team has no previous Round 1 assignment': () =>
      baseline?.round1Assigned === false &&
      baseline?.round1AssignmentType == null &&
      baseline?.round1Problem == null,
  });
  cleanPrecondition.add(preconditionOk);

  if (!preconditionOk || !baseline) {
    console.error(
      `[PRECONDITION FAILED] team="${user.teamName}" state=${baseline?.eventState} round1Assigned=${baseline?.round1Assigned}. Reset rehearsal event and start the current problem in Preview before rerunning.`,
    );

    if (LOGOUT_AFTER_TEST) {
      http.post(`${API_BASE}/logout`, null, {
        headers: authHeaders,
        tags: { endpoint: 'logout', team: user.teamName },
      });
    }
    return;
  }

  const teamId = Number(baseline.team.id);
  const startingBalance = Number(baseline.wallet.balance);

  // -------------------- Realtime / bidding / finalization

  let openSeen = false;
  let snapshotReceived = false;
  let sawBidding = false;
  let bidScheduled = false;
  let bidCompleted = false;

  let winnersAssignedReceived = false;
  let winnersAssignedPayload = null;
  let round1ResultSeen = false;

  let expectedClose = false;
  let closeSeen = false;
  let finalCloseScheduled = false;
  let safetyCloseScheduled = false;

  function placeBid(problemId) {
    if (!shouldBid || bidCompleted) return;

    bidAttempted.add(1);

    const startedAt = Date.now();
    const response = http.post(
      `${API_BASE}/bid`,
      JSON.stringify({
        ps_id: Number(problemId),
        increment: BID_INCREMENT,
      }),
      {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        tags: { endpoint: 'round1_finalize_test_bid', team: user.teamName },
        timeout: '15s',
      },
    );

    bidDuration.add(Date.now() - startedAt);

    if (response.status === 200) bid200.add(1);

    const ok = check(response, {
      'finalization-test bid returned 200': (r) => r.status === 200,
    });
    bidSuccess.add(ok);
    bidCompleted = true;

    if (!ok) {
      let detail = '';
      try {
        detail = response.json('detail') || response.body || '';
      } catch (_) {
        detail = response.body || '';
      }
      console.error(
        `[BID FAILED] team="${user.teamName}" status=${response.status} detail="${detail}"`,
      );
    }
  }

  function scheduleFinalClose(socket) {
    if (finalCloseScheduled) return;
    finalCloseScheduled = true;

    socket.setTimeout(function () {
      expectedClose = true;
      try {
        socket.close();
      } catch (_) {}
    }, POST_FINALIZE_HOLD_SECONDS * 1000);
  }

  function handleAuthoritativeState(socket, payload) {
    if (!payload || payload.event_state !== 'ROUND1_BIDDING') {
      if (payload && payload.event_state === 'ROUND1_RESULT') {
        round1ResultSeen = true;
      }
      return;
    }

    const round1 = payload.rounds && payload.rounds.ROUND1;
    const problemId = round1 && round1.current_problem_id;

    if (!problemId) {
      console.error(
        `[BIDDING STATE WITHOUT CURRENT PROBLEM] team="${user.teamName}"`,
      );
      return;
    }

    if (!sawBidding) {
      sawBidding = true;
      biddingSeen.add(true);
    }

    if (!safetyCloseScheduled) {
      safetyCloseScheduled = true;
      socket.setTimeout(function () {
        if (!winnersAssignedReceived) {
          console.error(
            `[WINNER ASSIGNMENT TIMEOUT] team="${user.teamName}" - after bidding, use Admin: Close bidding -> Assign winner(s).`,
          );
          expectedClose = true;
          try {
            socket.close();
          } catch (_) {}
        }
      }, WAIT_FOR_FINALIZATION_SECONDS * 1000);
    }

    if (!shouldBid || bidScheduled) return;
    bidScheduled = true;

    let delayMs = 0;
    if (BIDDERS > 1 && BID_WINDOW_MS > 0) {
      delayMs = Math.floor(((__VU - 1) / (BIDDERS - 1)) * BID_WINDOW_MS);
    }

    if (delayMs <= 0) {
      placeBid(problemId);
    } else {
      socket.setTimeout(function () {
        placeBid(problemId);
      }, delayMs);
    }
  }

  const wsResponse = ws.connect(
    `${WS_URL}?token=${encodeURIComponent(token)}`,
    {
      tags: { endpoint: 'participant_ws', team: user.teamName },
    },
    function (socket) {
      socket.on('open', function () {
        openSeen = true;

        socket.setInterval(function () {
          heartbeatsSent.add(1);
          socket.send(JSON.stringify({
            type: 'heartbeat',
            client_time: Date.now(),
          }));
        }, HEARTBEAT_SECONDS * 1000);

        // Safety timeout if Admin never moves Preview -> Bidding.
        socket.setTimeout(function () {
          if (!sawBidding) {
            console.error(
              `[BIDDING TIMEOUT] team="${user.teamName}" - click End preview / start bidding in Admin.`,
            );
            expectedClose = true;
            try {
              socket.close();
            } catch (_) {}
          }
        }, WAIT_FOR_BIDDING_SECONDS * 1000);
      });

      socket.on('message', function (message) {
        let event;
        try {
          event = JSON.parse(message);
        } catch (_) {
          return;
        }

        if (event.type === 'event_snapshot') {
          snapshotReceived = true;
          handleAuthoritativeState(socket, event.payload);
          return;
        }

        if (event.type === 'event_state_changed') {
          handleAuthoritativeState(socket, event.payload);
          return;
        }

        if (event.type === 'bid_updated') {
          bidUpdatedReceived.add(1);
          return;
        }

        if (
          event.type === 'round_updated' &&
          event.payload &&
          event.payload.round === 'ROUND1' &&
          event.payload.action === 'winners_assigned'
        ) {
          winnersAssignedReceived = true;
          winnersAssignedPayload = event.payload || {};
          scheduleFinalClose(socket);
          return;
        }

        if (event.type === 'session_heartbeat') {
          heartbeatAcks.add(1);
        }
      });

      socket.on('error', function (error) {
        wsErrors.add(1);
        console.error(`[WS ERROR] team="${user.teamName}" error=${String(error)}`);
      });

      socket.on('close', function (code, reason) {
        closeSeen = true;

        if (!expectedClose) {
          wsUnexpectedCloses.add(1);
          console.error(
            `[UNEXPECTED WS CLOSE] team="${user.teamName}" code=${code} reason="${reason || ''}"`,
          );
        }
      });
    },
  );

  const handshakeOk = check(wsResponse, {
    'websocket upgraded with 101': (r) => r && r.status === 101,
  });
  wsHandshakeSuccess.add(handshakeOk && openSeen);

  const snapshotOk = check(null, {
    'received initial event_snapshot': () => snapshotReceived,
  });
  wsSnapshotSuccess.add(snapshotOk);

  if (!sawBidding) {
    biddingSeen.add(false);
  }

  const finalizationOk = check(null, {
    'received round_updated winners_assigned event': () => winnersAssignedReceived,
  });
  finalizationEventReceived.add(finalizationOk);

  const winners = Array.isArray(winnersAssignedPayload?.winners)
    ? winnersAssignedPayload.winners
    : [];

  const winnerCountOk = check(null, {
    [`winners_assigned payload contains ${EXPECTED_WINNERS} winners`]: () =>
      winners.length === EXPECTED_WINNERS,
  });
  finalizationWinnerCountValid.add(winnerCountOk);

  const resultStateOk = check(null, {
    'saw ROUND1_RESULT after Close bidding': () => round1ResultSeen,
  });
  round1ResultAfterFinalize.add(resultStateOk);

  const cleanCloseOk = check(null, {
    'websocket stayed connected until planned close': () =>
      handshakeOk && openSeen && snapshotReceived && expectedClose && closeSeen,
  });
  wsCleanClose.add(cleanCloseOk);

  // -------------------- Verify authoritative participant state AFTER finalization

  const postResponse = http.get(`${API_BASE}/participant/dashboard`, {
    headers: authHeaders,
    tags: { endpoint: 'dashboard_after_finalize', team: user.teamName },
    timeout: '15s',
  });

  let after = null;
  try {
    after = postResponse.json();
  } catch (_) {
    after = null;
  }

  const postOk = check(postResponse, {
    'post-finalization dashboard returned 200': (r) => r.status === 200,
  });
  postFinalizeDashboardSuccess.add(postOk && after != null);

  if (after) {
    const winner = winners.find((row) => Number(row.team_id) === teamId);
    const isWinner = Boolean(winner);

    if (isWinner) winnerDetected.add(1);
    else loserDetected.add(1);

    const expectedBalance = isWinner
      ? startingBalance - Number(winner.amount)
      : startingBalance;

    const walletOk = check(null, {
      'wallet changed exactly once for winner or stayed unchanged for non-winner': () =>
        Number(after.wallet.balance) === expectedBalance &&
        Number(after.team.coins) === expectedBalance,
    });
    walletValidationSuccess.add(walletOk);

    const assignmentOk = check(null, {
      'Round 1 assignment matches finalization result': () => {
        if (isWinner) {
          return (
            after.round1Assigned === true &&
            after.round1AssignmentType === 'BID_WINNER' &&
            Number(after.round1AssignmentCost) === Number(winner.amount) &&
            after.round1Problem != null &&
            after.finalProblem != null
          );
        }

        return (
          after.round1Assigned === false &&
          after.round1AssignmentType == null &&
          after.round1AssignmentCost == null &&
          after.round1Problem == null
        );
      },
    });
    assignmentValidationSuccess.add(assignmentOk);

    if (!walletOk || !assignmentOk) {
      console.error(
        `[FINALIZATION VERIFY FAILED] team="${user.teamName}" winner=${isWinner} startBalance=${startingBalance} afterBalance=${after.wallet?.balance} assignmentType=${after.round1AssignmentType} assignmentCost=${after.round1AssignmentCost}`,
      );
    }
  } else {
    walletValidationSuccess.add(false);
    assignmentValidationSuccess.add(false);
  }

  // -------------------- Cleanup

  if (LOGOUT_AFTER_TEST) {
    const logoutResponse = http.post(`${API_BASE}/logout`, null, {
      headers: authHeaders,
      tags: { endpoint: 'logout', team: user.teamName },
      timeout: '15s',
    });

    check(logoutResponse, {
      'logout returned 200': (r) => r.status === 200,
    });
  }
}
