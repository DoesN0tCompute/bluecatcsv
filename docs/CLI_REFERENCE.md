# CLI Reference Guide

**Last Updated:** 2025-12-14 | **Version:** 0.3.0

This document provides a comprehensive reference for all command-line interface (CLI) commands and options.

## Installation

```bash
# Using Poetry
poetry install && poetry shell

# Using pip
pip install -r requirements.txt

# Run directly
python3 import.py --help
# or
bluecat-import --help
```

## Global Options

These options can be used with any command:

| Option | Short | Description |
|--------|-------|-------------|
| `--config FILE` | `-c` | Path to configuration YAML file |
| `--help` | `-h` | Show help message |
| `--version` | | Show version information |
| `--show-config` | | Display active configuration |

## Commands

### `apply`

Execute CSV import operations.

#### Syntax
```bash
bluecat-import apply [OPTIONS] CSV_FILE
```

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--dry-run` | | flag | False | Simulate without applying changes |
| `--resume` | | flag | False | Resume from last checkpoint |
| `--allow-dangerous-operations` | | flag | False | Allow deletion of blocks/networks/zones |
| `--show-plan` | | flag | False | Show execution order after dependency resolution |
| `--show-deps FILE` | | path | None | Export dependency graph to DOT file |
| `--verbose` | `-v` | flag | False | Enable detailed output |
| `--debug` | `-d` | flag | False | Enable debug-level tracing |

#### Examples

**Basic Import**
```bash
bluecat-import apply data.csv
```

**Dry Run with Preview**
```bash
bluecat-import apply data.csv --dry-run --show-plan
```

**Debug Mode with Dependency Graph**
```bash
bluecat-import apply data.csv --debug --show-deps deps.dot
```

**Resume Interrupted Import**
```bash
bluecat-import apply data.csv --resume --verbose
```

**High-Performance Import**
```bash
BAM_MAX_CONCURRENT=100 bluecat-import apply large_file.csv
```

#### Output

The command provides:
- Real-time progress bars
- Success/failure summary
- Rollback CSV location
- Performance statistics

### `validate`

Validate CSV file without executing.

#### Syntax
```bash
bluecat-import validate [OPTIONS] CSV_FILE
```

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--strict` | `-s` | flag | False | Fail on first error |

#### Examples

**Standard Validation**
```bash
bluecat-import validate data.csv
```

**Strict Mode (CI)**
```bash
bluecat-import validate data.csv --strict
```

#### Validation Checks

- CSV format and encoding
- Required columns presence
- Data type validation
- CIDR/IP address formats
- Required field combinations
- Duplicate row IDs

#### Exit Codes

- `0`: Validation successful
- `1`: Validation failed

### `export`

Export BAM resources to CSV.

#### Syntax
```bash
bluecat-import export [OPTIONS] OUTPUT_FILE
```

#### Options

| Option | Type | Description |
|--------|------|-------------|
| `--config-name TEXT` | Configuration name filter |
| `--network CIDR` | Network CIDR to export |
| `--zone TEXT` | DNS zone name to export |
| `--view-id INTEGER` | DNS view ID filter |
| `--view-name TEXT` | DNS view name filter |

#### Examples

**Export Entire Configuration**
```bash
bluecat-import export --config-name Default full_export.csv
```

**Export Network and Subnets**
```bash
bluecat-import export --network 10.0.0.0/8 network.csv
```

**Export DNS Zone**
```bash
bluecat-import export --zone example.com --view-name Internal zone.csv
```

**Export with Specific View ID**
```bash
bluecat-import export --zone corp.local --view-id 12345 dns.csv
```

#### Export Features

- Preserves hierarchical relationships
- Includes all properties and UDFs
- Ready for re-import with minimal changes
- Includes deployment role information

### `fix`

Clean and sanitize CSV files.

#### Syntax
```bash
bluecat-import fix [OPTIONS] INPUT_FILE
```

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--output FILE` | `-o` | path | None | Output file (default: overwrite) |
| `--yes` | `-y` | flag | False | Automatically accept changes |

#### Cleaning Operations

1. **Whitespace Management**:
   - Strip leading/trailing whitespace from all fields
   - Normalize internal whitespace
   - Handle Windows/Unix line endings

2. **Header Standardization**:
   - Normalize column names
   - Remove duplicate columns
   - Ensure required columns present

3. **Data Normalization**:
   - Empty string → None for optional fields
   - Standardize boolean representations
   - Fix common formatting issues

#### Examples

**Interactive Cleaning**
```bash
bluecat-import fix dirty.csv
# Shows diff, prompts for confirmation
```

**Automatic Cleaning**
```bash
bluecat-import fix dirty.csv -o clean.csv --yes
```

### `rollback`

Undo changes from a previous import.

#### Syntax
```bash
bluecat-import rollback [OPTIONS] ROLLBACK_FILE
```

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--dry-run` | | flag | False | Simulate rollback |
| `--confirm` | | flag | False | Skip confirmation prompt |

#### Examples

**Standard Rollback**
```bash
bluecat-import rollback rollbacks/20241214_abc123_rollback.csv
```

**Preview Rollback**
```bash
bluecat-import rollback rollbacks/20241214_abc123_rollback.csv --dry-run
```

#### Safety Features

- Validates rollback file integrity
- Checks for conflicting changes
- Creates backup before rollback
- Requires confirmation unless `--confirm` used

### `status`

Check status of an import session.

#### Syntax
```bash
bluecat-import status SESSION_ID
```

#### Examples

```bash
bluecat-import status 20241214_abc123
```

#### Status Information

- Session start time
- Operations completed/total
- Success/failure counts
- Last checkpoint
- Current phase
- Error summary

### `history`

View history of recent imports.

#### Syntax
```bash
bluecat-import history [OPTIONS]
```

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--limit INTEGER` | `-n` | int | 10 | Number of sessions to show |
| `--format TEXT` | `-f` | text | table | Output format (table/json) |
| `--all` | `-a` | flag | False | Show all sessions |

#### Examples

**Recent Sessions**
```bash
bluecat-import history
```

**Detailed History**
```bash
bluecat-import history --limit 50 --format json
```

### `self-test`

Run comprehensive self-test suite.

#### Syntax
```bash
bluecat-import self-test [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|---------|---------|-------------|
| `--url TEXT` | None | BAM server URL (overrides config) |
| `--username TEXT` | None | BAM username (overrides config) |
| `--password TEXT` | None | BAM password (overrides config) |
| `--test-mode TEXT` | basic | Test level (basic/standard/comprehensive) |
| `--output FILE` | None | Save results to file |
| `--full-diagnostics` | False | Include system diagnostics |

#### Test Categories

1. **Connection Tests**:
   - API connectivity
   - Authentication
   - SSL verification

2. **Permission Tests**:
   - Read access to configurations
   - Create/update/delete permissions
   - DNS zone management

3. **Performance Tests**:
   - API response times
   - Concurrent request handling
   - Rate limit detection

4. **Feature Tests**:
   - Resource creation
   - Dependency resolution
   - Rollback generation

#### Examples

**Quick Health Check**
```bash
bluecat-import self-test
```

**Full Diagnostic**
```bash
bluecat-import self-test --test-mode comprehensive --full-diagnostics
```

**Test Different Server**
```bash
bluecat-import self-test --url https://bam-test.example.com --username testuser
```

### `version`

Display version and build information.

#### Syntax
```bash
bluecat-import version [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|---------|---------|-------------|
| `--show-config` | flag | False | Display active configuration |
| `--show-system` | flag | False | Display system information |

#### Examples

```bash
bluecat-import version
# Version: 0.3.0
# Build: 2024-12-14T10:30:00Z
# Python: 3.11.7

bluecat-import version --show-config
# Shows full active configuration

bluecat-import version --show-system
# Shows system info, dependencies
```

## Environment Variables

All configuration can be set via environment variables with `BAM_` prefix:

### Connection

```bash
export BAM_URL="https://bam.example.com"
export BAM_USERNAME="api_user"
export BAM_PASSWORD="secure_password"
export BAM_API_VERSION="v2"
export BAM_VERIFY_SSL="true"
export BAM_CA_CERT_PATH="/path/to/ca.pem"
```

### Performance

```bash
export BAM_MAX_CONCURRENT="50"
export BAM_CACHE_SIZE="20000"
export BAM_BATCH_SIZE="500"
export BAM_MEMORY_LIMIT="4GB"
```

### Logging

```bash
export BAM_LOG_LEVEL="DEBUG"
export BAM_LOG_FILE="debug.log"
export BAM_LOG_FORMAT="json"
export BAM_JSON_LOGS="true"
```

### Policy

```bash
export BAM_SAFE_MODE="true"
export BAM_FAILURE_POLICY="continue"
export BAM_ALLOW_DANGEROUS="false"
export BAM_CONFLICT_RESOLUTION="update"
```

### Proxy

```bash
export HTTP_PROXY="http://proxy.company.com:8080"
export HTTPS_PROXY="https://proxy.company.com:8080"
export NO_PROXY="localhost,127.0.0.1"
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Validation error |
| 3 | Authentication error |
| 4 | Permission error |
| 5 | Network error |
| 6 | Configuration error |
| 130 | Interrupted (Ctrl+C) |

## Output Formats

### Progress Bars

During execution, you'll see:

```
Import Progress: ████████████████████ 75% (750/1000)
  Networks: ████████████████░░░ 40% (40/100)
  Addresses: ████████████████████ 80% (640/800)
  DNS Records: ████████████░░░░░░░░ 30% (30/100)
```

### Verbose Output

With `--verbose` flag:

```
[10:30:15] INFO: Resolving dependencies...
[10:30:15] INFO:   - Resolved Block 10.0.0.0/8 → ID 1001
[10:30:15] INFO:   - Resolved Network 10.1.0.0/24 → ID 2001
[10:30:16] INFO: Phase 1/3: Creating parent resources...
[10:30:16] INFO:   ✓ Created Block 10.0.0.0/8 (ID: 1001)
[10:30:17] INFO:   ✓ Created Network 10.1.0.0/24 (ID: 2001)
```

### Debug Output

With `--debug` flag:

```
[10:30:15] DEBUG: HTTP POST /api/v2/blocks
[10:30:15] DEBUG: Request payload: {"name": "Production", "cidr": "10.0.0.0/8"}
[10:30:15] DEBUG: Response: 201 Created (112ms)
[10:30:15] DEBUG: Response body: {"id": 1001, "_links": {...}}
[10:30:15] DEBUG: Added to cache: block://Default/10.0.0.0/8 → 1001
```

### JSON Logging

For automation:

```bash
export JSON_LOGS=true
bluecat-import apply data.csv 2>&1 | jq .
```

Output:
```json
{
  "timestamp": "2024-12-14T10:30:15.123Z",
  "level": "info",
  "message": "Created resource",
  "resource_type": "network",
  "resource_id": 2001,
  "duration_ms": 112
}
```

## Configuration File

Create `config.yaml` for persistent settings:

```yaml
bam:
  base_url: "https://bam.example.com"
  username: "${BAM_USERNAME}"
  password: "${BAM_PASSWORD}"
  verify_ssl: true
  timeout: 30.0

policy:
  safe_mode: true
  max_concurrent_operations: 20
  failure_policy: "continue"
  allow_dangerous_operations: false

performance:
  cache_size: 10000
  batch_size: 100
  checkpoint_interval: 1000

throttling:
  enabled: true
  target_latency: 200

observability:
  logging:
    level: "INFO"
    format: "text"
    file: "logs/importer.log"
  metrics:
    enabled: true
    port: 8080
```

## Usage Patterns

### CI/CD Integration

```bash
#!/bin/bash
# ci-validate.sh

set -e

# Validate all CSV files
for file in csv/*.csv; do
    echo "Validating $file..."
    bluecat-import validate "$file" --strict
done

# Dry run import
bluecat-import apply csv/import.csv --dry-run

echo "All validations passed!"
```

### Automation with Python

```python
#!/usr/bin/env python3
import subprocess
import sys
import json

def run_import(csv_file):
    """Run import and return results."""
    cmd = [
        "bluecat-import",
        "apply",
        str(csv_file),
        "--format", "json"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Import failed: {result.stderr}")
        sys.exit(1)

    return json.loads(result.stdout)

# Usage
results = run_import("data.csv")
print(f"Success: {results['success_count']}/{results['total_count']}")
```

### Batch Processing

```bash
#!/bin/bash
# batch-import.sh

for csv in data/*.csv; do
    echo "Processing $csv..."

    # Validate first
    if ! bluecat-import validate "$csv" --strict; then
        echo "Validation failed for $csv"
        continue
    fi

    # Import with resume capability
    bluecat-import apply "$csv" || {
        echo "Import failed, will resume later..."
        echo "$csv" >> failed_imports.txt
    }
done
```

### Monitoring Integration

```bash
#!/bin/bash
# monitor.sh

while true; do
    # Check active imports
    bluecat-import history --limit 1 --format json > current.json

    # Extract metrics
    ops_per_sec=$(jq '.operations_per_second' current.json)
    success_rate=$(jq '.success_rate' current.json)

    # Send to monitoring system
    curl -X POST http://monitoring/api/metrics \
        -d "metric=import.ops_per_sec&value=$ops_per_sec"
    curl -X POST http://monitoring/api/metrics \
        -d "metric=import.success_rate&value=$success_rate"

    sleep 60
done
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**:
   ```bash
   # Test credentials
   bluecat-import self-test --url $BAM_URL --username $BAM_USERNAME
   ```

2. **SSL Certificate Errors**:
   ```bash
   # Disable SSL verification (testing only)
   export BAM_VERIFY_SSL="false"
   ```

3. **Permission Errors**:
   ```bash
   # Run with debug to see exact API calls
   bluecat-import apply data.csv --debug
   ```

4. **Memory Issues**:
   ```bash
   # Reduce batch size
   export BAM_BATCH_SIZE="10"
   export BAM_MAX_CONCURRENT="5"
   ```

### Debug Workflow

1. Enable debug logging:
   ```bash
   bluecat-import apply data.csv --debug > debug.log 2>&1
   ```

2. Check dependencies:
   ```bash
   bluecat-import apply data.csv --show-deps deps.dot
   dot -Tpng deps.dot -o deps.png
   ```

3. Validate data:
   ```bash
   bluecat-import validate data.csv --strict
   ```

4. Test with single row:
   ```bash
   head -n 2 data.csv > single.csv
   bluecat-import apply single.csv --verbose
   ```

This CLI reference provides comprehensive documentation for all commands, options, and usage patterns.