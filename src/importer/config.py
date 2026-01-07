"""Configuration management for the BlueCat CSV Importer."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import yaml


class FailurePolicy(str, Enum):
    """Policy for handling failures during execution."""

    FAIL_FAST = "fail_fast"  # Stop on first error
    FAIL_GROUP = "fail_group"  # Stop if group fails (respect dependencies)
    CONTINUE = "continue"  # Continue despite errors


class ConflictResolution(str, Enum):
    """How to resolve conflicts when resource already exists."""

    FAIL = "fail"  # Raise error
    OVERWRITE = "overwrite"  # Overwrite existing
    MERGE = "merge"  # Merge changes
    MANUAL = "manual"  # Prompt user


class OrphanAction(str, Enum):
    """Action to take for orphaned resources."""

    REPORT = "report"  # Only report, don't delete
    DELETE = "delete"  # Delete orphans
    IGNORE = "ignore"  # Ignore orphans


@dataclass
class PolicyConfig:
    """
    Policy configuration for import operations.

    Controls behavior for auto-creation, conflicts, failures, etc.
    """

    # Auto-creation policies
    auto_create_network: bool = False
    auto_create_zone: bool = False
    auto_create_view: bool = False

    # DNS policies
    create_dns: bool = False
    create_reverse_record: bool = False
    override_naming_policy: bool = False

    # Execution policies
    allow_partial_failures: bool = True
    failure_policy: FailurePolicy = FailurePolicy.FAIL_GROUP
    safe_mode: bool = True  # Prevent destructive operations by default
    update_mode: str = "upsert"  # Options: "create_only", "upsert", "update_only"
    max_concurrent_operations: int = 10  # Maximum concurrent operations

    # Conflict resolution
    allow_overwrite: bool = False
    conflict_resolution: ConflictResolution = ConflictResolution.FAIL

    # Orphan detection
    enable_orphan_detection: bool = False
    orphan_action: OrphanAction = OrphanAction.REPORT

    # Performance
    initial_concurrency: int = 10
    max_concurrency: int = 50
    min_concurrency: int = 1
    enable_adaptive_throttle: bool = True

    # Observability
    enable_metrics: bool = False
    metrics_backend: str = "prometheus"


@dataclass
class BAMConfig:
    """BlueCat Address Manager connection configuration."""

    base_url: str
    username: str
    password: str
    api_version: str = "v2"
    timeout: int = 30
    verify_ssl: bool = True
    max_connections: int = 50  # Maximum total connections
    max_keepalive: int = 20  # Maximum keep-alive connections


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration for API resilience."""

    failure_threshold: int = 15  # Number of failures before opening circuit
    recovery_timeout: int = 30  # Seconds to wait before testing recovery
    auth_failure_threshold: int = 5  # Auth-specific circuit breaker threshold
    auth_circuit_timeout: int = 60  # Auth circuit recovery time


@dataclass
class CacheConfig:
    """Cache configuration for resolver and API responses."""

    ttl_seconds: int = 3600  # Cache TTL (1 hour)
    enabled: bool = True
    directory: str = ".resolver_cache"
    view_cache_ttl: int = 300  # In-memory view cache TTL (5 minutes)


@dataclass
class ThrottleConfig:
    """Adaptive throttle configuration."""

    initial_concurrency: int = 10
    min_concurrency: int = 1
    max_concurrency: int = 50
    increase_factor: float = 1.2  # 20% increase on success
    decrease_factor: float = 0.8  # 20% decrease on failure
    rate_limit_decrease: float = 0.5  # 50% decrease on rate limit
    adjustment_interval: float = 10.0  # Seconds between adjustments
    healthy_error_rate: float = 0.01  # < 1% errors
    unhealthy_error_rate: float = 0.05  # > 5% errors
    high_latency_ms: float = 1000.0  # > 1 second
    max_latency_samples: int = 100  # Maximum latency samples to track


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"
    file: Path | None = None


@dataclass
class ImporterConfig:
    """
    Complete configuration for the BlueCat CSV Importer.

    This combines all configuration sections.
    """

    policy: PolicyConfig = field(default_factory=PolicyConfig)
    bam: BAMConfig | None = None
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    throttle: ThrottleConfig = field(default_factory=ThrottleConfig)

    @classmethod
    def from_file(cls, config_path: Path) -> "ImporterConfig":
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to YAML config file

        Returns:
            ImporterConfig instance
        """
        try:
            with open(config_path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in configuration file {config_path}: {e}") from e

        if not isinstance(data, dict):
            raise ValueError(
                f"Invalid configuration file structure in {config_path}: "
                f"expected dictionary, got {type(data).__name__}"
            )

        # Parse each section
        policy_data = data.get("policy", {})
        policy = PolicyConfig(**policy_data)

        bam_data = data.get("bam")
        bam = BAMConfig(**bam_data) if bam_data else None

        logging_data = data.get("logging", {})
        # Convert file path string to Path if present
        if "file" in logging_data and logging_data["file"]:
            logging_data["file"] = Path(logging_data["file"])
        logging = LoggingConfig(**logging_data)

        # Parse new configuration sections
        circuit_breaker_data = data.get("circuit_breaker", {})
        circuit_breaker = CircuitBreakerConfig(**circuit_breaker_data)

        cache_data = data.get("cache", {})
        cache = CacheConfig(**cache_data)

        throttle_data = data.get("throttle", {})
        throttle = ThrottleConfig(**throttle_data)

        return cls(
            policy=policy,
            bam=bam,
            logging=logging,
            circuit_breaker=circuit_breaker,
            cache=cache,
            throttle=throttle,
        )

    def to_file(self, config_path: Path) -> None:
        """
        Save configuration to YAML file.

        Args:
            config_path: Path to save config file
        """
        data = {
            "policy": {
                k: v.value if isinstance(v, Enum) else v for k, v in self.policy.__dict__.items()
            },
            "bam": self.bam.__dict__ if self.bam else None,
            "logging": {
                k: str(v) if isinstance(v, Path) else v
                for k, v in self.logging.__dict__.items()
                if v is not None
            },
            "circuit_breaker": self.circuit_breaker.__dict__,
            "cache": self.cache.__dict__,
            "throttle": self.throttle.__dict__,
        }

        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    @classmethod
    def from_env(cls) -> "ImporterConfig":
        """
        Create configuration from environment variables.

        Environment variables:
            BAM_URL: BAM base URL
            BAM_USERNAME: BAM username
            BAM_PASSWORD: BAM password
            BAM_API_VERSION: BAM API version (default: v2)
            LOG_LEVEL: Logging level (default: INFO)

        Returns:
            ImporterConfig instance

        Raises:
            ValueError: If BAM_URL is set but required credentials are missing
        """
        import os

        bam_config = None
        bam_url = os.getenv("BAM_URL")
        if bam_url:
            # Validate required credentials when BAM_URL is set
            username = os.environ.get("BAM_USERNAME", "")
            password = os.environ.get("BAM_PASSWORD", "")

            missing_creds = []
            if not username:
                missing_creds.append("BAM_USERNAME")
            if not password:
                missing_creds.append("BAM_PASSWORD")

            if missing_creds:
                raise ValueError(
                    f"BAM_URL is set but required credentials are missing: {', '.join(missing_creds)}. "
                    f"Please set all required environment variables for BAM authentication."
                )

            # Parse verify_ssl from env (default True, set to 'false' to disable)
            verify_ssl_str = os.environ.get("BAM_VERIFY_SSL", "true").lower()
            verify_ssl = verify_ssl_str not in ("false", "0", "no", "off")

            bam_config = BAMConfig(
                base_url=bam_url,
                username=username,
                password=password,
                api_version=os.environ.get("BAM_API_VERSION", "v2"),
                verify_ssl=verify_ssl,
                max_connections=int(os.environ.get("BAM_MAX_CONNECTIONS", "50")),
                max_keepalive=int(os.environ.get("BAM_MAX_KEEPALIVE", "20")),
            )

        logging_config = LoggingConfig(
            level=os.environ.get("LOG_LEVEL", "INFO"),
            format=os.environ.get("LOG_FORMAT", "json"),
        )

        return cls(
            policy=PolicyConfig(),
            bam=bam_config,
            logging=logging_config,
            circuit_breaker=CircuitBreakerConfig(),
            cache=CacheConfig(),
            throttle=ThrottleConfig(),
        )


def load_config(config_file: Path | None = None) -> ImporterConfig:
    """
    Load configuration from file or environment variables.

    Args:
        config_file: Optional path to YAML config file

    Returns:
        ImporterConfig instance

    Raises:
        FileNotFoundError: If config_file is specified but doesn't exist
    """
    if config_file:
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        return ImporterConfig.from_file(config_file)
    return ImporterConfig.from_env()
