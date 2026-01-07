"""Unit tests for resolver view caching optimizations."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.importer.config import CacheConfig
from src.importer.core.resolver import Resolver


class TestResolverViewCaching:
    """Test resolver view caching functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BAM client."""
        client = AsyncMock()
        client.get_views_in_configuration = AsyncMock()
        return client

    @pytest.fixture
    def cache_dir(self, tmp_path):
        """Create temporary cache directory."""
        return tmp_path / "cache"

    @pytest.fixture
    def default_cache_config(self):
        """Create default cache configuration."""
        return CacheConfig()

    @pytest.fixture
    def fast_ttl_cache_config(self):
        """Create cache config with fast TTL for testing."""
        return CacheConfig(view_cache_ttl=1)  # 1 second TTL

    @pytest.fixture
    def resolver(self, mock_client, cache_dir, default_cache_config):
        """Create resolver with default cache config."""
        return Resolver(mock_client, cache_dir, default_cache_config)

    @pytest.fixture
    def resolver_fast_ttl(self, mock_client, cache_dir, fast_ttl_cache_config):
        """Create resolver with fast TTL for testing."""
        return Resolver(mock_client, cache_dir, fast_ttl_cache_config)

    @pytest.mark.asyncio
    async def test_view_cache_miss_first_call(self, resolver, mock_client):
        """Test that first call to get views results in cache miss."""
        config_id = 123
        expected_views = [{"id": 1, "name": "View1"}, {"id": 2, "name": "View2"}]
        mock_client.get_views_in_configuration.return_value = expected_views

        # First call should be a cache miss
        result = await resolver._get_views_cached(config_id)

        assert result == expected_views
        mock_client.get_views_in_configuration.assert_called_once_with(config_id)

    @pytest.mark.asyncio
    async def test_view_cache_hit_subsequent_call(self, resolver, mock_client):
        """Test that subsequent calls to get views result in cache hit."""
        config_id = 123
        expected_views = [{"id": 1, "name": "View1"}, {"id": 2, "name": "View2"}]
        mock_client.get_views_in_configuration.return_value = expected_views

        # First call - cache miss
        await resolver._get_views_cached(config_id)
        # Second call - should be cache hit
        result = await resolver._get_views_cached(config_id)

        assert result == expected_views
        # Should only be called once due to caching
        mock_client.get_views_in_configuration.assert_called_once_with(config_id)

    @pytest.mark.asyncio
    async def test_view_cache_ttl_expiration(self, resolver_fast_ttl, mock_client):
        """Test that view cache expires after TTL."""
        config_id = 123
        expected_views_first = [{"id": 1, "name": "View1"}]
        expected_views_second = [{"id": 1, "name": "View1_Updated"}]

        mock_client.get_views_in_configuration.return_value = expected_views_first

        # First call - cache miss
        result1 = await resolver_fast_ttl._get_views_cached(config_id)
        assert result1 == expected_views_first
        assert mock_client.get_views_in_configuration.call_count == 1

        # Wait for cache to expire (TTL is 1 second)
        await asyncio.sleep(1.1)

        # Configure second response
        mock_client.get_views_in_configuration.return_value = expected_views_second

        # Second call after TTL - should be cache miss again
        result2 = await resolver_fast_ttl._get_views_cached(config_id)
        assert result2 == expected_views_second
        # Should be called twice due to expiration
        assert mock_client.get_views_in_configuration.call_count == 2

    @pytest.mark.asyncio
    async def test_view_cache_different_configs(self, resolver, mock_client):
        """Test that different config IDs are cached separately."""
        config_id_1 = 123
        config_id_2 = 456

        views_1 = [{"id": 1, "name": "View1"}]
        views_2 = [{"id": 2, "name": "View2"}]

        mock_client.get_views_in_configuration.side_effect = [views_1, views_2]

        # Get views for both configs
        result1 = await resolver._get_views_cached(config_id_1)
        result2 = await resolver._get_views_cached(config_id_2)

        assert result1 == views_1
        assert result2 == views_2
        assert mock_client.get_views_in_configuration.call_count == 2

    @pytest.mark.asyncio
    async def test_view_cache_concurrent_access(self, resolver, mock_client):
        """Test that concurrent access to view cache works correctly."""
        config_id = 123
        expected_views = [{"id": 1, "name": "View1"}, {"id": 2, "name": "View2"}]
        mock_client.get_views_in_configuration.return_value = expected_views

        # Make concurrent calls
        tasks = [resolver._get_views_cached(config_id) for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # All should get the same result
        for result in results:
            assert result == expected_views

        # Should only make one API call due to caching
        assert mock_client.get_views_in_configuration.call_count == 1

    @pytest.mark.asyncio
    async def test_view_cache_error_handling(self, resolver, mock_client):
        """Test that view cache properly handles API errors."""
        config_id = 123
        mock_client.get_views_in_configuration.side_effect = Exception("API Error")

        # Should propagate the error
        with pytest.raises(Exception, match="API Error"):
            await resolver._get_views_cached(config_id)

    @pytest.mark.asyncio
    async def test_view_cache_isolated_instances(self, mock_client, cache_dir):
        """Test that different resolver instances have separate caches."""
        config_id = 123
        views_1 = [{"id": 1, "name": "View1"}]
        views_2 = [{"id": 1, "name": "View1_Different"}]

        # Create two different resolvers
        resolver1 = Resolver(mock_client, cache_dir / "resolver1")
        resolver2 = Resolver(mock_client, cache_dir / "resolver2")

        mock_client.get_views_in_configuration.side_effect = [views_1, views_2]

        # Get views from both resolvers
        result1 = await resolver1._get_views_cached(config_id)
        result2 = await resolver2._get_views_cached(config_id)

        # Should have different results
        assert result1 == views_1
        assert result2 == views_2
        assert mock_client.get_views_in_configuration.call_count == 2

    def test_view_cache_initialization(self, mock_client, cache_dir):
        """Test that view cache is properly initialized."""
        cache_config = CacheConfig(view_cache_ttl=600)
        resolver = Resolver(mock_client, cache_dir, cache_config)

        # Check that cache attributes are set
        assert hasattr(resolver, "_view_cache")
        assert hasattr(resolver, "_view_cache_ttl")
        assert hasattr(resolver, "_view_cache_duration")
        assert resolver._view_cache_duration == 600
        assert len(resolver._view_cache) == 0
        assert len(resolver._view_cache_ttl) == 0

    def test_view_cache_config_defaults(self, mock_client, cache_dir):
        """Test that view cache uses default configuration when not provided."""
        resolver = Resolver(mock_client, cache_dir)  # No cache_config provided

        # Should use default TTL from CacheConfig
        assert resolver._view_cache_duration == 300  # 5 minutes default

    @pytest.mark.asyncio
    async def test_view_cache_performance_improvement(self, resolver_fast_ttl, mock_client):
        """Test that view cache provides measurable performance improvement."""
        config_id = 123
        expected_views = [{"id": 1, "name": "View1"}]
        mock_client.get_views_in_configuration.return_value = expected_views

        # Clear any existing cache
        resolver_fast_ttl._view_cache.clear()
        resolver_fast_ttl._view_cache_ttl.clear()
        mock_client.reset_mock()

        # First call - should be a cache miss and trigger API call
        result1 = await resolver_fast_ttl._get_views_cached(config_id)

        # Verify it made the API call
        assert mock_client.get_views_in_configuration.call_count == 1
        assert mock_client.get_views_in_configuration.call_args == ((config_id,),)
        assert result1 == expected_views

        # Multiple subsequent calls - should all be cache hits
        for _ in range(10):
            result = await resolver_fast_ttl._get_views_cached(config_id)
            assert result == expected_views

        # API call count should not have increased (all cache hits)
        assert mock_client.get_views_in_configuration.call_count == 1

        # Verify data is in cache
        assert config_id in resolver_fast_ttl._view_cache
        assert config_id in resolver_fast_ttl._view_cache_ttl
        assert resolver_fast_ttl._view_cache[config_id] == expected_views

        # Clear cache and verify next call is a miss
        resolver_fast_ttl._view_cache.clear()
        resolver_fast_ttl._view_cache_ttl.clear()
        mock_client.reset_mock()
        mock_client.get_views_in_configuration.return_value = expected_views

        result2 = await resolver_fast_ttl._get_views_cached(config_id)
        assert mock_client.get_views_in_configuration.call_count == 1
        assert result2 == expected_views


class TestResolverWithRealCacheConfig:
    """Test resolver with realistic cache configurations."""

    @pytest.mark.asyncio
    async def test_custom_cache_configuration(self):
        """Test resolver with custom cache configuration."""
        mock_client = AsyncMock()
        cache_dir = Path("/tmp/test_cache")

        # Custom cache config
        cache_config = CacheConfig(
            ttl_seconds=7200, view_cache_ttl=900, directory="/custom/cache"  # 15 minutes
        )

        with patch("pathlib.Path.mkdir"):
            resolver = Resolver(mock_client, cache_dir, cache_config)

            # Verify configuration is applied
            assert resolver.cache_config.ttl_seconds == 7200
            assert resolver._view_cache_duration == 900
            assert resolver.cache_config.directory == "/custom/cache"
