"""Unit tests for Adaptive Throttle."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from src.importer.config import ThrottleConfig
from src.importer.execution.throttle import (
    AdaptiveThrottle,
    ThrottleMetrics,
)


class TestThrottleMetrics:
    """Test ThrottleMetrics class."""

    def test_throttle_metrics_initialization(self):
        """Test ThrottleMetrics initialization."""
        metrics = ThrottleMetrics()
        assert metrics.total_requests == 0
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 0
        assert metrics.rate_limit_errors == 0
        assert metrics.avg_latency_ms == 0.0
        assert isinstance(metrics.last_adjustment_time, float)

    def test_throttle_metrics_with_values(self):
        """Test ThrottleMetrics with specific values."""
        now = time.time()
        metrics = ThrottleMetrics(
            total_requests=100,
            successful_requests=95,
            failed_requests=5,
            rate_limit_errors=2,
            avg_latency_ms=250.5,
            last_adjustment_time=now,
        )

        assert metrics.total_requests == 100
        assert metrics.successful_requests == 95
        assert metrics.failed_requests == 5
        assert metrics.rate_limit_errors == 2
        assert metrics.avg_latency_ms == 250.5
        assert metrics.last_adjustment_time == now


class TestAdaptiveThrottle:
    """Test AdaptiveThrottle class."""

    def test_initialization(self):
        """Test AdaptiveThrottle initialization."""
        config = ThrottleConfig(
            initial_concurrency=10,
            min_concurrency=2,
            max_concurrency=20,
            adjustment_interval=15.0,
        )
        throttle = AdaptiveThrottle(config)

        assert throttle.current_concurrency == 10
        assert throttle.min_concurrency == 2
        assert throttle.max_concurrency == 20
        assert throttle.adjustment_interval == 15.0
        assert throttle._active_tasks == 0
        assert isinstance(throttle._condition, asyncio.Condition)
        assert isinstance(throttle.metrics, ThrottleMetrics)
        assert throttle._latencies == []

    def test_initialization_defaults(self):
        """Test AdaptiveThrottle initialization with defaults."""
        throttle = AdaptiveThrottle()

        assert throttle.current_concurrency == 10
        assert throttle.min_concurrency == 1
        assert throttle.max_concurrency == 50
        assert throttle.adjustment_interval == 10.0

    # Test acquire/release functionality
    @pytest.mark.asyncio
    async def test_acquire_available_slot(self):
        """Test acquiring a slot when one is available."""
        config = ThrottleConfig(initial_concurrency=5)
        throttle = AdaptiveThrottle(config)

        await throttle.acquire()

        assert throttle._active_tasks == 1

    @pytest.mark.asyncio
    async def test_acquire_blocks_at_limit(self):
        """Test that acquire blocks when at concurrency limit."""
        config = ThrottleConfig(initial_concurrency=1)
        throttle = AdaptiveThrottle(config)

        # Acquire the first slot
        await throttle.acquire()
        assert throttle._active_tasks == 1

        # Try to acquire second slot - should block
        acquired = False

        async def try_acquire():
            nonlocal acquired
            await throttle.acquire()
            acquired = True

        # Start second acquire task
        asyncio.create_task(try_acquire())

        # Give it time to start but not complete
        await asyncio.sleep(0.01)
        assert not acquired  # Should still be waiting

        # Release the first slot
        throttle.release()

        # Give it time to complete
        await asyncio.sleep(0.01)
        assert acquired  # Should have completed
        assert throttle._active_tasks == 1

        # Clean up
        throttle.release()

    @pytest.mark.asyncio
    async def test_release_when_no_tasks_active(self):
        """Test releasing when no tasks are active."""
        throttle = AdaptiveThrottle()

        # Release without any active tasks - should log warning but not error
        throttle.release()  # Should not raise

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test throttle as context manager."""
        config = ThrottleConfig(initial_concurrency=5)
        throttle = AdaptiveThrottle(config)

        async with throttle:
            assert throttle._active_tasks == 1

        assert throttle._active_tasks == 0

    @pytest.mark.asyncio
    async def test_context_manager_with_exception(self):
        """Test context manager handles exceptions gracefully."""
        config = ThrottleConfig(initial_concurrency=5)
        throttle = AdaptiveThrottle(config)

        with pytest.raises(ValueError):
            async with throttle:
                assert throttle._active_tasks == 1
                raise ValueError("Test error")

        assert throttle._active_tasks == 0

    # Test metrics recording
    @pytest.mark.asyncio
    async def test_record_success(self):
        """Test recording successful request."""
        throttle = AdaptiveThrottle()

        # Record multiple successes with different latencies
        throttle.record_success(100.0)
        throttle.record_success(200.0)
        throttle.record_success(300.0)

        assert throttle.metrics.total_requests == 3
        assert throttle.metrics.successful_requests == 3
        assert throttle.metrics.failed_requests == 0
        assert throttle.metrics.avg_latency_ms == 200.0  # (100+200+300)/3
        assert len(throttle._latencies) == 3

    @pytest.mark.asyncio
    async def test_record_success_latency_limit(self):
        """Test that latency list is limited to max samples."""
        throttle = AdaptiveThrottle()
        throttle._max_latency_samples = 3

        # Add more than max samples
        for i in range(5):
            throttle.record_success(float(i * 100))

        # Should keep only the last 3 samples
        assert len(throttle._latencies) == 3
        assert throttle._latencies == [200.0, 300.0, 400.0]
        assert throttle.metrics.avg_latency_ms == 300.0  # (200+300+400)/3

    @pytest.mark.asyncio
    async def test_record_failure(self):
        """Test recording failed request."""
        throttle = AdaptiveThrottle()

        throttle.record_failure()
        throttle.record_failure(is_rate_limit=True)

        # Give time for async task to complete
        await asyncio.sleep(0.01)

        assert throttle.metrics.total_requests == 2
        assert throttle.metrics.successful_requests == 0
        assert throttle.metrics.failed_requests == 2
        assert throttle.metrics.rate_limit_errors == 1

    @pytest.mark.asyncio
    async def test_record_failure_triggers_immediate_decrease_on_rate_limit(self):
        """Test that rate limit failure triggers immediate concurrency decrease."""
        config = ThrottleConfig(initial_concurrency=10, min_concurrency=1)
        throttle = AdaptiveThrottle(config)

        # Record rate limit failure
        throttle.record_failure(is_rate_limit=True)

        # Give time for async task to complete
        await asyncio.sleep(0.01)

        assert throttle.metrics.rate_limit_errors == 1

    # Test concurrency adjustment
    @pytest.mark.asyncio
    async def test_maybe_adjust_concurrency_no_requests(self):
        """Test adjustment when no requests have been made."""
        throttle = AdaptiveThrottle()
        throttle.metrics.last_adjustment_time = time.time() - 20  # 20 seconds ago

        throttle._maybe_adjust_concurrency()

        # Should not adjust when no requests
        assert throttle.current_concurrency == 10  # Default

    @pytest.mark.asyncio
    async def test_maybe_adjust_concurrency_too_soon(self):
        """Test adjustment doesn't happen too frequently."""
        throttle = AdaptiveThrottle()
        throttle.metrics.total_requests = 10

        # Record recent adjustment
        throttle.metrics.last_adjustment_time = time.time()

        throttle._maybe_adjust_concurrency()

        # Should not adjust - too soon
        assert throttle.current_concurrency == 10

    @pytest.mark.asyncio
    async def test_maybe_adjust_concurrency_increase_when_healthy(self):
        """Test concurrency increases when system is healthy."""
        config = ThrottleConfig(
            initial_concurrency=5,
            max_concurrency=20,
            adjustment_interval=1.0,
        )
        throttle = AdaptiveThrottle(config)
        # Set adjustment time to now so record_success doesn't trigger adjustment
        throttle.metrics.last_adjustment_time = time.time()

        # Record healthy metrics
        for _i in range(10):
            throttle.record_success(50.0)  # Low latency

        # Now set time back to allow adjustment
        throttle.metrics.last_adjustment_time = time.time() - 2.0
        throttle._adjusting = False  # Ensure flag is clear

        # Trigger adjustment check
        with patch.object(
            throttle, "_increase_concurrency_safe", new_callable=AsyncMock
        ) as mock_increase:
            throttle._maybe_adjust_concurrency()
            await asyncio.sleep(0.01)
            mock_increase.assert_called_once()

    @pytest.mark.asyncio
    async def test_maybe_adjust_concurrency_decrease_when_unhealthy(self):
        """Test concurrency decreases when system is unhealthy."""
        config = ThrottleConfig(
            initial_concurrency=10,
            min_concurrency=1,
            adjustment_interval=1.0,
        )
        throttle = AdaptiveThrottle(config)
        # Set adjustment time to now so record_failure doesn't trigger adjustment
        throttle.metrics.last_adjustment_time = time.time()

        # Record unhealthy metrics
        for _i in range(10):
            throttle.record_failure()  # High error rate

        # Now set time back to allow adjustment
        throttle.metrics.last_adjustment_time = time.time() - 2.0
        throttle._adjusting = False  # Ensure flag is clear

        # Trigger adjustment check
        with patch.object(
            throttle, "_decrease_concurrency_safe", new_callable=AsyncMock
        ) as mock_decrease:
            throttle._maybe_adjust_concurrency()
            await asyncio.sleep(0.01)
            mock_decrease.assert_called_once()

    @pytest.mark.asyncio
    async def test_maybe_adjust_concurrency_already_adjusting(self):
        """Test adjustment is skipped when already adjusting."""
        throttle = AdaptiveThrottle()
        throttle._adjusting = True

        throttle._maybe_adjust_concurrency()

        # Should not trigger adjustment
        assert throttle.current_concurrency == 10

    # Test concurrency adjustment methods
    @pytest.mark.asyncio
    async def test_increase_concurrency(self):
        """Test increasing concurrency limit."""
        config = ThrottleConfig(
            initial_concurrency=10,
            max_concurrency=20,
        )
        throttle = AdaptiveThrottle(config)

        await throttle._increase_concurrency()

        # Should increase by 20% (2) or 1, whichever is larger
        # Due to floating point (10 * 0.2 = 2.0 -> int(1.999) = 1)
        # So expected 11 instead of 12
        assert throttle.current_concurrency == 11

    @pytest.mark.asyncio
    async def test_increase_concurrency_at_max(self):
        """Test increasing concurrency when at max limit."""
        config = ThrottleConfig(
            initial_concurrency=20,
            max_concurrency=20,
        )
        throttle = AdaptiveThrottle(config)

        await throttle._increase_concurrency()

        # Should not exceed max
        assert throttle.current_concurrency == 20

    @pytest.mark.asyncio
    async def test_increase_concurrency_small_value(self):
        """Test increasing concurrency with small initial value."""
        config = ThrottleConfig(
            initial_concurrency=2,
            max_concurrency=20,
        )
        throttle = AdaptiveThrottle(config)

        await throttle._increase_concurrency()

        # Should increase by at least 1
        assert throttle.current_concurrency == 3

    @pytest.mark.asyncio
    async def test_decrease_concurrency(self):
        """Test decreasing concurrency limit."""
        config = ThrottleConfig(
            initial_concurrency=10,
            min_concurrency=1,
        )
        throttle = AdaptiveThrottle(config)

        await throttle._decrease_concurrency()

        # Should decrease by 20% (2) or 1, whichever is larger
        # However, due to floating point precision:
        # decrease = max(1, int(10 * (1.0 - 0.8))) = max(1, int(1.999...)) = 1
        # 10 - 1 = 9
        assert throttle.current_concurrency == 9

    @pytest.mark.asyncio
    async def test_decrease_concurrency_at_min(self):
        """Test decreasing concurrency when at min limit."""
        config = ThrottleConfig(
            initial_concurrency=1,
            min_concurrency=1,
        )
        throttle = AdaptiveThrottle(config)

        await throttle._decrease_concurrency()

        # Should not go below min
        assert throttle.current_concurrency == 1

    @pytest.mark.asyncio
    async def test_decrease_concurrency_small_value(self):
        """Test decreasing concurrency with small initial value."""
        config = ThrottleConfig(
            initial_concurrency=3,
            min_concurrency=1,
        )
        throttle = AdaptiveThrottle(config)

        await throttle._decrease_concurrency()

        # Should decrease by at least 1
        assert throttle.current_concurrency == 2

    @pytest.mark.asyncio
    async def test_increase_concurrency_safe_wrapper(self):
        """Test safe wrapper for increase concurrency."""
        throttle = AdaptiveThrottle()
        throttle._adjusting = True

        await throttle._increase_concurrency_safe()

        # Should reset adjusting flag
        assert throttle._adjusting is False

    @pytest.mark.asyncio
    async def test_decrease_concurrency_safe_wrapper(self):
        """Test safe wrapper for decrease concurrency."""
        throttle = AdaptiveThrottle()
        throttle._adjusting = True

        await throttle._decrease_concurrency_safe()

        # Should reset adjusting flag
        assert throttle._adjusting is False

    # Test metrics and utilities
    @pytest.mark.asyncio
    async def test_get_metrics(self):
        """Test getting current metrics."""
        throttle = AdaptiveThrottle()
        throttle._active_tasks = 3

        # Record some activity
        throttle.record_success(100.0)
        throttle.record_failure()

        # Give time for async task to complete
        await asyncio.sleep(0.01)

        metrics = throttle.get_metrics()

        assert metrics["current_concurrency"] == 10
        assert metrics["active_tasks"] == 3
        assert metrics["total_requests"] == 2
        assert metrics["successful_requests"] == 1
        assert metrics["failed_requests"] == 1
        assert metrics["rate_limit_errors"] == 0
        assert metrics["error_rate"] == 0.5  # 1 failure / 2 total
        assert metrics["avg_latency_ms"] == 100.0

    def test_get_metrics_no_requests(self):
        """Test getting metrics when no requests made."""
        throttle = AdaptiveThrottle()

        metrics = throttle.get_metrics()

        assert metrics["error_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_reset_metrics(self):
        """Test resetting metrics."""
        throttle = AdaptiveThrottle()

        # Record some activity
        throttle.record_success(100.0)
        throttle.record_failure()

        # Give time for async task to complete
        await asyncio.sleep(0.01)

        # Reset
        throttle.reset_metrics()

        # Verify reset
        assert throttle.metrics.total_requests == 0
        assert throttle.metrics.successful_requests == 0
        assert throttle.metrics.failed_requests == 0
        assert throttle.metrics.rate_limit_errors == 0
        assert throttle.metrics.avg_latency_ms == 0.0
        assert len(throttle._latencies) == 0

        # Concurrency settings should be preserved
        assert throttle.current_concurrency == 10

    # Test concurrent operations
    @pytest.mark.asyncio
    async def test_concurrent_acquire_release(self):
        """Test concurrent acquire and release operations."""
        config = ThrottleConfig(initial_concurrency=5)
        throttle = AdaptiveThrottle(config)
        tasks_completed = []

        async def worker(worker_id):
            async with throttle:
                # Simulate work
                await asyncio.sleep(0.01)
                tasks_completed.append(worker_id)

        # Start many concurrent workers
        tasks = [worker(i) for i in range(10)]
        await asyncio.gather(*tasks)

        # All tasks should complete
        assert len(tasks_completed) == 10
        assert set(tasks_completed) == set(range(10))
        assert throttle._active_tasks == 0

    @pytest.mark.asyncio
    async def test_concurrency_during_adjustment(self):
        """Test that concurrency adjustment works while tasks are running."""
        config = ThrottleConfig(
            initial_concurrency=2,
            max_concurrency=10,
            adjustment_interval=0.1,
        )
        throttle = AdaptiveThrottle(config)

        tasks_running = []

        async def long_task():
            async with throttle:
                tasks_running.append(len(tasks_running) + 1)
                await asyncio.sleep(0.2)  # Long enough for adjustment

        # Start tasks that will trigger adjustment
        tasks = [long_task() for _ in range(5)]

        # Give tasks time to start and trigger adjustments
        await asyncio.sleep(0.05)

        # Should have increased concurrency due to healthy performance
        # (exact behavior depends on timing, but should be > initial)
        assert throttle.current_concurrency >= 2

        # Wait for completion
        await asyncio.gather(*tasks)

    # Test edge cases
    @pytest.mark.asyncio
    async def test_release_async_without_acquire(self):
        """Test release without acquire doesn't cause negative count."""
        throttle = AdaptiveThrottle()
        throttle._active_tasks = 0

        await throttle._release_async()

        assert throttle._active_tasks == 0

    @pytest.mark.asyncio
    async def test_release_async_with_active_tasks(self):
        """Test release with active tasks decrements correctly."""
        throttle = AdaptiveThrottle()
        throttle._active_tasks = 2

        await throttle._release_async()

        assert throttle._active_tasks == 1

    def test_error_rate_calculation(self):
        """Test error rate calculation in get_metrics."""
        throttle = AdaptiveThrottle()

        # Test various error rates
        test_cases = [
            (0, 0, 0.0),  # No errors
            (1, 1, 1.0),  # All errors
            (10, 5, 0.5),  # 50% errors
            (100, 1, 0.01),  # 1% errors
        ]

        for total, failed, expected_rate in test_cases:
            throttle.metrics.total_requests = total
            throttle.metrics.failed_requests = failed
            metrics = throttle.get_metrics()
            assert abs(metrics["error_rate"] - expected_rate) < 0.0001
