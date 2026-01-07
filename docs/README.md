# BlueCat CSV Importer

**Production-grade bulk import tool for BlueCat Address Manager (BAM).**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Checked with mypy](https://http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This tool provides a robust, high-performance way to import, export, and manage BlueCat Address Manager resources using CSV files. It is designed for enterprise environments, handling large datasets with intelligent dependency management, safety checks, and rollback capabilities.

## Table of Contents

- [Key Features](#key-features)
- [Supported Resources](#supported-resources)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
- [Usage Guide](#usage-guide)
  - [Basic Workflow](#basic-workflow)
  - [CLI Commands](#cli-commands)
- [CSV Format](#csv-format)
- [Developer Guide](#developer-guide)
- [Documentation](#documentation)

## Key Features

- **Bulk Operations**: Import thousands of Blocks, Networks, IP Addresses, and DNS Records efficiently.
- **Smart Dependency Management**: Automatically detects and orders dependencies (e.g., creating a Block before its Networks, Zones before Records).
- **Safety First**:
    - **Dry Run Mode**: Simulate changes without applying them.
    - **Dangerous Operation Protection**: Prevents accidental deletion of critical resources. **Configurations and Views cannot be deleted via CSV import** (permanently blocked for safety). Blocks, Networks, and Zones require `--allow-dangerous-operations`.
    - **Rollback Generation**: Automatically generates a rollback CSV in `rollbacks/` for every import session.
- **High Performance**:
    - **Bulk Loading**: Efficiently fetch multiple resources in single API calls.
    - **Cache Prefetching**: Smart pre-loading of dependencies to minimize API round-trips.
    - **Async I/O**: Leveraging `asyncio` and `httpx` for non-blocking API calls.
    - **Adaptive Throttling**: Dynamically adjusts concurrency based on API latency and error rates.
    - **Caching**: Intelligent caching of resource resolutions to minimize API load.
- **Observability**: Detailed JSON/HTML reports, structured logging, and metrics.
- **Resumable Imports**: Checkpoint system allows resuming interrupted imports from where they left off.
- **Self-Test Capabilities**: Comprehensive self-test suite to validate connectivity and functionality against a live BAM instance.
- **Location Management**: Hierarchical location support with resource-location associations.

## Supported Resources

The importer supports a wide range of BAM resources:

- **IP Space**:
  - IPv4 Blocks (`ip4_block`)
  - IPv4 Networks (`ip4_network`) - Supports Auto-Discovery
  - IPv4 Addresses (`ip4_address`)
  - IPv6 Blocks (`ip6_block`)
  - IPv6 Networks (`ip6_network`)
  - IPv6 Addresses (`ip6_address`)
- **DNS**:
  - DNS Zones (`dns_zone`)
  - Host Records (`host_record`)
  - Alias (CNAME) Records (`alias_record`)
  - MX Records (`mx_record`)
  - TXT Records (`txt_record`)
  - SRV Records (`srv_record`)
  - External Host Records (`external_host_record`)
  - Generic Records (`generic_record`) - Custom DNS record types
- **DHCP**:
  - DHCP Ranges (`ipv4_dhcp_range`, `ipv6_dhcp_range`)
  - Deployment Roles (`dhcp_deployment_role`, `dns_deployment_role`)
  - DHCP Options (`dhcpv4_client_deployment_option`, `dhcpv4_service_deployment_option`)
- **Infrastructure**:
  - Locations (`location`) - Hierarchical location management
- **Metadata & Organization**:
  - Tag Groups (`tag_group`) - Organize tags into groups
  - Tags (`tag`) - Tag resources for organization
  - Resource Tags (`resource_tag`) - Associate tags with resources
  - UDF Definitions (`udf_definition`) - Define custom metadata fields
  - UDL Definitions (`udl_definition`) - Define custom resource relationships
  - User-Defined Links (`user_defined_link`) - Create actual links between resources
- **Device Management**:
  - Device Types (`device_type`) - Device categories (Cisco, Fortinet, etc.)
  - Device Subtypes (`device_subtype`) - Device models within types
  - Devices (`device`) - Network devices with type/subtype assignments
  - Device Addresses (`device_address`) - Link IP addresses to devices
- **MAC Pool Management**:
  - MAC Pools (`mac_pool`) - Create MAC address pools for DHCP control
  - MAC Addresses (`mac_address`) - Register MAC addresses globally or with pools

### DHCP Deployment Roles (Failover)

The importer inherently supports DHCP Failover (primary/secondary) configurations. When defining a `dhcp_deployment_role`, provide multiple interfaces separated by pipe (`|`).

- The **first** interface becomes the **Primary**.
- All **subsequent** interfaces become **Secondary**.

**Example:**
```csv
row_id,object_type,action,network_path,name,interfaces
1,dhcp_deployment_role,create,"10.0.0.0/24",Master-Role,"server1:eth0|server2:eth0"
```
In this example:
- `server1:eth0` -> **PRIMARY**
- `server2:eth0` -> **SECONDARY**

## Project Structure

The project is organized as follows:

```
src/importer/
├── bam/                # BAM API integration (client, endpoints, response models)
├── core/               # Core pipeline logic (parser, resolver, diff engine, state loader)
├── dependency/         # Dependency management (graph, planner)
├── execution/          # Operation execution (executor, handlers, planner, runner, throttle)
├── models/             # Pydantic models (csv_row, payloads, operations, state, results)
├── observability/      # Logging & reporting (logger, metrics, reporter)
├── persistence/        # State persistence (changelog, checkpoint)
├── rollback/           # Rollback generation
├── validation/         # Safety checks (safety)
├── utils/              # Utilities (exceptions, locking)
├── cli.py              # Typer CLI entry point
├── config.py           # YAML configuration management
└── self_test.py        # Comprehensive self-test suite
```

## Quick Start

### Prerequisites

- Python 3.11 or higher
- Access to a BlueCat Address Manager (BAM) instance (v9.3+ recommended for API v2 support)

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-org/bluecat-csv-importer.git
    cd bluecat-csv-importer
    ```

2.  **Install dependencies:**

    **Using Poetry (Recommended):**
    ```bash
    # Full install (production + dev)
    poetry install
    poetry shell

    # Production only (no pytest, black, etc.)
    poetry install --without dev
    ```

    **Using pip:**
    ```bash
    # Production only (no pytest, black, etc.)
    pip install -r requirements.txt

    # Full install (production + dev)
    pip install -r requirements-dev.txt
    ```

### Configuration

You can configure the importer using environment variables or a YAML configuration file.

**Environment Variables:**
```bash
export BAM_URL="https://bam.example.com"
export BAM_USERNAME="api_user"
export BAM_PASSWORD="secure_password"
# Optional
export BAM_API_VERSION="v2"
export BAM_VERIFY_SSL="true"
```

**YAML Configuration (`config.yaml`):**
```yaml
bam:
  base_url: "https://bam.example.com"
  username: "api_user"
  password: "secure_password"
  verify_ssl: true

policy:
  safe_mode: true
  max_concurrent_operations: 20
  failure_policy: "fail_group"
```

## Usage Guide

The tool exposes a CLI command `bluecat-import` (or `python import.py`).

### Basic Workflow

1.  **Export** existing data (optional) or create a CSV file.
2.  **Validate** the CSV file to check for errors.
3.  **Dry Run** to simulate the import and verify the plan.
4.  **Apply** the changes to BAM.
5.  Check **Status** or **Report** for results.

### CLI Commands

#### 1. Validate (`validate`)
Check your CSV for syntax errors, schema violations, and logical issues.
```bash
bluecat-import validate data/networks.csv --strict
```

#### 2. Fix (`fix`)
Automatically fix common CSV formatting issues like whitespace.
```bash
bluecat-import fix data/dirty.csv -o data/clean.csv
```

#### 3. Apply (`apply`)
Execute the import. Use `--dry-run` to simulate.
```bash
# Simulation
bluecat-import apply data/networks.csv --dry-run

# Preview execution order with dependency resolution
bluecat-import apply data/networks.csv --show-plan

# Generate dependency graph visualization (requires Graphviz)
bluecat-import apply data/networks.csv --show-deps > deps.dot

# Execution with enhanced logging
bluecat-import apply data/networks.csv --verbose  # Detailed output
bluecat-import apply data/networks.csv --debug    # Debug-level tracing

# Execution with rollback generation (default)
bluecat-import apply data/networks.csv

# Resume a failed session
bluecat-import apply data/networks.csv --resume
```

#### 4. Export (`export`)
Export resources to a CSV file for editing and re-importing.
```bash
# Export a network and its children
bluecat-import export --network 10.0.0.0/8 --config-name Default output.csv

# Export a DNS zone
bluecat-import export --zone example.com --view-id 12345 zone.csv
```

#### 5. Status & History
Monitor progress and review past imports.
```bash
# Check status of a specific session
bluecat-import status <session_id>

# View history of recent imports
bluecat-import history
```

#### 6. Rollback
Undo changes from a previous session using the generated rollback CSV.
```bash
bluecat-import rollback rollbacks/<session_id>_rollback.csv
```

#### 7. Self-Test
Verify connectivity and permissions.
```bash
bluecat-import self-test --url https://bam.example.com --username user
```

#### 8. Version
Show version and feature information.
```bash
bluecat-import version
```

## CSV Format

The CSV format requires a header row. Common columns include:
- `row_id` (Required): Unique identifier for the row (can be any string).
- `object_type` (Required): Type of resource (e.g., `ip4_network`).
- `action` (Required): `create`, `update`, or `delete`.
- `config`: Configuration name (e.g., `Default`).
- `cidr`, `address`, `name`: Resource-specific fields.
- `parent` (Optional): Explicit parent path. If omitted, parent is auto-discovered.
- `properties`: JSON string or extra columns for properties.
- `udf_*`: User Defined Fields (e.g., `udf_Location`).

**Example:**
```csv
row_id,object_type,action,config,cidr,name
1,ip4_block,create,Default,10.0.0.0/8,Private
2,ip4_network,create,Default,10.1.0.0/24,Servers
```

**Location Example:**
```csv
row_id,object_type,action,parent_location_code,code,name,description,latitude,longitude
1,location,create,US NYC,US NYC HQ,New York Headquarters,Main office,40.7128,-74.0060
2,location,create,US NYC HQ,US NYC HQ F1,Floor 1,First floor,40.7128,-74.0060
```

**GenericRecord Example:**
```csv
row_id,object_type,action,zone_path,name,type,record_data
1,generic_record,create,Default/example.com,test,CAA,0,issue "letsencrypt.org"
```

See `samples/` directory for detailed examples.

## Developer Guide

### Adding Support for New Resources

To add support for a new BAM resource type:

1.  **Define CSV Model**: Add a Pydantic model in `src/importer/models/csv_row.py`.
2.  **Add Handler**: Create a handler class in `src/importer/execution/handlers.py` implementing the `OperationHandler` protocol.
3.  **Register Handler**: Add the new handler to `HANDLER_REGISTRY` in `src/importer/execution/handlers.py`.
4.  **Update API Client**: Ensure `BAMClient` has methods to fetch/create/update the resource.

### Running Tests
```bash
pytest tests/
```

### Code Style
This project follows strictly enforced code style guidelines:
- **Formatting**: `black`
- **Linting**: `ruff`
- **Type Checking**: `mypy`

## Documentation

### User Guides
- **[QUICKSTART.md](QUICKSTART.md)**: Get started in 5 minutes
- **[TUTORIAL.md](TUTORIAL.md)**: Comprehensive step-by-step tutorial
- **[CONFIGURATION.md](CONFIGURATION.md)**: Complete configuration reference
- **[EXPORT_GUIDE.md](EXPORT_GUIDE.md)**: Guide to exporting resources from BAM
- **[OPERATIONS_GUIDE.md](OPERATIONS_GUIDE.md)**: Best practices and troubleshooting

### Developer Documentation
- **[ARCHITECTURE.md](ARCHITECTURE.md)**: System design and architecture
- **[API_REFERENCE.md](API_REFERENCE.md)**: Complete Python API reference
- **[CLI_REFERENCE.md](CLI_REFERENCE.md)**: Detailed command-line reference
- **[MODULE_GUIDE.md](MODULE_GUIDE.md)**: Module-by-module documentation
- **[CONTRIBUTING.md](CONTRIBUTING.md)**: Contributing guidelines
- **[SELF_TEST_GUIDE.md](SELF_TEST_GUIDE.md)**: Self-test suite documentation

### Additional Resources
- **[CHANGELOG.md](CHANGELOG.md)**: Version history and release notes
- **[VALIDATION_GUIDE.md](VALIDATION_GUIDE.md)**: CSV validation guide
- **[PERFORMANCE.md](PERFORMANCE.md)**: Performance tuning guide

## Frequently Asked Questions (FAQ)

### General Questions

**Q: What versions of BlueCat Address Manager are supported?**
A: The importer supports BAM v9.3+ with REST API v2. Earlier versions may work but are not officially supported.

**Q: Can I use the importer with IPv6?**
A: Yes! Full IPv6 support was added in v0.3.0 with feature parity to IPv4, including blocks, networks, addresses, and DHCPv6 ranges.

**Q: Is there a GUI interface?**
A: No, the importer is command-line only, designed for automation and scripting. However, it provides rich HTML reports for visual inspection.

### Usage Questions

**Q: How do I import thousands of resources efficiently?**
A: See the [Operations Guide - Performance Optimization](OPERATIONS_GUIDE.md#part-3-performance-optimization) for optimization strategies:
- Increase `max_concurrent_operations` gradually
- Enable adaptive throttling
- Split large files into logical chunks
- Use checkpointing for resumable imports

**Q: Can I update existing resources?**
A: Yes. Use `action: "update"` in your CSV with the resource's name or ID. The importer will find and update the existing resource.

**Q: How do I delete resources?**
A: Use `action: "delete"` with the resource's identifying information. 

> **Important Safety Restrictions:**
> - **Configurations and Views**: Cannot be deleted via CSV import. This is permanently blocked for safety. Manage these directly in BAM.
> - **Blocks, Networks, Zones**: Require `--allow-dangerous-operations` flag or `allow_dangerous_operations: true` in config.
> - **Other resources**: Can be deleted normally.

**Q: What happens if an import fails?**
A: The importer maintains a changelog of all successful operations. You can:
- Resume from the last checkpoint with `--resume`
- Rollback all changes using the generated rollback CSV
- Check the status with `bluecat-import status <session-id>`

### CSV Format Questions

**Q: Can I use my own column names?**
A: Required columns must use the standard names (row_id, object_type, action, etc.). Additional columns can use any names and will be mapped to properties or UDFs.

**Q: How do I handle special characters in CSV fields?**
A: Quote the field and escape quotes as per CSV standard:
```csv
"quoted field with ""inner quotes"""
```

**Q: Can I import multiple resource types in one CSV?**
A: Yes, you can mix resource types. The importer will automatically resolve dependencies and process in the correct order.

### Performance Questions

**Q: How long does an import take?**
A: It depends on:
- Number of resources (rule of thumb: ~10-50 operations/second)
- Network latency to BAM server
- Complexity of dependencies
- Server load

For 10,000 simple resources: expect 5-20 minutes with optimal settings.

**Q: Why is my import slow?**
A: Common causes:
- Low `max_concurrent_operations` setting
- High network latency
- Complex dependency chains
- BAM server under load
- API rate limiting

See the [Operations Guide - Troubleshooting](OPERATIONS_GUIDE.md#part-2-troubleshooting) for common issues and solutions.

### Security Questions

**Q: How are credentials stored?**
A: Credentials can be provided via:
- Environment variables (recommended)
- Configuration file (ensure proper file permissions)
- Secret management systems in production

**Q: Is it safe to run on production?**
A: Yes, with proper precautions:
- Always use `--dry-run` first
- Enable `safe_mode` (default)
- Test with non-critical resources
- Have rollback procedures ready
- Review changes before applying

### Error Questions

**Q: What does "deferred resolution" mean?**
A: Some resources couldn't be created because their dependencies weren't found. The importer will:
- Mark them as deferred
- Continue with other operations
- Allow retry after dependencies are resolved

**Q: Why am I getting API rate limit errors?**
A: The importer is hitting BlueCat's rate limits. Solutions:
- Reduce `max_concurrent_operations`
- Enable adaptive throttling
- Contact BlueCat admin about increasing limits

Q: What does "circular dependency" mean?**
A: Two or more resources depend on each other. For example:
- Network A requires Zone B
- Zone B requires Network A

Solution: Restructure your CSV to remove the circular dependency.

### Advanced Questions

**Q: Can I extend the importer for custom resource types?**
A: Yes. See the Developer Guide in README.md for adding new resource types and handlers.

**Q: How does the importer handle conflicts?**
A: Based on your `conflict_resolution` setting:
- `error`: Fail on conflicts
- `update`: Update existing resources
- `skip`: Skip conflicting resources

**Q: Can I monitor imports in real-time?**
A: Yes:
- Use `bluecat-import status <session-id>` for progress
- Enable metrics endpoint for Prometheus/Grafana
- Check logs in real-time with `tail -f logs/importer.log`

### Troubleshooting

**Q: My import failed. Where do I start?**
A: Follow these steps:
1. Check the error message carefully
2. Review the log file: `logs/importer.log`
3. Run with `--verbose` for more detail
4. Check the TROUBLESHOOTING.md guide
5. Contact support with diagnostic bundle

**Q: How do I generate a diagnostic bundle?**
A: Run:
```bash
bluecat-import self-test --full-diagnostics --output bundle.tar.gz
```

This includes logs, configuration, and system information for support.

---

Need more help? Check out our [complete documentation](docs/) or create an issue on GitHub.
