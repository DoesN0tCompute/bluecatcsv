# BlueCat CSV Importer - Tutorial

**Last Updated:** 2025-12-08 | **Version:** 0.3.0

Complete guide to using the BlueCat CSV Importer for bulk operations.

## Table of Contents

1. [Quick Start](#quick-start)
2. [CSV Format](#csv-format)
3. [Common Workflows](#common-workflows)
4. [Advanced Features](#advanced-features)
5. [Best Practices](#best-practices)
6. [Troubleshooting](#troubleshooting)

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd bluecat-csv

# Install dependencies with Poetry
poetry install

# Or with pip
pip install -e .
```

### Basic Usage

```bash
# 1. Validate your CSV file
bluecat-import validate samples/simple_import.csv

# 2. Test with dry-run
bluecat-import apply samples/simple_import.csv --dry-run

# 3. Execute the import
bluecat-import apply samples/simple_import.csv

# 4. Check status
bluecat-import status <session-id>

# 5. View history
bluecat-import history
```

## CSV Format

### Required Columns

- `row_id`: Unique identifier for each row (string or number)
- `object_type`: Type of resource (ip4_network, ip4_address, ip4_block, dns_zone, host_record)
- `action`: Operation to perform (create, update, delete)

### Object-Specific Columns

#### IP4 Network
```csv
row_id,object_type,action,config,parent,name,cidr
1,ip4_network,create,Default,/IPv4/10.0.0.0/8,Corp-Network,10.1.0.0/16
```

#### IP4 Address
```csv
row_id,object_type,action,config,address,name,mac
2,ip4_address,create,Default,10.1.0.5,server1,00:11:22:33:44:55
```

#### IP4 Block
```csv
row_id,object_type,action,config,name,cidr
3,ip4_block,create,Default,Private-Space,10.0.0.0/8
```

### Example: Complete Import

```csv
row_id,object_type,action,config,parent,name,cidr,address,mac
1,ip4_block,create,Default,,Private-10,10.0.0.0/8,,,
2,ip4_network,create,Default,/IPv4/10.0.0.0/8,Corp-HQ,10.1.0.0/16,,,
3,ip4_address,create,Default,,web-server-1,,10.1.0.10,00:11:22:33:44:55
4,ip4_address,create,Default,,db-server-1,,10.1.0.20,00:11:22:33:44:66
```

## Common Workflows

### Workflow 1: Initial Network Setup

```bash
# 1. Create a CSV with your network structure
cat > networks.csv << 'EOF'
row_id,object_type,action,config,parent,name,cidr
1,ip4_block,create,Default,,Corporate,10.0.0.0/8
2,ip4_network,create,Default,/IPv4/10.0.0.0/8,HQ-Network,10.1.0.0/16
3,ip4_network,create,Default,/IPv4/10.0.0.0/8,Branch-Network,10.2.0.0/16
EOF

# 2. Validate
bluecat-import validate networks.csv

# 3. Dry-run
bluecat-import apply networks.csv --dry-run

# 4. Execute
bluecat-import apply networks.csv
```

### Workflow 2: Bulk IP Assignment

```bash
# 1. Export existing network for reference
bluecat-import export existing.csv \
  --network 10.1.0.0/16 \
  --config-name Default

# 2. Create IPs CSV based on reference
cat > assign_ips.csv << 'EOF'
row_id,object_type,action,config,address,name,mac
1,ip4_address,create,Default,10.1.0.10,web-01,00:11:22:33:44:01
2,ip4_address,create,Default,10.1.0.11,web-02,00:11:22:33:44:02
3,ip4_address,create,Default,10.1.0.12,web-03,00:11:22:33:44:03
EOF

# 3. Apply
bluecat-import apply assign_ips.csv
```

### Workflow 3: Bulk Updates

```bash
# 1. Export current state
bluecat-import export current.csv \
  --network 10.1.0.0/16 \
  --config-name Default

# 2. Edit CSV (modify fields as needed)
# - Open current.csv in Excel or text editor
# - Update fields (names, UDFs, etc.)
# - Ensure action = "update" for existing resources
# - Save the file

# 3. Apply updates
bluecat-import apply current.csv --dry-run
bluecat-import apply current.csv
```

### Workflow 4: Cleanup with Rollback

```bash
# 1. Import resources
bluecat-import apply new_resources.csv

# 2. If something goes wrong, rollback
SESSION_ID="abc12345"  # From import output
bluecat-import rollback .changelogs/${SESSION_ID}_rollback.csv

# Or check status first
bluecat-import status $SESSION_ID
```

## Export Workflows

The export feature allows you to extract existing BlueCat resources into CSV format for editing and re-import. This is powerful for bulk updates, documentation, and environment migration.

### Export Workflow 1: Bulk Update UDFs

Update User-Defined Fields across many resources at once.

```bash
# Step 1: Export the network with all child resources
bluecat-import export network.csv \
  --network 10.1.0.0/16 \
  --config-name Default

# Output shows:
# Resources exported: 150
# UDFs discovered: 3
# UDF columns: udf_environment, udf_location, udf_owner

# Step 2: Edit the CSV file
# Open network.csv in Excel or a text editor
# - Filter to object_type = "ip4_address"
# - Update udf_owner column from "Old Team" to "New Team"
# - Save the file

# Step 3: Test the changes (dry-run)
bluecat-import apply network.csv --dry-run

# Review the diff output to verify changes

# Step 4: Apply the changes
bluecat-import apply network.csv

# Done! All addresses now have updated UDFs
```

### Export Workflow 2: Document Network Hierarchy

Create a backup and documentation of your network structure.

```bash
# Export entire block hierarchy
bluecat-import export datacenter-backup.csv \
  --block 12345

# This exports:
# - The block itself
# - All child blocks recursively
# - All child networks recursively
# - All IP addresses in all networks
# - All UDFs automatically

# For faster export without addresses:
bluecat-import export datacenter-structure.csv \
  --block 12345 \
  --no-addresses

# Keep this as documentation or backup
cp datacenter-backup.csv backups/datacenter-$(date +%Y%m%d).csv
```

### Export Workflow 3: Copy Network to Another Environment

Migrate a production network to development or test environment.

```bash
# Step 1: Export from production with action=create
bluecat-import export prod-network.csv \
  --network 10.1.0.0/16 \
  --config-name Production \
  --action create

# Step 2: Edit the CSV
# Open prod-network.csv
# - Change all "config" values from "Production" to "Development"
# - Optionally update udf_environment from "production" to "development"
# - Save the file

# Step 3: Import to development environment
bluecat-import apply prod-network.csv \
  --config dev-config.yaml \
  --dry-run

# Step 4: Execute if dry-run looks good
bluecat-import apply prod-network.csv \
  --config dev-config.yaml

# Network structure is now replicated in dev!
```

### Export Workflow 4: Audit DNS Zones

Export DNS zones for review and compliance checking.

```bash
# Export a zone with all records
bluecat-import export example-com.csv \
  --zone example.com \
  --view-id 100

# This exports:
# - The zone itself
# - All child zones (e.g., dev.example.com, staging.example.com)
# - All resource records (A, MX, CNAME, etc.)
# - All UDFs

# Review in spreadsheet
# - Look for duplicate records
# - Check TTL values
# - Verify ownership UDFs
# - Find stale records

# Make corrections and re-import
bluecat-import apply example-com.csv
```

### Export Workflow 5: Rename Networks in Bulk

Use export to rename many networks at once.

```bash
# Step 1: Export block (without addresses for speed)
bluecat-import export networks.csv \
  --block 12345 \
  --no-addresses

# Step 2: Edit network names
# Open networks.csv
# - Filter to object_type = "ip4_network"
# - Use find/replace to update naming convention
#   Example: "OLD-" → "NEW-"
# - Ensure action = "update"
# - Save the file

# Step 3: Apply the renames
bluecat-import apply networks.csv --dry-run
bluecat-import apply networks.csv

# All networks renamed!
```

### Export Workflow 6: Pre-Import Reference

Export existing resources before adding new ones to understand the current state.

```bash
# Export existing network as reference
bluecat-import export reference.csv \
  --network 10.1.0.0/16 \
  --config-name Default

# Review reference.csv to see:
# - Current IP address assignments
# - Existing UDF values
# - Network structure

# Create new IPs CSV based on reference
cat > new_ips.csv << 'EOF'
row_id,object_type,action,config,address,name,mac,udf_owner,udf_environment
1,ip4_address,create,Default,10.1.0.50,new-server-1,00:11:22:33:44:99,IT Team,production
2,ip4_address,create,Default,10.1.0.51,new-server-2,00:11:22:33:44:88,IT Team,production
EOF

# Apply new IPs
bluecat-import apply new_ips.csv
```

### Export Command Quick Reference

```bash
# Export network by CIDR
bluecat-import export output.csv \
  --network 10.1.0.0/16 \
  --config-name Default

# Export network by ID (faster, no config needed)
bluecat-import export output.csv \
  --network 12345

# Export network without children
bluecat-import export output.csv \
  --network 10.1.0.0/16 \
  --config-name Default \
  --no-children \
  --no-addresses

# Export block hierarchy
bluecat-import export output.csv \
  --block 12345

# Export block without addresses (faster)
bluecat-import export output.csv \
  --block 12345 \
  --no-addresses

# Export DNS zone by FQDN
bluecat-import export output.csv \
  --zone example.com \
  --view-id 100

# Export DNS zone by ID
bluecat-import export output.csv \
  --zone 54321

# Export zone without child zones
bluecat-import export output.csv \
  --zone example.com \
  --view-id 100 \
  --no-children

# Export with action=create for migration
bluecat-import export output.csv \
  --network 10.1.0.0/16 \
  --config-name Default \
  --action create
```

### Export Safety Features

The export command is designed to be safe:

1. **Scoped Export**: You MUST specify exactly what to export (network, block, or zone). You cannot accidentally export the entire database.

2. **Config Required for CIDR**: When using CIDR notation, you must specify `--config-name` or `--config-id` to avoid ambiguity.

3. **View Required for FQDN**: When using FQDN for zones, you must specify `--view-id` to avoid ambiguity.

4. **Automatic UDF Discovery**: All User-Defined Fields are automatically found and included as columns.

5. **Metadata Comments**: Exported CSV includes metadata about export date, resource count, and schema version.

### Export Tips

1. **Use IDs for Speed**: If you know the resource ID, use it instead of CIDR/FQDN for faster export.

2. **Skip Addresses for Large Exports**: Use `--no-addresses` when exporting large blocks to significantly speed up the export.

3. **Version Control**: Keep exported CSVs in git for change tracking:
   ```bash
   git add network-export.csv
   git commit -m "Network export before migration"
   ```

4. **Regular Backups**: Schedule periodic exports for documentation:
   ```bash
   bluecat-import export backups/network-$(date +%Y%m%d).csv \
     --network 10.1.0.0/16 \
     --config-name Default
   ```

5. **Excel Compatibility**: Exported CSVs work perfectly in Excel/LibreOffice. Save as "CSV UTF-8" when done editing.

## Advanced Features

### Checkpointing and Resume

If an import is interrupted, resume from the last checkpoint:

```bash
# Original import (interrupted)
bluecat-import apply large_import.csv

# Resume from checkpoint
bluecat-import apply large_import.csv --resume
```

### Orphan Detection

Detect resources in BAM not in your CSV (with strict scoping for safety):

```yaml
# config.yaml
policy:
  enable_orphan_detection: true
  safe_mode: true  # Orphans logged, not deleted
```

### Dry-Run with Reports

Test without making changes and generate a report:

```bash
bluecat-import apply changes.csv \
  --dry-run \
  --report

# View report
open .reports/<session-id>_report.html
```

### Configuration

Create a config file for repeated use:

```yaml
# config.yaml
bam:
  base_url: "https://bam.example.com"
  username: "admin"
  password: "${BAM_PASSWORD}"  # From environment
  verify_ssl: true

policy:
  max_concurrent_operations: 10
  update_mode: "upsert"  # create_only, upsert, strict
  safe_mode: false
  enable_orphan_detection: false
  auto_create_parents: true

logging:
  level: "INFO"
  log_file: "import.log"
  json_logs: false
```

Use it:

```bash
bluecat-import apply data.csv --config config.yaml
```

## Best Practices

### 1. Always Validate First

```bash
bluecat-import validate data.csv --strict
```

### 2. Test with Dry-Run

```bash
bluecat-import apply data.csv --dry-run
```

### 3. Use Descriptive row_id

```csv
row_id,object_type,action,...
web-server-1-ip,ip4_address,create,...
web-server-2-ip,ip4_address,create,...
```

### 4. Keep Backups

```bash
# Export before making changes
bluecat-import export backup_$(date +%Y%m%d).csv \
  --network 10.1.0.0/16 \
  --config-name Default
```

### 5. Use Version Control

```bash
# Track your CSV files in git
git add *.csv
git commit -m "Add new server IPs"
```

### 6. Start Small

Test with a small subset first:

```bash
# Create test CSV with 5-10 rows
head -11 large_import.csv > test.csv

# Test
bluecat-import apply test.csv --dry-run
```

### 7. Monitor Progress

```bash
# In another terminal
watch -n 2 'bluecat-import status <session-id>'
```

## Troubleshooting

### Issue: CSV Validation Fails

**Problem**: "Invalid CIDR notation"

**Solution**: Check CIDR format (e.g., `10.1.0.0/16` not `10.1.0.0-16`)

### Issue: Authentication Failed

**Problem**: "Invalid username or password"

**Solution**:
1. Check credentials in config or environment
2. Verify BAM URL is correct
3. Test with: `curl -k https://bam.example.com/api/v2/sessions`

### Issue: Rate Limiting

**Problem**: "Rate limit exceeded"

**Solution**: Adaptive throttling handles this automatically, but you can:
1. Reduce `max_concurrent_operations` in config
2. Wait for `Retry-After` period
3. Check throttle metrics in logs

### Issue: Dependency Errors

**Problem**: "Resource depends on non-existent parent"

**Solution**:
1. Enable auto-create: `auto_create_parents: true`
2. Or ensure parent resources are created first (check row order)

### Issue: Orphan Detection Too Aggressive

**Problem**: "Many orphans detected"

**Solution**:
1. Use `safe_mode: true` to log orphans without deleting
2. Review orphan list in report
3. Adjust scope to match CSV containers exactly

### Getting Help

1. Check logs: `tail -f import.log`
2. View session details: `bluecat-import status <session-id>`
3. Check history: `bluecat-import history --limit 20`
4. Review HTML report: `.reports/<session-id>_report.html`

## Example Scenarios

### Scenario 1: Initial Data Center Setup

```csv
# dc_setup.csv
row_id,object_type,action,config,parent,name,cidr,address,mac
# Layer 1: Create block
1,ip4_block,create,Default,,DC1-Block,172.16.0.0/12,,,

# Layer 2: Create networks
2,ip4_network,create,Default,/IPv4/172.16.0.0/12,DC1-Management,172.16.1.0/24,,,
3,ip4_network,create,Default,/IPv4/172.16.0.0/12,DC1-Servers,172.16.2.0/24,,,
4,ip4_network,create,Default,/IPv4/172.16.0.0/12,DC1-Storage,172.16.3.0/24,,,

# Layer 3: Assign IPs
5,ip4_address,create,Default,,gateway-1,,172.16.1.1,
6,ip4_address,create,Default,,dns-1,,172.16.1.10,
7,ip4_address,create,Default,,web-1,,172.16.2.10,00:11:22:33:44:01
8,ip4_address,create,Default,,web-2,,172.16.2.11,00:11:22:33:44:02
9,ip4_address,create,Default,,san-1,,172.16.3.10,00:11:22:33:44:10
```

Execute:
```bash
bluecat-import apply dc_setup.csv --config prod.yaml
```

### Scenario 2: Decommission Old Network

```csv
# decommission.csv
row_id,object_type,action,bam_id,verify_name
1,ip4_address,delete,123456,old-server-1
2,ip4_address,delete,123457,old-server-2
3,ip4_network,delete,789012,Old-Network
```

Execute:
```bash
bluecat-import apply decommission.csv --dry-run
bluecat-import apply decommission.csv
```

## Next Steps

- Review [ARCHITECTURE.md](ARCHITECTURE.md) for technical details
- Check [README.md](README.md) for API reference
- Explore example CSVs in `samples/`
- Read official BlueCat REST API v2 documentation

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review session reports and logs
3. Use `--dry-run` to test safely
4. Consult BlueCat API documentation
