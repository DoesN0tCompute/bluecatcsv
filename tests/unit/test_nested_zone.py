from unittest.mock import AsyncMock, MagicMock

import pytest

from src.importer.core.operation_factory import OperationFactory, PendingResources


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.get_zones_in_view = AsyncMock(return_value=[])
    client.get_zone_by_fqdn = AsyncMock()
    client.get_child_zones = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_resolver():
    return MagicMock()


@pytest.fixture
def pending():
    return PendingResources()


@pytest.fixture
def factory(mock_client, mock_resolver, pending):
    return OperationFactory(mock_client, mock_resolver, pending)


@pytest.mark.asyncio
async def test_resolve_dns_record_zone_with_absoluteName(factory, mock_client):
    """Test zone resolution using absoluteName attribute."""
    # Mock zone lookup
    mock_client.get_zone_by_fqdn = AsyncMock(
        return_value={"id": 100, "name": "sub", "absoluteName": "sub.example.com"}
    )

    row = MagicMock()
    row.row_id = "1"
    row.object_type = "host_record"
    row.name = "www.sub.example.com"
    row.zone_name = None  # Not provided
    row.absoluteName = "sub.example.com"  # Nested zone
    row.absolute_name = None

    payload = {}
    view_id = 10

    await factory._resolve_dns_record_zone(row, payload, view_id)

    assert payload["zone_id"] == 100
    assert payload["name"] == "www"  # Relative to zone
    mock_client.get_zone_by_fqdn.assert_called_with(10, "sub.example.com")


@pytest.mark.asyncio
async def test_resolve_nested_zone_by_walking_parents(factory, mock_client):
    """Test resolving nested zone by walking parent zones."""
    # First call fails (zone doesn't exist directly)
    # Second call succeeds (parent zone exists)
    mock_client.get_zone_by_fqdn = AsyncMock(
        side_effect=[
            Exception("Zone not found"),  # First call for sub.example.com
            {"id": 50, "name": "example", "absoluteName": "example.com"},  # Parent zone
        ]
    )

    # Child zones in parent
    mock_client.get_child_zones = AsyncMock(
        return_value=[{"id": 100, "name": "sub", "absoluteName": "sub.example.com"}]
    )

    row = MagicMock()
    row.row_id = "2"
    row.object_type = "host_record"
    row.name = "www.sub.example.com"
    row.zone_name = "sub.example.com"
    row.absoluteName = None
    row.absolute_name = None

    payload = {}
    view_id = 10

    await factory._resolve_dns_record_zone(row, payload, view_id)

    # Should have found the nested zone
    assert payload.get("zone_id") == 100
    assert payload.get("resource_path") == "sub.example.com"


@pytest.mark.asyncio
async def test_pending_zone_takes_precedence(factory, mock_client):
    """Test that pending zones are matched before API lookup."""
    # Add zone to pending
    factory.pending.zones["new.example.com"] = "row_5"

    row = MagicMock()
    row.row_id = "3"
    row.object_type = "host_record"
    row.name = "www.new.example.com"
    row.zone_name = "new.example.com"
    row.absoluteName = None
    row.absolute_name = None

    payload = {}
    view_id = 10

    await factory._resolve_dns_record_zone(row, payload, view_id)

    # Should be deferred
    assert payload["_deferred_zone_name"] == "new.example.com"
    assert payload["_deferred_zone_row"] == "row_5"
    # API should not be called
    mock_client.get_zone_by_fqdn.assert_not_called()
