"""
Concurrency utilities.
"""

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Hashable
from contextlib import AbstractAsyncContextManager, asynccontextmanager


class KeyedLock:
    """
    A lock that manages independent locks for different keys.
    Allows high concurrency for disjoint keys while ensuring exclusion for the same key.

    CONCURRENCY MODEL:
    This class provides per-key locking to prevent race conditions when multiple
    async tasks operate on resources identified by keys (e.g., resource paths, CIDRs).

    Example Use Case:
        Two tasks modifying different networks (keys: "10.1.0.0/24", "10.2.0.0/24")
        can proceed concurrently, but two tasks modifying the same network will
        serialize via the same lock.

    THREAD-SAFETY:
        - defaultdict access is atomic in CPython (GIL protection)
        - Once a lock is created for a key, it persists in the dict
        - asyncio.Lock itself is async-safe (not thread-safe, but we're async-only)
        - No lock is ever deleted, avoiding race during lookup

    DESIGN RATIONALE:
        - Using defaultdict instead of manual "if key not in dict" avoids
          TOCTOU (time-of-check-time-of-use) race conditions
        - Locks are never removed to prevent race where:
          1. Task A checks key exists
          2. Task B deletes lock after releasing
          3. Task A acquires stale/wrong lock
    """

    def __init__(self) -> None:
        # defaultdict creates Lock on first access atomically
        # WHY defaultdict: Avoids race between "check if exists" and "create lock"
        # MEMORY: Locks persist forever - acceptable for bounded key spaces (resource paths)
        self._locks: dict[Hashable, asyncio.Lock] = defaultdict(asyncio.Lock)

    @asynccontextmanager
    async def acquire(self, key: Hashable) -> AsyncIterator[None]:
        """
        Acquire lock for a specific key.

        USAGE:
            async with keyed_lock.acquire("some_resource_path"):
                # Critical section - exclusive access for this key
                # Other keys can proceed concurrently
                await modify_resource()

        Args:
            key: Any hashable identifier (str, int, tuple, etc.)
                 Common keys: resource paths, CIDRs, BAM IDs

        Yields:
            None (context manager pattern)
        """
        # Fetch or create lock for this key atomically
        lock = self._locks[key]

        # Acquire the key-specific lock
        # WHY async with: Ensures lock is released even if exception occurs
        async with lock:
            yield

    def __call__(self, key: Hashable) -> AbstractAsyncContextManager[None]:
        """
        Shortcut for acquire.

        Allows: async with keyed_lock(key): ...
        Instead of: async with keyed_lock.acquire(key): ...
        """
        return self.acquire(key)
