"""Authentication abuse protection independent of authenticated request state."""

from collections import defaultdict, deque
from time import monotonic
from threading import Lock


class AuthAttemptGuard:
    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, *identities: str) -> bool:
        now = monotonic()
        allowed = True
        with self._lock:
            for identity in identities:
                events = self._events[identity]
                while events and events[0] <= now - self.window_seconds:
                    events.popleft()
                if len(events) >= self.limit:
                    allowed = False
            if allowed:
                for identity in identities:
                    self._events[identity].append(now)
        return allowed


def client_identity(request) -> str:
    return request.client.host if request.client else "unknown"
