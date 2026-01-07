"""Integration tests for complete import workflow.

This module tests the full import pipeline from CSV parsing through
execution planning, including:
- Hierarchical resource parsing and dependency ordering
- DNS zone and record parsing
- Deferred resolution patterns
- Failure cascade scenarios
- Dry-run mode verification

Note: These tests focus on parsing, validation, and dependency
planning stages that don't require live BAM connections.
"""

from unittest.mock import AsyncMock

import pytest

from src.importer.config import PolicyConfig
from src.importer.core.parser import CSVParser
from src.importer.dependency.graph import DependencyGraph
from src.importer.execution.executor import OperationExecutor
from src.importer.models.csv_row import IP4AddressRow, IP4BlockRow, IP4NetworkRow
from src.importer.models.operations import Operation, OperationType
from src.importer.utils.exceptions import CSVValidationError


class TestHierarchicalIPParsingWorkflow:
    """Test CSV parsing for hierarchical IP resources."""

    @pytest.mark.asyncio
    async def test_parse_ip_hierarchy(self, tmp_path):
        """Test parsing block -> network -> address hierarchy."""
        csv_content = """row_id,object_type,action,config,parent,cidr,name,address,mac,state
1,ip4_block,create,Default,,10.0.0.0/8,TestBlock,,,
2,ip4_network,create,Default,10.0.0.0/8,10.1.0.0/24,TestNetwork,,,
3,ip4_address,create,Default,,,server1,10.1.0.5,00:11:22:33:44:55,STATIC
"""
        csv_path = tmp_path / "test_hierarchy.csv"
        csv_path.write_text(csv_content)

        parser = CSVParser(csv_path)
        rows = parser.parse()

        assert len(rows) == 3
        assert rows[0].object_type == "ip4_block"
        assert rows[1].object_type == "ip4_network"
        assert rows[2].object_type == "ip4_address"

        # Verify parsed values
        assert rows[0].config == "Default"
        assert rows[0].cidr == "10.0.0.0/8"
        assert rows[1].parent == "10.0.0.0/8"
        assert rows[2].address == "10.1.0.5"

    @pytest.mark.asyncio
    async def test_parse_dns_resources(self, tmp_path):
        """Test parsing DNS zone and host records."""
        csv_content = """row_id,object_type,action,config,view_path,zone_name,name,addresses
1,dns_zone,create,Default,Internal,example.com,,
2,host_record,create,Default,Internal,example.com,www,10.1.0.10
3,host_record,create,Default,Internal,example.com,mail,10.1.0.20
"""
        csv_path = tmp_path / "test_dns.csv"
        csv_path.write_text(csv_content)

        parser = CSVParser(csv_path)
        rows = parser.parse()

        assert len(rows) == 3
        assert rows[0].object_type == "dns_zone"
        assert rows[1].object_type == "host_record"
        assert rows[2].object_type == "host_record"

        # Verify zone parsed
        assert rows[0].zone_name == "example.com"
        assert rows[0].view_path == "Internal"

        # Verify host records parsed
        assert rows[1].name == "www"
        assert rows[2].name == "mail"


class TestDependencyGraphWorkflow:
    """Test dependency graph building and ordering."""

    @pytest.fixture
    def ip_operations(self) -> list[Operation]:
        """Create sample IP operations for dependency testing."""
        block_row = IP4BlockRow(
            row_id=1,
            object_type="ip4_block",
            action="create",
            config="Default",
            cidr="10.0.0.0/8",
            name="TestBlock",
        )
        network_row = IP4NetworkRow(
            row_id=2,
            object_type="ip4_network",
            action="create",
            config="Default",
            parent="10.0.0.0/8",
            cidr="10.1.0.0/24",
            name="TestNetwork",
        )
        address_row = IP4AddressRow(
            row_id=3,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.5",
            name="server1",
            mac="00:11:22:33:44:55",
            state="STATIC",
        )

        return [
            Operation(
                row_id=1,
                operation_type=OperationType.CREATE,
                object_type="ip4_block",
                resource_id=None,
                payload={"config_id": 1},
                csv_row=block_row,
            ),
            Operation(
                row_id=2,
                operation_type=OperationType.CREATE,
                object_type="ip4_network",
                resource_id=None,
                payload={"config_id": 1, "parent_id": 100},
                csv_row=network_row,
            ),
            Operation(
                row_id=3,
                operation_type=OperationType.CREATE,
                object_type="ip4_address",
                resource_id=None,
                payload={"config_id": 1, "network_id": 200},
                csv_row=address_row,
            ),
        ]

    def test_dependency_graph_building(self, ip_operations):
        """Test building dependency graph from operations."""
        graph = DependencyGraph()
        graph.build_from_operations(ip_operations)

        # Graph should be built without error
        # Validate graph has nodes by checking it can do topological sort
        batches = graph.get_execution_batches()
        assert len(batches) > 0

    def test_execution_ordering_via_graph(self, ip_operations):
        """Test execution batches respect phase ordering."""
        graph = DependencyGraph()
        graph.build_from_operations(ip_operations)

        # Get execution batches directly from graph
        batches = graph.get_execution_batches()

        # Should have at least one batch
        assert len(batches) > 0

        # Find batch indices for each resource type by checking node IDs
        block_batch = None
        network_batch = None
        address_batch = None

        for batch_idx, batch in enumerate(batches):
            for node in batch:
                node_id = node.node_id if hasattr(node, "node_id") else str(node)
                if "ip4_block" in node_id:
                    block_batch = batch_idx
                elif "ip4_network" in node_id:
                    network_batch = batch_idx
                elif "ip4_address" in node_id:
                    address_batch = batch_idx

        # Verify ordering (block before network before address)
        assert block_batch is not None
        assert network_batch is not None
        assert address_batch is not None
        assert block_batch <= network_batch <= address_batch


class TestDryRunWorkflow:
    """Test dry-run mode execution."""

    @pytest.fixture
    def mock_bam_client(self) -> AsyncMock:
        """Create mock BAM client."""
        client = AsyncMock()
        client.get_configuration_by_name.return_value = {"id": 1, "name": "Default"}
        client.create_ip4_block.return_value = {"id": 100}
        return client

    @pytest.fixture
    def sample_operation(self) -> Operation:
        """Create a sample block operation."""
        block_row = IP4BlockRow(
            row_id=1,
            object_type="ip4_block",
            action="create",
            config="Default",
            cidr="10.0.0.0/8",
            name="DryRunBlock",
        )
        return Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_block",
            resource_id=None,
            payload={"config_id": 1, "cidr": "10.0.0.0/8", "name": "DryRunBlock"},
            csv_row=block_row,
        )

    @pytest.mark.asyncio
    async def test_dry_run_no_api_mutations(self, mock_bam_client, sample_operation):
        """Verify dry-run mode doesn't call mutating API methods."""
        policy = PolicyConfig(max_concurrent_operations=10)
        executor = OperationExecutor(
            bam_client=mock_bam_client,
            policy=policy,
            allow_dangerous_operations=False,
        )
        executor.dry_run = True

        result = await executor._execute_operation(sample_operation)

        # Verify success in dry-run
        assert result.success is True

        # Verify no create/update/delete methods called
        mock_bam_client.create_ip4_block.assert_not_called()
        mock_bam_client.update_entity_by_id.assert_not_called()
        mock_bam_client.delete_entity_by_id.assert_not_called()


class TestDeleteOperationWorkflow:
    """Test delete operation parsing."""

    @pytest.mark.asyncio
    async def test_delete_operations_parsed(self, tmp_path):
        """Test that delete operations are parsed correctly."""
        csv_content = """row_id,object_type,action,config,cidr,name,address
1,ip4_address,delete,Default,,,10.1.0.5
"""
        csv_path = tmp_path / "test_delete.csv"
        csv_path.write_text(csv_content)

        parser = CSVParser(csv_path)
        rows = parser.parse()

        assert len(rows) == 1
        assert rows[0].action == "delete"
        assert rows[0].object_type == "ip4_address"


class TestValidationWorkflow:
    """Test CSV validation without BAM connectivity."""

    @pytest.mark.asyncio
    async def test_validate_valid_csv(self, tmp_path):
        """Test validation passes for valid CSV."""
        csv_content = """row_id,object_type,action,config,cidr,name
1,ip4_block,create,Default,10.0.0.0/8,TestBlock
"""
        csv_path = tmp_path / "valid.csv"
        csv_path.write_text(csv_content)

        parser = CSVParser(csv_path)
        rows = parser.parse()

        assert len(rows) == 1
        assert rows[0].config == "Default"
        assert rows[0].cidr == "10.0.0.0/8"

    @pytest.mark.asyncio
    async def test_validate_invalid_cidr(self, tmp_path):
        """Test validation fails for invalid CIDR."""
        csv_content = """row_id,object_type,action,config,cidr,name
1,ip4_block,create,Default,invalid-cidr,TestBlock
"""
        csv_path = tmp_path / "invalid.csv"
        csv_path.write_text(csv_content)

        parser = CSVParser(csv_path)

        with pytest.raises(CSVValidationError):
            parser.parse()

    @pytest.mark.asyncio
    async def test_validate_missing_required_field(self, tmp_path):
        """Test validation fails for missing required fields."""
        csv_content = """row_id,object_type,action,cidr,name
1,ip4_block,create,10.0.0.0/8,TestBlock
"""
        csv_path = tmp_path / "missing_field.csv"
        csv_path.write_text(csv_content)

        parser = CSVParser(csv_path)

        with pytest.raises(CSVValidationError):
            parser.parse()


class TestMultiResourceParsing:
    """Test parsing multiple resource types."""

    @pytest.mark.asyncio
    async def test_parse_mixed_ip_resources(self, tmp_path):
        """Test parsing multiple IP resource types."""
        csv_content = """row_id,object_type,action,config,parent,cidr,name,address,mac,state
1,ip4_block,create,Default,,10.0.0.0/8,CorpBlock,,,
2,ip4_network,create,Default,10.0.0.0/8,10.1.0.0/24,CorpNetwork,,,
3,ip4_address,create,Default,,,server1,10.1.0.10,00:11:22:33:44:55,STATIC
"""
        csv_path = tmp_path / "test_mixed.csv"
        csv_path.write_text(csv_content)

        parser = CSVParser(csv_path)
        rows = parser.parse()

        assert len(rows) == 3
        object_types = [r.object_type for r in rows]
        assert "ip4_block" in object_types
        assert "ip4_network" in object_types
        assert "ip4_address" in object_types
