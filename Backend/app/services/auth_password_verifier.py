from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import BoundedSemaphore, Lock
from time import perf_counter
from typing import Callable

from app.core.config import settings


PasswordVerifier = Callable[[str, str], bool]


@dataclass(frozen=True)
class PasswordVerificationResult:
    valid: bool
    queue_wait_ms: float
    bcrypt_ms: float


class AuthenticationCapacityUnavailable(RuntimeError):
    def __init__(self, reason: str, queue_wait_ms: float):
        super().__init__(reason)
        self.reason = reason
        self.queue_wait_ms = queue_wait_ms


class BoundedPasswordVerifier:
    """Run password verification in an isolated, bounded executor.

    Admission counts both running and waiting requests. Waiting for a worker is
    asynchronous and uses no general-purpose executor thread, while bcrypt is
    submitted only after one of the dedicated worker slots has been acquired.
    """

    def __init__(self, *, concurrency: int, queue_limit: int, queue_timeout_seconds: float):
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        if queue_limit < concurrency:
            raise ValueError("queue_limit must be at least concurrency")
        if queue_timeout_seconds <= 0:
            raise ValueError("queue_timeout_seconds must be greater than 0")

        self.concurrency = concurrency
        self.queue_limit = queue_limit
        self.queue_timeout_seconds = queue_timeout_seconds
        self._admission_slots = BoundedSemaphore(queue_limit)
        self._worker_slots = BoundedSemaphore(concurrency)
        self._executor = ThreadPoolExecutor(
            max_workers=concurrency,
            thread_name_prefix="auth-bcrypt",
        )
        self._stats_lock = Lock()
        self._active = 0
        self._peak_active = 0

    @property
    def peak_active(self) -> int:
        with self._stats_lock:
            return self._peak_active

    def _execute(self, verifier: PasswordVerifier, password: str, password_hash: str) -> tuple[bool, float]:
        with self._stats_lock:
            self._active += 1
            self._peak_active = max(self._peak_active, self._active)
        started_at = perf_counter()
        try:
            return verifier(password, password_hash), (perf_counter() - started_at) * 1000
        finally:
            with self._stats_lock:
                self._active -= 1

    async def verify(
        self,
        password: str,
        password_hash: str,
        verifier: PasswordVerifier,
    ) -> PasswordVerificationResult:
        queued_at = perf_counter()
        if not self._admission_slots.acquire(blocking=False):
            raise AuthenticationCapacityUnavailable("queue_full", 0.0)

        deadline = queued_at + self.queue_timeout_seconds
        worker_acquired = False
        try:
            while not self._worker_slots.acquire(blocking=False):
                remaining = deadline - perf_counter()
                if remaining <= 0:
                    raise AuthenticationCapacityUnavailable(
                        "queue_timeout",
                        (perf_counter() - queued_at) * 1000,
                    )
                await asyncio.sleep(min(0.01, remaining))
            worker_acquired = True

            queue_wait_ms = (perf_counter() - queued_at) * 1000
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(
                self._executor,
                self._execute,
                verifier,
                password,
                password_hash,
            )

            def release_capacity(_future) -> None:
                self._worker_slots.release()
                self._admission_slots.release()

            future.add_done_callback(release_capacity)
            worker_acquired = False
            valid, bcrypt_ms = await asyncio.shield(future)
            return PasswordVerificationResult(
                valid=valid,
                queue_wait_ms=queue_wait_ms,
                bcrypt_ms=bcrypt_ms,
            )
        finally:
            if worker_acquired:
                self._worker_slots.release()
                self._admission_slots.release()
            elif 'future' not in locals():
                self._admission_slots.release()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)


password_verifier = BoundedPasswordVerifier(
    concurrency=settings.AUTH_BCRYPT_CONCURRENCY,
    queue_limit=settings.AUTH_LOGIN_QUEUE_LIMIT,
    queue_timeout_seconds=settings.AUTH_LOGIN_QUEUE_TIMEOUT_SECONDS,
)
