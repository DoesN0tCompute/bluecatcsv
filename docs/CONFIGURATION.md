# Configuration Guide

**Last Updated:** 2025-12-08 | **Version:** 0.3.0

This guide explains all configuration options for the BlueCat CSV Importer, with practical examples for different scenarios.

## Table of Contents

1. [Configuration Methods](#configuration-methods)
2. [Core Configuration](#core-configuration)
3. [BAM Client Configuration](#bam-client-configuration)
4. [Policy Configuration](#policy-configuration)
5. [Performance Configuration](#performance-configuration)
6. [Throttling Configuration](#throttling-configuration)
7. [Observability Configuration](#observability-configuration)
8. [Environment Variables](#environment-variables)
9. [Configuration Examples](#configuration-examples)

## Configuration Methods

The importer supports multiple configuration methods, applied in the following priority order:

1. **Command-line flags** (highest priority)
2. **Environment variables**
3. **Configuration file** (YAML)
4. **Default values** (lowest priority)

### Configuration File Structure

Create a `config.yaml` file in your project root or specify with `--config`:

```yaml
# config.yaml - Complete example configuration
bam:
  # BlueCat server connection
  base_url: "https://bam.example.com"
  username: "admin"
  password: "${BAM_PASSWORD}"  # Environment variable substitution
  verify_ssl: true
  timeout: 30.0

policy:
  # Import behavior
  safe_mode: true
  max_concurrent_operations: 20
  failure_policy: "fail_group"
  conflict_resolution: "error"

performance:
  # Performance tuning
  cache_size: 10000
  batch_size: 100
  checkpoint_interval: 1000
  memory_limit: "1GB"

throttling:
  # Rate limiting
  enabled: true
  target_latency: 200
  max_increase_rate: 0.2
  max_decrease_rate: 0.5

observability:
  # Logging and metrics
  logging:
    level: "INFO"
    format: "text"
    file: "logs/importer.log"
  metrics:
    enabled: true
    port: 8080
```

## Core Configuration

### BAM Client Settings

```yaml
bam:
  # Server connection
  base_url: "https://bam.example.com"      # Required
  username: "admin"                        # Required
  password: "secret"                       # Required (or via env var)
  api_version: "v2"                        # Default: v2

  # SSL settings
  verify_ssl: true                         # Default: true
  ca_cert_path: "/path/to/ca.pem"          # Optional

  # Timeouts (seconds)
  timeout: 30.0                            # Default: 30.0
  connect_timeout: 10.0                    # Default: 10.0
  read_timeout: 20.0                       # Default: 20.0

  # Session management
  session_timeout: 1800                    # Default: 1800 (30 minutes)
  auto_renew: true                         # Default: true

  # Retry settings
  retry_attempts: 3                        # Default: 3
  retry_delay: 1.0                         # Default: 1.0 seconds
  retry_backoff: 2.0                       # Default: 2.0 (multiplier)
```

### Policy Settings

```yaml
policy:
  # Safety settings
  safe_mode: true                          # Default: true
  allow_dangerous_operations: false       # Default: false

  # Concurrency
  max_concurrent_operations: 20           # Default: 20
  operation_timeout: 60.0                 # Default: 60.0 seconds

  # Failure handling
  failure_policy: "fail_group"            # Options: continue, stop, fail_group
  orphan_action: "error"                  # Options: error, skip, create_parent

  # Conflict resolution
  conflict_resolution: "error"            # Options: error, update, skip

  # Checkpointing
  checkpoint_interval: 1000              # Default: 1000
  checkpoint_dir: ".changelogs"           # Default: .changelogs

  # Validation
  strict_validation: true                 # Default: true
  validate_dependencies: true             # Default: true
```

## Performance Configuration

```yaml
performance:
  # Caching
  cache_size: 10000                       # Number of resources to cache
  cache_ttl: 3600                         # TTL in seconds (1 hour)

  # Batching
  batch_size: 100                         # Operations per batch
  batch_timeout: 5.0                      # Max wait for full batch

  # Memory management
  memory_limit: "1GB"                     # Max memory usage
  streaming: false                        # Enable streaming for large files

  # Concurrency
  worker_pool_size: 10                    # Number of worker threads
  queue_size: 1000                        # Operation queue size

  # Optimization
  async_resolution: true                  # Resolve dependencies async
  prefetch_enabled: true                  # Prefetch likely resources
  bulk_operations: true                   # Use bulk APIs when possible
```

## Throttling Configuration

```yaml
throttling:
  # Adaptive throttling
  enabled: true                           # Default: true
  target_latency: 200                     # Target response time (ms)
  min_latency: 50                         # Minimum acceptable latency (ms)
  max_latency: 1000                       # Maximum acceptable latency (ms)

  # Rate adjustment
  max_increase_rate: 0.2                  # Max 20% increase per adjustment
  max_decrease_rate: 0.5                  # Max 50% decrease per adjustment
  adjustment_interval: 10                 # Adjust every 10 seconds

  # Circuit breaker
  circuit_breaker_threshold: 10           # Errors before breaking
  circuit_breaker_timeout: 60             # Seconds to wait before retry

  # Rate limiting
  requests_per_second: 100                # Max requests per second
  burst_size: 20                          # Burst capacity
```

## Observability Configuration

```yaml
observability:
  # Logging configuration
  logging:
    level: "INFO"                          # DEBUG, INFO, WARNING, ERROR
    format: "json"                         # text, json, structured
    file: "logs/importer.log"              # Log file path
    max_size: "100MB"                      # Max log file size
    backup_count: 5                        # Number of backup logs
    audit: true                            # Enable audit logging
    audit_file: "logs/audit.log"

  # Metrics configuration
  metrics:
    enabled: true                          # Enable metrics endpoint
    port: 8080                             # Metrics port
    path: "/metrics"                       # Metrics endpoint path
    format: "prometheus"                   # prometheus, json

    # Custom metrics
    export_detailed_metrics: true          # Export per-resource-type metrics
    export_latency_histograms: true        # Export latency histograms
    export_error_counters: true            # Export error counters

  # Reporting
  reporting:
    generate_html: true                    # Generate HTML report
    generate_json: true                    # Generate JSON report
    output_dir: "reports"                  # Report output directory
    include_diffs: true                    # Include before/after diffs

  # Tracing
  tracing:
    enabled: false                         # Enable distributed tracing
    jaeger_endpoint: "http://localhost:14268/api/traces"
    sample_rate: 0.1                       # 10% sampling
```

## Environment Variables

All configuration can be overridden with environment variables. Use the `BAM_` prefix:

```bash
# Connection
export BAM_URL="https://bam.example.com"
export BAM_USERNAME="admin"
export BAM_PASSWORD="secret"

# SSL
export BAM_VERIFY_SSL="false"

# Performance
export BAM_MAX_CONCURRENT="50"
export BAM_CACHE_SIZE="20000"

# Logging
export BAM_LOG_LEVEL="DEBUG"
export BAM_LOG_FILE="debug.log"

# Policy
export BAM_SAFE_MODE="false"
export BAM_FAILURE_POLICY="continue"
```

### Special Environment Variables

```bash
# Proxy settings
export HTTP_PROXY="http://proxy.company.com:8080"
export HTTPS_PROXY="https://proxy.company.com:8080"
export NO_PROXY="localhost,127.0.0.1"

# Debug settings
export DEBUG="true"
export PROFILE="true"

# Configuration override
export BAM_CONFIG_FILE="/path/to/config.yaml"
export BAM_CONFIG_SECTION="production"
```

## Configuration Examples

### Development Configuration

```yaml
# config-dev.yaml
bam:
  base_url: "https://bam-dev.company.com"
  username: "${BAM_DEV_USER}"
  password: "${BAM_DEV_PASS}"
  verify_ssl: false

policy:
  safe_mode: true
  max_concurrent_operations: 5
  failure_policy: "fail_group"

observability:
  logging:
    level: "DEBUG"
    format: "text"
  metrics:
    enabled: false
```

### Production Configuration

```yaml
# config-prod.yaml
bam:
  base_url: "https://bam.company.com"
  username: "${BAM_PROD_USER}"
  password: "${BAM_PROD_PASS}"
  verify_ssl: true
  timeout: 60.0

policy:
  safe_mode: true
  max_concurrent_operations: 50
  failure_policy: "continue"
  checkpoint_interval: 500

performance:
  cache_size: 50000
  batch_size: 500
  memory_limit: "4GB"

throttling:
  enabled: true
  target_latency: 500
  requests_per_second: 200

observability:
  logging:
    level: "INFO"
    format: "json"
    audit: true
  metrics:
    enabled: true
    port: 8080
  reporting:
    generate_html: true
    output_dir: "/var/log/bluecat/reports"
```

### High Throughput Configuration

```yaml
# config-high-throughput.yaml
policy:
  max_concurrent_operations: 100
  operation_timeout: 120.0
  failure_policy: "continue"

performance:
  cache_size: 100000
  batch_size: 1000
  streaming: true
  worker_pool_size: 20
  queue_size: 5000

throttling:
  enabled: true
  target_latency: 1000
  requests_per_second: 500
  burst_size: 100
```

### Resource Constrained Configuration

```yaml
# config-low-memory.yaml
performance:
  cache_size: 1000
  batch_size: 10
  memory_limit: "512MB"
  streaming: true

policy:
  max_concurrent_operations: 5
  checkpoint_interval: 50

throttling:
  enabled: true
  target_latency: 100
  requests_per_second: 20
```

### Secure Configuration

```yaml
# config-secure.yaml
bam:
  base_url: "https://bam.company.com"
  username: "${BAM_USER}"
  password: "${BAM_PASS}"
  verify_ssl: true
  ca_cert_path: "/etc/ssl/certs/company-ca.pem"

policy:
  safe_mode: true
  allow_dangerous_operations: false
  strict_validation: true

observability:
  logging:
    level: "INFO"
    format: "json"
    audit: true
    audit_file: "/var/log/bluecat/audit.log"
    file: "/var/log/bluecat/importer.log"
    max_size: "50MB"
    backup_count: 10
```

## Advanced Configuration

### Custom Conflict Handlers

```yaml
policy:
  conflict_resolution: "custom"
  custom_handlers:
    ip4_network: "merge_networks"
    dns_zone: "zone_versioning"
```

### Conditional Configuration

```yaml
# Conditional based on environment
{{ if eq .Environment "production" }}
policy:
  safe_mode: true
  max_concurrent_operations: 20
{{ else }}
policy:
  safe_mode: false
  max_concurrent_operations: 50
{{ end }}
```

### Template Variables

```yaml
# Using template variables
bam:
  base_url: "{{ .BamURL }}"
  username: "{{ .Username }}"

policy:
  max_concurrent_operations: {{ .Concurrency }}
```

## Configuration Validation

### Validate Configuration

```bash
# Check configuration syntax
bluecat-import config validate

# Test connection with current config
bluecat-import self-test --config config.yaml

# Show active configuration
bluecat-import version --show-config
```

### Common Configuration Issues

1. **SSL Certificate Errors**:
   ```yaml
   bam:
     verify_ssl: false  # For testing only
     # Or provide valid CA certificate
     ca_cert_path: "/path/to/ca.pem"
   ```

2. **Timeout Issues**:
   ```yaml
   bam:
     timeout: 60.0
     connect_timeout: 15.0
     read_timeout: 45.0
   ```

3. **Memory Issues**:
   ```yaml
   performance:
     memory_limit: "2GB"
     streaming: true
     batch_size: 50
   ```

4. **Rate Limiting**:
   ```yaml
   throttling:
     enabled: true
     target_latency: 500
     requests_per_second: 50
   ```

## Configuration Best Practices

1. **Never hardcode credentials** - Always use environment variables or secret management
2. **Use different configs per environment** - Dev, staging, production
3. **Enable audit logging in production** - For compliance and debugging
4. **Monitor resource usage** - Adjust based on actual performance
5. **Test configuration changes** - Validate before applying to production
6. **Document custom settings** - Keep README with configuration decisions
7. **Version control config** - But exclude secrets with .gitignore
8. **Use configuration validation** - Catch errors early

### Example .gitignore

```gitignore
# Exclude sensitive configurations
config-prod.yaml
config-*.secret.yaml
.secrets/
.env

# Keep templates
config-*.template.yaml
```

### Template Configuration

```yaml
# config.template.yaml
bam:
  base_url: "${BAM_URL}"
  username: "${BAM_USERNAME}"
  password: "${BAM_PASSWORD}"

# Create .env file:
# BAM_URL=https://bam.example.com
# BAM_USERNAME=admin
# BAM_PASSWORD=changeme
```

## CLI Debug Flags

The following CLI flags are available for debugging and enhanced visibility:

### Verbosity Levels

- `--verbose`: Enable detailed output with step-by-step progress
- `--debug`: Enable debug-level tracing with maximum detail

### Visualization Flags

- `--show-plan`: Preview the execution order of operations after dependency resolution
- `--show-deps <file>`: Output dependency graph in DOT format for Graphviz visualization

### Example Usage

```bash
# Basic verbose import
bluecat-import apply data.csv --verbose

# Debug mode with maximum detail
bluecat-import apply data.csv --debug

# Preview execution plan
bluecat-import apply data.csv --show-plan

# Generate dependency graph
bluecat-import apply data.csv --show-deps > deps.dot

# Convert to PNG (requires Graphviz)
dot -Tpng deps.dot -o deps.png

# Combine multiple flags
bluecat-import apply data.csv --dry-run --show-plan --verbose
```

These flags are particularly useful for:
- Troubleshooting complex dependency chains
- Understanding execution order before running imports
- Debugging import failures
- Creating documentation and diagrams for review