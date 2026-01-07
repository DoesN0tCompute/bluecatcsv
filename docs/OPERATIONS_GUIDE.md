# BlueCat CSV Importer - Operations Guide

**Last Updated:** 2025-12-08 | **Version:** 0.3.0

This comprehensive guide covers best practices, troubleshooting, and performance optimization for operating the BlueCat CSV Importer in production environments.

## Table of Contents

- [Part 1: Best Practices](#part-1-best-practices)
- [Part 2: Troubleshooting](#part-2-troubleshooting)
- [Part 3: Performance Optimization](#part-3-performance-optimization)

---

# Part 1: Best Practices

This section outlines best practices for using the BlueCat CSV Importer in production environments.

## Organizational Best Practices

### 1. Establish Clear Ownership

```yaml
# Define responsibility matrix
Resource Type           | Owner      | Approver | Backup
------------------------|------------|----------|--------
IP Networks            | Network    | Network  | Security
DNS Zones              | DNS        | DNS      | Network
DHCP Scopes            | DHCP       | DHCP     | Network
Locations              | Facilities | Facilities| IT Ops
```

### 2. Create Standard Operating Procedures (SOPs)

Document your procedures:

```markdown
# SOP: Production DNS Changes

## Required Steps
1. [ ] Create change request in ticketing system
2. [ ] Export current zone state
3. [ ] Prepare CSV with changes
4. [ ] Peer review CSV changes
5. [ ] Validate with --dry-run
6. [ ] Schedule change window
7. [ ] Execute during maintenance window
8. [ ] Verify changes
9. [ ] Update documentation

## Rollback Procedures
If changes fail:
1. [ ] Stop import immediately
2. [ ] Use generated rollback CSV
3. [ ] Notify stakeholders
4. [ ] Document incident
```

### 3. Implement Change Management

```yaml
# Change management policy
change_types:
  low_risk:
    - Adding new IPs in existing networks
    - Updating DNS records
    - Adding comments/UDFs

  medium_risk:
    - Creating new subnets
    - Modifying DHCP scopes
    - Adding new DNS zones

  high_risk:
    - Deleting resources
    - Modifying core networks
    - Bulk changes > 1000 resources

approval_levels:
  low_risk: team_lead
  medium_risk: manager
  high_risk: director + architectural_review
```

## CSV File Management

### 1. File Organization Structure

```
bluecat-imports/
├── production/
│   ├── 2024/
│   │   ├── 12-Dec/
│   │   │   ├── approved/
│   │   │   ├── pending/
│   │   │   └── processed/
│   │   └── 11-Nov/
│   └── templates/
├── staging/
├── development/
├── templates/
│   ├── network-template.csv
│   ├── dns-template.csv
│   └── dhcp-template.csv
└── documentation/
    └── change-logs/
```

### 2. Naming Conventions

```bash
# Format: YYYY-MM-DD_{type}_{description}_{environment}.csv
# Examples:
2024-12-08_network_new-subnets_prod.csv
2024-12-08_dns_record-updates_staging.csv
2024-12-08_bulk-ip-assignments_prod.csv

# For ongoing work:
2024-12-08_network_site-expansion_part01_prod.csv
2024-12-08_network_site-expansion_part02_prod.csv
```

### 3. CSV Templates

Create standardized templates with validation:

```csv
# network-template.csv
# Description: Template for creating new networks
# Required: Fill in all required fields marked with *
row_id*,object_type*,action*,config*,name*,cidr*,description,location_code
NET001,ip4_network,create,Default,New Network,192.168.1.0/24,New subnet for dept,US-NYC
```

### 4. Documentation in CSV

```csv
# Include metadata rows (commented out or in separate file)
# Change Request: CR-2024-1234
# Approver: john.doe@company.com
# Scheduled: 2024-12-08 02:00 UTC
# Risk Level: Medium
```

## Import Workflow Best Practices

### 1. Pre-Import Checklist

```bash
#!/bin/bash
# pre-import-check.sh

set -euo pipefail

CSV_FILE=$1
ENVIRONMENT=$2

echo "=== Pre-Import Checklist for $CSV_FILE ==="

# 1. Validate CSV syntax
echo -n "✓ Validating CSV syntax... "
if bluecat-import validate "$CSV_FILE" --strict; then
    echo "PASS"
else
    echo "FAIL - Fix validation errors"
    exit 1
fi

# 2. Check file size
echo -n "✓ Checking file size... "
SIZE=$(wc -l < "$CSV_FILE")
if [[ $SIZE -gt 10000 ]]; then
    echo "WARNING - Large file ($SIZE rows), consider splitting"
else
    echo "PASS ($SIZE rows)"
fi

# 3. Check for dangerous operations
echo -n "✓ Checking for deletions... "
DELETES=$(grep -c '"delete"' "$CSV_FILE" || true)
if [[ $DELETES -gt 0 ]]; then
    echo "WARNING - $DELETES delete operations found"
else
    echo "PASS"
fi

# 4. Verify environment
echo -n "✓ Verifying environment... "
if [[ $ENVIRONMENT == "production" ]]; then
    echo "PRODUCTION - Extra caution required"
    read -p "Continue? (yes/no) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^yes$ ]]; then
        exit 1
    fi
else
    echo "PASS"
fi

# 5. Run dry run
echo -n "✓ Running dry run... "
if bluecat-import apply "$CSV_FILE" --dry-run; then
    echo "PASS"
else
    echo "FAIL - Dry run errors"
    exit 1
fi

echo "=== All checks passed ==="
```

### 2. Import Execution

```python
#!/usr/bin/env python3
"""
Managed import execution with logging and notifications
"""

import subprocess
import json
import time
from datetime import datetime
import smtplib
from pathlib import Path

def execute_import(csv_file, environment, dry_run=True):
    """Execute import with proper logging."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"logs/import_{timestamp}.log"

    cmd = [
        "bluecat-import", "apply", csv_file,
        f"--config=config/{environment}.yaml",
        "--verbose"
    ]

    if dry_run:
        cmd.append("--dry-run")

    # Execute with logging
    with open(log_file, "w") as f:
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        f.write(process.stdout)
        f.write(process.stderr)

    return log_file

def send_notification(status, log_file, csv_file):
    """Send status notification."""
    # Implementation depends on your notification system
    pass

# Usage in script
if __name__ == "__main__":
    csv_file = sys.argv[1]
    environment = sys.argv[2]

    # Always dry run first
    log = execute_import(csv_file, environment, dry_run=True)

    # Prompt for production
    if environment == "production":
        response = input("Dry run successful. Apply to production? (yes/no): ")
        if response.lower() == "yes":
            log = execute_import(csv_file, environment, dry_run=False)
            send_notification("completed", log, csv_file)
```

### 3. Post-Import Verification

```bash
#!/bin/bash
# post-import-verify.sh

CSV_FILE=$1
SESSION_ID=$2

echo "=== Post-Import Verification ==="

# 1. Check import status
echo "Import status:"
bluecat-import status $SESSION_ID

# 2. Verify no deferred items
echo -n "Checking for deferred items... "
DEFERRED=$(bluecat-import status $SESSION_ID --show-deferred | grep -c "deferred" || true)
if [[ $DEFERRED -gt 0 ]]; then
    echo "WARNING - $DEFERRED deferred items found"
    echo "Run: bluecat-import apply $CSV_FILE --resolve-deferred --session $SESSION_ID"
else
    echo "PASS"
fi

# 3. Generate verification report
echo "Generating verification report..."
bluecat-import export --recent --since "1 hour ago" > verification_report.csv

# 4. Compare with expected changes
# (Custom comparison logic based on your needs)

echo "=== Verification complete ==="
```

## Performance Optimization

### 1. Optimize CSV Structure

```csv
# Good: Group related resources together
row_id,object_type,action,config,name,cidr,parent
1,ip4_block,create,Default,Block-10,10.0.0.0/8,
2,ip4_network,create,Default,Network-10.1,10.1.0.0/16,/IPv4/10.0.0.0/8
3,ip4_network,create,Default,Network-10.2,10.2.0.0/16,/IPv4/10.0.0.0/8

# Bad: Random order increases dependency resolution
row_id,object_type,action,config,name,cidr,parent
1,ip4_network,create,Default,Network-10.1,10.1.0.0/16,/IPv4/10.0.0.0/8  # Parent not yet created
2,ip4_block,create,Default,Block-10,10.0.0.0/8,
3,ip4_address,create,Default,Host-1,,,10.1.1.10  # Network not yet created
```

### 2. Batch Size Optimization

```yaml
# For different scenarios
scenarios:
  small_changes:
    batch_size: 10
    checkpoint_interval: 50

  medium_imports:
    batch_size: 100
    checkpoint_interval: 500

  large_imports:
    batch_size: 500
    checkpoint_interval: 1000

  memory_constrained:
    batch_size: 20
    checkpoint_interval: 100
```

### 3. Concurrency Guidelines

```yaml
# Start conservative and increase based on performance
concurrency_levels:
  initial: 5
  small_environment: 10
  medium_environment: 20
  large_environment: 50

# Monitor these metrics
metrics_to_watch:
  - api_response_time
  - error_rate
  - throughput
  - memory_usage
```

## Safety and Risk Management

### 1. Safety Checklist

```markdown
## Pre-Import Safety Checklist

- [ ] CSV reviewed by peer
- [ ] Dry run completed successfully
- [ ] Rollback plan documented
- [ ] Maintenance window scheduled
- [ ] Stakeholders notified
- [ ] Backup completed
- [ ] Test environment validated
- [ ] Emergency contacts on standby
```

### 2. Deletion Safeguards

> **Critical Safety Restriction:**
> **Configurations and Views can NEVER be deleted via CSV import.** This is a permanent safety block that cannot be bypassed, even with `--allow-dangerous-operations`. These resources must be managed directly in BlueCat Address Manager.

```yaml
# config.yaml with extra safety for deletions
policy:
  safe_mode: true
  allow_dangerous_operations: false  # Require explicit flag for block/network/zone deletions

# Deletable resource tiers:
# - NEVER via CSV: configuration, view (permanent block)
# - With flag: ip4_block, ip4_network, dns_zone (require --allow-dangerous-operations)
# - Always: ip4_address, host_record, etc. (safe to delete)

# Require explicit confirmation for high-risk deletes
# bluecat-import apply deletes.csv --allow-dangerous-operations --yes
```

### 3. Rollback Procedures

```bash
# rollback-procedure.sh
#!/bin/bash

ROLLBACK_FILE=$1
BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"

echo "=== Rollback Procedure ==="
echo "Rollback file: $ROLLBACK_FILE"

# 1. Create backup before rollback
echo "Creating backup..."
mkdir -p "$BACKUP_DIR"
bluecat-import export --full > "$BACKUP_DIR/pre-rollback.csv"

# 2. Review rollback changes
echo "Reviewing rollback changes..."
bluecat-import apply "$ROLLBACK_FILE" --dry-run

# 3. Confirm rollback
read -p "Proceed with rollback? (yes/no) " -n 1 -r
echo
if [[ $REPLY =~ ^yes$ ]]; then
    echo "Executing rollback..."
    bluecat-import apply "$ROLLBACK_FILE" --yes
    echo "Rollback completed"
else
    echo "Rollback cancelled"
fi
```

### 4. Change Freeze Procedures

```markdown
## Change Freeze Policy

Freeze Periods:
- Black Friday/Cyber Monday week
- End of quarter (last 3 days)
- Major product launches
- System maintenance windows

During Freeze:
- Only emergency changes allowed
- Requires VP approval
- Additional testing required
- Enhanced monitoring
```

## Monitoring and Maintenance

### 1. Daily Health Checks

```bash
#!/bin/bash
# daily-health-check.sh

echo "=== Daily BlueCat Importer Health Check ==="

# 1. Check disk space
echo "Disk usage:"
df -h .changelogs/ logs/ reports/

# 2. Check recent imports
echo -n "Recent imports (last 24h): "
bluecat-import history --since "1 day ago" | wc -l

# 3. Check error rates
echo -n "Error rate (last 24h): "
# Parse logs to calculate error rate

# 4. Check for deferred items
echo "Checking deferred items..."
# Find any sessions with deferred items

# 5. Archive old logs
echo "Archiving old logs..."
find logs/ -name "*.log" -mtime +30 -exec gzip {} \;

echo "=== Health check complete ==="
```

### 2. Monthly Maintenance

```bash
#!/bin/bash
# monthly-maintenance.sh

echo "=== Monthly Maintenance ==="

# 1. Clean up old changelogs
echo "Cleaning changelogs older than 90 days..."
find .changelogs/ -name "*.csv" -mtime +90 -delete

# 2. Update documentation
echo "Updating import statistics..."
# Generate monthly report

# 3. Review performance metrics
echo "Performance review..."
# Analyze metrics from the month

# 4. Backup configurations
echo "Backing up configurations..."
tar -czf "backups/config-$(date +%Y%m).tar.gz" config/

echo "=== Maintenance complete ==="
```

### 3. Alert Configuration

```yaml
# Critical alerts
alerts:
  critical:
    - Import failure in production
    - More than 100 failed operations
    - Safety mode violations

  warning:
    - High error rate (>5%)
    - Slow performance (<10 ops/sec)
    - Memory usage >80%

  info:
    - Import completion
    - Rollback executed
    - New deployment
```

## Team Collaboration

### 1. Code Review Process

```markdown
## CSV Review Template

### Change Description
- What is being changed?
- Why is it needed?
- Impact assessment

### Technical Review
- [ ] CSV syntax valid
- [ ] Dependencies correct
- [ ] No dangerous operations
- [ ] Proper rollback possible

### Business Review
- [ ] Approved by business owner
- [ ] Change window approved
- [ ] Stakeholders notified

### Approval Sign-off
- Technical Lead: _________________
- Business Owner: _________________
- Change Manager: _________________
```

### 2. Documentation Standards

```markdown
# Change Log Template

## Date: YYYY-MM-DD
## Author: Name <email@company.com>
## Change Request: CR-######

### Changes Made
- List of changes with counts

### Pre-Import Validation
- Dry run results
- Reviewer notes

### Post-Import Verification
- Actual results vs expected
- Any issues encountered

### Lessons Learned
- What went well
- What could be improved
```

### 3. Knowledge Sharing

```yaml
# Regular training schedule
training_topics:
  monthly:
    - New feature demonstrations
    - Common issues and solutions
    - Performance tuning tips

  quarterly:
    - Advanced use cases
    - Integration patterns
    - Troubleshooting workshops

  annually:
    - Complete refresher course
    - Certification update
```

## Disaster Recovery

### 1. Backup Strategy

```bash
#!/bin/bash
# backup-strategy.sh

# 1. Regular backups
bluecat-import export --full --output "backups/full-$(date +%Y%m%d).csv"

# 2. Incremental backups
bluecat-import export --since "1 day ago" --output "backups/incremental-$(date +%Y%m%d).csv"

# 3. Critical resource backups
bluecat-import export --config "Default" --network "10.0.0.0/8" --output "backups/critical-$(date +%Y%m%d).csv"

# 4. Offsite backup
scp backups/*.csv backup-server:/bluecat-backups/
```

### 2. Recovery Procedures

```markdown
## Disaster Recovery Playbook

### Scenario 1: Import Corruption
1. Identify last known good state
2. Restore from backup
3. Re-apply changes since backup
4. Verify integrity

### Scenario 2: Complete System Loss
1. Restore from offsite backup
2. Verify all configurations
3. Test critical functions
4. Notify all stakeholders

### Scenario 3: Partial Data Loss
1. Identify affected resources
2. Export current state
3. Compare with expected state
4. Re-create lost resources
```

### 3. Testing Recovery

```bash
#!/bin/bash
# test-recovery.sh

# Monthly recovery test
echo "=== Recovery Test ==="

# 1. Create test environment
bluecat-import export --full > test-backup.csv

# 2. Simulate disaster
# (In test environment only!)

# 3. Test recovery
echo "Testing recovery procedure..."
time bluecat-import apply test-backup.csv --config test-config.yaml

# 4. Verify results
echo "Verifying recovery..."
bluecat-import self-test --config test-config.yaml

echo "=== Recovery test complete ==="
```

---

# Part 2: Troubleshooting

This section helps you diagnose and resolve common issues with the BlueCat CSV Importer.

## Quick Diagnosis Checklist

When experiencing issues, run through this checklist:

```bash
# 1. Check basic connectivity
bluecat-import self-test

# 2. Validate CSV format
bluecat-import validate your_file.csv --strict

# 3. Check recent logs with enhanced output
tail -f logs/importer.log

# 4. Verify configuration
bluecat-import version --show-config

# 5. Test with a simple import using verbose mode
echo "row_id,object_type,action,config,name,cidr" > test.csv
echo "1,ip4_network,create,Default,Test,192.168.99.0/24" >> test.csv
bluecat-import apply test.csv --dry-run --verbose

# 6. For dependency issues, visualize the graph
bluecat-import apply your_file.csv --show-deps > deps.dot
dot -Tpng deps.dot -o deps.png  # Requires Graphviz

# 7. Preview execution order before running
bluecat-import apply your_file.csv --show-plan
```

## Common Error Messages

### `Authentication failed: Invalid credentials`

**Cause**: Incorrect username/password or API token

**Solution**:
```bash
# Check credentials
curl -X POST https://your-bam.com/api/v2/sessions \
  -H "Content-Type: application/json" \
  -d '{"username": "your_user", "password": "your_pass"}'

# Update configuration
export BAM_USERNAME="correct_user"
export BAM_PASSWORD="correct_pass"
```

### `Resource not found: Configuration 'Default' does not exist`

**Cause**: Configuration name is incorrect or user lacks permissions

**Solution**:
```bash
# List available configurations
bluecat-export --list-configurations

# Update CSV with correct configuration name
# Example: "config" might need to be "My Company" instead of "Default"
```

### `Circular dependency detected`

**Cause**: Resources depend on each other in a loop

**Solution**:
```bash
# Visualize dependency graph
bluecat-import validate problematic.csv --dependency-graph --output graph.dot

# Manually review and fix dependencies
# Remove circular references or restructure dependencies
```

### `API rate limit exceeded`

**Cause**: Too many requests in short period

**Solution**:
```yaml
# Reduce concurrency in config.yaml
policy:
  max_concurrent_operations: 5  # Reduce from higher value

throttling:
  enabled: true
  target_latency: 500  # Increase target latency
```

### `Pagination loop detected`

**Error**: `Pagination loop detected - request already seen`

**Cause**: The BAM API is returning a `next` link that points to a previously visited page, causing an infinite cycle. This usually indicates an issue with the BAM API or data consistency on the server.

**Solution**:
The importer detects this automatically and stops. To troubleshoot:
1. Check BAM logs for consistency specific to the endpoint being queried.
2. If data is missing, try running with a smaller batch size or filter scope.


## Authentication Issues

### Session Expired

**Symptoms**: Suddenly getting authentication errors during long imports

**Diagnosis**:
```bash
# Check session status
bluecat-import status

# Look for session expiration in logs
grep "session" logs/importer.log | tail -10
```

**Solution**:
The importer automatically handles session renewal. If issues persist:

```yaml
# Add session configuration
bam:
  session_timeout: 1800  # 30 minutes
  auto_renew: true
```

### Permission Denied

**Symptoms**: Can create some resources but not others

**Diagnosis**:
```bash
# Test permissions for different resource types
bluecat-import self-test --test-permissions --resource-types ip4_network,dns_zone
```

**Solution**:
Ensure your BAM user has:
- `Zone Admin` for DNS operations
- `IP Admin` for IP space operations
- `Configuration Admin` for configuration changes

## CSV Validation Errors

### Missing Required Columns

**Error**: `Missing required column: 'row_id'`

**Common required columns**:
- `row_id`: Unique identifier for each row
- `object_type`: Type of resource (ip4_network, dns_zone, etc.)
- `action`: create, update, or delete

**Solution**:
```csv
# Ensure your CSV has required columns
row_id,object_type,action,config,name,cidr
1,ip4_network,create,Default,Network1,10.0.1.0/24
```

### Invalid Header / BOM Issues

**Error**: `Validation Error: field required (row_id)` when the column appears to exist.

**Cause**: File saved with Byte Order Mark (BOM) on older versions of the tool.

**Solution**:
The current version automatically handles BOM (using `utf-8-sig`). If issues persist:
1. Open in a text editor like VS Code or Notepad++
2. Save with encoding "UTF-8" (without BOM)
3. Ensure no hidden characters at the start of the file


### Invalid Data Format

**Error**: `Invalid CIDR format: '10.0.1.0/24/32'`

**Common format issues**:
- CIDR: Must be valid CIDR notation (e.g., `10.0.0.0/8`)
- MAC addresses: Must be colon-separated (e.g., `00:11:22:33:44:55`)
- Email addresses: Must be valid format for MX records

**Solution**:
```bash
# Use the fix command to auto-correct common issues
bluecat-import fix dirty.csv -o clean.csv

# Manual verification
bluecat-import validate clean.csv --strict
```

### Duplicate Row IDs

**Error**: `Duplicate row_id: 'network1' found`

**Solution**:
```bash
# Find duplicates
awk -F, 'NR>1 {print $1}' data.csv | sort | uniq -d

# Fix by adding unique prefixes
awk -F, 'BEGIN{OFS=","} NR>1 {$1="row_"NR; print}' data.csv > fixed.csv
```

## Dependency Resolution Failures

### Parent Resource Not Found

**Error**: `Parent network '10.0.0.0/8' not found`

**Cause**: Parent resource doesn't exist or hasn't been created yet

**Solution**:
```csv
# Ensure parent is defined first
row_id,object_type,action,config,name,cidr,parent
1,ip4_block,create,Default,Corporate,10.0.0.0/8,
2,ip4_network,create,Default,DeptA,10.1.0.0/16,/IPv4/10.0.0.0/8
```

### Deferred Resolution

**Symptoms**: Import completes but some resources show "deferred" status

**Cause**: Resources couldn't be resolved during import

**Solution**:
```bash
# Check deferred resources
bluecat-import status <session_id> --show-deferred

# Re-run with --resolve-deferred flag
bluecat-import apply original.csv --resolve-deferred --session <session_id>
```

## API and Network Issues

### Connection Timeout

**Error**: `Connection timeout after 30 seconds`

**Solutions**:

1. Increase timeout values:
```yaml
bam:
  timeout: 60.0
  connect_timeout: 15.0
```

2. Check network connectivity:
```bash
# Test connectivity to BAM server
ping your-bam.com
telnet your-bam.com 443
```

3. Use a closer server or VPN:
```yaml
# If behind VPN
bam:
  base_url: "https://internal-bam.company.com"
```

### SSL Certificate Errors

**Error**: `SSL: CERTIFICATE_VERIFY_FAILED`

**Solutions**:

1. Use proper certificate:
```yaml
bam:
  verify_ssl: true
  ca_cert_path: "/path/to/ca.pem"
```

2. For testing only (not recommended for production):
```yaml
bam:
  verify_ssl: false
```

3. Export certificate:
```bash
# Export certificate from server
openssl s_client -showcerts -connect your-bam.com:443 </dev/null 2>/dev/null | openssl x509 -outform PEM > bam_cert.pem
```

## Performance Problems

### Import is Too Slow

**Symptoms**: Processing fewer than 10 operations per second

**Diagnosis**:
```bash
# Check current performance
bluecat-import status <session_id> --show-metrics

# Identify bottlenecks
bluecat-import validate large.csv --performance-analysis
```

**Solutions**:

1. Increase concurrency:
```yaml
policy:
  max_concurrent_operations: 20  # Increase gradually
```

2. Enable performance optimizations:
```yaml
performance:
  cache_size: 10000
  batch_processing: true
  async_resolution: true
```

3. Check BAM server load:
```bash
# Monitor BAM server performance
# Contact BAM administrator if server is overloaded
```

### Memory Issues

**Symptoms**: OutOfMemory errors, system swapping

**Solutions**:

1. Reduce memory usage:
```yaml
performance:
  cache_size: 1000  # Reduce from default
  batch_size: 50    # Smaller batches
```

2. Split large files:
```bash
# Split CSV into smaller chunks
python scripts/split_csv.py --input large.csv --output-dir chunks/ --chunk-size 5000
```

3. Use streaming mode:
```bash
bluecat-import apply large.csv --streaming --checkpoint-every 1000
```

## Rollback Issues

### Rollback File Not Found

**Error**: `Rollback file not found: .changelogs/123_rollback.csv`

**Solution**:
```bash
# List all available rollbacks
ls -la .changelogs/*_rollback.csv

# Find the correct rollback file
grep -l "your_operation" .changelogs/*_rollback.csv
```

### Rollback Fails

**Symptoms**: Rollback operations fail with errors

**Diagnosis**:
```bash
# Test rollback before execution
bluecat-import rollback 123_rollback.csv --dry-run

# Check what will be rolled back
bluecat-import rollback 123_rollback.csv --show-changes
```

**Common causes**:
- Resources deleted outside of importer
- Permissions changed since original import
- Dependencies modified

## Debug Mode and Logging

### Enabling Debug Mode

```bash
# Enable verbose logging for detailed output
bluecat-import apply data.csv --verbose

# Enable debug-level tracing for maximum detail
bluecat-import apply data.csv --debug

# Or via environment variable
export LOG_LEVEL=DEBUG
bluecat-import apply data.csv

# Or in configuration
observability:
  logging:
    level: "DEBUG"
    format: "json"
    file: "logs/importer-debug.log"
```

### Capturing API Traffic

```yaml
# Enable API debugging
bam:
  debug_requests: true
  save_responses: true
  response_dir: "logs/api-responses/"
```

### New Debugging Features

#### Dependency Graph Visualization

Visualize resource dependencies to understand execution order and resolve issues:

```bash
# Generate DOT format dependency graph
bluecat-import apply data.csv --show-deps > dependencies.dot

# Convert to PNG (requires Graphviz)
dot -Tpng dependencies.dot -o dependencies.png

# Convert to SVG for web viewing
dot -Tsvg dependencies.dot -o dependencies.svg
```

#### Execution Plan Preview

See the exact order in which operations will be executed:

```bash
# Preview execution order without applying changes
bluecat-import apply data.csv --show-plan

# Combine with dry-run for maximum visibility
bluecat-import apply data.csv --dry-run --show-plan --verbose
```

#### Enhanced Error Context

The importer now provides enhanced error messages with:
- Full context and tracebacks
- Related operations that might be affected
- Suggested remediation steps
- Dependency chain information when relevant

Example enhanced error:
```
ERROR: Failed to create host_record 'www.example.com'
Context: Creating DNS record in zone 'example.com'
Dependencies: Requires zone 'example.com' to exist
Affected Operations: 2 alias records reference this host
Suggestion: Ensure zone 'example.com' exists or is created in the same CSV
```

### Creating a Diagnostic Report

```bash
# Generate comprehensive report
bluecat-import self-test --full-diagnostics --output diagnostics.json

# Include recent logs
tar -czf support-bundle.tar.gz \
  logs/importer.log \
  diagnostics.json \
  config.yaml \
  your_import.csv

# Include dependency graph for analysis
bluecat-import apply your_import.csv --show-deps > support-bundle/deps.dot
```

## Getting Help

### Before Requesting Support

1. **Gather Information**:
   ```bash
   bluecat-import version
   python --version
   uname -a
   ```

2. **Create Minimal Reproduction**:
   ```bash
   # Create a minimal failing example
   echo "row_id,object_type,action,config,name,cidr" > minimal.csv
   echo "1,ip4_network,create,Default,Test,192.168.99.0/24" >> minimal.csv
   bluecat-import apply minimal.csv --dry-run
   ```

3. **Check Known Issues**:
   - Review GitHub issues
   - Check CHANGELOG.md for recent fixes
   - Search documentation

### Contact Information

- **Documentation**: Check `docs/` directory first
- **Issues**: Create GitHub issue with full diagnostic bundle
- **Community**: Join the discussion forums
- **Enterprise**: Contact your support representative

### Creating a Good Bug Report

Include in your report:

1. **Environment**:
   - Importer version
   - Python version
   - Operating system
   - BAM version

2. **Reproduction Steps**:
   - Exact commands used
   - Sample CSV (sanitized)
   - Configuration (sanitized)

3. **Error Messages**:
   - Full error output
   - Logs with DEBUG level
   - Screenshots if applicable

4. **Expected vs Actual**:
   - What you expected to happen
   - What actually happened

## Quick Reference Commands

```bash
# Health check
bluecat-import self-test

# Validate with strict checking
bluecat-import validate file.csv --strict

# Dry run with detailed output
bluecat-import apply file.csv --dry-run --verbose

# Check status with deferred items
bluecat-import status <session-id> --show-deferred

# Rollback with preview
bluecat-import rollback file.csv --dry-run --show-changes

# Export for backup
bluecat-import export --full --output backup.csv

# Performance analysis
bluecat-import apply file.csv --profile --output perf.json

# Generate support bundle
bluecat-import self-test --full-diagnostics --output bundle.tar.gz
```

---

# Part 3: Performance Optimization

This section provides comprehensive performance tuning recommendations for the BlueCat CSV Importer to optimize throughput, minimize resource usage, and ensure reliable operation at scale.

## Understanding Performance Factors

The importer's performance is influenced by several key factors:

- **API Rate Limits**: BlueCat BAM enforces API rate limits
- **Network Latency**: Round-trip time to the BAM server
- **Concurrent Operations**: Number of parallel API requests
- **Dependency Complexity**: Depth and breadth of resource dependencies
- **CSV File Size**: Number of rows and complexity of data
- **BAM Server Load**: Current load on the BlueCat server

## Configuration Tuning

### Basic Performance Configuration

```yaml
# config.yaml
policy:
  max_concurrent_operations: 20  # Adjust based on BAM capacity
  failure_policy: "fail_group"    # Stop related operations on failure
  safe_mode: true                 # Keep enabled for production

bam:
  timeout: 30.0                   # API timeout in seconds
  retry_attempts: 3               # Number of retries for failed requests

throttling:
  enabled: true                   # Enable adaptive throttling
  target_latency: 200             # Target response time (ms)
  max_increase_rate: 0.2          # Max 20% increase per adjustment
  max_decrease_rate: 0.5          # Max 50% decrease per adjustment
```

### Advanced Configuration

```yaml
# For high-performance environments
policy:
  max_concurrent_operations: 50
  failure_policy: "continue"      # Continue on individual failures

throttling:
  enabled: true
  target_latency: 500             # Higher latency for more throughput
  circuit_breaker_threshold: 10   # Stop after 10 consecutive errors
  circuit_breaker_timeout: 60     # Wait 60s before resuming

performance:
  cache_size: 10000              # Resource resolution cache size
  batch_size: 100                # Process in batches
  checkpoint_interval: 1000      # Save progress every 1000 operations
```

## Deployment Size Guidelines

### Small Deployments (< 1,000 resources)

```yaml
policy:
  max_concurrent_operations: 5
  checkpoint_interval: 100

throttling:
  target_latency: 100
```

**Characteristics:**
- Low memory footprint (< 100MB)
- Fast completion (< 5 minutes)
- Minimal impact on BAM server

### Medium Deployments (1,000 - 10,000 resources)

```yaml
policy:
  max_concurrent_operations: 20
  checkpoint_interval: 500

throttling:
  target_latency: 200
```

**Characteristics:**
- Moderate memory usage (100MB - 500MB)
- Completion time: 5-30 minutes
- Noticeable but manageable BAM load

### Large Deployments (10,000+ resources)

```yaml
policy:
  max_concurrent_operations: 50
  checkpoint_interval: 1000

throttling:
  target_latency: 500

performance:
  cache_size: 50000
  batch_size: 500
```

**Characteristics:**
- High memory usage (500MB+)
- Extended run time (30+ minutes)
- Significant BAM server load
- Consider running during maintenance windows

## Memory Management

### Estimating Memory Requirements

Use this formula to estimate memory usage:

```
Base Memory: 50MB
+ CSV Size (bytes) × 3
+ Resource Cache: 1KB × number_of_resources
+ Dependency Graph: 100 bytes × (rows²)
```

**Example:**
- 10,000 rows CSV (2MB)
- 5,000 unique resources
- Estimated memory: 50 + 6 + 5 + 10 = **71MB minimum**

### Memory Optimization Tips

1. **Split Large Files**: Break imports into logical chunks
2. **Use Checkpoints**: Enable resumable imports to avoid re-processing
3. **Adjust Cache Size**: Reduce cache size if memory constrained
4. **Batch Processing**: Process in smaller batches

```yaml
# Memory-constrained configuration
policy:
  max_concurrent_operations: 5
  checkpoint_interval: 50

performance:
  cache_size: 1000
  batch_size: 50
```

## Network Optimization

### Network Bandwidth Considerations

- **Minimum**: 1 Mbps for small imports
- **Recommended**: 10 Mbps for medium imports
- **Optimal**: 100 Mbps for large imports

### Latency Optimization

1. **Proximity**: Run importer as close to BAM server as possible
2. **VPN**: Consider dedicated VPN for stable latency
3. **DNS**: Use IP addresses to avoid DNS resolution delays

### Timeout Configuration

```yaml
bam:
  timeout: 30.0          # Base timeout
  connect_timeout: 10.0  # Connection timeout
  read_timeout: 20.0     # Read timeout

  # Slow network configuration
  timeout: 60.0
  connect_timeout: 20.0
  read_timeout: 40.0
```

## Large Import Strategies

### 1. Resource Type Segregation

Split imports by resource type to reduce dependency complexity:

```bash
# Import infrastructure first
bluecat-import apply 01-configuration.csv
bluecat-import apply 02-blocks.csv
bluecat-import apply 03-networks.csv

# Then import dependent resources
bluecat-import apply 04-zones.csv
bluecat-import apply 05-records.csv
bluecat-import apply 06-addresses.csv
```

### 2. Geographic Segregation

For multi-site deployments:

```bash
# Process by region
bluecat-import apply us-east-resources.csv
bluecat-import apply us-west-resources.csv
bluecat-import apply eu-resources.csv
```

### 3. Dependency-Aware Splitting

Use the dependency analyzer to identify optimal split points:

```bash
# Analyze dependencies
bluecat-import validate large-import.csv --dependency-graph

# Split based on analysis
python scripts/split_by_dependencies.py large-import.csv --output-dir chunks/
```

## Monitoring Performance

### Key Metrics to Track

1. **Operations per Second**: Current processing rate
2. **API Response Time**: Average BAM API latency
3. **Error Rate**: Percentage of failed operations
4. **Memory Usage**: Current memory consumption
5. **Queue Depth**: Number of pending operations

### Built-in Monitoring

Enable detailed metrics:

```yaml
observability:
  metrics:
    enabled: true
    export_interval: 10  # Export every 10 seconds
    export_format: "prometheus"
```

Access metrics at: `http://localhost:8080/metrics`

### Performance Dashboard Example

```python
# Example Grafana dashboard configuration
{
  "panels": [
    {
      "title": "Operations/sec",
      "type": "graph",
      "targets": [
        {
          "expr": "rate(importer_operations_total[5m])"
        }
      ]
    },
    {
      "title": "API Latency",
      "type": "graph",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, rate(bam_api_latency_seconds_bucket[5m]))"
        }
      ]
    }
  ]
}
```

## Troubleshooting Performance Issues

### Slow Processing

**Symptoms**: Low operations per second, long run times

**Solutions**:
1. Increase `max_concurrent_operations`
2. Check network latency to BAM server
3. Verify BAM server isn't overloaded
4. Check for throttling by BlueCat

### Memory Issues

**Symptoms**: OutOfMemory errors, system swapping

**Solutions**:
1. Reduce `cache_size`
2. Lower `max_concurrent_operations`
3. Split CSV into smaller files
4. Enable more frequent checkpoints

### Timeouts

**Symptoms**: Operation timeout errors

**Solutions**:
1. Increase `timeout` values
2. Check network stability
3. Reduce concurrent operations
4. Implement retry logic

### API Rate Limiting

**Symptoms**: 429 Too Many Requests errors

**Solutions**:
1. Enable adaptive throttling
2. Reduce concurrent operations
3. Increase delay between operations
4. Contact BlueCat about rate limits

## Performance Testing

### Load Testing Script

```bash
#!/bin/bash
# performance_test.sh

# Generate test data
python generate_test_data.py --count 10000 --output test_data.csv

# Run with different configurations
for ops in 5 10 20 50; do
    echo "Testing with $ops concurrent operations..."

    cat > config_test.yaml << EOF
policy:
  max_concurrent_operations: $ops
EOF

    bluecat-import apply test_data.csv \
        --config config_test.yaml \
        --dry-run \
        --timing-report \
        > results_${ops}.json

    sleep 60  # Cool down period
done

# Analyze results
python analyze_performance.py results_*.json
```

## Best Practices Summary

1. **Start Conservative**: Begin with low concurrency and increase gradually
2. **Monitor Continuously**: Always watch metrics during large imports
3. **Plan for Failures**: Use checkpoints and test rollback procedures
4. **Schedule Wisely**: Run large imports during off-peak hours
5. **Document Everything**: Record what works for your environment
6. **Test Thoroughly**: Validate with production-like data volumes
7. **Network First**: Optimize network before tuning application settings

---

## Summary

Following the best practices, troubleshooting techniques, and performance optimization strategies in this guide will help you operate the BlueCat CSV Importer reliably and efficiently in production environments.
