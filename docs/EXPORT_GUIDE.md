# BlueCat CSV Exporter - Complete Guide

**Last Updated:** 2025-12-08 | **Version:** 0.3.0

**The Idiot-Proof Guide to Exporting Networks and Zones**

This guide explains how to safely export networks, blocks, and DNS zones from BlueCat Address Manager, edit them, and re-import them.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Why Export?](#why-export)
3. [Safety First](#safety-first)
4. [How It Works](#how-it-works)
5. [Step-by-Step Examples](#step-by-step-examples)
7. [Advanced Filtering](#advanced-filtering)
8. [Common Scenarios](#common-scenarios)
9. [Troubleshooting](#troubleshooting)
10. [FAQs](#faqs)

## Quick Start

**The 3-Step Process:**

```bash
# Step 1: Export
bluecat-import export my-network.csv \
  --network 10.1.0.0/16 \
  --config-name Default

# Step 2: Edit the CSV file
# Open my-network.csv in Excel, LibreOffice, or text editor
# Make your changes (update UDFs, names, etc.)

# Step 3: Re-import
bluecat-import apply my-network.csv --dry-run  # Test first!
bluecat-import apply my-network.csv            # Do it for real
```

**That's it!** But read on to understand what you're doing.

## Why Export?

The export feature is designed for:

1. **Bulk UDF Updates** - Update User-Defined Fields across many resources at once
2. **Documentation** - Create backups and audit trails
3. **Environment Migration** - Copy networks/zones between prod/dev/test
4. **Bulk Renaming** - Rename multiple resources efficiently
5. **Data Cleanup** - Review and fix data quality issues

## Safety First

### The Export is Scoped (Not Full Database!)

**IMPORTANT:** The export command is designed to be **safe**. You CANNOT accidentally export your entire database.

You **MUST** specify exactly what to export:
- A specific network (by CIDR or ID)
- A specific block (by ID)
- A specific DNS zone (by FQDN or ID)

If you don't specify a scope, the command will fail with an error. This prevents accidents.

### Understanding the Scope

When you export a resource, you get:

**Network Export:**
```
Network 10.1.0.0/16
├── Child Network 10.1.1.0/24
│   ├── IP Address 10.1.1.10
│   ├── IP Address 10.1.1.11
│   └── ...
├── Child Network 10.1.2.0/24
│   └── ...
└── ...
```

**Block Export:**
```
Block 10.0.0.0/8
├── Child Block 10.1.0.0/16
│   ├── Network 10.1.1.0/24
│   │   ├── IP Address 10.1.1.10
│   │   └── ...
│   └── ...
└── ...
```

**Zone Export:**
```
Zone example.com
├── Resource Record www.example.com (A)
├── Resource Record mail.example.com (MX)
├── Child Zone dev.example.com
│   ├── Resource Record app.dev.example.com (A)
│   └── ...
└── ...
```

## How It Works

### The Export Process

1. **Connect to BAM** - Authenticate using your config file
2. **Fetch Resources** - Recursively fetch the resource and its children
3. **Discover UDFs** - Automatically find all User-Defined Fields
4. **Generate CSV** - Create a CSV file with all data

### The CSV Structure

```csv
# Exported from BlueCat Address Manager
# Export Date: 2025-12-02T10:30:00
# Total Resources: 150
# Schema Version: 3.0
row_id,object_type,action,bam_id,config,name,cidr,address,mac,udf_owner,udf_environment
1,ip4_network,update,12345,Default,Corp-Network,10.1.0.0/16,,,,,IT,production
2,ip4_address,update,12346,Default,web-server-1,,,10.1.0.10,00:11:22:33:44:55,Web Team,production
...
```

**Key Columns:**
- `row_id` - Sequential number for CSV ordering
- `object_type` - Type of resource (ip4_network, ip4_address, dns_zone, etc.)
- `action` - What to do on import (update or create)
- `bam_id` - BlueCat's internal ID (DO NOT CHANGE this!)
- `config` - Configuration name
- `name` - Resource name
- `cidr` - Network CIDR (for networks/blocks)
- `address` - IP address (for addresses)
- `udf_*` - User-Defined Fields (auto-discovered!)

### The Re-Import Process

When you run `bluecat-import apply network.csv`:

1. **Validate** - Check CSV format and data
2. **Diff** - Compare with current BAM state
3. **Plan** - Build execution plan with dependency order
4. **Execute** - Apply changes to BAM
5. **Log** - Record all changes for audit/rollback

## Step-by-Step Examples

### Example 1: Export a Network by CIDR

**Scenario:** You want to export network `10.1.0.0/16` and all its child resources.

```bash
# Export the network
bluecat-import export network.csv \
  --network 10.1.0.0/16 \
  --config-name Default

# Output:
# SUCCESS: Loading configuration...
# SUCCESS: Connecting to BAM...
# SUCCESS: Connected successfully!
# SUCCESS: Exporting network 10.1.0.0/16...
# SUCCESS: Writing CSV to network.csv...
#
# SUCCESS: Export completed!
# Resources exported: 150
# UDFs discovered: 3
# UDF columns: udf_environment, udf_location, udf_owner
# Output file: network.csv
```

**What You Got:**
- The network itself (`10.1.0.0/16`)
- All child networks (e.g., `10.1.1.0/24`, `10.1.2.0/24`)
- All IP addresses in all networks
- All UDFs for all resources

### Example 2: Export a Network by ID

**Scenario:** You know the network's BAM ID is `12345`.

```bash
# Export by ID (no config name needed!)
bluecat-import export network.csv \
  --network 12345

# Faster! No need to look up the network by CIDR
```

**When to use ID vs CIDR:**
- Use **ID** if you know it (faster, more precise)
- Use **CIDR** if you don't know the ID (more user-friendly)

### Example 3: Export Just the Network (No Children)

**Scenario:** You only want the network itself, not child networks or addresses.

```bash
# Export without children or addresses
bluecat-import export network.csv \
  --network 10.1.0.0/16 \
  --config-name Default \
  --no-children \
  --no-addresses

# Output:
# Resources exported: 1
# (Just the network, nothing else)
```

**Use case:** You want to update just the network's properties or UDFs, not everything inside it.

### Example 4: Export a Block Hierarchy

**Scenario:** Export an entire block and all its child blocks and networks.

```bash
# Export block (by ID)
bluecat-import export block.csv \
  --block 12345

# This gets:
# - The block
# - All child blocks
# - All child networks
# - All IP addresses
# - All UDFs
```

**Warning:** Block exports can be LARGE if you have many networks. Consider using `--no-addresses` if you only need network structure:

```bash
# Export block WITHOUT addresses (much faster!)
bluecat-import export block.csv \
  --block 12345 \
  --no-addresses
```

### Example 5: Export a DNS Zone

**Scenario:** Export a DNS zone and all its resource records.

```bash
# Export by FQDN (requires view ID)
bluecat-import export zone.csv \
  --zone example.com \
  --view-id 100

# This gets:
# - The zone
# - All child zones (e.g., dev.example.com)
# - All resource records (A, MX, CNAME, etc.)
# - All UDFs
```

**To find your view ID:**
1. Log into BlueCat Address Manager UI
2. Go to DNS → Views
3. Note the ID number for your view

**Export by zone ID (if you know it):**
```bash
bluecat-import export zone.csv \
  --zone 54321
```

### Example 6: Bulk Update UDFs

**Scenario:** You need to update the `udf_owner` field for all addresses in a network.

```bash
# Step 1: Export
bluecat-import export network.csv \
  --network 10.1.0.0/16 \
  --config-name Default

# Step 2: Edit CSV
# Open network.csv in Excel
# Find column "udf_owner"
# Update all rows where object_type = "ip4_address"
# Change from "Old Team" to "New Team"
# Save the file

# Step 3: Test the import (DRY RUN!)
bluecat-import apply network.csv --dry-run

# Review the output to see what will change

# Step 4: Import for real
bluecat-import apply network.csv

# Done! All addresses now have udf_owner = "New Team"
```

### Example 7: Copy Network to Another Environment

**Scenario:** Copy a production network to dev environment.

```bash
# Step 1: Export from production with action=create
bluecat-import export prod-network.csv \
  --network 10.1.0.0/16 \
  --config-name Production \
  --action create

# Step 2: Edit CSV
# Open prod-network.csv
# Change all "config" values from "Production" to "Development"
# Save the file

# Step 3: Import to dev
bluecat-import apply prod-network.csv \
  --config dev-config.yaml

# Done! Network is now in dev environment
```

**Key points:**
- Use `--action create` for exports you plan to import elsewhere
- Use `--action update` (default) for exports you plan to re-import to same place

## Advanced Filtering

The `export` command supports powerful filtering capabilities to extract surgical subsets of data. This turns the tool into a flexible reporting utility.

### Filtering Syntax
Use the `--filter` flag with BAM v2 syntax: `field:operator(value)` or `field:value` (for equality).

| Operator | Syntax | Example |
|----------|--------|---------|
| **Equals** | `field:val` | `name:MyNetwork` |
| **Not Equals** | `field:ne(val)` | `status:ne(ACTIVE)` |
| **Like** | `field:like(val)` | `name:like('Site-A*')` |
| **Contains** | `field:contains(val)` | `comments:contains(important)` |
| **Greater Than** | `field:gt(val)` | `row_id:gt(100)` |

### Examples

#### 1. Export Only Static IP Addresses
Export all addresses in a network, but ONLY the static ones:

```bash
bluecat-import export static-ips.csv \
  --network 10.1.0.0/16 \
  --config-name Default \
  --filter "state:STATIC"
```

#### 2. Export Specific UDF Values
Find all networks owned by "IT Dept":

```bash
bluecat-import export it-networks.csv \
  --block 12345 \
  --filter "udf_owner:like('IT*')"
```

#### 3. Limit Fields and Rows (Reporting Mode)
Generate a quick report of just names and IDs for the first 50 networks:

```bash
bluecat-import export report.csv \
  --block 12345 \
  --fields "id,name,cidr" \
  --limit 50 \
  --order-by "name asc" \
  --no-addresses
```

> [!TIP]
> **Filtering applies to the *contents* of your scope.**
> - If you export a **Network**, the filter applies to its child addresses.
> - If you export a **Block**, the filter applies to its child networks/blocks.
> - If you export a **Zone**, the filter applies to its resource records.

## Common Scenarios

### Scenario: "I Need to Update UDFs for 500 IP Addresses"

**Solution: Export → Edit → Import**

```bash
# 1. Export the network
bluecat-import export network.csv \
  --network 10.1.0.0/16 \
  --config-name Default

# 2. Open in Excel/LibreOffice
# - Filter to object_type = "ip4_address"
# - Update udf columns as needed
# - Save

# 3. Test import
bluecat-import apply network.csv --dry-run

# 4. Import
bluecat-import apply network.csv
```

### Scenario: "I Need to Rename All Networks in a Block"

**Solution: Export Block → Edit Names → Import**

```bash
# 1. Export (without addresses for speed)
bluecat-import export block.csv \
  --block 12345 \
  --no-addresses

# 2. Edit CSV
# - Update "name" column for all ip4_network rows
# - Use find/replace for bulk changes

# 3. Import
bluecat-import apply block.csv --dry-run
bluecat-import apply block.csv
```

### Scenario: "I Need to Audit What's in a Zone"

**Solution: Export and Review**

```bash
# Export
bluecat-import export zone-audit.csv \
  --zone example.com \
  --view-id 100

# Open zone-audit.csv in Excel
# Review all resource records
# Look for issues, duplicates, etc.
# Make changes if needed
# Re-import if you made changes
```

### Scenario: "I Want to Backup a Network Before Making Changes"

**Solution: Export for Backup**

```bash
# Export with date stamp
bluecat-import export backup-$(date +%Y%m%d).csv \
  --network 10.1.0.0/16 \
  --config-name Default

# File: backup-20251202.csv
# Keep this file safe - you can restore from it later
```

## Troubleshooting

### Error: "You must specify exactly ONE of: --network, --block, or --zone"

**Problem:** You didn't specify what to export, or you specified more than one scope.

**Solution:**
```bash
# Wrong - no scope
bluecat-import export output.csv

# Wrong - multiple scopes
bluecat-import export output.csv --network 10.1.0.0/16 --block 12345

# SUCCESS: Correct - exactly one scope
bluecat-import export output.csv --network 10.1.0.0/16 --config-name Default
```

### Error: "Either --config-id or --config-name is required"

**Problem:** You're using `--network` with a CIDR, but didn't specify which configuration.

**Solution:**
```bash
# Wrong - CIDR without config
bluecat-import export output.csv --network 10.1.0.0/16

# SUCCESS: Correct - CIDR with config name
bluecat-import export output.csv --network 10.1.0.0/16 --config-name Default

# SUCCESS: Also correct - CIDR with config ID
bluecat-import export output.csv --network 10.1.0.0/16 --config-id 100

# SUCCESS: Also correct - use ID instead of CIDR (no config needed)
bluecat-import export output.csv --network 12345
```

### Error: "--view-id is required when using --zone with FQDN"

**Problem:** You're using `--zone` with an FQDN, but didn't specify which view.

**Solution:**
```bash
# Wrong - FQDN without view
bluecat-import export output.csv --zone example.com

# SUCCESS: Correct - FQDN with view ID
bluecat-import export output.csv --zone example.com --view-id 100

# SUCCESS: Also correct - use zone ID instead (no view needed)
bluecat-import export output.csv --zone 54321
```

### Error: "ResourceNotFoundError: Network '10.1.0.0/16' not found"

**Problem:** The network doesn't exist in the specified configuration, or you have the wrong CIDR.

**Solution:**
1. Check the CIDR is correct
2. Check you're using the right configuration
3. Log into BAM UI and verify the network exists
4. Try using network ID instead of CIDR

### Warning: Export Takes Forever

**Problem:** You're exporting a large block with many addresses.

**Solution:** Use `--no-addresses` to skip IP address export:
```bash
bluecat-import export block.csv \
  --block 12345 \
  --no-addresses
```

This will export just the block and network structure, which is much faster.

## FAQs

### Q: Can I export my entire BlueCat database?

**A: No, and that's intentional.** The export is scoped to prevent accidents. You must specify exactly what to export. If you need everything, export multiple blocks/zones separately.

### Q: What if I don't know the network/block/zone ID?

**A: Use human-readable identifiers:**
- For networks: Use CIDR (e.g., `--network 10.1.0.0/16`)
- For zones: Use FQDN (e.g., `--zone example.com`)
- For blocks: You need the ID (look it up in BAM UI)

### Q: How do I find my configuration ID or view ID?

**A: Log into BlueCat Address Manager:**
1. For config ID: Administration → Configurations → Note the ID column
2. For view ID: DNS → Views → Note the ID column

Or use configuration/view names instead:
- `--config-name Default` instead of `--config-id 12345`
- View names are rarely used; view ID is simpler

### Q: What's the difference between --action create and --action update?

**A:**
- `update` (default): For editing existing resources and re-importing to the same place
- `create`: For exporting resources to import into a different environment

The `action` column in CSV tells the importer what to do:
- `update` = modify existing resource (using `bam_id`)
- `create` = create new resource (ignoring `bam_id`)

### Q: Can I edit the exported CSV in Excel?

**A: Yes!** The CSV works perfectly in:
- Microsoft Excel
- LibreOffice Calc
- Google Sheets
- Any text editor (VS Code, Notepad++, etc.)

**Tip:** Be careful with Excel auto-formatting (it might change MAC addresses or IP addresses). Save as "CSV UTF-8" when done.

### Q: What UDFs get exported?

**A: ALL UDFs are automatically discovered!** You don't need to specify which ones. The exporter looks at all resources and finds every UDF that exists, then creates columns for them.

### Q: Can I add new UDFs during export/import?

**A: Not directly.** UDFs must be defined in BlueCat first. The export will include existing UDFs, and you can update their values. To add new UDFs, create them in BlueCat UI first, then export/import.

### Q: What happens if I change the bam_id column?

**A: DON'T CHANGE bam_id!** This is BlueCat's internal ID. Changing it will cause the import to fail or update the wrong resource. Only change values in other columns (name, cidr, UDFs, etc.).

### Q: Can I delete resources using export/import?

**A: Not directly with export.** Exported CSVs have `action=update` (or `create`). To delete resources, you need to manually create a CSV with `action=delete` rows.

### Q: How do I know what changed after import?

**A: Check the changelog!** After each import, a changelog file is created in `.changelogs/` with full before/after state. You can also use `bluecat-import history` to review past imports.

### Q: Can I roll back an import?

**A: Yes!** After each import, a rollback CSV is automatically generated in `.changelogs/`. You can apply this CSV to undo the import.

```bash
# Undo last import
bluecat-import rollback .changelogs/<session-id>_rollback.csv
```

### Q: What's the maximum number of resources I can export?

**A: There's no hard limit,** but practical limits exist:
- Large exports (>10,000 resources) may be slow
- CSV files can get very large
- Consider using `--no-addresses` or `--no-children` to reduce size

### Q: Can I export multiple networks at once?

**A: Not directly.** You must export one scope at a time. However, you can export a parent block that contains multiple networks:

```bash
# This exports all networks under the block
bluecat-import export block.csv --block 12345
```

Or run multiple export commands and combine CSVs manually (advanced).

---

## Need More Help?

- **Documentation:** See [README.md](README.md), [TUTORIAL.md](TUTORIAL.md), [ARCHITECTURE.md](ARCHITECTURE.md)
- **Examples:** Check `samples/` directory for example CSVs
- **Issues:** Report bugs at [GitHub Issues](https://github.com/DoesN0tCompute/bluecat-csv/issues)
