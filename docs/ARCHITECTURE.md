# BlueCat CSV Importer - Architecture

**Last Updated:** 2025-12-08 | **Version:** 0.3.0

## Overview

This document describes the architecture of the BlueCat CSV Importer, a production-grade tool for bulk importing resources into BlueCat Address Manager via CSV files.

## Design Principles

1. **Idempotency**: Same CSV + same BAM state = same result
2. **Observability**: Every operation logged and traceable
3. **Recoverability**: Resume from any point, undo any import
4. **Safety**: Validate before execution, verify before rollback
5. **Performance**: Adaptive throttling, parallel execution, caching
6. **Type Safety**: Full type annotations, Pydantic validation

## Implementation Status

### Completed Components

- **Project Structure**: Complete directory layout and configuration
- **Data Models**: Pydantic v2 models with discriminated unions
- **CSV Parser**: Schema-aware parser with validation
- **BAM Client**: Async HTTP client with httpx and retry logic
- **Resolver**: Path-to-ID resolver with disk caching
- **Configuration**: YAML-based configuration management
- **CLI**: Typer-based CLI with Rich output
- **Tests**: Unit tests for models and parser
- **State Loader**: Fetch current state from BAM
- **Diff Engine**: Compare desired vs current state
- **Dependency Graph**: DAG with cycle detection
- **Execution Engine**: Async operation executor with throttling
- **Changelog**: SQLite-based change tracking
- **Checkpoint Store**: Resume support with checkpoints
- **Rollback Generator**: Automatic inverse CSV generation
- **Metrics & Reporting**: Prometheus, StatsD, JSON/HTML reports
- **Progress Bars**: Real-time progress with Rich
- **Structured Logging**: Production-grade logging with structlog

## Architecture Layers

```
┌─────────────────────────────────────────────────────────┐
│                    CLI Layer (Typer)                    │
│            Human-friendly commands and output           │
└─────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────┐
│                  Orchestration Layer                    │
│     Pipeline coordination, error handling, reporting    │
└─────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────┐
│                    Core Engine Layer                    │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐            │
│  │  Parser  │  │ Resolver │  │   Diff    │            │
│  │          │→ │          │→ │  Engine   │            │
│  └──────────┘  └──────────┘  └───────────┘            │
│         CSV → Models → IDs → Operations                │
└─────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────┐
│               Execution & State Layer                   │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐            │
│  │Dependency│  │ Executor │  │ Changelog │            │
│  │  Graph   │→ │          │→ │           │            │
│  └──────────┘  └──────────┘  └───────────┘            │
└─────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────┐
│                   Integration Layer                     │
│              BAM REST API v2 Client (httpx)             │
└─────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────┐
│               Persistence & Cache Layer                 │
│    SQLite (changelog)  │  diskcache (resolver)          │
└─────────────────────────────────────────────────────────┘
```

## Data Flow

### Import Pipeline

```
1. Schema Validation
   CSV File → Check version compatibility

2. Parse
   CSV → DictReader → Pydantic models
   └─ Discriminated unions select correct model type
   └─ Whitespace stripping, field validation

3. Pre-flight Validation (Future)
   Models → Syntax checks, dependency validation

4. Resolve
   Paths → BAM IDs (with caching)
   └─ Check pending creates
   └─ Query disk cache
   └─ Fall back to BAM API

5. State Load (Future)
   BAM IDs → Current state
   └─ Fetch existing resources

6. Diff (Future)
   Desired state + Current state → Operations
   └─ Create / Update / Delete / Noop

7. Plan Build (Future)
   Operations → Execution graph
   └─ Topological sort by dependencies

8. Execute (Future)
   Graph → Async execution with throttling

9. Change Log (Future)
   Operations → SQLite database

10. Generate Rollback (Future)
    Changelog → Inverse CSV
```

## Key Components

### CSV Parser (`core/parser.py`)

**Responsibilities**:
- Read CSV files using Python's csv.DictReader
- Validate schema version (defaults to 3.0)
- Convert rows to Pydantic models
- Handle validation errors (strict and non-strict modes)

**Key Features**:
- Order-independent columns (uses headers)
- Automatic whitespace stripping
- UDF field preservation
- Detailed error reporting with line numbers

### Pydantic Models (`models/csv_row.py`)

**Design**:
- Base class `CSVRowBase` for common fields
- Discriminated union on `object_type` field
- Specific models for each resource type:
  - `IP4NetworkRow`
  - `IP4BlockRow`
  - `IP4AddressRow`
  - `HostRecordRow`
  - `DNSZoneRow`
  - `IPv4DHCPRangeRow`
  - `DHCPDeploymentRoleRow`
  - `DNSDeploymentRoleRow`
  - `ExternalHostRecordRow`
  - `LocationRow` - Hierarchical location management
  - `GenericRecordRow` - Custom DNS record types
  - `IPv6BlockRow` - IPv6 address blocks
  - `IPv6NetworkRow` - IPv6 networks
  - `IPv6AddressRow` - IPv6 addresses
  - `IPv6DHCPRangeRow` - DHCPv6 ranges
  - `TagGroupRow` - Tag group definitions
  - `TagRow` - Tag definitions
  - `ResourceTagRow` - Resource tag associations
  - `UDFDefinitionRow` - User-Defined Field definitions
  - `UDLDefinitionRow` - User-Defined Link definitions

**Validation**:
- IP address validation with `ipaddress` module
- CIDR notation validation
- MAC address format validation (AA:BB:CC:DD:EE:FF or AA-BB-CC-DD-EE-FF)
- DHCP range format validation (startIP-endIP)
- DHCP option code validation (1-254)
- DHCP role type validation (PRIMARY, SECONDARY, ACTIVE, PASSIVE, NONE)
- Watermark percentage validation (0-100)
- IP address state validation (STATIC, RESERVED, DHCP_RESERVED, GATEWAY)
- Custom validators with `@field_validator`

### BAM Endpoints (`bam/endpoints.py`)

**Purpose**: Centralized API endpoint configuration for all BAM REST API v2 paths.

**Features**:
- Single source of truth for all endpoint paths
- Reduces risk of typos in endpoint strings
- Makes API version upgrades easier
- Helper methods for common ID substitutions
- Frozen dataclass for immutability

**Usage**:
```python
from importer.bam.endpoints import BAMEndpoints

# Using constants
endpoint = BAMEndpoints.CONFIGURATIONS  # "configurations"

# Using string formatting
endpoint = BAMEndpoints.BLOCK_BY_ID.format(block_id=123)  # "blocks/123"

# Using helper methods (recommended)
endpoint = BAMEndpoints.block_networks(123)  # "blocks/123/networks"
endpoint = BAMEndpoints.zone_resource_records(456)  # "zones/456/resourceRecords"
```

**Available Endpoints**:
- Authentication: `SESSIONS`
- Configurations: `CONFIGURATIONS`, `CONFIGURATION_BY_ID`, `CONFIGURATION_BLOCKS`, `CONFIGURATION_VIEWS`
- Blocks: `BLOCKS`, `BLOCK_BY_ID`, `BLOCK_NETWORKS`, `BLOCK_SUB_BLOCKS`
- Networks: `NETWORKS`, `NETWORK_BY_ID`, `NETWORK_ADDRESSES`, `NETWORK_RANGES`, `NETWORK_DEPLOYMENT_OPTIONS`, `NETWORK_DEPLOYMENT_ROLES`
- Addresses: `ADDRESSES`, `ADDRESS_BY_ID`
- Views: `VIEWS`, `VIEW_BY_ID`, `VIEW_ZONES`, `VIEW_DEPLOYMENT_ROLES`
- Zones: `ZONES`, `ZONE_BY_ID`, `ZONE_SUB_ZONES`, `ZONE_RESOURCE_RECORDS`, `ZONE_DEPLOYMENT_ROLES`
- Resource Records: `RESOURCE_RECORDS`, `RESOURCE_RECORD_BY_ID`
- DHCP: `RANGES`, `RANGE_BY_ID`
- Deployment: `DEPLOYMENT_OPTIONS`, `DEPLOYMENT_OPTION_BY_ID`, `DEPLOYMENT_ROLES`, `DEPLOYMENT_ROLE_BY_ID`
- Locations: `LOCATIONS`, `LOCATION_BY_ID`, `LOCATION_CHILD_LOCATIONS`, `LOCATION_ANNOTATED_RESOURCES`
- Servers: `SERVERS`, `SERVER_BY_ID`, `SERVER_INTERFACES`

### Type-Safe Payload Models (`models/payloads.py`)

**Purpose**: Pydantic models for BAM API request payloads with validation.

**Features**:
- Type validation before API calls
- IDE autocomplete for payload fields
- Automatic CIDR/IP/MAC address validation
- Consistent payload structure

**Available Payload Models**:
- IP Resources: `IPv4BlockPayload`, `IPv4NetworkPayload`, `IPv4AddressPayload`, `IPv4DHCPRangePayload`
- DNS Zones: `ZonePayload`, `ExternalHostsZonePayload`
- DNS Records: `HostRecordPayload`, `AliasRecordPayload`, `MXRecordPayload`, `TXTRecordPayload`, `SRVRecordPayload`, `ExternalHostRecordPayload`, `GenericRecordPayload`
- Deployment: `DHCPDeploymentRolePayload`, `DNSDeploymentRolePayload`, `DHCPv4ClientOptionPayload`, `DHCPv4ServiceOptionPayload`
- Locations: `LocationPayload`
- Helper Models: `MACAddressPayload`, `AddressObject`, `LinkedRecordRef`, `ViewRef`, `InterfaceRef`

**Usage**:
```python
from importer.models.payloads import IPv4BlockPayload, HostRecordPayload, AddressObject

# Create a block payload with validation
block = IPv4BlockPayload(name="Corp Block", range="10.0.0.0/8")
await client.post(endpoint, json=block.model_dump(exclude_none=True))

# Create a host record payload
addresses = [AddressObject(type="IPv4Address", address="10.1.0.10")]
host = HostRecordPayload(name="www", addresses=addresses, ttl=3600)
await client.post(endpoint, json=host.model_dump(exclude_none=True))

# Invalid data raises ValidationError at creation time, not at API call
try:
    block = IPv4BlockPayload(name="Test", range="invalid-cidr")  # Raises!
except ValidationError as e:
    print(f"Invalid payload: {e}")
```

### Response Validation Models (`bam/response_models.py`)

**Purpose**: Pydantic models for BAM API responses providing early error detection and resilience to API changes.

**Design Principles**:
- **Graceful degradation**: `extra="allow"` for unknown fields (forward compatibility)
- **Backward compatibility**: Field aliases for renamed fields
- **Optional validation**: Can be used selectively for critical paths
- **Type safety**: IDE autocomplete and better error messages

**Available Response Models**:
- `AuthenticationResponse`: POST /sessions authentication endpoint
- `BAMResourceResponse`: All resource creation/retrieval (validates id, name, type, properties)
- `PaginatedResponse`: List endpoints with HAL+JSON format (data, _links, _embedded)
- `HALLinks`: HAL navigation links for pagination
- `ErrorResponse`: Structured error responses with message extraction

**Usage**:
```python
from importer.bam.response_models import AuthenticationResponse, BAMResourceResponse

# Validate authentication response
auth_data = response.json()
validated = AuthenticationResponse.model_validate(auth_data)
token = validated.apiToken  # Guaranteed to exist or ValidationError raised

# Validate resource creation
resource_data = response.json()
validated = BAMResourceResponse.model_validate(resource_data)
resource_id = validated.id  # ID validation ensures positive integer

# Client uses validation with fallback for backward compatibility
result = await client.create_ip4_block(config_id, cidr, name)
# Logs warning if validation fails but continues with raw data
```

**Benefits**:
- **Early failure detection**: ValidationError at API boundary, not deep in code
- **Better error messages**: "Field 'id' is required" vs "NoneType has no attribute"
- **API change resilience**: Explicit validation catches breaking changes immediately
- **Type safety**: Full IDE support for response fields

**Validation Strategy**:
- Critical paths (auth, resource creation) use validation with fallback to raw dict
- Validation failures log warnings but don't break existing code
- Can be made strict after stability period
- ~5-10% latency overhead acceptable for critical operations


### BAM Client (`bam/client.py`)

**Features**:
- Async/await with httpx
- Automatic authentication and token management per official BAM REST API v2
- Retry logic with tenacity
- Rate limit handling (429 responses with Retry-After header)
- Connection pooling
- HAL+JSON format support with `_links` and `_embedded`
- Custom x-bcn-* header support
- **Centralized endpoints**: Uses `BAMEndpoints` for all API paths
- **Security**: Automatic escaping of filter parameters to prevent injection attacks

**Authentication** (per official API):
- Endpoint: `POST /api/v2/sessions`
- Request: `{"username": "user", "password": "pass"}`
- Response: `{"apiToken": "...", "basicAuthenticationCredentials": "..."}`
- Uses Bearer token authentication
- Thread-safe token refresh with `asyncio.Lock` to prevent race conditions during concurrent requests

**Key Methods**:
- `authenticate(force=False)`: Obtain and refresh auth tokens via `/api/v2/sessions` (uses lock to prevent concurrent auth requests)
- `get()`, `post()`, `put()`, `delete()`: HTTP methods with custom header support
- `get_configuration_by_name()`: Configuration lookup via `/api/v2/configurations`
- `get_entity_by_id()`: Type-specific entity lookup via `/api/v2/{resource_type}/{id}`
- `update_entity_by_id()`: Type-specific entity update via `/api/v2/{resource_type}/{id}`
- `delete_entity_by_id()`: Type-specific entity deletion via `/api/v2/{resource_type}/{id}`
- `create_ip4_block()`: Create block via `POST /api/v2/configurations/{id}/blocks`
- `create_ip4_network()`: Create network via `POST /api/v2/blocks/{id}/networks`
- `create_ip4_address()`: Create address via `POST /api/v2/networks/{id}/addresses`
- `create_ipv4_dhcp_range()`: Create DHCP range via `POST /api/v2/networks/{networkId}/ranges` (full options with range string)
- `create_ipv4_dhcp_range_simple()`: Create DHCP range with separate start/end IP addresses
- `create_dhcp_deployment_role()`: Create DHCP deployment role via `POST /api/v2/networks/{networkId}/deploymentRoles` or `POST /api/v2/blocks/{blockId}/deploymentRoles`
- `create_dns_deployment_role()`: Create DNS deployment role via `POST /api/v2/zones/{zoneId}/deploymentRoles`
- `create_external_host_record()`: Create external host record via `POST /api/v2/zones/{zoneId}/resourceRecords`
- `create_generic_record()`: Create custom DNS record via `POST /api/v2/zones/{zoneId}/resourceRecords`
- `create_location()`: Create location via `POST /api/v2/locations/{parentId}/locations`
- `update_location()`: Update location via `PUT /api/v2/locations/{id}`
- `delete_location()`: Delete location via `DELETE /api/v2/locations/{id}`
- `get_location_by_code()`: Lookup location by code
- `get_locations()`: List all locations
- `get_server_interfaces()`: Get server interfaces for deployment roles
- `resolve_interface_string()`: Resolve interface identifier to ID

> **Note:** Previously, this project included `create_dhcp_client_identifier()`, `create_dhcp_vendor_option()`, and `create_dhcpv4_client_class()` methods.
> These were removed as they used endpoints that don't exist in the BAM API v9.6.0 OpenAPI specification.
> See `OPENAPI_VALIDATION_REPORT.md` for details. For DHCP reservations, use MAC address objects instead.

**Resource Hierarchy** (per official API):
```
Configuration
├── Block (POST /configurations/{id}/blocks)
│   └── Network (POST /blocks/{id}/networks)
│       └── Address (POST /networks/{id}/addresses)
└── View (POST /configurations/{id}/views)
    └── Zone (POST /views/{id}/zones)
        └── Resource Record (POST /zones/{id}/resourceRecords)

Locations (hierarchical, separate from IP/DNS hierarchy):
Location
└── Child Location (POST /locations/{id}/locations)
    └── Grandchild Location
```

### Resolver (`core/resolver.py`)

**Purpose**: Convert human-readable paths to BAM resource IDs

**Caching Strategy**:
1. **Pending Creates**: In-memory tracking of resources being created in current batch
2. **Disk Cache**: Persistent cache using diskcache
3. **BAM API**: Fallback to live queries
4. **Deferred Resolution**: Special handling for parent-child dependencies in same CSV

**Deferred Resolution Feature**:
- **PendingResources**: Pre-scans CSV for resources being created in current batch
- **Deferred Markers**: Special markers for unresolved dependencies:
  - `_deferred_block_cidr`: Block CIDR not yet created
  - `_deferred_network_cidr`: Network CIDR not yet created
  - `_deferred_zone_name`: DNS zone name not yet created
  - `_deferred_location_code`: Location code not yet created
- **Dynamic Resolution**: During execution, resolves deferred IDs after parent resources are created

**Key Methods**:
- `resolve()`: Convert path to BAM ID (with deferred resolution support)
- `register_pending_create()`: Track pending operations
- `confirm_create()`: Update cache after successful create
- `cancel_create()`: Clean up failed creates
- `prefetch_hierarchy()`: Bulk load for performance
- `is_pending_create()`: Check if resource is pending creation in current batch

### Configuration (`config.py`)

**Structure**:
- `PolicyConfig`: Behavior policies (auto-creation, conflicts, orphans)
- `BAMConfig`: BAM connection settings
- `LoggingConfig`: Logging configuration
- `ImporterConfig`: Combined configuration

**Loading**:
- From YAML file: `ImporterConfig.from_file(path)`
- From environment: `ImporterConfig.from_env()`

## Phase 2 Components

### State Loader (`core/state_loader.py`)

**Purpose**: Fetch current state from BAM for comparison with desired CSV state

**Features**:
- Configurable fetch strategies (SHALLOW, CHILDREN, DEEP)
- Caching to minimize API calls
- Batch loading with concurrency control (default: 10 concurrent)
- Pagination support for large result sets
- HAL+JSON response parsing

**Official API Endpoints** (per BlueCat REST API v2):
- GET /api/v2/configurations - List configurations
- GET /api/v2/blocks/{id} - Get specific block
- GET /api/v2/networks/{id} - Get specific network
- GET /api/v2/addresses/{id} - Get specific address
- GET /api/v2/zones/{id} - Get specific zone
- GET /api/v2/configurations/{id} - Get specific configuration
- GET /api/v2/ranges/{id} - Get specific DHCP range
- GET /api/v2/deploymentRoles/{id} - Get specific deployment role
- GET /api/v2/blocks/{id}/networks - Get networks under block
- GET /api/v2/networks/{id}/addresses - Get addresses under network
- GET /api/v2/networks/{id}/ranges - Get DHCP ranges under network
- GET /api/v2/networks/{id}/deploymentRoles - Get deployment roles under network
- GET /api/v2/zones/{id}/deploymentRoles - Get deployment roles under zone

**Key Methods**:
- `load_resource_state()`: Load single resource with strategy
- `batch_load()`: Load multiple resources in parallel
- `clear_cache()`: Clear cached states

### Diff Engine (`core/diff_engine.py`)

**Purpose**: Compare desired CSV state vs current BAM state

**Operations Determined**:
- CREATE: Resource doesn't exist in BAM
- UPDATE: Resource exists but fields differ
- DELETE: Resource should be removed
- NOOP: No changes needed
- ORPHAN: Resource in BAM but not in CSV

**Features**:
- Field-level change detection with normalization
- Policy-driven behavior (update_mode, safe_mode)
- Orphan detection with strict safety scoping
- Conflict detection
- Safe mode converts deletes to NOOPs

**Key Methods**:
- `compute_diff()`: Compare desired vs current for single resource
- `detect_orphans()`: Find resources in BAM not in CSV
- `_compute_field_changes()`: Field-level diff with normalization

### Dependency Graph (`dependency/graph.py`)

**Purpose**: Build DAG of operations with cycle detection

**Features**:
- Automatic parent-child dependency detection
- Resource hierarchy: Configuration → Block → Network → Address
- Topological sorting using Kahn's algorithm
- Dependency depth calculation
- Cycle detection and prevention
- Delete operations: children delete before parents
- **Deferred Dependencies**: Handles dependencies on resources being created in the same CSV
- **Delete Phasing**: DELETE operations run in separate phases BEFORE CREATE/UPDATE operations

**Delete Phasing Strategy**:
The dependency graph now properly phases DELETE operations to prevent race conditions:

1. **DELETE operations run FIRST** in REVERSE phase order (children before parents)
   - Phase 5 deletes (DHCP) -> Phase 4 deletes (DNS records) -> ... -> Phase 0 deletes (Blocks)
2. **CREATE/UPDATE operations run AFTER** all deletes in NORMAL phase order
   - Phase 0 creates (Blocks) -> Phase 1 creates (Zones) -> ... -> Phase 5 creates (DHCP)

This ensures:
- No race conditions between delete and recreate of the same resource
- Proper dependency ordering within each operation type
- Children are always deleted before parents
- Parents are always created before children

**Phase Order**:
```
PHASE_ORDER = [
    Phase 0: ip4_block, ip4_network, ip6_block, ip6_network, location
    Phase 1: dns_zone
    Phase 2: external_host_record
    Phase 3: host_record, ip4_address, ip6_address, generic_record
    Phase 4: alias_record, mx_record, srv_record, txt_record
    Phase 5: ipv4_dhcp_range, dhcp_deployment_role, dns_deployment_role, ...
]
DELETE_PHASE_ORDER = reversed(PHASE_ORDER)  # Children before parents
```

**Deferred Dependency Handling**:
- **Pre-scan Analysis**: Identifies parent-child relationships within the same CSV batch
- **Dependency Direction**: Correctly maps dependencies from child to parent resources
- **Depth Calculation**: Uses `_calculate_depths()` to compute proper execution depths
- **Depth Calculation**: Uses `_calculate_depths()` to compute proper execution depths
- **Host Record Dependencies**: Adds host record dependency on networks containing their IP addresses
- **Record Reference Dependencies**: Automatically detects and adds dependencies between DNS records (MX -> Host, Alias -> Host, SRV -> Host) based on target FQDNs.

**Key Methods**:
- `add_operation()`: Add operation as node
- `add_dependency()`: Add dependency edge with cycle check
- `build_from_operations()`: Build complete graph (with deferred dependency support)
- `topological_sort()`: Get execution order
- `get_execution_batches()`: Group by depth for parallelization
- `validate()`: Validate graph integrity
- `_calculate_depths()`: Compute execution depths for all nodes

### Execution Planner (`dependency/planner.py`)

**Purpose**: Create optimized execution plans from dependency graphs

**Features**:
- Batch creation for parallel execution
- Operation grouping by type
- Estimated duration calculation
- Batch size limiting and splitting
- Plan optimization (grouping, ordering)

**Key Components**:
- `ExecutionBatch`: Group of parallel operations with metadata
- `ExecutionPlan`: Complete plan with batches and statistics

**Key Methods**:
- `create_plan()`: Convert dependency graph to execution plan
- `optimize_plan()`: Optimize for performance
- `get_plan_summary()`: Detailed plan statistics

### Adaptive Throttle (`execution/throttle.py`)

**Purpose**: Dynamic concurrency control based on API performance

**Architecture**: Uses manual counter with asyncio.Condition instead of Semaphore to support safe dynamic concurrency adjustment at runtime.

**Features**:
- Starts conservative, increases when healthy
- Decreases on errors or high latency
- Exponential backoff on rate limits
- Tracks: requests, errors, latency, rate limits, active task count
- Automatic adjustment every 10 seconds
- Safe concurrency limit changes without breaking synchronization

**Thresholds**:
- Healthy: < 1% errors, < 1s latency → increase concurrency by 20%
- Unhealthy: > 5% errors or > 1s latency → decrease concurrency by 30%
- Rate limit: immediate decrease

**Key Methods**:
- `acquire()`: Block until slot available (uses Condition wait)
- `release()`: Free a slot and notify waiting tasks
- `record_success()`: Track successful request with latency
- `record_failure()`: Track failed request
- `get_metrics()`: Current throttle metrics including active task count

### Operation Executor (`execution/executor.py`)

**Purpose**: Execute operations against BAM with throttling

**Features**:
- Batch execution with parallel operations
- Adaptive throttle integration
- Automatic retry with exponential backoff
- Rate limit handling (429 with Retry-After)
- Dry-run mode support
- Detailed result tracking
- **Deferred ID Resolution**: Resolves deferred IDs during execution after parent resources are created
- **Payload Safety**: Deep-copies operation payloads to ensure idempotency and prevent in-place modification side-effects
- **Created Resources Tracking**: Tracks resources created during execution for dependency resolution

**Deferred Resolution in Executor**:
- `resolve_deferred_ids()`: Resolve all deferred IDs in operations before execution
- `store_created_resource()`: Store created resource information for deferred resolution
- **Dynamic Resolution**: Automatically resolves deferred dependencies when parent resources are created

**Official API Operations** (per BlueCat REST API v2):
- CREATE Block: POST /api/v2/configurations/{id}/blocks
- CREATE Network: POST /api/v2/blocks/{id}/networks
- CREATE Address: POST /api/v2/networks/{id}/addresses
- CREATE DHCP Range: POST /api/v2/networks/{networkId}/ranges
- CREATE DHCP Deployment Role: POST /api/v2/networks/{networkId}/deploymentRoles or POST /api/v2/blocks/{blockId}/deploymentRoles
- CREATE DNS Deployment Role: POST /api/v2/zones/{zoneId}/deploymentRoles
- CREATE External Host Record: POST /api/v2/zones/{zoneId}/resourceRecords
- UPDATE Block: PUT /api/v2/blocks/{id}
- UPDATE Network: PUT /api/v2/networks/{id}
- UPDATE Address: PUT /api/v2/addresses/{id}
- UPDATE Zone: PUT /api/v2/zones/{id}
- UPDATE Configuration: PUT /api/v2/configurations/{id}
- UPDATE DHCP Range: PUT /api/v2/ranges/{id}
- UPDATE Deployment Role: PUT /api/v2/deploymentRoles/{id}
- DELETE Block: DELETE /api/v2/blocks/{id}
- DELETE Network: DELETE /api/v2/networks/{id}
- DELETE Address: DELETE /api/v2/addresses/{id}
- DELETE Zone: DELETE /api/v2/zones/{id}
- DELETE Configuration: DELETE /api/v2/configurations/{id}
- DELETE DHCP Range: DELETE /api/v2/ranges/{id}
- DELETE Deployment Role: DELETE /api/v2/deploymentRoles/{id}

**Key Methods**:
- `execute_plan()`: Execute complete execution plan
- `_execute_operation()`: Execute single operation with throttle
- `get_statistics()`: Execution statistics and metrics
- `resolve_deferred_ids()`: Resolve deferred IDs before execution
- `store_created_resource()`: Track created resources for deferred resolution

### Operation Handlers (`execution/handlers.py`)

**Purpose**: Strategy pattern implementation for handling different BAM resource types

**Architecture**:
- **Strategy Pattern**: Eliminates large if/elif chains in executor
- **Handler Registry**: Efficient dispatch using HANDLER_REGISTRY
- **Protocol-based**: All handlers implement OperationHandler protocol
- **Unified Operations**: Standardized create, update, delete operations

**Handler Features**:
- **BaseHandler**: Common functionality for all handlers
- **Type-Specific Handlers**: Specialized handlers for each resource type
- **Unified Delete Logic**: Uses `delete_entity_by_id()` for consistent deletion
- **Safety Support**: All handlers accept `allow_dangerous_operations` flag

**Handler Protocol**:
```python
class OperationHandler(Protocol):
    async def create(self, client: BAMClient, operation: Operation) -> Dict[str, Any]: ...
    async def update(self, client: BAMClient, operation: Operation) -> Dict[str, Any]: ...
    async def delete(self, client: BAMClient, operation: Operation, allow_dangerous_operations: bool) -> None: ...
```

**Key Methods**:
- `create_resource()`: Generic create operation
- `update_resource()`: Generic update operation
- `delete_resource()`: Generic delete operation with safety checks
- `_update_generic_entity()`: Unified update logic for all entity types

### ChangeLog (`persistence/changelog.py`)

**Purpose**: SQLite-based audit trail and change tracking

**Features**:
- Records before/after state for all operations
- Session-based grouping
- Query by session, resource, time range
- Indexed for fast lookups

**Database Schema**:
```sql
changelog:
  - id, timestamp, session_id
  - operation_type, object_type, resource_id, row_id
  - before_state (JSON), after_state (JSON)
  - success, error_message, metadata (JSON)
Indexes: session_id, resource_id, timestamp
```

**Key Methods**:
- `record_operation()`: Record operation with before/after state
- `get_session_entries()`: Get all entries for a session
- `get_resource_history()`: Get change history for resource
- `get_successful_creates()`: For rollback generation
- `get_sessions()`: List recent sessions with statistics

### CheckpointManager (`persistence/checkpoint.py`)

**Purpose**: Resume support with checkpoint persistence

**Features**:
- Save checkpoints after each batch
- Track execution progress
- Session status tracking (in_progress, completed, failed)
- Automatic cleanup of old checkpoints

**Database Schema**:
```sql
checkpoints:
  - id, timestamp, session_id
  - batch_id, operation_index
  - completed_operations, total_operations
  - status, metadata (JSON)
Indexes: session_id, timestamp
```

**Key Methods**:
- `save_checkpoint()`: Save execution checkpoint
- `get_last_checkpoint()`: Get last checkpoint for session
- `can_resume()`: Check if session can be resumed
- `mark_completed()` / `mark_failed()`: Update session status
- `cleanup_old_checkpoints()`: Remove old checkpoints (30+ days)

### RollbackGenerator (`rollback/generator.py`)

**Purpose**: Generate inverse CSV for rollback operations

**Features**:
- Converts operations to their inverse
- Reverse chronological order
- Includes metadata comments in CSV
- Rollback manifest with statistics

**Operation Conversions**:
- CREATE → DELETE (with bam_id for precise targeting)
- UPDATE → UPDATE (restore from before_state)
- DELETE → Complex (requires recreation from before_state)

**Key Methods**:
- `generate_rollback_csv()`: Generate rollback CSV for session
- `get_rollback_manifest()`: Get rollback summary and statistics
- `_create_delete_row()`: Convert CREATE to DELETE
- `_create_restore_row()`: Convert UPDATE to restore UPDATE

**Output Format**:
```csv
# Rollback CSV for session: {session_id}
# Generated: {timestamp}
# Operations: {count}
row_id,object_type,action,bam_id,verify_name,verify_address,...
rollback_1,ip4_address,delete,12345,server1,10.1.0.5,...
```

## Phase 3 Components (Observability)

### MetricsCollector (`observability/metrics.py`)

**Purpose**: Export metrics to monitoring systems

**Backends**:
- **LoggingBackend**: Development/debugging (logs via structlog)
- **StatsDBackend**: StatsD integration (requires `statsd` package)
- **PrometheusBackend**: Prometheus /metrics endpoint (requires `prometheus-client`)

**Metrics Tracked**:
- Import metrics: started, completed, failed, duration
- Operation metrics: by type, status, duration
- API metrics: calls, latency, errors, rate limits
- Throttle metrics: concurrency, error rate, adjustments
- Resource state tracking

**Key Methods**:
- `record_import_started()` / `record_import_completed()` / `record_import_failed()`
- `record_operation()`: Track operation execution
- `record_batch_completed()`: Track batch execution
- `record_api_call()`: Track BAM API calls
- `record_throttle_metrics()`: Track concurrency state

### ReportGenerator (`observability/reporter.py`)

**Purpose**: Generate comprehensive JSON/HTML reports

**Features**:
- JSON reports with full statistics
- HTML reports with CSS styling and visualizations
- Operation breakdown (CREATE/UPDATE/DELETE/NOOP)
- Performance metrics (duration, ops/sec)
- Error summaries with details
- Rollback information

**ImportReport Structure**:
```python
- session_id, start_time, end_time, duration_seconds, status
- total_operations, successful_operations, failed_operations
- creates, updates, deletes, noops
- avg_operation_duration_ms, max_operation_duration_ms
- operations_per_second
- initial_concurrency, final_concurrency, rate_limit_hits
- errors: [row_id, object_type, operation_type, error]
- rollback_csv_generated, rollback_csv_path
```

**Key Methods**:
- `generate_report()`: Create report from results
- `write_json_report()`: Write JSON format
- `write_html_report()`: Write HTML with visualizations
- `get_session_summary()`: Get summary from changelog

### Enhanced Logging (`observability/logger.py`)

**Purpose**: Production-grade structured logging

**Features**:
- Structured logging with structlog
- JSON logs for production, pretty console for development
- Context variables for request tracing
- File logging support
- LogContext manager for scoped context

**Key Functions**:
- `configure_logging()`: Configure structlog and stdlib logging
- `add_context()`: Add context variables to logs
- `clear_context()`: Clear specific context
- `clear_all_context()`: Clear all context
- `LogContext`: Context manager for scoped logging

**Usage**:
```python
configure_logging(level="INFO", log_file=Path("import.log"), json_logs=True)

with LogContext(session_id="abc123", user="admin"):
    logger.info("operation")  # Includes session_id and user
```

### CLI Enhancements (`cli.py`)

**Purpose**: User-friendly command-line interface with Rich

**Apply Command** (Phase 3):
- Rich progress bars with spinner, bar, time tracking
- Multi-stage progress: parse, connect, load state, diff, graph, plan, execute
- Panel-based information display
- Session ID generation and tracking
- Duration tracking and statistics

**Status Command**:
- Check session status from checkpoint database
- Display checkpoint info in Rich table
- Show progress (completed/total, percentage)
- Status indicators (in_progress, completed, failed)
- Resume instructions

**History Command**:
- List recent sessions from changelog
- Rich table with session summaries
- Duration calculations
- Color-coded success rates

**Version Command**:
- Panel display with version information
- Feature list and implementation status
- Version: 0.3.0

## Error Handling

### Exception Hierarchy

```
ImporterError (base)
├── ValidationError
│   ├── CSVValidationError
│   └── SchemaValidationError
├── ResourceNotFoundError
├── PendingCreateError
├── CyclicDependencyError
├── DeferredResolutionError  # Fail-fast on unresolved dependencies
└── BAMAPIError
    ├── ResourceAlreadyExistsError  # HTTP 409 Conflict
    ├── BAMRateLimitError           # HTTP 429 Too Many Requests
    └── BAMAuthenticationError      # HTTP 401 Unauthorized
```

### DeferredResolutionError

**Purpose**: Fail fast when deferred dependencies cannot be resolved during execution.

When an operation requires a parent resource ID that was expected to be created by a previous operation, but that operation either failed or was skipped, `DeferredResolutionError` is raised instead of continuing with a missing ID.

**Attributes**:
- `row_id`: Row ID of the operation that failed
- `resource_type`: Type of the deferred resource (block, network, zone)
- `deferred_key`: The deferred placeholder key
- `deferred_value`: The value that could not be resolved

**Example**:
```python
# If block "10.0.0.0/8" was never created, this error is raised:
DeferredResolutionError(
    row_id="row_5",
    resource_type="block",
    deferred_key="_deferred_block_cidr",
    deferred_value="10.0.0.0/8"
)
# Message: "Critical Dependency Failure: Could not resolve deferred block '10.0.0.0/8'
#           for row row_5. The parent block creation likely failed or was skipped."
```

### Error Recovery

- **CSV Validation**: Collect all errors in non-strict mode
- **API Errors**: Retry with exponential backoff
- **Rate Limits**: Global pause for all workers
- **Dependency Failures**: Skip dependent operations
- **409 Conflicts**: Lookup existing resource by name/address and convert CREATE to UPDATE

## Testing Strategy

### Unit Tests (`tests/unit/`)

- `test_models.py`: Pydantic model validation
- `test_parser.py`: CSV parsing and validation
- More to come...

### Test Coverage

- All models have validation tests
- Parser tested with valid and invalid inputs
- Error handling verification
- Edge cases (whitespace, missing fields, UDFs)

### Running Tests

```bash
# Run all tests
pytest -v

# Run with coverage
pytest --cov=src/importer --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_parser.py -v
```

## Performance Considerations

### Caching

- **Resolver Cache**: Disk-based with 1-hour expiration
- **Prefetch**: Bulk load hierarchies before processing
- **Connection Pooling**: Reuse HTTP connections

### Concurrency

- Async/await for I/O operations
- Configurable concurrency limits
- Adaptive throttling based on API health

### Memory

- Stream CSV parsing (not loading entire file)
- SQLite for changelog (not in-memory)
- Disk cache for resolver (not in-memory)

## Deferred Resolution Design (DOC-001)

### Overview

Deferred resolution enables creating parent and child resources in a single CSV import when the parent doesn't exist yet. Without it, users would need to run multiple imports in sequence.

### Problem Statement

When importing a CSV like this:
```csv
row_id,object_type,action,name,cidr,config,parent_block
1,ip4_block,create,Main Block,10.0.0.0/8,Default,
2,ip4_network,create,Web Network,10.1.0.0/24,Default,10.0.0.0/8
```

Row 2 needs the BAM ID of the block from Row 1, but Row 1 hasn't been created yet during parsing!

### How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                    CSV Parsing Phase                            │
├─────────────────────────────────────────────────────────────────┤
│  1. Pre-scan CSV for CREATE operations                          │
│  2. Build PendingResources registry                             │
│  3. For each row needing parent ID:                             │
│     - If parent in PendingResources → use deferred marker       │
│     - If parent exists in BAM → resolve normally                │
│     - If parent not found → raise ResourceNotFoundError         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Execution Phase                               │
├─────────────────────────────────────────────────────────────────┤
│  1. Execute parent CREATE (e.g., block)                         │
│  2. Call confirm_create(path, bam_id) → stores ID               │
│  3. Execute child CREATE (e.g., network)                        │
│  4. Resolver replaces deferred marker with actual BAM ID        │
└─────────────────────────────────────────────────────────────────┘
```

### Deferred Markers

When a parent resource is pending, the resolver returns a special marker:

| Resource Type | Marker Key | Example Value |
|---------------|------------|---------------|
| Block | `_deferred_block_cidr` | `10.0.0.0/8` |
| Network | `_deferred_network_cidr` | `10.1.0.0/24` |
| Zone | `_deferred_zone_name` | `example.com` |
| Location | `_deferred_location_code` | `NYC` |

### Key Components

#### PendingResources (`core/operation_factory.py`)
Pre-scans CSV for resources being created in the current batch.

```python
pending = PendingResources.from_rows(rows)
if pending.has_block("10.0.0.0/8"):
    # Parent is being created in this batch
    return {"_deferred_block_cidr": "10.0.0.0/8"}
```

#### Resolver Methods (`core/resolver.py`)

| Method | Purpose |
|--------|---------|
| `register_pending_create(path, row_id)` | Track pending operation |
| `confirm_create(path, bam_id)` | Store ID after successful create |
| `cancel_create(path)` | Clean up failed creates |
| `is_pending_create(path)` | Check if resource is pending |

#### Executor Integration (`execution/executor.py`)

```python
# After successful CREATE
result = await client.create_ip4_block(payload)
resolver.confirm_create(f"{config}/{cidr}", result["id"])
```

### Failure Modes

#### 1. Parent CREATE Failed

**Scenario**: Block creation fails, network depends on it.

**Behavior**: 
- Network operation receives `DeferredResolutionError`
- Error message includes: "Deferred dependency not resolved: block 10.0.0.0/8"
- Network operation is marked as failed (not skipped)

**Resolution**: Fix the block creation issue and re-run import.

#### 2. Circular Dependency

**Scenario**: A → B → C → A

**Behavior**: 
- Detected during dependency graph building
- `CyclicDependencyError` raised before execution
- No operations executed

**Resolution**: Restructure CSV to break the cycle.

#### 3. Missing Parent in CSV

**Scenario**: Child references parent that's not in CSV and not in BAM.

**Behavior**:
- `ResourceNotFoundError` during parsing
- Fails fast before any operations

**Resolution**: Add parent to CSV or verify it exists in BAM.

### Troubleshooting

| Symptom | Cause | Solution |
|---------|-------|----------|
| "Deferred dependency not resolved" | Parent CREATE failed | Check parent operation error |
| "Resource not found: block X" | Parent not in CSV or BAM | Add parent to CSV or verify BAM |
| "Cyclic dependency detected" | A depends on B depends on A | Restructure CSV |
| Network created with wrong block | Block CIDR mismatch | Verify CIDR matches exactly |

### Example: Complete Flow

**Input CSV:**
```csv
row_id,object_type,action,name,cidr,config
1,ip4_block,create,Corp Block,10.0.0.0/8,Default
2,ip4_network,create,Server VLAN,10.1.0.0/24,Default
```

**Execution Flow:**
1. Pre-scan identifies block `10.0.0.0/8` as pending
2. Network resolution returns `{parent_id: None, _deferred_block_cidr: "10.0.0.0/8"}`
3. Dependency graph orders: Block before Network
4. Block CREATE executes → `resolver.confirm_create("Default/10.0.0.0/8", 12345)`
5. Network CREATE resolves `_deferred_block_cidr` → finds ID `12345`
6. Network created under block ID `12345`

## Security

### Credentials

- Configuration file with restricted permissions
- Environment variable support
- No credentials in code or logs

### SSL/TLS

- Configurable SSL verification
- Support for custom CA certificates

### Input Validation

- All CSV data validated with Pydantic
- SQL injection prevention (parameterized queries)
- Path traversal prevention

## Future Enhancements

### Phase 2 (Advanced Features)

- Dependency graph with cycle detection
- Full execution engine
- Rollback generation and execution
- Conflict detection and resolution

### Phase 3 (Observability)

- Structured logging with structlog
- Metrics (Prometheus/StatsD)
- Rich progress bars
- JSON reports

### Phase 4 (Polish)

- Export command
- Interactive conflict resolution
- Web UI (optional)
- Advanced documentation

## Contributing

### Code Style

- Type hints on all functions
- Docstrings (Google style)
- Max line length: 100
- Format with black
- Lint with ruff

### Pull Request Checklist

- [ ] Tests added/updated
- [ ] Type hints added
- [ ] Docstrings added
- [ ] README updated if needed
- [ ] ARCHITECTURE.md updated if needed

## References

- **BlueCat Address Manager RESTful v2 API Guide** (PDF Export.pdf)
  - Authentication: POST /api/v2/sessions
  - Resource hierarchy: Configurations → Blocks → Networks → Addresses
  - HAL+JSON response format with _links and _embedded
  - Custom headers: x-bcn-skip-cache, x-bcn-calculate-inherited, etc.
- Pydantic v2 Documentation
- Typer Documentation
- httpx Documentation
