"""Tests for KeyedLock concurrency utilities.

This module tests the KeyedLock implementation which prevents race conditions
during concurrent resource operations.
"""

import asyncio

import pytest

from importer.utils.locking import KeyedLock


@pytest.mark.asyncio
async def test_keyed_lock_basic_acquire_release():
    """Test basic lock acquire and release."""
    lock = KeyedLock()
    key = "test_resource"

    async with lock.acquire(key):
        # Successfully acquired
        pass

    # Lock should be released after context exit
    # Acquiring again should succeed immediately
    async with lock.acquire(key):
        pass


@pytest.mark.asyncio
async def test_keyed_lock_prevents_concurrent_access_same_key():
    """Verify that same key blocks concurrent access."""
    lock = KeyedLock()
    key = "same_resource"
    execution_order = []

    async def task1():
        async with lock.acquire(key):
            execution_order.append("task1_start")
            await asyncio.sleep(0.1)  # Hold lock for 100ms
            execution_order.append("task1_end")

    async def task2():
        await asyncio.sleep(0.01)  # Ensure task1 acquires first
        async with lock.acquire(key):
            execution_order.append("task2_start")
            await asyncio.sleep(0.05)
            execution_order.append("task2_end")

    # Run both tasks concurrently
    await asyncio.gather(task1(), task2())

    # Task2 should wait for task1 to complete
    assert execution_order == ["task1_start", "task1_end", "task2_start", "task2_end"]


@pytest.mark.asyncio
async def test_keyed_lock_allows_different_keys_concurrent():
    """Verify that different keys can execute concurrently."""
    lock = KeyedLock()
    execution_order = []

    async def task1():
        async with lock.acquire("resource_a"):
            execution_order.append("task1_start")
            await asyncio.sleep(0.1)
            execution_order.append("task1_end")

    async def task2():
        async with lock.acquire("resource_b"):
            execution_order.append("task2_start")
            await asyncio.sleep(0.05)
            execution_order.append("task2_end")

    # Run both tasks concurrently
    await asyncio.gather(task1(), task2())

    # Both tasks should execute concurrently
    # task2 should finish before task1 (it sleeps for less time)
    assert execution_order == ["task1_start", "task2_start", "task2_end", "task1_end"]


@pytest.mark.asyncio
async def test_keyed_lock_release_on_exception():
    """Ensure locks release even when exceptions occur."""
    lock = KeyedLock()
    key = "error_resource"

    # First task raises exception
    with pytest.raises(ValueError):
        async with lock.acquire(key):
            raise ValueError("Test error")

    # Lock should be released; second task should acquire successfully
    acquired = False
    async with lock.acquire(key):
        acquired = True

    assert acquired


@pytest.mark.asyncio
async def test_keyed_lock_multiple_concurrent_waiters():
    """Test multiple tasks waiting on same key."""
    lock = KeyedLock()
    key = "popular_resource"
    execution_order = []

    async def task(task_id: int):
        async with lock.acquire(key):
            execution_order.append(f"task{task_id}_start")
            await asyncio.sleep(0.02)
            execution_order.append(f"task{task_id}_end")

    # Launch 5 tasks simultaneously
    await asyncio.gather(*(task(i) for i in range(5)))

    # All tasks should complete
    assert len(execution_order) == 10

    # Each task should complete before next starts
    for i in range(5):
        start_idx = execution_order.index(f"task{i}_start")
        end_idx = execution_order.index(f"task{i}_end")
        assert end_idx == start_idx + 1, "Tasks should execute sequentially"


@pytest.mark.asyncio
async def test_keyed_lock_call_shortcut():
    """Test that __call__ shortcut works like acquire."""
    lock = KeyedLock()
    key = "shortcut_resource"
    executed = False

    # Use __call__ syntax
    async with lock(key):
        executed = True

    assert executed


@pytest.mark.asyncio
async def test_keyed_lock_different_key_types():
    """Test that different hashable types work as keys."""
    lock = KeyedLock()
    execution_order = []

    async def string_task():
        async with lock.acquire("string_key"):
            execution_order.append("string")
            await asyncio.sleep(0.05)

    async def int_task():
        async with lock.acquire(12345):
            execution_order.append("int")
            await asyncio.sleep(0.05)

    async def tuple_task():
        async with lock.acquire(("tuple", "key")):
            execution_order.append("tuple")
            await asyncio.sleep(0.05)

    # All should execute concurrently (different keys)
    await asyncio.gather(string_task(), int_task(), tuple_task())

    # All should complete
    assert set(execution_order) == {"string", "int", "tuple"}


@pytest.mark.asyncio
async def test_keyed_lock_high_concurrency():
    """Test lock behavior under high concurrency."""
    lock = KeyedLock()
    counter = {"value": 0}

    async def increment_task(key: str):
        async with lock.acquire(key):
            # Critical section - increment counter
            current = counter["value"]
            await asyncio.sleep(0.001)  # Simulate some work
            counter["value"] = current + 1

    # Run 100 tasks on same key
    await asyncio.gather(*(increment_task("counter") for _ in range(100)))

    # All increments should be serialized correctly
    assert counter["value"] == 100


@pytest.mark.asyncio
async def test_keyed_lock_reentrancy_not_supported():
    """Test that reentrancy (same task acquiring twice) will deadlock.

    Note: This tests expected behavior - asyncio.Lock is not reentrant.
    This test uses a timeout to detect deadlock.
    """
    lock = KeyedLock()
    key = "reentrant_test"

    async def nested_acquire():
        async with lock.acquire(key):
            # Try to acquire same lock again
            try:
                async with asyncio.timeout(0.1):
                    async with lock.acquire(key):
                        pass
            except TimeoutError:
                return "deadlock_detected"
        return "no_deadlock"

    result = await nested_acquire()
    assert result == "deadlock_detected", "Reentrant lock should deadlock"


@pytest.mark.asyncio
async def test_keyed_lock_memory_persistence():
    """Test that locks persist in memory (never deleted)."""
    lock = KeyedLock()
    key = "persistent_key"

    # Acquire and release
    async with lock.acquire(key):
        pass

    # Lock should still exist in internal dict
    assert key in lock._locks


@pytest.mark.asyncio
async def test_keyed_lock_stress_test():
    """Stress test with many keys and concurrent operations."""
    lock = KeyedLock()
    results = {}
    num_keys = 20
    operations_per_key = 10

    async def operation(key_id: int, op_id: int):
        key = f"key_{key_id}"
        async with lock.acquire(key):
            if key not in results:
                results[key] = []
            results[key].append(op_id)
            await asyncio.sleep(0.001)

    # Create tasks for all keys and operations
    tasks = [
        operation(key_id, op_id)
        for key_id in range(num_keys)
        for op_id in range(operations_per_key)
    ]

    # Run all concurrently
    await asyncio.gather(*tasks)

    # Verify all operations completed
    assert len(results) == num_keys
    for key, ops in results.items():
        assert len(ops) == operations_per_key


@pytest.mark.asyncio
async def test_keyed_lock_cancellation_releases_lock():
    """Test that cancelled tasks release their locks."""
    lock = KeyedLock()
    key = "cancellation_test"
    holder_started = asyncio.Event()
    holder_cancelled = False

    async def lock_holder():
        nonlocal holder_cancelled
        try:
            async with lock.acquire(key):
                holder_started.set()
                await asyncio.sleep(10)  # Hold lock for a long time
        except asyncio.CancelledError:
            holder_cancelled = True
            raise

    async def lock_acquirer():
        # Wait for holder to acquire lock
        await holder_started.wait()
        await asyncio.sleep(0.1)

        # Should be able to acquire after cancellation
        async with lock.acquire(key):
            return "acquired"

    # Start lock holder
    holder_task = asyncio.create_task(lock_holder())

    # Wait for holder to start
    await holder_started.wait()

    # Cancel the holder
    holder_task.cancel()
    try:
        await holder_task
    except asyncio.CancelledError:
        pass

    # Now try to acquire - should succeed
    result = await lock_acquirer()
    assert result == "acquired"
    assert holder_cancelled
