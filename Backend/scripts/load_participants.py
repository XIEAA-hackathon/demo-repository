"""Authenticated single-process load driver for participant sockets and bids.

Credential CSV columns: email,password. Point only at an authorized test event.

Scenarios: default = sockets only; --reconcile = dashboard load; --round with
--bid-clients = bidding/fan-out; add --slow-clients for slow-reader isolation.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

import websockets


def request(url: str, *, token: str | None = None, data: dict | None = None) -> tuple[int, float, dict, str | None]:
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json"} if body else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=15) as response:
            return response.status, (time.perf_counter() - started) * 1000, json.load(response), response.headers.get("Server-Timing")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.load(exc)
        except Exception:
            payload = {}
        return exc.code, (time.perf_counter() - started) * 1000, payload, exc.headers.get("Server-Timing")


def record_server_timing(value: str | None, latencies: dict[str, list[float]]) -> None:
    for metric in (value or "").split(","):
        name, _, parameters = metric.strip().partition(";")
        for parameter in parameters.split(";"):
            if parameter.startswith("dur=") and name in latencies:
                with suppress(ValueError):
                    latencies[name].append(float(parameter.removeprefix("dur=")))


def login(base_url: str, email: str, password: str) -> str:
    body = urllib.parse.urlencode({"username": email, "password": password}).encode()
    with urllib.request.urlopen(
        urllib.request.Request(
            f"{base_url}/login",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ),
        timeout=15,
    ) as response:
        return json.load(response)["access_token"]


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))], 2)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("credentials", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--clients", type=int, default=600)
    parser.add_argument("--duration", type=int, default=180)
    parser.add_argument("--heartbeat-seconds", type=float, default=20)
    parser.add_argument("--reconcile", action="store_true")
    parser.add_argument("--slow-clients", type=int, default=0)
    parser.add_argument("--round", choices=("none", "round1", "wildcard"), default="none")
    parser.add_argument("--bid-clients", type=int, default=10)
    parser.add_argument("--problem-id", type=int)
    parser.add_argument("--bid-increment", type=int, default=1)
    parser.add_argument("--bid-interval", type=float, default=6)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    base_parts = urllib.parse.urlsplit(base_url)
    ws_url = urllib.parse.urlunsplit((
        "wss" if base_parts.scheme == "https" else "ws",
        base_parts.netloc,
        base_parts.path,
        "",
        "",
    ))
    credentials = list(csv.DictReader(args.credentials.open(encoding="utf-8")))[: args.clients]
    if len(credentials) < args.clients:
        parser.error(f"need {args.clients} unique credentials, found {len(credentials)}")
    if args.round == "round1" and not args.problem_id:
        parser.error("--problem-id is required for Round 1 bids")
    if args.round != "none" and not 0 <= args.bid_clients <= args.clients:
        parser.error("--bid-clients must be between 0 and --clients")

    stats = Counter()
    latencies: dict[str, list[float]] = {
        "http": [], "dashboard": [], "bid": [], "broadcast": [],
        "auction-lock": [], "db-transaction": [],
    }
    health_samples: list[dict] = []
    login_limit = asyncio.Semaphore(20)

    async def authenticate(row: dict[str, str]) -> str | None:
        async with login_limit:
            try:
                return await asyncio.to_thread(login, base_url, row["email"], row["password"])
            except Exception:
                stats["login_failures"] += 1
                return None

    tokens = [token for token in await asyncio.gather(*(authenticate(row) for row in credentials)) if token]
    stop_at = asyncio.get_running_loop().time() + args.duration

    async def participant(index: int, token: str) -> None:
        try:
            async with websockets.connect(
                f"{ws_url}/ws/auction?token={urllib.parse.quote(token)}",
                open_timeout=15,
                close_timeout=2,
            ) as socket:
                stats["connections"] += 1

                async def receive() -> None:
                    if index < args.slow_clients:
                        await asyncio.sleep(args.duration)
                        return
                    async for raw in socket:
                        message = json.loads(raw)
                        stats[f"event_{message.get('type', 'unknown')}"] += 1
                        server_time = message.get("server_time")
                        if isinstance(server_time, str):
                            with suppress(ValueError):
                                sent_at = datetime.fromisoformat(server_time.replace("Z", "+00:00"))
                                latencies["broadcast"].append(max(
                                    0.0,
                                    (datetime.now(timezone.utc) - sent_at).total_seconds() * 1000,
                                ))

                async def heartbeat() -> None:
                    while asyncio.get_running_loop().time() < stop_at:
                        await asyncio.sleep(args.heartbeat_seconds)
                        await socket.send(json.dumps({"type": "heartbeat", "client_time": int(time.time() * 1000)}))
                        stats["heartbeats"] += 1

                async def reconcile() -> None:
                    while args.reconcile and asyncio.get_running_loop().time() < stop_at:
                        await asyncio.sleep(random.uniform(60, 90))
                        status, elapsed, _, _ = await asyncio.to_thread(
                            request, f"{base_url}/participant/dashboard", token=token,
                        )
                        stats[f"dashboard_{status}"] += 1
                        stats["http_requests"] += 1
                        stats["http_failures"] += status >= 400
                        stats["http_503"] += status == 503
                        latencies["http"].append(elapsed)
                        latencies["dashboard"].append(elapsed)

                async def bid() -> None:
                    if args.round == "none" or index >= args.bid_clients:
                        return
                    while asyncio.get_running_loop().time() < stop_at:
                        await asyncio.sleep(random.uniform(0, args.bid_interval))
                        path = "/bid" if args.round == "round1" else "/wildcard/bid"
                        payload = {"increment": args.bid_increment}
                        if args.round == "round1":
                            payload["ps_id"] = args.problem_id
                        status, elapsed, _, server_timing = await asyncio.to_thread(
                            request, f"{base_url}{path}", token=token, data=payload,
                        )
                        stats[f"bid_{status}"] += 1
                        stats["http_requests"] += 1
                        stats["http_failures"] += status >= 400
                        stats["http_503"] += status == 503
                        latencies["http"].append(elapsed)
                        latencies["bid"].append(elapsed)
                        record_server_timing(server_timing, latencies)
                        await asyncio.sleep(args.bid_interval)

                tasks = [asyncio.create_task(work()) for work in (receive, heartbeat, reconcile, bid)]
                await asyncio.sleep(max(0, stop_at - asyncio.get_running_loop().time()))
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as exc:
            stats["disconnects_or_connect_failures"] += 1
            stats[f"connection_error_{exc.__class__.__name__}"] += 1

    async def sample_health() -> None:
        while asyncio.get_running_loop().time() < stop_at:
            status, _, payload, _ = await asyncio.to_thread(request, f"{base_url}/health/ready")
            stats[f"health_{status}"] += 1
            stats["http_requests"] += 1
            stats["http_failures"] += status >= 400
            stats["http_503"] += status == 503
            if status == 200:
                health_samples.append(payload)
            await asyncio.sleep(5)

    await asyncio.gather(sample_health(), *(participant(index, token) for index, token in enumerate(tokens)))
    pool_samples = [sample.get("database_pool", {}) for sample in health_samples]
    websocket_samples = [sample.get("websocket", {}) for sample in health_samples]
    http_requests = stats["http_requests"]
    summary = {
        "configured_clients": args.clients,
        "authenticated_clients": len(tokens),
        "bid_clients": min(args.bid_clients, len(tokens)) if args.round != "none" else 0,
        "duration_seconds": args.duration,
        "counts": dict(stats),
        "rates": {
            "http_requests_per_second": round(http_requests / args.duration, 2),
            "http_failure_percent": round(100 * stats["http_failures"] / http_requests, 2) if http_requests else 0,
            "http_503_percent": round(100 * stats["http_503"] / http_requests, 2) if http_requests else 0,
        },
        "latency_ms": {
            name: {"p50": percentile(values, 0.50), "p95": percentile(values, 0.95), "p99": percentile(values, 0.99), "mean": round(statistics.mean(values), 2) if values else None}
            for name, values in latencies.items()
        },
        "observed_peaks": {
            "db_checked_out": max((sample.get("checked_out") or 0 for sample in pool_samples), default=0),
            "db_overflow_in_use": max((sample.get("overflow_in_use") or 0 for sample in pool_samples), default=0),
            "db_pool_timeout_count": max((sample.get("pool_timeout_count") or 0 for sample in pool_samples), default=0),
            "websocket_active_connections": max((sample.get("active_connections") or 0 for sample in websocket_samples), default=0),
            "broadcast_queue_depth": max((sample.get("broadcast_queue_depth") or 0 for sample in websocket_samples), default=0),
            "broadcast_dropped_total": max((sample.get("broadcast_dropped_total") or 0 for sample in websocket_samples), default=0),
            "client_queue_overflows": max((sample.get("client_queue_overflows") or 0 for sample in websocket_samples), default=0),
            "slow_client_disconnects": max((sample.get("slow_client_disconnects") or 0 for sample in websocket_samples), default=0),
        },
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
