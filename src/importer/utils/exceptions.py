"""Custom exceptions for the BlueCat CSV Importer.

Exception Hierarchy:
-------------------
ImporterError (base)
├── ValidationError
│   ├── CSVValidationError      # Malformed CSV, missing columns, invalid values
│   └── SchemaValidationError   # Pydantic model validation failures
├── ResourceNotFoundError       # BAM resource lookup failed (GET 404)
├── PendingCreateError          # Deferred resource not yet created
├── CyclicDependencyError       # Circular dependency in operation graph
├── DeferredResolutionError     # Parent resource creation failed
└── BAMAPIError (base for API errors)
    ├── ResourceAlreadyExistsError  # HTTP 409 Conflict
    ├── BAMRateLimitError           # HTTP 429 Too Many Requests
    └── BAMAuthenticationError      # HTTP 401 Unauthorized

Usage Guidelines:
----------------
1. Catch specific exceptions for specific handling:
   - BAMRateLimitError: Wait and retry
   - ResourceAlreadyExistsError: Check if idempotent update is possible
   - ResourceNotFoundError: Mark operation as failed, skip dependents

2. Use ImporterError as catch-all for importer-specific errors

3. Let httpx errors (NetworkError, TimeoutException) bubble up for retry logic

4. Include context in exceptions:
   - Row ID for CSV-related errors
   - Resource type and identifier for BAM errors
   - Original exception when wrapping errors

Error Recovery Strategy:
-----------------------
The executor handles errors by:
1. Logging the error with full context
2. Recording in changelog for rollback generation
3. Skipping dependent operations (cascade skip)
4. Continuing with independent operations
5. Reporting summary at completion
"""


class ImporterError(Exception):
    """Base exception for all importer errors."""

    pass


class ValidationError(ImporterError):
    """Raised when validation fails."""

    def __init__(
        self,
        message: str,
        line_number: int | None = None,
        original_error: Exception | None = None,
    ) -> None:
        """
        Initialize ValidationError.

        Args:
            message: Error message.
            line_number: Optional line number where error occurred.
            original_error: Optional original exception that caused this error.
        """
        super().__init__(message)
        self.line_number = line_number
        self.original_error = original_error


class CSVValidationError(ValidationError):
    """Raised when CSV validation fails."""

    def __str__(self) -> str:
        """
        Return string representation with line number if available.

        Returns:
            str: Error message prefixed with line number if set.
        """
        if self.line_number:
            return f"Line {self.line_number}: {self.args[0]}"
        return str(self.args[0]) if self.args else "CSV validation error"


class SchemaValidationError(ValidationError):
    """Raised when schema validation fails."""

    pass


class ResourceNotFoundError(ImporterError):
    """Raised when a BAM resource cannot be found."""

    def __init__(self, resource_type: str, identifier: str) -> None:
        """
        Initialize ResourceNotFoundError.

        Args:
            resource_type: Type of resource that wasn't found.
            identifier: Identifier used to search for the resource.
        """
        super().__init__(f"{resource_type} not found: {identifier}")
        self.resource_type = resource_type
        self.identifier = identifier


class PendingCreateError(ImporterError):
    """Raised when trying to resolve a resource that is pending creation."""

    def __init__(self, path: str, row_id: str) -> None:
        """
        Initialize PendingCreateError.

        Args:
            path: Path that is pending creation.
            row_id: Row ID that will create the path.
        """
        super().__init__(f"Path {path} is pending creation (row {row_id})")
        self.path = path
        self.row_id = row_id


class CyclicDependencyError(ImporterError):
    """
    Raised when circular dependencies are detected in the resource graph.

    Example cycles:
    1. Network A requires Network B, Network B requires Network A
    2. Host Record A points to Host Record B as its CNAME target,
       but Host Record B also points to Host Record A
    3. Address in Network A depends on DHCP service in Network B,
       but Network B's DHCP scope is limited by Network A

    The dependency planner will fail fast when cycles are detected to prevent
    infinite loops and deadlocks during execution.
    """

    def __init__(self, message: str, cycles: list[list[str]] | None = None) -> None:
        """
        Initialize CyclicDependencyError.

        Args:
            message: Error message.
            cycles: List of detected cycles, where each cycle is a list of resource IDs.
        """
        super().__init__(message)
        self.cycles = cycles or []


class BAMAPIError(ImporterError):
    """Base exception for BAM API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """
        Initialize BAMAPIError.

        Args:
            message: Error message.
            status_code: Optional HTTP status code.
        """
        super().__init__(message)
        self.status_code = status_code


class ResourceAlreadyExistsError(BAMAPIError):
    """Raised when attempting to create a resource that already exists (409 Conflict)."""

    def __init__(self, message: str, resource_type: str | None = None) -> None:
        """
        Initialize ResourceAlreadyExistsError.

        Args:
            message: Error message from API.
            resource_type: Optional type of resource that already exists.
        """
        super().__init__(message, status_code=409)
        self.resource_type = resource_type


class BAMRateLimitError(BAMAPIError):
    """Raised when BAM API rate limit is hit."""

    def __init__(self, retry_after: int) -> None:
        """
        Initialize BAMRateLimitError.

        Args:
            retry_after: Seconds to wait before retrying.
        """
        super().__init__(f"Rate limit exceeded, retry after {retry_after}s", status_code=429)
        self.retry_after = retry_after


class BAMAuthenticationError(BAMAPIError):
    """Raised when BAM authentication fails."""

    def __init__(self, message: str = "Authentication failed") -> None:
        """
        Initialize BAMAuthenticationError.

        Args:
            message: Error message (default: "Authentication failed").
        """
        super().__init__(message, status_code=401)


class DeferredResolutionError(ImporterError):
    """
    Raised when deferred ID resolution fails during operation execution.

    This occurs when an operation requires a parent resource ID that was expected
    to be created by a previous operation, but that operation either failed or
    was skipped.

    Common Scenarios:
    1. Network creation depends on a block that failed to create
    2. Address creation depends on a network that was skipped due to parent failure
    3. DNS record depends on a zone that couldn't be resolved
    4. DHCP deployment role depends on a network that doesn't exist

    The dependency planner inserts placeholders for resources that will be created
    during the same batch. These placeholders are resolved just before execution.
    If resolution fails, we fail fast with a clear error message to help users
    understand the dependency chain.
    """

    def __init__(
        self,
        row_id: str | int,
        resource_type: str,
        deferred_key: str,
        deferred_value: str,
    ) -> None:
        """
        Initialize DeferredResolutionError.

        Args:
            row_id: Row ID of the operation that failed.
            resource_type: Type of the deferred resource (e.g., 'block', 'network', 'zone').
            deferred_key: The deferred placeholder key (e.g., '_deferred_block_cidr').
            deferred_value: The value that could not be resolved (e.g., CIDR or zone name).
        """
        message = (
            f"Critical Dependency Failure: Could not resolve deferred {resource_type} "
            f"'{deferred_value}' for row {row_id}. The parent {resource_type} creation "
            f"likely failed or was skipped."
        )
        super().__init__(message)
        self.row_id = row_id
        self.resource_type = resource_type
        self.deferred_key = deferred_key
        self.deferred_value = deferred_value
