import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter, Rate, Trend } from 'k6/metrics';

const API_BASE = (__ENV.API_BASE || 'https://bidtobuild.dev/api').replace(/\/+$/, '');
const USER_COUNT = Number(__ENV.USERS || 100);
const LOGIN_SPREAD_SECONDS = Number(__ENV.LOGIN_SPREAD_SECONDS ?? 10);
const HOLD_SECONDS = Number(__ENV.HOLD_SECONDS ?? 2);
const LOGOUT_AFTER_TEST = (__ENV.LOGOUT_AFTER_TEST ?? '1') !== '0';

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let quoted = false;

  // Remove UTF-8 BOM if present.
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

    if (ch === '"') {
      quoted = true;
    } else if (ch === ',') {
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
    throw new Error('CSV must contain a header and at least one participant row.');
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

    return {
      teamName,
      login,
      password,
    };
  });

  if (mapped.length < USER_COUNT) {
    throw new Error(
      `CSV has only ${mapped.length} participants, but USERS=${USER_COUNT}.`,
    );
  }

  return mapped.slice(0, USER_COUNT);
});

const loginSuccess = new Rate('participant_login_success');
const sessionValidationSuccess = new Rate('participant_session_validation_success');
const loginDuration = new Trend('participant_login_duration', true);
const sessionValidationDuration = new Trend('participant_session_validation_duration', true);
const duplicateLogin409 = new Counter('participant_login_409');
const login401 = new Counter('participant_login_401');
const login5xx = new Counter('participant_login_5xx');

export const options = {
  scenarios: {
    participant_login: {
      executor: 'per-vu-iterations',
      vus: USER_COUNT,
      iterations: 1,
      maxDuration: '2m',
    },
  },

  thresholds: {
    participant_login_success: ['rate==1'],
    participant_session_validation_success: ['rate==1'],
    participant_login_duration: ['p(95)<2500'],
    participant_session_validation_duration: ['p(95)<1500'],
    'http_req_failed{endpoint:login}': ['rate<0.01'],
    'http_req_duration{endpoint:login}': ['p(95)<2500'],
  },
};

export default function () {
  const user = participants[__VU - 1];

  // Spread 100 users across a short login window by default.
  // For a full burst test, run with LOGIN_SPREAD_SECONDS=0.
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
      tags: {
        endpoint: 'login',
        team: user.teamName,
      },
      timeout: '15s',
    },
  );
  loginDuration.add(Date.now() - loginStarted);

  if (loginResponse.status === 409) duplicateLogin409.add(1);
  if (loginResponse.status === 401) login401.add(1);
  if (loginResponse.status >= 500) login5xx.add(1);

  let token = null;
  try {
    token = loginResponse.json('access_token');
  } catch (_) {
    token = null;
  }

  const loginOk = check(loginResponse, {
    'login returned 200': (response) => response.status === 200,
    'login returned access token': () => typeof token === 'string' && token.length > 0,
  });

  loginSuccess.add(loginOk);

  if (!loginOk || !token) {
    console.error(
      `[LOGIN FAILED] team="${user.teamName}" status=${loginResponse.status}`,
    );
    return;
  }

  // The real React participant login immediately validates the issued token
  // with GET /participant/session, so this reproduces the website login flow.
  const sessionStarted = Date.now();
  const sessionResponse = http.get(`${API_BASE}/participant/session`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    tags: {
      endpoint: 'participant_session',
      team: user.teamName,
    },
    timeout: '15s',
  });
  sessionValidationDuration.add(Date.now() - sessionStarted);

  const sessionOk = check(sessionResponse, {
    'participant session returned 200': (response) => response.status === 200,
    'participant session is leader/member': (response) => {
      if (response.status !== 200) return false;
      try {
        const role = response.json('role');
        return role === 'leader' || role === 'member';
      } catch (_) {
        return false;
      }
    },
  });

  sessionValidationSuccess.add(sessionOk);

  if (!sessionOk) {
    console.error(
      `[SESSION VALIDATION FAILED] team="${user.teamName}" status=${sessionResponse.status}`,
    );
  }

  if (HOLD_SECONDS > 0) {
    sleep(HOLD_SECONDS);
  }

  // Default cleanup makes the script safely repeatable with the app's
  // strict single-active-session participant policy.
  if (LOGOUT_AFTER_TEST) {
    http.post(`${API_BASE}/logout`, null, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
      tags: {
        endpoint: 'logout',
        team: user.teamName,
      },
      timeout: '15s',
    });
  }
}
