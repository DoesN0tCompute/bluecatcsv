"""Tests for BAMClient safety features."""

import httpx
import pytest
import respx

from src.importer.bam.client import BAMClient
from src.importer.config import BAMConfig


class TestBAMClientSafety:
    """Test BAMClient safety features for dangerous operations."""

    @pytest.fixture
    def client(self, mock_auth):
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

    @pytest.fixture(autouse=True)
    def mock_auth(self):
        """Mock authentication for all tests."""
        with respx.mock(assert_all_called=False):
            respx.post("https://test.example.com/api/v2/sessions").mock(
                return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
            )
            yield

    @pytest.mark.asyncio
    async def test_delete_entity_by_id_safe_operations(self, client, mocker):
        """Test that safe deletions work normally."""
        # Mock the HTTP delete method
        mock_delete = mocker.patch.object(client, "_delete")
        mock_delete.return_value = None

        # Test safe resource types
        safe_types = ["IPv4Address", "HostRecord"]

        for resource_type in safe_types:
            result = await client.delete_entity_by_id(123, resource_type)
            assert result is None
            if resource_type == "IPv4Address":
                expected_endpoint = "addresses/123"
            else:  # HostRecord
                expected_endpoint = "resourceRecords/123"
            mock_delete.assert_called_with(expected_endpoint)

    @pytest.mark.asyncio
    async def test_delete_entity_by_id_block_configuration_without_flag(self, client):
        """Test that configuration deletion is blocked without flag."""
        with pytest.raises(PermissionError) as exc_info:
            await client.delete_entity_by_id(123, "Configuration")

        error_msg = str(exc_info.value)
        assert "CRITICAL SAFETY" in error_msg
        assert "Configuration" in error_msg
        assert "ID: 123" in error_msg
        assert "--allow-dangerous-operations" in error_msg
        assert "significant data loss" in error_msg

    @pytest.mark.asyncio
    async def test_delete_entity_by_id_block_view_without_flag(self, client):
        """Test that view deletion is blocked without flag."""
        with pytest.raises(PermissionError) as exc_info:
            await client.delete_entity_by_id(456, "View")

        error_msg = str(exc_info.value)
        assert "CRITICAL SAFETY" in error_msg
        assert "View" in error_msg
        assert "ID: 456" in error_msg
        assert "--allow-dangerous-operations" in error_msg

    @pytest.mark.asyncio
    async def test_delete_entity_by_id_block_block_without_flag(self, client):
        """Test that block deletion is blocked without flag."""
        with pytest.raises(PermissionError) as exc_info:
            await client.delete_entity_by_id(789, "IPv4Block")

        error_msg = str(exc_info.value)
        assert "HIGH-RISK SAFETY" in error_msg
        assert "IPv4Block" in error_msg
        assert "ID: 789" in error_msg
        assert "--allow-dangerous-operations" in error_msg

    @pytest.mark.asyncio
    async def test_delete_entity_by_id_block_network_without_flag(self, client):
        """Test that network deletion is blocked without flag."""
        with pytest.raises(PermissionError) as exc_info:
            await client.delete_entity_by_id(101112, "IPv4Network")

        error_msg = str(exc_info.value)
        assert "HIGH-RISK SAFETY" in error_msg
        assert "IPv4Network" in error_msg
        assert "ID: 101112" in error_msg
        assert "--allow-dangerous-operations" in error_msg

    @pytest.mark.asyncio
    async def test_delete_entity_by_id_block_zone_without_flag(self, client):
        """Test that zone deletion is blocked without flag."""
        with pytest.raises(PermissionError) as exc_info:
            await client.delete_entity_by_id(131415, "DNSZone")

        error_msg = str(exc_info.value)
        assert "HIGH-RISK SAFETY" in error_msg
        assert "DNSZone" in error_msg
        assert "ID: 131415" in error_msg
        assert "--allow-dangerous-operations" in error_msg

    @pytest.mark.asyncio
    async def test_delete_entity_by_id_allow_configuration_with_flag(self, client, mocker):
        """Test that configuration deletion works with flag."""
        mock_delete = mocker.patch.object(client, "_delete")
        mock_delete.return_value = None

        result = await client.delete_entity_by_id(
            123, "Configuration", allow_dangerous_operations=True
        )

        assert result is None
        mock_delete.assert_called_once_with("configurations/123")

    @pytest.mark.asyncio
    async def test_delete_entity_by_id_allow_view_with_flag(self, client, mocker):
        """Test that view deletion works with flag."""
        mock_delete = mocker.patch.object(client, "_delete")
        mock_delete.return_value = None

        result = await client.delete_entity_by_id(456, "View", allow_dangerous_operations=True)

        assert result is None
        mock_delete.assert_called_once_with("views/456")

    @pytest.mark.asyncio
    async def test_delete_entity_by_id_block_unsupported_type(self, client):
        """Test that unsupported resource types are blocked."""
        with pytest.raises(ValueError) as exc_info:
            await client.delete_entity_by_id(123, "UnsupportedType")

        assert "Unsupported resource type for entity deletion" in str(exc_info.value)
        assert "UnsupportedType" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_entity_by_id_handles_api_error(self, client, mocker):
        """Test that API errors are properly handled."""
        from src.importer.utils.exceptions import BAMAPIError

        mock_delete = mocker.patch.object(client, "_delete")
        mock_delete.side_effect = BAMAPIError("Not found", status_code=404)

        with pytest.raises(BAMAPIError):
            await client.delete_entity_by_id(123, "IPv4Address")

    @pytest.mark.asyncio
    async def test_delete_entity_by_id_allows_all_safe_types(self, client, mocker):
        """Test that all safe resource types work."""
        mock_delete = mocker.patch.object(client, "_delete")
        mock_delete.return_value = None

        safe_endpoints = {
            "IPv4Address": "addresses/123",
            "HostRecord": "resourceRecords/123",
        }

        for resource_type, expected_endpoint in safe_endpoints.items():
            result = await client.delete_entity_by_id(123, resource_type)
            assert result is None
            mock_delete.assert_called_with(expected_endpoint)

    @pytest.mark.asyncio
    async def test_delete_entity_by_id_dangerous_flag_defaults_to_false(self, client):
        """Test that dangerous operations flag defaults to False."""
        with pytest.raises(PermissionError):
            await client.delete_entity_by_id(
                123, "Configuration"
            )  # No flag provided, should default to False

    @pytest.mark.asyncio
    async def test_delete_entity_by_id_explicit_false_flag(self, client):
        """Test that explicitly setting flag to False blocks operations."""
        with pytest.raises(PermissionError):
            await client.delete_entity_by_id(123, "Configuration", allow_dangerous_operations=False)

    @pytest.mark.asyncio
    async def test_delete_entity_by_id_dangerous_operations_with_logging(
        self, client, mocker, caplog
    ):
        """Test that dangerous operations are properly logged."""
        mock_logger = mocker.patch("src.importer.bam.client.logger")

        with pytest.raises(PermissionError):
            await client.delete_entity_by_id(123, "Configuration")

        # Verify error logging
        mock_logger.error.assert_called_once_with(
            "PROTECTED OPERATION BLOCKED",
            resource_type="Configuration",
            entity_id=123,
            risk_level="CRITICAL",
            reason="Deletion of critical resources requires --allow-dangerous-operations flag",
        )
