"""Shared HTTP helpers for direct-API loaders: per-host throttling + JSON/CSV GET.

Several free providers — Eastmoney most notably — rate-limit by source IP and
will temporarily ban a client that bursts requests. Rather than scatter sleep
calls across loaders, every ban-prone call routes through :func:`throttled_get`
here, which enforces a minimum spacing between consecutive requests to the same
*host bucket* (plus a little jitter so concurrent workers don't lock-step) and
reuses one :class:`requests.Session` per process so TCP/TLS setup is amortized.

This module is intentionally provider-agnostic: it knows nothing about
Eastmoney/Sina/Stooq field layouts, only how to space requests politely. A
loader picks its own ``host_key`` and ``min_interval`` and stays ignorant of
the locking mechanics.

All spacing is best-effort and process-local — it does not coordinate across
machines. For batch jobs raise the relevant ``*_MIN_INTERVAL`` env var.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any

import requests

from backtest.loaders.base import positive_env_float

logger = logging.getLogger(__name__)

# Default User-Agent. Many free quote endpoints reject the bare urllib/requests
# UA, so we present a normal desktop browser string. Loaders may override.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Upper bound on the random jitter (seconds) added on top of the configured
# minimum interval, so parallel callers de-synchronize instead of all firing
# the instant the interval elapses.
_JITTER_MAX_S = 0.4
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_DEFAULT_ATTEMPTS = 3
_BACKOFF_BASE_S = 0.45
_BACKOFF_MAX_S = 2.0


class HostThrottle:
    """Process-wide minimum-spacing gate keyed by an arbitrary host bucket.

    One instance guards all callers; ``wait(bucket, min_interval)`` blocks until
    at least ``min_interval`` seconds (plus jitter) have elapsed since the last
    request tagged with the same ``bucket``. The lock is held only for the
    bookkeeping arithmetic, not across the sleep, so distinct buckets never block
    one another.
    """

    def __init__(self) -> None:
        self._last: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()
        self._last_sweep: float = 0.0

    def _sweep_stale_locked(self, cutoff: float) -> None:
        """Drop buckets whose spacing window has fully elapsed. Caller holds the lock.

        A bucket is only stale once ``fire_at + min_interval`` has passed —
        before that, the next request to that bucket must still wait for its
        spacing interval. Sweeping earlier would let the next request fire
        immediately, defeating the rate limiter.
        """
        stale = [k for k, (t, interval) in self._last.items() if t + interval < cutoff]
        for k in stale:
            del self._last[k]

    def wait(self, bucket: str, min_interval: float) -> None:
        """Block until ``bucket`` is allowed to fire again, then record the slot.

        The *reserved fire time* — jitter included — is what gets stored, so the
        next caller spaces off this caller's actual fire instant rather than an
        earlier un-jittered one. This keeps consecutive requests at least
        ``min_interval`` apart even when many callers burst concurrently (the
        exact scenario the throttle exists for); the jitter only ever pushes a
        slot later, never earlier.
        """
        if min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            # Periodic sweep: drop stale buckets so a process that queries
            # many distinct hosts (e.g. a batch job hitting N tickers) does
            # not accumulate dead entries without bound. Throttled to once
            # per minute to avoid sweeping on every call.
            if now - self._last_sweep >= 60.0:
                self._sweep_stale_locked(now)
                self._last_sweep = now
            entry = self._last.get(bucket)
            last = entry[0] if entry is not None else None
            if last is None or now >= last + min_interval:
                # Slot is free right now — fire immediately, no jitter needed.
                fire_at = now
            else:
                # Chain off the previous reservation and add jitter to desync
                # concurrent callers, baking the jitter into the stored slot.
                fire_at = last + min_interval + random.uniform(0.0, _JITTER_MAX_S)
            self._last[bucket] = (fire_at, min_interval)
        sleep_for = fire_at - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)


# One shared gate for the whole process.
_THROTTLE = HostThrottle()

# Per-process session reuse, keyed by host bucket so different providers keep
# independent connection pools and cookie jars.
_SESSIONS: dict[str, requests.Session] = {}
_SESSIONS_LOCK = threading.Lock()


def _session_for(bucket: str) -> requests.Session:
    with _SESSIONS_LOCK:
        session = _SESSIONS.get(bucket)
        if session is None:
            session = requests.Session()
            _SESSIONS[bucket] = session
        return session


def _reset_session(bucket: str) -> requests.Session:
    """Close and replace a stale session for *bucket*.

    Some providers (e.g. Eastmoney) intermittently drop keep-alive connections
    without sending ``Connection: close``, causing ``RemoteDisconnected`` on
    the next reuse.  Rebuilding the session forces a fresh TCP/TLS handshake.
    """
    with _SESSIONS_LOCK:
        old = _SESSIONS.pop(bucket, None)
        if old is not None:
            try:
                old.close()
            except Exception:  # noqa: BLE001
                pass
        session = requests.Session()
        _SESSIONS[bucket] = session
        return session


def _sleep_backoff(attempt: int) -> None:
    delay = min(_BACKOFF_BASE_S * (2**attempt) + random.uniform(0.0, 0.15), _BACKOFF_MAX_S)
    time.sleep(delay)


def _is_retryable_request_exception(exc: Exception) -> bool:
    return isinstance(exc, (requests.ConnectionError, requests.Timeout))


def _is_retryable_http_error(exc: Exception) -> bool:
    if not isinstance(exc, requests.HTTPError):
        return False
    response = getattr(exc, "response", None)
    if response is None:
        return True
    return int(getattr(response, "status_code", 0) or 0) in _RETRYABLE_STATUS_CODES


def resolve_min_interval(env_name: str, default: float) -> float:
    """Resolve a per-provider minimum request interval from the environment.

    Args:
        env_name: Env var carrying an override in seconds (e.g.
            ``VIBE_TRADING_EASTMONEY_MIN_INTERVAL``).
        default: Fallback interval when the env var is absent or invalid.

    Returns:
        The override when it parses to a positive float, else ``default``.
    """
    return positive_env_float(env_name, default)


def throttled_get(
    url: str,
    *,
    host_key: str,
    min_interval: float,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    attempts: int = _DEFAULT_ATTEMPTS,
) -> requests.Response:
    """GET ``url`` after waiting out the per-host minimum interval.

    Args:
        url: Fully-qualified request URL.
        host_key: Throttle/session bucket. All calls sharing a key are spaced
            by ``min_interval`` and reuse one session.
        min_interval: Minimum seconds between consecutive calls to ``host_key``.
        params: Optional query parameters.
        headers: Optional headers merged over the default browser UA.
        timeout: Per-request socket timeout in seconds.

    Returns:
        The :class:`requests.Response`; the caller decides how to parse it.

    Raises:
        requests.RequestException: Propagated unchanged for the caller's retry
            policy to classify as transient.
    """
    merged_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        merged_headers.update(headers)
    last_exc: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            _THROTTLE.wait(host_key, min_interval)
            session = _session_for(host_key)
            return session.get(url, params=params, headers=merged_headers, timeout=timeout)
        except requests.RequestException as exc:
            last_exc = exc
            # RemoteDisconnected / ConnectionReset → stale keep-alive; rebuild
            # the session so the next attempt gets a fresh TCP connection.
            _is_stale_conn = isinstance(
                exc,
                (requests.ConnectionError,),
            ) and any(
                kw in str(exc).lower()
                for kw in ("remote disconnected", "connection reset", "broken pipe")
            )
            if _is_stale_conn:
                logger.debug("resetting stale session for %s after %s", host_key, exc)
                _reset_session(host_key)
            if attempt + 1 >= max(1, attempts) or not _is_retryable_request_exception(exc):
                raise
            logger.debug("retrying throttled GET %s after %s", url, exc)
            _sleep_backoff(attempt)
    assert last_exc is not None
    raise last_exc


def throttled_get_json(
    url: str,
    *,
    host_key: str,
    min_interval: float,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    attempts: int = _DEFAULT_ATTEMPTS,
) -> Any:
    """Throttled GET that decodes the response body as JSON.

    Same contract as :func:`throttled_get`, plus ``response.raise_for_status()``
    and ``response.json()``. A non-2xx status or undecodable body raises, which
    the caller's bounded-retry wrapper treats as transient.
    """
    last_exc: Exception | None = None
    for attempt in range(max(1, attempts)):
        response = throttled_get(
            url,
            host_key=host_key,
            min_interval=min_interval,
            params=params,
            headers=headers,
            timeout=timeout,
            attempts=1,
        )
        try:
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            last_exc = exc
            if attempt + 1 >= max(1, attempts) or not _is_retryable_http_error(exc):
                raise
            logger.debug("retrying throttled JSON GET %s after %s", url, exc)
        except ValueError as exc:
            last_exc = exc
            if attempt + 1 >= max(1, attempts):
                raise
            logger.debug("retrying throttled JSON decode %s after %s", url, exc)
        _sleep_backoff(attempt)
    assert last_exc is not None
    raise last_exc
