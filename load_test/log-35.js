import http from 'k6/http';
import { check, sleep } from 'k6';

const csv = open('bid_to_build_80_participants.csv');
const users = csv
  .trim()
  .split(/\r?\n/)
  .slice(1)
  .map((line) => {
    const columns = line.split(',');

    const password = columns[2].trim(); // Leader Password
    const username = columns[4].trim(); // Leader Login Email

    return { username, password };
  });

export const options = {
  scenarios: {
    simultaneous_logins: {
      executor: 'per-vu-iterations',
      vus: users.length,
      iterations: 1,
      maxDuration: '60s',
    },
  },
};

export default function () {
  const user = users[__VU - 1];

  const payload =
    `username=${encodeURIComponent(user.username)}` +
    `&password=${encodeURIComponent(user.password)}`;

  const loginRes = http.post(
    'https://bidtobuild.dev/api/login',
    payload,
    {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      timeout: '30s',
    }
  );

  const ok = check(loginRes, {
    'login 200': (r) => r.status === 200,
  });

  if (!ok) {
    console.log(`VU ${__VU} failed: ${loginRes.status}`);
    return;
  }

  const token = loginRes.json('access_token');

  sleep(1);

  const logoutRes = http.post(
    'https://bidtobuild.dev/api/logout',
    null,
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );

  check(logoutRes, {
    'logout 200': (r) => r.status === 200,
  });
}