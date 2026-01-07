"""Configuration constants for the BlueCat CSV Importer.

QUALITY-002: Named constants for magic numbers and configuration values,
improving code readability and maintainability.
"""

# -----------------------------------------------------------------------------
# Pagination Limits
# -----------------------------------------------------------------------------

# Default number of items per page in API requests
DEFAULT_PAGE_SIZE: int = 100

# Maximum page size for API requests
MAX_PAGE_SIZE: int = 1000


# Supported CSV schema versions
# Used by parser to warn about unsupported versions
SUPPORTED_CSV_VERSIONS: frozenset[str] = frozenset({"3.0", "3"})


# -----------------------------------------------------------------------------
# Resource Type Mappings
# -----------------------------------------------------------------------------
# Centralized type mappings to ensure consistency across the codebase.
# Previously scattered across client.py, resolver.py, and handlers.py.

# Maps snake_case CSV object types to PascalCase BAM API type names.
# Used by handlers and operation factory when constructing API payloads.
CSV_TO_BAM_TYPE_MAP: dict[str, str] = {
    # IPv4 types
    "ip4_block": "IPv4Block",
    "ip4_group": "IPv4Group",
    "ip4_network": "IPv4Network",
    "ip4_address": "IPv4Address",
    "ipv4_dhcp_range": "IPv4DHCPRange",
    # IPv6 types
    "ip6_block": "IPv6Block",
    "ip6_network": "IPv6Network",
    "ip6_address": "IPv6Address",
    "ipv6_dhcp_range": "IPv6DHCPRange",
    # Deployment roles
    "dhcp_deployment_role": "DHCPDeploymentRole",
    "dns_deployment_role": "DNSDeploymentRole",
    # DNS types
    "dns_zone": "DNSZone",
    "host_record": "HostRecord",
    "alias_record": "AliasRecord",
    "mx_record": "MXRecord",
    "txt_record": "TXTRecord",
    "srv_record": "SRVRecord",
    "external_host_record": "ExternalHostRecord",
    "generic_record": "GenericRecord",
    # Infrastructure
    "configuration": "Configuration",
    "view": "View",
    # Access Rights
    "access_right": "AccessRight",
    # Short aliases for convenience (explicit IPv4 only)
    "block": "IPv4Block",
    "network": "IPv4Network",
    "address": "IPv4Address",
}

# Maps PascalCase BAM API types to snake_case safety registry keys.
# Used by delete_entity_by_id for safety checks against PROTECTED_RESOURCE_TYPES.
BAM_TO_SAFETY_TYPE_MAP: dict[str, str] = {
    "IPv4Block": "ip4_block",
    "IPv4Network": "ip4_network",
    "IPv6Block": "ip6_block",
    "IPv6Network": "ip6_network",
    "DNSZone": "dns_zone",
    "Zone": "dns_zone",  # Alias
    "Configuration": "configuration",
    "View": "view",
}

# Maps various type aliases to canonical names for path resolution.
# Used by Resolver._query_bam when looking up resources.
RESOLVER_TYPE_MAP: dict[str, str] = {
    "block": "IPv4Block",
    "ip4_block": "IPv4Block",
    "ip4_group": "IPv4Group",
    "network": "IPv4Network",
    "ip4_network": "IPv4Network",
    "ip6_network": "IPv6Network",
    "ip6_block": "IPv6Block",
    "view": "View",
    "zone": "Zone",
    "dns_zone": "Zone",
    "configuration": "Configuration",
    "config": "Configuration",
    "dns_deployment_role": "dns_deployment_role",
    "location": "Location",
}
