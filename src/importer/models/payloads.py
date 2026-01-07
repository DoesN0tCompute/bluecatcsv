"""Type-Safe Pydantic Models for BAM REST API v2 Payloads.

This module provides Pydantic models for all BAM API request payloads,
ensuring type validation before API calls and providing IDE autocomplete.

Usage:
    from importer.models.payloads import IPv4BlockPayload

    payload = IPv4BlockPayload(name="Example Block", range="10.0.0.0/8")
    await client.post(endpoint, json=payload.model_dump(exclude_none=True))
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class BAMResourcePayload(BaseModel):
    """Base model for all BAM resource payloads."""

    type: str = Field(..., description="BAM resource type discriminator")
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Additional resource properties"
    )
    userDefinedFields: dict[str, Any] = Field(
        default_factory=dict, description="User-defined fields (UDFs)"
    )

    model_config = {"extra": "allow"}

    def merge_properties(self, additional: dict[str, Any] | None) -> None:
        """Merge additional properties into the payload."""
        if additional:
            self.properties.update(additional)


# -----------------------------------------------------------------------------
# IPv4 Block Payloads
# -----------------------------------------------------------------------------


class IPv4BlockPayload(BAMResourcePayload):
    """Payload for creating IPv4 blocks."""

    type: Literal["IPv4Block"] = "IPv4Block"
    name: str = Field(..., min_length=1, description="Block name")
    range: str = Field(..., description="CIDR notation (e.g., '10.0.0.0/8')")

    @field_validator("range")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        """Validate CIDR notation format."""
        import ipaddress

        try:
            ipaddress.ip_network(v, strict=False)
        except ValueError as e:
            raise ValueError(f"Invalid CIDR notation: {v}") from e
        return v


# -----------------------------------------------------------------------------
# IPv4 Network Payloads
# -----------------------------------------------------------------------------


class IPv4NetworkPayload(BAMResourcePayload):
    """Payload for creating IPv4 networks."""

    type: Literal["IPv4Network"] = "IPv4Network"
    name: str = Field(..., min_length=1, description="Network name")
    range: str = Field(..., description="CIDR notation (e.g., '10.0.0.0/24')")

    @field_validator("range")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        """Validate CIDR notation format."""
        import ipaddress

        try:
            ipaddress.ip_network(v, strict=False)
        except ValueError as e:
            raise ValueError(f"Invalid CIDR notation: {v}") from e
        return v


# -----------------------------------------------------------------------------
# IPv4 Address Payloads
# -----------------------------------------------------------------------------


class MACAddressPayload(BaseModel):
    """MAC address payload structure."""

    address: str = Field(..., description="MAC address (format: XX-XX-XX-XX-XX-XX)")

    @field_validator("address")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        """Validate and normalize MAC address format."""
        import re

        # Remove any non-hex characters
        clean = re.sub(r"[^0-9a-fA-F]", "", v)
        if len(clean) != 12:
            raise ValueError(f"Invalid MAC address: {v}")
        # Format with dashes (BAM format)
        return "-".join(clean[i : i + 2].upper() for i in range(0, 12, 2))


class IPv4AddressPayload(BAMResourcePayload):
    """Payload for creating IPv4 addresses."""

    type: Literal["IPv4Address"] = "IPv4Address"
    address: str = Field(..., description="IP address string (e.g., '10.0.0.1')")
    state: str = Field(
        default="STATIC",
        description="Address state (STATIC, RESERVED, DHCP_RESERVED, GATEWAY)",
    )
    name: str | None = Field(default=None, description="Optional address name")
    macAddress: MACAddressPayload | None = Field(default=None, description="Optional MAC address")

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        """Validate IP address format."""
        import ipaddress

        try:
            ipaddress.ip_address(v)
        except ValueError as e:
            raise ValueError(f"Invalid IP address: {v}") from e
        return v

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        """Validate address state."""
        valid_states = {"STATIC", "RESERVED", "DHCP_RESERVED", "GATEWAY", "DHCP_ALLOCATED"}
        if v not in valid_states:
            raise ValueError(f"Invalid state: {v}. Must be one of {valid_states}")
        return v


# -----------------------------------------------------------------------------
# DHCP Range Payloads
# -----------------------------------------------------------------------------


class IPv4DHCPRangePayload(BAMResourcePayload):
    """Payload for creating IPv4 DHCP ranges."""

    type: Literal["IPv4DHCPRange"] = "IPv4DHCPRange"
    name: str | None = Field(default=None, description="Range name")
    range: str = Field(..., description="Range in 'start-end' format (e.g., '10.0.0.10-10.0.0.50')")
    start: str | None = Field(default=None, description="Start IP address")
    end: str | None = Field(default=None, description="End IP address")
    splitAroundStaticAddresses: bool = Field(
        default=False, description="Split range around static addresses"
    )
    lowWaterMark: int | None = Field(
        default=None, ge=0, le=100, description="Low water mark percentage"
    )
    highWaterMark: int | None = Field(
        default=None, ge=0, le=100, description="High water mark percentage"
    )


# -----------------------------------------------------------------------------
# DNS Zone Payloads
# -----------------------------------------------------------------------------


class ZonePayload(BAMResourcePayload):
    """Payload for creating DNS zones."""

    type: Literal["Zone"] = "Zone"
    absoluteName: str = Field(..., min_length=1, description="Zone absolute name (FQDN)")


# -----------------------------------------------------------------------------
# DNS Record Payloads
# -----------------------------------------------------------------------------


class AddressObject(BaseModel):
    """IP address object for host records."""

    type: Literal["IPv4Address", "IPv6Address"]
    address: str

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        """Validate IP address format."""
        import ipaddress

        try:
            ipaddress.ip_address(v)
        except ValueError as e:
            raise ValueError(f"Invalid IP address: {v}") from e
        return v


class LinkedRecordRef(BaseModel):
    """Reference to a linked record (for CNAME, MX, SRV targets)."""

    type: str = Field(default="HostRecord", description="Target record type")
    absoluteName: str = Field(..., min_length=1, description="Target record FQDN")


class HostRecordPayload(BAMResourcePayload):
    """Payload for creating Host records."""

    type: Literal["HostRecord"] = "HostRecord"
    name: str = Field(..., min_length=1, description="Hostname")
    addresses: list[AddressObject] = Field(..., min_length=1, description="List of IP addresses")
    reverseRecord: bool = Field(default=False, description="Create reverse record")
    ttl: int | None = Field(default=None, ge=0, description="TTL in seconds")
    comment: str | None = Field(default=None, description="Record comment")


class AliasRecordPayload(BAMResourcePayload):
    """Payload for creating Alias (CNAME) records."""

    type: Literal["AliasRecord"] = "AliasRecord"
    name: str = Field(..., min_length=1, description="Alias name")
    linkedRecord: LinkedRecordRef = Field(..., description="Target record reference")
    ttl: int | None = Field(default=None, ge=0, description="TTL in seconds")
    comment: str | None = Field(default=None, description="Record comment")


class MXRecordPayload(BAMResourcePayload):
    """Payload for creating MX records."""

    type: Literal["MXRecord"] = "MXRecord"
    name: str = Field(..., description="Record name (e.g., '@' for zone apex)")
    linkedRecord: LinkedRecordRef = Field(..., description="Mail server reference")
    priority: int = Field(
        ..., ge=0, le=2147483647, description="MX priority (lower = higher priority)"
    )
    ttl: int | None = Field(default=None, ge=0, description="TTL in seconds")
    comment: str | None = Field(default=None, description="Record comment")


class TXTRecordPayload(BAMResourcePayload):
    """Payload for creating TXT records."""

    type: Literal["TXTRecord"] = "TXTRecord"
    name: str = Field(..., min_length=1, description="Record name")
    text: str = Field(..., min_length=1, description="TXT record content")
    ttl: int | None = Field(default=None, ge=0, description="TTL in seconds")
    comment: str | None = Field(default=None, description="Record comment")


class SRVRecordPayload(BAMResourcePayload):
    """Payload for creating SRV records."""

    type: Literal["SRVRecord"] = "SRVRecord"
    name: str = Field(..., min_length=1, description="Service name (e.g., '_sip._tcp')")
    linkedRecord: LinkedRecordRef = Field(..., description="Target host reference")
    priority: int = Field(
        ..., ge=0, le=2147483647, description="Priority (lower = higher priority)"
    )
    weight: int = Field(..., ge=0, le=2147483647, description="Weight for load balancing")
    port: int = Field(..., ge=0, le=65535, description="Port number")
    ttl: int | None = Field(default=None, ge=0, description="TTL in seconds")
    comment: str | None = Field(default=None, description="Record comment")


class ViewRef(BaseModel):
    """Reference to a View."""

    id: int = Field(..., description="View ID")


class ExternalHostRecordPayload(BAMResourcePayload):
    """Payload for creating External Host records."""

    type: Literal["ExternalHostRecord"] = "ExternalHostRecord"
    name: str = Field(..., min_length=1, description="External host FQDN")
    view: ViewRef = Field(..., description="View reference")
    ttl: int | None = Field(default=None, ge=0, description="TTL in seconds")
    comment: str | None = Field(default=None, description="Record comment")


class GenericRecordPayload(BAMResourcePayload):
    """Payload for creating Generic DNS records.

    Generic records allow creating DNS record types not natively supported,
    such as SSHFP, TLSA, CAA, DS, DNAME, etc.
    """

    type: Literal["GenericRecord"] = "GenericRecord"
    name: str = Field(..., min_length=1, description="Record name")
    recordType: str = Field(..., description="DNS record type (e.g., SSHFP, TLSA, CAA)")
    rdata: str = Field(..., min_length=1, description="Raw record data in zone file format")
    ttl: int | None = Field(default=None, ge=0, description="TTL in seconds")
    comment: str | None = Field(default=None, description="Record comment")

    @field_validator("recordType")
    @classmethod
    def validate_record_type(cls, v: str) -> str:
        """Validate record type is uppercase."""
        valid_types = {
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
        v_upper = v.upper()
        if v_upper not in valid_types:
            raise ValueError(f"Invalid record type: {v}")
        return v_upper


# -----------------------------------------------------------------------------
# Deployment Role Payloads
# -----------------------------------------------------------------------------


class InterfaceRef(BaseModel):
    """Reference to a server interface."""

    id: int = Field(..., description="Interface ID")


class DHCPDeploymentRolePayload(BAMResourcePayload):
    """Payload for creating DHCP deployment roles."""

    type: Literal["DHCPDeploymentRole"] = "DHCPDeploymentRole"
    name: str | None = Field(default=None, description="Role name")
    roleType: str = Field(..., description="Role type (e.g., 'MASTER', 'FAILOVER')")
    interfaces: list[InterfaceRef] | None = Field(default=None, description="Server interfaces")


class DNSDeploymentRolePayload(BAMResourcePayload):
    """Payload for creating DNS deployment roles."""

    type: Literal["DNSDeploymentRole"] = "DNSDeploymentRole"
    name: str | None = Field(default=None, description="Role name")
    roleType: str = Field(..., description="Role type (e.g., 'PRIMARY', 'SECONDARY')")
    interfaces: list[InterfaceRef] = Field(..., description="Server interfaces")
    nsRecordTtl: int | None = Field(default=None, ge=0, description="NS record TTL")


# -----------------------------------------------------------------------------
# Deployment Option Payloads
# -----------------------------------------------------------------------------


class DHCPv4ClientOptionPayload(BaseModel):
    """Payload for creating DHCPv4 client deployment options."""

    type: Literal["DHCPv4ClientOption"] = "DHCPv4ClientOption"
    name: str = Field(..., min_length=1, description="Option name")
    code: int = Field(..., ge=1, le=254, description="DHCP option code (1-254)")
    value: Any = Field(..., description="Option value (string, list, int, bool)")
    serverScope: str = Field(
        default="DHCP_SERVER",
        description="Server scope (DHCP_SERVER, DNS_SERVER, ALL_SERVERS, DHCP_CLIENT)",
    )

    @field_validator("serverScope")
    @classmethod
    def validate_server_scope(cls, v: str) -> str:
        """Validate server scope value."""
        valid_scopes = {"DHCP_SERVER", "DNS_SERVER", "ALL_SERVERS", "DHCP_CLIENT"}
        if v not in valid_scopes:
            raise ValueError(f"Invalid server scope: {v}. Must be one of {valid_scopes}")
        return v


class DHCPv4ServiceOptionPayload(BaseModel):
    """Payload for creating DHCPv4 service deployment options."""

    type: Literal["DHCPv4ServiceOption"] = "DHCPv4ServiceOption"
    name: str = Field(..., min_length=1, description="Option name")
    code: int = Field(..., ge=1, le=254, description="DHCP option code (1-254)")
    value: Any = Field(..., description="Option value (string, list, int, bool)")
    serverScope: str = Field(
        default="DHCP_SERVER",
        description="Server scope (DHCP_SERVER, DNS_SERVER, ALL_SERVERS)",
    )

    @field_validator("serverScope")
    @classmethod
    def validate_server_scope(cls, v: str) -> str:
        """Validate server scope value."""
        valid_scopes = {"DHCP_SERVER", "DNS_SERVER", "ALL_SERVERS"}
        if v not in valid_scopes:
            raise ValueError(f"Invalid server scope: {v}. Must be one of {valid_scopes}")
        return v


# -----------------------------------------------------------------------------
# User-Defined Field (UDF) Payloads
# -----------------------------------------------------------------------------


class UDFDefinitionPayload(BaseModel):
    """Payload for creating User-Defined Field definitions.

    UDF definitions describe custom metadata fields that can be attached to
    various BAM resource types.
    """

    name: str = Field(..., min_length=1, description="UDF internal name (no spaces)")
    displayName: str | None = Field(default=None, description="Human-readable display name")
    type: Literal["TEXT", "MULTILINE_TEXT", "URL", "EMAIL", "PHONE"] = Field(
        ..., description="Field type"
    )
    defaultValue: str | None = Field(default=None, description="Default value for the field")
    required: bool = Field(default=False, description="Whether field is required")
    resourceTypes: list[str] = Field(
        default_factory=list,
        description="List of resource types this UDF applies to",
    )
    predefinedValues: list[str] | None = Field(
        default=None, description="Allowed values for dropdown fields"
    )
    hideFromSearch: bool = Field(default=False, description="Hide from search results")
    renderAsLink: bool = Field(default=False, description="Render value as clickable link")
    validators: str | None = Field(default=None, description="Regex validation pattern")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate UDF name format."""
        if " " in v:
            raise ValueError(f"UDF name cannot contain spaces: '{v}'")
        if not v[0].isalpha():
            raise ValueError(f"UDF name must start with a letter: '{v}'")
        return v


class UDLDefinitionPayload(BaseModel):
    """Payload for creating User-Defined Link definitions.

    UDL definitions describe custom links that can be created between
    BAM resource types.
    """

    name: str = Field(..., min_length=1, description="UDL internal name")
    displayName: str | None = Field(default=None, description="Human-readable display name")
    sourceTypes: list[str] = Field(..., min_length=1, description="Source resource types")
    destinationTypes: list[str] = Field(..., min_length=1, description="Destination resource types")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate UDL name format."""
        if " " in v:
            raise ValueError(f"UDL name cannot contain spaces: '{v}'")
        return v


# -----------------------------------------------------------------------------
# Device Payloads
# -----------------------------------------------------------------------------


class InlinedAddress(BaseModel):
    """Inlined address reference for device creation."""

    type: Literal["IPv4Address", "IPv6Address"]
    id: int | None = Field(default=None, description="Address ID (for linking existing)")
    address: str | None = Field(default=None, description="Address string (for inline creation)")


class InlinedDeviceType(BaseModel):
    """Inlined device type reference."""

    type: Literal["DeviceType"] = "DeviceType"
    id: int = Field(..., description="Device type ID")


class InlinedDeviceSubtype(BaseModel):
    """Inlined device subtype reference."""

    type: Literal["DeviceSubtype"] = "DeviceSubtype"
    id: int = Field(..., description="Device subtype ID")


class DevicePayload(BaseModel):
    """Payload for creating/updating devices.

    Devices represent physical or virtual network appliances such as
    firewalls, switches, routers, and servers.
    """

    type: Literal["Device"] = "Device"
    name: str = Field(..., min_length=1, description="Device name")
    deviceType: InlinedDeviceType | None = Field(default=None, description="Device type reference")
    deviceSubtype: InlinedDeviceSubtype | None = Field(
        default=None, description="Device subtype reference"
    )
    addresses: list[InlinedAddress] | None = Field(
        default=None, description="List of addresses to associate"
    )
    userDefinedFields: dict[str, Any] | None = Field(
        default=None, description="User-defined fields"
    )


class DeviceTypePayload(BaseModel):
    """Payload for creating device types.

    Device types are global resources (not per-configuration) that categorize
    devices, such as Cisco, Fortinet, F5, etc.
    """

    type: Literal["DeviceType"] = "DeviceType"
    name: str = Field(..., min_length=1, description="Device type name")
    userDefinedFields: dict[str, Any] | None = Field(
        default=None, description="User-defined fields"
    )


class DeviceSubtypePayload(BaseModel):
    """Payload for creating device subtypes.

    Device subtypes are specific models within a device type,
    such as FortiGate-600E under Fortinet or Catalyst-9300 under Cisco.
    """

    type: Literal["DeviceSubtype"] = "DeviceSubtype"
    name: str = Field(..., min_length=1, description="Device subtype name")
    userDefinedFields: dict[str, Any] | None = Field(
        default=None, description="User-defined fields"
    )


class DeviceAddressLinkPayload(BaseModel):
    """Payload for linking an address to a device.

    Used with POST /devices/{id}/addresses to associate an existing
    IP address with a device.
    """

    type: Literal["IPv4Address", "IPv6Address"]
    id: int = Field(..., description="Address ID to link")


# -----------------------------------------------------------------------------
# Access Right Payloads
# -----------------------------------------------------------------------------


class UserScopeRef(BaseModel):
    """Reference to a user or user group for access rights."""

    type: Literal["User", "UserGroup"]
    id: int = Field(..., description="User or group ID")


class ResourceRef(BaseModel):
    """Reference to a BAM resource for access rights."""

    type: str = Field(..., description="Resource type (e.g., Configuration, IPv4Block)")
    id: int = Field(..., description="Resource ID")


class AccessOverride(BaseModel):
    """Access level override for a specific resource type."""

    resourceType: str = Field(..., description="Resource type to override")
    accessLevel: Literal["HIDE", "VIEW", "CHANGE", "ADD", "FULL"] = Field(
        ..., description="Access level for this resource type"
    )


class AccessRightPayload(BaseModel):
    """Payload for creating/updating access rights.

    Access rights control what actions users and groups can perform
    on specific resources or resource types in BAM.
    """

    type: Literal["AccessRight"] = "AccessRight"
    userScope: UserScopeRef = Field(..., description="User or group to grant access to")
    resource: ResourceRef | None = Field(
        default=None, description="Specific resource (optional - for resource-level access)"
    )
    defaultAccessLevel: Literal["HIDE", "VIEW", "CHANGE", "ADD", "FULL"] = Field(
        ..., description="Default access level"
    )
    deploymentsAllowed: bool = Field(default=False, description="Allow full deployments")
    quickDeploymentsAllowed: bool = Field(default=False, description="Allow quick DNS deployments")
    selectiveDeploymentsAllowed: bool = Field(
        default=False, description="Allow selective deployments"
    )
    workflowLevel: Literal["NONE", "RECOMMEND", "APPROVE"] = Field(
        default="NONE", description="Workflow level"
    )
    accessOverrides: list[AccessOverride] = Field(
        default_factory=list, description="Type-specific access overrides"
    )


class AccessRightUpdatePayload(BaseModel):
    """Payload for updating access rights (PUT requires all fields)."""

    defaultAccessLevel: Literal["HIDE", "VIEW", "CHANGE", "ADD", "FULL"] = Field(
        ..., description="Default access level"
    )
    deploymentsAllowed: bool = Field(..., description="Allow full deployments")
    quickDeploymentsAllowed: bool = Field(..., description="Allow quick DNS deployments")
    selectiveDeploymentsAllowed: bool = Field(..., description="Allow selective deployments")
    workflowLevel: Literal["NONE", "RECOMMEND", "APPROVE"] = Field(
        ..., description="Workflow level"
    )
    accessOverrides: list[AccessOverride] = Field(..., description="Type-specific access overrides")
