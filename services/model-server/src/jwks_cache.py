"""Bounded LRU cache with positive & negative TTL for JWKS public keys."""

import asyncio
import collections
import time
from typing import Any

_SENTINEL = object()


class JwksKeyCache:
    """Bounded LRU cache with positive & negative TTL, for use from one event loop.

    Protects Control Plane from DoS floods when requests query unknown or invalid key IDs.
    The cache itself is not locked: its methods never await, so coroutines on a single
    loop cannot interleave inside them. ``fetch_lock`` serialises JWKS downloads and
    ``last_fetch_at`` rate-limits them, so concurrent or ever-changing unknown key IDs
    cost the Control Plane at most one fetch per ``min_refetch_interval``.
    """

    def __init__(
        self,
        max_size: int = 500,
        positive_ttl: float = 3600.0,
        negative_ttl: float = 60.0,
        min_refetch_interval: float = 10.0,
    ):
        self.max_size = max_size
        self.positive_ttl = positive_ttl
        self.negative_ttl = negative_ttl
        self.min_refetch_interval = min_refetch_interval
        self.fetch_lock = asyncio.Lock()
        self.last_fetch_at: float | None = None
        # Map: kid -> (value, expires_at_monotonic)
        self._entries: collections.OrderedDict[str, tuple[Any, float]] = collections.OrderedDict()

    def _evict_expired(self, now: float) -> None:
        expired = [kid for kid, (_, exp) in self._entries.items() if now > exp]
        for kid in expired:
            del self._entries[kid]

    def _enforce_capacity(self) -> None:
        now = time.monotonic()
        self._evict_expired(now)
        while len(self._entries) >= self.max_size:
            self._entries.popitem(last=False)

    def get(self, kid: str, default: Any = None) -> Any:
        now = time.monotonic()
        if kid not in self._entries:
            return default
        value, expires_at = self._entries[kid]
        if now > expires_at:
            del self._entries[kid]
            return default
        self._entries.move_to_end(kid)
        return value

    def set(self, kid: str, value: Any, ttl: float | None = None) -> None:
        if ttl is None:
            ttl = self.positive_ttl if value is not None else self.negative_ttl
        self._enforce_capacity()
        self._entries[kid] = (value, time.monotonic() + ttl)
        self._entries.move_to_end(kid)

    def set_negative(self, kid: str) -> None:
        """Cache a missing key ID as negative entry for negative_ttl seconds."""
        self.set(kid, None, ttl=self.negative_ttl)

    def is_negative(self, kid: str) -> bool:
        """Check if kid is currently cached as negative (None) and unexpired."""
        now = time.monotonic()
        if kid not in self._entries:
            return False
        value, expires_at = self._entries[kid]
        if now > expires_at:
            del self._entries[kid]
            return False
        return value is None

    def __contains__(self, kid: str) -> bool:
        now = time.monotonic()
        if kid not in self._entries:
            return False
        _, expires_at = self._entries[kid]
        if now > expires_at:
            del self._entries[kid]
            return False
        return True

    def __getitem__(self, kid: str) -> Any:
        res = self.get(kid, default=_SENTINEL)
        if res is _SENTINEL:
            raise KeyError(kid)
        return res

    def __setitem__(self, kid: str, value: Any) -> None:
        self.set(kid, value)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        now = time.monotonic()
        self._evict_expired(now)
        return len(self._entries)

