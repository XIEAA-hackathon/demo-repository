import http from 'k6/http';
import ws from 'k6/ws';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter, Rate, Trend } from 'k6/metrics';

const API_BASE = (__ENV.API_BASE || 'https://bidtobuild.dev/api').replace(/\/+$/, '');
const WS_URL = __ENV.WS_URL || 'wss://bidtobuild.dev/ws/auction';

const USER_COUNT = Number(__ENV.USERS || 100);
const BIDDERS = Math.min(Number(__ENV.BIDDERS || 50), USER_COUNT);
const BIDS_PER_BIDDER = Number(__ENV.BIDS_PER_BIDDER || 8);

const LOGIN_SPREAD_SECONDS = Number(__ENV.LOGIN_SPREAD_SECONDS ?? 5);
const BID_INTERVAL_MS = Number(__ENV.BID_INTERVAL_MS ?? 5500); // 5s cooldown + 0.5s safety margin
const BID_BURST_WINDOW_MS = Number(__ENV.BID_BURST_WINDOW_MS ?? 1000);
const BID_INCREMENT = Number(__ENV.BID_INCREMENT ?? 1);

const WAIT_FOR_BIDDING_SECONDS = Number(__ENV.WAIT_FOR_BIDDING_SECONDS ?? 120);
const HOLD_AFTER_BIDDING_SECONDS = Number(__ENV.HOLD_AFTER_BIDDING_SECONDS ?? 55);
const HEARTBEAT_SECONDS = Number(__ENV.HEARTBEAT_SECONDS ?? 20);
const LOGOUT_AFTER_TEST = (__ENV.LOGOUT_AFTER_TEST ?? '1') !== '0';

if (BID_INTERVAL_MS < 5000) {
  throw new Error('BID_INTERVAL_MS must be >= 5000 because the server cooldown is 5 seconds.');
}
if (BID_INCREMENT < 1 || BID_INCREMENT > 25) {
  throw new Error('BID_INCREMENT must be between 1 and 25.');
}
if (BIDS_PER_BIDDER < 1) {
  throw new Error('BIDS_PER_BIDDER must be >= 1.');
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

  if (rows.length < 2) {
    throw new Error('CSV must contain a header and participant rows.');
  }

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
const wsHandshakeSuccess = new Rate('participant_ws_handshake_success');
const wsSnapshotSuccess = new Rate('participant_ws_snapshot_success');
const wsCleanClose = new Rate('participant_ws_clean_close');
const round1BiddingSeen = new Rate('round1_bidding_seen');

const bidAttempted = new Counter('round1_repeat_bid_attempted');
const bid200 = new Counter('round1_repeat_bid_200');
const bid400 = new Counter('round1_repeat_bid_400');
const bid401 = new Counter('round1_repeat_bid_401');
const bid409 = new Counter('round1_repeat_bid_409');
const bid429 = new Counter('round1_repeat_bid_429');
const bid503 = new Counter('round1_repeat_bid_503');
const bid5xx = new Counter('round1_repeat_bid_5xx');

const bidSuccess = new Rate('round1_repeat_bid_success');
const bidDuration = new Trend('round1_repeat_bid_duration', true);
const bidAuctionLockWait = new Trend('round1_repeat_bid_auction_lock_wait', true);
const bidDbTransaction = new Trend('round1_repeat_bid_db_transaction', true);

const bidUpdatedReceived = new Counter('round1_bid_updated_received');
const heartbeatsSent = new Counter('participant_ws_heartbeats_sent');
const heartbeatAcks = new Counter('participant_ws_heartbeat_acks');
const wsUnexpectedCloses = new Counter('participant_ws_unexpected_closes');
const wsErrors = new Counter('participant_ws_errors');

function addServerTimingMetrics(response) {
  const raw = response.headers['Server-Timing'] || response.headers['server-timing'];
  if (!raw) return;

  const lock = /auction-lock;dur=([\d.]+)/i.exec(raw);
  const txn = /db-transaction;dur=([\d.]+)/i.exec(raw);

  if (lock) bidAuctionLockWait.add(Number(lock[1]));
  if (txn) bidDbTransaction.add(Number(txn[1]));
}

export const options = {
  scenarios: {
    repeated_round1_bidding: {
      executor: 'per-vu-iterations',
      vus: USER_COUNT,
      iterations: 1,
      maxDuration: `${WAIT_FOR_BIDDING_SECONDS + HOLD_AFTER_BIDDING_SECONDS + LOGIN_SPREAD_SECONDS + 60}s`,
      gracefulStop: '30s',
    },
  },

  thresholds: {
    participant_login_success: ['rate==1'],
    participant_session_validation_success: ['rate==1'],
    participant_ws_handshake_success: ['rate==1'],
    participant_ws_snapshot_success: ['rate==1'],
    participant_ws_clean_close: ['rate==1'],
    participant_ws_unexpected_closes: ['count==0'],
    participant_ws_errors: ['count==0'],

    round1_repeat_bid_success: ['rate>=0.98'],
    round1_repeat_bid_duration: ['p(95)<2500'],

    // A healthy run with 5.5s spacing should not hit the 5s per-team cooldown.
    round1_repeat_bid_429: ['count==0'],

    // No server-side failures should occur.
    round1_repeat_bid_5xx: ['count==0'],
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

  const sessionResponse = http.get(`${API_BASE}/participant/session`, {
    headers: { Authorization: `Bearer ${token}` },
    tags: { endpoint: 'participant_session', team: user.teamName },
    timeout: '15s',
  });

  const sessionOk = check(sessionResponse, {
    'participant session returned 200': (r) => r.status === 200,
    'participant role is leader/member': (r) => {
      if (r.status !== 200) return false;
      try {
        const role = r.json('role');
        return role === 'leader' || role === 'member';
      } catch (_) {
        return false;
      }
    },
  });
  sessionSuccess.add(sessionOk);

  if (!sessionOk) {
    console.error(`[SESSION FAILED] team="${user.teamName}" status=${sessionResponse.status}`);
    return;
  }

  // -------------------- Realtime + repeated bidding

  let openSeen = false;
  let snapshotReceived = false;
  let biddingSeen = false;
  let bidSequenceScheduled = false;
  let bidsCompletedByThisVu = 0;
  let expectedClose = false;
  let closeSeen = false;
  let closeScheduled = false;

  function placeOneBid(problemId) {
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
        tags: {
          endpoint: 'round1_repeat_bid',
          team: user.teamName,
        },
        timeout: '15s',
      },
    );

    bidDuration.add(Date.now() - startedAt);
    addServerTimingMetrics(response);

    if (response.status === 200) bid200.add(1);
    if (response.status === 400) bid400.add(1);
    if (response.status === 401) bid401.add(1);
    if (response.status === 409) bid409.add(1);
    if (response.status === 429) bid429.add(1);
    if (response.status === 503) bid503.add(1);
    if (response.status >= 500) bid5xx.add(1);

    const ok = check(response, {
      'repeated Round 1 bid returned 200': (r) => r.status === 200,
    });

    bidSuccess.add(ok);

    if (!ok) {
      let detail = '';
      try {
        detail = response.json('detail') || response.body || '';
      } catch (_) {
        detail = response.body || '';
      }

      console.error(
        `[REPEAT BID FAILED] vu=${__VU} team="${user.teamName}" bid=${bidsCompletedByThisVu + 1}/${BIDS_PER_BIDDER} status=${response.status} detail="${detail}"`,
      );
    }

    bidsCompletedByThisVu += 1;
  }

  function runBidSequence(socket, problemId) {
    if (!shouldBid || bidsCompletedByThisVu >= BIDS_PER_BIDDER) return;

    placeOneBid(problemId);

    if (bidsCompletedByThisVu < BIDS_PER_BIDDER) {
      socket.setTimeout(function () {
        runBidSequence(socket, problemId);
      }, BID_INTERVAL_MS);
    }
  }

  function handleAuthoritativeState(socket, payload) {
    if (!payload || payload.event_state !== 'ROUND1_BIDDING') return;

    const round1 = payload.rounds && payload.rounds.ROUND1;
    const problemId = round1 && round1.current_problem_id;

    if (!problemId) {
      console.error(
        `[BIDDING STATE WITHOUT CURRENT PROBLEM] vu=${__VU} team="${user.teamName}"`,
      );
      return;
    }

    if (!biddingSeen) {
      biddingSeen = true;
      round1BiddingSeen.add(true);

      // Keep every participant connected for the same sustained bidding window,
      // including the 50 non-bidders, so every bid is broadcast to 100 clients.
      if (!closeScheduled) {
        closeScheduled = true;
        socket.setTimeout(function () {
          expectedClose = true;
          try {
            socket.close();
          } catch (_) {}
        }, HOLD_AFTER_BIDDING_SECONDS * 1000);
      }
    }

    if (!shouldBid || bidSequenceScheduled) return;
    bidSequenceScheduled = true;

    let initialDelayMs = 0;
    if (BIDDERS > 1 && BID_BURST_WINDOW_MS > 0) {
      initialDelayMs = Math.floor(((__VU - 1) / (BIDDERS - 1)) * BID_BURST_WINDOW_MS);
    }

    if (initialDelayMs <= 0) {
      runBidSequence(socket, problemId);
    } else {
      socket.setTimeout(function () {
        runBidSequence(socket, problemId);
      }, initialDelayMs);
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

        // Safety close if Admin never opens Round 1 bidding.
        socket.setTimeout(function () {
          if (!closeScheduled) {
            expectedClose = true;
            try {
              socket.close();
            } catch (_) {}
          }
        }, (WAIT_FOR_BIDDING_SECONDS + 5) * 1000);
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

  if (!biddingSeen) {
    round1BiddingSeen.add(false);
    console.error(
      `[NO ROUND1_BIDDING SEEN] team="${user.teamName}" - start in Preview, then click Start Bidding in Admin.`,
    );
  }

  if (shouldBid) {
    check(null, {
      'bidder completed configured bid sequence': () =>
        bidsCompletedByThisVu === BIDS_PER_BIDDER,
    });
  }

  const cleanCloseOk = check(null, {
    'websocket stayed connected until planned close': () =>
      handshakeOk && openSeen && snapshotReceived && expectedClose && closeSeen,
  });
  wsCleanClose.add(cleanCloseOk);

  // -------------------- Cleanup

  if (LOGOUT_AFTER_TEST) {
    const logoutResponse = http.post(`${API_BASE}/logout`, null, {
      headers: { Authorization: `Bearer ${token}` },
      tags: { endpoint: 'logout', team: user.teamName },
      timeout: '15s',
    });

    check(logoutResponse, {
      'logout returned 200': (r) => r.status === 200,
    });
  }
}
