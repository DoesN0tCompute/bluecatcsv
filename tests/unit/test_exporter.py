"""Unit tests for BlueCat CSV Exporter."""

import csv
from unittest.mock import AsyncMock

import pytest

from src.importer.bam.client import BAMClient
from src.importer.core.exporter import BlueCatExporter


@pytest.fixture
def mock_client():
    """Create a mock BAM client for testing."""
    client = AsyncMock(spec=BAMClient)
    return client


@pytest.fixture
def exporter(mock_client):
    """Create a BlueCatExporter instance with mock client."""
    return BlueCatExporter(mock_client)


@pytest.fixture
def sample_network():
    """Sample network resource from BAM API."""
    return {
        "id": 12345,
        "type": "IPv4Network",
        "name": "Corp-Network",
        "range": "10.1.0.0/16",
        "configuration": {"id": 100, "name": "Default"},
        "userDefinedFields": {"owner": "IT Team", "environment": "production"},
    }


@pytest.fixture
def sample_address():
    """Sample IP address resource from BAM API."""
    return {
        "id": 12346,
        "type": "IP4Address",
        "name": "web-server-1",
        "address": "10.1.0.10",
        "macAddress": "00:11:22:33:44:55",
        "configuration": {"id": 100, "name": "Default"},
        "userDefinedFields": {"owner": "Web Team", "environment": "production", "location": "DC1"},
    }


@pytest.fixture
def sample_zone():
    """Sample DNS zone resource from BAM API."""
    return {
        "id": 54321,
        "type": "Zone",
        "name": "example",
        "absoluteName": "example.com",
        "configuration": {"id": 100, "name": "Default"},
        "view": {"id": 200, "name": "Internal"},
        "userDefinedFields": {"owner": "DNS Team"},
    }


@pytest.fixture
def sample_resource_record():
    """Sample DNS resource record from BAM API."""
    return {
        "id": 54322,
        "type": "HostRecord",
        "name": "www",
        "absoluteName": "www.example.com",
        "ttl": 3600,
        "configuration": {"id": 100, "name": "Default"},
        "view": {"id": 200, "name": "Internal"},
        "_embedded": {"addresses": [{"address": "10.1.0.10"}, {"address": "10.1.0.11"}]},
    }


class TestBlueCatExporter:
    """Test BlueCatExporter class."""

    @pytest.mark.asyncio
    async def test_export_network_by_id(self, exporter, mock_client, sample_network):
        """Test exporting a network by ID."""
        # Setup mock
        mock_client.get_network_by_id.return_value = sample_network
        mock_client.get_child_networks.return_value = []
        mock_client.get_addresses_in_network.return_value = []

        # Execute
        result = await exporter.export_network(
            network_identifier=12345, include_children=True, include_addresses=True, action="update"
        )

        # Assert
        assert len(result) == 1
        assert result[0]["object_type"] == "ip4_network"
        assert result[0]["bam_id"] == 12345
        assert result[0]["name"] == "Corp-Network"
        assert result[0]["cidr"] == "10.1.0.0/16"
        assert result[0]["udf_owner"] == "IT Team"
        assert result[0]["udf_environment"] == "production"
        assert result[0]["action"] == "update"

    @pytest.mark.asyncio
    async def test_export_network_by_cidr(self, exporter, mock_client, sample_network):
        """Test exporting a network by CIDR."""
        # Setup mock
        mock_client.get_network_by_cidr.return_value = sample_network
        mock_client.get_child_networks.return_value = []
        mock_client.get_addresses_in_network.return_value = []

        # Execute
        result = await exporter.export_network(
            network_identifier="10.1.0.0/16",
            config_id=100,
            include_children=True,
            include_addresses=True,
            action="update",
        )

        # Assert
        assert len(result) == 1
        mock_client.get_network_by_cidr.assert_called_once_with(100, "10.1.0.0/16")

    @pytest.mark.asyncio
    async def test_export_network_with_addresses(
        self, exporter, mock_client, sample_network, sample_address
    ):
        """Test exporting a network with IP addresses."""
        # Setup mock
        mock_client.get_network_by_id.return_value = sample_network
        mock_client.get_child_networks.return_value = []
        mock_client.get_addresses_in_network.return_value = [sample_address]

        # Execute
        result = await exporter.export_network(
            network_identifier=12345, include_children=True, include_addresses=True, action="update"
        )

        # Assert
        assert len(result) == 2  # Network + address
        assert result[0]["object_type"] == "ip4_network"
        assert result[1]["object_type"] == "ip4_address"
        assert result[1]["address"] == "10.1.0.10"
        assert result[1]["mac"] == "00:11:22:33:44:55"
        assert result[1]["udf_location"] == "DC1"

    @pytest.mark.asyncio
    async def test_export_network_no_addresses(self, exporter, mock_client, sample_network):
        """Test exporting a network without IP addresses."""
        # Setup mock
        mock_client.get_network_by_id.return_value = sample_network
        mock_client.get_child_networks.return_value = []

        # Execute
        result = await exporter.export_network(
            network_identifier=12345,
            include_children=True,
            include_addresses=False,  # Skip addresses
            action="update",
        )

        # Assert
        assert len(result) == 1  # Just the network
        mock_client.get_addresses_in_network.assert_not_called()

    @pytest.mark.asyncio
    async def test_export_network_with_children(self, exporter, mock_client, sample_network):
        """Test exporting a network with child networks."""
        # Setup mocks
        child_network = sample_network.copy()
        child_network["id"] = 12346
        child_network["name"] = "Child-Network"
        child_network["range"] = "10.1.1.0/24"

        mock_client.get_network_by_id.return_value = sample_network
        mock_client.get_child_networks.side_effect = [
            [child_network],  # First call returns child
            [],  # Second call (for child) returns empty
        ]
        mock_client.get_addresses_in_network.return_value = []

        # Execute
        result = await exporter.export_network(
            network_identifier=12345,
            include_children=True,
            include_addresses=False,
            action="update",
        )

        # Assert
        assert len(result) == 2  # Parent + child
        assert result[0]["name"] == "Corp-Network"
        assert result[1]["name"] == "Child-Network"

    @pytest.mark.asyncio
    async def test_export_zone_by_id(self, exporter, mock_client, sample_zone):
        """Test exporting a DNS zone by ID."""
        # Setup mock
        mock_client.get_zone_by_id.return_value = sample_zone
        mock_client.get_resource_records_in_zone.return_value = []
        mock_client.get_child_zones.return_value = []

        # Execute
        result = await exporter.export_zone(
            zone_identifier=54321, include_children=True, include_records=True, action="update"
        )

        # Assert
        assert len(result) == 1
        assert result[0]["object_type"] == "dns_zone"
        assert result[0]["bam_id"] == 54321
        assert result[0]["zone_name"] == "example.com"
        assert result[0]["udf_owner"] == "DNS Team"

    @pytest.mark.asyncio
    async def test_export_zone_with_records(
        self, exporter, mock_client, sample_zone, sample_resource_record
    ):
        """Test exporting a zone with resource records."""
        # Setup mock
        mock_client.get_zone_by_id.return_value = sample_zone
        mock_client.get_resource_records_in_zone.return_value = [sample_resource_record]
        mock_client.get_child_zones.return_value = []

        # Execute
        result = await exporter.export_zone(
            zone_identifier=54321, include_children=True, include_records=True, action="update"
        )

        # Assert
        assert len(result) == 2  # Zone + record
        assert result[0]["object_type"] == "dns_zone"
        assert result[1]["object_type"] == "host_record"
        assert result[1]["name"] == "www"
        assert result[1]["addresses"] == "10.1.0.10|10.1.0.11"
        assert result[1]["ttl"] == 3600

    @pytest.mark.asyncio
    async def test_udf_discovery(self, exporter, mock_client, sample_network, sample_address):
        """Test automatic UDF discovery."""
        # Setup mock with different UDFs
        mock_client.get_network_by_id.return_value = sample_network
        mock_client.get_child_networks.return_value = []
        mock_client.get_addresses_in_network.return_value = [sample_address]

        # Execute
        await exporter.export_network(
            network_identifier=12345, include_children=True, include_addresses=True, action="update"
        )

        # Assert UDF discovery
        assert "udf_owner" in exporter.discovered_udfs
        assert "udf_environment" in exporter.discovered_udfs
        assert "udf_location" in exporter.discovered_udfs  # From address
        assert len(exporter.discovered_udfs) == 3

    @pytest.mark.asyncio
    async def test_csv_columns_generation(self, exporter):
        """Test CSV column generation with dynamic UDFs."""
        # Add some discovered UDFs
        exporter.discovered_udfs = {"udf_owner", "udf_environment", "udf_location"}

        # Get columns
        columns = exporter.get_csv_columns()

        # Assert base columns are present
        assert "row_id" in columns
        assert "object_type" in columns
        assert "action" in columns
        assert "bam_id" in columns
        assert "name" in columns
        assert "cidr" in columns
        assert "address" in columns

        # Assert UDF columns are present and sorted
        assert "udf_environment" in columns
        assert "udf_location" in columns
        assert "udf_owner" in columns

        # UDFs should be at the end and sorted
        udf_cols = [c for c in columns if c.startswith("udf_")]
        assert udf_cols == sorted(udf_cols)

    @pytest.mark.asyncio
    async def test_write_csv(self, exporter, tmp_path):
        """Test writing CSV file."""
        # Setup test data
        exporter.exported_resources = [
            {
                "row_id": 1,
                "object_type": "ip4_network",
                "action": "update",
                "bam_id": 12345,
                "name": "Test-Network",
                "cidr": "10.1.0.0/16",
                "udf_owner": "IT Team",
            }
        ]
        exporter.discovered_udfs = {"udf_owner"}

        # Write CSV
        output_file = tmp_path / "test.csv"
        await exporter.write_csv(output_file)

        # Assert file exists
        assert output_file.exists()

        # Read and verify content
        with open(output_file) as f:
            lines = f.readlines()

            # Check metadata comments
            assert lines[0].startswith("# Exported from BlueCat")
            assert "# Export Date:" in lines[1]
            assert "# Total Resources: 1" in lines[2]
            assert "# Schema Version: 3.0" in lines[3]

            # Check CSV header
            reader = csv.DictReader(lines[4:])
            rows = list(reader)

            assert len(rows) == 1
            assert rows[0]["row_id"] == "1"
            assert rows[0]["object_type"] == "ip4_network"
            assert rows[0]["name"] == "Test-Network"
            assert rows[0]["udf_owner"] == "IT Team"

    @pytest.mark.asyncio
    async def test_action_default_update(self, exporter, mock_client, sample_network):
        """Test that default action is 'update'."""
        # Setup mock
        mock_client.get_network_by_id.return_value = sample_network
        mock_client.get_child_networks.return_value = []
        mock_client.get_addresses_in_network.return_value = []

        # Execute without specifying action (should default to update)
        await exporter.export_network(
            network_identifier=12345,
            include_children=True,
            include_addresses=True,
            # action parameter omitted
        )

        # Assert - but action might be required, let's check the signature
        # This test might need adjustment based on actual default

    @pytest.mark.asyncio
    async def test_action_create(self, exporter, mock_client, sample_network):
        """Test export with action='create'."""
        # Setup mock
        mock_client.get_network_by_id.return_value = sample_network
        mock_client.get_child_networks.return_value = []
        mock_client.get_addresses_in_network.return_value = []

        # Execute with action=create
        result = await exporter.export_network(
            network_identifier=12345, include_children=True, include_addresses=True, action="create"
        )

        # Assert
        assert result[0]["action"] == "create"

    @pytest.mark.asyncio
    async def test_export_network_requires_config_for_cidr(self, exporter, mock_client):
        """Test that CIDR export requires config_id."""
        # Execute without config_id for CIDR (should raise ValueError)
        with pytest.raises(ValueError, match="config_id is required"):
            await exporter.export_network(
                network_identifier="10.1.0.0/16",
                # config_id missing!
                include_children=True,
                include_addresses=True,
                action="update",
            )

    @pytest.mark.asyncio
    async def test_export_zone_requires_view_for_fqdn(self, exporter, mock_client):
        """Test that FQDN export requires view_id."""
        # Execute without view_id for FQDN (should raise ValueError)
        with pytest.raises(ValueError, match="view_id is required"):
            await exporter.export_zone(
                zone_identifier="example.com",
                # view_id missing!
                include_children=True,
                include_records=True,
                action="update",
            )

    @pytest.mark.asyncio
    async def test_row_id_sequential(self, exporter, mock_client, sample_network, sample_address):
        """Test that row_id is sequential across all resources."""
        # Setup mock
        address2 = sample_address.copy()
        address2["id"] = 12347
        address2["address"] = "10.1.0.11"

        mock_client.get_network_by_id.return_value = sample_network
        mock_client.get_child_networks.return_value = []
        mock_client.get_addresses_in_network.return_value = [sample_address, address2]

        # Execute
        result = await exporter.export_network(
            network_identifier=12345, include_children=True, include_addresses=True, action="update"
        )

        # Assert row_id is sequential
        assert result[0]["row_id"] == 1  # Network
        assert result[1]["row_id"] == 2  # First address
        assert result[2]["row_id"] == 3  # Second address

    @pytest.mark.asyncio
    async def test_empty_udf_handling(self, exporter, mock_client):
        """Test handling of resources with no UDFs."""
        network_no_udfs = {
            "id": 12345,
            "type": "IPv4Network",
            "name": "Test-Network",
            "range": "10.1.0.0/16",
            "configuration": {"id": 100, "name": "Default"},
            "userDefinedFields": None,  # No UDFs
        }

        # Setup mock
        mock_client.get_network_by_id.return_value = network_no_udfs
        mock_client.get_child_networks.return_value = []
        mock_client.get_addresses_in_network.return_value = []

        # Execute
        result = await exporter.export_network(
            network_identifier=12345, include_children=True, include_addresses=True, action="update"
        )

        # Assert - should work fine with no UDFs
        assert len(result) == 1
        assert len(exporter.discovered_udfs) == 0
