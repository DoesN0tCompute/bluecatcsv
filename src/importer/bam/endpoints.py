"""Centralized API Endpoint Configuration for BlueCat Address Manager REST API v2.

This module provides a single source of truth for all BAM API endpoint paths,
reducing the risk of typos and making API version upgrades easier to manage.

Usage:
    from importer.bam.endpoints import BAMEndpoints

    endpoint = BAMEndpoints.BLOCK_NETWORKS.format(block_id=123)
    # Returns: "blocks/123/networks"
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BAMEndpoints:
    """
    Centralized BAM REST API v2 endpoint constants.

    All endpoints are relative to the base API URL (e.g., /api/v2/).
    Use .format() method to substitute path parameters.

    Example:
        endpoint = BAMEndpoints.BLOCK_BY_ID.format(block_id=123)
        # Result: "blocks/123"
    """

    # -------------------------------------------------------------------------
    # Authentication
    # -------------------------------------------------------------------------
    SESSIONS: str = "sessions"

    # -------------------------------------------------------------------------
    # Configurations
    # -------------------------------------------------------------------------
    CONFIGURATIONS: str = "configurations"
    CONFIGURATION_BY_ID: str = "configurations/{config_id}"
    CONFIGURATION_BLOCKS: str = "configurations/{config_id}/blocks"
    CONFIGURATION_VIEWS: str = "configurations/{config_id}/views"

    # -------------------------------------------------------------------------
    # Blocks
    # -------------------------------------------------------------------------
    BLOCKS: str = "blocks"
    BLOCK_BY_ID: str = "blocks/{block_id}"
    BLOCK_NETWORKS: str = "blocks/{block_id}/networks"
    BLOCK_SUB_BLOCKS: str = "blocks/{block_id}/blocks"

    # -------------------------------------------------------------------------
    # Networks
    # -------------------------------------------------------------------------
    NETWORKS: str = "networks"
    NETWORK_BY_ID: str = "networks/{network_id}"
    NETWORK_ADDRESSES: str = "networks/{network_id}/addresses"
    NETWORK_RANGES: str = "networks/{network_id}/ranges"
    NETWORK_DEPLOYMENT_OPTIONS: str = "networks/{network_id}/deploymentOptions"
    NETWORK_DEPLOYMENT_ROLES: str = "networks/{network_id}/deploymentRoles"
    NETWORK_IP_GROUPS: str = "networks/{network_id}/ipGroups"

    # -------------------------------------------------------------------------
    # IP Groups
    # -------------------------------------------------------------------------
    IP_GROUPS: str = "ipGroups"
    IP_GROUP_BY_ID: str = "ipGroups/{ip_group_id}"

    # -------------------------------------------------------------------------
    # Addresses
    # -------------------------------------------------------------------------
    ADDRESSES: str = "addresses"
    ADDRESS_BY_ID: str = "addresses/{address_id}"

    # -------------------------------------------------------------------------
    # Views
    # -------------------------------------------------------------------------
    VIEWS: str = "views"
    VIEW_BY_ID: str = "views/{view_id}"
    VIEW_ZONES: str = "views/{view_id}/zones"
    VIEW_DEPLOYMENT_ROLES: str = "views/{view_id}/deploymentRoles"

    # -------------------------------------------------------------------------
    # Zones
    # -------------------------------------------------------------------------
    ZONES: str = "zones"
    ZONE_BY_ID: str = "zones/{zone_id}"
    ZONE_SUB_ZONES: str = "zones/{zone_id}/zones"
    ZONE_RESOURCE_RECORDS: str = "zones/{zone_id}/resourceRecords"
    ZONE_DEPLOYMENT_ROLES: str = "zones/{zone_id}/deploymentRoles"

    # -------------------------------------------------------------------------
    # Resource Records
    # -------------------------------------------------------------------------
    RESOURCE_RECORDS: str = "resourceRecords"
    RESOURCE_RECORD_BY_ID: str = "resourceRecords/{record_id}"

    # -------------------------------------------------------------------------
    # DHCP
    # -------------------------------------------------------------------------
    RANGES: str = "ranges"
    RANGE_BY_ID: str = "ranges/{range_id}"

    # -------------------------------------------------------------------------
    # Deployment Options
    # -------------------------------------------------------------------------
    DEPLOYMENT_OPTIONS: str = "deploymentOptions"
    DEPLOYMENT_OPTION_BY_ID: str = "deploymentOptions/{option_id}"

    # -------------------------------------------------------------------------
    # Deployment Roles
    # -------------------------------------------------------------------------
    DEPLOYMENT_ROLES: str = "deploymentRoles"
    DEPLOYMENT_ROLE_BY_ID: str = "deploymentRoles/{role_id}"

    # -------------------------------------------------------------------------
    # Servers
    # -------------------------------------------------------------------------
    SERVERS: str = "servers"
    SERVER_BY_ID: str = "servers/{server_id}"
    SERVER_INTERFACES: str = "servers/{server_id}/interfaces"

    # -------------------------------------------------------------------------
    # Locations
    # -------------------------------------------------------------------------
    LOCATIONS: str = "locations"
    LOCATION_BY_ID: str = "locations/{location_id}"
    LOCATION_CHILD_LOCATIONS: str = "locations/{location_id}/locations"
    LOCATION_ANNOTATED_RESOURCES: str = "locations/{location_id}/annotatedResources"

    # -------------------------------------------------------------------------
    # User-Defined Fields (UDFs)
    # -------------------------------------------------------------------------
    UDF_DEFINITIONS: str = "userDefinedFieldDefinitions"
    UDF_DEFINITION_BY_ID: str = "userDefinedFieldDefinitions/{udf_id}"

    # -------------------------------------------------------------------------
    # User-Defined Links (UDLs)
    # -------------------------------------------------------------------------
    UDL_DEFINITIONS: str = "userDefinedLinkDefinitions"
    UDL_DEFINITION_BY_ID: str = "userDefinedLinkDefinitions/{udl_id}"
    UDL_DEFINITION_LINKED_RESOURCES: str = "userDefinedLinkDefinitions/{udl_id}/linkedResources"

    # User-Defined Link instances (actual links between resources)
    # Format: {collection}/{collectionId}/userDefinedLinks
    # Supported collections: addresses, blocks, devices, ipGroups, macAddresses,
    #                       macPools, networks, ranges, serverGroups, servers, views, zones
    RESOURCE_USER_DEFINED_LINKS: str = "{collection}/{resource_id}/userDefinedLinks"
    RESOURCE_USER_DEFINED_LINK_BY_ID: str = "{collection}/{resource_id}/userDefinedLinks/{link_id}"

    # -------------------------------------------------------------------------
    # MAC Pools
    # -------------------------------------------------------------------------
    MAC_POOLS: str = "macPools"
    MAC_POOL_BY_ID: str = "macPools/{pool_id}"
    CONFIGURATION_MAC_POOLS: str = "configurations/{config_id}/macPools"
    MAC_POOL_MAC_ADDRESSES: str = "macPools/{pool_id}/macAddresses"

    # -------------------------------------------------------------------------
    # MAC Addresses
    # -------------------------------------------------------------------------
    MAC_ADDRESSES: str = "macAddresses"
    MAC_ADDRESS_BY_ID: str = "macAddresses/{mac_id}"
    CONFIGURATION_MAC_ADDRESSES: str = "configurations/{config_id}/macAddresses"

    # -------------------------------------------------------------------------
    # Tags & Tag Groups
    # -------------------------------------------------------------------------
    TAGS: str = "tags"
    TAG_BY_ID: str = "tags/{tag_id}"
    TAG_GROUPS: str = "tagGroups"
    TAG_GROUP_BY_ID: str = "tagGroups/{tag_group_id}"
    TAG_GROUP_TAGS: str = "tagGroups/{tag_group_id}/tags"

    # Resource tagging endpoints
    NETWORK_TAGS: str = "networks/{network_id}/tags"
    BLOCK_TAGS: str = "blocks/{block_id}/tags"
    ZONE_TAGS: str = "zones/{zone_id}/tags"
    ADDRESS_TAGS: str = "addresses/{address_id}/tags"

    # -------------------------------------------------------------------------
    # Access Rights
    # -------------------------------------------------------------------------
    ACCESS_RIGHTS: str = "accessRights"
    ACCESS_RIGHT_BY_ID: str = "accessRights/{access_right_id}"

    # -------------------------------------------------------------------------
    # Users and Groups
    # -------------------------------------------------------------------------
    USERS: str = "users"
    USER_BY_ID: str = "users/{user_id}"
    GROUPS: str = "groups"
    GROUP_BY_ID: str = "groups/{group_id}"

    # -------------------------------------------------------------------------
    # Devices
    # -------------------------------------------------------------------------
    DEVICES: str = "devices"
    DEVICE_BY_ID: str = "devices/{device_id}"
    DEVICE_ADDRESSES: str = "devices/{device_id}/addresses"
    DEVICE_ADDRESS_BY_ID: str = "devices/{device_id}/addresses/{address_id}"
    CONFIGURATION_DEVICES: str = "configurations/{config_id}/devices"

    # -------------------------------------------------------------------------
    # Device Types (GLOBAL - not per-configuration)
    # -------------------------------------------------------------------------
    DEVICE_TYPES: str = "deviceTypes"
    DEVICE_TYPE_BY_ID: str = "deviceTypes/{type_id}"
    DEVICE_SUBTYPES: str = "deviceSubtypes"
    DEVICE_SUBTYPE_BY_ID: str = "deviceSubtypes/{subtype_id}"
    DEVICE_TYPE_SUBTYPES: str = "deviceTypes/{type_id}/deviceSubtypes"

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------
    @classmethod
    def configuration_blocks(cls, config_id: int) -> str:
        """Get blocks endpoint for a configuration."""
        return cls.CONFIGURATION_BLOCKS.format(config_id=config_id)

    @classmethod
    def configuration_views(cls, config_id: int) -> str:
        """Get views endpoint for a configuration."""
        return cls.CONFIGURATION_VIEWS.format(config_id=config_id)

    @classmethod
    def block_by_id(cls, block_id: int) -> str:
        """Get endpoint for a specific block."""
        return cls.BLOCK_BY_ID.format(block_id=block_id)

    @classmethod
    def block_networks(cls, block_id: int) -> str:
        """Get networks endpoint for a block."""
        return cls.BLOCK_NETWORKS.format(block_id=block_id)

    @classmethod
    def block_sub_blocks(cls, block_id: int) -> str:
        """Get sub-blocks endpoint for a block."""
        return cls.BLOCK_SUB_BLOCKS.format(block_id=block_id)

    @classmethod
    def network_by_id(cls, network_id: int) -> str:
        """Get endpoint for a specific network."""
        return cls.NETWORK_BY_ID.format(network_id=network_id)

    @classmethod
    def network_addresses(cls, network_id: int) -> str:
        """Get addresses endpoint for a network."""
        return cls.NETWORK_ADDRESSES.format(network_id=network_id)

    @classmethod
    def network_ranges(cls, network_id: int) -> str:
        """Get DHCP ranges endpoint for a network."""
        return cls.NETWORK_RANGES.format(network_id=network_id)

    @classmethod
    def network_deployment_options(cls, network_id: int) -> str:
        """Get deployment options endpoint for a network."""
        return cls.NETWORK_DEPLOYMENT_OPTIONS.format(network_id=network_id)

    @classmethod
    def network_deployment_roles(cls, network_id: int) -> str:
        """Get deployment roles endpoint for a network."""
        return cls.NETWORK_DEPLOYMENT_ROLES.format(network_id=network_id)

    @classmethod
    def view_by_id(cls, view_id: int) -> str:
        """Get endpoint for a specific view."""
        return cls.VIEW_BY_ID.format(view_id=view_id)

    @classmethod
    def view_zones(cls, view_id: int) -> str:
        """Get zones endpoint for a view."""
        return cls.VIEW_ZONES.format(view_id=view_id)

    @classmethod
    def zone_by_id(cls, zone_id: int) -> str:
        """Get endpoint for a specific zone."""
        return cls.ZONE_BY_ID.format(zone_id=zone_id)

    @classmethod
    def zone_sub_zones(cls, zone_id: int) -> str:
        """Get sub-zones endpoint for a zone."""
        return cls.ZONE_SUB_ZONES.format(zone_id=zone_id)

    @classmethod
    def zone_resource_records(cls, zone_id: int) -> str:
        """Get resource records endpoint for a zone."""
        return cls.ZONE_RESOURCE_RECORDS.format(zone_id=zone_id)

    @classmethod
    def zone_deployment_roles(cls, zone_id: int) -> str:
        """Get deployment roles endpoint for a zone."""
        return cls.ZONE_DEPLOYMENT_ROLES.format(zone_id=zone_id)

    @classmethod
    def server_by_id(cls, server_id: int) -> str:
        """Get endpoint for a specific server."""
        return cls.SERVER_BY_ID.format(server_id=server_id)

    @classmethod
    def server_interfaces(cls, server_id: int) -> str:
        """Get interfaces endpoint for a server."""
        return cls.SERVER_INTERFACES.format(server_id=server_id)

    @classmethod
    def deployment_role_by_id(cls, role_id: int) -> str:
        """Get endpoint for a specific deployment role."""
        return cls.DEPLOYMENT_ROLE_BY_ID.format(role_id=role_id)

    @classmethod
    def deployment_option_by_id(cls, option_id: int) -> str:
        """Get endpoint for a specific deployment option."""
        return cls.DEPLOYMENT_OPTION_BY_ID.format(option_id=option_id)

    @classmethod
    def location_by_id(cls, location_id: int) -> str:
        """Get endpoint for a specific location."""
        return cls.LOCATION_BY_ID.format(location_id=location_id)

    @classmethod
    def location_child_locations(cls, location_id: int) -> str:
        """Get child locations endpoint for a location."""
        return cls.LOCATION_CHILD_LOCATIONS.format(location_id=location_id)

    @classmethod
    def location_annotated_resources(cls, location_id: int) -> str:
        """Get annotated resources endpoint for a location."""
        return cls.LOCATION_ANNOTATED_RESOURCES.format(location_id=location_id)

    @classmethod
    def udf_definition_by_id(cls, udf_id: int) -> str:
        """Get endpoint for a specific UDF definition."""
        return cls.UDF_DEFINITION_BY_ID.format(udf_id=udf_id)

    @classmethod
    def udl_definition_by_id(cls, udl_id: int) -> str:
        """Get endpoint for a specific UDL definition."""
        return cls.UDL_DEFINITION_BY_ID.format(udl_id=udl_id)

    @classmethod
    def tag_by_id(cls, tag_id: int) -> str:
        """Get endpoint for a specific tag."""
        return cls.TAG_BY_ID.format(tag_id=tag_id)

    @classmethod
    def tag_group_by_id(cls, tag_group_id: int) -> str:
        """Get endpoint for a specific tag group."""
        return cls.TAG_GROUP_BY_ID.format(tag_group_id=tag_group_id)

    @classmethod
    def tag_group_tags(cls, tag_group_id: int) -> str:
        """Get tags endpoint for a tag group."""
        return cls.TAG_GROUP_TAGS.format(tag_group_id=tag_group_id)

    @classmethod
    def network_tags(cls, network_id: int) -> str:
        """Get tags endpoint for a network."""
        return cls.NETWORK_TAGS.format(network_id=network_id)

    @classmethod
    def block_tags(cls, block_id: int) -> str:
        """Get tags endpoint for a block."""
        return cls.BLOCK_TAGS.format(block_id=block_id)

    @classmethod
    def zone_tags(cls, zone_id: int) -> str:
        """Get tags endpoint for a zone."""
        return cls.ZONE_TAGS.format(zone_id=zone_id)

    @classmethod
    def address_tags(cls, address_id: int) -> str:
        """Get tags endpoint for an address."""
        return cls.ADDRESS_TAGS.format(address_id=address_id)

    @classmethod
    def configuration_devices(cls, config_id: int) -> str:
        """Get devices endpoint for a configuration."""
        return cls.CONFIGURATION_DEVICES.format(config_id=config_id)

    @classmethod
    def device_by_id(cls, device_id: int) -> str:
        """Get endpoint for a specific device."""
        return cls.DEVICE_BY_ID.format(device_id=device_id)

    @classmethod
    def device_addresses(cls, device_id: int) -> str:
        """Get addresses endpoint for a device."""
        return cls.DEVICE_ADDRESSES.format(device_id=device_id)

    @classmethod
    def device_address_by_id(cls, device_id: int, address_id: int) -> str:
        """Get endpoint for a specific address linked to a device."""
        return cls.DEVICE_ADDRESS_BY_ID.format(device_id=device_id, address_id=address_id)

    @classmethod
    def device_type_by_id(cls, type_id: int) -> str:
        """Get endpoint for a specific device type."""
        return cls.DEVICE_TYPE_BY_ID.format(type_id=type_id)

    @classmethod
    def device_subtype_by_id(cls, subtype_id: int) -> str:
        """Get endpoint for a specific device subtype."""
        return cls.DEVICE_SUBTYPE_BY_ID.format(subtype_id=subtype_id)

    @classmethod
    def device_type_subtypes(cls, type_id: int) -> str:
        """Get subtypes endpoint for a device type."""
        return cls.DEVICE_TYPE_SUBTYPES.format(type_id=type_id)

    # -------------------------------------------------------------------------
    # MAC Pool Helper Methods
    # -------------------------------------------------------------------------
    @classmethod
    def mac_pool_by_id(cls, pool_id: int) -> str:
        """Get endpoint for a specific MAC pool."""
        return cls.MAC_POOL_BY_ID.format(pool_id=pool_id)

    @classmethod
    def configuration_mac_pools(cls, config_id: int) -> str:
        """Get MAC pools endpoint for a configuration."""
        return cls.CONFIGURATION_MAC_POOLS.format(config_id=config_id)

    @classmethod
    def mac_pool_mac_addresses(cls, pool_id: int) -> str:
        """Get MAC addresses endpoint for a MAC pool."""
        return cls.MAC_POOL_MAC_ADDRESSES.format(pool_id=pool_id)

    # -------------------------------------------------------------------------
    # MAC Address Helper Methods
    # -------------------------------------------------------------------------
    @classmethod
    def mac_address_by_id(cls, mac_id: int) -> str:
        """Get endpoint for a specific MAC address."""
        return cls.MAC_ADDRESS_BY_ID.format(mac_id=mac_id)

    @classmethod
    def configuration_mac_addresses(cls, config_id: int) -> str:
        """Get MAC addresses endpoint for a configuration."""
        return cls.CONFIGURATION_MAC_ADDRESSES.format(config_id=config_id)

    # -------------------------------------------------------------------------
    # User-Defined Link Helper Methods
    # -------------------------------------------------------------------------
    @classmethod
    def udl_definition_linked_resources(cls, udl_id: int) -> str:
        """Get linked resources endpoint for a UDL definition."""
        return cls.UDL_DEFINITION_LINKED_RESOURCES.format(udl_id=udl_id)

    @classmethod
    def resource_user_defined_links(cls, collection: str, resource_id: int) -> str:
        """Get user-defined links endpoint for a resource.

        Args:
            collection: The collection name (e.g., 'addresses', 'networks', 'devices')
            resource_id: The resource ID

        Returns:
            Formatted endpoint path
        """
        return cls.RESOURCE_USER_DEFINED_LINKS.format(
            collection=collection, resource_id=resource_id
        )

    @classmethod
    def resource_user_defined_link_by_id(
        cls, collection: str, resource_id: int, link_id: int
    ) -> str:
        """Get endpoint for a specific user-defined link on a resource.

        Args:
            collection: The collection name (e.g., 'addresses', 'networks', 'devices')
            resource_id: The resource ID
            link_id: The link ID

        Returns:
            Formatted endpoint path
        """
        return cls.RESOURCE_USER_DEFINED_LINK_BY_ID.format(
            collection=collection, resource_id=resource_id, link_id=link_id
        )

    # -------------------------------------------------------------------------
    # Access Right Helper Methods
    # -------------------------------------------------------------------------
    @classmethod
    def access_right_by_id(cls, access_right_id: int) -> str:
        """Get endpoint for a specific access right."""
        return cls.ACCESS_RIGHT_BY_ID.format(access_right_id=access_right_id)

    # -------------------------------------------------------------------------
    # User and Group Helper Methods
    # -------------------------------------------------------------------------
    @classmethod
    def user_by_id(cls, user_id: int) -> str:
        """Get endpoint for a specific user."""
        return cls.USER_BY_ID.format(user_id=user_id)

    @classmethod
    def group_by_id(cls, group_id: int) -> str:
        """Get endpoint for a specific group."""
        return cls.GROUP_BY_ID.format(group_id=group_id)

    # -------------------------------------------------------------------------
    # IP Group Helper Methods
    # -------------------------------------------------------------------------
    @classmethod
    def ip_group_by_id(cls, ip_group_id: int) -> str:
        """Get endpoint for a specific IP group."""
        return cls.IP_GROUP_BY_ID.format(ip_group_id=ip_group_id)

    @classmethod
    def network_ip_groups(cls, network_id: int) -> str:
        """Get IP groups endpoint for a network."""
        return cls.NETWORK_IP_GROUPS.format(network_id=network_id)
