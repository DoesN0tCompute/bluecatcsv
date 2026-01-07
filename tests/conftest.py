"""Pytest configuration and shared fixtures.

This module provides reusable fixtures for testing the BlueCat CSV Importer.
Fixtures are organized by category:
- Path fixtures: Sample CSV file paths
- Mock fixtures: Pre-configured mocks for BAM client and operations
- Data fixtures: Sample CSV rows and operations
- Infrastructure fixtures: Temp directories, caches, etc.
"""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.importer.bam.client import BAMClient
from src.importer.config import PolicyConfig, ThrottleConfig
from src.importer.execution.executor import OperationExecutor
from src.importer.execution.planner import ExecutionBatch, ExecutionPlan
from src.importer.models.csv_row import (
    AliasRecordRow,
    DNSZoneRow,
    HostRecordRow,
    IP4AddressRow,
    IP4BlockRow,
    IP4NetworkRow,
    MXRecordRow,
    TXTRecordRow,
)
from src.importer.models.operations import Operation, OperationType
from src.importer.models.results import OperationResult

# =============================================================================
# Path Fixtures
# =============================================================================


@pytest.fixture
def sample_csv_dir() -> Path:
    """Get path to sample CSV directory."""
    return Path(__file__).parent.parent / "samples"


@pytest.fixture
def simple_csv(sample_csv_dir: Path) -> Path:
    """Get path to simple CSV file."""
    return sample_csv_dir / "simple_import.csv"


@pytest.fixture
def networks_csv(sample_csv_dir: Path) -> Path:
    """Get path to networks CSV file."""
    return sample_csv_dir / "networks_only.csv"


@pytest.fixture
def complex_csv(sample_csv_dir: Path) -> Path:
    """Get path to complex CSV file."""
    return sample_csv_dir / "complex_import.csv"


# =============================================================================
# Mock BAM Client Fixtures
# =============================================================================


@pytest.fixture
def mock_bam_client() -> AsyncMock:
    """Create a pre-configured mock BAM client.

    Returns an AsyncMock with spec=BAMClient and common methods pre-configured
    to return sensible defaults. Individual tests can override specific methods.

    Example:
        def test_something(mock_bam_client):
            mock_bam_client.create_ip4_block.return_value = {"id": 999}
            # ... test code
    """
    client = AsyncMock(spec=BAMClient)

    # Configure default return values for common operations
    client.create_ip4_block.return_value = {"id": 100}
    client.create_ip4_network.return_value = {"id": 200}
    client.create_ip4_address.return_value = {"id": 300}
    client.create_dns_zone.return_value = {"id": 400}
    client.create_host_record.return_value = {"id": 500}

    # Update/delete operations return success by default
    client.update_entity_by_id.return_value = {"id": 100}
    client.delete_entity_by_id.return_value = None

    # Configuration lookup
    client.get_configuration_by_name.return_value = {"id": 1, "name": "Default"}

    # Interface resolution for deployment roles
    client.resolve_interface_string.return_value = 12345

    return client


@pytest.fixture
def mock_bam_client_with_errors() -> AsyncMock:
    """Create a mock BAM client configured to raise errors.

    Useful for testing error handling scenarios.
    """
    from src.importer.utils.exceptions import BAMAPIError

    client = AsyncMock(spec=BAMClient)
    client.create_ip4_block.side_effect = BAMAPIError("API Error")
    client.create_ip4_network.side_effect = BAMAPIError("API Error")
    client.create_ip4_address.side_effect = BAMAPIError("API Error")
    return client


# =============================================================================
# CSV Row Fixtures
# =============================================================================


@pytest.fixture
def sample_ip4_block_row() -> IP4BlockRow:
    """Create a sample IP4 block row."""
    return IP4BlockRow(
        row_id=1,
        object_type="ip4_block",
        action="create",
        config="Default",
        cidr="10.0.0.0/8",
        name="Test Block",
    )


@pytest.fixture
def sample_ip4_network_row() -> IP4NetworkRow:
    """Create a sample IP4 network row."""
    return IP4NetworkRow(
        row_id=2,
        object_type="ip4_network",
        action="create",
        config="Default",
        cidr="10.1.0.0/24",
        name="Test Network",
    )


@pytest.fixture
def sample_ip4_address_row() -> IP4AddressRow:
    """Create a sample IP4 address row."""
    return IP4AddressRow(
        row_id=3,
        object_type="ip4_address",
        action="create",
        config="Default",
        address="10.1.0.5",
        name="server1",
        mac="00:11:22:33:44:55",
        state="STATIC",
    )


@pytest.fixture
def sample_dns_zone_row() -> DNSZoneRow:
    """Create a sample DNS zone row."""
    return DNSZoneRow(
        row_id=4,
        object_type="dns_zone",
        action="create",
        view_path="Default",
        name="example.com",
        deployable=True,
    )


@pytest.fixture
def sample_host_record_row() -> HostRecordRow:
    """Create a sample host record row."""
    return HostRecordRow(
        row_id=5,
        object_type="host_record",
        action="create",
        zone_path="Default/example.com",
        name="www",
        addresses="10.1.0.5",
    )


@pytest.fixture
def sample_alias_record_row() -> AliasRecordRow:
    """Create a sample alias (CNAME) record row."""
    return AliasRecordRow(
        row_id=6,
        object_type="alias_record",
        action="create",
        zone_path="Default/example.com",
        name="cdn",
        linked_record_name="www.example.com",
    )


@pytest.fixture
def sample_mx_record_row() -> MXRecordRow:
    """Create a sample MX record row."""
    return MXRecordRow(
        row_id=7,
        object_type="mx_record",
        action="create",
        zone_path="Default/example.com",
        name="@",
        priority=10,
        exchange="mail.example.com",
    )


@pytest.fixture
def sample_txt_record_row() -> TXTRecordRow:
    """Create a sample TXT record row."""
    return TXTRecordRow(
        row_id=8,
        object_type="txt_record",
        action="create",
        zone_path="Default/example.com",
        name="@",
        text="v=spf1 include:_spf.google.com ~all",
    )


# =============================================================================
# Operation Fixtures
# =============================================================================


@pytest.fixture
def sample_create_block_operation(sample_ip4_block_row: IP4BlockRow) -> Operation:
    """Create a sample CREATE operation for an IP4 block."""
    return Operation(
        row_id=1,
        operation_type=OperationType.CREATE,
        object_type="ip4_block",
        resource_id=None,
        payload={"config_id": 1, "properties": {}},
        csv_row=sample_ip4_block_row,
    )


@pytest.fixture
def sample_create_network_operation(sample_ip4_network_row: IP4NetworkRow) -> Operation:
    """Create a sample CREATE operation for an IP4 network."""
    return Operation(
        row_id=2,
        operation_type=OperationType.CREATE,
        object_type="ip4_network",
        resource_id=None,
        payload={"block_id": 100, "properties": {}},
        csv_row=sample_ip4_network_row,
    )


@pytest.fixture
def sample_create_address_operation(sample_ip4_address_row: IP4AddressRow) -> Operation:
    """Create a sample CREATE operation for an IP4 address."""
    return Operation(
        row_id=3,
        operation_type=OperationType.CREATE,
        object_type="ip4_address",
        resource_id=None,
        payload={"network_id": 200, "properties": {}},
        csv_row=sample_ip4_address_row,
    )


@pytest.fixture
def sample_noop_operation(sample_ip4_address_row: IP4AddressRow) -> Operation:
    """Create a sample NOOP operation."""
    return Operation(
        row_id=1,
        operation_type=OperationType.NOOP,
        object_type="ip4_address",
        resource_id=300,
        payload={},
        csv_row=sample_ip4_address_row,
    )


@pytest.fixture
def sample_update_operation(sample_ip4_address_row: IP4AddressRow) -> Operation:
    """Create a sample UPDATE operation."""
    return Operation(
        row_id=1,
        operation_type=OperationType.UPDATE,
        object_type="ip4_address",
        resource_id=300,
        payload={"properties": {"name": "updated-server"}},
        csv_row=sample_ip4_address_row,
    )


@pytest.fixture
def sample_delete_operation(sample_ip4_address_row: IP4AddressRow) -> Operation:
    """Create a sample DELETE operation."""
    return Operation(
        row_id=1,
        operation_type=OperationType.DELETE,
        object_type="ip4_address",
        resource_id=300,
        payload={},
        csv_row=sample_ip4_address_row,
    )


# =============================================================================
# Execution Fixtures
# =============================================================================


@pytest.fixture
def sample_execution_batch(
    sample_create_address_operation: Operation,
) -> ExecutionBatch:
    """Create a sample execution batch with one operation."""
    return ExecutionBatch(batch_id=1, operations=[sample_create_address_operation])


@pytest.fixture
def sample_execution_plan(sample_execution_batch: ExecutionBatch) -> ExecutionPlan:
    """Create a sample execution plan with one batch."""
    return ExecutionPlan(batches=[sample_execution_batch], total_operations=1)


@pytest.fixture
def sample_operation_result() -> OperationResult:
    """Create a sample successful operation result."""
    return OperationResult(
        row_id=1,
        operation=OperationType.CREATE,
        success=True,
        resource_id=300,
        duration_ms=50.0,
    )


@pytest.fixture
def sample_failed_result() -> OperationResult:
    """Create a sample failed operation result."""
    return OperationResult(
        row_id=1,
        operation=OperationType.CREATE,
        success=False,
        error_message="API Error: Resource conflict",
        duration_ms=25.0,
    )


# =============================================================================
# Executor Fixtures
# =============================================================================


@pytest.fixture
def default_policy() -> PolicyConfig:
    """Create a default policy configuration for testing."""
    return PolicyConfig(max_concurrent_operations=5)


@pytest.fixture
def default_throttle_config() -> ThrottleConfig:
    """Create a default throttle configuration for testing."""
    return ThrottleConfig(initial_concurrency=5, max_concurrency=10, min_concurrency=1)


@pytest.fixture
def executor(mock_bam_client: AsyncMock, default_policy: PolicyConfig) -> OperationExecutor:
    """Create a pre-configured OperationExecutor for testing."""
    return OperationExecutor(mock_bam_client, default_policy)


@pytest.fixture
def dry_run_executor(mock_bam_client: AsyncMock, default_policy: PolicyConfig) -> OperationExecutor:
    """Create an OperationExecutor in dry-run mode."""
    executor = OperationExecutor(mock_bam_client, default_policy)
    executor.dry_run = True
    return executor


# =============================================================================
# Infrastructure Fixtures
# =============================================================================


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for cache testing.

    Uses pytest's tmp_path fixture which is automatically cleaned up.
    """
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def temp_changelog_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for changelog testing."""
    changelog_dir = tmp_path / "changelogs"
    changelog_dir.mkdir()
    return changelog_dir


# =============================================================================
# Factory Fixtures
# =============================================================================


@pytest.fixture
def operation_factory():
    """Factory fixture for creating operations with custom parameters.

    Example:
        def test_something(operation_factory):
            op = operation_factory(
                row_id=99,
                operation_type=OperationType.DELETE,
                object_type="ip4_network",
            )
    """

    def _create_operation(
        row_id: int = 1,
        operation_type: OperationType = OperationType.CREATE,
        object_type: str = "ip4_address",
        resource_id: int | None = None,
        payload: dict[str, Any] | None = None,
        config: str = "Default",
        address: str = "10.1.0.5",
    ) -> Operation:
        csv_row = IP4AddressRow(
            row_id=row_id,
            object_type="ip4_address",
            action=operation_type.value if operation_type != OperationType.NOOP else "create",
            config=config,
            address=address,
        )
        return Operation(
            row_id=row_id,
            operation_type=operation_type,
            object_type=object_type,
            resource_id=resource_id,
            payload=payload or {},
            csv_row=csv_row,
        )

    return _create_operation


@pytest.fixture
def csv_row_factory():
    """Factory fixture for creating CSV rows with custom parameters.

    Example:
        def test_something(csv_row_factory):
            row = csv_row_factory("ip4_block", cidr="192.168.0.0/16")
    """

    def _create_row(
        object_type: str = "ip4_address",
        row_id: int = 1,
        action: str = "create",
        **kwargs: Any,
    ) -> Any:
        base_kwargs = {"row_id": row_id, "object_type": object_type, "action": action}

        if object_type == "ip4_block":
            return IP4BlockRow(
                **base_kwargs,
                config=kwargs.get("config", "Default"),
                cidr=kwargs.get("cidr", "10.0.0.0/8"),
                name=kwargs.get("name", "Test Block"),
            )
        elif object_type == "ip4_network":
            return IP4NetworkRow(
                **base_kwargs,
                config=kwargs.get("config", "Default"),
                cidr=kwargs.get("cidr", "10.1.0.0/24"),
                name=kwargs.get("name", "Test Network"),
            )
        elif object_type == "ip4_address":
            return IP4AddressRow(
                **base_kwargs,
                config=kwargs.get("config", "Default"),
                address=kwargs.get("address", "10.1.0.5"),
                name=kwargs.get("name"),
                mac=kwargs.get("mac"),
                state=kwargs.get("state", "STATIC"),
            )
        elif object_type == "dns_zone":
            return DNSZoneRow(
                **base_kwargs,
                view_path=kwargs.get("view_path", "Default"),
                name=kwargs.get("name", "example.com"),
                deployable=kwargs.get("deployable", True),
            )
        elif object_type == "host_record":
            return HostRecordRow(
                **base_kwargs,
                zone_path=kwargs.get("zone_path", "Default/example.com"),
                name=kwargs.get("name", "www"),
                addresses=kwargs.get("addresses", "10.1.0.5"),
            )
        else:
            raise ValueError(f"Unsupported object_type: {object_type}")

    return _create_row
