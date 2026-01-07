"""Adaptive Throttle - Dynamic concurrency control based on API performance.

Adjusts concurrency limits based on error rates and latency.

ARCHITECTURE NOTE:
This implementation uses a manual counter with Condition variable instead of
Semaphore to support safe dynamic concurrency adjustment. Unlike Semaphore,
which has fixed permit counts, a counter can be adjusted at runtime without
breaking invariants or orphaning waiting tasks.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from ..config import ThrottleConfig

logger = structlog.get_logger(__name__)


@dataclass
class ThrottleMetrics:
    """Metrics for adaptive throttling decisions."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rate_limit_errors: int = 0
    avg_latency_ms: float = 0.0
    last_adjustment_time: float = field(default_factory=time.time)


class AdaptiveThrottle:
    """
    Adaptive concurrency control with automatic adjustment.

    Features:
    - Starts at conservative concurrency level
    - Increases concurrency when system is healthy
    - Decreases concurrency on errors or rate limits
    - Tracks latency and error rates
    - Exponential backoff on rate limit errors
    - Safe dynamic concurrency adjustment (no semaphore issues)

    Architecture:
    Uses a manual task counter with asyncio.Condition for efficient waiting.
    This approach allows seamless concurrency limit changes without orphaning
    tasks or breaking synchronization primitives.
    """

    def __init__(
        self,
        config: ThrottleConfig | None = None,
    ) -> None:
        """
        Initialize adaptive throttle with manual counter for dynamic concurrency control.

        Architecture Rationale:
        - Manual counter + Condition instead of Semaphore:
          * Semaphore has fixed permits that can't be safely adjusted
          * Changing semaphore permits while tasks wait breaks invariants
          * Manual counter allows dynamic adjustment without orphaning tasks

        - Feedback Control Loop:
          * Input: Error rate, average latency
          * Output: Concurrency adjustment
          * Goal: Maximize throughput while maintaining stability

        WHY MANUAL COUNTER:
        asyncio.Semaphore maintains an internal counter that cannot be changed
        after initialization. If we need to decrease concurrency from 10 to 5
        while tasks are waiting, we'd need to:
          1. Create a new Semaphore(5)
          2. Somehow migrate waiting tasks
          3. Risk orphaning tasks or breaking invariants

        With manual counter + Condition:
          1. Simply set self.current_concurrency = 5
          2. Waiting tasks check the new limit on next wakeup
          3. No migration, no orphaning, no race conditions
        """
        cfg = config or ThrottleConfig()

        # Configuration parameters
        self.config = cfg
        self.current_concurrency = cfg.initial_concurrency
        self.min_concurrency = cfg.min_concurrency
        self.max_concurrency = cfg.max_concurrency
        self.adjustment_interval = cfg.adjustment_interval

        # Manual counter approach:
        # - _active_tasks: Current number of running operations
        # - _condition: Efficient wait/notify mechanism
        # - Advantage: Can change current_concurrency safely at runtime
        self._active_tasks = 0
        self._condition = asyncio.Condition()

        # Performance metrics for adaptive decisions
        self.metrics = ThrottleMetrics()

        # Latency tracking uses sliding window for responsiveness
        self._latencies: list[float] = []
        self._max_latency_samples = cfg.max_latency_samples

        # Prevents concurrent adjustments that could interfere
        self._adjusting = False

        logger.info(
            "Adaptive throttle initialized (manual counter mode)",
            initial_concurrency=cfg.initial_concurrency,
            min=cfg.min_concurrency,
            max=cfg.max_concurrency,
            increase_factor=cfg.increase_factor,
            decrease_factor=cfg.decrease_factor,
        )

    async def acquire(self) -> None:
        """
        Acquire a concurrency slot, waiting if necessary.

        WAIT STRATEGY:
        This uses asyncio.Condition.wait() which is more efficient than polling:
          - Task yields control (non-blocking wait)
          - OS scheduler wakes task when notified
          - No CPU wasted on spin-loops

        CONCURRENCY SAFETY:
        The while loop handles two scenarios:
          1. Spurious Wakeups: Rare OS-level false notifications
          2. Dynamic Limit Changes: Concurrency limit decreased while waiting

        Example Timeline:
          T0: Task acquires with limit=10, active=10 → waits
          T1: Limit decreased to 5 due to errors → task still waits
          T2: Active drops to 4, task notified → still waits (4 < 5 is fine)
          T3: Active drops to 3 → task acquires (now room available)

        WHY NOT SEMAPHORE:
        asyncio.Semaphore has fixed permits that can't be adjusted safely.
        Our manual counter + condition allows runtime concurrency changes.
        """
        async with self._condition:
            # Keep waiting while we're at or above the limit
            # WHY WHILE NOT IF: Handles spurious wakeups and limit changes
            while self._active_tasks >= self.current_concurrency:
                # Wait efficiently until notified (either release or limit increase)
                # BLOCKING: Task yields here, doesn't consume CPU
                await self._condition.wait()

            # We have a slot - increment active counter
            # ATOMIC: We hold the condition lock, so this is thread-safe
            self._active_tasks += 1

            logger.debug(
                "Acquired throttle slot",
                active=self._active_tasks,
                limit=self.current_concurrency,
            )

    def release(self) -> None:
        """
        Release a throttle slot non-blocking.

        WHY create_task:
        This method is often called from synchronous contexts (like __exit__).
        Using create_task allows:
          1. Caller doesn't need to await (fire-and-forget)
          2. Release happens asynchronously without blocking caller
          3. Notification might wake multiple waiting tasks

        EDGE CASE: If release is called from an async context where you want
        to wait for completion, call await _release_async() directly instead.
        """
        asyncio.create_task(self._release_async())

    async def _release_async(self) -> None:
        """
        Internal async release implementation with proper synchronization.

        CRITICAL: Must be called within async context to use await

        NOTIFICATION STRATEGY:
        We notify(1) to wake exactly one waiting task. This prevents thundering
        herd where all waiting tasks wake up and fight for the slot.

        ERROR HANDLING:
        If active_tasks is already 0, we log a warning. This indicates a bug:
          - release() called more times than acquire()
          - Likely caused by exception in acquire/release pairing
        """
        async with self._condition:
            if self._active_tasks > 0:
                self._active_tasks -= 1

                # Wake up ONE task waiting for a slot
                # WHY notify(1): Only one slot freed, only one task should wake
                # FAIRNESS: Tasks wake in FIFO order (asyncio.Condition guarantee)
                self._condition.notify(1)

                logger.debug(
                    "Released throttle slot",
                    active=self._active_tasks,
                    limit=self.current_concurrency,
                )
            else:
                # BUG INDICATOR: This indicates release called more than acquire
                # Common causes:
                #   - Exception between acquire and release
                #   - Double-release in error handling
                #   - Manual release without corresponding acquire
                logger.warning("Attempted to release when no tasks active")

    async def __aenter__(self) -> "AdaptiveThrottle":
        """Context manager entry - acquire slot."""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - release slot with error handling."""
        try:
            await self._release_async()
        except Exception as e:
            logger.error("Error releasing throttle slot", error=str(e), exc_info=True)
            # Don't re-raise - we don't want to mask the original exception

    def record_success(self, latency_ms: float) -> None:
        """
        Record a successful request.

        Args:
            latency_ms: Request latency in milliseconds
        """
        self.metrics.total_requests += 1
        self.metrics.successful_requests += 1

        # Track latency
        self._latencies.append(latency_ms)
        if len(self._latencies) > self._max_latency_samples:
            self._latencies.pop(0)

        # Update average latency
        self.metrics.avg_latency_ms = sum(self._latencies) / len(self._latencies)

        # Maybe adjust concurrency
        self._maybe_adjust_concurrency()

    def record_failure(self, is_rate_limit: bool = False) -> None:
        """
        Record a failed request.

        Args:
            is_rate_limit: Whether failure was due to rate limiting
        """
        self.metrics.total_requests += 1
        self.metrics.failed_requests += 1

        if is_rate_limit:
            self.metrics.rate_limit_errors += 1
            # Immediate decrease on rate limit using configurable factor
            asyncio.create_task(self._decrease_concurrency_rate_limit())

        # Maybe adjust concurrency
        self._maybe_adjust_concurrency()

    def _maybe_adjust_concurrency(self) -> None:
        """
        Adjust concurrency based on performance metrics using adaptive feedback control.

        ADAPTIVE ALGORITHM:
        This algorithm implements a feedback control system that dynamically adjusts
        concurrency to optimize throughput while maintaining system stability.

        CONTROL VARIABLES:
        - Error Rate: Failed requests / Total requests
        - Average Latency: Rolling average of request latencies
        - Current Concurrency: Current number of concurrent operations

        ADJUSTMENT STRATEGY:
        1. INCREASE concurrency when:
           - Error rate < healthy_error_rate (default: 1%)
           - Average latency < high_latency_ms (default: 1000ms)
           - Result: Multiply by increase_factor (default: 1.2 = 20% increase)

        2. DECREASE concurrency when:
           - Error rate > unhealthy_error_rate (default: 5%)
           - Average latency > high_latency_ms (default: 1000ms)
           - Result: Multiply by decrease_factor (default: 0.8 = 20% decrease)

        3. BOUNDS CHECKING:
           - Never go below min_concurrency (default: 1)
           - Never exceed max_concurrency (default: 50)

        RATE LIMIT HANDLING:
        - Immediate 50% reduction on 429 responses
        - Uses rate_limit_decrease factor (default: 0.5)

        FEEDBACK LOOP:
        - Adjustments happen every adjustment_interval seconds (default: 10s)
        - Uses rolling window of latency samples (max_latency_samples)
        - Prevents oscillation with adjustment cooldown

        Example:
            Start: 10 concurrent
            Conditions: 0.5% error rate, 200ms avg latency
            Action: Increase (healthy)
            Result: 10 * 1.2 = 12 concurrent

        Time Complexity: O(1) per adjustment
        Space Complexity: O(S) where S = max_latency_samples
        """
        # Skip if already adjusting
        if self._adjusting:
            return

        now = time.time()
        time_since_adjustment = now - self.metrics.last_adjustment_time

        if time_since_adjustment < self.adjustment_interval:
            return

        # Calculate error rate
        if self.metrics.total_requests > 0:
            error_rate = self.metrics.failed_requests / self.metrics.total_requests
        else:
            error_rate = 0.0

        # Check against configurable thresholds
        if (
            error_rate < self.config.healthy_error_rate
            and self.metrics.avg_latency_ms < self.config.high_latency_ms
        ):
            # System is healthy - try increasing concurrency
            self._adjusting = True
            asyncio.create_task(self._increase_concurrency_safe())
        elif (
            error_rate > self.config.unhealthy_error_rate
            or self.metrics.avg_latency_ms > self.config.high_latency_ms
        ):
            # System is struggling - decrease concurrency
            self._adjusting = True
            asyncio.create_task(self._decrease_concurrency_safe())

        self.metrics.last_adjustment_time = now

    async def _increase_concurrency(self) -> None:
        """
        Increase concurrency limit (cautiously).

        With manual counter, we just change the limit - no semaphore manipulation needed!
        Waiting tasks will automatically wake up when checking their condition.
        """
        async with self._condition:
            if self.current_concurrency >= self.max_concurrency:
                return

            old_concurrency = self.current_concurrency

            # Increase by configurable factor
            increase = max(1, int(self.current_concurrency * (self.config.increase_factor - 1.0)))
            new_concurrency = min(
                self.current_concurrency + increase,
                self.max_concurrency,
            )

            if new_concurrency > self.current_concurrency:
                self.current_concurrency = new_concurrency

                # Wake up waiting tasks - they'll check the new limit
                self._condition.notify(new_concurrency - old_concurrency)

                logger.info(
                    "Increased concurrency",
                    old=old_concurrency,
                    new=new_concurrency,
                    active_tasks=self._active_tasks,
                    error_rate=f"{self.metrics.failed_requests / max(self.metrics.total_requests, 1):.2%}",
                    avg_latency=f"{self.metrics.avg_latency_ms:.1f}ms",
                )

    async def _decrease_concurrency(self) -> None:
        """
        Decrease concurrency limit.

        With manual counter, we just change the limit - active tasks continue,
        but new tasks must wait. This is safe and doesn't break anything!
        """
        async with self._condition:
            if self.current_concurrency <= self.min_concurrency:
                return

            old_concurrency = self.current_concurrency

            # Decrease by configurable factor
            decrease = max(1, int(self.current_concurrency * (1.0 - self.config.decrease_factor)))
            new_concurrency = max(
                self.current_concurrency - decrease,
                self.min_concurrency,
            )

            if new_concurrency < self.current_concurrency:
                self.current_concurrency = new_concurrency

                logger.warning(
                    "Decreased concurrency",
                    old=old_concurrency,
                    new=new_concurrency,
                    active_tasks=self._active_tasks,
                    error_rate=f"{self.metrics.failed_requests / max(self.metrics.total_requests, 1):.2%}",
                    avg_latency=f"{self.metrics.avg_latency_ms:.1f}ms",
                    rate_limit_errors=self.metrics.rate_limit_errors,
                )

    async def _decrease_concurrency_rate_limit(self) -> None:
        """
        Decrease concurrency limit aggressively for rate limit errors.

        Uses the configurable rate_limit_decrease factor for more aggressive
        throttling when encountering rate limits.
        """
        async with self._condition:
            if self.current_concurrency <= self.min_concurrency:
                return

            old_concurrency = self.current_concurrency

            # Decrease by configurable rate limit factor (more aggressive)
            decrease = max(
                1, int(self.current_concurrency * (1.0 - self.config.rate_limit_decrease))
            )
            new_concurrency = max(
                self.current_concurrency - decrease,
                self.min_concurrency,
            )

            if new_concurrency < self.current_concurrency:
                self.current_concurrency = new_concurrency

                logger.warning(
                    "Decreased concurrency (rate limit)",
                    old=old_concurrency,
                    new=new_concurrency,
                    active_tasks=self._active_tasks,
                    rate_limit_factor=self.config.rate_limit_decrease,
                )

    async def _increase_concurrency_safe(self) -> None:
        """Wrapper for _increase_concurrency with adjustment flag management."""
        try:
            await self._increase_concurrency()
        finally:
            self._adjusting = False

    async def _decrease_concurrency_safe(self) -> None:
        """Wrapper for _decrease_concurrency with adjustment flag management."""
        try:
            await self._decrease_concurrency()
        finally:
            self._adjusting = False

    def get_metrics(self) -> dict[str, Any]:
        """
        Get current throttle metrics.

        Returns:
            Dictionary of metrics including active task count
        """
        return {
            "current_concurrency": self.current_concurrency,
            "active_tasks": self._active_tasks,  # New: actual active count
            "total_requests": self.metrics.total_requests,
            "successful_requests": self.metrics.successful_requests,
            "failed_requests": self.metrics.failed_requests,
            "rate_limit_errors": self.metrics.rate_limit_errors,
            "error_rate": (
                self.metrics.failed_requests / self.metrics.total_requests
                if self.metrics.total_requests > 0
                else 0.0
            ),
            "avg_latency_ms": self.metrics.avg_latency_ms,
        }

    def reset_metrics(self) -> None:
        """Reset all metrics (but not concurrency settings)."""
        self.metrics = ThrottleMetrics()
        self._latencies.clear()
        logger.debug("Throttle metrics reset")
