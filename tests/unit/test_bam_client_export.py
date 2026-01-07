"""Unit tests for BAM Client export methods."""

import pytest
import respx
from httpx import Response

from src.importer.bam.client import BAMClient
from src.importer.config import BAMConfig
from src.importer.utils.exceptions import ResourceNotFoundError


@pytest.fixture
def bam_config():
    """Create test BAM configuration."""
    return {
        "base_url": "https://bam.example.com",
        "username": "admin",
        "password": "password",
        "api_version": "v2",
        "timeout": 30,
        "verify_ssl": True,
        "max_connections": 50,
        "max_keepalive": 20,
    }


@pytest.fixture
async def authenticated_client(bam_config):
    """Create an authenticated BAM client with mocked session."""
    with respx.mock(assert_all_called=False) as router:
        # Mock authentication endpoint
        router.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=Response(
                201,
                json={
                    "apiToken": "test-token",
                    "basicAuthenticationCredentials": "test-basic-creds",
                },
            )
        )

        config = BAMConfig(
            base_url=bam_config["base_url"],
            username=bam_config["username"],
            password=bam_config["password"],
            api_version=bam_config["api_version"],
            timeout=bam_config["timeout"],
            verify_ssl=bam_config["verify_ssl"],
            max_connections=bam_config["max_connections"],
            max_keepalive=bam_config["max_keepalive"],
        )
        client = BAMClient(config=config)
        client.mock_router = router
        await client.authenticate()
        yield client
        await client.close()


class TestGetBlockById:
    """Test get_block_by_id method."""

    @pytest.mark.asyncio
    async def test_get_block_success(self, authenticated_client):
        """Test successful block retrieval by ID."""
        block_id = 12345
        mock_block = {
            "id": block_id,
            "type": "IP4Block",
            "name": "Corp-Block",
            "range": "10.0.0.0/8",
            "configuration": {"id": 100, "name": "Default"},
            "userDefinedFields": {"owner": "IT Team"},
        }

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/blocks/{block_id}"
        ).mock(return_value=Response(200, json=mock_block))

        result = await authenticated_client.get_block_by_id(block_id)

        assert result == mock_block
        assert result["id"] == block_id
        assert result["type"] == "IP4Block"

    @pytest.mark.asyncio
    async def test_get_block_not_found(self, authenticated_client):
        """Test block not found returns 404."""
        block_id = 99999

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/blocks/{block_id}"
        ).mock(return_value=Response(404, json={"error": "Block not found"}))

        with pytest.raises(ResourceNotFoundError):
            await authenticated_client.get_block_by_id(block_id)


class TestGetNetworkById:
    """Test get_network_by_id method."""

    @pytest.mark.asyncio
    async def test_get_network_success(self, authenticated_client):
        """Test successful network retrieval by ID."""
        network_id = 12345
        mock_network = {
            "id": network_id,
            "type": "IPv4Network",
            "name": "Corp-Network",
            "range": "10.1.0.0/16",
            "configuration": {"id": 100, "name": "Default"},
            "userDefinedFields": {"environment": "production"},
        }

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/networks/{network_id}"
        ).mock(return_value=Response(200, json=mock_network))

        result = await authenticated_client.get_network_by_id(network_id)

        assert result == mock_network
        assert result["id"] == network_id
        assert result["type"] == "IPv4Network"

    @pytest.mark.asyncio
    async def test_get_network_not_found(self, authenticated_client):
        """Test network not found returns 404."""
        network_id = 99999

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/networks/{network_id}"
        ).mock(return_value=Response(404, json={"error": "Network not found"}))

        with pytest.raises(ResourceNotFoundError):
            await authenticated_client.get_network_by_id(network_id)


class TestGetNetworkByCidr:
    """Test get_network_by_cidr method."""

    @pytest.mark.asyncio
    async def test_get_network_by_cidr_success(self, authenticated_client):
        """Test successful network retrieval by CIDR."""
        config_id = 100
        cidr = "10.1.0.0/16"
        mock_network = {
            "id": 12345,
            "type": "IPv4Network",
            "name": "Corp-Network",
            "range": cidr,
            "configuration": {"id": config_id, "name": "Default"},
        }

        route = authenticated_client.mock_router.get(
            "https://bam.example.com/api/v2/networks"
        ).mock(
            return_value=Response(
                200,
                json={
                    "_embedded": {"networks": [mock_network]},
                    "page": {"totalElements": 1},
                },
            )
        )

        result = await authenticated_client.get_network_by_cidr(config_id, cidr)

        assert result == mock_network
        # Verify query parameters - config_id is not quoted (numbers don't need quotes)
        assert (
            route.calls.last.request.url.params["filter"]
            == f"configuration.id:{config_id} and range:'{cidr}'"
        )

    @pytest.mark.asyncio
    async def test_get_network_by_cidr_not_found(self, authenticated_client):
        """Test network not found by CIDR."""
        config_id = 100
        cidr = "192.168.1.0/24"

        authenticated_client.mock_router.get("https://bam.example.com/api/v2/networks").mock(
            return_value=Response(
                200,
                json={
                    "_embedded": {"networks": []},
                    "page": {"totalElements": 0},
                },
            )
        )

        with pytest.raises(ResourceNotFoundError, match=f"Network not found: {cidr}"):
            await authenticated_client.get_network_by_cidr(config_id, cidr)

    @pytest.mark.asyncio
    async def test_get_network_by_cidr_multiple_results(self, authenticated_client):
        """Test network CIDR with multiple results (should return first)."""
        config_id = 100
        cidr = "10.1.0.0/16"
        mock_networks = [
            {"id": 12345, "type": "IPv4Network", "range": cidr},
            {"id": 12346, "type": "IPv4Network", "range": cidr},
        ]

        authenticated_client.mock_router.get("https://bam.example.com/api/v2/networks").mock(
            return_value=Response(
                200,
                json={
                    "_embedded": {"networks": mock_networks},
                    "page": {"totalElements": 2},
                },
            )
        )

        result = await authenticated_client.get_network_by_cidr(config_id, cidr)

        # Should return first result
        assert result == mock_networks[0]


class TestGetChildBlocks:
    """Test get_child_blocks method."""

    @pytest.mark.asyncio
    async def test_get_child_blocks_success(self, authenticated_client):
        """Test successful retrieval of child blocks with pagination."""
        parent_id = 12345
        mock_blocks = [
            {"id": 12346, "type": "IP4Block", "name": "Child-Block-1"},
            {"id": 12347, "type": "IP4Block", "name": "Child-Block-2"},
        ]

        route = authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/blocks/{parent_id}/blocks"
        ).mock(
            return_value=Response(
                200,
                json={
                    "data": mock_blocks,  # Use data format for get_all_pages
                    "_links": {},  # No next page
                },
            )
        )

        result = await authenticated_client.get_child_blocks(parent_id)

        assert result == mock_blocks
        assert len(result) == 2
        # With pagination enabled, limit param is sent
        assert route.calls.last.request.url.params.get("limit") == "100"  # DEFAULT_PAGE_SIZE

    @pytest.mark.asyncio
    async def test_get_child_blocks_custom_pagination(self, authenticated_client):
        """Test child blocks with pagination disabled (single page fetch)."""
        parent_id = 12345
        mock_blocks = [{"id": 12346, "type": "IP4Block", "name": "Child-Block-1"}]

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/blocks/{parent_id}/blocks"
        ).mock(
            return_value=Response(
                200,
                json={"_embedded": {"blocks": mock_blocks}, "page": {"totalElements": 1}},
            )
        )

        # With paginate=False, uses legacy single-page fetch
        result = await authenticated_client.get_child_blocks(parent_id, paginate=False)

        assert result == mock_blocks

    @pytest.mark.asyncio
    async def test_get_child_blocks_empty(self, authenticated_client):
        """Test child blocks with no results."""
        parent_id = 12345

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/blocks/{parent_id}/blocks"
        ).mock(
            return_value=Response(
                200,
                json={"data": [], "_links": {}},  # Use data format for get_all_pages
            )
        )

        result = await authenticated_client.get_child_blocks(parent_id)

        assert result == []


class TestGetChildNetworks:
    """Test get_child_networks method."""

    @pytest.mark.asyncio
    async def test_get_child_networks_success(self, authenticated_client):
        """Test successful retrieval of child networks."""
        parent_id = 12345
        mock_networks = [
            {"id": 12346, "type": "IPv4Network", "name": "Child-Network-1", "range": "10.1.1.0/24"},
            {"id": 12347, "type": "IPv4Network", "name": "Child-Network-2", "range": "10.1.2.0/24"},
        ]

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/blocks/{parent_id}/networks"
        ).mock(
            return_value=Response(
                200,
                json={
                    "_embedded": {"networks": mock_networks},
                    "page": {"totalElements": 2},
                },
            )
        )

        result = await authenticated_client.get_child_networks(parent_id)

        assert result == mock_networks
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_child_networks_empty(self, authenticated_client):
        """Test child networks with no results."""
        parent_id = 12345

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/blocks/{parent_id}/networks"
        ).mock(
            return_value=Response(
                200,
                json={"_embedded": {"networks": []}, "page": {"totalElements": 0}},
            )
        )

        result = await authenticated_client.get_child_networks(parent_id)

        assert result == []


class TestGetAddressesInNetwork:
    """Test get_addresses_in_network method."""

    @pytest.mark.asyncio
    async def test_get_addresses_success(self, authenticated_client):
        """Test successful retrieval of addresses in network."""
        network_id = 12345
        mock_addresses = [
            {
                "id": 12346,
                "type": "IP4Address",
                "address": "10.1.0.10",
                "macAddress": "00:11:22:33:44:55",
                "name": "server-1",
            },
            {
                "id": 12347,
                "type": "IP4Address",
                "address": "10.1.0.11",
                "macAddress": "00:11:22:33:44:66",
                "name": "server-2",
            },
        ]

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/networks/{network_id}/addresses"
        ).mock(
            return_value=Response(
                200,
                json={
                    "_embedded": {"addresses": mock_addresses},
                    "page": {"totalElements": 2},
                },
            )
        )

        result = await authenticated_client.get_addresses_in_network(network_id)

        assert result == mock_addresses
        assert len(result) == 2
        assert result[0]["address"] == "10.1.0.10"

    @pytest.mark.asyncio
    async def test_get_addresses_empty(self, authenticated_client):
        """Test addresses with no results."""
        network_id = 12345

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/networks/{network_id}/addresses"
        ).mock(
            return_value=Response(
                200,
                json={"_embedded": {"addresses": []}, "page": {"totalElements": 0}},
            )
        )

        result = await authenticated_client.get_addresses_in_network(network_id)

        assert result == []


class TestGetZoneById:
    """Test get_zone_by_id method."""

    @pytest.mark.asyncio
    async def test_get_zone_success(self, authenticated_client):
        """Test successful zone retrieval by ID."""
        zone_id = 54321
        mock_zone = {
            "id": zone_id,
            "type": "Zone",
            "name": "example",
            "absoluteName": "example.com",
            "configuration": {"id": 100, "name": "Default"},
            "view": {"id": 200, "name": "Internal"},
            "userDefinedFields": {"owner": "DNS Team"},
        }

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/zones/{zone_id}"
        ).mock(return_value=Response(200, json=mock_zone))

        result = await authenticated_client.get_zone_by_id(zone_id)

        assert result == mock_zone
        assert result["id"] == zone_id
        assert result["absoluteName"] == "example.com"

    @pytest.mark.asyncio
    async def test_get_zone_not_found(self, authenticated_client):
        """Test zone not found returns 404."""
        zone_id = 99999

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/zones/{zone_id}"
        ).mock(return_value=Response(404, json={"error": "Zone not found"}))

        with pytest.raises(ResourceNotFoundError):
            await authenticated_client.get_zone_by_id(zone_id)


class TestGetZoneByFqdn:
    """Test get_zone_by_fqdn method."""

    @pytest.mark.asyncio
    async def test_get_zone_by_fqdn_success(self, authenticated_client):
        """Test successful zone retrieval by FQDN."""
        view_id = 200
        fqdn = "example.com"
        mock_zone = {
            "id": 54321,
            "type": "Zone",
            "name": "example",
            "absoluteName": fqdn,
            "view": {"id": view_id, "name": "Internal"},
        }

        route = authenticated_client.mock_router.get(
            "https://bam.example.com/api/v2/views/200/zones"
        ).mock(
            return_value=Response(
                200,
                json={
                    "_embedded": {"zones": [mock_zone]},
                    "page": {"totalElements": 1},
                },
            )
        )

        result = await authenticated_client.get_zone_by_fqdn(view_id, fqdn)

        assert result == mock_zone
        # Verify query parameters
        assert route.calls.last.request.url.params["filter"] == f"absoluteName:'{fqdn}'"

    @pytest.mark.asyncio
    async def test_get_zone_by_fqdn_not_found(self, authenticated_client):
        """Test zone not found by FQDN."""
        view_id = 200
        fqdn = "nonexistent.com"

        authenticated_client.mock_router.get("https://bam.example.com/api/v2/views/200/zones").mock(
            return_value=Response(
                200,
                json={
                    "_embedded": {"zones": []},
                    "page": {"totalElements": 0},
                },
            )
        )

        with pytest.raises(ResourceNotFoundError, match=f"DNSZone not found: {fqdn}"):
            await authenticated_client.get_zone_by_fqdn(view_id, fqdn)


class TestGetChildZones:
    """Test get_child_zones method."""

    @pytest.mark.asyncio
    async def test_get_child_zones_success(self, authenticated_client):
        """Test successful retrieval of child zones."""
        parent_zone_id = 54321
        mock_zones = [
            {"id": 54322, "type": "Zone", "name": "dev", "absoluteName": "dev.example.com"},
            {"id": 54323, "type": "Zone", "name": "staging", "absoluteName": "staging.example.com"},
        ]

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/zones/{parent_zone_id}/zones"
        ).mock(
            return_value=Response(
                200,
                json={
                    "_embedded": {"zones": mock_zones},
                    "page": {"totalElements": 2},
                },
            )
        )

        result = await authenticated_client.get_child_zones(parent_zone_id)

        assert result == mock_zones
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_child_zones_empty(self, authenticated_client):
        """Test child zones with no results."""
        parent_zone_id = 54321

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/zones/{parent_zone_id}/zones"
        ).mock(
            return_value=Response(
                200,
                json={"_embedded": {"zones": []}, "page": {"totalElements": 0}},
            )
        )

        result = await authenticated_client.get_child_zones(parent_zone_id)

        assert result == []


class TestGetResourceRecordsInZone:
    """Test get_resource_records_in_zone method."""

    @pytest.mark.asyncio
    async def test_get_resource_records_success(self, authenticated_client):
        """Test successful retrieval of resource records."""
        zone_id = 54321
        mock_records = [
            {
                "id": 54322,
                "type": "HostRecord",
                "name": "www",
                "absoluteName": "www.example.com",
                "ttl": 3600,
                "_embedded": {"addresses": [{"address": "10.1.0.10"}]},
            },
            {
                "id": 54323,
                "type": "MXRecord",
                "name": "mail",
                "absoluteName": "mail.example.com",
                "ttl": 3600,
            },
        ]

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/zones/{zone_id}/resourceRecords"
        ).mock(
            return_value=Response(
                200,
                json={
                    "_embedded": {"resourceRecords": mock_records},
                    "page": {"totalElements": 2},
                },
            )
        )

        result = await authenticated_client.get_resource_records_in_zone(zone_id)

        assert result == mock_records
        assert len(result) == 2
        assert result[0]["type"] == "HostRecord"
        assert result[1]["type"] == "MXRecord"

    @pytest.mark.asyncio
    async def test_get_resource_records_empty(self, authenticated_client):
        """Test resource records with no results."""
        zone_id = 54321

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/zones/{zone_id}/resourceRecords"
        ).mock(
            return_value=Response(
                200,
                json={
                    "_embedded": {"resourceRecords": []},
                    "page": {"totalElements": 0},
                },
            )
        )

        result = await authenticated_client.get_resource_records_in_zone(zone_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_resource_records_custom_pagination(self, authenticated_client):
        """Test resource records with pagination disabled (single page fetch)."""
        zone_id = 54321
        mock_records = [{"id": 54322, "type": "HostRecord", "name": "www"}]

        authenticated_client.mock_router.get(
            f"https://bam.example.com/api/v2/zones/{zone_id}/resourceRecords"
        ).mock(
            return_value=Response(
                200,
                json={
                    "_embedded": {"resourceRecords": mock_records},
                    "page": {"totalElements": 1},
                },
            )
        )

        # With paginate=False, uses legacy single-page fetch
        result = await authenticated_client.get_resource_records_in_zone(zone_id, paginate=False)

        assert result == mock_records
