# Module Guide

**Last Updated:** 2025-12-14 | **Version:** 0.3.0

This document provides detailed documentation for each module in the BlueCat CSV Importer, including their purpose, key classes, functions, and integration points.

## Table of Contents

- [Core Modules](#core-modules)
- [BAM API Integration](#bam-api-integration)
- [Execution Engine](#execution-engine)
- [Data Models](#data-models)
- [Dependency Management](#dependency-management)
- [Observability](#observability)
- [Persistence](#persistence)
- [Utilities](#utilities)
- [Validation](#validation)

## Core Modules

### importer.core.parser

**Purpose**: Parse CSV files with Pydantic validation and discriminated unions.

#### Key Classes

##### `CSVParser`

Main class for parsing CSV files into typed models.

```python
class CSVParser:
    def __init__(self, file_path: Path, encoding: str = 'utf-8')
    async def parse(self, strict: bool = False) -> list[CSVRow]
```

**Features:**
- Multi-schema support (header rows can change schema)
- Discriminated unions for type-specific validation
- Whitespace stripping and empty string handling
- Comment support (lines starting with #)
- Duplicate row ID detection

**Usage Example:**
```python
from importer.core.parser import CSVParser

parser = CSVParser("data.csv")
rows = await parser.parse(strict=True)

# Each row is typed based on object_type
for row in rows:
    if row.object_type == "ip4_network":
        print(f"Network: {row.cidr}, Name: {row.name}")
```

#### Key Functions

##### `strip_whitespace(v: Any) -> Any`

Custom validator for string fields that handles whitespace and empty strings intelligently.

### importer.core.resolver

**Purpose**: Resolve resource paths to BAM IDs with intelligent caching.

#### Key Classes

##### `Resolver`

Handles path-to-ID resolution with disk-based caching.

```python
class Resolver:
    def __init__(self, client: BAMClient, config: ImporterConfig)
    async def resolve_path(self, path: str, resource_type: str) -> int
    async def resolve_by_name(self, name: str, resource_type: str, parent_id: int) -> int
    def invalidate_cache(self, pattern: str) -> None
    def get_cache_stats(self) -> dict
```

**Features:**
- Multi-level caching (memory + disk)
- Cache invalidation on resource changes
- Concurrent resolution protection with KeyedLock
- Auto-discovery of parent resources
- Support for absolute and relative paths

**Cache Keys:**
- Configuration: `config://<name>`
- Block: `block://<config>/<cidr>`
- Network: `network://<config>/<cidr>`
- DNS Zone: `zone://<view>/<name>`

### importer.core.diff_engine

**Purpose**: Compare desired state (CSV) with current state (BAM) to determine operations.

#### Key Classes

##### `DiffEngine`

Computes differences between CSV and BAM state.

```python
class DiffEngine:
    def __init__(self, client: BAMClient)
    async def compute_diff(self, csv_rows: list[CSVRow]) -> list[Operation]
```

**Algorithm:**
1. Load current state from BAM
2. Parse desired state from CSV
3. Match resources by identifiers
4. Generate operations:
   - CREATE: Resource in CSV but not in BAM
   - UPDATE: Resource in both but with differences
   - DELETE: Resource in BAM but marked for deletion in CSV

### importer.core.exporter

**Purpose**: Export BAM resources to CSV format.

#### Key Classes

##### `Exporter`

Exports resources maintaining hierarchical relationships.

```python
class Exporter:
    def __init__(self, client: BAMClient)
    async def export(self, filters: ExportFilters) -> list[CSVRow]
```

**Export Filters:**
- Configuration name
- Network CIDR
- DNS zone
- View name/ID
- Resource types

**Features:**
- Preserves parent-child relationships
- Includes all properties and UDFs
- Orders resources for proper import
- Handles circular references

### importer.core.operation_factory

**Purpose**: Create Operation objects from CSV rows with dependency resolution.

#### Key Classes

##### `OperationFactory`

Creates operations and manages deferred resolution.

```python
class OperationFactory:
    def __init__(self, resolver: Resolver)
    async def create_operations(self, csv_rows: list[CSVRow]) -> list[Operation]
```

**Deferred Resolution:**
- Identifies resources that depend on to-be-created parents
- Creates placeholder references with `_deferred_` prefix
- Allows same-batch resource references

### importer.core.state_loader

**Purpose**: Load current resource state from BAM efficiently.

#### Key Classes

##### `StateLoader`

Bulk loads resources with optimization.

```python
class StateLoader:
    def __init__(self, client: BAMClient)
    async def load_all_configs(self) -> dict[str, int]
    async def load_blocks_by_config(self, config_id: int) -> dict[str, int]
    async def load_networks_by_block(self, block_id: int) -> dict[str, int]
```

**Optimization Strategies:**
- Bulk API calls when available
- Parallel loading with asyncio.gather
- Selective loading based on CSV content
- Cache-friendly data structures

## BAM API Integration

### importer.bam.client

**Purpose**: Async HTTP client for BlueCat REST API v2 with authentication and retry logic.

#### Key Classes

##### `BAMClient`

Main API client with full resource management.

```python
class BAMClient:
    def __init__(self, config: BAMConfig)
    async def login(self) -> None
    async def get_by_id(self, resource_type: str, resource_id: int) -> dict
    async def get_by_path(self, path: str, resource_type: str) -> dict
    async def create(self, resource_type: str, parent_id: int, data: dict) -> dict
    async def update(self, resource_type: str, resource_id: int, data: dict) -> dict
    async def delete(self, resource_type: str, resource_id: int) -> None
    async def list(self, resource_type: str, parent_id: int = None, filters: dict = None) -> list[dict]
```

**Authentication Flow:**
1. POST to `/api/v2/sessions` with credentials
2. Receive `apiToken` and `basicAuthenticationCredentials`
3. Use Basic auth header for subsequent requests
4. Auto-renew on token expiration
5. Handle concurrent login attempts

**Error Handling:**
- Retry with exponential backoff for transient errors
- Rate limit handling with `Retry-After` header
- Clear error messages with context
- Automatic session renewal

**Resource-Specific Methods:**
- `get_network_by_ip()`: Find network containing IP
- `get_dns_records()`: Query DNS records with filters
- `bulk_get_by_ids()`: Efficiently get multiple resources

### importer.bam.endpoints

**Purpose**: Centralized API endpoint constants and path generation.

#### Constants

```python
class BAMEndpoints:
    # Base paths
    API_V2 = "/api/v2"
    SESSIONS = "/api/v2/sessions"

    # Resource endpoints
    CONFIGURATIONS = "/api/v2/configurations"
    BLOCKS = "/api/v2/blocks"
    NETWORKS = "/api/v2/networks"
    ADDRESSES = "/api/v2/addresses"
    ZONES = "/api/v2/zones"
    RESOURCE_RECORDS = "/api/v2/resourceRecords"

    # Path templates
    @staticmethod
    def get_resource_path(resource_type: str, resource_id: int = None) -> str:
        # Returns: /api/v2/{type} or /api/v2/{type}/{id}
```

### importer.bam.response_models

**Purpose**: Pydantic models for validating API responses.

#### Key Models

##### `SessionResponse`

Validates session creation response.

```python
class SessionResponse(BaseModel):
    apiToken: str
    basicAuthenticationCredentials: str
```

##### `ResourceResponse`

Generic resource response model.

```python
class ResourceResponse(BaseModel):
    id: int
    name: str
    properties: dict[str, str]
    _links: dict[str, Any]
    _embedded: Optional[dict[str, Any]] = None
```

## Execution Engine

### importer.execution.executor

**Purpose**: Execute operations with dependency resolution, throttling, and error handling.

#### Key Classes

##### `OperationExecutor`

Main executor with parallel processing.

```python
class OperationExecutor:
    def __init__(self, client: BAMClient, config: ImporterConfig)
    async def execute(self, phases: list[ExecutionPhase]) -> list[OperationResult]
    def get_statistics(self) -> ExecutionStatistics
    def cancel(self) -> None
```

**Execution Flow:**
1. Sort operations by dependency graph
2. Group into phases (independent operations)
3. Execute phases in order
4. Within phase, execute operations in parallel
5. Handle failures with retry logic
6. Update changelog and generate rollback data

**Features:**
- Configurable concurrency limits
- Adaptive throttling based on API response times
- Comprehensive error reporting
- Progress tracking and ETA calculation
- Checkpoint support for resumable imports

### importer.execution.handlers

**Purpose**: Strategy pattern for resource-specific operations.

#### Handler Registry

```python
HANDLER_REGISTRY: dict[str, OperationHandler] = {
    "ip4_block": IP4BlockHandler(),
    "ip4_network": IP4NetworkHandler(),
    "ip4_address": IP4AddressHandler(),
    "ip6_block": IP6BlockHandler(),
    "ip6_network": IP6NetworkHandler(),
    "ip6_address": IP6AddressHandler(),
    "dns_zone": DNSZoneHandler(),
    "host_record": HostRecordHandler(),
    "alias_record": AliasRecordHandler(),
    "mx_record": MXRecordHandler(),
    "txt_record": TXTRecordHandler(),
    "srv_record": SRVRecordHandler(),
    "generic_record": GenericRecordHandler(),
    "external_host_record": ExternalHostRecordHandler(),
    "ipv4_dhcp_range": IPv4DHCPRangeHandler(),
    "ipv6_dhcp_range": IPv6DHCPRangeHandler(),
    "dhcpv4_client_deployment_option": DHCPv4ClientOptionHandler(),
    "dhcpv4_service_deployment_option": DHCPv4ServiceOptionHandler(),
    "dhcp_deployment_role": DHCPDeploymentRoleHandler(),
    "dns_deployment_role": DNSDeploymentRoleHandler(),
    "location": LocationHandler(),
    "tag_group": TagGroupHandler(),
    "tag": TagHandler(),
    "resource_tag": ResourceTagHandler(),
    "udf_definition": UDFDefinitionHandler(),
    "udl_definition": UDLDefinitionHandler(),
    "device_type": DeviceTypeHandler(),
    "device_subtype": DeviceSubtypeHandler(),
    "device": DeviceHandler(),
    "device_address": DeviceAddressHandler(),
}
```

#### Handler Protocol

```python
class OperationHandler(Protocol):
    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any] | OperationResult
    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any] | OperationResult
    async def delete(self, client: BAMClient, operation: Operation) -> dict[str, Any] | OperationResult
```

#### Handler Implementation Example

```python
class IP4NetworkHandler(OperationHandler):
    async def create(self, client: BAMClient, operation: Operation) -> dict:
        # Create network in parent block
        data = {
            "name": operation.data["name"],
            "cidr": operation.data["cidr"],
        }
        return await client.create("network", operation.parent_id, data)

    async def update(self, client: BAMClient, operation: Operation) -> dict:
        # Update network properties
        return await client.update("network", operation.resource_id, operation.data)

    async def delete(self, client: BAMClient, operation: Operation) -> None:
        # Delete network (with safety checks)
        await client.delete("network", operation.resource_id)
```

### importer.execution.planner

**Purpose**: Create optimal execution plans from dependency graph.

#### Key Classes

##### `ExecutionPlanner`

Generates execution phases for parallel processing.

```python
class ExecutionPlanner:
    def __init__(self, config: ImporterConfig)
    def create_execution_phases(self, graph: DependencyGraph) -> list[ExecutionPhase]
    def optimize_phase_order(self, phases: list[ExecutionPhase]) -> list[ExecutionPhase]
```

**Planning Algorithm:**
1. Topological sort to remove cycles
2. Group operations by dependency level
3. Optimize within each phase:
   - Group by resource type for API efficiency
   - Order by creation vs deletion
   - Batch similar operations

### importer.execution.throttle

**Purpose**: Adaptive throttling to prevent API overload.

#### Key Classes

##### `AdaptiveThrottler`

Dynamically adjusts concurrency based on performance.

```python
class AdaptiveThrottler:
    def __init__(self, config: ThrottlingConfig)
    async def acquire(self) -> None
    async def release(self, latency_ms: float) -> None
    def get_current_limit(self) -> int
```

**Adaptation Logic:**
- Increase concurrency if latency below target
- Decrease if latency above threshold or errors increase
- Circuit breaker on excessive errors
- Rate limiting enforcement

### importer.execution.runner

**Purpose**: High-level orchestration of import process.

#### Key Classes

##### `ImportRunner`

Main import workflow coordinator.

```python
class ImportRunner:
    def __init__(self, config: ImporterConfig)
    async def run_import(self, csv_file: Path, options: ImportOptions) -> ImportResult
    async def resume_import(self, session_id: str) -> ImportResult
```

**Workflow:**
1. Parse and validate CSV
2. Load current BAM state
3. Compute differences
4. Build dependency graph
5. Create execution plan
6. Execute with checkpoints
7. Generate reports and rollback

## Data Models

### importer.models.csv_row

**Purpose**: Pydantic models for CSV rows with discriminated unions.

#### Model Hierarchy

```
CSVRow (base)
├── IP4BlockRow
├── IP4NetworkRow
├── IP4AddressRow
├── IP6BlockRow
├── IP6NetworkRow
├── IP6AddressRow
├── DNSZoneRow
├── HostRecordRow
├── AliasRecordRow
├── MXRecordRow
├── TXTRecordRow
├── SRVRecordRow
├── GenericRecordRow
├── ExternalHostRecordRow
├── IPv4DHCPRangeRow
├── IPv6DHCPRangeRow
├── DHCPv4ClientOptionRow
├── DHCPv4ServiceOptionRow
├── DHCPDeploymentRoleRow
├── DNSDeploymentRoleRow
├── LocationRow
├── TagGroupRow
├── TagRow
├── ResourceTagRow
├── UDFDefinitionRow
├── UDLDefinitionRow
├── DeviceTypeRow
├── DeviceSubtypeRow
├── DeviceRow
└── DeviceAddressRow
```

#### Common Fields

All models inherit from `CSVRow` base:

```python
class CSVRow(BaseModel):
    row_id: str
    object_type: str
    action: Literal["create", "update", "delete"]
```

#### Custom Validators

##### `strip_whitespace`

Applied to all string fields:
- Removes leading/trailing whitespace
- Converts empty strings to None for optional fields
- Preserves empty strings for clearable fields

##### `cidr_validator`

Validates CIDR notation and ensures appropriate sizes:
- IPv4 blocks: /0 to /23
- IPv4 networks: /24 to /32
- IPv6 blocks: /0 to /59
- IPv6 networks: /60 to /128

### importer.models.operations

**Purpose**: Internal operation representations.

#### Key Classes

##### `Operation`

Represents a single operation to execute.

```python
@dataclass(frozen=True)
class Operation:
    row_id: str
    action: Literal["create", "update", "delete"]
    object_type: str
    csv_row: CSVRow
    resource_id: Optional[int] = None
    parent_id: Optional[int] = None
    data: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
```

##### `OperationResult`

Result of operation execution.

```python
@dataclass(frozen=True)
class OperationResult:
    operation: Operation
    success: bool
    resource_id: Optional[int] = None
    message: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    duration_ms: Optional[float] = None
    error: Optional[Exception] = None
```

### importer.models.payloads

**Purpose**: Pydantic models for BAM API request payloads.

#### Key Models

##### `NetworkCreatePayload`

```python
class NetworkCreatePayload(BaseModel):
    name: str
    cidr: str
    properties: Optional[dict[str, str]] = None
```

##### `HostRecordCreatePayload`

```python
class HostRecordCreatePayload(BaseModel):
    name: str
    absoluteName: bool = True
    addresses: list[str]
    properties: Optional[dict[str, str]] = None
```

## Dependency Management

### importer.dependency.graph

**Purpose**: Build and manage dependency graphs for operations.

#### Key Classes

##### `DependencyGraph`

Directed acyclic graph (DAG) of resource dependencies.

```python
class DependencyGraph:
    def __init__(self)
    def add_operation(self, operation: Operation) -> None
    def add_dependency(self, from_id: str, to_id: str) -> None
    def get_topological_order(self) -> list[str]
    def detect_cycles(self) -> list[list[str]]
    def get_execution_phases(self) -> list[list[str]]
```

**Dependency Rules:**
- Parent before child (block → network → address)
- Zone before records (zone → A/AAAA/CNAME/MX/TXT/SRV)
- Host records before aliases/CNAME targets
- Networks before DHCP options/ranges

### importer.dependency.planner

**Purpose**: Optimize execution order based on dependencies.

#### Key Classes

##### `DependencyPlanner`

Creates optimal execution plans.

```python
class DependencyPlanner:
    def __init__(self, config: ImporterConfig)
    def create_plan(self, operations: list[Operation]) -> ExecutionPlan
    def optimize_batching(self, plan: ExecutionPlan) -> ExecutionPlan
```

**Optimization Strategies:**
1. Type-based batching
2. Parent-child co-location
3. Critical path identification
4. Parallel maximization

## Observability

### importer.observability.logger

**Purpose**: Structured logging with context.

#### Setup

```python
from importer.observability.logger import setup_logging

setup_logging(
    level="INFO",
    format="json",
    file="logs/importer.log",
    audit=True
)
```

#### Usage

```python
import structlog

logger = structlog.get_logger(__name__)

# With context
logger.info("Processing operation",
           operation_id=op.row_id,
           resource_type=op.object_type,
           phase="execution")
```

### importer.observability.metrics

**Purpose**: Metrics collection for monitoring.

#### Key Classes

##### `MetricsCollector`

Collects and exposes metrics.

```python
class MetricsCollector:
    def counter(self, name: str) -> Counter
    def histogram(self, name: str) -> Histogram
    def gauge(self, name: str) -> Gauge
    def get_summary(self) -> dict[str, Any]
```

#### Metrics Categories

- **Operations**: Total, created, updated, deleted
- **Performance**: Latency, throughput, queue depth
- **Errors**: By type, by resource
- **Resources**: Cache hits, API calls
- **System**: Memory, CPU, goroutines

### importer.observability.reporter

**Purpose**: Generate HTML and JSON reports.

#### Key Classes

##### `ReportGenerator`

Creates comprehensive reports.

```python
class ReportGenerator:
    def __init__(self, template_dir: Path)
    async def generate_html_report(self, results: list[OperationResult]) -> str
    async def generate_json_report(self, results: list[OperationResult]) -> dict
```

**Report Sections:**
1. Executive summary
2. Operation statistics
3. Success/failure breakdown
4. Performance metrics
5. Error details
6. Resource changes
7. Dependency graph

## Persistence

### importer.persistence.changelog

**Purpose**: SQLite-based change tracking for rollback.

#### Key Classes

##### `Changelog`

Tracks all successful operations.

```python
class Changelog:
    def __init__(self, db_path: Path)
    async def initialize(self) -> None
    async def add_operation(self, operation: Operation, result: OperationResult) -> None
    async def get_session_operations(self, session_id: str) -> list[OperationResult]
    async def generate_rollback(self, session_id: str) -> Path
```

**Schema:**
```sql
CREATE TABLE changelog (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    row_id TEXT NOT NULL,
    object_type TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_id INTEGER,
    old_data TEXT,  -- JSON
    new_data TEXT,  -- JSON
    success BOOLEAN NOT NULL,
    message TEXT
);
```

### importer.persistence.checkpoint

**Purpose**: Resume capability for interrupted imports.

#### Key Classes

##### `CheckpointManager`

Manages checkpoints for resumable imports.

```python
class CheckpointManager:
    def __init__(self, checkpoint_dir: Path)
    async def save_checkpoint(self, session_id: str, completed_ops: list[str]) -> None
    async def load_checkpoint(self, session_id: str) -> list[str]
    async def create_checkpoint_path(self, session_id: str) -> Path
```

**Checkpoint Format:**
```json
{
    "session_id": "20241214_abc123",
    "timestamp": "2024-12-14T10:30:00Z",
    "completed_operations": ["row_1", "row_2", "row_3"],
    "current_phase": 2,
    "total_phases": 3
}
```

## Rollback

### importer.rollback.generator

**Purpose**: Generate inverse CSV for rollback operations.

#### Key Classes

##### `RollbackGenerator`

Creates rollback CSV from changelog.

```python
class RollbackGenerator:
    def __init__(self, changelog: Changelog)
    async def generate_rollback_csv(self, session_id: str) -> Path
    async def generate_rollback_operations(self, session_id: str) -> list[Operation]
```

**Rollback Logic:**
1. Reverse operation order (delete dependencies first)
2. Invert actions:
   - CREATE → DELETE
   - DELETE → CREATE (if old_data available)
   - UPDATE → UPDATE (with old data)
3. Preserve UDFs and properties

## Validation

### importer.validation.safety

**Purpose**: Safety checks for dangerous operations.

#### Key Classes

##### `SafetyValidator`

Validates operations against safety policies.

```python
class SafetyValidator:
    def __init__(self, config: PolicyConfig)
    async def validate_operation(self, operation: Operation) -> ValidationResult
    async def validate_batch(self, operations: list[Operation]) -> ValidationResult
```

**Safety Rules:**
1. **NEVER DELETE**:
   - Configurations
   - DNS Views

2. **HIGH RISK** (requires flag):
   - IP4/IP6 Blocks
   - IP4/IP6 Networks
   - DNS Zones

3. **SAFE**:
   - IP Addresses
   - DNS Records
   - DHCP Options
   - Tags

## Utilities

### importer.utils.exceptions

**Purpose**: Hierarchical exception system.

#### Exception Hierarchy

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

### importer.utils.locking

**Purpose**: Prevent concurrent resource modification conflicts.

#### Key Classes

##### `KeyedLock`

Lock manager with resource-specific locks.

```python
class KeyedLock:
    def __init__(self)
    async def acquire(self, key: str) -> None
    async def release(self, key: str) -> None
    async def with_lock(self, key: str, coro: Coroutine) -> Any
```

**Usage:**
```python
lock = KeyedLock()

async with lock.with_lock("resource_123"):
    # Critical section for resource 123
    resource = await client.get("resource", 123)
    await client.update("resource", 123, updates)
```

## Integration Examples

### Adding a New Resource Type

1. **Create CSV Model** (`csv_row.py`):
```python
class CustomResourceRow(CSVRow):
    object_type: Literal["custom_resource"]
    name: str
    custom_field: str
    config: str
```

2. **Create Handler** (`handlers.py`):
```python
class CustomResourceHandler(OperationHandler):
    async def create(self, client: BAMClient, operation: Operation) -> dict:
        # Implementation
        pass

    async def update(self, client: BAMClient, operation: Operation) -> dict:
        # Implementation
        pass

    async def delete(self, client: BAMClient, operation: Operation) -> None:
        # Implementation
        pass
```

3. **Register Handler**:
```python
HANDLER_REGISTRY["custom_resource"] = CustomResourceHandler()
```

4. **Add API Methods** (`client.py` if needed):
```python
async def create_custom_resource(self, parent_id: int, data: dict) -> dict:
    return await self.create("customResource", parent_id, data)
```

### Custom Validation Logic

```python
from importer.validation.safety import SafetyValidator

class CustomSafetyValidator(SafetyValidator):
    async def validate_operation(self, operation: Operation) -> ValidationResult:
        # Run standard validation
        result = await super().validate_operation(operation)

        # Add custom validation
        if operation.object_type == "custom_resource":
            if operation.data.get("custom_field") == "forbidden":
                result.add_error("Custom field cannot be 'forbidden'")

        return result
```

### Custom Metrics

```python
from importer.observability.metrics import get_metrics

metrics = get_metrics()

# Custom counter
custom_counter = metrics.counter("custom_operations_total")
custom_counter.inc()

# Custom histogram
custom_histogram = metrics.histogram("custom_operation_duration")
custom_histogram.observe(duration_ms)

# Custom gauge
custom_gauge = metrics.gauge("custom_queue_size")
custom_gauge.set(queue_size)
```

This module guide provides comprehensive documentation for each component of the BlueCat CSV Importer, enabling developers to understand, extend, and integrate with the system effectively.