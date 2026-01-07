from unittest.mock import AsyncMock, MagicMock

import pytest

from src.importer.config import CacheConfig
from src.importer.core.resolver import Resolver


@pytest.fixture
def mock_bam_client():
    client = MagicMock()
    client.get_configuration_by_name = AsyncMock(return_value={"id": 1, "name": "Default"})
    return client


@pytest.fixture
def resolver_with_cache(mock_bam_client, tmp_path):
    """Resolver with caching enabled (default)."""
    return Resolver(mock_bam_client, tmp_path / "cache", CacheConfig(), no_cache=False)


@pytest.fixture
def resolver_no_cache(mock_bam_client, tmp_path):
    """Resolver with caching disabled."""
    return Resolver(mock_bam_client, tmp_path / "cache", CacheConfig(), no_cache=True)


def test_resolver_no_cache_flag(resolver_no_cache):
    """Test that no_cache flag is stored correctly."""
    assert resolver_no_cache.no_cache is True


def test_resolver_with_cache_flag(resolver_with_cache):
    """Test that cache is enabled by default."""
    assert resolver_with_cache.no_cache is False


@pytest.mark.asyncio
async def test_no_cache_bypasses_cache_lookup(resolver_no_cache, mock_bam_client):
    """Test that resolve() skips cache when no_cache=True."""
    # Prime the cache with a value
    resolver_no_cache.cache.set("Configuration:Default", 999, expire=3600)

    # With no_cache=True, it should call the API anyway
    result = await resolver_no_cache.resolve("Default", "Configuration")

    # Should return API result (id=1), not cached value (999)
    assert result == 1
    mock_bam_client.get_configuration_by_name.assert_called_once_with("Default")


@pytest.mark.asyncio
async def test_with_cache_uses_cached_value(resolver_with_cache, mock_bam_client):
    """Test that resolve() uses cache when no_cache=False."""
    # Prime the cache with a value
    resolver_with_cache.cache.set("Configuration:Default", 999, expire=3600)

    # With caching enabled, it should return cached value
    result = await resolver_with_cache.resolve("Default", "Configuration")

    # Should return cached value (999), not call API
    assert result == 999
    mock_bam_client.get_configuration_by_name.assert_not_called()


@pytest.mark.asyncio
async def test_invalidate_removes_cache_entry(resolver_with_cache):
    """Test that invalidate() removes cache entries with normalized keys."""
    # Add entry with normalized key (network -> Network)
    normalized_key = "Network:10.0.0.0/24"
    resolver_with_cache.cache.set(normalized_key, 100, expire=3600)
    assert resolver_with_cache.cache.get(normalized_key) == 100

    # Invalidate using any type variation (should normalize)
    await resolver_with_cache.invalidate("10.0.0.0/24", "network")

    # Entry should be gone
    assert resolver_with_cache.cache.get(normalized_key) is None


@pytest.mark.asyncio
async def test_delete_create_same_resource_cache_coherency(resolver_with_cache, mock_bam_client):
    """Test DELETE followed by CREATE of same resource doesn't use stale cache.

    This verifies EDGE-003: Concurrent DELETE and CREATE of same resource.
    The scenario is:
    1. Resource exists with ID 100 (cached)
    2. DELETE operation invalidates cache
    3. CREATE operation for same resource should query BAM, not use old ID 100
    """
    path = "Default/10.0.0.0/8"
    resource_type = "ip4_block"
    old_id = 100
    new_id = 200

    # Step 1: Simulate cached resource from previous resolution
    normalized_key = "Block:Default/10.0.0.0/8"
    resolver_with_cache.cache.set(normalized_key, old_id, expire=3600)
    assert resolver_with_cache.cache.get(normalized_key) == old_id

    # Step 2: DELETE operation invalidates cache (simulating runner behavior)
    await resolver_with_cache.invalidate(path, resource_type)
    assert resolver_with_cache.cache.get(normalized_key) is None

    # Step 3: CREATE operation for same resource - should query BAM, not use old cached ID
    # Mock BAM to return new ID
    mock_bam_client.get_configuration_by_name = AsyncMock(return_value={"id": 1, "name": "Default"})
    mock_bam_client.get_block_by_cidr_in_config = AsyncMock(return_value={"id": new_id})

    # Resolve should query BAM since cache was invalidated
    resolved_id = await resolver_with_cache.resolve(path, resource_type)

    # Should get NEW id, not old cached one
    assert resolved_id == new_id
    assert resolved_id != old_id

    # Verify BAM was queried (cache miss)
    mock_bam_client.get_block_by_cidr_in_config.assert_called_once()
