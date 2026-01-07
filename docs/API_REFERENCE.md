# API Reference Documentation

**Last Updated:** 2025-12-14 | **Version:** 0.3.0

This document provides a comprehensive reference for all Python APIs in the BlueCat CSV Importer.

## Table of Contents

- [Core Modules](#core-modules)
- [BAM API Integration](#bam-api-integration)
- [Data Models](#data-models)
- [Execution Engine](#execution-engine)
- [Utilities](#utilities)
- [Exception Handling](#exception-handling)

## Core Modules

### importer.cli

The main CLI entry point using Typer.

#### Functions

##### `apply(csv_file, dry_run, resume, allow_dangerous_operations, show_plan, show_deps, verbose, debug)`

Execute the import operation.

**Parameters:**
- `csv_file` (Path): CSV file to import
- `dry_run` (bool): Simulate without applying changes
- `resume` (bool): Resume from last checkpoint
- `allow_dangerous_operations` (bool): Allow deletion of blocks/networks/zones
- `show_plan` (bool): Show execution order after dependency resolution
- `show_deps` (Optional[str]): Export dependency graph to DOT file
- `verbose` (bool): Enable detailed output
- `debug` (bool): Enable debug-level tracing

**Raises:**
- `CSVValidationError`: CSV file has validation errors
- `CyclicDependencyError`: Circular dependencies detected
- `BAMAPIError`: API communication errors

**Example:**
```python
from importer.cli import apply

await apply(
    csv_file=Path("data.csv"),
    dry_run=True,
    show_plan=True,
    verbose=True
)
```

##### `validate(csv_file, strict)`

Validate CSV file without executing.

**Parameters:**
- `csv_file` (Path): CSV file to validate
- `strict` (bool): Fail on first error (default: False)

##### `export(output_file, config_name, network, zone, view_id, view_name)`

Export BAM resources to CSV.

**Parameters:**
- `output_file` (Path): Output CSV file path
- `config_name` (Optional[str]): Configuration name filter
- `network` (Optional[str]): Network CIDR filter
- `zone` (Optional[str]): DNS zone filter
- `view_id` (Optional[int]): DNS view ID filter
- `view_name` (Optional[str]): DNS view name filter

### importer.config

Configuration management using Pydantic settings.

#### Classes

##### `ImporterConfig`

Main configuration class with environment variable support.

**Attributes:**
- `bam` (BAMConfig): BlueCat server connection settings
- `policy` (PolicyConfig): Import behavior and safety settings
- `performance` (PerformanceConfig): Performance tuning parameters
- `throttling` (ThrottlingConfig): Rate limiting settings
- `observability` (ObservabilityConfig): Logging and metrics configuration

**Methods:**
- `from_file(path)`: Load from YAML file
- `from_env()`: Load from environment variables
- `merge_with(other)`: Merge with another config (lower priority)

### importer.core.parser

CSV parsing with Pydantic validation.

#### Classes

##### `CSVParser`

Parse CSV files into typed Pydantic models.

**Methods:**
- `__init__(file_path, encoding)`: Initialize parser
- `parse(strict=False)`: Parse CSV and return list of CSVRow models

**Parameters:**
- `strict` (bool): If True, raise on first error; if False, collect all errors

**Returns:**
- `list[CSVRow]`: Parsed rows as discriminated union models

**Raises:**
- `CSVValidationError`: Invalid CSV format or data
- `FileNotFoundError`: CSV file doesn't exist
- `UnicodeDecodeError`: File encoding issues

**Example:**
```python
from importer.core.parser import CSVParser

parser = CSVParser("data.csv")
rows = parser.parse(strict=True)

# Each row is a discriminated union based on object_type
for row in rows:
    match row.object_type:
        case "ip4_network":
            print(f"Network: {row.cidr}")
        case "host_record":
            print(f"Host: {row.name}")
```

### importer.core.resolver

Resource path resolution with caching.

#### Classes

##### `Resolver`

Resolve resource paths to BAM IDs with intelligent caching.

**Methods:**
- `resolve_path(path, resource_type, parent_id=None)`: Resolve path to ID
- `resolve_by_name(name, resource_type, parent_id=None)`: Resolve by name
- `invalidate_cache(pattern)`: Clear cache entries matching pattern
- `get_cache_stats()`: Get cache hit/miss statistics

**Features:**
- Disk-based caching with diskcache
- Automatic cache invalidation on resource changes
- Concurrent resolution with KeyedLock
- Supports both absolute and relative paths

### importer.bam.client

Async HTTP client for BlueCat REST API v2.

#### Classes

##### `BAMClient`

Main API client with authentication and retry logic.

**Methods:**
- `__init__(config)`: Initialize with BAMConfig
- `async login()`: Authenticate and get session token
- `async get_by_id(resource_type, resource_id)`: Get resource by ID
- `async get_by_path(path, resource_type)`: Get resource by path
- `async create(resource_type, parent_id, data)`: Create new resource
- `async update(resource_type, resource_id, data)`: Update resource
- `async delete(resource_type, resource_id)`: Delete resource
- `async list(resource_type, parent_id=None, filters=None)`: List resources
- `async bulk_get(resource_type, ids)`: Get multiple resources efficiently

**Authentication:**
The client handles session-based authentication automatically:
1. Logs in with username/password
2. Receives Bearer token
3. Refreshes token on expiration
4. Handles concurrent login attempts with locks

**Error Handling:**
- Automatic retry with exponential backoff for transient errors
- Rate limit handling with `Retry-After` header
- Clear error messages with context

**Example:**
```python
from importer.bam.client import BAMClient
from importer.config import BAMConfig

config = BAMConfig(
    base_url="https://bam.example.com",
    username="admin",
    password="secret"
)
client = BAMClient(config)

# Get a network
network = await client.get_by_id("network", 12345)

# Create an address
address_data = {"name": "server1", "address": "10.1.1.10"}
result = await client.create("address", 12345, address_data)
```

## Data Models

### importer.models.csv_row

Pydantic models for CSV rows with discriminated unions.

#### Base Classes

##### `CSVRow`

Base model for all CSV rows with common fields.

**Required Fields:**
- `row_id` (str): Unique identifier for the row
- `object_type` (str): Resource type (determines specific model)
- `action` (Literal["create", "update", "delete"]): Operation to perform

#### Resource-Specific Models

##### `IP4NetworkRow`

Model for IPv4 network resources.

**Fields:**
- `cidr` (IPv4Network): Network CIDR (e.g., "10.1.0.0/24")
- `name` (str): Network name
- `config` (str): Configuration name
- `parent` (Optional[str]): Parent block path (optional, auto-discovered if omitted)
- `properties` (Optional[dict]): Additional properties
- `udf_*` fields: User-defined fields

**Example:**
```python
row = IP4NetworkRow(
    row_id="1",
    object_type="ip4_network",
    action="create",
    config="Default",
    cidr="10.1.0.0/24",
    name="Production",
    udf_Location="Rack A12"
)
```

##### `HostRecordRow`

Model for DNS host (A) records.

**Fields:**
- `name` (str): Host name
- `zone_path` (str): DNS zone path
- `addresses` (str): Comma-separated IP addresses
- `view_path` (Optional[str]): DNS view path (default: "Default")

### importer.models.operations

Models for import operations.

#### Classes

##### `Operation`

Represents a single import operation.

**Attributes:**
- `row_id` (str): Original CSV row ID
- `action` (Literal["create", "update", "delete"]): Operation type
- `object_type` (str): BAM resource type
- `csv_row` (CSVRow): Original CSV row data
- `resource_id` (Optional[int]): BAM resource ID (for updates/deletes)
- `parent_id` (Optional[int]): Parent resource ID
- `data` (dict): Data payload for API calls

##### `OperationResult`

Result of an operation execution.

**Attributes:**
- `operation` (Operation): The executed operation
- `success` (bool): Whether operation succeeded
- `resource_id` (Optional[int]): Created/updated resource ID
- `message` (Optional[str]): Success or error message
- `details` (Optional[dict]): Additional details
- `duration_ms` (Optional[float]): Operation duration in milliseconds

## Execution Engine

### importer.execution.executor

Async operation executor with throttling and error handling.

#### Classes

##### `OperationExecutor`

Execute operations with dependency resolution and error recovery.

**Methods:**
- `async execute(operations)`: Execute list of operations
- `get_statistics()`: Get execution statistics
- `cancel()`: Cancel ongoing execution

**Features:**
- Parallel execution with configurable concurrency
- Dependency-aware ordering
- Automatic retries for transient failures
- Comprehensive error reporting
- Progress tracking

### importer.execution.handlers

Strategy pattern implementation for resource-specific operations.

#### Registry

##### `HANDLER_REGISTRY`

Dictionary mapping resource types to handler instances.

**Usage:**
```python
from importer.execution.handlers import HANDLER_REGISTRY

handler = HANDLER_REGISTRY["ip4_network"]
result = await handler.create(client, operation)
```

#### Handler Protocol

##### `OperationHandler`

Protocol that all resource handlers must implement.

**Methods:**
- `async create(client, operation)`: Create resource
- `async update(client, operation)`: Update resource
- `async delete(client, operation)`: Delete resource

**Return Types:**
- Can return either `dict[str, Any]` for simple responses or `OperationResult` for complex handling

## Exception Handling

### importer.utils.exceptions

Hierarchical exception system for error handling.

#### Hierarchy

```
ImporterError (base)
├── ValidationError
│   ├── CSVValidationError
│   └── SchemaValidationError
├── ResourceNotFoundError
├── PendingCreateError
├── CyclicDependencyError
├── DeferredResolutionError
└── BAMAPIError
    ├── ResourceAlreadyExistsError
    ├── BAMRateLimitError
    └── BAMAuthenticationError
```

#### Common Patterns

**Handling API Errors:**
```python
from importer.utils.exceptions import (
    BAMRateLimitError,
    ResourceNotFoundError,
    ResourceAlreadyExistsError
)

try:
    await operation.execute()
except ResourceNotFoundError as e:
    logger.warning(f"Resource not found: {e}")
except BAMRateLimitError as e:
    logger.info(f"Rate limited, waiting {e.retry_after}s")
    await asyncio.sleep(e.retry_after)
except ResourceAlreadyExistsError:
    # Handle idempotent operations
    pass
```

**Creating Custom Errors:**
```python
from importer.utils.exceptions import ImporterError

class CustomBusinessError(ImporterError):
    """Custom error for specific business logic."""
    pass
```

## Utility Modules

### importer.observability.logger

Structured logging with structlog.

#### Setup

```python
from importer.observability.logger import setup_logging

# Configure logging
setup_logging(
    level="INFO",
    format="json",
    file="logs/importer.log"
)
```

#### Usage

```python
import structlog

logger = structlog.get_logger(__name__)

# With context
logger.info("Creating resource",
           resource_type="network",
           resource_id=12345,
           user="admin")

# Error with exception
logger.error("Failed to create resource",
            resource_type="network",
            exc_info=True)
```

### importer.observability.metrics

Metrics collection for monitoring.

#### Metrics Types

- **Counters**: Track occurrences (e.g., operations completed)
- **Histograms**: Track distributions (e.g., operation latency)
- **Gauges**: Track current values (e.g., cache size)

#### Example

```python
from importer.observability.metrics import get_metrics

metrics = get_metrics()

# Increment counter
metrics.counter("operations.total").inc()

# Record latency
metrics.histogram("operation.duration").observe(1.23)

# Set gauge
metrics.gauge("cache.size").set(1000)
```

## Integration Examples

### Complete Import Workflow

```python
import asyncio
from pathlib import Path
from importer.config import ImporterConfig
from importer.core.parser import CSVParser
from importer.execution.executor import OperationExecutor
from importer.execution.planner import ExecutionPlanner
from importer.dependency.graph import DependencyGraph
from importer.observability.logger import setup_logging

async def main():
    # Setup
    setup_logging(level="INFO")
    config = ImporterConfig.from_env()

    # Parse CSV
    parser = CSVParser(Path("data.csv"))
    rows = parser.parse(strict=True)

    # Build operations
    operations = [Operation.from_row(row) for row in rows]

    # Resolve dependencies
    graph = DependencyGraph()
    graph.build_from_operations(operations)

    # Plan execution
    planner = ExecutionPlanner(config)
    phases = planner.create_execution_phases(graph)

    # Execute
    executor = OperationExecutor(config)
    results = await executor.execute(phases)

    # Report
    success_count = sum(1 for r in results if r.success)
    print(f"Completed: {success_count}/{len(results)} operations")

asyncio.run(main())
```

### Custom Resource Handler

```python
from importer.execution.handlers import OperationHandler
from importer.models.operations import Operation, OperationResult
from importer.bam.client import BAMClient
from importer.utils.exceptions import ImporterError

class CustomResourceHandler(OperationHandler):
    """Handler for custom resource type."""

    async def create(self, client: BAMClient, operation: Operation) -> OperationResult:
        try:
            # Create resource via API
            result = await client.create(
                resource_type="customResource",
                parent_id=operation.parent_id,
                data=operation.data
            )

            return OperationResult(
                operation=operation,
                success=True,
                resource_id=result["id"],
                message="Custom resource created successfully"
            )
        except Exception as e:
            return OperationResult(
                operation=operation,
                success=False,
                message=f"Failed to create custom resource: {e}"
            )

    async def update(self, client: BAMClient, operation: Operation) -> OperationResult:
        # Implementation for update
        pass

    async def delete(self, client: BAMClient, operation: Operation) -> OperationResult:
        # Implementation for delete
        pass

# Register the handler
from importer.execution.handlers import HANDLER_REGISTRY
HANDLER_REGISTRY["custom_resource"] = CustomResourceHandler()
```

## Best Practices

1. **Use Type Hints**: All APIs have full type annotations
2. **Handle Exceptions**: Use specific exception types for proper error handling
3. **Log with Context**: Include relevant context in log messages
4. **Use Async**: All I/O operations are async
5. **Cache Awareness**: The resolver caches results automatically
6. **Idempotency**: Design operations to be safe to retry
7. **Resource Cleanup**: Use context managers for resources
8. **Configuration**: Use environment variables for sensitive data

## Testing Examples

### Unit Testing with Mocks

```python
import pytest
from unittest.mock import AsyncMock, patch
from importer.bam.client import BAMClient
from importer.models.operations import Operation

@pytest.mark.asyncio
async def test_create_network():
    # Setup
    client = BAMClient(config)
    client._authenticated = True
    client.http_client = AsyncMock()

    operation = Operation(
        row_id="1",
        action="create",
        object_type="network",
        data={"cidr": "10.1.0.0/24", "name": "Test"}
    )

    # Mock response
    client.http_client.post.return_value.json.return_value = {"id": 12345}

    # Execute
    result = await client.create("network", 100, operation.data)

    # Assert
    assert result["id"] == 12345
    client.http_client.post.assert_called_once()
```

### Integration Testing

```python
import pytest
from importer.cli import apply
from pathlib import Path

@pytest.mark.integration
async def test_full_import_workflow():
    # Test with real BAM server
    csv_path = Path("test_data.csv")

    # Dry run first
    await apply(csv_path=csv_path, dry_run=True)

    # Real import
    await apply(csv_path=csv_path, dry_run=False)

    # Verify results
    # ... assertions ...
```

This API reference provides comprehensive documentation for all public APIs in the BlueCat CSV Importer, including parameters, return types, exceptions, and usage examples.