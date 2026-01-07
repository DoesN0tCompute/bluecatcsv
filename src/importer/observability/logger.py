"""Structured logging configuration with custom verbosity levels.

DX-002: Adds four log levels:
- INFO (20): Summary only (default)
- VERBOSE (15): Operation-level detail
- DEBUG (10): Full trace including resolver cache hits
- TRACE (5): Everything (extremely verbose)
"""

import logging
import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import structlog

# Context variables for request tracing
_log_context: ContextVar[dict[str, Any]] = ContextVar("log_context", default={})

# DX-002: Custom log levels
TRACE = 5  # Below DEBUG, for extremely verbose output
VERBOSE = 15  # Between DEBUG and INFO, for operation-level detail

# Register custom levels with logging module
logging.addLevelName(TRACE, "TRACE")
logging.addLevelName(VERBOSE, "VERBOSE")


def trace(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    """Log at TRACE level (extremely verbose)."""
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kwargs)


def verbose(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    """Log at VERBOSE level (operation-level detail)."""
    if self.isEnabledFor(VERBOSE):
        self._log(VERBOSE, message, args, **kwargs)


# Add methods to Logger class
logging.Logger.trace = trace  # type: ignore
logging.Logger.verbose = verbose  # type: ignore


class LogContext:
    """
    Context manager for adding context to logs.

    Usage:
        with LogContext(request_id="123"):
            logger.info("Processing request")
    """

    def __init__(self, **kwargs: Any) -> None:
        """
        Initialize log context.

        Args:
            **kwargs: Key-value pairs to add to log context
        """
        self.new_context = kwargs
        self.token = None

    def __enter__(self) -> "LogContext":
        """Enter context and merge new values."""
        current = _log_context.get().copy()
        current.update(self.new_context)
        self.token = _log_context.set(current)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context and restore previous values."""
        if self.token:
            _log_context.reset(self.token)


def add_context(**kwargs: Any) -> None:
    """
    Add context to the current execution context globally.

    Args:
        **kwargs: Key-value pairs to add to log context
    """
    current = _log_context.get().copy()
    current.update(kwargs)
    _log_context.set(current)


def clear_context(key: str) -> None:
    """
    Remove a key from the current log context.

    Args:
        key: Key to remove
    """
    current = _log_context.get().copy()
    if key in current:
        del current[key]
        _log_context.set(current)


def clear_all_context() -> None:
    """Clear all context variables."""
    _log_context.set({})


def _context_processor(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """
    Structlog processor to inject context variables.

    Args:
        logger: Logger instance
        method_name: Logging method name
        event_dict: Event dictionary

    Returns:
        Updated event dictionary with context
    """
    context = _log_context.get()
    if context:
        event_dict.update(context)
    return event_dict


# DX-002: Log level mapping including custom levels
LOG_LEVELS = {
    "TRACE": TRACE,
    "DEBUG": logging.DEBUG,
    "VERBOSE": VERBOSE,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def get_log_level(level: str) -> int:
    """
    Get numeric log level from string.

    Args:
        level: Level name (TRACE, DEBUG, VERBOSE, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Numeric log level
    """
    return LOG_LEVELS.get(level.upper(), logging.INFO)


def configure_logging(
    level: str = "INFO",
    json_logs: bool = False,
    log_file: str | Path | None = None,
    log_filter: str | None = None,
) -> None:
    """
    Configure structured logging with custom verbosity levels.

    DX-002: Supports four levels:
    - INFO: Summary only (default)
    - VERBOSE: Operation-level detail
    - DEBUG: Full trace including resolver cache hits
    - TRACE: Everything (extremely verbose)

    Args:
        level: Logging level (TRACE, DEBUG, VERBOSE, INFO, WARNING, ERROR, CRITICAL)
        json_logs: Whether to output logs in JSON format
        log_file: Optional path to write logs to file
        log_filter: Comma-separated component names to filter (e.g., "resolver,executor")
    """
    # Parse level using custom mapping
    log_level = get_log_level(level)

    # Basic configuration for standard logging
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(file_path))

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=handlers,
        force=True,  # Force reconfiguration even if logging has been configured
    )
    # Also explicitly set root logger level (basicConfig may not update it)
    logging.getLogger().setLevel(log_level)

    # DX-002: Apply component filtering if specified
    if log_filter:
        components = [c.strip() for c in log_filter.split(",")]
        for name in logging.root.manager.loggerDict:
            logger = logging.getLogger(name)
            # Mute loggers that don't match filter
            if not any(comp in name for comp in components):
                logger.setLevel(logging.WARNING)

    # Structlog processors
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        _context_processor,
    ]

    if json_logs:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
