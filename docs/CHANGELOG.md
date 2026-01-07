# Changelog

All notable changes to the BlueCat CSV Importer documentation will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **IP Address Groups Support:** Added IPv4 address groups for organizing IP ranges within networks:
  - `ip4_group` - Create and manage IPv4 address groups
  - Supports IP range specification (e.g., 10.1.1.100-10.1.1.200)
  - Organize IPs within networks for DHCP pools, reserved ranges, etc.
  - Full CRUD operations for IP address groups
  - Sample CSV: `ip4_group.csv`
- **Device Management Support:** Added comprehensive device management capabilities:
  - `device_type` - Create device categories (Cisco, Fortinet, F5, etc.) as GLOBAL resources
  - `device_subtype` - Create specific device models within a type (FortiGate-600E, Catalyst-3750)
  - `device` - Create/update devices with type/subtype assignments and address associations
  - `device_address` - Link/unlink IP addresses to/from devices
  - Full CRUD operations for all device-related resources
  - Sample CSVs: `device_type.csv`, `device_subtype.csv`, `device.csv`, `device_address.csv`
- **Tags & Tag Groups Support:** Added comprehensive tagging system for resource organization:
  - `tag_group` - Create and manage tag groups for organizing tags
  - `tag` - Define tags within tag groups
  - `resource_tag` - Associate tags with resources (networks, addresses, zones, etc.)
  - Full CRUD operations (create, update, delete) for all tag-related resources
  - Sample CSVs: `tag_group.csv`, `tag.csv`, `resource_tag.csv`
- **User-Defined Fields & Links Support:** Added custom metadata capabilities:
  - `udf_definition` - Define custom metadata fields for resource types (TEXT, EMAIL, URL, PHONE, MULTILINE_TEXT)
  - `udl_definition` - Define custom relationships between resource types
  - `user_defined_link` - Create actual links between resources using UDL definitions
  - Apply UDFs to specific resource types or all resources with wildcard `*`
  - Set UDF values on resources using `udf_<FieldName>` columns in CSV
  - Sample CSVs: `udf_definition.csv`, `udl_definition.csv`, `user_defined_link.csv`
- **MAC Pool Management Support:** Added MAC address pool management for DHCP control:
  - `mac_pool` - Create and manage MAC pools (MACPool or DenyMACPool types)
  - `mac_address` - Register MAC addresses globally or with pool association
  - Automatic MAC address format normalization (accepts XX:XX:XX:XX:XX:XX, XX-XX-XX-XX-XX-XX, etc.)
  - Full CRUD operations for MAC pools and addresses
  - Sample CSVs: `mac_pool.csv`, `mac_address.csv`
- **IPv6 Support:** Added full IPv6 support with feature parity to IPv4 including blocks (ip6_block), networks (ip6_network), addresses (ip6_address), and DHCPv6 ranges (ipv6_dhcp_range). IPv6 addresses support STATIC and DHCP_RESERVED states only.
- **PTR Record Option (FEAT-007):** Added `ptr` field to `HostRecordRow` to control automatic PTR (reverse DNS) record creation when creating host records via CSV. Accepts `true`, `false`, or empty (default behavior).
- **Deferred Resolution Design:** Added comprehensive documentation for deferred resolution system architecture and implementation
- **--show-plan CLI Flag:** Added execution order preview to show dependency-resolved operation sequence before execution
- **Verbose Debug Logging:** Added multiple debug levels (--verbose, --debug) for enhanced troubleshooting and detailed execution tracing
- **--show-deps CLI Flag:** Added dependency graph visualization output in DOT format for Graphviz
- **Zone Nested Name Resolution:** Enhanced resolution for nested DNS zone names and hierarchical zone structures
- **Detailed Dry-Run Reports:** Improved dry-run output with detailed operation previews and expected changes
- **Improved Error Messages:** Enhanced error reporting with contextual information and actionable guidance
- **Dependency Graph Visualization:** Added visual representation of resource dependencies for debugging
- **CSV Injection Prevention:** Added security measures to prevent CSV injection attacks
- **IPv6 Interface Support:** Added support for IPv6 addresses in DHCP deployment role interfaces
- **Cache Coherency:** Implemented complete cache coherency system with proper invalidation for deleted resources
- **KeyedLock Concurrency:** Added granular locking system to prevent resolver state corruption in concurrent scenarios
- **ImportRunner Module:** Refactored import logic into reusable ImportRunner class for better modularity
- **Rollback Command:** Added dedicated rollback CLI command for undoing imports with proper validation
- **Execution Planner Module:** Separated execution planning logic into dedicated module for better organization
- **ACL (Access Control List) Support:** Added CSV import for DNS ACLs with bulk match element support:
  - `acl` object type for managing DNS access control lists
  - Support for up to 500+ IPs/CIDRs per ACL via comma-separated `match_elements` field
  - Full CRUD operations (create, update, delete)
  - Sample CSV: `samples/acl.csv`

### Performance
- **N+1 Query Fix in Validator:** Replaced sequential config lookups with `asyncio.gather` for parallel execution
- **Bulk API Filters:** Added `range:in()` filter syntax for batch CIDR existence checking
- **Dependency Graph O(n²) → O(n):** Optimized dependency detection using indexed lookups instead of linear scans

### Fixed
- **IPv6 Address Filter Parsing (BUG-005):** Fixed `FilterTokenError` when looking up IPv6 addresses in BAM. Changed filter to use double quotes for address values and removed `type:IPv6Address` constraint (which also contained parsing-problematic colons). The `get_ip6_address` method now correctly finds existing IPv6 addresses.
- **Generic Record Unsupported Types (BUG-006):** Removed DNSKEY from `VALID_RECORD_TYPES` in `GenericRecordRow` as it is not supported by the BAM API for GenericRecord type (validated against OpenAPI spec). Updated `samples/generic_record.csv` to remove unsupported record types.
- **Location Code Validation (BUG-007):** Updated `samples/location.csv` with valid ISO 3166-2 compliant location codes (US-NY, US-CA, GB-LND, JP-13).
- **Empty CSV Files:** Fixed handling of empty CSV files to succeed gracefully
- **Resolver Race Conditions:** Fixed concurrent access issues in resolver state management with granular KeyedLock implementation
- **Cache Coherency:** Fixed cache invalidation issues when resources are deleted, ensuring cache consistency
- **Test Failures:** Corrected 3 failing tests in runner, parser, and server_resolution modules
- **Error Context:** Improved error handling with full context and traceback capture during operation creation and execution
- **Interface Validation:** Added validation for numeric interface IDs in BAM client
- **Dependency Logic:** Extracted and refactored dependency logic to DependencyPlanner for better maintainability
- **Sample CSVs:** Updated `dns_deployment_role.csv` (and verified `dhcp_deployment_role.csv`) to match lab environment server names (`server-01`/`02`, `server1`/`2`).

### Improved
- **Performance:** Optimized resolver performance with granular locking instead of global locks
- **Code Organization:** Improved separation of concerns with dedicated modules for dependency planning and execution
- **Debugging Experience:** Enhanced debugging capabilities with detailed logging and visualization options
- **Error Reporting:** Improved error messages with contextual information for better troubleshooting
- **CLI Usability:** Added new CLI flags for better insight into import process and dependencies

### Code Quality Improvements
- **Unicode Validation (EDGE-008):** Added character validation for resource names to reject control characters and null bytes while allowing legitimate Unicode text (German, Japanese, emoji, accents). Prevents API issues with malformed names.
- **Named Constants (QUALITY-002):** Extracted magic numbers to named constants module (`constants.py`) covering cache TTL, pagination limits, retry configuration, checkpointing intervals, and throttling parameters.
- **Dependency Graph Optimization (QUALITY-005):** Optimized dependency graph with indexed data structures (`_nodes_by_type`, `_nodes_by_operation`, `_create_operations`) reducing lookup complexity from O(n²) to O(k) for large CSV files.

### Removed
- **Unused modules:** Removed `type_defs.py`, `models/resource_types.py`, and `utils/profiling.py` - infrastructure prepared but never integrated into the codebase
- **Unused exceptions:** Removed `OrphanDetectionScopeError`, `ConflictError`, and `CheckpointError` - defined but never raised

## [0.3.0] - 2025-12-08

### Added
- **Location Support:** Added hierarchical location management with `location` object type
- **Generic Record Support:** Added `generic_record` object type for custom DNS record types
- **Resource Location Associations:** Added `location_code` field for resource-location associations
- **Enhanced DHCP Options:** Improved DHCP option handling with validation and generation scripts
- **Phasing Barriers:** Added phasing barriers in CLI dependency graph building for better execution control

### Improved
- **Documentation Reorganization:** Moved all documentation to `docs/` directory for better organization
- **Self-Test Capabilities:** Enhanced self-test with more comprehensive validation
- **Error Handling:** Improved error messages and debugging capabilities
- **Performance:** Optimized dependency resolution and execution planning

## [0.2.0] - 2025-11-15

### Added
- **DNS Deployment Roles:** Server name resolution support for DNS deployment roles with automatic interface lookup
- **DHCP Deployment Options:** DHCPv4 client and service deployment options for comprehensive DHCP configuration
- **Network Auto-Discovery:** Implemented intelligent network discovery by IP address (`find_network_containing_address`)
- **Performance Optimizations:** Optimized network and block discovery to use server-side API filtering

### Fixed
- **External Host Records:** Added proper support for `ExternalHostsZone` to resolve 404 errors
- **DNS Dependencies:** Added record-to-record dependency detection for MX, Alias, and SRV records
- **Memory Scalability:** Resolved memory scalability issues and empty string handling
- **Duplicate Field Annotations:** Fixed duplicate `Field()` annotations in deployment role models

## [Unreleased]

### Security
- **CRITICAL: Delete Method Safety Bypass:** Specific delete methods (`delete_configuration`, `delete_dns_deployment_role`, `delete_location`) now route through `delete_entity_by_id` to enforce safety checks for protected resource types
- **Delete Helper Method:** Renamed public `delete()` helper to private `_delete()` to prevent accidental bypass of safety checks

### Added
- **DNS Deployment Roles:** Server name resolution support for DNS deployment roles with automatic interface lookup
- **DHCP Deployment Options:** DHCPv4 client and service deployment options for comprehensive DHCP configuration
- **Test CSV Documentation:** Complete documentation of valid test CSV files with cleanup of invalid examples
- **Sample Files:** New sample CSVs for DNS deployment roles, DHCP options, and server name resolution
- **Example Config:** Added `config.yaml.example` with placeholder credentials
- **View Deletion Safety:** Added `delete_view()` method with proper safety checks for dangerous operations

### Fixed
- **Pagination Infinite Loop:** Added `max_pages` safety limit (default 1000) and duplicate request detection to `get_all_pages()` to prevent infinite loops from malformed API responses
- **Rate Limit Retry-After:** Fixed rate limit handling to properly respect the server's `Retry-After` header value instead of using exponential backoff that ignores the header
- **CSV Sanitizer Memory:** Added streaming mode for large CSV files (>50MB) to prevent out-of-memory errors
- **Dependency Resolution Substring:** Fixed CIDR dependency matching to use strict segment comparison instead of loose substring matching, preventing false positives
- **Missing Credentials Validation:** `ImporterConfig.from_env()` now fails fast with a clear error message when `BAM_URL` is set but `BAM_USERNAME` or `BAM_PASSWORD` are missing
- **CSV Multi-line Fields:** Fixed CSV sanitizer to properly handle quoted fields with embedded newlines
- **Duplicate DHCP Method:** Renamed `create_ipv4_dhcp_range` to `create_ipv4_dhcp_range_simple` for the simple start/end IP version, preventing Python method shadowing
- **DHCP Server Scope:** Fixed DHCP deployment option methods to properly include non-default `serverScope` values in API payloads
- **Deferred Key Cleanup:** Deferred resolution keys (`_deferred_*`) are now removed from operation payloads after successful resolution
- **Credential Security:** Added `config.yaml` to `.gitignore` to prevent accidental credential commits
- **Location Root Support:** Fixed LocationRow to allow empty `parent_code` for root locations
- **Self-Test Import:** Fixed self_test.py to use `OperationFactory.create_from_row()` instead of removed function
- **Location Sample CSV:** Fixed `location.csv` sample to use correct field name `parent_code` and valid hierarchical codes

### Improved
- **Code Quality:** Enterprise-grade code quality and performance improvements across the codebase
- **Memory Scalability:** Resolved memory scalability issues and empty string handling
- **Error Handling:** Enhanced error handling and graceful degradation
- **Production Readiness:** Comprehensive fixes for production deployment scenarios
- **Documentation:** Professionalized all documentation, improved consistency and clarity
- **Type Annotations:** Added complete type annotations to all Pydantic validators
- **Exception Chaining:** Added proper exception chaining (`from e`) in deployment role handlers

### Documentation
- **Improved:** Added consistent command examples showing both `bluecat-import` and `python3 import.py` formats
- **Added:** Comprehensive prerequisites section to README.md and QUICKSTART.md
- **Enhanced:** CSV Schema Reference with complete column documentation
- **Updated:** Command consistency across all documentation files
- **Added:** Clear system requirements and operating system support information
- **Added:** Test CSV documentation with validated file listings
- **Enhanced:** CLAUDE.md with comprehensive improvements for AI assistants

### Fixed
- **Fixed:** Command examples mismatch between `python import.py` and actual installed `bluecat-import` command
- **Fixed:** Inconsistent configuration examples across documentation files
- **Fixed:** Missing prerequisite information in user guides
- **Fixed:** Memory scalability and resource leak issues
- **Fixed:** All critical production-readiness issues identified in testing
- **Cleanup:** Removed 14 invalid CSV test files that didn't pass validation
- **Fixed:** Duplicate `Field()` annotations in deployment role models
- **Fixed:** `validate_interfaces` now returns `None` instead of empty string for empty input

### Fixed (Recent)
- **External Host Records:** Added proper support for `ExternalHostsZone` to resolve 404 errors during creation of external host records.
- **DNS Dependencies:** Added record-to-record dependency detection for MX (exchange), Alias (linkedRecord), and SRV (target) records to prevent `InlinedResourceNotFound` errors.
- **Security:** Fixed API filter injection vulnerability in `BAMClient` by escaping single quotes in filter parameters.
- **CSV Encoding:** Fixed handling of CSV files with Byte Order Mark (BOM) by using `utf-8-sig` encoding, ensuring compatibility with Excel exports.
- **Deferred Execution:** Fixed in-place modification of operation payloads during deferred resolution in `Executor`, ensuring idempotency and retry safety using deep copies.
- **IPv6 Parsing:** Improved robustness of IPv6 interface string parsing in `BAMClient` to correctly handle server:interface formats containing IPv6 addresses.
- **Pagination:** Enhanced infinite loop detection in `get_all_pages` to detect larger cycles (A -> B -> A) and prevent infinite recursion.

- **IPv6 Import Fixes:** Resolved multiple issues preventing IPv6 resource import:
  - Removed strict type filtering (type:IPv6Block/IPv6Network) in BAMClient that caused 400 Bad Request errors.
  - Fixed IP6BlockHandler to resolve default parent block (2000::/3) within the target configuration instead of globally.
  - Corrected Resolver type mapping for "ip6_network" to use the correct BAM type string "IPv6Network".
  - Added missing dispatch logic for `ipv6_dhcp_range` in OperationFactory.
  - Added missing `alias="parent"` to `IPv6DHCPRangeRow.network_path` to correctly map CSV columns.


### Added (Recent)
- **Bulk Operations (Phase 2):** Implemented efficient bulk loading in `StateLoader` using BAM v2 filtering (`in` operator) to fetch multiple resources (addresses, networks, zones, records) in single API calls.
- **Cache Prefetching:** Added `prefetch_from_csv` capability and bulk resolution helpers to `Resolver` to warm caches before execution, significantly reducing API round-trips.
- **Save Rollbacks to Directory:** Rollback CSVs are now saved to a dedicated `rollbacks/` directory in the project root instead of the current working directory.

### Fixed (Recent)
- **Circular Import:** Renamed `src/importer/types.py` to `src/importer/type_defs.py` to avoid shadowing the standard library `types` module.
- **Self-Test Path Resolution:** Fixed CLI issue where `self-test` would duplicate paths (e.g., `samples/samples/file.csv`).
- **External Host Records:** Added proper support for `ExternalHostsZone` to resolve 404 errors during creation of external host records.

## [0.1.0] - 2024-12-02

### Added
- Initial release of BlueCat CSV Importer
- Production-grade CSV bulk import functionality
- Complete rollback capability with inverse CSV generation
- Dependency-aware execution with topological sorting
- Adaptive throttling for API rate limiting
- Comprehensive error handling and logging
- SQLite-based changelog and checkpoint system
- Rich CLI interface with progress bars
- JSON/HTML reporting capabilities
- Export functionality for networks, blocks, and DNS zones
- Complete documentation suite:
  - README.md - Complete feature documentation and API reference
  - QUICKSTART.md - 5-minute getting started guide
  - TUTORIAL.md - Comprehensive tutorial with real-world examples
  - ARCHITECTURE.md - Technical implementation details
  - EXPORT_GUIDE.md - Complete export workflow guide
  - samples/README.md - Example CSV files and usage guides

### Features
- **Core Import/Export**: Full CSV-based bulk operations
- **Idempotency**: Safe to run multiple times with same result
- **Rollback Support**: Automatic inverse CSV generation for undo operations
- **Resume Capability**: Checkpoint-based resume for interrupted imports
- **Validation Engine**: Pydantic v2 validation with strict mode support
- **Dependency Management**: Automatic parent-child relationship resolution
- **Performance**: Adaptive throttling and parallel execution
- **Observability**: Structured logging, metrics, and detailed reporting
- **Safety Features**: Dry-run mode, orphan detection, conflict resolution
- **Configuration**: YAML-based configuration with environment variable support

### Technology Stack
- Python 3.11+ with async/await
- Pydantic v2 for data validation
- httpx for async HTTP client operations
- Typer + Rich for CLI and terminal UI
- SQLite for persistence
- diskcache for resolver caching
- pytest for testing
- structlog for structured logging