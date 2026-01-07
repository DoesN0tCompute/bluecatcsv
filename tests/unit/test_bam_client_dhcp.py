"""Tests for BAM client DHCP functionality."""

import pytest

from src.importer.bam.client import BAMClient
from src.importer.config import BAMConfig
from src.importer.utils.exceptions import BAMAPIError


class TestBAMClientDHCP:
    """Test BAMClient DHCP methods."""

    @pytest.fixture
    def client(self):
        """Create a BAMClient for testing."""
        config = BAMConfig(
            base_url="https://test.example.com",
            username="testuser",
            password="testpass",
            api_version="v2",
            timeout=30,
            verify_ssl=True,
            max_connections=50,
            max_keepalive=20,
        )
        return BAMClient(config=config)

    @pytest.mark.asyncio
    async def test_create_ipv4_dhcp_range_success(self, client, mocker):
        """Test successful IPv4 DHCP range creation."""
        mock_post = mocker.patch.object(client, "post")
        mock_post.return_value = {"id": 123, "name": "Test Range"}

        result = await client.create_ipv4_dhcp_range(
            config_id=1,
            network_id=456,
            name="Test Range",
            dhcp_range="10.1.1.100-10.1.1.200",
            split_around_static_addresses=True,
            low_water_mark=20,
            high_water_mark=80,
            custom_property="test-value",
        )

        assert result == {"id": 123, "name": "Test Range"}

        # Verify the correct payload was sent
        expected_payload = {
            "type": "IPv4DHCPRange",
            "name": "Test Range",
            "range": "10.1.1.100-10.1.1.200",
            "splitAroundStaticAddresses": True,
            "lowWaterMark": 20,
            "highWaterMark": 80,
            "custom_property": "test-value",
        }
        mock_post.assert_called_once_with("networks/456/ranges", json=expected_payload)

    @pytest.mark.asyncio
    async def test_create_ipv4_dhcp_range_minimal(self, client, mocker):
        """Test IPv4 DHCP range creation with minimal parameters."""
        mock_post = mocker.patch.object(client, "post")
        mock_post.return_value = {"id": 123}

        result = await client.create_ipv4_dhcp_range(
            config_id=1, network_id=456, name="Minimal Range", dhcp_range="10.1.1.100-10.1.1.110"
        )

        assert result == {"id": 123}

        expected_payload = {
            "type": "IPv4DHCPRange",
            "name": "Minimal Range",
            "range": "10.1.1.100-10.1.1.110",
            "splitAroundStaticAddresses": False,
        }
        mock_post.assert_called_once_with("networks/456/ranges", json=expected_payload)

    @pytest.mark.asyncio
    async def test_create_ipv4_dhcp_range_api_error(self, client, mocker):
        """Test IPv4 DHCP range creation with API error."""
        mock_post = mocker.patch.object(client, "post")
        mock_post.side_effect = BAMAPIError("Network not found", status_code=404)

        with pytest.raises(BAMAPIError) as exc_info:
            await client.create_ipv4_dhcp_range(
                config_id=1, network_id=999, name="Test Range", dhcp_range="10.1.1.100-10.1.1.200"
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_dhcp_endpoint_mapping_get_entity(self, client, mocker):
        """Test that DHCP entity types are correctly mapped for get operations."""
        mock_get = mocker.patch.object(client, "get")

        # Test each DHCP object type with their actual endpoint mappings
        dhcp_test_cases = [
            ("IPv4DHCPRange", 123, "ranges/123"),
            ("DHCPDeploymentRole", 654, "deploymentRoles/654"),
        ]

        for resource_type, entity_id, expected_endpoint in dhcp_test_cases:
            # Configure mock to return the correct ID for this iteration
            mock_get.return_value = {"id": entity_id, "name": "Test DHCP Range"}

            result = await client.get_entity_by_id(entity_id, resource_type)
            assert result == {"id": entity_id, "name": "Test DHCP Range"}
            mock_get.assert_called_with(expected_endpoint)

    @pytest.mark.asyncio
    async def test_dhcp_endpoint_mapping_update_entity(self, client, mocker):
        """Test that DHCP entity types are correctly mapped for update operations."""
        dhcp_test_cases = [
            ("IPv4DHCPRange", 123, "ranges/123"),
            ("DHCPDeploymentRole", 654, "deploymentRoles/654"),
        ]

        for resource_type, entity_id, expected_endpoint in dhcp_test_cases:
            # Configure mock to return the correct ID for this iteration
            # Mock request because update_entity_by_id uses PATCH via request()
            mock_request = mocker.patch.object(client, "request")
            mock_request.return_value = {"id": entity_id, "name": "Updated DHCP Range"}

            properties = {"name": "Updated"}
            result = await client.update_entity_by_id(entity_id, resource_type, properties)
            assert result == {"id": entity_id, "name": "Updated DHCP Range"}

            expected_payload = {"type": resource_type}
            expected_payload.update(properties)

            # The expected_endpoint already includes the resource and ID logic from get test
            # But wait, dhcp_test_cases defines expected_endpoint as e.g. "ranges/123"
            # update_entity_by_id calls request("PATCH", "{endpoint}/{id}")
            # If endpoint for type is "ranges", it calls "ranges/123".
            # The test case defines expected_endpoint as "ranges/123"
            # So we should match against expected_endpoint, NOT append entity_id again IF expected_endpoint is the full path.
            mock_request.assert_called_with("PATCH", expected_endpoint, json=expected_payload)

    @pytest.mark.asyncio
    async def test_dhcp_endpoint_mapping_delete_entity(self, client, mocker):
        """Test that DHCP entity types are correctly mapped for delete operations."""
        mock_delete = mocker.patch.object(client, "_delete")

        # Test each DHCP object type with their actual endpoint mappings
        dhcp_test_cases = [
            ("IPv4DHCPRange", 123, "ranges/123"),
            ("DHCPDeploymentRole", 654, "deploymentRoles/654"),
        ]

        for resource_type, entity_id, expected_endpoint in dhcp_test_cases:
            # Reset the mock for each iteration and configure response
            mock_delete.reset_mock()
            mock_delete.return_value = {"id": entity_id, "status": "success"}

            result = await client.delete_entity_by_id(
                entity_id, resource_type, allow_dangerous_operations=False
            )
            assert result is None
            mock_delete.assert_called_once_with(expected_endpoint)

    @pytest.mark.asyncio
    async def test_dhcp_endpoint_mapping_delete_entity_dangerous(self, client, mocker):
        """Test that DHCP entity types are NOT blocked by safety protection."""
        mock_delete = mocker.patch.object(client, "_delete")
        mock_delete.return_value = {"id": 123, "status": "success"}

        # DHCP objects should NOT be blocked by dangerous operations protection
        result = await client.delete_entity_by_id(
            123, "IPv4DHCPRange", allow_dangerous_operations=False
        )
        assert result is None
        mock_delete.assert_called_once_with("ranges/123")

    @pytest.mark.asyncio
    async def test_create_dhcpv4_client_deployment_option_success(self, client, mocker):
        """Test successful DHCPv4 client deployment option creation."""
        mock_post = mocker.patch.object(client, "post")
        mock_post.return_value = {
            "id": 789,
            "name": "DNS Servers",
            "code": 6,
            "value": "8.8.8.8,8.8.4.4",
        }

        result = await client.create_dhcpv4_client_deployment_option(
            network_id=456,
            name="DNS Servers",
            code=6,
            value="8.8.8.8,8.8.4.4",
            server_scope="DHCP_SERVER",
            custom_property="test-value",
        )

        assert result == {"id": 789, "name": "DNS Servers", "code": 6, "value": "8.8.8.8,8.8.4.4"}

        # Verify the correct endpoint and payload were sent
        mock_post.assert_called_once_with(
            "networks/456/deploymentOptions",
            json={
                "name": "DNS Servers",
                "code": 6,
                "value": "8.8.8.8,8.8.4.4",
                "custom_property": "test-value",
                "type": "DHCPv4ClientOption",
            },
        )

    @pytest.mark.asyncio
    async def test_create_dhcpv4_client_deployment_option_minimal(self, client, mocker):
        """Test DHCPv4 client deployment option creation with minimal parameters."""
        mock_post = mocker.patch.object(client, "post")
        mock_post.return_value = {"id": 790, "name": "Domain Name", "code": 15}

        result = await client.create_dhcpv4_client_deployment_option(
            network_id=456, name="Domain Name", code=15, value="example.com"
        )

        assert result == {"id": 790, "name": "Domain Name", "code": 15}

        # Verify the correct endpoint and minimal payload were sent
        mock_post.assert_called_once_with(
            "networks/456/deploymentOptions",
            json={
                "name": "Domain Name",
                "code": 15,
                "value": "example.com",
                "type": "DHCPv4ClientOption",
            },
        )

    @pytest.mark.asyncio
    async def test_create_dhcpv4_client_deployment_option_invalid_code(self, client):
        """Test that invalid DHCP option codes are rejected."""
        with pytest.raises(ValueError) as exc_info:
            await client.create_dhcpv4_client_deployment_option(
                network_id=456,
                name="Invalid Option",
                code=300,  # Invalid code (> 254)
                value="test",
            )

        assert "DHCP option code must be between 1 and 254" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_dhcpv4_client_deployment_option_invalid_scope(self, client):
        """Test that invalid server scopes are rejected."""
        with pytest.raises(ValueError) as exc_info:
            await client.create_dhcpv4_client_deployment_option(
                network_id=456,
                name="Invalid Scope",
                code=6,
                value="test",
                server_scope="INVALID_SCOPE",
            )

        assert "Invalid server scope: INVALID_SCOPE" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_dhcpv4_service_deployment_option_success(self, client, mocker):
        """Test successful DHCPv4 service deployment option creation."""
        mock_post = mocker.patch.object(client, "post")
        mock_post.return_value = {
            "id": 791,
            "name": "Default Lease Time",
            "code": 51,
            "value": "86400",
        }

        result = await client.create_dhcpv4_service_deployment_option(
            network_id=456,
            name="Default Lease Time",
            code=51,
            value=86400,
            server_scope="DHCP_SERVER",
        )

        assert result == {"id": 791, "name": "Default Lease Time", "code": 51, "value": "86400"}

        # Verify the correct endpoint and payload were sent
        mock_post.assert_called_once_with(
            "networks/456/deploymentOptions",
            json={
                "name": "Default Lease Time",
                "code": 51,
                "value": 86400,
                "type": "DHCPv4ServiceOption",
            },
        )

    @pytest.mark.asyncio
    async def test_update_dhcp_deployment_option_success(self, client, mocker):
        """Test successful DHCP deployment option update."""
        mock_put = mocker.patch.object(client, "put")
        mock_put.return_value = {
            "id": 789,
            "name": "Updated DNS Servers",
            "value": "1.1.1.1,1.0.0.1",
        }

        result = await client.update_dhcp_deployment_option(
            option_id=789,
            name="Updated DNS Servers",
            value="1.1.1.1,1.0.0.1",
            server_scope="ALL_SERVERS",
        )

        assert result == {"id": 789, "name": "Updated DNS Servers", "value": "1.1.1.1,1.0.0.1"}

        # Verify the correct endpoint and payload were sent
        mock_put.assert_called_once_with(
            "deploymentOptions/789",
            json={
                "name": "Updated DNS Servers",
                "value": "1.1.1.1,1.0.0.1",
                "serverScope": "ALL_SERVERS",
            },
        )

    @pytest.mark.asyncio
    async def test_update_dhcp_deployment_option_partial_update(self, client, mocker):
        """Test DHCP deployment option update with only some fields."""
        mock_put = mocker.patch.object(client, "put")
        mock_put.return_value = {"id": 789, "value": "new-value"}

        result = await client.update_dhcp_deployment_option(option_id=789, value="new-value")

        assert result == {"id": 789, "value": "new-value"}

        # Verify only the provided field was sent
        mock_put.assert_called_once_with("deploymentOptions/789", json={"value": "new-value"})

    @pytest.mark.asyncio
    async def test_update_dhcp_deployment_option_no_fields(self, client):
        """Test that DHCP deployment option update requires at least one field."""
        with pytest.raises(ValueError) as exc_info:
            await client.update_dhcp_deployment_option(option_id=789)

        assert "At least one field must be provided for update" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_dhcp_deployment_option_invalid_scope(self, client):
        """Test that invalid server scopes are rejected during update."""
        with pytest.raises(ValueError) as exc_info:
            await client.update_dhcp_deployment_option(option_id=789, server_scope="INVALID_SCOPE")

        assert "Invalid server scope: INVALID_SCOPE" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_dhcp_deployment_option_success(self, client, mocker):
        """Test successful DHCP deployment option deletion."""
        mock_delete = mocker.patch.object(client, "_delete")
        mock_delete.return_value = None

        result = await client.delete_dhcp_deployment_option(option_id=789)

        assert result is None

        # Verify the correct endpoint was called
        mock_delete.assert_called_once_with("deploymentOptions/789")

    @pytest.mark.asyncio
    async def test_get_deployment_options_in_network_success(self, client, mocker):
        """Test successful retrieval of deployment options in a network."""
        mock_get = mocker.patch.object(client, "get")
        mock_get.return_value = {
            "data": [
                {"id": 789, "name": "DNS Servers", "code": 6, "type": "DHCPv4ClientOption"},
                {
                    "id": 790,
                    "name": "Default Lease Time",
                    "code": 51,
                    "type": "DHCPv4ServiceOption",
                },
            ]
        }

        result = await client.get_deployment_options_in_network(network_id=456)

        assert len(result) == 2
        assert result[0]["id"] == 789
        assert result[0]["name"] == "DNS Servers"
        assert result[1]["id"] == 790
        assert result[1]["name"] == "Default Lease Time"

        # Verify the correct endpoint was called
        mock_get.assert_called_once_with("networks/456/deploymentOptions", params={})

    @pytest.mark.asyncio
    async def test_get_deployment_options_in_network_with_filter(self, client, mocker):
        """Test retrieval of deployment options with type filter."""
        mock_get = mocker.patch.object(client, "get")
        mock_get.return_value = {
            "data": [{"id": 789, "name": "DNS Servers", "code": 6, "type": "DHCPv4ClientOption"}]
        }

        result = await client.get_deployment_options_in_network(
            network_id=456, option_type="DHCPv4ClientOption"
        )

        assert len(result) == 1
        assert result[0]["type"] == "DHCPv4ClientOption"

        # Verify the correct endpoint and parameters were called
        mock_get.assert_called_once_with(
            "networks/456/deploymentOptions", params={"type": "DHCPv4ClientOption"}
        )

    @pytest.mark.asyncio
    async def test_create_dhcpv4_client_deployment_option_api_error(self, client, mocker):
        """Test handling of API errors during DHCP deployment option creation."""
        mock_post = mocker.patch.object(client, "post")
        mock_post.side_effect = BAMAPIError("API Error", status_code=400)

        with pytest.raises(BAMAPIError):
            await client.create_dhcpv4_client_deployment_option(
                network_id=456, name="Test Option", code=6, value="test"
            )

    @pytest.mark.asyncio
    async def test_boundary_codes_deployment_options(self, client, mocker):
        """Test DHCP deployment option creation with boundary codes."""
        mock_post = mocker.patch.object(client, "post")
        mock_post.return_value = {"id": 999}

        # Test minimum valid code
        await client.create_dhcpv4_service_deployment_option(
            network_id=456, name="Min Code", code=1, value="test"  # Minimum valid code
        )

        # Test maximum valid code
        await client.create_dhcpv4_service_deployment_option(
            network_id=456, name="Max Code", code=254, value="test"  # Maximum valid code
        )

        assert mock_post.call_count == 2

        # Test invalid code below minimum
        with pytest.raises(ValueError) as exc_info:
            await client.create_dhcpv4_service_deployment_option(
                network_id=456, name="Invalid Min Code", code=0, value="test"  # Invalid code (< 1)
            )
        assert "DHCP option code must be between 1 and 254" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_ipv4_dhcp_range_simple(self, client, mocker):
        """Test the simple DHCP range creation method with separate start/end IPs."""
        mock_post = mocker.patch.object(client, "post")
        mock_post.return_value = {"id": 123, "start": "10.1.1.100", "end": "10.1.1.200"}

        result = await client.create_ipv4_dhcp_range_simple(
            network_id=456,
            start_ip="10.1.1.100",
            end_ip="10.1.1.200",
            properties={"description": "Test range"},
        )

        assert result == {"id": 123, "start": "10.1.1.100", "end": "10.1.1.200"}

        # Verify the correct payload was sent
        expected_payload = {
            "type": "IPv4DHCPRange",
            "range": "10.1.1.100-10.1.1.200",
            "start": "10.1.1.100",
            "end": "10.1.1.200",
            "userDefinedFields": {"description": "Test range"},
        }
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]["json"] == expected_payload

    @pytest.mark.asyncio
    async def test_create_ipv4_dhcp_range_simple_minimal(self, client, mocker):
        """Test simple DHCP range creation without optional properties."""
        mock_post = mocker.patch.object(client, "post")
        mock_post.return_value = {"id": 124}

        result = await client.create_ipv4_dhcp_range_simple(
            network_id=456,
            start_ip="10.1.1.50",
            end_ip="10.1.1.60",
        )

        assert result == {"id": 124}

        # Verify no userDefinedFields when properties not provided
        expected_payload = {
            "type": "IPv4DHCPRange",
            "range": "10.1.1.50-10.1.1.60",
            "start": "10.1.1.50",
            "end": "10.1.1.60",
        }
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]["json"] == expected_payload

    @pytest.mark.asyncio
    async def test_create_dhcpv4_client_deployment_option_non_default_scope(self, client, mocker):
        """Test that non-default server scope is included in payload."""
        mock_post = mocker.patch.object(client, "post")
        mock_post.return_value = {"id": 800}

        await client.create_dhcpv4_client_deployment_option(
            network_id=456,
            name="All Servers Option",
            code=6,
            value="8.8.8.8",
            server_scope="ALL_SERVERS",
        )

        # Verify serverScope is included for non-default value
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["serverScope"] == "ALL_SERVERS"

    @pytest.mark.asyncio
    async def test_create_dhcpv4_service_deployment_option_non_default_scope(self, client, mocker):
        """Test that non-default server scope is included in service option payload."""
        mock_post = mocker.patch.object(client, "post")
        mock_post.return_value = {"id": 801}

        await client.create_dhcpv4_service_deployment_option(
            network_id=456,
            name="DNS Server Option",
            code=6,
            value="1.1.1.1",
            server_scope="DNS_SERVER",
        )

        # Verify serverScope is included for non-default value
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["serverScope"] == "DNS_SERVER"

    @pytest.mark.asyncio
    async def test_create_dhcpv4_service_deployment_option_invalid_scope(self, client):
        """Test that invalid server scopes are rejected for service options."""
        with pytest.raises(ValueError) as exc_info:
            await client.create_dhcpv4_service_deployment_option(
                network_id=456,
                name="Invalid Scope",
                code=6,
                value="test",
                server_scope="INVALID_SCOPE",
            )

        assert "Invalid server scope: INVALID_SCOPE" in str(exc_info.value)
