# Sample CSV Files

This directory contains example CSV files demonstrating various import scenarios for the BlueCat CSV Importer.

## Conventions

All sample files use consistent naming conventions:

- **Configuration**: `Default`
- **View**: `Internal`
- **Domain**: `example.local` (RFC 2606 reserved for documentation)
- **IPv4 Space**: 10.0.0.0/8 (RFC 1918 private)
- **IPv6 Space**: 2001:db8::/32 (RFC 3849 documentation)
- **Professional naming**: Descriptive resource names (e.g., `app-server-01`, `Production-Servers`)

These defaults align with the self-test system, which uses `Default` and `Internal` as base paths for dynamic substitution during testing.

## File Overview

### IP Address Management

#### IPv4 Resources

| File | Description |
|------|-------------|
| [`ip4_block.csv`](ip4_block.csv) | IPv4 address blocks (Corporate, Datacenter, Branch) |
| [`ip4_network.csv`](ip4_network.csv) | IPv4 networks (Production, Development, Database) |
| [`ip4_address.csv`](ip4_address.csv) | Static IP addresses with MAC addresses |
| [`ip4_group.csv`](ip4_group.csv) | IPv4 address groups for organizing IP ranges within networks |

#### IPv6 Resources

| File | Description |
|------|-------------|
| [`ip6_block.csv`](ip6_block.csv) | IPv6 address blocks (RFC 3849 documentation prefix) |
| [`ip6_network.csv`](ip6_network.csv) | IPv6 networks (/64 subnets) |
| [`ip6_address.csv`](ip6_address.csv) | IPv6 addresses with MAC addresses (STATIC, DHCP_RESERVED) |
| [`ipv6_dhcp_range.csv`](ipv6_dhcp_range.csv) | DHCPv6 address pools |

### DNS Management

| File | Description |
|------|-------------|
| [`dns_zone.csv`](dns_zone.csv) | DNS zones under `example.local` |
| [`host_record.csv`](host_record.csv) | Host (A) records with PTR control |
| [`alias_record.csv`](alias_record.csv) | CNAME records for service aliases |
| [`mx_record.csv`](mx_record.csv) | Mail exchanger records |
| [`txt_record.csv`](txt_record.csv) | TXT records (SPF, DMARC, verification) |
| [`srv_record.csv`](srv_record.csv) | SRV records (LDAP, Kerberos, SIP) |
| [`generic_record.csv`](generic_record.csv) | CAA, TLSA, DS, NS, SPF, TXT records |
| [`external_host_record.csv`](external_host_record.csv) | External host records |

### DHCP Management

| File | Description |
|------|-------------|
| [`ipv4_dhcp_range.csv`](ipv4_dhcp_range.csv) | DHCP address pools |
| [`dhcpv4_client_deployment_option.csv`](dhcpv4_client_deployment_option.csv) | Client-side DHCP options |
| [`dhcpv4_service_deployment_option.csv`](dhcpv4_service_deployment_option.csv) | Server-side DHCP options |
| [`dhcp_deployment_role.csv`](dhcp_deployment_role.csv) | DHCP server deployment roles |
| [`dns_deployment_role.csv`](dns_deployment_role.csv) | DNS server deployment roles |

### Location Management

| File | Description |
|------|-------------|
| [`location.csv`](location.csv) | Hierarchical location structure (regions, countries, sites) |
| [`location_associations.csv`](location_associations.csv) | Resources with location associations |

### User-Defined Fields & Links

| File | Description |
|------|-------------|
| [`udf_definition.csv`](udf_definition.csv) | UDF definition creation (TEXT, EMAIL, URL, PHONE, MULTILINE_TEXT) |
| [`udl_definition.csv`](udl_definition.csv) | UDL (User-Defined Link) definition creation |
| [`user_defined_link.csv`](user_defined_link.csv) | Create actual links between resources using UDL definitions |
| [`ip4_network_with_udf.csv`](ip4_network_with_udf.csv) | Networks with UDF values using `udf_` prefix columns |

### MAC Pool Management

| File | Description |
|------|-------------|
| [`mac_pool.csv`](mac_pool.csv) | MAC pools for DHCP control (MACPool and DenyMACPool types) |
| [`mac_address.csv`](mac_address.csv) | MAC address registration with optional pool association |

### Device Management

| File | Description |
|------|-------------|
| [`device_type.csv`](device_type.csv) | Device type definitions (Cisco, Fortinet, etc.) - GLOBAL resources |
| [`device_subtype.csv`](device_subtype.csv) | Device subtypes (specific models within a type) |
| [`device.csv`](device.csv) | Devices with type/subtype assignments and address associations |
| [`device_address.csv`](device_address.csv) | Device-to-IP address associations |

### Access Control Lists (ACLs)

| File | Description |
|------|-------------|
| [`acl.csv`](acl.csv) | DNS access control lists with bulk IP/CIDR management |

### Access Rights Management

| File | Description |
|------|-------------|
| [`access_right.csv`](access_right.csv) | User and group permission management for BAM resources |
| [`access_right_create.csv`](access_right_create.csv) | Create access rights for users and groups |
| [`access_right_update.csv`](access_right_update.csv) | Update access levels and permissions |
| [`access_right_delete.csv`](access_right_delete.csv) | Remove access rights |

### Comprehensive Examples

| File | Description |
|------|-------------|
| [`combined_all_resources.csv`](combined_all_resources.csv) | Full integration example with all resource types (Phased execution) |

## CSV Format Reference

### Required Columns

All CSV files must include:

| Column | Description |
|--------|-------------|
| `row_id` | Unique identifier for the row (used for tracking and rollback) |
| `object_type` | Type of resource being managed |
| `action` | Operation to perform: `create`, `update`, or `delete` |

### Common Columns

| Column | Description |
|--------|-------------|
| `config` | Configuration name (e.g., `Default`) |
| `view_path` | DNS view path (e.g., `Internal`) |
| `name` | Resource name |
| `description` | Optional description |

### Resource-Specific Columns

#### IP Space Resources

```csv
# ip4_block
row_id,object_type,action,config,name,cidr,description
1,ip4_block,create,Default,Corporate-Network,10.0.0.0/8,Corporate network space

# ip4_network
row_id,object_type,action,config,cidr,name,description
1,ip4_network,create,Default,10.1.1.0/24,Production-Servers,Production server network

# ip4_address
row_id,object_type,action,config,address,name,mac,description,state
1,ip4_address,create,Default,10.1.1.10,app-server-01,00:50:56:01:01:01,App server,STATIC
```

**IPv6 Resources**

```csv
# ip6_block
row_id,object_type,action,config,cidr,name,description,location_code
1,ip6_block,create,Default,2001:db8::/32,IPv6-Documentation-Block,RFC 3849 documentation prefix,

# ip6_network
row_id,object_type,action,config,parent,cidr,name,description,location_code
1,ip6_network,create,Default,/IPv6/2001:db8::/32,2001:db8:1::/64,IPv6-Production-Network,Production IPv6 network,US NYC DC1

# ip6_address
row_id,object_type,action,config,address,name,mac,description,state,location_code
1,ip6_address,create,Default,2001:db8:1::10,ipv6-server-01,00:50:56:01:01:01,Primary IPv6 server,STATIC,US NYC DC1
2,ip6_address,create,Default,2001:db8:1::20,ipv6-dev-server,00:50:56:01:01:02,Development server,DHCP_RESERVED,

# ipv6_dhcp_range
row_id,object_type,action,config,network_path,range,name,splitAroundStaticAddresses,lowWaterMark,highWaterMark
1,ipv6_dhcp_range,create,Default,Default/2001:db8::/32/2001:db8:1::/64,2001:db8:1::1000-2001:db8:1::2000,IPv6-Production-DHCP-Pool,false,20,80
```

**Important IPv6 Differences:**

- **Address Format**: Colon-separated hexadecimal with compression (e.g., `2001:db8::1`)
- **CIDR Notation**: Typical blocks use /32 or /48, networks use /64
- **Address States**: IPv6 addresses only support `STATIC` and `DHCP_RESERVED` (not `RESERVED` or `GATEWAY`)
- **MAC Addresses**: Supported same as IPv4 (XX:XX:XX:XX:XX:XX format)
- **Compressed Notation**: IPv6 addresses are automatically normalized to compressed form (e.g., `2001:db8::1` instead of `2001:0db8:0000:0000:0000:0000:0000:0001`)
```

#### DNS Resources

```csv
# dns_zone
row_id,object_type,action,config,view_path,zone_name,description
1,dns_zone,create,Default,Internal,example.local,Internal corporate domain

# host_record (with optional ptr column for PTR record control)
row_id,object_type,action,config,view_path,name,addresses,ttl,ptr,description
1,host_record,create,Default,Internal,www.example.local,10.1.1.20,3600,true,Web server with PTR
2,host_record,create,Default,Internal,api.example.local,10.1.1.21,3600,false,API server (no PTR)

# alias_record
row_id,object_type,action,config,view_path,zone_name,name,cname,ttl,description
1,alias_record,create,Default,Internal,example.local,portal.example.local,www.example.local,3600,Portal alias

# mx_record
row_id,object_type,action,config,view_path,zone_name,name,exchange,preference,ttl,description
1,mx_record,create,Default,Internal,example.local,example.local,mail.example.local,10,3600,Mail exchanger

# txt_record
row_id,object_type,action,config,view_path,zone_name,name,text,ttl,description
1,txt_record,create,Default,Internal,example.local,example.local,"v=spf1 mx -all",3600,SPF policy

# srv_record
row_id,object_type,action,config,view_path,zone_name,name,target,port,priority,weight,ttl,description
1,srv_record,create,Default,Internal,example.local,_ldap._tcp.example.local,dc01.example.local,389,10,50,3600,LDAP

# generic_record
row_id,object_type,action,config,view_path,zone_name,name,record_type,rdata,ttl,description
1,generic_record,create,Default,Internal,example.local,example.local,CAA,0 issue letsencrypt.org,3600,CA auth
```

#### DHCP Resources

```csv
# ipv4_dhcp_range
row_id,object_type,action,config,network_path,range,name
1,ipv4_dhcp_range,create,Default,Default/10.0.0.0/8/10.1.1.0/24,10.1.1.100-10.1.1.200,Production-DHCP

# dhcpv4_client_deployment_option
row_id,object_type,action,config,network_path,name,code,value,server_scope
1,dhcpv4_client_deployment_option,create,Default,Default/10.0.0.0/8/10.1.1.0/24,router,3,"[""10.1.1.1""]",

# dhcp_deployment_role
row_id,object_type,action,name,config,network_path,roleType,interfaces
1,dhcp_deployment_role,create,Production-DHCP-Primary,Default,10.1.1.0/24,PRIMARY,dhcp-server-01

# ipv6_dhcp_range
row_id,object_type,action,config,network_path,range,name,splitAroundStaticAddresses,lowWaterMark,highWaterMark
1,ipv6_dhcp_range,create,Default,Default/2001:db8:1::/64,2001:db8:1::1000-2001:db8:1::2000,IPv6-Production-DHCP-Pool,false,20,80
```

#### User-Defined Fields (UDFs)

UDFs allow adding custom metadata fields to BAM resources. There are two aspects:

1. **UDF Definitions**: Create new UDF field definitions that apply to resource types
2. **UDF Values**: Set values for UDF fields on resources using `udf_<FieldName>` columns

```csv
# udf_definition - Create UDF field definitions
row_id,object_type,action,name,display_name,field_type,default_value,required,resource_types,predefined_values
1,udf_definition,create,CostCenter,Cost Center,TEXT,,false,IPv4Network|IPv4Block,
2,udf_definition,create,Environment,Environment,TEXT,Production,false,IPv4Network,Development|Staging|Production

# Using UDF values on resources - prefix column names with 'udf_'
row_id,object_type,action,config,parent,cidr,name,udf_CostCenter,udf_Environment
1,ip4_network,create,Default,/IPv4/10.0.0.0/8,10.1.0.0/24,Production-Network,CC-12345,Production
```

**UDF Field Types:**
- `TEXT`: Single-line text field
- `MULTILINE_TEXT`: Multi-line text field
- `URL`: URL field (can be rendered as link)
- `EMAIL`: Email address field
- `PHONE`: Phone number field

**Resource Types:**
- Use pipe-separated list: `IPv4Network|IPv4Block|IPv4Address`
- Use `*` to apply to all resource types

#### Location Resources

Locations use UN/LOCODE (United Nations Code for Trade and Transport Locations) format for parent references. BAM comes pre-populated with:
- **Country codes**: `US`, `GB`, `JP`, etc.
- **City codes**: `US NYC` (New York), `US SFO` (San Francisco), `GB LON` (London), `JP TYO` (Tokyo)

Custom locations must be created under existing UN/LOCODE locations. The `parent_code` field references either a UN/LOCODE or a previously created custom location.

```csv
# location - Create custom locations under UN/LOCODE parents
row_id,object_type,action,parent_code,code,name,description,latitude,longitude
1,location,create,US NYC,US NYC DC2,NYC Primary Datacenter,Primary datacenter in NYC,40.7128,-74.0060
2,location,create,US NYC DC2,US NYC DC2 F23,NYC DC2 Floor 23,First floor of datacenter,40.7128,-74.0060
```

**Important**: The `parent_code` must reference an existing location:
- Use UN/LOCODE format with space separator (e.g., `US NYC`, not `US-NYC`)
- Or reference a custom location created earlier in the same CSV (deferred resolution)

#### Device Resources

Devices represent physical or virtual network appliances (firewalls, switches, routers, servers). The device hierarchy is:

1. **Device Types** (GLOBAL): Categories like Cisco, Fortinet, F5
2. **Device Subtypes**: Specific models within a type (e.g., FortiGate-600E under Fortinet)
3. **Devices** (per-configuration): Actual devices with optional type/subtype assignments
4. **Device-Address Links**: Associate IP addresses with devices

```csv
# device_type - GLOBAL resource (not per-configuration)
row_id,object_type,action,name
1,device_type,create,Fortinet
2,device_type,create,Cisco

# device_subtype - Must reference parent device type
row_id,object_type,action,device_type,name
1,device_subtype,create,Fortinet,FortiGate-600E
2,device_subtype,create,Cisco,Catalyst-3750

# device - Per-configuration, optional type/subtype references
row_id,object_type,action,config,name,device_type,device_subtype,addresses,mac_address
1,device,create,Default,firewall-01,Fortinet,FortiGate-600E,10.0.1.1|10.0.2.1,00:11:22:33:44:55
2,device,create,Default,core-switch,Cisco,Catalyst-3750,,

# device_address - Link existing addresses to devices
row_id,object_type,action,config,device_name,address
1,device_address,create,Default,core-switch,10.0.1.254
2,device_address,delete,Default,firewall-01,10.0.2.1
```

**Device Fields:**
- `device_type`: Name of device type (optional)
- `device_subtype`: Name of device subtype (optional, requires device_type)
- `addresses`: Pipe-separated IP addresses to associate with device during creation
- `mac_address`: MAC address in XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX format

**Notes:**
- Device types are GLOBAL (not per-configuration) and must be created before subtypes
- Device subtypes require a parent device type
- Devices can be created without type/subtype assignments
- The `addresses` field allows linking addresses during device creation
- Use `device_address` for post-creation address associations

#### ACL Resources

Access Control Lists (ACLs) define which hosts are allowed or denied access to DNS services.

```csv
# acl - DNS access control lists with bulk IP/CIDR management
row_id,object_type,action,config,name,match_elements
1,acl,create,Default,internal_networks,"10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
2,acl,create,Default,trusted_partners,"203.0.113.0/24,198.51.100.0/24"
3,acl,update,Default,internal_networks,"10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10"
4,acl,delete,Default,old_acl,
```

**ACL Fields:**
- `name`: ACL name (required)
- `config`: Configuration name (required)
- `match_elements`: Comma-separated list of IPs/CIDRs (supports 500+ entries)

**Notes:**
- Match elements replace the entire ACL on update (no append mode)
- Use quotes around `match_elements` if it contains commas

#### Access Rights Resources

Access rights control what actions users and groups can perform on specific resources or resource types within BlueCat Address Manager.

```csv
# access_right - Grant VIEW access to a user on a specific configuration
row_id,object_type,action,user_type,user_name,resource_type,resource_path,config,default_access_level,deployments_allowed,quick_deployments_allowed,selective_deployments_allowed,workflow_level,access_overrides
1,access_right,create,user,operator,Configuration,Default,,VIEW,false,false,false,NONE,

# access_right - Grant ADD access to a group with deployment permissions
2,access_right,create,group,NetworkAdmins,Configuration,Production,,ADD,true,true,false,APPROVE,

# access_right - Default access with type-specific overrides
3,access_right,create,user,developer,,,Default,VIEW,false,false,false,NONE,IPv4Address:FULL|HostRecord:ADD
```

**Access Right Fields:**
- `user_type`: Type of user scope - `user` or `group` (required)
- `user_name`: Username or group name to grant access to (required)
- `resource_type`: BAM resource type (e.g., Configuration, IPv4Block, Zone) - optional
- `resource_path`: Path to resolve the resource - optional
- `config`: Configuration name (for resources that need config context) - optional
- `default_access_level`: Access level - `HIDE`, `VIEW`, `CHANGE`, `ADD`, `FULL` (required)
- `deployments_allowed`: Allow full deployments (`true`/`false`)
- `quick_deployments_allowed`: Allow quick DNS deployments (`true`/`false`)
- `selective_deployments_allowed`: Allow selective deployments (`true`/`false`)
- `workflow_level`: Workflow level - `NONE`, `RECOMMEND`, `APPROVE`
- `access_overrides`: Pipe-separated type:level pairs for overrides (e.g., `IPv4Address:FULL|HostRecord:VIEW`)

**Access Levels:**
- `HIDE`: Resource is hidden from the user
- `VIEW`: Read-only access
- `CHANGE`: Can modify existing resources
- `ADD`: Can create new resources
- `FULL`: Complete control including delete

**Workflow Levels:**
- `NONE`: No workflow approval required
- `RECOMMEND`: Changes are recommendations
- `APPROVE`: User can approve workflow requests

**Notes:**
- Users and groups must exist in BAM before creating access rights
- Access overrides allow fine-grained control over specific resource types
- The user scope and resource cannot be changed after creation - delete and recreate to modify

## Usage Examples

### Basic Workflow

```bash
# 1. Validate CSV syntax and schema
bluecat-import validate samples/ip4_block.csv

# 2. Preview changes (dry-run)
bluecat-import apply samples/ip4_block.csv --dry-run

# 3. Apply changes
bluecat-import apply samples/ip4_block.csv
```

### Self-Test with Samples

The self-test uses these samples with automatic path substitution:

```bash
# Run all sample CSVs in dry-run mode
bluecat-import self-test --url https://bam.example.com --username admin --csv-tests

# Run with auto-cleanup on success
bluecat-import self-test --url https://bam.example.com --username admin --csv-tests --auto-cleanup
```

### Specific File Testing

```bash
# Test specific CSV files
bluecat-import self-test --url https://bam.example.com --username admin \
  --csv-tests \
  --csv-file ip4_block.csv \
  --csv-file ip4_network.csv \
  --csv-file host_record.csv
```

## Multi-Section CSV Format

For complex imports, use multi-section CSVs with different headers:

```csv
# Section 1: IP Space
row_id,object_type,action,config,name,cidr,description
1,ip4_block,create,Default,Corporate,10.0.0.0/8,Corporate block
2,ip4_network,create,Default,Production,10.1.1.0/24,Production network

# Section 2: DNS Records
row_id,object_type,action,config,view_path,name,addresses,ttl,description
10,host_record,create,Default,Internal,www.example.local,10.1.1.10,3600,Web server
11,host_record,create,Default,Internal,api.example.local,10.1.1.11,3600,API server
```

## Dependencies and Ordering

The importer automatically handles dependencies:

1. **Parent-first creation**: Blocks before networks, networks before addresses
2. **Cross-type dependencies**: Networks before DHCP ranges, zones before records
3. **Reverse deletion**: Children deleted before parents
4. **Same-batch references**: Resources can reference parents created in the same CSV

## Tips

1. **Validate First**: Always use `validate` before `apply`
2. **Dry-Run**: Test with `--dry-run` to preview changes
3. **Unique row_id**: Each row needs a unique identifier
4. **Path Format**: Use forward slashes for paths (e.g., `Default/10.0.0.0/8`)
5. **Case Sensitivity**: Object types are case-sensitive (`ip4_network`, not `IP4_Network`)

## Prerequisites and Dependencies

Some sample files require other resources to exist before they can be imported successfully:

| Sample File | Prerequisite | Notes |
|-------------|--------------|-------|
| `ip4_network.csv` | `ip4_block.csv` | Networks require a containing block. Import blocks first or ensure equivalent blocks exist in BAM. |
| `ip6_network.csv` | `ip6_block.csv` | IPv6 networks require a containing IPv6 block. |
| `ip4_address.csv` | `ip4_network.csv` | Addresses require a containing network. |
| `ip6_address.csv` | `ip6_network.csv` | IPv6 addresses require a containing network. |
| `ipv4_dhcp_range.csv` | `ip4_network.csv` | DHCP ranges are created within networks. |
| `ipv6_dhcp_range.csv` | `ip6_network.csv` | DHCPv6 ranges are created within networks. |
| `host_record.csv` | `dns_zone.csv` | DNS records require a zone. |
| `device_subtype.csv` | `device_type.csv` | Subtypes belong to device types. |
| `device.csv` | `device_type.csv` (optional) | Devices can reference types/subtypes. |
| `tag.csv` | `tag_group.csv` | Tags belong to tag groups. |
| `resource_tag.csv` | `tag.csv` + target resource | Requires both tag and resource to exist. |
| `user_defined_link.csv` | `udl_definition.csv` + resources | Requires UDL definition and linked resources. |

**Recommended Import Order for Full Stack:**
1. `ip4_block.csv`, `ip6_block.csv` (IP space containers)
2. `ip4_network.csv`, `ip6_network.csv` (Networks within blocks)
3. `dns_zone.csv` (DNS containers)
4. `ip4_address.csv`, `ip6_address.csv` (IP addresses)
5. `host_record.csv` and other DNS records
6. `ipv4_dhcp_range.csv`, `ipv6_dhcp_range.csv` (DHCP pools)
7. Device types, subtypes, and devices
8. Tags, resource tags, and access rights

## Creating Custom CSV Files

1. Copy a relevant sample as a template
2. Update configuration/view names for your environment
3. Modify resource values (CIDRs, names, addresses)
4. Validate before applying

## See Also

- [SELF_TEST_GUIDE.md](../docs/SELF_TEST_GUIDE.md) - Comprehensive testing guide
- [TUTORIAL.md](../docs/TUTORIAL.md) - Step-by-step tutorial
- [ARCHITECTURE.md](../docs/ARCHITECTURE.md) - Technical architecture
