import http from 'k6/http';
import ws from 'k6/ws';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter, Rate, Trend } from 'k6/metrics';

const API_BASE = (__ENV.API_BASE || 'https://bidtobuild.dev/api').replace(/\/+$/, '');
const WS_URL = __ENV.WS_URL || 'wss://bidtobuild.dev/ws/auction';
const USER_COUNT = Number(__ENV.USERS || 100);
const LOGIN_SPREAD_SECONDS = Number(__ENV.LOGIN_SPREAD_SECONDS ?? 5);
const HOLD_SECONDS = Number(__ENV.HOLD_SECONDS ?? 300); // 5 minutes
const HEARTBEAT_SECONDS = Number(__ENV.HEARTBEAT_SECONDS ?? 20);
const LOGOUT_AFTER_TEST = (__ENV.LOGOUT_AFTER_TEST ?? '1') !== '0';

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
    throw new Error(`CSV has ${mapped.length} rows but USERS=${USER_COUNT}.`);
  }

  return mapped.slice(0, USER_COUNT);
});

const loginSuccess = new Rate('participant_login_success');
const sessionSuccess = new Rate('participant_session_validation_success');
const wsHandshakeSuccess = new Rate('participant_ws_handshake_success');
const wsSnapshotSuccess = new Rate('participant_ws_snapshot_success');
const wsCleanClose = new Rate('participant_ws_clean_close');

const loginDuration = new Trend('participant_login_duration', true);
const wsLifetime = new Trend('participant_ws_lifetime', true);

const heartbeatsSent = new Counter('participant_ws_heartbeats_sent');
const heartbeatAcks = new Counter('participant_ws_heartbeat_acks');
const wsUnexpectedCloses = new Counter('participant_ws_unexpected_closes');
const wsErrors = new Counter('participant_ws_errors');
const login409 = new Counter('participant_login_409');
const login5xx = new Counter('participant_login_5xx');

export const options = {
  scenarios: {
    websocket_hold: {
      executor: 'per-vu-iterations',
      vus: USER_COUNT,
      iterations: 1,
      maxDuration: `${Math.max(120, HOLD_SECONDS + LOGIN_SPREAD_SECONDS + 60)}s`,
      gracefulStop: '30s',
    },
  },

  thresholds: {
    participant_login_success: ['rate==1'],
    participant_session_validation_success: ['rate==1'],
    participant_ws_handshake_success: ['rate==1'],
    participant_ws_snapshot_success: ['rate==1'],
    participant_ws_clean_close: ['rate==1'],
    participant_login_duration: ['p(95)<2500'],
    participant_ws_unexpected_closes: ['count==0'],
    participant_ws_errors: ['count==0'],
    'http_req_failed{endpoint:login}': ['rate<0.01'],
  },
};

export default function () {
  const user = participants[__VU - 1];

  // Spread logins slightly so Step 2 focuses on persistent WebSocket load
  // rather than repeating the Step 1 login burst test.
  if (LOGIN_SPREAD_SECONDS > 0 && USER_COUNT > 1) {
    sleep(((__VU - 1) / (USER_COUNT - 1)) * LOGIN_SPREAD_SECONDS);
  }

  const loginStarted = Date.now();
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
  loginDuration.add(Date.now() - loginStarted);

  if (loginResponse.status === 409) login409.add(1);
  if (loginResponse.status >= 500) login5xx.add(1);

  let token = null;
  try {
    token = loginResponse.json('access_token');
  } catch (_) {
    token = null;
  }

  const loginOk = check(loginResponse, {
    'login returned 200': (r) => r.status === 200,
    'login returned token': () => typeof token === 'string' && token.length > 0,
  });
  loginSuccess.add(loginOk);

  if (!loginOk || !token) {
    console.error(`[LOGIN FAILED] team="${user.teamName}" status=${loginResponse.status}`);
    return;
  }

  // Match the real frontend: validate the issued participant session.
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

  let snapshotReceived = false;
  let expectedClose = false;
  let closeSeen = false;
  let openSeen = false;
  const wsStarted = Date.now();

  const response = ws.connect(
    `${WS_URL}?token=${encodeURIComponent(token)}`,
    {
      tags: { endpoint: 'participant_ws', team: user.teamName },
    },
    function (socket) {
      socket.on('open', function () {
        openSeen = true;

        // The real participant client sends a heartbeat every 20 seconds.
        socket.setInterval(function () {
          heartbeatsSent.add(1);
          socket.send(JSON.stringify({
            type: 'heartbeat',
            client_time: Date.now(),
          }));
        }, HEARTBEAT_SECONDS * 1000);

        // Keep this participant connected for the configured soak duration.
        socket.setTimeout(function () {
          expectedClose = true;
          socket.close();
        }, HOLD_SECONDS * 1000);
      });

      socket.on('message', function (message) {
        try {
          const event = JSON.parse(message);

          if (event.type === 'event_snapshot') {
            snapshotReceived = true;
          } else if (event.type === 'session_heartbeat') {
            heartbeatAcks.add(1);
          }
        } catch (_) {
          // Ignore non-JSON frames; the current application protocol uses JSON.
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

  wsLifetime.add(Date.now() - wsStarted);

  const handshakeOk = check(response, {
    'websocket upgraded with 101': (r) => r && r.status === 101,
  });
  wsHandshakeSuccess.add(handshakeOk && openSeen);

  const snapshotOk = check(null, {
    'received initial event_snapshot': () => snapshotReceived,
  });
  wsSnapshotSuccess.add(snapshotOk);

  const cleanCloseOk = check(null, {
    'websocket remained connected until planned close': () =>
      handshakeOk && openSeen && snapshotReceived && expectedClose && closeSeen,
  });
  wsCleanClose.add(cleanCloseOk);

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
