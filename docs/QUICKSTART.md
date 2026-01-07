# QuickStart Guide

**Last Updated:** 2025-12-08 | **Version:** 0.3.0

Get started with BlueCat CSV Importer in 5 minutes.

## Prerequisites

- **Python 3.11+** - Required runtime environment
- **BlueCat Address Manager** with REST API v2 access
- **API Credentials** with appropriate permissions for IP/DNS management
- **Network Access** to BlueCat server (HTTPS port 443 typically)
- **Operating System**: Linux, macOS, or Windows with WSL2

## Installation

```bash
# Clone repository
git clone <repo-url>
cd bluecat-csv

# Install with Poetry (recommended)
poetry install
poetry shell

# Or with pip
pip install -e .
```

## Configuration

Create a `.env` file with your BAM credentials:

```bash
# .env
BAM_URL=https://bam.example.com
BAM_USERNAME=admin
BAM_PASSWORD=your-password
```

Or create a `config.yaml`:

```yaml
bam:
  base_url: "https://bam.example.com"
  username: "admin"
  password: "${BAM_PASSWORD}"
  verify_ssl: true

policy:
  max_concurrent_operations: 10
  safe_mode: false
```

## Your First Import

### Step 1: Create a Simple CSV

Create `first_import.csv`:

```csv
row_id,object_type,action,config,name,cidr,address,mac
1,ip4_network,create,Default,Test-Network,192.168.100.0/24,,,
2,ip4_address,create,Default,test-server-1,,,192.168.100.10,00:11:22:33:44:55
```

### Step 2: Validate

```bash
bluecat-import validate first_import.csv
# Or if running directly:
python3 import.py validate first_import.csv
```

Expected output:
```
PASS: Validation successful!
  Total rows: 2

┌─ Summary by Object Type ─┐
│ Object Type     Count     │
├──────────────────────────┤
│ ip4_address     1         │
│ ip4_network     1         │
└──────────────────────────┘
```

### Step 3: Preview Execution Plan (Optional)

See the execution order and dependencies:

```bash
bluecat-import apply first_import.csv --show-plan
```

### Step 4: Dry-Run

Test without making changes:

```bash
bluecat-import apply first_import.csv --dry-run --verbose
# Or if running directly:
python3 import.py apply first_import.csv --dry-run --verbose
```

### Step 5: Execute

Perform the actual import:

```bash
bluecat-import apply first_import.csv
# Or if running directly:
python3 import.py apply first_import.csv
```

Output:
```
╭─────────────────────────────────╮
│ BlueCat CSV Import              │
│                                 │
│ Session ID: abc12345            │
│ CSV File: first_import.csv      │
│ Mode: EXECUTE                   │
│ Rollback: Enabled               │
│ Report: Enabled                 │
╰─────────────────────────────────╯

DONE: Parsed 2 rows
DONE: Connected to BAM
DONE: Loaded state for 2 resources
DONE: Diff computed
DONE: Dependency graph built
DONE: Execution plan created
DONE: Executed 2 operations

SUCCESS: Import completed successfully!

Duration: 2.34 seconds
Session ID: abc12345

Rollback CSV: rollbacks/abc12345_rollback.csv
To rollback: bluecat-import rollback rollbacks/abc12345_rollback.csv

Report: .reports/abc12345_report.html
```

## Next Steps

### Check Status

```bash
bluecat-import status abc12345
# Or if running directly:
python3 import.py status abc12345
```

### View History

```bash
bluecat-import history
# Or if running directly:
python3 import.py history
```

### Export Current State

```bash
bluecat-import export backup.csv --config-name Default
# Or if running directly:
python3 import.py export backup.csv --config-name Default
```

### Rollback if Needed

```bash
bluecat-import rollback rollbacks/abc12345_rollback.csv --dry-run
bluecat-import rollback rollbacks/abc12345_rollback.csv
# Or if running directly:
python3 import.py rollback rollbacks/abc12345_rollback.csv --dry-run
python3 import.py rollback rollbacks/abc12345_rollback.csv
```

## Common Commands

```bash
# Validate CSV
bluecat-import validate file.csv
# Or: python3 import.py validate file.csv

# Apply changes
bluecat-import apply file.csv
# Or: python3 import.py apply file.csv

# Apply with dry-run
bluecat-import apply file.csv --dry-run
# Or: python3 import.py apply file.csv --dry-run

# Apply with custom config
bluecat-import apply file.csv --config prod.yaml
# Or: python3 import.py apply file.csv --config prod.yaml

# Export BAM state
bluecat-import export backup.csv --config-name Default
# Or: python3 import.py export backup.csv --config-name Default

# Check session status
bluecat-import status <session-id>
# Or: python3 import.py status <session-id>

# View history
bluecat-import history --limit 20
# Or: python3 import.py history --limit 20

# Rollback changes
bluecat-import rollback rollback.csv
# Or: python3 import.py rollback rollback.csv

# Show version
bluecat-import version
# Or: python3 import.py version
```

## Key Features

**Core Capabilities:**
- CSV validation, BAM client, data models
- State management, diff engine, execution, rollback
- Metrics, reporting, progress bars, observability

**Features:**
- **Idempotent**: Safe to run multiple times
- **Resumable**: Checkpoint-based resume for interrupted imports
- **Rollback**: Automatic inverse CSV generation
- **Progress Tracking**: Real-time progress bars
- **Reports**: JSON/HTML reports with statistics
- **Safe Mode**: Test mode with orphan detection

## Examples

See `samples/` directory:
- `simple_import.csv` - Basic network and IP
- `complex_import.csv` - Multi-layer hierarchy
- `networks_only.csv` - Network creation only
- `tutorial_datacenter.csv` - Complete data center setup
- `location.csv` - Hierarchical location creation

### Location Creation Example

```csv
row_id,object_type,action,parent_location_code,code,name,description,latitude,longitude
1,location,create,US NYC,US NYC HQ,New York Headquarters,Main office,40.7128,-74.0060
2,location,create,US NYC HQ,US NYC HQ F1,Floor 1,First floor,40.7128,-74.0060
3,location,create,US LAX,US LAX Office,Los Angeles Office,West coast,34.0522,-118.2437
```

### Generic DNS Record Example

```csv
row_id,object_type,action,zone_path,name,type,record_data
1,generic_record,create,Default/example.com,caa,CAA,0,issue "letsencrypt.org"
2,generic_record,create,Default/example.com,dkey,DNSKEY,257 3 8 AwEAA...
3,generic_record,create,Default/example.com,sshfp,SSHFP,1 1 4321...
```

## Need Help?

1. **Tutorial**: See [TUTORIAL.md](TUTORIAL.md) for detailed guide
2. **Architecture**: See [ARCHITECTURE.md](ARCHITECTURE.md) for technical details
3. **Logs**: Check `import.log` for detailed logs
4. **Reports**: Open `.reports/<session-id>_report.html` in browser

## Pro Tips

**Parent-Child Creation**: You can now create parent and child resources in the same CSV file. The importer automatically detects dependencies and creates resources in the correct order.

Example:
```csv
row_id,object_type,action,config,name,cidr
1,ip4_block,create,Default,Corporate,10.0.0.0/8
2,ip4_network,create,Default,Office-LAN,10.1.0.0/24
```
The network will automatically wait for the block to be created first.

## Troubleshooting

**Authentication fails**: Check credentials in `.env` or config file
**CSV validation fails**: Run `validate` with `--strict` for detailed errors
**Rate limiting**: Adaptive throttling handles this automatically
**Dependency errors**: Enable `auto_create_parents: true` in config

## What's Next?

- Read the full [TUTORIAL.md](TUTORIAL.md)
- Review [ARCHITECTURE.md](ARCHITECTURE.md) for implementation details
- Check out example CSVs in `samples/`
- Configure for your environment with `config.yaml`
- Integrate with your workflow (git, CI/CD, monitoring)

Happy importing!
