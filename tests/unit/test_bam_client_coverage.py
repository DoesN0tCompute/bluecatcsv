"""Unit tests for coverage improvement of BAMClient."""

import pytest
import respx
from httpx import Response

from src.importer.bam.client import BAMClient
from src.importer.config import BAMConfig
from src.importer.utils.exceptions import (
    BAMAuthenticationError,
    BAMRateLimitError,
    ResourceNotFoundError,
)


@pytest.fixture
def bam_config():
    return BAMConfig(
        base_url="https://bam.example.com",
        username="testuser",
        password="testpassword",
    )


@pytest.fixture
async def client(bam_config):
    client = BAMClient(bam_config)
    yield client
    await client.close()


@pytest.mark.asyncio
async def test_authentication_flow(client):
    """Test the full authentication flow including successful token retrieval."""
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        # Mock successful authentication
        respx_mock.post("/sessions").mock(
            return_value=Response(
                201,
                json={
                    "apiToken": "test-token",
                    "basicAuthenticationCredentials": "base64-credentials",
                },
            )
        )

        await client.authenticate()

        assert client.token == "test-token"
        assert client.basic_auth_credentials == "base64-credentials"


@pytest.mark.asyncio
async def test_authentication_failure(client):
    """Test authentication failure handling."""
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.post("/sessions").mock(return_value=Response(401, text="Unauthorized"))

        with pytest.raises(BAMAuthenticationError, match="Authentication failed"):
            await client.authenticate()


@pytest.mark.asyncio
async def test_authentication_connection_error(client):
    """Test authentication connection error handling."""
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.post("/sessions").side_effect = Exception("Connection refused")

        with pytest.raises(Exception, match="Connection refused"):
            await client.authenticate()


@pytest.mark.asyncio
async def test_request_rate_limiting(client):
    """Test rate limit handling with retry-after."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        # Mock 429 followed by success
        route = respx_mock.get("/test").mock(
            side_effect=[
                Response(429, headers={"Retry-After": "0"}),
                Response(200, json={"data": "success"}),
            ]
        )

        result = await client.request("GET", "test")
        assert result == {"data": "success"}
        assert route.call_count == 2


@pytest.mark.asyncio
async def test_request_rate_limit_exhausted(client):
    """Test rate limit exhaustion."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.get("/test").mock(return_value=Response(429, headers={"Retry-After": "0"}))

        with pytest.raises(BAMRateLimitError):
            await client.request("GET", "test")


@pytest.mark.asyncio
async def test_request_token_expiry(client):
    """Test automatic re-authentication on 401."""
    client.basic_auth_credentials = "old-creds"

    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        # First request fails with 401
        # Re-auth request succeeds
        # Retry request succeeds
        respx_mock.get("/test").side_effect = [
            Response(401, text="Token expired"),
            Response(200, json={"data": "success"}),
        ]

        respx_mock.post("/sessions").mock(
            return_value=Response(
                201,
                json={
                    "apiToken": "new-token",
                    "basicAuthenticationCredentials": "new-creds",
                },
            )
        )

        result = await client.request("GET", "test")
        assert result == {"data": "success"}
        assert client.basic_auth_credentials == "new-creds"


@pytest.mark.asyncio
async def test_get_all_pages_pagination_loop(client):
    """Test detection of infinite pagination loops."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        # Mock response that points back to itself
        response_json = {"data": [{"id": 1}], "_links": {"next": {"href": "/test?limit=100"}}}
        respx_mock.get("/test").mock(return_value=Response(200, json=response_json))

        results = await client.get_all_pages("test")
        # Should stop after loop detection (2 calls likely: initial + loop check)
        # The client logic breaks on current_request_key == previous_request_key
        # 1. Fetch /test?limit=100 -> returns next: /test?limit=100
        # 2. Key is same, loop detected -> break
        assert len(results) == 1  # Only first page results


@pytest.mark.asyncio
async def test_create_configuration(client):
    """Test creating a configuration."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.post("/configurations").mock(
            return_value=Response(201, json={"id": 1, "name": "Test Config"})
        )

        result = await client.create_configuration(
            name="Test Config", description="Test Description", properties={"custom": "val"}
        )
        assert result["id"] == 1


@pytest.mark.asyncio
async def test_create_view(client):
    """Test creating a view."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.post("/configurations/1/views").mock(
            return_value=Response(201, json={"id": 2, "name": "Test View"})
        )

        result = await client.create_view(config_id=1, name="Test View", description="Desc")
        assert result["id"] == 2


@pytest.mark.asyncio
async def test_delete_view_safety(client):
    """Test delete view safety check."""
    with pytest.raises(PermissionError, match="CRITICAL SAFETY VIOLATION"):
        await client.delete_view(1, allow_dangerous_operations=False)


@pytest.mark.asyncio
async def test_delete_configuration_safety(client):
    """Test delete configuration safety check."""
    with pytest.raises(PermissionError, match="CRITICAL SAFETY VIOLATION"):
        await client.delete_configuration(1, allow_dangerous_operations=False)


@pytest.mark.asyncio
async def test_get_block_by_cidr_in_config(client):
    """Test getting block by CIDR."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.get("/configurations/1/blocks").mock(
            return_value=Response(200, json={"data": [{"id": 10}]})
        )

        result = await client.get_block_by_cidr_in_config(1, "10.0.0.0/8")
        assert result["id"] == 10


@pytest.mark.asyncio
async def test_create_ip4_block(client):
    """Test creating IPv4 block."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.post("/configurations/1/blocks").mock(
            return_value=Response(201, json={"id": 10})
        )

        result = await client.create_ip4_block(
            config_id=1, cidr="10.0.0.0/8", name="Test Block", location={"id": 5}
        )
        assert result["id"] == 10


@pytest.mark.asyncio
async def test_get_ip4_blocks_no_pagination(client):
    """Test getting IPv4 blocks without pagination."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.get("/configurations/1/blocks").mock(
            return_value=Response(200, json={"data": [{"id": 10}]})
        )

        results = await client.get_ip4_blocks(config_id=1, paginate=False)
        assert len(results) == 1
        assert results[0]["id"] == 10


@pytest.mark.asyncio
async def test_get_network_by_cidr(client):
    """Test getting network by CIDR."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.get("/networks").mock(return_value=Response(200, json={"data": [{"id": 20}]}))

        result = await client.get_network_by_cidr(1, "10.0.0.0/24")
        assert result["id"] == 20


@pytest.mark.asyncio
async def test_find_network_containing_address(client):
    """Test finding network containing address."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.get("/networks").mock(
            return_value=Response(
                200,
                json={
                    "data": [{"id": 1, "range": "10.0.0.0/8"}, {"id": 2, "range": "10.1.0.0/16"}]
                },
            )
        )

        # Should match most specific (longest prefix)
        result = await client.find_network_containing_address(1, "10.1.1.1")
        assert result["id"] == 2


@pytest.mark.asyncio
async def test_create_ip4_address(client):
    """Test creating IPv4 address."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.post("/networks/1/addresses").mock(return_value=Response(201, json={"id": 30}))

        result = await client.create_ip4_address(
            network_id=1,
            address="10.1.1.1",
            name="host",
            mac="00-11-22-33-44-55",
            properties={"custom": "val"},
        )
        assert result["id"] == 30


@pytest.mark.asyncio
async def test_create_ip6_block(client):
    """Test creating IPv6 block."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.post("/configurations/1/blocks").mock(
            return_value=Response(201, json={"id": 40})
        )

        result = await client.create_ip6_block(config_id=1, cidr="2001:db8::/32", name="IPv6 Block")
        assert result["id"] == 40


@pytest.mark.asyncio
async def test_get_zone_by_fqdn_traversal(client):
    """Test getting zone by FQDN with traversal."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        # Direct matches fail
        respx_mock.get("/views/1/zones", params={"filter": "absoluteName:'foo.example.com'"}).mock(
            return_value=Response(200, json={"data": []})
        )
        respx_mock.get("/views/1/zones", params={"filter": "name:'foo.example.com'"}).mock(
            return_value=Response(200, json={"data": []})
        )

        # TLD match
        respx_mock.get("/views/1/zones", params={"filter": "name:'com'"}).mock(
            return_value=Response(200, json={"data": [{"id": 100, "name": "com"}]})
        )
        # Child match 'example' - FIXED ENDPOINT: zones/{id}/zones
        respx_mock.get("/zones/100/zones", params={"filter": "name:'example'"}).mock(
            return_value=Response(200, json={"data": [{"id": 101, "name": "example"}]})
        )
        # Child match 'foo' - FIXED ENDPOINT: zones/{id}/zones
        respx_mock.get("/zones/101/zones", params={"filter": "name:'foo'"}).mock(
            return_value=Response(200, json={"data": [{"id": 102, "name": "foo"}]})
        )

        result = await client.get_zone_by_fqdn(1, "foo.example.com")
        assert result["id"] == 102


@pytest.mark.asyncio
async def test_create_dns_records(client):
    """Test creating various DNS record types."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.post("/zones/1/resourceRecords").mock(
            return_value=Response(201, json={"id": 50})
        )

        # Host Record
        await client.create_host_record(1, "host", ["1.1.1.1"])

        # Alias Record
        await client.create_alias_record(1, "www", "host.example.com")

        # MX Record
        await client.create_mx_record(1, "@", "mail.example.com", 10)

        # TXT Record
        await client.create_txt_record(1, "@", "v=spf1 -all")

        # SRV Record
        await client.create_srv_record(1, "_sip", "sip.example.com", 5060, 10, 20)

        # External Host Record
        await client.create_external_host_record(1, 2, "ext.example.com")

        # Generic Record
        await client.create_generic_record(1, "gen", "CAA", "0 issue letsencrypt.org")


@pytest.mark.asyncio
async def test_location_methods(client):
    """Test location management methods."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        # Get Locations
        respx_mock.get("/locations").mock(
            return_value=Response(200, json={"data": [{"id": 1, "code": "US"}]})
        )

        # Create Location - FIXED ENDPOINT: locations/{id}/locations
        respx_mock.post("/locations/1/locations").mock(
            return_value=Response(201, json={"id": 2, "code": "US NYC"})
        )

        # Update Location
        respx_mock.put("/locations/2").mock(
            return_value=Response(200, json={"id": 2, "name": "New Name"})
        )

        # Delete Location
        respx_mock.delete("/locations/2").mock(return_value=Response(204))

        locs = await client.get_locations()
        assert len(locs) == 1

        new_loc = await client.create_location(parent_location_id=1, code="US NYC", name="New York")
        assert new_loc["id"] == 2

        updated = await client.update_location(2, name="New Name")
        assert updated["name"] == "New Name"

        await client.delete_location(2)


@pytest.mark.asyncio
async def test_resolve_interface_string(client):
    """Test interface string resolution."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        # Numeric ID - Fix: Return JSON or 204
        respx_mock.get("/interfaces/123").mock(return_value=Response(200, json={"id": 123}))
        assert await client.resolve_interface_string("123") == 123

        # Server Name Only (no interfaces)
        respx_mock.get("/servers", params={"filter": "name:'server1'"}).mock(
            return_value=Response(200, json={"data": [{"id": 1}]})
        )
        respx_mock.get("/servers/1/interfaces").mock(return_value=Response(200, json={"data": []}))
        with pytest.raises(ResourceNotFoundError):
            await client.resolve_interface_string("server1")

        # Server:Interface
        respx_mock.get("/servers", params={"filter": "name:'server2'"}).mock(
            return_value=Response(200, json={"data": [{"id": 2}]})
        )
        respx_mock.get("/servers/2/interfaces").mock(
            return_value=Response(200, json={"data": [{"id": 20, "name": "eth0"}]})
        )
        assert await client.resolve_interface_string("server2:eth0") == 20


@pytest.mark.asyncio
async def test_create_dhcp_deployment_role(client):
    """Test creating DHCP deployment role."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.post("/networks/1/deploymentRoles").mock(
            return_value=Response(201, json={"id": 60})
        )

        result = await client.create_dhcp_deployment_role(
            parent_id=1,
            parent_type="network",
            name="Role",
            role_type="MASTER",
            interfaces=[{"id": 1}],
        )
        assert result["id"] == 60


@pytest.mark.asyncio
async def test_create_dns_deployment_role(client):
    """Test creating DNS deployment role."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.post("/zones/1/deploymentRoles").mock(
            return_value=Response(201, json={"id": 70})
        )

        result = await client.create_dns_deployment_role(
            parent_id=1,
            parent_type="zones",
            name="Role",
            role_type="PRIMARY",
            interfaces=[{"id": 1}],
        )
        assert result["id"] == 70


@pytest.mark.asyncio
async def test_location_methods_all_fields(client):
    """Test location methods with all optional fields."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.post("/locations/1/locations").mock(
            return_value=Response(201, json={"id": 2, "code": "US NYC"})
        )
        respx_mock.put("/locations/2").mock(return_value=Response(200, json={"id": 2}))

        await client.create_location(
            parent_location_id=1,
            code="US NYC",
            name="NYC",
            description="New York City",
            localized_name="New York",
            latitude=40.7128,
            longitude=-74.0060,
            properties={"custom": "val"},
        )

        await client.update_location(
            location_id=2,
            name="NYC Updated",
            description="Updated Desc",
            localized_name="NY",
            latitude=40.7,
            longitude=-74.0,
            properties={"new": "val"},
        )


@pytest.mark.asyncio
async def test_context_manager(bam_config):
    """Test BAMClient context manager."""
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.post("/sessions").mock(
            return_value=Response(
                201, json={"apiToken": "token", "basicAuthenticationCredentials": "creds"}
            )
        )

        async with BAMClient(bam_config) as client:
            assert client.token == "token"
            assert client._client is not None

        # Client should be closed after exit
        assert client._client is None


@pytest.mark.asyncio
async def test_authentication_skip(client):
    """Test authentication skip when already authenticated."""
    client.basic_auth_credentials = "existing_creds"

    with respx.mock(
        base_url="https://bam.example.com/api/v2", assert_all_called=False
    ) as respx_mock:
        # Should not call sessions endpoint
        session_route = respx_mock.post("/sessions").mock(return_value=Response(500))

        await client.authenticate(force=False)
        assert not session_route.called


@pytest.mark.asyncio
async def test_update_location_no_fields(client):
    """Test update location validation with no fields."""
    with pytest.raises(ValueError, match="At least one field must be provided"):
        await client.update_location(1)


@pytest.mark.asyncio
async def test_find_network_containing_address_not_found(client):
    """Test find network containing address when not found."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.get("/networks").mock(return_value=Response(200, json={"data": []}))

        with pytest.raises(ResourceNotFoundError):
            await client.find_network_containing_address(1, "1.2.3.4")


@pytest.mark.asyncio
async def test_find_block_containing_network(client):
    """Test finding block containing network."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.get("/blocks").mock(
            return_value=Response(
                200,
                json={
                    "data": [{"id": 1, "range": "10.0.0.0/8"}, {"id": 2, "range": "10.1.0.0/16"}]
                },
            )
        )

        result = await client.find_block_containing_network(1, "10.1.1.0/24")
        assert result["id"] == 2

        # Test not found
        respx_mock.get("/blocks").mock(return_value=Response(200, json={"data": []}))
        with pytest.raises(ValueError):
            await client.find_block_containing_network(1, "192.168.1.0/24")


@pytest.mark.asyncio
async def test_find_block_containing_address(client):
    """Test finding block containing address."""
    client.basic_auth_credentials = "creds"
    with respx.mock(base_url="https://bam.example.com/api/v2") as respx_mock:
        respx_mock.get("/blocks").mock(
            return_value=Response(200, json={"data": [{"id": 1, "range": "10.0.0.0/8"}]})
        )

        result = await client.find_block_containing_address(1, "10.0.0.1")
        assert result["id"] == 1

        # Test not found
        respx_mock.get("/blocks").mock(return_value=Response(200, json={"data": []}))
        with pytest.raises(ValueError):
            await client.find_block_containing_address(1, "192.168.1.1")
