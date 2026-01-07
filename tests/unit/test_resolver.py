"""Unit tests for Path Resolver."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.importer.bam.client import BAMClient
from src.importer.core.resolver import CacheStats, Resolver
from src.importer.utils.exceptions import PendingCreateError, ResourceNotFoundError


class TestCacheStats:
    """Test CacheStats class."""

    def test_cache_stats_initialization(self):
        """Test CacheStats initialization."""
        stats = CacheStats()
        assert stats.cache_hits == 0
        assert stats.cache_misses == 0
        assert stats.pending_hits == 0
        assert stats.total_queries == 0
        assert stats.hit_rate() == 0.0

    def test_cache_hit(self):
        """Test recording cache hit."""
        stats = CacheStats()
        stats.cache_hit()
        assert stats.cache_hits == 1
        assert stats.total_queries == 1
        assert stats.hit_rate() == 1.0

    def test_cache_miss(self):
        """Test recording cache miss."""
        stats = CacheStats()
        stats.cache_miss()
        assert stats.cache_misses == 1
        assert stats.total_queries == 1
        assert stats.hit_rate() == 0.0

    def test_pending_hit(self):
        """Test recording pending hit."""
        stats = CacheStats()
        stats.pending_hit()
        assert stats.pending_hits == 1
        assert stats.total_queries == 1
        assert stats.hit_rate() == 1.0

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        stats = CacheStats()
        stats.cache_hit()
        stats.cache_miss()
        stats.pending_hit()
        # 1 cache hit + 1 pending hit = 2 hits out of 3 total queries
        assert stats.hit_rate() == 2.0 / 3.0

    def test_hit_rate_no_queries(self):
        """Test hit rate with no queries."""
        stats = CacheStats()
        assert stats.hit_rate() == 0.0


class TestResolver:
    """Test Resolver class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = AsyncMock(spec=BAMClient)
        self.temp_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.temp_dir)
        self.resolver = Resolver(self.mock_client, self.cache_dir)

    def teardown_method(self):
        """Clean up test fixtures."""
        self.resolver.cache.close()
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_initialization(self):
        """Test Resolver initialization."""
        assert self.resolver.client == self.mock_client
        assert self.resolver.cache_dir == self.cache_dir
        assert self.cache_dir.exists()
        assert len(self.resolver.pending_creates) == 0
        assert isinstance(self.resolver.stats, CacheStats)

    # Test pending create management
    @pytest.mark.asyncio
    async def test_register_pending_create(self):
        """Test registering a pending create."""
        path = "/config/Test/10.0.0.0/8"
        row_id = "row1"
        resource_type = "ip4_block"

        await self.resolver.register_pending_create(path, row_id, resource_type)

        assert path in self.resolver.pending_creates
        assert self.resolver.pending_creates[path] == (row_id, resource_type)

    @pytest.mark.asyncio
    async def test_confirm_create(self):
        """Test confirming a create operation."""
        path = "/config/Test/10.0.0.0/8"
        row_id = "row1"
        resource_type = "ip4_block"
        bam_id = 123

        # First register pending create
        await self.resolver.register_pending_create(path, row_id, resource_type)

        # Then confirm it
        await self.resolver.confirm_create(path, bam_id)

        # Verify it's removed from pending and added to cache
        assert path not in self.resolver.pending_creates

        cache_key = self.resolver._cache_key(path, resource_type)
        cached_id = self.resolver.cache.get(cache_key)
        assert cached_id == bam_id

    @pytest.mark.asyncio
    async def test_confirm_create_unknown_pending(self):
        """Test confirming a create for unknown pending path."""
        path = "/config/Test/10.0.0.0/8"
        bam_id = 123

        # Confirm without registering
        await self.resolver.confirm_create(path, bam_id)

        # Should not raise error, just log warning
        assert path not in self.resolver.pending_creates

    @pytest.mark.asyncio
    async def test_cancel_create(self):
        """Test cancelling a pending create."""
        path = "/config/Test/10.0.0.0/8"
        row_id = "row1"
        resource_type = "ip4_block"

        # First register pending create
        await self.resolver.register_pending_create(path, row_id, resource_type)

        # Then cancel it
        await self.resolver.cancel_create(path, "Test failure")

        # Verify it's removed from pending
        assert path not in self.resolver.pending_creates

    @pytest.mark.asyncio
    async def test_cancel_create_unknown_pending(self):
        """Test cancelling a create for unknown pending path."""
        path = "/config/Test/10.0.0.0/8"

        # Cancel without registering
        await self.resolver.cancel_create(path, "Test failure")

        # Should not raise error

    @pytest.mark.asyncio
    async def test_clear_pending(self):
        """Test clearing all pending creates."""
        # Register multiple pending creates
        await self.resolver.register_pending_create("/path1", "row1", "type1")
        await self.resolver.register_pending_create("/path2", "row2", "type2")

        # Clear all
        await self.resolver.clear_pending()

        # Verify all are cleared
        assert len(self.resolver.pending_creates) == 0

    # Test path resolution
    @pytest.mark.asyncio
    async def test_resolve_pending_create_raises_error(self):
        """Test that resolving pending create raises error."""
        path = "/config/Test/10.0.0.0/8"
        row_id = "row1"
        resource_type = "ip4_block"

        # Register pending create
        await self.resolver.register_pending_create(path, row_id, resource_type)

        # Try to resolve - should raise error
        with pytest.raises(PendingCreateError) as exc_info:
            await self.resolver.resolve(path, resource_type)

        assert path in str(exc_info.value)
        assert row_id in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_resolve_cache_hit(self):
        """Test resolving path from cache."""
        path = "/config/Test/10.0.0.0/8"
        resource_type = "ip4_block"
        bam_id = 123

        # Pre-populate cache
        cache_key = self.resolver._cache_key(path, resource_type)
        self.resolver.cache.set(cache_key, bam_id)

        # Resolve
        result = await self.resolver.resolve(path, resource_type)

        assert result == bam_id
        assert self.resolver.stats.cache_hits == 1
        assert self.resolver.stats.total_queries == 1

    @pytest.mark.asyncio
    async def test_resolve_cache_miss_queries_bam(self):
        """Test resolving path queries BAM on cache miss."""
        path = "/config/Test/10.0.0.0/8"
        resource_type = "ip4_block"
        bam_id = 123

        # Mock BAM query to succeed
        with patch.object(self.resolver, "_query_bam", return_value=bam_id):
            result = await self.resolver.resolve(path, resource_type)

        assert result == bam_id
        assert self.resolver.stats.cache_misses == 1
        assert self.resolver.stats.total_queries == 1

        # Verify it's cached
        cache_key = self.resolver._cache_key(path, resource_type)
        cached_id = self.resolver.cache.get(cache_key)
        assert cached_id == bam_id

    @pytest.mark.asyncio
    async def test_resolve_bypass_cache(self):
        """Test bypassing cache forces BAM query."""
        path = "/config/Test/10.0.0.0/8"
        resource_type = "ip4_block"
        cached_id = 123
        query_id = 456

        # Pre-populate cache with different value
        cache_key = self.resolver._cache_key(path, resource_type)
        self.resolver.cache.set(cache_key, cached_id)

        # Mock BAM query to return different value
        with patch.object(self.resolver, "_query_bam", return_value=query_id):
            result = await self.resolver.resolve(path, resource_type, bypass_cache=True)

        # Should get query result, not cached result
        assert result == query_id
        assert result != cached_id

    @pytest.mark.asyncio
    async def test_resolve_resource_not_found(self):
        """Test resolving non-existent resource raises error."""
        path = "/config/Test/nonexistent"
        resource_type = "ip4_block"

        # Mock BAM query to raise error
        with patch.object(
            self.resolver, "_query_bam", side_effect=ResourceNotFoundError("ip4_block", path)
        ):
            with pytest.raises(ResourceNotFoundError):
                await self.resolver.resolve(path, resource_type)

        assert self.resolver.stats.cache_misses == 1

    # Test prefetch functionality
    @pytest.mark.asyncio
    async def test_prefetch_hierarchy(self):
        """Test prefetching hierarchy."""
        config_names = ["Config1", "Config2"]
        mock_config = {"id": 123, "name": "Config1"}

        self.mock_client.get_configuration_by_name.return_value = mock_config

        await self.resolver.prefetch_hierarchy(config_names)

        # Should have called get_configuration_by_name for each config
        assert self.mock_client.get_configuration_by_name.call_count == 2
        assert self.resolver._prefetch_complete is True

        # Verify cache was populated
        cache_key = self.resolver._cache_key("/configurations/Config1", "unknown")
        cached_id = self.resolver.cache.get(cache_key)
        assert cached_id == 123

    @pytest.mark.asyncio
    async def test_prefetch_hierarchy_with_views(self):
        """Test prefetching hierarchy with views."""
        config_names = ["Config1"]
        view_names = ["View1"]
        mock_config = {"id": 123, "name": "Config1"}

        self.mock_client.get_configuration_by_name.return_value = mock_config

        await self.resolver.prefetch_hierarchy(config_names, view_names)

        assert self.mock_client.get_configuration_by_name.call_count == 1
        assert self.resolver._prefetch_complete is True

    @pytest.mark.asyncio
    async def test_resolve_warning_no_prefetch(self):
        """Test warning when many queries without prefetch."""
        path = "/config/Test/resource"
        resource_type = "ip4_block"

        # Mock BAM query
        with patch.object(self.resolver, "_query_bam", return_value=123):
            # Make many queries to trigger warning (threshold is 100)
            for i in range(101):
                await self.resolver.resolve(f"{path}{i}", resource_type)

        # Should have logged warning about no prefetch
        # Note: In real test, you'd capture logs and verify warning

    # Test cache management
    def test_cache_key_generation(self):
        """Test cache key generation with normalization."""
        path = "/config/Test/10.0.0.0/8"
        resource_type = "ip4_block"
        # Cache keys should be normalized (ip4_block -> Block)
        expected_key = "Block:/config/Test/10.0.0.0/8"

        key = self.resolver._cache_key(path, resource_type)
        assert key == expected_key

        # Test that different type variations normalize to same key
        key_variant1 = self.resolver._cache_key(path, "block")
        key_variant2 = self.resolver._cache_key(path, "ip4_block")
        assert key_variant1 == key_variant2 == expected_key

    def test_cache_entity(self):
        """Test caching entity."""
        path = "/config/Test/10.0.0.0/8"
        bam_id = 123
        resource_type = "ip4_block"

        self.resolver._cache_entity(path, bam_id, resource_type)

        cache_key = self.resolver._cache_key(path, resource_type)
        cached_id = self.resolver.cache.get(cache_key)
        assert cached_id == bam_id

    @pytest.mark.asyncio
    async def test_invalidate_cache(self):
        """Test cache invalidation."""
        path = "/config/Test/10.0.0.0/8"
        resource_type = "ip4_block"
        bam_id = 123

        # First cache entity
        self.resolver._cache_entity(path, bam_id, resource_type)

        # Verify it's cached
        cache_key = self.resolver._cache_key(path, resource_type)
        assert self.resolver.cache.get(cache_key) == bam_id

        # Invalidate
        await self.resolver.invalidate(path, resource_type)

        # Verify it's gone
        assert self.resolver.cache.get(cache_key) is None

    # Test statistics
    def test_get_stats(self):
        """Test getting resolver statistics."""
        stats = self.resolver.get_stats()
        assert isinstance(stats, CacheStats)
        assert stats == self.resolver.stats

    # Test BAM query (placeholder)
    @pytest.mark.asyncio
    async def test_query_bam_invalid_path(self):
        """Test BAM query with invalid path format."""
        path = "/config/InvalidConfig/10.0.0.0/8"  # Non-existent config
        resource_type = "ip4_block"

        # Mock client to raise error for non-existent config
        from src.importer.utils.exceptions import ResourceNotFoundError

        self.mock_client.get_configuration_by_name.side_effect = ResourceNotFoundError(
            "Configuration", "InvalidConfig"
        )

        with pytest.raises(ResourceNotFoundError):
            await self.resolver._query_bam(path, resource_type)

    # Test thread safety
    @pytest.mark.asyncio
    async def test_concurrent_pending_operations(self):
        """Test concurrent pending operations are thread-safe."""
        path = "/config/Test/resource"
        row_id = "row1"
        resource_type = "ip4_block"
        bam_id = 123

        # Run concurrent operations
        async def register_and_confirm():
            await self.resolver.register_pending_create(path, row_id, resource_type)
            await asyncio.sleep(0.01)  # Small delay
            await self.resolver.confirm_create(path, bam_id)

        # Run multiple concurrent operations
        tasks = [register_and_confirm() for _ in range(5)]
        await asyncio.gather(*tasks)

        # Should have handled concurrency safely
        assert path not in self.resolver.pending_creates

    @pytest.mark.asyncio
    async def test_concurrent_resolves(self):
        """Test concurrent resolves are handled correctly."""
        path = "/config/Test/resource"
        resource_type = "ip4_block"
        bam_id = 123

        # Mock BAM query
        with patch.object(self.resolver, "_query_bam", return_value=bam_id):
            # Run multiple concurrent resolves
            tasks = [self.resolver.resolve(path, resource_type) for _ in range(10)]
            results = await asyncio.gather(*tasks)

        # All should get the same result
        assert all(result == bam_id for result in results)

        # Should have only made one query to BAM (due to caching)
        # Since we're patching _query_bam directly, we check it was called once
        assert self.resolver.stats.cache_misses == 1  # First call
        assert self.resolver.stats.cache_hits == 9  # Remaining 9 calls hit cache
