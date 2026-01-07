"""Unit tests for configuration management."""

from pathlib import Path

import pytest
import yaml

from src.importer.config import (
    BAMConfig,
    CacheConfig,
    CircuitBreakerConfig,
    ConflictResolution,
    FailurePolicy,
    ImporterConfig,
    LoggingConfig,
    OrphanAction,
    PolicyConfig,
    ThrottleConfig,
)


class TestPolicyConfig:
    """Test PolicyConfig dataclass."""

    def test_default_values(self):
        """Test default policy configuration values."""
        policy = PolicyConfig()

        # Auto-creation policies
        assert policy.auto_create_network is False
        assert policy.auto_create_zone is False
        assert policy.auto_create_view is False

        # DNS policies
        assert policy.create_dns is False
        assert policy.create_reverse_record is False
        assert policy.override_naming_policy is False

        # Execution policies
        assert policy.allow_partial_failures is True
        assert policy.failure_policy == FailurePolicy.FAIL_GROUP
        assert policy.safe_mode is True
        assert policy.update_mode == "upsert"
        assert policy.max_concurrent_operations == 10

        # Conflict resolution
        assert policy.allow_overwrite is False
        assert policy.conflict_resolution == ConflictResolution.FAIL

        # Orphan detection
        assert policy.enable_orphan_detection is False
        assert policy.orphan_action == OrphanAction.REPORT

        # Performance
        assert policy.initial_concurrency == 10
        assert policy.max_concurrency == 50
        assert policy.min_concurrency == 1
        assert policy.enable_adaptive_throttle is True

        # Observability
        assert policy.enable_metrics is False
        assert policy.metrics_backend == "prometheus"

    def test_custom_values(self):
        """Test policy configuration with custom values."""
        policy = PolicyConfig(
            auto_create_network=True,
            safe_mode=False,
            max_concurrent_operations=20,
            failure_policy=FailurePolicy.CONTINUE,
            conflict_resolution=ConflictResolution.OVERWRITE,
            orphan_action=OrphanAction.DELETE,
        )

        assert policy.auto_create_network is True
        assert policy.safe_mode is False
        assert policy.max_concurrent_operations == 20
        assert policy.failure_policy == FailurePolicy.CONTINUE
        assert policy.conflict_resolution == ConflictResolution.OVERWRITE
        assert policy.orphan_action == OrphanAction.DELETE


class TestBAMConfig:
    """Test BAMConfig dataclass."""

    def test_required_fields(self):
        """Test BAM configuration with required fields."""
        bam = BAMConfig(
            base_url="https://bam.example.com",
            username="admin",
            password="secret",
        )

        assert bam.base_url == "https://bam.example.com"
        assert bam.username == "admin"
        assert bam.password == "secret"
        assert bam.api_version == "v2"
        assert bam.timeout == 30
        assert bam.verify_ssl is True

    def test_custom_values(self):
        """Test BAM configuration with custom values."""
        bam = BAMConfig(
            base_url="https://bam.custom.com",
            username="user",
            password="pass",
            api_version="v1",
            timeout=60,
            verify_ssl=False,
        )

        assert bam.base_url == "https://bam.custom.com"
        assert bam.api_version == "v1"
        assert bam.timeout == 60
        assert bam.verify_ssl is False


class TestLoggingConfig:
    """Test LoggingConfig dataclass."""

    def test_default_values(self):
        """Test default logging configuration."""
        logging = LoggingConfig()

        assert logging.level == "INFO"
        assert logging.format == "json"
        assert logging.file is None

    def test_custom_values(self):
        """Test logging configuration with custom values."""
        log_path = Path("/var/log/importer.log")
        logging = LoggingConfig(
            level="DEBUG",
            format="text",
            file=log_path,
        )

        assert logging.level == "DEBUG"
        assert logging.format == "text"
        assert logging.file == log_path


class TestImporterConfig:
    """Test ImporterConfig dataclass and methods."""

    def test_default_values(self):
        """Test default importer configuration."""
        config = ImporterConfig()

        assert isinstance(config.policy, PolicyConfig)
        assert config.bam is None
        assert isinstance(config.logging, LoggingConfig)

    def test_from_file(self, tmp_path):
        """Test loading configuration from YAML file."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "policy": {
                "auto_create_network": True,
                "safe_mode": False,
                "max_concurrent_operations": 25,
                "failure_policy": "continue",
                "conflict_resolution": "overwrite",
                "orphan_action": "delete",
            },
            "bam": {
                "base_url": "https://bam.test.com",
                "username": "testuser",
                "password": "testpass",
                "api_version": "v2",
                "timeout": 45,
                "verify_ssl": False,
            },
            "logging": {
                "level": "DEBUG",
                "format": "text",
                "file": "/var/log/test.log",
            },
        }

        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        config = ImporterConfig.from_file(config_file)

        # Check policy
        assert config.policy.auto_create_network is True
        assert config.policy.safe_mode is False
        assert config.policy.max_concurrent_operations == 25
        assert config.policy.failure_policy == FailurePolicy.CONTINUE
        assert config.policy.conflict_resolution == ConflictResolution.OVERWRITE
        assert config.policy.orphan_action == OrphanAction.DELETE

        # Check BAM
        assert config.bam is not None
        assert config.bam.base_url == "https://bam.test.com"
        assert config.bam.username == "testuser"
        assert config.bam.password == "testpass"
        assert config.bam.api_version == "v2"
        assert config.bam.timeout == 45
        assert config.bam.verify_ssl is False

        # Check logging
        assert config.logging.level == "DEBUG"
        assert config.logging.format == "text"
        assert config.logging.file == Path("/var/log/test.log")

    def test_from_file_minimal(self, tmp_path):
        """Test loading minimal configuration from file."""
        config_file = tmp_path / "minimal.yaml"
        config_data = {
            "bam": {
                "base_url": "https://bam.minimal.com",
                "username": "user",
                "password": "pass",
            }
        }

        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        config = ImporterConfig.from_file(config_file)

        # Policy should have defaults
        assert isinstance(config.policy, PolicyConfig)
        assert config.policy.safe_mode is True

        # BAM should be configured
        assert config.bam is not None
        assert config.bam.base_url == "https://bam.minimal.com"

        # Logging should have defaults
        assert config.logging.level == "INFO"

    def test_from_file_no_bam(self, tmp_path):
        """Test loading configuration without BAM section."""
        config_file = tmp_path / "no_bam.yaml"
        config_data = {
            "policy": {
                "safe_mode": True,
            }
        }

        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        config = ImporterConfig.from_file(config_file)

        assert config.bam is None
        assert isinstance(config.policy, PolicyConfig)

    def test_from_file_malformed(self, tmp_path):
        """Test loading malformed YAML file."""
        config_file = tmp_path / "malformed.yaml"
        with open(config_file, "w") as f:
            f.write("key: [unclosed list")

        with pytest.raises(ValueError) as exc_info:
            ImporterConfig.from_file(config_file)

        assert "Invalid YAML in configuration file" in str(exc_info.value)

    def test_from_file_invalid_type(self, tmp_path):
        """Test loading YAML file that is not a dictionary."""
        config_file = tmp_path / "not_dict.yaml"
        # YAML list instead of dict
        with open(config_file, "w") as f:
            f.write("- item1\n- item2")

        with pytest.raises(ValueError) as exc_info:
            ImporterConfig.from_file(config_file)

        assert "Invalid configuration file structure" in str(exc_info.value)
        assert "expected dictionary" in str(exc_info.value)

    def test_to_file(self, tmp_path):
        """Test saving configuration to YAML file."""
        config = ImporterConfig(
            policy=PolicyConfig(
                auto_create_network=True,
                max_concurrent_operations=15,
                failure_policy=FailurePolicy.FAIL_FAST,
            ),
            bam=BAMConfig(
                base_url="https://bam.save.com",
                username="saveuser",
                password="savepass",
                timeout=40,
            ),
            logging=LoggingConfig(
                level="WARN",
                format="json",
                file=Path("/tmp/save.log"),
            ),
        )

        output_file = tmp_path / "output.yaml"
        config.to_file(output_file)

        assert output_file.exists()

        # Load and verify
        with open(output_file) as f:
            data = yaml.safe_load(f)

        assert data["policy"]["auto_create_network"] is True
        assert data["policy"]["max_concurrent_operations"] == 15
        assert data["policy"]["failure_policy"] == "fail_fast"

        assert data["bam"]["base_url"] == "https://bam.save.com"
        assert data["bam"]["username"] == "saveuser"
        assert data["bam"]["timeout"] == 40

        assert data["logging"]["level"] == "WARN"
        assert data["logging"]["format"] == "json"
        assert data["logging"]["file"] == "/tmp/save.log"

    def test_to_file_creates_directory(self, tmp_path):
        """Test that to_file creates parent directories if needed."""
        config = ImporterConfig(
            bam=BAMConfig(
                base_url="https://bam.test.com",
                username="user",
                password="pass",
            )
        )

        nested_path = tmp_path / "nested" / "dir" / "config.yaml"
        config.to_file(nested_path)

        assert nested_path.exists()
        assert nested_path.parent.exists()

    def test_from_env(self, monkeypatch):
        """Test loading configuration from environment variables."""
        monkeypatch.setenv("BAM_URL", "https://bam.env.com")
        monkeypatch.setenv("BAM_USERNAME", "envuser")
        monkeypatch.setenv("BAM_PASSWORD", "envpass")
        monkeypatch.setenv("BAM_API_VERSION", "v3")
        monkeypatch.setenv("LOG_LEVEL", "ERROR")
        monkeypatch.setenv("LOG_FORMAT", "text")

        config = ImporterConfig.from_env()

        assert config.bam is not None
        assert config.bam.base_url == "https://bam.env.com"
        assert config.bam.username == "envuser"
        assert config.bam.password == "envpass"
        assert config.bam.api_version == "v3"

        assert config.logging.level == "ERROR"
        assert config.logging.format == "text"

    def test_from_env_minimal(self, monkeypatch):
        """Test from_env with minimal environment variables."""
        # Clear any existing env vars
        for key in ["BAM_URL", "BAM_USERNAME", "BAM_PASSWORD", "LOG_LEVEL"]:
            monkeypatch.delenv(key, raising=False)

        config = ImporterConfig.from_env()

        assert config.bam is None
        assert config.logging.level == "INFO"
        assert config.logging.format == "json"

    def test_from_env_partial_bam(self, monkeypatch):
        """Test from_env with BAM_URL but missing credentials raises error."""
        # Clear any existing BAM credentials
        monkeypatch.delenv("BAM_USERNAME", raising=False)
        monkeypatch.delenv("BAM_PASSWORD", raising=False)
        monkeypatch.setenv("BAM_URL", "https://bam.partial.com")
        # No username or password

        # Should raise ValueError because BAM_URL is set but credentials are missing
        with pytest.raises(ValueError) as exc_info:
            ImporterConfig.from_env()

        assert "BAM_URL is set but required credentials are missing" in str(exc_info.value)
        assert "BAM_USERNAME" in str(exc_info.value)
        assert "BAM_PASSWORD" in str(exc_info.value)

    def test_roundtrip_save_load(self, tmp_path):
        """Test that configuration can be saved and loaded without data loss."""
        original = ImporterConfig(
            policy=PolicyConfig(
                auto_create_network=True,
                safe_mode=False,
                failure_policy=FailurePolicy.CONTINUE,
                conflict_resolution=ConflictResolution.MERGE,
            ),
            bam=BAMConfig(
                base_url="https://bam.roundtrip.com",
                username="roundtripuser",
                password="roundtrippass",
            ),
            logging=LoggingConfig(level="DEBUG"),
        )

        config_file = tmp_path / "roundtrip.yaml"
        original.to_file(config_file)

        loaded = ImporterConfig.from_file(config_file)

        assert loaded.policy.auto_create_network == original.policy.auto_create_network
        assert loaded.policy.safe_mode == original.policy.safe_mode
        assert loaded.policy.failure_policy == original.policy.failure_policy
        assert loaded.policy.conflict_resolution == original.policy.conflict_resolution

        assert loaded.bam.base_url == original.bam.base_url
        assert loaded.bam.username == original.bam.username
        assert loaded.bam.password == original.bam.password

        assert loaded.logging.level == original.logging.level


class TestEnums:
    """Test enum definitions."""

    def test_failure_policy_values(self):
        """Test FailurePolicy enum values."""
        assert FailurePolicy.FAIL_FAST == "fail_fast"
        assert FailurePolicy.FAIL_GROUP == "fail_group"
        assert FailurePolicy.CONTINUE == "continue"

    def test_conflict_resolution_values(self):
        """Test ConflictResolution enum values."""
        assert ConflictResolution.FAIL == "fail"
        assert ConflictResolution.OVERWRITE == "overwrite"
        assert ConflictResolution.MERGE == "merge"
        assert ConflictResolution.MANUAL == "manual"

    def test_orphan_action_values(self):
        """Test OrphanAction enum values."""
        assert OrphanAction.REPORT == "report"
        assert OrphanAction.DELETE == "delete"
        assert OrphanAction.IGNORE == "ignore"


class TestCircuitBreakerConfig:
    """Test CircuitBreakerConfig dataclass."""

    def test_default_values(self):
        """Test default circuit breaker configuration values."""
        config = CircuitBreakerConfig()

        assert config.failure_threshold == 15
        assert config.recovery_timeout == 30
        assert config.auth_failure_threshold == 5
        assert config.auth_circuit_timeout == 60

    def test_custom_values(self):
        """Test custom circuit breaker configuration values."""
        config = CircuitBreakerConfig(
            failure_threshold=25,
            recovery_timeout=45,
            auth_failure_threshold=3,
            auth_circuit_timeout=90,
        )

        assert config.failure_threshold == 25
        assert config.recovery_timeout == 45
        assert config.auth_failure_threshold == 3
        assert config.auth_circuit_timeout == 90


class TestCacheConfig:
    """Test CacheConfig dataclass."""

    def test_default_values(self):
        """Test default cache configuration values."""
        config = CacheConfig()

        assert config.ttl_seconds == 3600
        assert config.enabled is True
        assert config.directory == ".resolver_cache"
        assert config.view_cache_ttl == 300

    def test_custom_values(self):
        """Test custom cache configuration values."""
        config = CacheConfig(
            ttl_seconds=7200, enabled=False, directory="/tmp/cache", view_cache_ttl=600
        )

        assert config.ttl_seconds == 7200
        assert config.enabled is False
        assert config.directory == "/tmp/cache"
        assert config.view_cache_ttl == 600


class TestThrottleConfig:
    """Test ThrottleConfig dataclass."""

    def test_default_values(self):
        """Test default throttle configuration values."""
        config = ThrottleConfig()

        assert config.initial_concurrency == 10
        assert config.min_concurrency == 1
        assert config.max_concurrency == 50
        assert config.increase_factor == 1.2
        assert config.decrease_factor == 0.8
        assert config.rate_limit_decrease == 0.5
        assert config.adjustment_interval == 10.0
        assert config.healthy_error_rate == 0.01
        assert config.unhealthy_error_rate == 0.05
        assert config.high_latency_ms == 1000.0
        assert config.max_latency_samples == 100

    def test_custom_values(self):
        """Test custom throttle configuration values."""
        config = ThrottleConfig(
            initial_concurrency=20,
            min_concurrency=2,
            max_concurrency=100,
            increase_factor=1.5,
            decrease_factor=0.7,
            rate_limit_decrease=0.3,
            adjustment_interval=5.0,
            healthy_error_rate=0.02,
            unhealthy_error_rate=0.10,
            high_latency_ms=500.0,
            max_latency_samples=200,
        )

        assert config.initial_concurrency == 20
        assert config.min_concurrency == 2
        assert config.max_concurrency == 100
        assert config.increase_factor == 1.5
        assert config.decrease_factor == 0.7
        assert config.rate_limit_decrease == 0.3
        assert config.adjustment_interval == 5.0
        assert config.healthy_error_rate == 0.02
        assert config.unhealthy_error_rate == 0.10
        assert config.high_latency_ms == 500.0
        assert config.max_latency_samples == 200


class TestBAMConfigEnhanced:
    """Test enhanced BAMConfig with connection pool settings."""

    def test_default_values(self):
        """Test default BAM configuration values including connection limits."""
        config = BAMConfig(base_url="https://test.com", username="user", password="pass")

        assert config.base_url == "https://test.com"
        assert config.username == "user"
        assert config.password == "pass"
        assert config.api_version == "v2"
        assert config.timeout == 30
        assert config.verify_ssl is True
        assert config.max_connections == 50
        assert config.max_keepalive == 20

    def test_custom_connection_settings(self):
        """Test custom connection pool settings."""
        config = BAMConfig(
            base_url="https://test.com",
            username="user",
            password="pass",
            max_connections=100,
            max_keepalive=40,
        )

        assert config.max_connections == 100
        assert config.max_keepalive == 40


class TestImporterConfigEnhanced:
    """Test enhanced ImporterConfig with new configuration sections."""

    def test_default_new_configs(self):
        """Test default values for new configuration sections."""
        config = ImporterConfig()

        # Should have default instances of all new config classes
        assert isinstance(config.circuit_breaker, CircuitBreakerConfig)
        assert isinstance(config.cache, CacheConfig)
        assert isinstance(config.throttle, ThrottleConfig)

        # Check defaults are applied
        assert config.circuit_breaker.failure_threshold == 15
        assert config.cache.ttl_seconds == 3600
        assert config.throttle.initial_concurrency == 10

    def test_custom_new_configs(self):
        """Test custom values for new configuration sections."""
        circuit_breaker = CircuitBreakerConfig(failure_threshold=20)
        cache = CacheConfig(ttl_seconds=7200)
        throttle = ThrottleConfig(initial_concurrency=15)

        config = ImporterConfig(circuit_breaker=circuit_breaker, cache=cache, throttle=throttle)

        assert config.circuit_breaker.failure_threshold == 20
        assert config.cache.ttl_seconds == 7200
        assert config.throttle.initial_concurrency == 15
