"""CSV row models with Pydantic v2 discriminated unions."""

import re
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network
from typing import Annotated, Any, ClassVar, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


def strip_whitespace(v: Any) -> Any:
    """
    Strip whitespace from all string fields with intelligent empty string handling.

    CRITICAL: Excel, Google Sheets, and manual CSV editing often
    introduce trailing/leading spaces:
    - "10.1.1.1 " → breaks IP parsing
    - " Default" → breaks path resolution
    - "server1
    " → breaks name matching

    SMART EMPTY STRING HANDLING:
    - Required fields: empty string → None (will fail validation appropriately)
    - Optional fields: empty string → None (do not update)
    - Clearable fields: empty string → "" (clear the field in BAM API)

    The distinction is made by checking if the field name suggests it can be cleared.

    Args:
        v: The value to process.

    Returns:
        Any: The processed value with whitespace stripped.
    """
    if isinstance(v, str):
        stripped = v.strip()

        # Handle empty strings based on context
        if not stripped:
            # For empty strings, we need to determine if this should be None or ""
            # This is handled at the model level with custom validators
            return None
        return stripped
    return v


def strip_whitespace_preserve_empty(v: Any) -> Any:
    """
    Strip whitespace but preserve empty strings for clearable fields.

    This validator is used for fields where empty string has semantic meaning
    (e.g., clearing a description field vs leaving it unchanged).

    - "  hello  " → "hello"
    - "      " → "" (preserve empty for clearing)
    - "" → "" (preserve empty for clearing)

    Args:
        v: The value to process.

    Returns:
        Any: The processed value.
    """
    if isinstance(v, str):
        return v.strip()
    return v


def normalize_dns_record_name(v: Any) -> str:
    """
    Normalize DNS record name, handling apex record representations.

    Zone apex records can be represented as:
    - Empty string "" → normalized to "@"
    - "@" → preserved as "@"
    - None → normalized to "@"
    - Normal name (e.g., "www") → preserved

    This ensures consistent handling of apex records across the codebase.

    Args:
        v: The value to process.

    Returns:
        str: Normalized DNS record name.
    """
    if v is None or v == "":
        # Empty or None means apex record
        return "@"
    if isinstance(v, str):
        stripped = v.strip()
        if not stripped:
            return "@"
        return stripped
    return str(v)


def validate_name_encoding(v: Any) -> Any:
    """
    Validate that name fields don't contain BAM-incompatible characters.

    EDGE-008: Resource names with Unicode are allowed, but control characters
    (ASCII < 32) and null bytes are rejected as they can cause API issues.

    Args:
        v: The value to validate.

    Returns:
        Any: The original value if valid.

    Raises:
        ValueError: If the value contains control characters or null bytes.
    """
    if not v or not isinstance(v, str):
        return v

    # Check for null bytes
    if "\x00" in v:
        raise ValueError(
            f"Name contains null bytes which are not allowed in resource names: {repr(v)}"
        )

    # Check for control characters (ASCII < 32, excluding common whitespace)
    # Allow: tab (\x09), newline (\x0a), carriage return (\x0d) for multi-line fields
    # Reject: all other control characters
    allowed_control_chars = {"\t", "\n", "\r"}  # ASCII 9, 10, 13
    for char in v:
        if ord(char) < 32 and char not in allowed_control_chars:
            raise ValueError(
                f"Name contains control character (ASCII {ord(char)}): {repr(v)}. "
                "Please remove control characters from resource names."
            )

    return v


def strip_whitespace_and_validate_encoding(v: Any) -> Any:
    """
    Strip whitespace from string and validate encoding.

    Combines strip_whitespace and validate_name_encoding for use on name fields.

    Args:
        v: The value to process.

    Returns:
        Any: The processed value.

    Raises:
        ValueError: If the value contains control characters or null bytes.
    """
    stripped = strip_whitespace(v)
    return validate_name_encoding(stripped)


def validate_and_normalize_ipv4_cidr(v: Any) -> str:
    """
    Validate and normalize IPv4 CIDR notation.

    Handles:
    - "10.1.0.1/24" → "10.1.0.0/24" (normalized to network address)
    - "10.0.0.0/8" → "10.0.0.0/8" (already correct)
    - Invalid formats → raises ValueError

    Args:
        v: CIDR value to validate.

    Returns:
        str: Normalized CIDR notation.

    Raises:
        ValueError: If CIDR format is invalid.
    """
    if not v:
        raise ValueError("CIDR is required")

    # Strip whitespace first
    if isinstance(v, str):
        v = v.strip()

    try:
        # Validate using ipaddress module (strict=False allows host bits set)
        network = IPv4Network(v, strict=False)
        # Return normalized CIDR
        return str(network)
    except Exception as e:
        raise ValueError(f"Invalid IPv4 CIDR notation '{v}': {str(e)}") from e


def validate_and_normalize_ipv6_cidr(v: Any) -> str:
    """
    Validate and normalize IPv6 CIDR notation.

    Handles:
    - "2001:db8::1/64" → "2001:db8::/64" (normalized to network address)
    - "2001:db8::/32" → "2001:db8::/32" (already correct)
    - Invalid formats → raises ValueError

    Args:
        v: CIDR value to validate.

    Returns:
        str: Normalized CIDR notation.

    Raises:
        ValueError: If CIDR format is invalid.
    """
    if not v:
        raise ValueError("CIDR is required")

    # Strip whitespace first
    if isinstance(v, str):
        v = v.strip()

    try:
        # Validate using ipaddress module (strict=False allows host bits set)
        network = IPv6Network(v, strict=False)
        # Return normalized CIDR
        return str(network)
    except Exception as e:
        raise ValueError(f"Invalid IPv6 CIDR notation '{v}': {str(e)}") from e


class CSVRowBase(BaseModel):
    """
    Base class for all CSV rows.

    All CSV rows share these common fields regardless of object type.
    """

    model_config = ConfigDict(
        # Allow extra fields for UDFs (udf_*)
        extra="allow",
        # Fields can appear in any order in CSV
        populate_by_name=True,
    )

    row_id: Annotated[int | str, Field(description="CSV row identifier")]
    object_type: Annotated[str, Field(description="BAM object type")]
    action: Annotated[
        Literal["create", "update", "delete"], Field(description="Operation to perform")
    ]
    version: Annotated[
        str, Field(default="3.0", description="CSV schema version", alias="_version")
    ]
    bam_id: Annotated[int | None, Field(default=None, description="Direct BAM resource ID")]
    verify_name: Annotated[
        str | None, Field(default=None, description="Verify name matches for safety")
    ]
    verify_address: Annotated[
        str | None, Field(default=None, description="Verify address matches for safety")
    ]

    def get_udf_fields(self) -> dict[str, Any]:
        """
        Extract user-defined fields (udf_*).

        Returns:
            dict[str, Any]: A dictionary of user-defined fields found in the row.
        """
        return {k: v for k, v in self.model_dump().items() if k.startswith("udf_")}


class IP4NetworkRow(CSVRowBase):
    """
    IPv4 Network row model.

    Example:
        row_id,object_type,action,config,parent,cidr,name,location_code
        1,ip4_network,create,Default,/IPv4/10.0.0.0/8,10.1.0.0/16,Corp-Network,US NYC DC1
    """

    object_type: Literal["ip4_network"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    parent: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    cidr: Annotated[str, BeforeValidator(strip_whitespace)]
    name: Annotated[str, BeforeValidator(strip_whitespace)]
    description: Annotated[
        str | None, Field(default=None), BeforeValidator(strip_whitespace_preserve_empty)
    ]
    location_code: Annotated[
        str | None,
        Field(default=None, description="Location code to associate with this network"),
        BeforeValidator(strip_whitespace),
    ]

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        """
        Validate and normalize CIDR notation after whitespace stripping.

        Args:
            v: The CIDR string to validate.

        Returns:
            str: The validated and normalized CIDR string.

        Raises:
            ValueError: If the CIDR format is invalid or empty.
        """
        if not v:
            raise ValueError("CIDR cannot be empty")

        try:
            # Validate and normalize (strict=False allows host bits to be set)
            network = IPv4Network(v, strict=False)
            normalized = str(network)

            # Log if normalization occurred
            if normalized != v:
                import structlog

                logger = structlog.get_logger(__name__)
                logger.info(
                    "CIDR normalized",
                    original=v,
                    normalized=normalized,
                    message="Input CIDR was not in canonical form",
                )

            # Additional check: warn if it's a host address
            if network.num_addresses == 1:
                import structlog

                logger = structlog.get_logger(__name__)
                logger.warning(
                    f"CIDR {normalized} represents a single host (/32), this is valid but unusual"
                )

            return normalized
        except ValueError as e:
            raise ValueError(
                f"Invalid CIDR notation '{v}': {e}. Must be in format x.x.x.x/yy (e.g., 10.1.0.0/24)"
            ) from e


class IP4BlockRow(CSVRowBase):
    """
    IPv4 Block row model.

    Example:
        row_id,object_type,action,config,parent,cidr,name,location_code
        1,ip4_block,create,Default,,10.0.0.0/8,Private-Block,US NYC DC1
    """

    object_type: Literal["ip4_block"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    parent: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    cidr: Annotated[str, BeforeValidator(strip_whitespace)]
    name: Annotated[str, BeforeValidator(strip_whitespace)]
    description: Annotated[
        str | None, Field(default=None), BeforeValidator(strip_whitespace_preserve_empty)
    ]
    location_code: Annotated[
        str | None,
        Field(default=None, description="Location code to associate with this block"),
        BeforeValidator(strip_whitespace),
    ]

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        """
        Validate and normalize CIDR notation.

        Args:
            v: The CIDR string to validate.

        Returns:
            str: The validated and normalized CIDR string.

        Raises:
            ValueError: If the CIDR format is invalid or empty.
        """
        if not v:
            raise ValueError("CIDR cannot be empty")

        try:
            # Validate and normalize (strict=False allows host bits to be set)
            network = IPv4Network(v, strict=False)
            normalized = str(network)

            # Log if normalization occurred
            if normalized != v:
                import structlog

                logger = structlog.get_logger(__name__)
                logger.info(
                    "CIDR normalized",
                    original=v,
                    normalized=normalized,
                    message="Input CIDR was not in canonical form",
                )

            # Additional check: warn if it's a host address
            if network.num_addresses == 1:
                import structlog

                logger = structlog.get_logger(__name__)
                logger.warning(
                    f"CIDR {normalized} represents a single host (/32), this is valid but unusual for a block"
                )

            return normalized
        except ValueError as e:
            raise ValueError(
                f"Invalid CIDR notation '{v}': {e}. Must be in format x.x.x.x/yy (e.g., 10.0.0.0/8)"
            ) from e


class IP4GroupRow(CSVRowBase):
    """
    IPv4 Group row model.

    IP Groups are logical groupings of consecutive IP addresses within a network.
    They allow administrators to organize address ranges for management purposes.

    Range formats:
    - IP addresses: '192.168.0.20-192.168.0.30'
    - Offset,size: '20,30' (offset 20 from network start, 30 addresses)
    - Offset,percentage: '20,15%' (offset 20, 15% of network size)
    - Negative offset: '-40,30' (40 from end, 30 addresses)

    Example:
        row_id,object_type,action,config,parent,name,range
        1,ip4_group,create,Default,/IPv4/10.0.0.0/8/10.1.0.0/24,DHCP-Pool,10.1.0.100-10.1.0.200
    """

    object_type: Literal["ip4_group"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    parent: Annotated[
        str,
        Field(description="Network path (e.g., /IPv4/10.0.0.0/8/10.1.0.0/24)"),
        BeforeValidator(strip_whitespace),
    ]
    name: Annotated[str, BeforeValidator(strip_whitespace_and_validate_encoding)]
    range: Annotated[
        str,
        Field(
            description="Address range specification. Formats: IP range (10.1.0.1-10.1.0.50), offset+size (20,30), offset+percent (20,15%), negative offset (-40,30)"
        ),
        BeforeValidator(strip_whitespace),
    ]

    @field_validator("parent")
    @classmethod
    def validate_parent(cls, v: str) -> str:
        """
        Validate parent network path is not empty.

        Args:
            v: The parent path to validate.

        Returns:
            str: The validated parent path.

        Raises:
            ValueError: If parent is empty.
        """
        if not v:
            raise ValueError(
                "Parent network path cannot be empty for IP groups. "
                "Provide a path like /IPv4/10.0.0.0/8/10.1.0.0/24"
            )
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """
        Validate name is not empty.

        Args:
            v: The name to validate.

        Returns:
            str: The validated name.

        Raises:
            ValueError: If name is empty.
        """
        if not v:
            raise ValueError("IP group name cannot be empty")
        return v

    @field_validator("range")
    @classmethod
    def validate_range(cls, v: str) -> str:
        """
        Validate range is not empty and appears to be a valid format.

        Args:
            v: The range to validate.

        Returns:
            str: The validated range.

        Raises:
            ValueError: If range is empty or invalid.
        """
        if not v:
            raise ValueError("IP group range cannot be empty")

        # Basic format validation - the API will do full validation
        # Valid formats:
        # - IP range: 192.168.0.20-192.168.0.30
        # - Offset,size: 20,30
        # - Offset,percentage: 20,15%
        # - Negative offset: -40,30
        if not ("-" in v or "," in v):
            raise ValueError(
                f"Invalid range format '{v}'. Expected formats: "
                "'10.1.0.1-10.1.0.50', '20,30', '20,15%', or '-40,30'"
            )

        return v


class IP4AddressRow(CSVRowBase):
    """
    IPv4 Address row model.

    Example:
        row_id,object_type,action,config,address,name,mac,location_code
        2,ip4_address,create,Default,10.1.0.5,server1,00:11:22:33:44:55,US NYC DC1
    """

    object_type: Literal["ip4_address"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    address: Annotated[str, BeforeValidator(strip_whitespace)]
    name: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    mac: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    parent: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    description: Annotated[
        str | None, Field(default=None), BeforeValidator(strip_whitespace_preserve_empty)
    ]
    location_code: Annotated[
        str | None,
        Field(default=None, description="Location code to associate with this address"),
        BeforeValidator(strip_whitespace),
    ]

    # DHCP reservation state (from BlueCat API spec)
    state: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str | None) -> str | None:
        """
        Validate IP address state against BlueCat API enum values.

        Args:
            v: The state value to validate.

        Returns:
            The validated state value in uppercase.

        Raises:
            ValueError: If the state is invalid.
        """
        if v is None:
            return v

        valid_states = ["STATIC", "RESERVED", "DHCP_RESERVED", "GATEWAY"]
        if v.upper() not in valid_states:
            raise ValueError(f"Invalid state: {v}. Valid states: {', '.join(valid_states)}")
        return v.upper()

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        """
        Validate IP address format after whitespace stripping.

        Args:
            v: The IP address string to validate.

        Returns:
            str: The validated IP address string.

        Raises:
            ValueError: If the IP address format is invalid.
        """
        try:
            IPv4Address(v)
        except ValueError as e:
            raise ValueError(f"Invalid IPv4 address '{v}': {e}") from e
        return v

    @field_validator("mac")
    @classmethod
    def validate_mac(cls, v: str | None) -> str | None:
        """
        Validate MAC address format.

        Args:
            v: The MAC address string to validate.

        Returns:
            Optional[str]: The validated MAC address string or None.

        Raises:
            ValueError: If the MAC address format is invalid.
        """
        if v:
            # MAC validation: XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX
            if not re.match(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$", v):
                raise ValueError(f"Invalid MAC address format: {v}")
        return v


class IP6BlockRow(CSVRowBase):
    """
    IPv6 Block row model - top-level IPv6 address block container.

    Example:
        row_id,object_type,action,config,parent,cidr,name,description
        1,ip6_block,create,Default,,2001:db8::/32,IPv6-Documentation-Block,RFC 3849 documentation prefix
    """

    object_type: Literal["ip6_block"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    parent: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    cidr: Annotated[str, BeforeValidator(strip_whitespace)]
    name: Annotated[str, BeforeValidator(strip_whitespace)]
    description: Annotated[
        str | None, Field(default=None), BeforeValidator(strip_whitespace_preserve_empty)
    ]
    location_code: Annotated[
        str | None,
        Field(default=None, description="Location code"),
        BeforeValidator(strip_whitespace),
    ]

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        """
        Validate and normalize IPv6 CIDR notation.

        Args:
            v: The IPv6 CIDR string to validate.

        Returns:
            str: The validated and normalized CIDR string.

        Raises:
            ValueError: If the CIDR format is invalid.
        """
        if not v:
            raise ValueError("CIDR cannot be empty")
        try:
            # Validate and normalize (strict=False allows host bits to be set)
            network = IPv6Network(v, strict=False)
            normalized = str(network)

            # Log if normalization occurred
            if normalized != v:
                import structlog

                logger = structlog.get_logger(__name__)
                logger.info(
                    "IPv6 CIDR normalized",
                    original=v,
                    normalized=normalized,
                    message="Input CIDR was not in canonical form",
                )

            if network.num_addresses == 1:
                import structlog

                logger = structlog.get_logger(__name__)
                logger.warning(
                    f"CIDR {normalized} represents a single host (/128), unusual for a block"
                )

            return normalized
        except ValueError as e:
            raise ValueError(f"Invalid IPv6 CIDR notation '{v}': {e}. Format: 2001:db8::/48") from e


class IP6NetworkRow(CSVRowBase):
    """
    IPv6 Network row model - IPv6 subnet within blocks.

    Example:
        row_id,object_type,action,config,parent,cidr,name,description
        2,ip6_network,create,Default,/IPv6/2001:db8::/32,2001:db8:1::/64,Production-IPv6,Primary production network
    """

    object_type: Literal["ip6_network"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    parent: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    cidr: Annotated[str, BeforeValidator(strip_whitespace)]
    name: Annotated[str, BeforeValidator(strip_whitespace)]
    description: Annotated[
        str | None, Field(default=None), BeforeValidator(strip_whitespace_preserve_empty)
    ]
    location_code: Annotated[
        str | None,
        Field(default=None, description="Location code"),
        BeforeValidator(strip_whitespace),
    ]

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        """
        Validate and normalize IPv6 CIDR notation.

        Args:
            v: The IPv6 CIDR string to validate.

        Returns:
            str: The validated and normalized CIDR string.

        Raises:
            ValueError: If the CIDR format is invalid.
        """
        if not v:
            raise ValueError("CIDR cannot be empty")
        try:
            # Validate and normalize (strict=False allows host bits to be set)
            network = IPv6Network(v, strict=False)
            normalized = str(network)

            # Log if normalization occurred
            if normalized != v:
                import structlog

                logger = structlog.get_logger(__name__)
                logger.info(
                    "IPv6 CIDR normalized",
                    original=v,
                    normalized=normalized,
                    message="Input CIDR was not in canonical form",
                )

            if network.num_addresses == 1:
                import structlog

                logger = structlog.get_logger(__name__)
                logger.warning(
                    f"CIDR {normalized} represents a single host (/128), unusual for a network"
                )

            return normalized
        except ValueError as e:
            raise ValueError(
                f"Invalid IPv6 CIDR notation '{v}': {e}. Format: 2001:db8:1::/64"
            ) from e


class IP6AddressRow(CSVRowBase):
    """
    IPv6 Address row model.

    Example:
        row_id,object_type,action,config,address,name,mac,description,state
        3,ip6_address,create,Default,2001:db8:1::10,server1,00:11:22:33:44:55,Production server,STATIC

    Note:
        IPv6 addresses only support STATIC and DHCP_RESERVED states (per BAM API spec).
        RESERVED and GATEWAY states are not supported for IPv6.
    """

    object_type: Literal["ip6_address"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    address: Annotated[str, BeforeValidator(strip_whitespace)]
    name: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    mac: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    parent: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    description: Annotated[
        str | None, Field(default=None), BeforeValidator(strip_whitespace_preserve_empty)
    ]
    location_code: Annotated[
        str | None,
        Field(default=None, description="Location code"),
        BeforeValidator(strip_whitespace),
    ]
    state: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str | None) -> str | None:
        """
        Validate IPv6 address state.

        IPv6 addresses only support STATIC and DHCP_RESERVED states.

        Args:
            v: The state string to validate.

        Returns:
            Optional[str]: The validated uppercase state string or None.

        Raises:
            ValueError: If the state is not valid for IPv6.
        """
        if v is None:
            return v
        valid_states = ["STATIC", "DHCP_RESERVED"]
        if v.upper() not in valid_states:
            raise ValueError(
                f"Invalid IPv6 address state: {v}. Valid states: {', '.join(valid_states)}"
            )
        return v.upper()

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        """
        Validate IPv6 address format.

        Always returns compressed notation for consistency.

        Args:
            v: The IPv6 address string to validate.

        Returns:
            str: The validated IPv6 address in compressed notation.

        Raises:
            ValueError: If the address format is invalid.
        """
        try:
            addr = IPv6Address(v)
            # Return compressed notation for consistency
            return addr.compressed
        except ValueError as e:
            raise ValueError(f"Invalid IPv6 address '{v}': {e}") from e

    @field_validator("mac")
    @classmethod
    def validate_mac(cls, v: str | None) -> str | None:
        """
        Validate MAC address format (same as IPv4).

        Args:
            v: The MAC address string to validate.

        Returns:
            Optional[str]: The validated MAC address string or None.

        Raises:
            ValueError: If the MAC address format is invalid.
        """
        if v:
            # MAC validation: XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX
            if not re.match(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$", v):
                raise ValueError(f"Invalid MAC address format: {v}")
        return v


class HostRecordRow(CSVRowBase):
    """
    DNS Host Record row model.

    Example:
        row_id,object_type,action,config,view_path,name,addresses,location_code
        3,host_record,create,Default,Internal,www.example.com,10.1.0.5|10.1.0.6,US NYC DC1

    Note: Empty name ("" or "@") represents zone apex record.
    """

    object_type: Literal["host_record"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    view_path: Annotated[str, BeforeValidator(strip_whitespace)]
    name: Annotated[str, BeforeValidator(normalize_dns_record_name)]
    addresses: Annotated[
        str, BeforeValidator(strip_whitespace), Field(description="Pipe-separated IP addresses")
    ]
    ttl: Annotated[int | None, Field(default=None, description="TTL in seconds")]
    description: Annotated[
        str | None, Field(default=None), BeforeValidator(strip_whitespace_preserve_empty)
    ]
    location_code: Annotated[
        str | None,
        Field(default=None, description="Location code to associate with this record"),
        BeforeValidator(strip_whitespace),
    ]
    ptr: Annotated[
        bool | None,
        Field(default=None, description="Create reverse PTR record (true/false)"),
    ]

    @field_validator("addresses")
    @classmethod
    def validate_addresses(cls, v: str) -> str:
        """
        Validate that all addresses in pipe-separated list are valid IPs.

        Args:
            v: The pipe-separated addresses string.

        Returns:
            str: The validated string.

        Raises:
            ValueError: If any address is invalid or the list is empty.
        """
        if not v:
            raise ValueError("Addresses cannot be empty")

        addresses = [addr.strip() for addr in v.split("|")]
        valid_addresses = []
        for addr in addresses:
            if not addr:  # Empty address
                continue
            try:
                IPv4Address(addr)  # Validate IP address format
                valid_addresses.append(addr)
            except ValueError as e:
                raise ValueError(f"Invalid IP address '{addr}': {e}") from e

        if not valid_addresses:
            raise ValueError("Addresses cannot be empty or contain only delimiters")

        return v

    def get_address_list(self) -> list[str]:
        """
        Parse pipe-separated addresses into list.

        Returns:
            list[str]: List of IP address strings.
        """
        return [addr.strip() for addr in self.addresses.split("|") if addr.strip()]


class AliasRecordRow(CSVRowBase):
    """
    DNS Alias (CNAME) Record row model.

    Example:
        row_id,object_type,action,config,view_path,name,cname,ttl,description,location_code
        4,alias_record,create,Default,Internal,www,www.example.com,3600,CNAME for www,US NYC DC1
    """

    object_type: Literal["alias_record"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    view_path: Annotated[str, BeforeValidator(strip_whitespace)]
    zone_name: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    name: Annotated[str, BeforeValidator(normalize_dns_record_name)]
    linked_record_name: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(alias="cname", description="Canonical name (CNAME target)"),
    ]
    ttl: Annotated[int | None, Field(default=None, description="TTL in seconds")]
    description: Annotated[
        str | None, Field(default=None), BeforeValidator(strip_whitespace_preserve_empty)
    ]
    location_code: Annotated[
        str | None,
        Field(default=None, description="Location code to associate with this record"),
        BeforeValidator(strip_whitespace),
    ]


class MXRecordRow(CSVRowBase):
    """
    DNS MX Record row model.

    Example:
        row_id,object_type,action,config,view_path,name,exchange,preference,ttl,description,location_code
        5,mx_record,create,Default,Internal,example.com,mail.example.com,10,3600,Mail server,US NYC DC1
    """

    object_type: Literal["mx_record"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    view_path: Annotated[str, BeforeValidator(strip_whitespace)]
    zone_name: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    name: Annotated[str, BeforeValidator(normalize_dns_record_name)]
    exchange: Annotated[
        str, BeforeValidator(strip_whitespace), Field(description="Mail exchange server")
    ]
    preference: Annotated[int, Field(description="MX preference value")]
    ttl: Annotated[int | None, Field(default=None, description="TTL in seconds")]
    description: Annotated[
        str | None, Field(default=None), BeforeValidator(strip_whitespace_preserve_empty)
    ]
    location_code: Annotated[
        str | None,
        Field(default=None, description="Location code to associate with this record"),
        BeforeValidator(strip_whitespace),
    ]


class TXTRecordRow(CSVRowBase):
    """
    DNS TXT Record row model.

    Example:
        row_id,object_type,action,config,view_path,name,text,ttl,description,location_code
        6,txt_record,create,Default,Internal,_dmarc.example.com,"v=DMARC1",3600,DMARC record,US NYC DC1
    """

    object_type: Literal["txt_record"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    view_path: Annotated[str, BeforeValidator(strip_whitespace)]
    zone_name: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    name: Annotated[str, BeforeValidator(normalize_dns_record_name)]
    text: Annotated[str, Field(description="Text content for TXT record")]
    ttl: Annotated[int | None, Field(default=None, description="TTL in seconds")]
    description: Annotated[
        str | None, Field(default=None), BeforeValidator(strip_whitespace_preserve_empty)
    ]
    location_code: Annotated[
        str | None,
        Field(default=None, description="Location code to associate with this record"),
        BeforeValidator(strip_whitespace),
    ]


class SRVRecordRow(CSVRowBase):
    """
    DNS SRV Record row model.

    Example:
        row_id,object_type,action,config,view_path,name,target,port,priority,weight,ttl,description,location_code
        7,srv_record,create,Default,Internal,_sip._tcp.example.com,sip.example.com,5060,10,50,3600,SIP service,US NYC DC1
    """

    object_type: Literal["srv_record"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    view_path: Annotated[str, BeforeValidator(strip_whitespace)]
    zone_name: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    name: Annotated[str, BeforeValidator(normalize_dns_record_name)]
    target: Annotated[
        str, BeforeValidator(strip_whitespace), Field(description="Target host for SRV record")
    ]
    port: Annotated[int, Field(description="Port number")]
    priority: Annotated[int, Field(description="SRV priority")]
    weight: Annotated[int, Field(description="SRV weight")]
    ttl: Annotated[int | None, Field(default=None, description="TTL in seconds")]
    description: Annotated[
        str | None, Field(default=None), BeforeValidator(strip_whitespace_preserve_empty)
    ]
    location_code: Annotated[
        str | None,
        Field(default=None, description="Location code to associate with this record"),
        BeforeValidator(strip_whitespace),
    ]

    @field_validator("ttl")
    @classmethod
    def validate_ttl(cls, v: int | None) -> int | None:
        """
        Validate TTL is positive and reasonable.

        Args:
            v: The TTL value to validate.

        Returns:
            Optional[int]: The validated TTL value.

        Raises:
            ValueError: If TTL is negative or exceeds maximum value.
        """
        if v is not None:
            if v <= 0:
                raise ValueError(f"TTL must be positive, got {v}")
            if v > 2147483647:  # Max 32-bit signed int
                raise ValueError(f"TTL {v} exceeds maximum value (2147483647)")
            if v > 86400:  # More than 24 hours
                import structlog

                logger = structlog.get_logger(__name__)
                logger.warning(
                    f"TTL {v} is very large (>{v//3600} hours), consider if this is intentional"
                )
        return v


class ExternalHostRecordRow(CSVRowBase):
    """
    DNS External Host Record row model.

    External host records represent hosts that exist outside of BlueCat Address Manager.
    These are typically used as targets for CNAME, MX, or SRV records that point to
    external hosts not managed in BAM.

    Example:
        row_id,object_type,action,config,view_path,zone_name,name,ttl,description
        1,external_host_record,create,Default,Internal,example.com,host.external.com,3600,External server
    """

    object_type: Literal["external_host_record"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    view_path: Annotated[str, BeforeValidator(strip_whitespace)]
    zone_name: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    name: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="External host fully qualified domain name"),
    ]
    ttl: Annotated[int | None, Field(default=None, description="TTL in seconds")]
    description: Annotated[
        str | None, Field(default=None), BeforeValidator(strip_whitespace_preserve_empty)
    ]

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """
        Validate external host name is a valid FQDN.

        Args:
            v: The name to validate.

        Returns:
            str: The validated name.

        Raises:
            ValueError: If the name is empty or invalid.
        """
        if not v:
            raise ValueError("External host name cannot be empty")

        # Basic FQDN validation
        if v.endswith("."):
            # Fully qualified domain name ending with dot
            v = v[:-1]  # Remove trailing dot for storage

        # Check for invalid characters
        import re

        if not re.match(
            r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$",
            v,
        ):
            raise ValueError(f"Invalid external host name '{v}'. Must be a valid domain name")

        return v


class GenericRecordRow(CSVRowBase):
    """
    DNS Generic Record row model.

    Generic records allow creating DNS record types not natively supported by BlueCat,
    such as SSHFP, TLSA, CAA, DS, DNAME, etc. The record data is provided as raw rdata.

    Supported record types: A, A6, AAAA, AFSDB, APL, CAA, CERT, DHCID, DNAME, DS,
    IPSECKEY, ISDN, KEY, KX, LOC, MB, MG, MINFO, MR, NS, NSAP, PTR, PX, RP, RT,
    SINK, SPF, SSHFP, TLSA, TXT, WKS, X25

    Example:
        row_id,object_type,action,config,view_path,zone_name,name,record_type,rdata,ttl,description
        1,generic_record,create,Default,Internal,example.com,server1,SSHFP,2 1 123456789abcdef,3600,SSH fingerprint
        2,generic_record,create,Default,Internal,example.com,_dmarc,TXT,v=DMARC1; p=reject,3600,DMARC policy
        3,generic_record,create,Default,Internal,example.com,@,CAA,0 issue letsencrypt.org,3600,CAA record
    """

    object_type: Literal["generic_record"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    view_path: Annotated[str, BeforeValidator(strip_whitespace)]
    zone_name: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    name: Annotated[str, BeforeValidator(normalize_dns_record_name)]
    record_type: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="DNS record type (e.g., SSHFP, TLSA, CAA, DS)"),
    ]
    rdata: Annotated[
        str,
        Field(description="Raw record data in zone file format"),
    ]
    ttl: Annotated[int | None, Field(default=None, description="TTL in seconds")]
    description: Annotated[
        str | None, Field(default=None), BeforeValidator(strip_whitespace_preserve_empty)
    ]

    # Valid record types for GenericRecord
    VALID_RECORD_TYPES: ClassVar[set[str]] = {
        "A",
        "A6",
        "AAAA",
        "AFSDB",
        "APL",
        "CAA",
        "CERT",
        "DHCID",
        "DNAME",
        "DS",
        "IPSECKEY",
        "ISDN",
        "KEY",
        "KX",
        "LOC",
        "MB",
        "MG",
        "MINFO",
        "MR",
        "NS",
        "NSAP",
        "PTR",
        "PX",
        "RP",
        "RT",
        "SINK",
        "SPF",
        "SSHFP",
        "TLSA",
        "TXT",
        "WKS",
        "X25",
    }

    @field_validator("record_type")
    @classmethod
    def validate_record_type(cls, v: str) -> str:
        """Validate the record type is a supported GenericRecord type."""
        v_upper = v.upper()
        if v_upper not in cls.VALID_RECORD_TYPES:
            raise ValueError(
                f"Invalid record type '{v}'. Supported types: {', '.join(sorted(cls.VALID_RECORD_TYPES))}"
            )
        return v_upper

    @field_validator("rdata")
    @classmethod
    def validate_rdata(cls, v: str) -> str:
        """Validate rdata is not empty."""
        if not v or not v.strip():
            raise ValueError("rdata cannot be empty")
        return v

    @field_validator("ttl")
    @classmethod
    def validate_ttl(cls, v: int | None) -> int | None:
        """Validate TTL is positive and reasonable."""
        if v is not None:
            if v <= 0:
                raise ValueError(f"TTL must be positive, got {v}")
            if v > 2147483647:
                raise ValueError(f"TTL {v} exceeds maximum value (2147483647)")
        return v


class DNSZoneRow(CSVRowBase):
    """
    DNS Zone row model.

    Example:
        row_id,object_type,action,config,view_path,zone_name,location_code
        4,dns_zone,create,Default,Internal,example.com,US NYC DC1
    """

    object_type: Literal["dns_zone"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    view_path: Annotated[str, BeforeValidator(strip_whitespace)]
    zone_name: Annotated[str, BeforeValidator(strip_whitespace)]
    description: Annotated[
        str | None, Field(default=None), BeforeValidator(strip_whitespace_preserve_empty)
    ]
    location_code: Annotated[
        str | None,
        Field(default=None, description="Location code to associate with this zone"),
        BeforeValidator(strip_whitespace),
    ]


class IPv4DHCPRangeRow(CSVRowBase):
    """DHCP IPv4 Range configuration for CSV import."""

    object_type: Literal["ipv4_dhcp_range"]

    # Core DHCP Range properties
    name: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    config: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    range: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    network_id: Annotated[int | None, Field(default=None)]
    network_path: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]

    # DHCP Range settings
    split_around_static_addresses: Annotated[
        bool | None, Field(default=None, alias="splitAroundStaticAddresses")
    ]
    low_water_mark: Annotated[int | None, Field(default=None, alias="lowWaterMark")]
    high_water_mark: Annotated[int | None, Field(default=None, alias="highWaterMark")]

    # Template related
    template_name: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    template_id: Annotated[int | None, Field(default=None)]

    @field_validator("range")
    @classmethod
    def validate_dhcp_range(cls, v: str | None) -> str | None:
        """
        Validate DHCP range format (e.g., '10.1.1.100-10.1.1.200').

        Args:
            v: The range string to validate.

        Returns:
            The validated range string.

        Raises:
            ValueError: If the range format is invalid.
        """
        if v is None:
            return v

        # Basic IPv4 range validation
        range_pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}-\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
        if not re.match(range_pattern, v):
            raise ValueError(
                f"Invalid DHCP range format: {v}. Expected format: '10.1.1.100-10.1.1.200'"
            )
        return v

    @field_validator("low_water_mark", "high_water_mark")
    @classmethod
    def validate_watermark(cls, v: int | None) -> int | None:
        """
        Validate watermarks are between 0-100.

        Args:
            v: The watermark value.

        Returns:
            The validated watermark value.

        Raises:
            ValueError: If the value is not between 0 and 100.
        """
        if v is not None:
            if not 0 <= v <= 100:
                raise ValueError(f"Watermark must be between 0-100, got: {v}")
        return v


class IPv6DHCPRangeRow(CSVRowBase):
    """
    DHCPv6 Range configuration for CSV import.

    Example:
        row_id,object_type,action,config,network_path,range,name
        4,ipv6_dhcp_range,create,Default,Default/2001:db8:1::/64,2001:db8:1::1000-2001:db8:1::2000,DHCPv6-Pool
    """

    object_type: Literal["ipv6_dhcp_range"]

    # Core DHCPv6 Range properties
    name: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    config: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    range: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    network_id: Annotated[int | None, Field(default=None)]
    network_path: Annotated[
        str | None, Field(default=None, alias="parent"), BeforeValidator(strip_whitespace)
    ]

    # DHCPv6 Range settings
    split_around_static_addresses: Annotated[
        bool | None, Field(default=None, alias="splitAroundStaticAddresses")
    ]
    low_water_mark: Annotated[int | None, Field(default=None, alias="lowWaterMark")]
    high_water_mark: Annotated[int | None, Field(default=None, alias="highWaterMark")]

    # Template related
    template_name: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    template_id: Annotated[int | None, Field(default=None)]

    @field_validator("range")
    @classmethod
    def validate_dhcp_range(cls, v: str | None) -> str | None:
        """
        Validate DHCPv6 range format.

        Supports formats:
        - start-end: '2001:db8::100-2001:db8::200'
        - offset,size: '20,10'
        - offset,percentage: '20,1%'
        - CIDR notation: '/120'

        Args:
            v: The range string to validate.

        Returns:
            The validated range string.

        Raises:
            ValueError: If the range format is invalid.
        """
        if v is None:
            return v

        # IPv6 range validation for start-end format
        if "-" in v:
            parts = v.split("-")
            if len(parts) != 2:
                raise ValueError(
                    f"Invalid DHCPv6 range format: {v}. Expected format: '2001:db8::100-2001:db8::200'"
                )
            try:
                start = IPv6Address(parts[0].strip())
                end = IPv6Address(parts[1].strip())
                if start >= end:
                    raise ValueError(f"DHCPv6 range start must be less than end: {v}")
            except ValueError as e:
                raise ValueError(f"Invalid IPv6 address in range: {v}. {str(e)}") from e

        return v

    @field_validator("low_water_mark", "high_water_mark")
    @classmethod
    def validate_watermark(cls, v: int | None) -> int | None:
        """
        Validate watermarks are between 0-100.

        Args:
            v: The watermark value.

        Returns:
            The validated watermark value.

        Raises:
            ValueError: If the value is not between 0 and 100.
        """
        if v is not None:
            if not 0 <= v <= 100:
                raise ValueError(f"Watermark must be between 0-100, got: {v}")
        return v


class DHCPDeploymentRoleRow(CSVRowBase):
    """DHCP Deployment Role configuration for CSV import."""

    object_type: Literal["dhcp_deployment_role"]

    # Core Deployment Role properties
    name: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    config: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    network_path: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    block_path: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]

    # Role properties
    role_type: Annotated[
        str | None,
        Field(default=None, alias="roleType"),
        BeforeValidator(strip_whitespace),
    ]
    interfaces: Annotated[
        str | None,
        Field(
            default=None,
            description="Pipe-separated server interfaces in format 'server:interface|server2:interface2'",
        ),
        BeforeValidator(strip_whitespace),
    ]
    server_group: Annotated[
        str | None, Field(default=None, alias="serverGroup"), BeforeValidator(strip_whitespace)
    ]
    server_group_id: Annotated[int | None, Field(default=None, alias="serverGroupId")]

    @field_validator("role_type")
    @classmethod
    def validate_role_type(cls, v: str | None) -> str | None:
        """
        Validate deployment role type.

        Args:
            v: The role type value.

        Returns:
            The validated role type in uppercase.

        Raises:
            ValueError: If the role type is invalid.
        """
        if v is None:
            return v

        valid_types = ["PRIMARY", "SECONDARY", "ACTIVE", "PASSIVE", "NONE"]
        if v.upper() not in valid_types:
            raise ValueError(f"Invalid role type: {v}. Valid types: {', '.join(valid_types)}")
        return v.upper()

    @field_validator("interfaces")
    @classmethod
    def validate_interfaces(cls, v: str | None) -> str | None:
        """
        Validate interfaces format.

        Supports three formats:
        1. 'server:interface' - traditional server:interface format
        2. Server names only - server names to be resolved to primary interface (e.g., "server1|server2")
        3. Interface IDs - numeric interface IDs (e.g., "4402278|4402274")

        Args:
            v: The interfaces string.

        Returns:
            The validated interfaces string, or None if empty.

        Raises:
            ValueError: If the format is invalid.
        """
        if v is None:
            return v

        interfaces = [iface.strip() for iface in v.split("|")]
        for iface in interfaces:
            if not iface:  # Empty interface
                continue
            # Allow interface IDs (numeric), server:interface format, or server names
            if (
                ":" not in iface
                and not iface.isdigit()
                and not iface.replace("-", "").replace("_", "").isalnum()
            ):
                raise ValueError(
                    f"Invalid interface format: '{iface}'. Expected format: 'server:interface', interface ID, or server name"
                )
        # Return the cleaned up interfaces string, or None if empty
        cleaned = "|".join(iface for iface in interfaces if iface)
        return cleaned if cleaned else None

    def get_interface_list(self) -> list[str]:
        """
        Get list of interfaces from pipe-separated string.

        Returns:
            list[str]: List of interface strings.
        """
        if not self.interfaces:
            return []
        return [i.strip() for i in self.interfaces.split("|") if i.strip()]


class DNSDeploymentRoleRow(CSVRowBase):
    """
    DNS Deployment Role configuration for CSV import.

    DNS deployment roles define how DNS services are deployed to servers.
    They control which servers provide DNS service for specific zones, networks, or blocks.

    Examples:
        Zone-level:
        row_id,object_type,action,config,zone_path,name,role_type,interfaces,ns_record_ttl
        1,dns_deployment_role,create,Default,Internal/test.local,Zone-DNS,PRIMARY,"server1:interface1|server2:interface2",3600

        Network-level:
        row_id,object_type,action,config,network_path,name,role_type,interfaces,ns_record_ttl
        2,dns_deployment_role,create,Default,192.168.40.0/24,Network-DNS,PRIMARY,"server1:interface1",3600

        Block-level:
        row_id,object_type,action,config,block_path,name,role_type,interfaces,ns_record_ttl
        3,dns_deployment_role,create,Default,/IPv4/10.0.0.0/8,Block-DNS,PRIMARY,"server1:interface1",3600
    """

    object_type: Literal["dns_deployment_role"]

    # Core Deployment Role properties
    name: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    config: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]

    # Parent resource paths (one must be provided)
    zone_path: Annotated[
        str | None,
        Field(default=None, description="Zone path for zone-level DNS deployment roles"),
        BeforeValidator(strip_whitespace),
    ]
    network_path: Annotated[
        str | None,
        Field(default=None, description="Network path for network-level DNS deployment roles"),
        BeforeValidator(strip_whitespace),
    ]
    block_path: Annotated[
        str | None,
        Field(default=None, description="Block path for block-level DNS deployment roles"),
        BeforeValidator(strip_whitespace),
    ]

    # Role properties (from OpenAPI spec)
    role_type: Annotated[
        str | None, Field(default=None, alias="roleType"), BeforeValidator(strip_whitespace)
    ]
    interfaces: Annotated[
        str | None,
        Field(
            default=None,
            description="Pipe-separated server interfaces in format 'server:interface|server2:interface2'",
        ),
        BeforeValidator(strip_whitespace),
    ]
    ns_record_ttl: Annotated[
        int | None,
        Field(default=None, alias="nsRecordTtl", description="NS record TTL in seconds"),
    ]

    @field_validator("role_type")
    @classmethod
    def validate_role_type(cls, v: str | None) -> str | None:
        """
        Validate DNS deployment role type against BlueCat API enum values.

        Args:
            v: The role type value.

        Returns:
            The validated role type in uppercase.

        Raises:
            ValueError: If the role type is invalid.
        """
        if v is None:
            return v

        valid_types = [
            "PRIMARY",
            "MULTI_PRIMARY",
            "HIDDEN_PRIMARY",
            "HIDDEN_MULTI_PRIMARY",
            "SECONDARY",
            "STEALTH_SECONDARY",
            "FORWARDING",
            "STUB",
            "RECURSIVE",
            "NONE",
        ]
        if v.upper() not in valid_types:
            raise ValueError(
                f"Invalid DNS deployment role type: {v}. Valid types: {', '.join(valid_types)}"
            )
        return v.upper()

    @field_validator("interfaces")
    @classmethod
    def validate_interfaces(cls, v: str | None) -> str | None:
        """
        Validate interfaces format.

        Supports three formats:
        1. 'server:interface' - traditional server:interface format
        2. Server names only - server names to be resolved to primary interface (e.g., "server1|server2")
        3. Interface IDs - numeric interface IDs (e.g., "4402278|4402274")

        Args:
            v: The interfaces string.

        Returns:
            The validated interfaces string, or None if empty.

        Raises:
            ValueError: If the format is invalid.
        """
        if v is None:
            return v

        interfaces = [iface.strip() for iface in v.split("|")]
        for iface in interfaces:
            if not iface:  # Empty interface
                continue
            # Allow interface IDs (numeric), server:interface format, or server names
            if (
                ":" not in iface
                and not iface.isdigit()
                and not iface.replace("-", "").replace("_", "").isalnum()
            ):
                raise ValueError(
                    f"Invalid interface format: '{iface}'. Expected format: 'server:interface', interface ID, or server name"
                )
        # Return the cleaned up interfaces string, or None if empty
        cleaned = "|".join(iface for iface in interfaces if iface)
        return cleaned if cleaned else None

    @field_validator("ns_record_ttl")
    @classmethod
    def validate_ns_record_ttl(cls, v: int | None) -> int | None:
        """
        Validate NS record TTL is within valid range.

        Args:
            v: The TTL value.

        Returns:
            The validated TTL value.

        Raises:
            ValueError: If TTL is negative or too large.
        """
        if v is None:
            return v

        if v < 0:
            raise ValueError(f"NS record TTL must be non-negative, got {v}")
        if v > 2147483647:  # Max 32-bit signed int from API spec
            raise ValueError(f"NS record TTL {v} exceeds maximum value (2147483647)")
        return v

    @model_validator(mode="after")
    def validate_parent(self) -> "DNSDeploymentRoleRow":
        """
        Ensure exactly one parent path is provided.

        Returns:
            DNSDeploymentRoleRow: The validated row.

        Raises:
            ValueError: If zero or more than one parent path is provided.
        """
        parents = [self.zone_path, self.network_path, self.block_path]

        # Count non-None parent paths
        provided_paths = [path for path in parents if path is not None and path.strip()]

        if len(provided_paths) == 0:
            raise ValueError(
                "Exactly one parent path must be provided: zone_path, network_path, or block_path"
            )

        if len(provided_paths) > 1:
            raise ValueError(
                "Only one parent path may be provided: zone_path, network_path, or block_path"
            )

        return self

    def get_interface_list(self) -> list[str]:
        """
        Parse pipe-separated interfaces into list.

        Returns:
            list[str]: List of interface strings.
        """
        if not self.interfaces:
            return []
        return [iface.strip() for iface in self.interfaces.split("|") if iface.strip()]

    def get_api_interfaces(self) -> list[dict[str, Any]]:
        """
        Convert interface string to API format.

        Converts interface IDs to format expected by BAM API:
        [{"id": interface_id}, ...] or [{"id": interface_id, "type": "interface"}, ...]

        Returns:
            list[dict[str, Any]]: List of interface dictionaries for API.
        """
        if not self.interfaces:
            return []

        api_interfaces: list[dict[str, Any]] = []
        for iface in self.interfaces.split("|"):
            iface = iface.strip()
            if not iface:
                continue

            if iface.isdigit():
                # Interface ID format
                api_interfaces.append({"id": int(iface)})
            elif ":" in iface:
                # server:interface format - extract interface ID
                parts = iface.split(":", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    api_interfaces.append({"id": int(parts[1])})
                else:
                    # Keep as-is for server:interface format
                    api_interfaces.append({"id": parts[1], "type": "interface"})

        return api_interfaces

    def get_parent_info(self) -> tuple[str, str]:
        """
        Get parent type and path for DNS deployment role.

        Returns:
            tuple[str, str]: (parent_type, parent) where parent_type is one of
                             'zones', 'networks', or 'blocks'

        Raises:
            ValueError: If no parent path is specified.
        """
        if self.zone_path:
            return "zones", self.zone_path
        elif self.network_path:
            return "networks", self.network_path
        elif self.block_path:
            return "blocks", self.block_path
        else:
            raise ValueError("No parent path specified for DNS deployment role")


class DHCPv4ClientDeploymentOptionRow(CSVRowBase):
    """
    DHCPv4 Client Deployment Option configuration for CSV import.

    DHCP client deployment options are specific DHCP options that are
    deployed to networks for client assignment. These options are
    sent to DHCP clients during the lease process.

    Example:
        row_id,object_type,action,config,network_path,name,code,value,server_scope
        1,dhcpv4_client_deployment_option,create,Default,/IPv4/10.0.0.0/8,"DNS Servers",6,"8.8.8.8,8.8.4.4",DHCP_SERVER
    """

    object_type: Literal["dhcpv4_client_deployment_option"]

    # Core properties
    name: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    config: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    network_path: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    network_id: Annotated[int | None, Field(default=None)]

    # DHCP option properties
    code: Annotated[int | None, Field(default=None, description="DHCP option code per RFC 2132")]
    value: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    server_scope: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]

    @field_validator("code")
    @classmethod
    def validate_dhcp_code(cls, v: int | None) -> int | None:
        """
        Validate DHCP option code is within valid range.

        Args:
            v: The DHCP option code.

        Returns:
            The validated option code.

        Raises:
            ValueError: If the code is not between 1 and 254.
        """
        if v is None:
            return v

        if v < 1 or v > 254:
            raise ValueError(f"DHCP option code must be between 1 and 254, got {v}")
        return v

    @field_validator("server_scope")
    @classmethod
    def validate_server_scope(cls, v: str | None) -> str | None:
        """
        Validate server scope against BlueCat API enum values.

        Args:
            v: The server scope value.

        Returns:
            The validated server scope in uppercase.

        Raises:
            ValueError: If the scope is invalid.
        """
        if v is None:
            return v

        valid_scopes = ["DHCP_SERVER", "DNS_SERVER", "ALL_SERVERS"]
        if v.upper() not in valid_scopes:
            raise ValueError(f"Invalid server scope: {v}. Valid scopes: {', '.join(valid_scopes)}")
        return v.upper()


class LocationRow(CSVRowBase):
    """
    Location row model for CSV import.

    Locations in BlueCat are hierarchical and based on UN/LOCODE codes.
    Custom locations can only be created under existing UN/LOCODE city-level
    locations. The code format is "COUNTRY CITY CUSTOM" (e.g., "US NYC HQ").

    IMPORTANT: Root-level location creation is NOT supported by the BAM API.
    The parent_code field is REQUIRED and must reference a valid UN/LOCODE
    location (e.g., "US NYC", "GB LON", "JP TYO") or a previously created
    custom location.

    Example:
        row_id,object_type,action,parent_code,code,name,description,latitude,longitude
        1,location,create,US NYC,US NYC HQ,New York Headquarters,Main office,40.7128,-74.0060
        2,location,create,US NYC HQ,US NYC HQ F1,Floor 1,First floor,40.7128,-74.0060
    """

    object_type: Literal["location"]

    # Parent location code (REQUIRED - must reference a valid UN/LOCODE or custom location)
    parent_code: Annotated[
        str,  # Changed from str | None to str - parent_code is required
        BeforeValidator(strip_whitespace),
        Field(
            description="Parent location code (e.g., 'US NYC'). REQUIRED - root locations cannot be created.",
        ),
    ]

    # Location properties
    code: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="Full location code including parent hierarchy (e.g., 'US NYC HQ')"),
    ]
    name: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="Display name of the location"),
    ]
    description: Annotated[
        str | None,
        Field(default=None),
        BeforeValidator(strip_whitespace_preserve_empty),
    ]
    localized_name: Annotated[
        str | None,
        Field(default=None, alias="localizedName"),
        BeforeValidator(strip_whitespace),
    ]
    latitude: Annotated[
        float | None,
        Field(default=None, ge=-90, le=90, description="Latitude in decimal degrees"),
    ]
    longitude: Annotated[
        float | None,
        Field(default=None, ge=-180, le=180, description="Longitude in decimal degrees"),
    ]

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        """
        Validate location code format.

        Location codes should be space-separated hierarchical codes.
        Format: "COUNTRY CITY [CUSTOM...]" (e.g., "US NYC HQ F1")

        Args:
            v: The location code to validate.

        Returns:
            str: The validated location code.

        Raises:
            ValueError: If the code is empty or invalid.
        """
        if not v:
            raise ValueError("Location code cannot be empty")

        # Location codes should have at least 2 parts (country + city or custom)
        parts = v.split()
        if len(parts) < 2:
            raise ValueError(
                f"Location code '{v}' must have at least 2 parts (e.g., 'US NYC' or 'US NYC HQ')"
            )

        return v

    @field_validator("parent_code")
    @classmethod
    def validate_parent_code(cls, v: str) -> str:
        """
        Validate parent location code format.

        Parent code is REQUIRED as root-level location creation is not supported
        by the BAM API.

        Args:
            v: The parent location code to validate.

        Returns:
            str: The validated parent code.

        Raises:
            ValueError: If parent_code is empty or missing.
        """
        if not v or not v.strip():
            raise ValueError(
                "parent_code is required. Root-level location creation is not supported "
                "by the BAM API. Custom locations must be created under an existing "
                "UN/LOCODE location (e.g., 'US NYC', 'GB LON', 'JP TYO')."
            )

        return v

    @model_validator(mode="after")
    def validate_code_hierarchy(self) -> "LocationRow":
        """
        Validate that the code starts with the parent code.

        Returns:
            LocationRow: The validated row.

        Raises:
            ValueError: If code doesn't start with parent_code.
        """
        if not self.code.startswith(self.parent_code):
            raise ValueError(
                f"Location code '{self.code}' must start with parent code '{self.parent_code}'"
            )

        return self


class DHCPv4ServiceDeploymentOptionRow(CSVRowBase):
    """
    DHCPv4 Service Deployment Option configuration for CSV import.

    DHCP service deployment options are specific DHCP options that configure
    the DHCP service itself on servers. These options control how the DHCP
    service operates rather than what clients receive.

    Example:
        row_id,object_type,action,config,network_path,name,code,value,server_scope
        1,dhcpv4_service_deployment_option,create,Default,/IPv4/10.0.0.0/8,"Default Lease Time",51,"86400",DHCP_SERVER
    """

    object_type: Literal["dhcpv4_service_deployment_option"]

    # Core properties
    name: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    config: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    network_path: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    network_id: Annotated[int | None, Field(default=None)]

    # DHCP option properties
    code: Annotated[int | None, Field(default=None, description="DHCP option code per RFC 2132")]
    value: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]
    server_scope: Annotated[str | None, Field(default=None), BeforeValidator(strip_whitespace)]

    @field_validator("code")
    @classmethod
    def validate_dhcp_code(cls, v: int | None) -> int | None:
        """
        Validate DHCP option code is within valid range.

        Args:
            v: The DHCP option code.

        Returns:
            The validated option code.

        Raises:
            ValueError: If the code is not between 1 and 254.
        """
        if v is None:
            return v

        if v < 1 or v > 254:
            raise ValueError(f"DHCP option code must be between 1 and 254, got {v}")
        return v

    @field_validator("server_scope")
    @classmethod
    def validate_server_scope(cls, v: str | None) -> str | None:
        """
        Validate server scope against BlueCat API enum values.

        Args:
            v: The server scope value.

        Returns:
            The validated server scope in uppercase.

        Raises:
            ValueError: If the scope is invalid.
        """
        if v is None:
            return v

        valid_scopes = ["DHCP_SERVER", "DNS_SERVER", "ALL_SERVERS"]
        if v.upper() not in valid_scopes:
            raise ValueError(f"Invalid server scope: {v}. Valid scopes: {', '.join(valid_scopes)}")
        return v.upper()


class UDFDefinitionRow(CSVRowBase):
    """
    User-Defined Field (UDF) Definition row model.

    UDFs allow adding custom metadata to BAM resources. This row type is used
    to create new UDF definitions that can then be applied to resources.

    Example:
        row_id,object_type,action,name,display_name,field_type,default_value,required,resource_types
        1,udf_definition,create,CostCenter,Cost Center,TEXT,,false,IPv4Network|IPv4Block
        2,udf_definition,create,Owner,Owner Email,EMAIL,,true,*

    Notes:
        - resource_types: Pipe-separated list of resource types this UDF applies to
        - Use "*" for resource_types to apply to all resource types
        - Valid field_types: TEXT, MULTILINE_TEXT, URL, EMAIL, PHONE
    """

    object_type: Literal["udf_definition"]

    # UDF definition properties
    name: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="Internal name of the UDF (no spaces, used in API)"),
    ]
    display_name: Annotated[
        str | None,
        Field(default=None, alias="displayName"),
        BeforeValidator(strip_whitespace),
    ]
    field_type: Annotated[
        str,
        Field(alias="fieldType", description="Field type: TEXT, MULTILINE_TEXT, URL, EMAIL, PHONE"),
        BeforeValidator(strip_whitespace),
    ]
    default_value: Annotated[
        str | None,
        Field(default=None, alias="defaultValue"),
        BeforeValidator(strip_whitespace_preserve_empty),
    ]
    required: Annotated[
        bool | None,
        Field(default=False, description="Whether the field is required"),
    ]
    resource_types: Annotated[
        str | None,
        Field(
            default=None,
            alias="resourceTypes",
            description="Pipe-separated list of resource types (e.g., 'IPv4Network|IPv4Block') or '*' for all",
        ),
        BeforeValidator(strip_whitespace),
    ]
    predefined_values: Annotated[
        str | None,
        Field(
            default=None,
            alias="predefinedValues",
            description="Pipe-separated list of allowed values for dropdown fields",
        ),
        BeforeValidator(strip_whitespace),
    ]
    hide_from_search: Annotated[
        bool | None,
        Field(default=False, alias="hideFromSearch"),
    ]
    render_as_link: Annotated[
        bool | None,
        Field(default=False, alias="renderAsLink"),
    ]
    validators: Annotated[
        str | None,
        Field(default=None, description="Validation regex pattern"),
        BeforeValidator(strip_whitespace),
    ]

    # Valid UDF field types
    VALID_FIELD_TYPES: ClassVar[set[str]] = {
        "TEXT",
        "MULTILINE_TEXT",
        "URL",
        "EMAIL",
        "PHONE",
    }

    @field_validator("field_type")
    @classmethod
    def validate_field_type(cls, v: str) -> str:
        """Validate UDF field type."""
        v_upper = v.upper()
        if v_upper not in cls.VALID_FIELD_TYPES:
            raise ValueError(
                f"Invalid UDF field type '{v}'. Valid types: {', '.join(sorted(cls.VALID_FIELD_TYPES))}"
            )
        return v_upper

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate UDF name contains no spaces and is valid identifier."""
        if not v:
            raise ValueError("UDF name cannot be empty")
        if " " in v:
            raise ValueError(f"UDF name cannot contain spaces: '{v}'")
        if not v[0].isalpha():
            raise ValueError(f"UDF name must start with a letter: '{v}'")
        return v

    def get_resource_types_list(self) -> list[str]:
        """
        Parse pipe-separated resource types into list.

        Returns:
            list[str]: List of resource type strings, or ["*"] for all.
        """
        if not self.resource_types or self.resource_types == "*":
            return ["*"]
        return [rt.strip() for rt in self.resource_types.split("|") if rt.strip()]

    def get_predefined_values_list(self) -> list[str]:
        """
        Parse pipe-separated predefined values into list.

        Returns:
            list[str]: List of predefined value strings.
        """
        if not self.predefined_values:
            return []
        return [v.strip() for v in self.predefined_values.split("|") if v.strip()]


class UDLDefinitionRow(CSVRowBase):
    """
    User-Defined Link (UDL) Definition row model.

    UDLs allow creating custom links between BAM resources. This row type is
    used to create new UDL definitions.

    Example:
        row_id,object_type,action,name,display_name,source_types,destination_types
        1,udl_definition,create,AssociatedDevice,Associated Device,IPv4Address,Device
    """

    object_type: Literal["udl_definition"]

    # UDL definition properties
    name: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="Internal name of the UDL"),
    ]
    display_name: Annotated[
        str | None,
        Field(default=None, alias="displayName"),
        BeforeValidator(strip_whitespace),
    ]
    source_types: Annotated[
        str,
        Field(
            alias="sourceTypes",
            description="Pipe-separated list of source resource types",
        ),
        BeforeValidator(strip_whitespace),
    ]
    destination_types: Annotated[
        str,
        Field(
            alias="destinationTypes",
            description="Pipe-separated list of destination resource types",
        ),
        BeforeValidator(strip_whitespace),
    ]

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate UDL name."""
        if not v:
            raise ValueError("UDL name cannot be empty")
        if " " in v:
            raise ValueError(f"UDL name cannot contain spaces: '{v}'")
        return v

    def get_source_types_list(self) -> list[str]:
        """Parse pipe-separated source types into list."""
        return [t.strip() for t in self.source_types.split("|") if t.strip()]

    def get_destination_types_list(self) -> list[str]:
        """Parse pipe-separated destination types into list."""
        return [t.strip() for t in self.destination_types.split("|") if t.strip()]


class UserDefinedLinkRow(CSVRowBase):
    """
    User-Defined Link (UDL) instance row model.

    Creates an actual link between two BAM resources using a UDL definition.
    The source resource is specified by source_type and source_path, and the
    destination resource is specified by destination_type and destination_path.

    Example:
        row_id,object_type,action,config,udl_name,source_type,source_path,destination_type,destination_path,description
        1,user_defined_link,create,Default,AssociatedDevice,ip4_address,10.0.1.10,device,firewall-01,Primary firewall
        2,user_defined_link,create,Default,BackupServer,ip4_network,10.1.0.0/24,device,backup-server-01,Network backup
    """

    object_type: Literal["user_defined_link"]

    # Configuration for resource resolution
    config: Annotated[
        str, BeforeValidator(strip_whitespace), Field(description="Configuration name")
    ]

    # UDL definition reference
    udl_name: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="Name of the UDL definition to use"),
    ]

    # Source resource (the "from" side of the link)
    source_type: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="Source resource type (e.g., ip4_address, ip4_network, device)"),
    ]
    source_path: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="Path to identify the source resource"),
    ]

    # Destination resource (the "to" side of the link)
    destination_type: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="Destination resource type (e.g., device, ip4_network, host_record)"),
    ]
    destination_path: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="Path to identify the destination resource"),
    ]

    # Optional description for the link
    description: Annotated[
        str | None,
        Field(default=None, description="Optional description for the link"),
        BeforeValidator(strip_whitespace),
    ] = None


# -----------------------------------------------------------------------------
# MAC Pool Management
# -----------------------------------------------------------------------------


class MACPoolRow(CSVRowBase):
    """
    MAC Pool row model.

    MAC pools are used to group MAC addresses for DHCP allocation control.
    A MAC pool can be either a regular pool (MACPool) or a deny pool (DenyMACPool).

    Example:
        row_id,object_type,action,config,name,pool_type
        1,mac_pool,create,Default,VoIP-Phones,MACPool
        2,mac_pool,create,Default,Blocked-Devices,DenyMACPool
    """

    object_type: Literal["mac_pool"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    name: Annotated[str, BeforeValidator(strip_whitespace_and_validate_encoding)]
    pool_type: Annotated[
        Literal["MACPool", "DenyMACPool"],
        Field(default="MACPool", description="Pool type: MACPool or DenyMACPool"),
        BeforeValidator(strip_whitespace),
    ] = "MACPool"


class MACAddressRow(CSVRowBase):
    """
    MAC Address row model.

    MAC addresses can be registered globally or associated with a MAC pool.
    When associated with a pool, they control IP address allocation behavior.

    Example:
        row_id,object_type,action,config,mac_address,name,pool_name
        1,mac_address,create,Default,00:11:22:33:44:55,voip-phone-01,VoIP-Phones
        2,mac_address,create,Default,AA:BB:CC:DD:EE:FF,blocked-device,Blocked-Devices
        3,mac_address,create,Default,11:22:33:44:55:66,registered-mac,
    """

    object_type: Literal["mac_address"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    mac_address: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="MAC address (XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX format)"),
    ]
    name: Annotated[
        str | None,
        Field(default=None, description="Optional name for the MAC address"),
        BeforeValidator(strip_whitespace),
    ] = None
    pool_name: Annotated[
        str | None,
        Field(default=None, description="Optional MAC pool to associate with"),
        BeforeValidator(strip_whitespace),
    ] = None

    @field_validator("mac_address")
    @classmethod
    def validate_mac_address(cls, v: str) -> str:
        """Validate and normalize MAC address format."""
        import re

        if not v:
            raise ValueError("MAC address cannot be empty")

        # Remove common separators and convert to uppercase
        clean = v.upper().replace(":", "").replace("-", "").replace(".", "")

        # Validate length and characters
        if len(clean) != 12:
            raise ValueError(f"Invalid MAC address length: '{v}'")
        if not re.match(r"^[0-9A-F]{12}$", clean):
            raise ValueError(f"Invalid MAC address format: '{v}'")

        # Return in XX:XX:XX:XX:XX:XX format (BAM standard)
        return ":".join(clean[i : i + 2] for i in range(0, 12, 2))


class TagGroupRow(CSVRowBase):
    """
    Tag Group row model for organizing tags.

    Example:
        row_id,object_type,action,name
        1,tag_group,create,Environment
        2,tag_group,create,Owner
    """

    object_type: Literal["tag_group"]
    name: Annotated[str, BeforeValidator(strip_whitespace_and_validate_encoding)]


class TagRow(CSVRowBase):
    """
    Tag row model - tags must be created within a tag group.

    Example:
        row_id,object_type,action,name,tag_group
        1,tag,create,Production,Environment
        2,tag,create,Development,Environment
    """

    object_type: Literal["tag"]
    name: Annotated[str, BeforeValidator(strip_whitespace_and_validate_encoding)]
    tag_group: Annotated[
        str, BeforeValidator(strip_whitespace), Field(description="Required tag group name")
    ]


class ResourceTagRow(CSVRowBase):
    """
    Resource tagging row for associating tags with resources.

    Example:
        row_id,object_type,action,config,resource_type,resource_path,tag_name
        1,resource_tag,create,Default,ip4_network,10.1.0.0/24,Production
        2,resource_tag,delete,Default,dns_zone,example.com,Development
    """

    object_type: Literal["resource_tag"]
    config: Annotated[
        str, BeforeValidator(strip_whitespace), Field(description="Configuration name")
    ]
    resource_type: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="Resource type: ip4_network, ip4_block, dns_zone, etc."),
    ]
    resource_path: Annotated[
        str, BeforeValidator(strip_whitespace), Field(description="Path to resolve the resource")
    ]
    tag_name: Annotated[
        str, BeforeValidator(strip_whitespace), Field(description="Tag name to apply/remove")
    ]


# -----------------------------------------------------------------------------
# Device Management
# -----------------------------------------------------------------------------


class DeviceTypeRow(CSVRowBase):
    """
    Device Type row model (GLOBAL resource).

    Device types are global resources (not per-configuration) that categorize
    devices, such as Cisco, Fortinet, F5, etc.

    Example:
        row_id,object_type,action,name
        1,device_type,create,Fortinet
        2,device_type,create,Palo Alto
    """

    object_type: Literal["device_type"]
    name: Annotated[str, BeforeValidator(strip_whitespace_and_validate_encoding)]


class DeviceSubtypeRow(CSVRowBase):
    """
    Device Subtype row model.

    Device subtypes are specific models within a device type,
    such as FortiGate-600E under Fortinet or Catalyst-9300 under Cisco.

    Example:
        row_id,object_type,action,device_type,name
        1,device_subtype,create,Fortinet,FortiGate-600E
        2,device_subtype,create,Cisco,Catalyst-9300
    """

    object_type: Literal["device_subtype"]
    device_type: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="Parent device type name"),
    ]
    name: Annotated[str, BeforeValidator(strip_whitespace_and_validate_encoding)]


class DeviceRow(CSVRowBase):
    """
    Device row model.

    Devices represent physical or virtual network appliances such as
    firewalls, switches, routers, and servers.

    Example:
        row_id,object_type,action,config,name,device_type,device_subtype,addresses,mac_address
        1,device,create,Default,firewall-01,Fortinet,FortiGate-600E,10.0.1.1|10.0.2.1,00:11:22:33:44:55
        2,device,create,Default,switch-core-01,Cisco,Catalyst-9300,,
    """

    object_type: Literal["device"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    name: Annotated[str, BeforeValidator(strip_whitespace_and_validate_encoding)]
    device_type: Annotated[
        str | None,
        Field(default=None, description="Device type name"),
        BeforeValidator(strip_whitespace),
    ]
    device_subtype: Annotated[
        str | None,
        Field(default=None, description="Device subtype name"),
        BeforeValidator(strip_whitespace),
    ]
    addresses: Annotated[
        str | None,
        Field(default=None, description="Pipe-separated IP addresses to associate"),
        BeforeValidator(strip_whitespace),
    ]
    mac_address: Annotated[
        str | None,
        Field(default=None, description="MAC address for the device"),
        BeforeValidator(strip_whitespace),
    ]
    description: Annotated[
        str | None, Field(default=None), BeforeValidator(strip_whitespace_preserve_empty)
    ]

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: str | None) -> str | None:
        """
        Validate MAC address format.

        Args:
            v: The MAC address string to validate.

        Returns:
            Optional[str]: The validated MAC address string or None.

        Raises:
            ValueError: If the MAC address format is invalid.
        """
        if v:
            # MAC validation: XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX
            if not re.match(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$", v):
                raise ValueError(f"Invalid MAC address format: {v}")
        return v

    @field_validator("addresses")
    @classmethod
    def validate_addresses(cls, v: str | None) -> str | None:
        """
        Validate that all addresses in pipe-separated list are valid IPs.

        Args:
            v: The pipe-separated addresses string.

        Returns:
            str | None: The validated string or None.

        Raises:
            ValueError: If any address is invalid.
        """
        if not v:
            return v

        addresses = [addr.strip() for addr in v.split("|")]
        for addr in addresses:
            if not addr:  # Empty address
                continue
            try:
                # Try IPv4 first
                IPv4Address(addr)
            except ValueError:
                try:
                    # Try IPv6
                    IPv6Address(addr)
                except ValueError as e:
                    raise ValueError(f"Invalid IP address '{addr}': {e}") from e

        return v

    def get_address_list(self) -> list[str]:
        """
        Parse pipe-separated addresses into list.

        Returns:
            list[str]: List of IP address strings.
        """
        if not self.addresses:
            return []
        return [addr.strip() for addr in self.addresses.split("|") if addr.strip()]


class DeviceAddressRow(CSVRowBase):
    """
    Device-Address association row model.

    Used for linking existing IP addresses to existing devices (post-creation).

    Example:
        row_id,object_type,action,config,device_name,address
        1,device_address,create,Default,firewall-01,10.0.1.1
        2,device_address,delete,Default,firewall-01,10.0.3.1
    """

    object_type: Literal["device_address"]
    config: Annotated[str, BeforeValidator(strip_whitespace)]
    device_name: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="Name of the device to link address to"),
    ]
    address: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="IP address to link/unlink"),
    ]

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        """
        Validate IP address format.

        Args:
            v: The IP address string to validate.

        Returns:
            str: The validated IP address string.

        Raises:
            ValueError: If the IP address format is invalid.
        """
        if not v:
            raise ValueError("Address cannot be empty")
        try:
            # Try IPv4 first
            IPv4Address(v)
        except ValueError:
            try:
                # Try IPv6
                IPv6Address(v)
            except ValueError as e:
                raise ValueError(f"Invalid IP address '{v}': {e}") from e
        return v


# =============================================================================
# Access Rights Row
# =============================================================================


class AccessRightRow(CSVRowBase):
    """
    Access Right row model for managing user/group permissions on BAM resources.

    Access rights control what actions users and groups can perform on specific
    resources or resource types within BlueCat Address Manager.

    Fields:
        user_type: Type of user scope - "user" or "group"
        user_name: Username or group name to grant access to
        resource_type: Optional - BAM resource type (e.g., Configuration, IPv4Block)
        resource_path: Optional - Path to resolve the resource (e.g., config name, block CIDR)
        default_access_level: Access level - HIDE, VIEW, CHANGE, ADD, FULL
        deployments_allowed: Whether full deployments are allowed
        quick_deployments_allowed: Whether quick DNS deployments are allowed
        selective_deployments_allowed: Whether selective deployments are allowed
        workflow_level: Workflow level - NONE, RECOMMEND, APPROVE
        access_overrides: Pipe-separated type:level pairs for type-specific overrides

    Example - Grant VIEW access to a user on a specific configuration:
        row_id,object_type,action,user_type,user_name,resource_type,resource_path,default_access_level
        1,access_right,create,user,operator,Configuration,Default,VIEW

    Example - Grant ADD access to a group with deployment permissions:
        row_id,object_type,action,user_type,user_name,resource_type,resource_path,default_access_level,deployments_allowed,workflow_level
        2,access_right,create,group,NetworkAdmins,Configuration,Production,ADD,true,APPROVE

    Example - Default access right with type overrides:
        row_id,object_type,action,user_type,user_name,default_access_level,access_overrides
        3,access_right,create,user,developer,VIEW,IPv4Address:FULL|HostRecord:ADD
    """

    object_type: Literal["access_right"]
    user_type: Annotated[
        Literal["user", "group"],
        BeforeValidator(strip_whitespace),
        Field(description="Type of user scope - 'user' or 'group'"),
    ]
    user_name: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="Username or group name"),
    ]
    resource_type: Annotated[
        str | None,
        BeforeValidator(strip_whitespace),
        Field(
            default=None,
            description="BAM resource type (e.g., Configuration, IPv4Block, Zone)",
        ),
    ]
    resource_path: Annotated[
        str | None,
        BeforeValidator(strip_whitespace),
        Field(
            default=None,
            description="Path to resolve the resource (config name, block CIDR, etc.)",
        ),
    ]
    config: Annotated[
        str | None,
        BeforeValidator(strip_whitespace),
        Field(
            default=None,
            description="Configuration name (required when resource_type needs config context)",
        ),
    ]
    default_access_level: Annotated[
        Literal["HIDE", "VIEW", "CHANGE", "ADD", "FULL"],
        BeforeValidator(strip_whitespace),
        Field(description="Default access level for the user/group"),
    ]
    deployments_allowed: Annotated[
        bool,
        Field(
            default=False,
            description="Allow full deployments from configuration to managed servers",
        ),
    ]
    quick_deployments_allowed: Annotated[
        bool,
        Field(
            default=False,
            description="Allow instant deployment of changed DNS resource records",
        ),
    ]
    selective_deployments_allowed: Annotated[
        bool,
        Field(
            default=False,
            description="Allow selective deployments and dynamic DNS updates",
        ),
    ]
    workflow_level: Annotated[
        Literal["NONE", "RECOMMEND", "APPROVE"],
        BeforeValidator(strip_whitespace),
        Field(
            default="NONE",
            description="Workflow level - NONE, RECOMMEND, or APPROVE",
        ),
    ]
    access_overrides: Annotated[
        str | None,
        BeforeValidator(strip_whitespace),
        Field(
            default=None,
            description="Pipe-separated type:level pairs (e.g., 'IPv4Address:FULL|HostRecord:VIEW')",
        ),
    ]

    @field_validator("default_access_level", mode="before")
    @classmethod
    def normalize_access_level(cls, v: str | None) -> str | None:
        """Normalize access level to uppercase."""
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @field_validator("workflow_level", mode="before")
    @classmethod
    def normalize_workflow_level(cls, v: str | None) -> str:
        """Normalize workflow level to uppercase."""
        if v is None:
            return "NONE"
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @field_validator("user_type", mode="before")
    @classmethod
    def normalize_user_type(cls, v: str | None) -> str | None:
        """Normalize user type to lowercase."""
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip().lower()
        return v

    def get_access_overrides_list(self) -> list[dict[str, str]]:
        """
        Parse access_overrides into a list of override dictionaries.

        Format: "ResourceType:AccessLevel|ResourceType2:AccessLevel2"
        Example: "IPv4Address:FULL|HostRecord:VIEW"

        Returns:
            List of dicts with 'resourceType' and 'accessLevel' keys
        """
        if not self.access_overrides:
            return []
        overrides = []
        for override in self.access_overrides.split("|"):
            override = override.strip()
            if ":" in override:
                resource_type, access_level = override.split(":", 1)
                overrides.append(
                    {
                        "resourceType": resource_type.strip(),
                        "accessLevel": access_level.strip().upper(),
                    }
                )
        return overrides


# =============================================================================
# ACL (Access Control List) Row
# =============================================================================


class ACLRow(CSVRowBase):
    """
    Row for Access Control List management.

    ACLs define which hosts are allowed or denied access to DNS services.

    Fields:
        name: Name of the ACL (required)
        config: Configuration name (required)
        match_elements: Comma-separated list of IPs/CIDRs that define the ACL
    """

    object_type: Literal["acl"] = "acl"
    name: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="ACL name"),
    ]
    config: Annotated[
        str,
        BeforeValidator(strip_whitespace),
        Field(description="Configuration name"),
    ]
    match_elements: Annotated[
        str | None,
        BeforeValidator(strip_whitespace),
        Field(
            default=None,
            description="Pipe-separated IPs/CIDRs for ACL (e.g., '10.0.0.0/8|192.168.1.0/24')",
        ),
    ] = None

    def get_match_elements_list(self) -> list[str]:
        """
        Parse match_elements into a list.

        Uses pipe separation (|) consistent with other list fields in the system
        (addresses, interfaces, etc.).

        Returns:
            List of match element strings (IPs/CIDRs)
        """
        if not self.match_elements:
            return []
        return [elem.strip() for elem in self.match_elements.split("|") if elem.strip()]


# Discriminated union for all row types
# Type aliases for better organization and readability
IPResourceRow = (
    IP4BlockRow
    | IP4GroupRow
    | IP4NetworkRow
    | IP4AddressRow
    | IP6BlockRow
    | IP6NetworkRow
    | IP6AddressRow
)

DNSResourceRow = (
    DNSZoneRow
    | HostRecordRow
    | AliasRecordRow
    | MXRecordRow
    | TXTRecordRow
    | SRVRecordRow
    | ExternalHostRecordRow
    | GenericRecordRow
)

DHCPResourceRow = IPv4DHCPRangeRow | IPv6DHCPRangeRow | DHCPDeploymentRoleRow

DeploymentOptionRow = DHCPv4ClientDeploymentOptionRow | DHCPv4ServiceDeploymentOptionRow

DeploymentRow = DHCPDeploymentRoleRow | DNSDeploymentRoleRow

LocationResourceRow = LocationRow

UDFResourceRow = UDFDefinitionRow | UDLDefinitionRow | UserDefinedLinkRow

MACResourceRow = MACPoolRow | MACAddressRow

TagResourceRow = TagGroupRow | TagRow | ResourceTagRow

DeviceResourceRow = DeviceTypeRow | DeviceSubtypeRow | DeviceRow | DeviceAddressRow

ACLResourceRow = ACLRow

AccessRightResourceRow = AccessRightRow

# Combine into main discriminated union
CSVRow = Annotated[
    IPResourceRow
    | DNSResourceRow
    | DHCPResourceRow
    | DeploymentOptionRow
    | DeploymentRow
    | LocationResourceRow
    | UDFResourceRow
    | MACResourceRow
    | TagResourceRow
    | DeviceResourceRow
    | ACLResourceRow
    | AccessRightResourceRow,
    Field(discriminator="object_type"),
]
