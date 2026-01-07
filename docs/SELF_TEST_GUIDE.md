# BlueCat CSV Self-Test Guide

**Last Updated:** 2025-12-08 | **Version:** 0.4.0

## Overview

The BlueCat CSV Importer includes a comprehensive self-test functionality that validates all features against a live BlueCat Address Manager instance. The self-test creates an **isolated temporary configuration and view** for testing, ensuring complete separation from production data.

Key features:
- **Isolated Test Environment**: Creates a dedicated temp configuration and view
- **Dynamic Path Substitution**: CSV paths are automatically updated to use the temp environment
- **Safe Cleanup**: Preserves test environment for debugging unless cleanup is requested
- **End-to-End Validation**: Tests the complete CSV import pipeline

## Features

### Isolated Test Environment

The self-test creates:
1. **Temporary Configuration**: `selftest-{test_id}-{timestamp}` (e.g., `selftest-abc12345-20251208-143022`)
2. **Temporary View**: `selftest-view-{test_id}` for DNS record testing

All CSV paths referencing the original config/view (e.g., `Default`, `Internal`) are dynamically substituted to use the temporary environment.

### Comprehensive Test Coverage

The self-test validates **45+ distinct test scenarios** across **10 functional categories**:

1. **Connection & Authentication**
   - API connectivity and authentication
   - Session management and token refresh
   - SSL/TLS certificate validation

2. **IP Management**
   - IPv4 Blocks creation and management
   - IPv4 Networks creation and management
   - IPv4 Address assignment and state management

3. **DNS Management**
   - DNS Zone creation and management
   - Host Record creation with multiple IPs
   - Resource Record management (MX, TXT, SRV, ALIAS)

4. **DHCP Management**
   - IPv4 DHCP Range configuration
   - DHCP Deployment Options
   - DHCP Deployment Roles for HA setups

5. **Export Functionality**
   - Network export by CIDR or ID
   - Block export with recursive children
   - Zone export with resource records

6. **Import Functionality**
   - Real CSV file parsing with CSVParser
   - Schema version validation with Pydantic models
   - Field validation (IP, MAC, CIDR, TTL)

7. **End-to-End Workflow Testing**
   - Complete pipeline testing with CSV files from samples directory
   - Dynamic path substitution for isolated testing
   - Dry-run and execute modes

8. **Safety Features**
   - Dangerous operation detection
   - Resource protection levels
   - Safety validation mechanisms

9. **Error Handling**
   - Invalid resource handling
   - Network error recovery
   - Rate limit handling

10. **Configuration Management**
    - Configuration discovery and caching
    - Entity retrieval by ID and type
    - Hierarchical relationship resolution

### Cleanup Behavior

The self-test provides three cleanup modes:

| Mode | Flag | Behavior |
|------|------|----------|
| **Preserve** | (default) | Test environment preserved for debugging/validation |
| **Auto-cleanup** | `--auto-cleanup` | Cleanup only if ALL tests pass (recommended for CI/CD) |
| **Force cleanup** | `--cleanup` | Always cleanup regardless of test results |

## Usage

### Basic CSV Self-Test (Dry-Run)

```bash
bluecat-import self-test \
  --url https://bam.example.com \
  --username admin \
  --csv-tests
```

This will:
1. Create a temporary configuration and view
2. Run all sample CSV files in dry-run mode
3. Substitute `Default` -> temp config name and `Internal` -> temp view name
4. Preserve the test environment for inspection

### CSV Self-Test with Auto-Cleanup

```bash
bluecat-import self-test \
  --url https://bam.example.com \
  --username admin \
  --csv-tests \
  --auto-cleanup
```

Cleans up the test environment only if all tests pass.

### CSV Self-Test with Custom Config/View Names

If your CSVs reference different config/view names:

```bash
bluecat-import self-test \
  --url https://bam.example.com \
  --username admin \
  --csv-tests \
  --config "Production" \
  --view "External" \
  --auto-cleanup
```

### Execute Mode (Real Changes)

```bash
bluecat-import self-test \
  --url https://bam.example.com \
  --username admin \
  --csv-tests \
  --csv-execute \
  --auto-cleanup
```

**Warning**: This makes real changes to the temporary configuration.

### Comprehensive Test (All Features)

```bash
bluecat-import self-test \
  --url https://bam.example.com \
  --username admin \
  --report test_report.json
```

### Force Cleanup After Failure

```bash
bluecat-import self-test \
  --url https://bam.example.com \
  --username admin \
  --csv-tests \
  --cleanup
```

## Command Options

| Option | Required | Description | Default |
|--------|----------|-------------|---------|
| `--url` | Yes | BlueCat Address Manager URL | - |
| `--username` | Yes | BAM username | - |
| `--password` | Yes | BAM password (prompts if not provided) | - |
| `--config` | No | Original configuration name in CSVs | `Default` |
| `--view` | No | Original view name in CSVs | `Internal` |
| `--test-prefix` | No | Prefix for temp configuration naming | `bluecat-csv-test` |
| `--auto-cleanup` | No | Cleanup only on successful tests | `False` |
| `--cleanup` | No | Force cleanup regardless of results | `False` |
| `--csv-tests` | No | Run CSV file tests from samples | `False` |
| `--samples-dir` | No | Directory containing CSV files | `./samples` |
| `--csv-file` | No | Specific CSV files to test (repeatable) | All CSVs |
| `--csv-execute` | No | Execute operations (vs dry-run) | `False` |
| `--report` | No | Save detailed report to JSON file | - |

## Path Substitution

The self-test automatically substitutes paths in CSV rows:

| Original Path | Substituted Path |
|---------------|------------------|
| `Default` | `selftest-abc12345-20251208-143022` |
| `Internal` | `selftest-view-abc12345` |
| `Default/10.0.0.0/8` | `selftest-abc12345-.../10.0.0.0/8` |
| `Internal/example.local` | `selftest-view-abc12345/example.local` |

Fields that are substituted:
- `config`, `config_path` - Simple config name
- `view_path` - Simple view name
- `network_path`, `zone_path`, `parent`, `parent_path` - Compound paths

## Test Report Format

### Summary Statistics
- Total tests run by category
- Pass/fail rates
- Overall success percentage
- Execution duration

### Test Environment Info
```json
{
  "test_environment": {
    "config_id": 12345,
    "config_name": "selftest-abc12345-20251208-143022",
    "view_id": 67890,
    "view_name": "selftest-view-abc12345",
    "original_config_name": "Default",
    "original_view_name": "Internal",
    "created_at": "2025-12-08T14:30:22.123456"
  }
}
```

### CSV Test Results
```json
{
  "csv_test_summary": {
    "total_files": 15,
    "successful_files": 15,
    "failed_files": 0,
    "total_operations": 45,
    "successful_operations": 45,
    "failed_operations": 0
  }
}
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: BlueCat Self-Test
on: [push, pull_request]

jobs:
  self-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install poetry
          poetry install
      - name: Run self-test
        run: |
          poetry run bluecat-import self-test \
            --url ${{ secrets.BAM_URL }} \
            --username ${{ secrets.BAM_USERNAME }} \
            --password ${{ secrets.BAM_PASSWORD }} \
            --csv-tests \
            --auto-cleanup \
            --report self_test_report.json
      - name: Upload test report
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: self-test-report
          path: self_test_report.json
```

### Jenkins Pipeline Example

```groovy
pipeline {
    agent any
    environment {
        BAM_URL = credentials('bam-url')
        BAM_USERNAME = credentials('bam-username')
        BAM_PASSWORD = credentials('bam-password')
    }
    stages {
        stage('Self-Test') {
            steps {
                sh '''
                    poetry install
                    poetry run bluecat-import self-test \
                        --url ${BAM_URL} \
                        --username ${BAM_USERNAME} \
                        --password ${BAM_PASSWORD} \
                        --csv-tests \
                        --auto-cleanup \
                        --report jenkins_self_test.json
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'jenkins_self_test.json', fingerprint: true
                }
            }
        }
    }
}
```

## Troubleshooting

### Common Issues

#### Authentication Failures
```
ERROR: SELF-TEST FAILED: Authentication failed
```
**Solution**: Verify username/password and check API access permissions.

#### Permission Errors
```
ERROR: Failed to create configuration
```
**Solution**: Ensure user has admin rights to create configurations and views.

#### Path Substitution Issues
```
ERROR: Resource not found after substitution
```
**Solution**: Check that your CSVs use `Default` for config and `Internal` for view, or specify correct names with `--config` and `--view`.

#### Cleanup Failures
```
ERROR: Failed to clean up test environment
```
**Solution**: Manually delete the test configuration in BAM UI. Look for configurations starting with `selftest-`.

### Debug Mode

```bash
export BLUECAT_LOG_LEVEL=DEBUG
bluecat-import self-test \
  --url https://bam.example.com \
  --username admin \
  --csv-tests
```

### Manual Cleanup

If automatic cleanup fails, manually clean up:

1. Log in to BAM UI
2. Navigate to Configurations
3. Find and delete configurations starting with `selftest-`

## Required Permissions

The self-test requires:

- **Configuration Management**: Create, read, delete configurations
- **View Management**: Create views
- **IP Address Management**: Create, read blocks, networks, addresses
- **DNS Management**: Create, read zones and records
- **DHCP Management**: Create, read DHCP objects

## Best Practices

1. **Use `--auto-cleanup` in CI/CD**: Ensures cleanup only on success, preserving failed runs for debugging
2. **Use `--dry-run` for initial testing**: Validate CSVs without making changes
3. **Specify correct `--config` and `--view`**: Match the names used in your sample CSVs
4. **Review reports**: Check detailed reports for validation errors
5. **Test environment isolation**: Use a dedicated BAM instance for automated testing

## Sample CSV Files

The self-test uses sample CSVs from the `samples/` directory:

| File | Resource Types | Description |
|------|----------------|-------------|
| `ip4_block.csv` | ip4_block | IPv4 address blocks |
| `ip4_network.csv` | ip4_network | IPv4 networks |
| `ip4_address.csv` | ip4_address | IPv4 addresses |
| `dns_zone.csv` | dns_zone | DNS zones |
| `host_record.csv` | host_record | Host (A) records |
| `alias_record.csv` | alias_record | CNAME records |
| `mx_record.csv` | mx_record | Mail exchanger records |
| `txt_record.csv` | txt_record | TXT records |
| `srv_record.csv` | srv_record | Service records |
| `generic_record.csv` | generic_record | CAA, SSHFP, TLSA, etc. |
| `ipv4_dhcp_range.csv` | ipv4_dhcp_range | DHCP ranges |
| `location.csv` | location | Location hierarchy |

All sample CSVs use:
- **Configuration**: `Default`
- **View**: `Internal`
- **Zone**: `example.local`
- **Professional naming conventions**

## Version History

- **0.4.0** (2025-12-08): Added isolated test environment with temp config/view
- **0.3.0** (2025-12-02): Added end-to-end workflow testing
- **0.2.0** (2025-11-15): Added CSV file testing
- **0.1.0** (2025-10-01): Initial self-test implementation
