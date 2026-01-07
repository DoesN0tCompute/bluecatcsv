"""Integration tests for export workflow."""

import csv

import pytest
import respx
from httpx import Response

from src.importer.bam.client import BAMClient
from src.importer.config import BAMConfig
from src.importer.core.exporter import BlueCatExporter


@pytest.fixture
def bam_client_config():
    """BAM client configuration."""
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
async def authenticated_client(bam_client_config):
    """Create authenticated BAM client with mocked API."""
    with respx.mock:
        # Mock authentication
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=Response(
                201, json={"apiToken": "test-token", "basicAuthenticationCredentials": "test-creds"}
            )
        )

        config = BAMConfig(
            base_url=bam_client_config["base_url"],
            username=bam_client_config["username"],
            password=bam_client_config["password"],
            api_version=bam_client_config["api_version"],
            timeout=bam_client_config["timeout"],
            verify_ssl=bam_client_config["verify_ssl"],
            max_connections=bam_client_config["max_connections"],
            max_keepalive=bam_client_config["max_keepalive"],
        )
        client = BAMClient(config=config)
        await client.authenticate()
        yield client
        await client.close()


class TestNetworkExportIntegration:
    """Integration tests for network export workflow."""

    @pytest.mark.asyncio
    async def test_export_network_with_hierarchy(self, authenticated_client, tmp_path):
        """Test complete network export with children and addresses."""
        # Mock data
        parent_network = {
            "id": 12345,
            "type": "IPv4Network",
            "name": "Corp-Network",
            "range": "10.1.0.0/16",
            "configuration": {"id": 100, "name": "Default"},
            "userDefinedFields": {
                "owner": "IT Team",
                "environment": "production",
            },
        }

        child_network = {
            "id": 12346,
            "type": "IPv4Network",
            "name": "Corp-Subnet-1",
            "range": "10.1.1.0/24",
            "configuration": {"id": 100, "name": "Default"},
            "userDefinedFields": {
                "owner": "IT Team",
                "environment": "production",
            },
        }

        address1 = {
            "id": 12347,
            "type": "IP4Address",
            "name": "web-server-1",
            "address": "10.1.1.10",
            "macAddress": "00:11:22:33:44:55",
            "configuration": {"id": 100, "name": "Default"},
            "userDefinedFields": {
                "owner": "Web Team",
                "environment": "production",
                "location": "DC1",
            },
        }

        address2 = {
            "id": 12348,
            "type": "IP4Address",
            "name": "db-server-1",
            "address": "10.1.1.20",
            "macAddress": "00:11:22:33:44:66",
            "configuration": {"id": 100, "name": "Default"},
            "userDefinedFields": {
                "owner": "Database Team",
                "environment": "production",
                "location": "DC1",
            },
        }

        with respx.mock:
            # Mock API calls
            respx.get("https://bam.example.com/api/v2/networks/12345").mock(
                return_value=Response(200, json=parent_network)
            )

            respx.get("https://bam.example.com/api/v2/blocks/12345/networks").mock(
                return_value=Response(
                    200,
                    json={
                        "_embedded": {"networks": [child_network]},
                        "page": {"totalElements": 1},
                    },
                )
            )

            respx.get("https://bam.example.com/api/v2/networks/12345/addresses").mock(
                return_value=Response(
                    200,
                    json={
                        "_embedded": {"addresses": []},
                        "page": {"totalElements": 0},
                    },
                )
            )

            respx.get("https://bam.example.com/api/v2/blocks/12346/networks").mock(
                return_value=Response(
                    200,
                    json={
                        "_embedded": {"networks": []},
                        "page": {"totalElements": 0},
                    },
                )
            )

            respx.get("https://bam.example.com/api/v2/networks/12346/addresses").mock(
                return_value=Response(
                    200,
                    json={
                        "_embedded": {"addresses": [address1, address2]},
                        "page": {"totalElements": 2},
                    },
                )
            )

            # Execute export
            exporter = BlueCatExporter(authenticated_client)
            await exporter.export_network(
                network_identifier=12345,
                include_children=True,
                include_addresses=True,
                action="update",
            )

            # Write CSV
            output_file = tmp_path / "network_export.csv"
            await exporter.write_csv(output_file)

            # Verify CSV file exists
            assert output_file.exists()

            # Read and verify CSV contents
            with open(output_file) as f:
                lines = f.readlines()

                # Check metadata comments
                assert lines[0].startswith("# Exported from BlueCat")
                assert "# Export Date:" in lines[1]
                assert "# Total Resources: 4" in lines[2]
                assert "# Schema Version: 3.0" in lines[3]

                # Parse CSV
                reader = csv.DictReader(lines[4:])
                rows = list(reader)

                # Should have 4 resources (1 parent network + 1 child network + 2 addresses)
                assert len(rows) == 4

                # Verify parent network
                assert rows[0]["object_type"] == "ip4_network"
                assert rows[0]["bam_id"] == "12345"
                assert rows[0]["name"] == "Corp-Network"
                assert rows[0]["cidr"] == "10.1.0.0/16"
                assert rows[0]["action"] == "update"
                assert rows[0]["udf_owner"] == "IT Team"
                assert rows[0]["udf_environment"] == "production"

                # Verify child network
                assert rows[1]["object_type"] == "ip4_network"
                assert rows[1]["bam_id"] == "12346"
                assert rows[1]["name"] == "Corp-Subnet-1"
                assert rows[1]["cidr"] == "10.1.1.0/24"

                # Verify first address
                assert rows[2]["object_type"] == "ip4_address"
                assert rows[2]["bam_id"] == "12347"
                assert rows[2]["name"] == "web-server-1"
                assert rows[2]["address"] == "10.1.1.10"
                assert rows[2]["mac"] == "00:11:22:33:44:55"
                assert rows[2]["udf_owner"] == "Web Team"
                assert rows[2]["udf_location"] == "DC1"

                # Verify second address
                assert rows[3]["object_type"] == "ip4_address"
                assert rows[3]["bam_id"] == "12348"
                assert rows[3]["name"] == "db-server-1"
                assert rows[3]["address"] == "10.1.1.20"
                assert rows[3]["udf_owner"] == "Database Team"

                # Verify UDF columns are present and sorted
                assert "udf_environment" in reader.fieldnames
                assert "udf_location" in reader.fieldnames
                assert "udf_owner" in reader.fieldnames

                # UDFs should be at the end and sorted
                udf_cols = [c for c in reader.fieldnames if c.startswith("udf_")]
                assert udf_cols == sorted(udf_cols)

            # Verify UDF discovery
            assert len(exporter.discovered_udfs) == 3
            assert "udf_owner" in exporter.discovered_udfs
            assert "udf_environment" in exporter.discovered_udfs
            assert "udf_location" in exporter.discovered_udfs


class TestBlockExportIntegration:
    """Integration tests for block export workflow."""

    @pytest.mark.asyncio
    async def test_export_block_hierarchy(self, authenticated_client, tmp_path):
        """Test complete block export with nested structure."""
        # Mock data
        parent_block = {
            "id": 10000,
            "type": "IP4Block",
            "name": "Corporate",
            "range": "10.0.0.0/8",
            "configuration": {"id": 100, "name": "Default"},
            "userDefinedFields": {"owner": "Network Team"},
        }

        child_block = {
            "id": 10001,
            "type": "IP4Block",
            "name": "Regional",
            "range": "10.1.0.0/16",
            "configuration": {"id": 100, "name": "Default"},
            "userDefinedFields": {"owner": "Regional Team"},
        }

        network = {
            "id": 12345,
            "type": "IPv4Network",
            "name": "Office-Network",
            "range": "10.1.1.0/24",
            "configuration": {"id": 100, "name": "Default"},
            "userDefinedFields": {},
        }

        with respx.mock:
            # Mock API calls
            respx.get("https://bam.example.com/api/v2/blocks/10000").mock(
                return_value=Response(200, json=parent_block)
            )

            respx.get("https://bam.example.com/api/v2/blocks/10000/blocks").mock(
                return_value=Response(
                    200,
                    json={
                        "_embedded": {"blocks": [child_block]},
                        "page": {"totalElements": 1},
                    },
                )
            )

            respx.get("https://bam.example.com/api/v2/blocks/10000/networks").mock(
                return_value=Response(
                    200,
                    json={"_embedded": {"networks": []}, "page": {"totalElements": 0}},
                )
            )

            respx.get("https://bam.example.com/api/v2/blocks/10001/blocks").mock(
                return_value=Response(
                    200,
                    json={"_embedded": {"blocks": []}, "page": {"totalElements": 0}},
                )
            )

            respx.get("https://bam.example.com/api/v2/blocks/10001/networks").mock(
                return_value=Response(
                    200,
                    json={
                        "_embedded": {"networks": [network]},
                        "page": {"totalElements": 1},
                    },
                )
            )

            respx.get("https://bam.example.com/api/v2/blocks/12345/networks").mock(
                return_value=Response(
                    200,
                    json={"_embedded": {"networks": []}, "page": {"totalElements": 0}},
                )
            )

            respx.get("https://bam.example.com/api/v2/networks/12345/addresses").mock(
                return_value=Response(
                    200,
                    json={"_embedded": {"addresses": []}, "page": {"totalElements": 0}},
                )
            )

            # Execute export
            exporter = BlueCatExporter(authenticated_client)
            await exporter.export_block(
                block_id=10000,
                include_children=True,
                include_addresses=True,
                action="update",
            )

            # Write CSV
            output_file = tmp_path / "block_export.csv"
            await exporter.write_csv(output_file)

            # Verify CSV
            assert output_file.exists()

            with open(output_file) as f:
                lines = f.readlines()
                reader = csv.DictReader(lines[4:])
                rows = list(reader)

                # Should have 3 resources (parent block + child block + network)
                assert len(rows) == 3

                # Verify parent block
                assert rows[0]["object_type"] == "ip4_block"
                assert rows[0]["bam_id"] == "10000"
                assert rows[0]["name"] == "Corporate"
                assert rows[0]["cidr"] == "10.0.0.0/8"

                # Verify child block
                assert rows[1]["object_type"] == "ip4_block"
                assert rows[1]["bam_id"] == "10001"
                assert rows[1]["name"] == "Regional"

                # Verify network
                assert rows[2]["object_type"] == "ip4_network"
                assert rows[2]["bam_id"] == "12345"
                assert rows[2]["name"] == "Office-Network"


class TestZoneExportIntegration:
    """Integration tests for DNS zone export workflow."""

    @pytest.mark.asyncio
    async def test_export_zone_with_records(self, authenticated_client, tmp_path):
        """Test complete DNS zone export with resource records."""
        # Mock data
        zone = {
            "id": 54321,
            "type": "Zone",
            "name": "example",
            "absoluteName": "example.com",
            "configuration": {"id": 100, "name": "Default"},
            "view": {"id": 200, "name": "Internal"},
            "userDefinedFields": {"owner": "DNS Team"},
        }

        host_record = {
            "id": 54322,
            "type": "HostRecord",
            "name": "www",
            "absoluteName": "www.example.com",
            "ttl": 3600,
            "configuration": {"id": 100, "name": "Default"},
            "view": {"id": 200, "name": "Internal"},
            "_embedded": {"addresses": [{"address": "10.1.0.10"}, {"address": "10.1.0.11"}]},
            "userDefinedFields": {},
        }

        mx_record = {
            "id": 54323,
            "type": "MXRecord",
            "name": "mail",
            "absoluteName": "mail.example.com",
            "ttl": 3600,
            "configuration": {"id": 100, "name": "Default"},
            "view": {"id": 200, "name": "Internal"},
            "userDefinedFields": {},
        }

        with respx.mock:
            # Mock API calls
            respx.get("https://bam.example.com/api/v2/zones/54321").mock(
                return_value=Response(200, json=zone)
            )

            respx.get("https://bam.example.com/api/v2/zones/54321/resourceRecords").mock(
                return_value=Response(
                    200,
                    json={
                        "_embedded": {"resourceRecords": [host_record, mx_record]},
                        "page": {"totalElements": 2},
                    },
                )
            )

            respx.get("https://bam.example.com/api/v2/zones/54321/zones").mock(
                return_value=Response(
                    200,
                    json={"_embedded": {"zones": []}, "page": {"totalElements": 0}},
                )
            )

            # Execute export
            exporter = BlueCatExporter(authenticated_client)
            await exporter.export_zone(
                zone_identifier=54321,
                include_children=True,
                include_records=True,
                action="update",
            )

            # Write CSV
            output_file = tmp_path / "zone_export.csv"
            await exporter.write_csv(output_file)

            # Verify CSV
            assert output_file.exists()

            with open(output_file) as f:
                lines = f.readlines()
                reader = csv.DictReader(lines[4:])
                rows = list(reader)

                # Should have 3 resources (zone + 2 records)
                assert len(rows) == 3

                # Verify zone
                assert rows[0]["object_type"] == "dns_zone"
                assert rows[0]["bam_id"] == "54321"
                assert rows[0]["zone_name"] == "example.com"
                assert rows[0]["udf_owner"] == "DNS Team"

                # Verify host record
                assert rows[1]["object_type"] == "host_record"
                assert rows[1]["bam_id"] == "54322"
                assert rows[1]["name"] == "www"
                assert rows[1]["addresses"] == "10.1.0.10|10.1.0.11"
                assert rows[1]["ttl"] == "3600"

                # Verify MX record
                assert rows[2]["object_type"] == "mx_record"
                assert rows[2]["bam_id"] == "54323"
                assert rows[2]["name"] == "mail"
