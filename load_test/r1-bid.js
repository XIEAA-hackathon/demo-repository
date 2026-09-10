import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Trend, Rate, Counter } from 'k6/metrics';

// ============================================================
// CONFIG
// ============================================================

const BASE_URL = 'https://bidtobuild.dev/api';

const PARTICIPANTS = Number(__ENV.USERS || 80);
const PS_ID = Number(__ENV.PS_ID || 1);

const BIDS_PER_USER = Number(__ENV.BIDS_PER_USER || 10);
const COOLDOWN_SECONDS = Number(__ENV.COOLDOWN || 5);

// ============================================================
// METRICS
// ============================================================

const loginDuration = new Trend('login_duration', true);
const bidDuration = new Trend('bid_duration', true);

const loginSuccess = new Rate('login_success');
const bidSuccess = new Rate('bid_success');

const bidAttempts = new Counter('bid_attempts');
const bid429 = new Counter('bid_429');
const bid4xx = new Counter('bid_4xx');
const bid5xx = new Counter('bid_5xx');

// ============================================================
// LOAD PARTICIPANTS
// ============================================================

const users = new SharedArray('users', function () {
    const csv = open('bid_to_build_80_participants.csv');

    return csv
        .trim()
        .split(/\r?\n/)
        .slice(1)
        .map((line) => {
            const columns = line.split(',');

            // CSV format:
            // 0 = index
            // 1 = Team Name
            // 2 = Leader Name
            // 3 = Leader Password
            // 4 = Leader Email ID
            // 5 = Leader Login Email
            // 6 = Credential Status

            return {
                password: columns[2].trim(),
                username: columns[4].trim(),
            };
        });
});

if (users.length < PARTICIPANTS) {
    throw new Error(
        `Requested ${PARTICIPANTS} users but CSV only has ${users.length}`
    );
}

// ============================================================
// K6 OPTIONS
// ============================================================

export const options = {
    scenarios: {
        round1_bidding: {
            executor: 'per-vu-iterations',

            vus: PARTICIPANTS,
            iterations: 1,

            maxDuration: '3m',
            gracefulStop: '30s',
        },
    },

    thresholds: {
        login_success: ['rate>0.99'],

        // Successful bids ideally under 2 sec p95
        bid_duration: ['p(95)<2000'],

        bid_5xx: ['count==0'],
    },
};

// ============================================================
// SETUP
// ============================================================

export function setup() {
    /*
        Give everyone 25 seconds to complete login.

        All VUs then send their FIRST bid at approximately
        the same moment.

        After that every VU waits 5 seconds between bids.
    */

    return {
        firstBidAt: Date.now() + 25000,
    };
}

// ============================================================
// TEST
// ============================================================

export default function (data) {

    const user = users[__VU - 1];

    // ========================================================
    // 1. LOGIN
    // ========================================================

    const loginPayload =
        `username=${encodeURIComponent(user.username)}` +
        `&password=${encodeURIComponent(user.password)}`;

    const loginRes = http.post(
        `${BASE_URL}/login`,
        loginPayload,
        {
            headers: {
                'Content-Type':
                    'application/x-www-form-urlencoded',
            },

            timeout: '30s',

            tags: {
                operation: 'login',
            },
        }
    );

    loginDuration.add(loginRes.timings.duration);

    const loginOk = check(loginRes, {
        'login 200': (r) => r.status === 200,
    });

    loginSuccess.add(loginOk);

    if (!loginOk) {
        console.error(
            `LOGIN_FAIL ` +
            `VU=${__VU} ` +
            `user=${user.username} ` +
            `status=${loginRes.status} ` +
            `duration=${loginRes.timings.duration}ms`
        );

        return;
    }

    // ========================================================
    // GET TOKEN
    // ========================================================

    let token;

    try {
        token = loginRes.json('access_token');
    } catch (_) {
        console.error(
            `TOKEN_PARSE_FAIL VU=${__VU}`
        );
        return;
    }

    if (!token) {
        console.error(
            `TOKEN_MISSING VU=${__VU}`
        );
        return;
    }

    // ========================================================
    // 2. WAIT FOR SIMULTANEOUS FIRST BID
    // ========================================================

    const waitMs =
        data.firstBidAt - Date.now();

    if (waitMs > 0) {
        sleep(waitMs / 1000);
    }

    // ========================================================
    // 3. BID LOOP
    // ========================================================

    for (
        let bidNumber = 1;
        bidNumber <= BIDS_PER_USER;
        bidNumber++
    ) {

        bidAttempts.add(1);

        const bidRes = http.post(
            `${BASE_URL}/bid`,

            JSON.stringify({
                ps_id: PS_ID,
                increment: 5,
            }),

            {
                headers: {
                    Authorization:
                        `Bearer ${token}`,

                    'Content-Type':
                        'application/json',
                },

                timeout: '30s',

                tags: {
                    operation: 'bid',
                },
            }
        );

        // ---------------------------------------------
        // SUCCESS
        // ---------------------------------------------

        if (bidRes.status === 200) {

            bidSuccess.add(true);

            bidDuration.add(
                bidRes.timings.duration
            );

        }

        // ---------------------------------------------
        // 429 COOLDOWN
        // ---------------------------------------------

        else if (bidRes.status === 429) {

            bidSuccess.add(false);
            bid429.add(1);

            console.log(
                `COOLDOWN ` +
                `VU=${__VU} ` +
                `bid=${bidNumber}`
            );

        }

        // ---------------------------------------------
        // OTHER 4XX
        // ---------------------------------------------

        else if (
            bidRes.status >= 400 &&
            bidRes.status < 500
        ) {

            bidSuccess.add(false);
            bid4xx.add(1);

            console.error(
                `BID_4XX ` +
                `VU=${__VU} ` +
                `bid=${bidNumber} ` +
                `status=${bidRes.status} ` +
                `body=${bidRes.body}`
            );

        }

        // ---------------------------------------------
        // 5XX
        // ---------------------------------------------

        else if (bidRes.status >= 500) {

            bidSuccess.add(false);
            bid5xx.add(1);

            console.error(
                `BID_5XX ` +
                `VU=${__VU} ` +
                `bid=${bidNumber} ` +
                `status=${bidRes.status} ` +
                `duration=${bidRes.timings.duration}ms ` +
                `body=${bidRes.body}`
            );

        }

        // ---------------------------------------------
        // TIMEOUT / NETWORK ERROR
        // ---------------------------------------------

        else if (bidRes.status === 0) {

            bidSuccess.add(false);

            console.error(
                `BID_TIMEOUT ` +
                `VU=${__VU} ` +
                `bid=${bidNumber} ` +
                `duration=${bidRes.timings.duration}ms`
            );

        }

        check(bidRes, {
            'bid response received':
                (r) => r.status !== 0,
        });

        // ====================================================
        // REAL APPLICATION COOLDOWN
        // ====================================================

        if (bidNumber < BIDS_PER_USER) {
            sleep(COOLDOWN_SECONDS);
        }
    }

    // ========================================================
    // 4. LOGOUT
    // ========================================================

    sleep(1);

    const logoutRes = http.post(
        `${BASE_URL}/logout`,
        null,
        {
            headers: {
                Authorization:
                    `Bearer ${token}`,
            },

            timeout: '15s',

            tags: {
                operation: 'logout',
            },
        }
    );

    check(logoutRes, {
        'logout 200':
            (r) => r.status === 200,
    });
}