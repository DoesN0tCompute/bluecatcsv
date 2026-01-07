# Test CSV Files

This directory contains CSV test files for validating and testing the BlueCat CSV Importer functionality.

## VALIDATED: Validated Test Files

The following **13 CSV files** have been validated and confirmed to pass the current CSV schema validation:

### IP Management Tests
- **`self-test-simple.csv`** - Basic IP management (block, network, address)
- **`self-test-ip-types.csv`** - IPv4 address management test cases
- **`self-test-all-types.csv`** - Comprehensive IP address management examples
- **`test-dhcp-real-network.csv`** - Real DHCP network configuration examples

### DNS Tests
- **`self-test-dns-types.csv`** - DNS zone and host record examples
- **`test-dns-real-block.csv`** - Block-level DNS deployment roles
- **`test-dns-real-network.csv`** - Network-level DNS deployment roles
- **`test-dns-real-zone.csv`** - Zone-level DNS deployment roles
- **`test-dns-deployment-role-block-level.csv`** - Block-level DNS deployment role tests
- **`test-dns-deployment-role-network-level.csv`** - Network-level DNS deployment role tests
- **`test-dns-deployment-role-zone-level.csv`** - Zone-level DNS deployment role tests

### DHCP Tests
- **`self-test-dhcp-types.csv`** - DHCP ranges, client classes, and deployment roles
- **`test-dhcp-deployment-role.csv`** - DHCP deployment role examples

## CLEANED: Cleaned Up Files

The following **14 invalid CSV files** were identified and removed from the repository due to validation errors:

### Removed Files:
- `self-test-all-8-types.csv` - Data format issues with string parsing
- `self-test-dangerous.csv` - Deprecated object types and format errors
- `self-test-all-dns-records.csv` - Invalid data structure
- `self-test-all-types-working.csv` - Validation errors
- `self-test-comprehensive-working.csv` - Field format issues
- `self-test-comprehensive.csv` - Multiple validation errors
- `test-dns-deployment-role.csv` - Missing required parent paths
- `test-prerequisites.csv` - Invalid string values
- `test-deployment-roles.csv` - Missing required fields
- `test-comprehensive-deployment-roles.csv` - Field format issues
- `test-deployment-roles-real.csv` - Data format problems
- `test-comprehensive-deployment-roles-real.csv` - Format issues
- `test-prerequisites-and-roles.csv` - Invalid string formats

### Why They Were Removed:
- Outdated object types and field names
- Invalid data formats and parsing errors
- Missing required fields for current schema
- Deprecated functionality and testing approaches
- Poor data quality and inconsistent formatting

## Usage

To validate any CSV file:

```bash
python3 import.py validate tests/filename.csv
```

To run a dry-run test:

```bash
python3 import.py apply tests/filename.csv --dry-run
```

## Server Name Resolution Feature

The DNS deployment role CSV files support the new server name resolution feature:

```csv
# Server names (automatically resolved)
interfaces="dns-server-1|dns-server-2"

# Server:interface format
interfaces="dns-server-1:eth0|dns-server-2:eth1"

# Mixed formats
interfaces="12345|dns-server-1:eth0|server2"
```