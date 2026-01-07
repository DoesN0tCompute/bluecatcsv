# BlueCat CSV Importer

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Checked with mypy](https://img.shields.io/badge/mypy-checked-blue.svg)](https://mypy-lang.org/)
[![Test Coverage: 61%](https://img.shields.io/badge/coverage-61%25-yellow.svg)](https://pytest-cov.readthedocs.io/)

**Production-grade bulk import tool for BlueCat Address Manager (BAM) v0.3.0**

A robust, high-performance CLI tool for importing, exporting, and managing BlueCat Address Manager resources using CSV files. Designed for enterprise environments with intelligent dependency management, comprehensive safety checks, and rollback capabilities.

## Key Features

- **Bulk Operations**: Import thousands of resources efficiently with async I/O
- **Smart Dependency Management**: Automatic dependency detection and topological sorting
- **Safety First**:
  - Dry-run mode for simulation
  - Dangerous operation protection (configurations and views cannot be deleted via CSV)
  - Automatic rollback generation
- **High Performance**:
  - **Bulk Loading**: Efficiently fetch multiple resources in single API calls
  - **Cache Prefetching**: Smart pre-loading of dependencies to minimize API round-trips
  - **Adaptive Throttling**: Auto-tuning concurrency based on load
  - **Parallel Execution**: Optimized async task processing
  - **KeyedLock Concurrency**: Granular locking prevents state corruption
  - **Cache Coherency**: Complete cache invalidation system for consistency
- **Full IPv6 Support**: Complete IPv6 feature parity with IPv4
- **Location Management**: Hierarchical location support with resource associations
- **Generic DNS Records**: Support for custom DNS record types
- **Observability**: JSON/HTML reports, structured logging, metrics
- **Resumable Imports**: Checkpoint system for interrupted imports
- **Comprehensive Self-Test**: Validate connectivity and functionality

## Supported Resources

### IP Address Management

- **IPv4**: Blocks, Networks (with Auto-Discovery), Addresses, Address Groups, DHCP Ranges
- **IPv6**: Blocks, Networks, Addresses, DHCPv6 Ranges

### DNS Management

- Zones
- Host Records (A/AAAA)
- Alias Records (CNAME)
- MX Records
- TXT Records
- SRV Records
- External Host Records
- Generic Records (custom types: CAA, SSHFP, TLSA, etc.)

### DHCP Management

- IPv4/IPv6 DHCP Ranges
- DHCP Client/Service Deployment Options
- DHCP Deployment Roles (failover support)

### Infrastructure

- Hierarchical Locations with geographic coordinates
- Location associations for all resources

### Metadata & Organization

- **Tags & Tag Groups**: Organize and categorize resources with tags
- **User-Defined Fields (UDFs)**: Custom metadata fields for all resource types
- **User-Defined Links (UDLs)**: Custom relationships between resources
- **Access Rights**: User and group permission management for BAM resources
- **Access Control Lists (ACLs)**: DNS ACLs with bulk IP/CIDR management
- **MAC Pool Management**: MAC pools and addresses for DHCP control
- **Device Management**: Device types, subtypes, devices, and address associations

## Quick Start

### Prerequisites

- Python 3.11 or higher
- BlueCat Address Manager v9.3+ with API v2 enabled

### Installation

**Using Poetry (recommended):**

```bash
git clone https://github.com/DoesN0tCompute/bluecatcsv.git
cd bluecatcsv
poetry install
poetry shell
```

**Using pip:**

```bash
git clone https://github.com/DoesN0tCompute/bluecatcsv.git
cd bluecatcsv
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Production only (no pytest, black, etc.)
pip install -r requirements.txt

# Full install (production + dev)
pip install -r requirements-dev.txt
```

### Configuration

Set environment variables:

```bash
export BAM_URL="https://bam.example.com"
export BAM_USERNAME="api_user"
export BAM_PASSWORD="secure_password"
export BAM_VERIFY_SSL="true"  # Optional
```

Or create a `config.yaml`:

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

## Usage

### Basic Workflow

1. **Export** existing data (optional) or create a CSV file
2. **Validate** the CSV file
3. **Dry Run** to simulate changes
4. **Apply** the changes
5. **Review** the results and rollback if needed

### CLI Commands

```bash
# Fix CSV formatting issues
bluecat-import fix dirty.csv -o clean.csv

# Validate CSV
bluecat-import validate data.csv --strict

# Preview execution plan
bluecat-import apply data.csv --show-plan

# Preview dependency graph (DOT format for Graphviz)
bluecat-import apply data.csv --show-deps > deps.dot

# Dry run simulation
bluecat-import apply data.csv --dry-run

# Apply with verbose logging
bluecat-import apply data.csv --verbose

# Resume interrupted import
bluecat-import apply data.csv --resume

# Export resources
bluecat-import export --network 10.0.0.0/8 --config-name Default output.csv

# View import history
bluecat-import history

# Check import session status
bluecat-import status <session_id>

# Rollback changes
bluecat-import rollback rollbacks/<session_id>_rollback.csv

# Self-test connectivity
bluecat-import self-test --url https://bam.example.com --username user

# Show version information
bluecat-import version
```

## CSV Format

The CSV format uses standard column names (updated in v0.3.0):

```csv
row_id,object_type,action,config,cidr,name
1,ip4_block,create,Default,10.0.0.0/8,Corporate Network
2,ip4_network,create,Default,10.1.0.0/24,Servers
3,ip4_address,create,Default,10.1.0.10,web-server-01,,state=STATIC
```

**Key changes in v0.3.0:**

- `config_path` → `config`
- `parent_path` → `parent` (for IP hierarchy)

See [samples/](samples/) directory for complete examples.

## Architecture

```
src/importer/
├── bam/                # BAM API integration
├── core/               # Core pipeline logic
├── dependency/         # Dependency management
├── execution/          # Operation execution
├── models/             # Pydantic models
├── observability/      # Logging & reporting
├── persistence/        # State management
├── rollback/           # Rollback generation
├── validation/         # Safety checks
├── utils/              # Utilities
├── cli.py              # CLI interface
├── config.py           # Configuration
└── self_test.py        # Self-test suite
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/importer --cov-report=html

# Code quality checks
black src/ tests/
ruff check src/ tests/
mypy src/
```

Current test coverage: **61%**

## Documentation

- [**Quick Start**](docs/QUICKSTART.md): Get up and running in minutes.
- [**Tutorial**](docs/TUTORIAL.md): Step-by-step guide for common workflows.
- [**Export Guide**](docs/EXPORT_GUIDE.md): Deep dive into data export and filtering.
- [**Validation Guide**](docs/VALIDATION_GUIDE.md): Learn about offline vs. online bulk validation.
- [**Performance Tuning**](docs/PERFORMANCE.md): Optimize for large datasets.
- [**Operations Guide**](docs/OPERATIONS_GUIDE.md): Advanced usage and deployment.
- [**Architecture**](docs/ARCHITECTURE.md): System design and components.
- [**Self-Test Guide**](docs/SELF_TEST_GUIDE.md) - Self-test usage
- [**Change Log**](docs/CHANGELOG.md) - Version history

## Safety Features

- **Dry-run mode** - Simulate without applying changes
- **Three-tier deletion protection**:
  1. NEVER DELETE: Configurations, Views (cannot be bypassed)
  2. HIGH RISK: Blocks, Networks, Zones (requires `--allow-dangerous-operations`)
  3. SAFE: All other resources
- **Automatic rollback generation** for every import
- **Comprehensive validation** before execution
- **Checkpoint system** for resumable imports

## Contributing

We welcome contributions! See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines.

### Development Setup

```bash
# Install development dependencies
poetry install --with dev

# Run pre-commit checks
pre-commit run --all-files
```

## License

Please contact the project maintainers for licensing information.

## Support

- Check the [Operations Guide - Troubleshooting](docs/OPERATIONS_GUIDE.md#part-2-troubleshooting)
- Review [FAQ](docs/README.md#frequently-asked-questions)
- Create an issue on GitHub
- Contact your BlueCat support representative

---

**Version**: 0.3.0
**Python**: 3.11+
**BAM API**: v2 (REST)
**BAM Version**: 9.3+ (recommended 9.6+)
