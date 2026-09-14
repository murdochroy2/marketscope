"""Resilient HTTP for third-party APIs: rate limiting, retries with backoff, request budgets.

Every provider goes through ``ResilientHttpClient`` so that throttling and failure
policy are defined once rather than re-implemented per integration.
"""

from __future__ import annotations

import asyncio
import email.utils
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


class ProviderError(Exception):
    """A request that failed permanently, after any retries."""

    def __init__(
        self, message: str, *, status_code: int | None = None, retryable: bool = False
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class RetryableResponseError(ProviderError):
    """Raised by a response validator when a 200 response still means "try again"."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class RequestBudgetExceededError(ProviderError):
    """The per-market cap on outbound requests has been reached."""


class RateLimiter:
    """Spaces requests at least ``min_interval_s`` apart across all concurrent callers."""

    def __init__(self, min_interval_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._min_interval_s = min_interval_s
        self._clock = clock
        self._next_slot = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = self._clock()
            wait = self._next_slot - now
            self._next_slot = max(now, self._next_slot) + self._min_interval_s
        if wait > 0:
            await asyncio.sleep(wait)


class RequestBudget:
    """Counts outbound requests, retries included, and refuses once the cap is hit."""

    def __init__(self, limit: int | None) -> None:
        self.limit = limit
        self.used = 0

    @property
    def exhausted(self) -> bool:
        return self.limit is not None and self.used >= self.limit

    def spend(self) -> None:
        if self.exhausted:
            raise RequestBudgetExceededError(f"request budget of {self.limit} exhausted")
        self.used += 1


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay_s: float = 1.0
    max_delay_s: float = 20.0

    def backoff(self, attempt: int) -> float:
        """Exponential backoff with full jitter. ``attempt`` is 1-based."""
        ceiling = min(self.max_delay_s, self.base_delay_s * 2 ** (attempt - 1))
        return random.uniform(0, ceiling)


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        parsed = email.utils.parsedate_to_datetime(value)
        return max(0.0, parsed.timestamp() - time.time()) if parsed else None


Sleep = Callable[[float], Awaitable[None]]


class ResilientHttpClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        rate_limiter: RateLimiter | None = None,
        retry: RetryPolicy | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._client = client
        self._rate_limiter = rate_limiter
        self._retry = retry or RetryPolicy()
        self._sleep = sleep

    async def request_json(
        self,
        method: str,
        url: str | Callable[[int], str],
        *,
        budget: RequestBudget | None = None,
        validate: Callable[[Any], None] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Send a request and return parsed JSON, retrying transient failures.

        ``url`` may be a function of the attempt number, which lets a provider rotate
        between mirrors when one is overloaded. ``validate`` inspects the decoded body
        and may raise ``RetryableResponseError`` for APIs that report overload with a 200.
        """
        last_error: ProviderError | None = None
        for attempt in range(1, self._retry.max_attempts + 1):
            if budget is not None:
                budget.spend()
            if self._rate_limiter is not None:
                await self._rate_limiter.acquire()

            target = url(attempt) if callable(url) else url
            retry_after: float | None = None
            try:
                response = await self._client.request(method, target, **kwargs)
                if response.status_code in RETRYABLE_STATUS:
                    retry_after = parse_retry_after(response.headers.get("Retry-After"))
                    raise ProviderError(
                        f"{response.status_code} from {httpx.URL(target).host}",
                        status_code=response.status_code,
                        retryable=True,
                    )
                if response.is_error:
                    host = httpx.URL(target).host
                    raise ProviderError(
                        f"{response.status_code} from {host}: {response.text[:200]}",
                        status_code=response.status_code,
                    )
                try:
                    body = response.json()
                except ValueError as exc:
                    raise RetryableResponseError(
                        f"non-JSON response from {httpx.URL(target).host}"
                    ) from exc
                if validate is not None:
                    validate(body)
                return body
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = ProviderError(
                    f"{type(exc).__name__} calling {httpx.URL(target).host}", retryable=True
                )
            except ProviderError as exc:
                if not exc.retryable:
                    raise
                last_error = exc

            if attempt < self._retry.max_attempts:
                delay = retry_after if retry_after is not None else self._retry.backoff(attempt)
                logger.warning(
                    "attempt %s failed (%s); retrying in %.1fs", attempt, last_error, delay
                )
                await self._sleep(delay)

        assert last_error is not None
        raise ProviderError(
            f"gave up after {self._retry.max_attempts} attempts: {last_error}",
            status_code=last_error.status_code,
        )
