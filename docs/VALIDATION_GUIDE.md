# Validation Guide

BlueCat CSV Importer provides two levels of validation to ensure your data is clean and safe before deployment.

## 1. Offline Validation (Syntax Check)

This runs automatically when you run `validate` or `apply`. It checks for errors that can be detected without connecting to BlueCat.

**Checks performed:**
- CSV format correctness
- Required columns present
- Value formats (CIDR, IP, MAC address)
- Data types (integers, booleans)
- Schema version compatibility

**Usage:**
```bash
# Basic check
bluecat-import validate my-network.csv

# Strict check (fail on warnings)
bluecat-import validate my-network.csv --strict
```

## 2. Online Bulk Validation (Pre-flight Check)

This is a powerful "Pre-flight" check that connects to BAM and verifies that your planned changes are valid in the current environment.

**Checks performed:**
- **Duplicate CIDRs**: Checks if networks/blocks you are creating already exist.
- **Duplicate Names**: Checks if zones/records you are creating already exist (partial support).
- **Parent Existence**: Verifies that parent configurations/views exist.

**Usage:**
```bash
# Explicitly enable bulk validation
bluecat-import validate my-network.csv --bulk --config prod.yaml

# Auto-enabled for large files (>50 rows)
bluecat-import validate large-import.csv --config prod.yaml
```

**Requirements:**
- You must provide authentication (env vars or `--config`) since it connects to the API.

### Smart Logic
- If your CSV has **> 50 rows**, Online Validation is automatically enabled (unless you pass `--no-bulk`).
- If your CSV is small, it defaults to Offline Validation only (unless you pass `--bulk`).

## Resolving Validation Errors

### "Network 10.0.0.0/24 already exists"
- **Cause**: You are trying to `create` a network that is already in BAM.
- **Fix**: Change the `action` column in your CSV from `create` to `update`, or delete the existing network in BAM if appropriate.

### "Configuration 'X' not found"
- **Cause**: The `config` column references a configuration name that doesn't exist in BAM.
- **Fix**: Check for typos in the configuration name.

## Best Practices
1. Always run `validate` before `apply`.
2. Use `--bulk` for any production change to catch conflicts early.
3. Fix all errors and warnings before proceeding.
