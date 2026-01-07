# Performance Tuning Guide

The BlueCat CSV Importer is designed to handle large datasets efficiently. This guide covers how to tune the tool for maximum performance in different network environments.

## Quick Reference

| Goal | Flag/Setting | Impact | Recommended For |
|------|--------------|--------|-----------------|
| **Faster Pre-check** | `--bulk` | **10-50x Faster** validation | Large imports (>100 rows) |
| **Faster Import** | `bulk_threshold: 10` | **10x Faster** API calls | Default (don't change) |
| **Low Memory** | `--no-prefetch` | Reduced memory, slower speed | Systems with <1GB RAM |
| **Debug Speed** | `--no-cache` | Disables caching (Slowest) | Debugging only |

## 1. Bulk Validation (`--bulk`)

By default, `validate` runs offline checks. For deep validation against BAM, use `--bulk`.

- **On (Default > 50 rows)**: Checks for duplicates and parent existence using optimized bulk queries.
- **Off**: Offline syntax check only.

```bash
# Force enable for small files
bluecat-import validate small.csv --bulk

# Force disable for very large files (if BAM is slow)
bluecat-import validate huge.csv --no-bulk
```

## 2. Prefetching & Caching (`--prefetch`)

The importer analyzes your CSV relationships and pre-fetches dependencies (like Parent Blocks or Views) in a single batch before processing rows.

- **Default**: Enabled.
- **Benefit**: Reduces API round-trips by 90%+.
- **Cost**: Uses more memory to store the cache.

**When to disable:**
If you are running on a constrained container with strictly limited memory and importing massive datasets (100k+ rows), you might disable prefetch to trade speed for memory safety.

```bash
# Disable prefetch (slower, less memory)
bluecat-import apply data.csv --no-prefetch
```

## 3. Bulk Loading (Internal)

The system automatically switches to "Bulk Mode" for creation steps when creating multiple resources of the same type in the same parent.

- **Threshold**: Configurable via `config.yaml` (default: 10 items).
- **Mechanism**: Instead of 100 `create_network` calls, it sends 1 `bulk_create` call (if API supports) or uses parallel async workers.

## 4. Adaptive Throttling

The tool monitors BAM response times. If BAM starts responding slowly (latency increases), the tool automatically reduces concurrency to preventing overloading the server.

- **Initial Concurrency**: 10 parallel requests.
- **Min Concurrency**: 1 request.
- **Max Concurrency**: 50 requests.

## Best Practices for Large Imports (>10,000 rows)

1. **Split your files**: Process Networks in one file, then Addresses in another. This keeps the dependency graph simple.
2. **Use `--bulk` validation first**: Catch conflicts early.
3. **Monitor logs**: Look for "Throttling down" messages—this means BAM is struggling.
