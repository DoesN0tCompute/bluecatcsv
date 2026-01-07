# BlueCat CSV Importer - CSV Guide

**Version:** 1.0 | **Last Updated:** 2025-12-16

This comprehensive guide documents all CSV formats supported by the BlueCat CSV Importer. It covers required headers, field descriptions, valid values, and examples for each object type.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [CSV Format Basics](#csv-format-basics)
3. [Required Columns (All Objects)](#required-columns-all-objects)
4. [IP Address Management](#ip-address-management)
   - [IPv4 Blocks](#ipv4-blocks-ip4_block)
   - [IPv4 Networks](#ipv4-networks-ip4_network)
   - [IPv4 Addresses](#ipv4-addresses-ip4_address)
   - [IPv4 Groups](#ipv4-groups-ip4_group)
   - [IPv6 Blocks](#ipv6-blocks-ip6_block)
   - [IPv6 Networks](#ipv6-networks-ip6_network)
   - [IPv6 Addresses](#ipv6-addresses-ip6_address)
5. [DNS Management](#dns-management)
   - [DNS Zones](#dns-zones-dns_zone)
   - [Host Records](#host-records-host_record)
   - [Alias Records (CNAME)](#alias-records-cname-alias_record)
   - [MX Records](#mx-records-mx_record)
   - [TXT Records](#txt-records-txt_record)
   - [SRV Records](#srv-records-srv_record)
   - [External Host Records](#external-host-records-external_host_record)
   - [Generic Records](#generic-records-generic_record)
6. [DHCP Management](#dhcp-management)
   - [IPv4 DHCP Ranges](#ipv4-dhcp-ranges-ipv4_dhcp_range)
   - [IPv6 DHCP Ranges](#ipv6-dhcp-ranges-ipv6_dhcp_range)
   - [DHCP Deployment Roles](#dhcp-deployment-roles-dhcp_deployment_role)
   - [DNS Deployment Roles](#dns-deployment-roles-dns_deployment_role)
   - [DHCPv4 Client Options](#dhcpv4-client-options-dhcpv4_client_deployment_option)
   - [DHCPv4 Service Options](#dhcpv4-service-options-dhcpv4_service_deployment_option)
7. [Device Management](#device-management)
   - [Device Types](#device-types-device_type)
   - [Device Subtypes](#device-subtypes-device_subtype)
   - [Devices](#devices-device)
   - [Device Addresses](#device-addresses-device_address)
8. [MAC Pool Management](#mac-pool-management)
   - [MAC Pools](#mac-pools-mac_pool)
   - [MAC Addresses](#mac-addresses-mac_address)
9. [Location Management](#location-management)
   - [Locations](#locations-location)
10. [User-Defined Fields & Links](#user-defined-fields--links)
    - [UDF Definitions](#udf-definitions-udf_definition)
    - [UDL Definitions](#udl-definitions-udl_definition)
    - [User-Defined Links](#user-defined-links-user_defined_link)
    - [Using UDF Values on Resources](#using-udf-values-on-resources)
11. [Tags & Tagging](#tags--tagging)
    - [Tag Groups](#tag-groups-tag_group)
    - [Tags](#tags-tag)
    - [Resource Tags](#resource-tags-resource_tag)
12. [Access Control](#access-control)
    - [Access Control Lists (ACLs)](#access-control-lists-acl)
    - [Access Rights](#access-rights-access_right)
13. [Multi-Section CSVs](#multi-section-csvs)
14. [Common Conventions](#common-conventions)
15. [Troubleshooting](#troubleshooting)

---

## Quick Start

```csv
row_id,object_type,action,config,cidr,name
1,ip4_block,create,Default,10.0.0.0/8,Corporate-Block
2,ip4_network,create,Default,10.1.0.0/24,Production-Network
```

```bash
# Validate CSV syntax
bluecat-import validate my_import.csv

# Preview changes (dry-run)
bluecat-import apply my_import.csv --dry-run

# Execute import
bluecat-import apply my_import.csv
```

---

## CSV Format Basics

### File Requirements

| Requirement | Description |
|-------------|-------------|
| **Encoding** | UTF-8 (recommended) or ASCII |
| **Line Endings** | Unix (LF) or Windows (CRLF) |
| **Delimiter** | Comma (`,`) |
| **Quote Character** | Double quote (`"`) for values containing commas |
| **Header Row** | Required as first non-comment line |

### Comments

Lines starting with `#` are treated as comments and ignored:

```csv
# This is a comment describing the import
row_id,object_type,action,config,cidr,name
1,ip4_block,create,Default,10.0.0.0/8,Corporate
```

### Value Formatting

| Type | Format | Examples |
|------|--------|----------|
| **Strings** | Plain text, quote if contains commas | `Production-Net`, `"Value, with comma"` |
| **Numbers** | Plain integers | `3600`, `10` |
| **Booleans** | `true` or `false` (case-insensitive) | `true`, `false` |
| **Lists** | Pipe-separated (`\|`) | `10.1.1.1\|10.1.1.2` |
| **IPv4 CIDR** | `x.x.x.x/prefix` | `10.1.0.0/24` |
| **IPv6 CIDR** | Standard notation | `2001:db8::/32` |
| **MAC Address** | Colon or dash separated | `00:11:22:33:44:55` or `00-11-22-33-44-55` |

---

## Required Columns (All Objects)

Every CSV row **must** include these three columns:

| Column | Type | Description |
|--------|------|-------------|
| `row_id` | string/int | **Unique identifier** for tracking and rollback. Can be descriptive like `web-server-1` or numeric like `1` |
| `object_type` | string | **Type of resource** being managed. Must match exactly (case-sensitive). See object types below |
| `action` | string | **Operation**: `create`, `update`, or `delete` |

### Optional Safety Columns

| Column | Type | Description |
|--------|------|-------------|
| `bam_id` | int | Direct BAM resource ID (bypasses path resolution) |
| `verify_name` | string | Verify the resource name matches before update/delete |
| `verify_address` | string | Verify the address matches before update/delete |
| `_version` | string | CSV schema version (default: `3.0`) |

### Example

```csv
row_id,object_type,action,bam_id,verify_name,config,name,cidr
server-cleanup,ip4_network,delete,12345,Old-Network,Default,,
```

---

## IP Address Management

### IPv4 Blocks (`ip4_block`)

IPv4 blocks are the top-level containers for organizing IP address space.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name (e.g., `Default`) |
| `cidr` | Yes | string | CIDR notation (e.g., `10.0.0.0/8`) |
| `name` | Yes | string | Block name |
| `parent` | No | string | Parent path for nested blocks (e.g., `/IPv4/10.0.0.0/8`) |
| `description` | No | string | Optional description |
| `location_code` | No | string | Location association (e.g., `US NYC DC1`) |

#### Example

```csv
row_id,object_type,action,config,cidr,name,description,location_code
1,ip4_block,create,Default,10.0.0.0/8,Corporate-Block,Main corporate address space,US NYC
2,ip4_block,create,Default,10.1.0.0/16,Datacenter-Block,Primary datacenter,US NYC DC1
```

---

### IPv4 Networks (`ip4_network`)

IPv4 networks are subnets within blocks that contain IP addresses.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `cidr` | Yes | string | Network CIDR notation (e.g., `10.1.1.0/24`) |
| `name` | Yes | string | Network name |
| `parent` | No | string | Parent block path (e.g., `/IPv4/10.0.0.0/8`) |
| `description` | No | string | Optional description |
| `location_code` | No | string | Location association |

#### Example

```csv
row_id,object_type,action,config,parent,cidr,name,description,location_code
1,ip4_network,create,Default,/IPv4/10.0.0.0/8,10.1.1.0/24,Production-Servers,Production server network,US NYC DC1
2,ip4_network,create,Default,/IPv4/10.0.0.0/8,10.1.2.0/24,Development-Servers,Development environment,US NYC DC1
3,ip4_network,update,Default,,10.1.1.0/24,Production-Servers-Updated,Updated description,
```

---

### IPv4 Addresses (`ip4_address`)

Individual IPv4 addresses within networks.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `address` | Yes | string | IPv4 address (e.g., `10.1.1.10`) |
| `name` | No | string | Address name/hostname |
| `mac` | No | string | MAC address (`XX:XX:XX:XX:XX:XX` or `XX-XX-XX-XX-XX-XX`) |
| `parent` | No | string | Parent network path |
| `description` | No | string | Optional description |
| `location_code` | No | string | Location association |
| `state` | No | string | Address state: `STATIC`, `RESERVED`, `DHCP_RESERVED`, or `GATEWAY` |

#### IP Address States

| State | Description |
|-------|-------------|
| `STATIC` | Statically assigned address |
| `RESERVED` | Reserved for future use |
| `DHCP_RESERVED` | Reserved for specific DHCP client (requires MAC) |
| `GATEWAY` | Network gateway address |

#### Example

```csv
row_id,object_type,action,config,address,name,mac,state,description
1,ip4_address,create,Default,10.1.1.1,gateway-01,,GATEWAY,Network gateway
2,ip4_address,create,Default,10.1.1.10,web-server-01,00:11:22:33:44:55,STATIC,Primary web server
3,ip4_address,create,Default,10.1.1.20,dhcp-printer,AA:BB:CC:DD:EE:FF,DHCP_RESERVED,Reserved for printer
```

---

### IPv4 Groups (`ip4_group`)

IP groups are logical groupings of consecutive IP addresses within a network.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `parent` | Yes | string | Parent network path (e.g., `/IPv4/10.0.0.0/8/10.1.0.0/24`) |
| `name` | Yes | string | Group name |
| `range` | Yes | string | Address range specification (see formats below) |

#### Range Formats

| Format | Example | Description |
|--------|---------|-------------|
| IP Range | `10.1.0.100-10.1.0.200` | Start and end IP addresses |
| Offset + Size | `20,30` | 30 addresses starting at offset 20 from network start |
| Offset + Percent | `20,15%` | 15% of network size starting at offset 20 |
| Negative Offset | `-40,30` | 30 addresses starting 40 from network end |

#### Example

```csv
row_id,object_type,action,config,parent,name,range
1,ip4_group,create,Default,/IPv4/10.0.0.0/8/10.1.0.0/24,DHCP-Pool,10.1.0.100-10.1.0.200
2,ip4_group,create,Default,/IPv4/10.0.0.0/8/10.1.0.0/24,Server-Range,20,30
3,ip4_group,create,Default,/IPv4/10.0.0.0/8/10.1.0.0/24,Reserved-End,-40,30
```

---

### IPv6 Blocks (`ip6_block`)

Top-level IPv6 address block containers.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `cidr` | Yes | string | IPv6 CIDR notation (e.g., `2001:db8::/32`) |
| `name` | Yes | string | Block name |
| `parent` | No | string | Parent path for nested blocks |
| `description` | No | string | Optional description |
| `location_code` | No | string | Location association |

#### Example

```csv
row_id,object_type,action,config,cidr,name,description
1,ip6_block,create,Default,2001:db8::/32,IPv6-Documentation-Block,RFC 3849 documentation prefix
```

---

### IPv6 Networks (`ip6_network`)

IPv6 subnets within blocks.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `cidr` | Yes | string | IPv6 network CIDR (typically `/64`) |
| `name` | Yes | string | Network name |
| `parent` | No | string | Parent block path |
| `description` | No | string | Optional description |
| `location_code` | No | string | Location association |

#### Example

```csv
row_id,object_type,action,config,parent,cidr,name,description
1,ip6_network,create,Default,/IPv6/2001:db8::/32,2001:db8:1::/64,Production-IPv6,Primary production network
2,ip6_network,create,Default,/IPv6/2001:db8::/32,2001:db8:2::/64,Development-IPv6,Development network
```

---

### IPv6 Addresses (`ip6_address`)

Individual IPv6 addresses.

> **Important:** IPv6 addresses only support `STATIC` and `DHCP_RESERVED` states. The `RESERVED` and `GATEWAY` states are not available for IPv6.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `address` | Yes | string | IPv6 address (e.g., `2001:db8:1::10`) |
| `name` | No | string | Address name/hostname |
| `mac` | No | string | MAC address |
| `parent` | No | string | Parent network path |
| `description` | No | string | Optional description |
| `location_code` | No | string | Location association |
| `state` | No | string | Address state: `STATIC` or `DHCP_RESERVED` only |

#### Example

```csv
row_id,object_type,action,config,address,name,mac,state,description
1,ip6_address,create,Default,2001:db8:1::10,ipv6-server-01,00:50:56:01:01:01,STATIC,Primary IPv6 server
2,ip6_address,create,Default,2001:db8:1::20,ipv6-printer,AA:BB:CC:DD:EE:FF,DHCP_RESERVED,IPv6 printer reservation
```

---

## DNS Management

### DNS Zones (`dns_zone`)

DNS zones are containers for DNS resource records.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `view_path` | Yes | string | DNS view path (e.g., `Internal`) |
| `zone_name` | Yes | string | Zone name (e.g., `example.com`) |
| `description` | No | string | Optional description |
| `location_code` | No | string | Location association |

#### Example

```csv
row_id,object_type,action,config,view_path,zone_name,description
1,dns_zone,create,Default,Internal,example.local,Internal corporate domain
2,dns_zone,create,Default,Internal,dev.example.local,Development subdomain
```

---

### Host Records (`host_record`)

DNS A records mapping hostnames to IP addresses.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `view_path` | Yes | string | DNS view path |
| `name` | Yes | string | Fully qualified domain name (e.g., `www.example.local`) or `@` for apex |
| `addresses` | Yes | string | Pipe-separated IP addresses (e.g., `10.1.1.20\|10.1.1.21`) |
| `ttl` | No | int | Time-to-live in seconds |
| `description` | No | string | Optional description |
| `location_code` | No | string | Location association |
| `ptr` | No | bool | Create reverse PTR record (`true`/`false`) |

> **Note:** Use `@` or leave `name` empty to create apex (zone root) records.

#### Example

```csv
row_id,object_type,action,config,view_path,name,addresses,ttl,ptr,description
1,host_record,create,Default,Internal,www.example.local,10.1.1.20,3600,true,Web server with PTR
2,host_record,create,Default,Internal,api.example.local,10.1.1.21|10.1.1.22,3600,false,API servers (no PTR)
3,host_record,create,Default,Internal,@,10.1.1.10,3600,true,Zone apex record
```

---

### Alias Records (CNAME) (`alias_record`)

DNS CNAME records for aliasing hostnames.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `view_path` | Yes | string | DNS view path |
| `name` | Yes | string | Alias name (source) |
| `cname` | Yes | string | Canonical name (target) |
| `zone_name` | No | string | Zone name (helps with resolution) |
| `ttl` | No | int | Time-to-live in seconds |
| `description` | No | string | Optional description |
| `location_code` | No | string | Location association |

#### Example

```csv
row_id,object_type,action,config,view_path,zone_name,name,cname,ttl,description
1,alias_record,create,Default,Internal,example.local,portal.example.local,www.example.local,3600,Portal alias
2,alias_record,create,Default,Internal,example.local,cdn.example.local,external-cdn.provider.com,3600,CDN alias
```

---

### MX Records (`mx_record`)

Mail exchanger records for email routing.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `view_path` | Yes | string | DNS view path |
| `name` | Yes | string | Record name (usually zone apex, use `@` or zone name) |
| `exchange` | Yes | string | Mail server hostname |
| `preference` | Yes | int | MX priority (lower = higher priority) |
| `zone_name` | No | string | Zone name |
| `ttl` | No | int | Time-to-live in seconds |
| `description` | No | string | Optional description |
| `location_code` | No | string | Location association |

#### Example

```csv
row_id,object_type,action,config,view_path,zone_name,name,exchange,preference,ttl,description
1,mx_record,create,Default,Internal,example.local,example.local,mail1.example.local,10,3600,Primary mail server
2,mx_record,create,Default,Internal,example.local,example.local,mail2.example.local,20,3600,Backup mail server
```

---

### TXT Records (`txt_record`)

DNS TXT records for SPF, DKIM, DMARC, and other text data.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `view_path` | Yes | string | DNS view path |
| `name` | Yes | string | Record name (e.g., `_dmarc.example.local`) |
| `text` | Yes | string | TXT record content (quote if contains special characters) |
| `zone_name` | No | string | Zone name |
| `ttl` | No | int | Time-to-live in seconds |
| `description` | No | string | Optional description |
| `location_code` | No | string | Location association |

#### Example

```csv
row_id,object_type,action,config,view_path,zone_name,name,text,ttl,description
1,txt_record,create,Default,Internal,example.local,example.local,"v=spf1 mx -all",3600,SPF policy
2,txt_record,create,Default,Internal,example.local,_dmarc.example.local,"v=DMARC1; p=reject",3600,DMARC policy
3,txt_record,create,Default,Internal,example.local,_verification.example.local,verify-abc123,3600,Domain verification
```

---

### SRV Records (`srv_record`)

DNS SRV records for service location (LDAP, Kerberos, SIP, etc.).

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `view_path` | Yes | string | DNS view path |
| `name` | Yes | string | Service name (e.g., `_ldap._tcp.example.local`) |
| `target` | Yes | string | Target server hostname |
| `port` | Yes | int | Service port number |
| `priority` | Yes | int | Priority (lower = higher priority) |
| `weight` | Yes | int | Weight for load balancing |
| `zone_name` | No | string | Zone name |
| `ttl` | No | int | Time-to-live in seconds |
| `description` | No | string | Optional description |
| `location_code` | No | string | Location association |

#### Common SRV Records

| Service | Name Format |
|---------|-------------|
| LDAP | `_ldap._tcp.domain` |
| Kerberos | `_kerberos._tcp.domain` |
| SIP | `_sip._tcp.domain` or `_sip._udp.domain` |
| XMPP | `_xmpp-client._tcp.domain` |

#### Example

```csv
row_id,object_type,action,config,view_path,zone_name,name,target,port,priority,weight,ttl,description
1,srv_record,create,Default,Internal,example.local,_ldap._tcp.example.local,dc01.example.local,389,10,50,3600,LDAP service
2,srv_record,create,Default,Internal,example.local,_kerberos._tcp.example.local,dc01.example.local,88,10,100,3600,Kerberos
```

---

### External Host Records (`external_host_record`)

Records for external hosts not managed in BAM (used as CNAME/MX/SRV targets).

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `view_path` | Yes | string | DNS view path |
| `name` | Yes | string | External FQDN (e.g., `cdn.external-provider.com`) |
| `zone_name` | No | string | Zone for context |
| `ttl` | No | int | Time-to-live in seconds |
| `description` | No | string | Optional description |

#### Example

```csv
row_id,object_type,action,config,view_path,zone_name,name,ttl,description
1,external_host_record,create,Default,Internal,example.local,cdn.cloudprovider.com,3600,External CDN
2,external_host_record,create,Default,Internal,example.local,smtp.mailservice.com,3600,External mail relay
```

---

### Generic Records (`generic_record`)

Create DNS record types not natively supported by dedicated CSV types.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `view_path` | Yes | string | DNS view path |
| `name` | Yes | string | Record name (use `@` for zone apex) |
| `record_type` | Yes | string | DNS record type (see list below) |
| `rdata` | Yes | string | Record data in zone file format |
| `zone_name` | No | string | Zone name |
| `ttl` | No | int | Time-to-live in seconds |
| `description` | No | string | Optional description |

#### Supported Record Types

`A`, `A6`, `AAAA`, `AFSDB`, `APL`, `CAA`, `CERT`, `DHCID`, `DNAME`, `DS`, `IPSECKEY`, `ISDN`, `KEY`, `KX`, `LOC`, `MB`, `MG`, `MINFO`, `MR`, `NS`, `NSAP`, `PTR`, `PX`, `RP`, `RT`, `SINK`, `SPF`, `SSHFP`, `TLSA`, `TXT`, `WKS`, `X25`

#### Example

```csv
row_id,object_type,action,config,view_path,zone_name,name,record_type,rdata,ttl,description
1,generic_record,create,Default,Internal,example.local,@,CAA,0 issue letsencrypt.org,3600,CA authorization
2,generic_record,create,Default,Internal,example.local,server1,SSHFP,2 1 123456789abcdef...,3600,SSH fingerprint
3,generic_record,create,Default,Internal,example.local,_443._tcp.www,TLSA,3 1 1 abc123...,3600,DANE TLSA record
```

---

## DHCP Management

### IPv4 DHCP Ranges (`ipv4_dhcp_range`)

DHCP address pools within IPv4 networks.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `network_path` | Yes | string | Network path (e.g., `Default/10.0.0.0/8/10.1.1.0/24`) |
| `range` | Yes | string | DHCP range (e.g., `10.1.1.100-10.1.1.200`) |
| `name` | No | string | Range name |
| `splitAroundStaticAddresses` | No | bool | Split pool around static assignments |
| `lowWaterMark` | No | int | Low threshold percentage (0-100) |
| `highWaterMark` | No | int | High threshold percentage (0-100) |
| `template_name` | No | string | DHCP template name |

#### Example

```csv
row_id,object_type,action,config,network_path,range,name,splitAroundStaticAddresses,lowWaterMark,highWaterMark
1,ipv4_dhcp_range,create,Default,Default/10.0.0.0/8/10.1.1.0/24,10.1.1.100-10.1.1.200,Production-DHCP,false,20,80
2,ipv4_dhcp_range,create,Default,Default/10.0.0.0/8/10.1.2.0/24,10.1.2.50-10.1.2.150,Dev-DHCP,true,10,90
```

---

### IPv6 DHCP Ranges (`ipv6_dhcp_range`)

DHCPv6 address pools.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `network_path` | Yes | string | Network path |
| `range` | Yes | string | DHCPv6 range (e.g., `2001:db8:1::100-2001:db8:1::200`) |
| `name` | No | string | Range name |
| `splitAroundStaticAddresses` | No | bool | Split pool around static assignments |
| `lowWaterMark` | No | int | Low threshold percentage (0-100) |
| `highWaterMark` | No | int | High threshold percentage (0-100) |

#### Range Formats for DHCPv6

| Format | Example | Description |
|--------|---------|-------------|
| Start-End | `2001:db8::100-2001:db8::200` | IPv6 address range |
| Offset,Size | `20,10` | 10 addresses at offset 20 |
| Offset,Percent | `20,1%` | 1% of network at offset 20 |
| CIDR | `/120` | CIDR notation within network |

#### Example

```csv
row_id,object_type,action,config,network_path,range,name,splitAroundStaticAddresses
1,ipv6_dhcp_range,create,Default,Default/2001:db8::/32/2001:db8:1::/64,2001:db8:1::1000-2001:db8:1::2000,IPv6-Production-Pool,false
```

---

### DHCP Deployment Roles (`dhcp_deployment_role`)

Define DHCP server deployment for networks or blocks.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `network_path` | Note | string | Network path (provide either network_path or block_path) |
| `block_path` | Note | string | Block path |
| `name` | No | string | Role name |
| `roleType` | Yes | string | Role type: `PRIMARY`, `SECONDARY`, `ACTIVE`, `PASSIVE`, `NONE` |
| `interfaces` | Yes | string | Pipe-separated server interfaces (e.g., `server1\|server2`) |
| `serverGroup` | No | string | Server group name |

#### Example

```csv
row_id,object_type,action,config,network_path,name,roleType,interfaces
1,dhcp_deployment_role,create,Default,Default/10.0.0.0/8/10.1.1.0/24,Production-DHCP-Primary,PRIMARY,dhcp-server-01|dhcp-server-02
```

---

### DNS Deployment Roles (`dns_deployment_role`)

Define DNS server deployment for zones, networks, or blocks.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `zone_path` | Note | string | Zone path (provide exactly one of zone/network/block_path) |
| `network_path` | Note | string | Network path |
| `block_path` | Note | string | Block path |
| `name` | No | string | Role name |
| `roleType` | Yes | string | Role type (see table below) |
| `interfaces` | Yes | string | Pipe-separated interfaces |
| `nsRecordTtl` | No | int | NS record TTL in seconds |

#### DNS Role Types

| Role Type | Description |
|-----------|-------------|
| `PRIMARY` | Primary DNS server |
| `MULTI_PRIMARY` | Multi-primary configuration |
| `HIDDEN_PRIMARY` | Hidden primary (not in NS records) |
| `HIDDEN_MULTI_PRIMARY` | Hidden multi-primary |
| `SECONDARY` | Secondary/slave DNS server |
| `STEALTH_SECONDARY` | Stealth secondary |
| `FORWARDING` | Forwarding role |
| `STUB` | Stub zone |
| `RECURSIVE` | Recursive resolver |
| `NONE` | No DNS role |

#### Example

```csv
row_id,object_type,action,config,zone_path,name,roleType,interfaces,nsRecordTtl
1,dns_deployment_role,create,Default,Internal/example.local,Zone-DNS-Primary,PRIMARY,dns-server-01|dns-server-02,3600
```

---

### DHCPv4 Client Options (`dhcpv4_client_deployment_option`)

DHCP options sent to clients during lease assignment.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `network_path` | Yes | string | Network path |
| `name` | No | string | Option name |
| `code` | Yes | int | DHCP option code (1-254, per RFC 2132) |
| `value` | Yes | string | Option value |
| `server_scope` | No | string | Server scope: `DHCP_SERVER`, `DNS_SERVER`, `ALL_SERVERS` |

#### Common DHCP Option Codes

| Code | Name | Description |
|------|------|-------------|
| 3 | Router | Default gateway |
| 6 | DNS Servers | Domain name servers |
| 15 | Domain Name | Client domain suffix |
| 51 | Lease Time | IP address lease time |
| 66 | TFTP Server | TFTP server name |
| 67 | Bootfile | Boot file name |

#### Example

```csv
row_id,object_type,action,config,network_path,name,code,value,server_scope
1,dhcpv4_client_deployment_option,create,Default,Default/10.0.0.0/8/10.1.1.0/24,router,3,10.1.1.1,
2,dhcpv4_client_deployment_option,create,Default,Default/10.0.0.0/8/10.1.1.0/24,dns-servers,6,"8.8.8.8,8.8.4.4",
```

---

### DHCPv4 Service Options (`dhcpv4_service_deployment_option`)

DHCP options that configure the DHCP service itself.

#### Headers

Same as DHCPv4 Client Options above.

#### Example

```csv
row_id,object_type,action,config,network_path,name,code,value,server_scope
1,dhcpv4_service_deployment_option,create,Default,Default/10.0.0.0/8/10.1.1.0/24,default-lease-time,51,86400,DHCP_SERVER
```

---

## Device Management

### Device Types (`device_type`)

Global device categories (e.g., manufacturer names).

> **Note:** Device types are GLOBAL resources, not per-configuration.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `name` | Yes | string | Device type name (e.g., `Cisco`, `Fortinet`) |

#### Example

```csv
row_id,object_type,action,name
1,device_type,create,Cisco
2,device_type,create,Fortinet
3,device_type,create,Palo Alto
```

---

### Device Subtypes (`device_subtype`)

Specific models within a device type.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `device_type` | Yes | string | Parent device type name |
| `name` | Yes | string | Subtype name (e.g., `Catalyst-9300`) |

#### Example

```csv
row_id,object_type,action,device_type,name
1,device_subtype,create,Cisco,Catalyst-9300
2,device_subtype,create,Fortinet,FortiGate-600E
3,device_subtype,create,Palo Alto,PA-3220
```

---

### Devices (`device`)

Physical or virtual network appliances.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `name` | Yes | string | Device name |
| `device_type` | No | string | Device type (optional) |
| `device_subtype` | No | string | Device subtype (requires device_type) |
| `addresses` | No | string | Pipe-separated IP addresses to associate |
| `mac_address` | No | string | Device MAC address |
| `description` | No | string | Optional description |

#### Example

```csv
row_id,object_type,action,config,name,device_type,device_subtype,addresses,mac_address,description
1,device,create,Default,firewall-01,Fortinet,FortiGate-600E,10.0.1.1|10.0.2.1,00:11:22:33:44:55,Primary firewall
2,device,create,Default,core-switch-01,Cisco,Catalyst-9300,,02:AA:BB:CC:DD:EE,Core network switch
3,device,create,Default,server-01,,,10.1.1.50,,Generic server
```

---

### Device Addresses (`device_address`)

Link IP addresses to devices after device creation.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `device_name` | Yes | string | Device name |
| `address` | Yes | string | IP address to link/unlink |

#### Example

```csv
row_id,object_type,action,config,device_name,address
1,device_address,create,Default,core-switch-01,10.0.1.254
2,device_address,create,Default,core-switch-01,10.0.2.254
3,device_address,delete,Default,firewall-01,10.0.3.1
```

---

## MAC Pool Management

### MAC Pools (`mac_pool`)

Groups of MAC addresses for DHCP control.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `name` | Yes | string | Pool name |
| `pool_type` | No | string | `MACPool` (allow) or `DenyMACPool` (deny). Default: `MACPool` |

#### Example

```csv
row_id,object_type,action,config,name,pool_type
1,mac_pool,create,Default,VoIP-Phones,MACPool
2,mac_pool,create,Default,Blocked-Devices,DenyMACPool
```

---

### MAC Addresses (`mac_address`)

Register MAC addresses, optionally associating with pools.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `mac_address` | Yes | string | MAC address |
| `name` | No | string | Optional name |
| `pool_name` | No | string | MAC pool to associate with |

#### Example

```csv
row_id,object_type,action,config,mac_address,name,pool_name
1,mac_address,create,Default,00:11:22:33:44:55,voip-phone-01,VoIP-Phones
2,mac_address,create,Default,AA:BB:CC:DD:EE:FF,blocked-device-01,Blocked-Devices
3,mac_address,create,Default,11:22:33:44:55:66,registered-device,
```

---

## Location Management

### Locations (`location`)

Hierarchical locations based on UN/LOCODE format.

> **Important:** Custom locations must be created under existing UN/LOCODE locations. Root-level creation is not supported.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `parent_code` | Yes | string | Parent location code (e.g., `US NYC`) |
| `code` | Yes | string | Full location code including hierarchy (e.g., `US NYC DC1`) |
| `name` | Yes | string | Display name |
| `description` | No | string | Optional description |
| `localizedName` | No | string | Localized name |
| `latitude` | No | float | Latitude (-90 to 90) |
| `longitude` | No | float | Longitude (-180 to 180) |

#### Common UN/LOCODE Examples

| Code | Location |
|------|----------|
| `US NYC` | New York, USA |
| `US SFO` | San Francisco, USA |
| `US LAX` | Los Angeles, USA |
| `GB LON` | London, UK |
| `DE FRA` | Frankfurt, Germany |
| `JP TYO` | Tokyo, Japan |
| `SG SIN` | Singapore |

#### Example

```csv
row_id,object_type,action,parent_code,code,name,description,latitude,longitude
1,location,create,US NYC,US NYC DC1,NYC Primary Datacenter,Primary datacenter in NYC,40.7128,-74.0060
2,location,create,US NYC DC1,US NYC DC1 F1,NYC DC1 Floor 1,First floor,40.7128,-74.0060
3,location,create,US SFO,US SFO COLO1,SF Colocation,Bay Area colo facility,37.7749,-122.4194
```

---

## User-Defined Fields & Links

### UDF Definitions (`udf_definition`)

Create custom metadata field definitions.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `name` | Yes | string | Internal name (no spaces, used in API) |
| `displayName` | No | string | Display name for UI |
| `fieldType` | Yes | string | Field type: `TEXT`, `MULTILINE_TEXT`, `URL`, `EMAIL`, `PHONE` |
| `defaultValue` | No | string | Default value |
| `required` | No | bool | Whether field is required |
| `resourceTypes` | No | string | Pipe-separated resource types or `*` for all |
| `predefinedValues` | No | string | Pipe-separated allowed values (for dropdowns) |
| `hideFromSearch` | No | bool | Hide from search results |
| `renderAsLink` | No | bool | Render URL fields as clickable links |
| `validators` | No | string | Validation regex pattern |

#### UDF Field Types

| Type | Description |
|------|-------------|
| `TEXT` | Single-line text |
| `MULTILINE_TEXT` | Multi-line text area |
| `URL` | URL (can render as link) |
| `EMAIL` | Email address |
| `PHONE` | Phone number |

#### Example

```csv
row_id,object_type,action,name,displayName,fieldType,defaultValue,required,resourceTypes,predefinedValues
1,udf_definition,create,CostCenter,Cost Center,TEXT,,false,IPv4Network|IPv4Block,
2,udf_definition,create,Environment,Environment,TEXT,Production,false,IPv4Network,Development|Staging|Production
3,udf_definition,create,Owner,Owner Email,EMAIL,,true,*,
```

---

### UDL Definitions (`udl_definition`)

Create custom link type definitions between resources.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `name` | Yes | string | Internal name (no spaces) |
| `displayName` | No | string | Display name |
| `sourceTypes` | Yes | string | Pipe-separated allowed source resource types |
| `destinationTypes` | Yes | string | Pipe-separated allowed destination resource types |

#### Example

```csv
row_id,object_type,action,name,displayName,sourceTypes,destinationTypes
1,udl_definition,create,AssociatedDevice,Associated Device,IPv4Address,Device
2,udl_definition,create,BackupServer,Backup Server,IPv4Network,Device
```

---

### User-Defined Links (`user_defined_link`)

Create actual links between resources using UDL definitions.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `udl_name` | Yes | string | UDL definition name |
| `source_type` | Yes | string | Source resource type (e.g., `ip4_address`) |
| `source_path` | Yes | string | Path to source resource |
| `destination_type` | Yes | string | Destination resource type |
| `destination_path` | Yes | string | Path to destination resource |
| `description` | No | string | Link description |

#### Example

```csv
row_id,object_type,action,config,udl_name,source_type,source_path,destination_type,destination_path,description
1,user_defined_link,create,Default,AssociatedDevice,ip4_address,10.0.1.10,device,firewall-01,Primary interface
2,user_defined_link,create,Default,BackupServer,ip4_network,10.1.0.0/24,device,backup-server-01,Network backup
```

---

### Using UDF Values on Resources

To set UDF values on resources, add columns prefixed with `udf_`:

```csv
row_id,object_type,action,config,cidr,name,udf_CostCenter,udf_Environment,udf_Owner
1,ip4_network,create,Default,10.1.0.0/24,Production-Net,CC-12345,Production,admin@example.com
2,ip4_network,create,Default,10.2.0.0/24,Dev-Net,CC-67890,Development,dev@example.com
```

> **Tip:** The UDF definition must exist before you can set values. Create UDF definitions first, then import resources with UDF values.

---

## Tags & Tagging

### Tag Groups (`tag_group`)

Organize tags into logical groups.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `name` | Yes | string | Tag group name |

#### Example

```csv
row_id,object_type,action,name
1,tag_group,create,Environment
2,tag_group,create,Owner
3,tag_group,create,Compliance
```

---

### Tags (`tag`)

Create tags within tag groups.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `name` | Yes | string | Tag name |
| `tag_group` | Yes | string | Parent tag group name |

#### Example

```csv
row_id,object_type,action,name,tag_group
1,tag,create,Production,Environment
2,tag,create,Development,Environment
3,tag,create,IT-Operations,Owner
4,tag,create,PCI-DSS,Compliance
```

---

### Resource Tags (`resource_tag`)

Apply or remove tags from resources.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `resource_type` | Yes | string | Resource type (e.g., `ip4_network`, `dns_zone`) |
| `resource_path` | Yes | string | Path to resource |
| `tag_name` | Yes | string | Tag name to apply/remove |

#### Example

```csv
row_id,object_type,action,config,resource_type,resource_path,tag_name
1,resource_tag,create,Default,ip4_network,10.1.0.0/24,Production
2,resource_tag,create,Default,ip4_network,10.1.0.0/24,PCI-DSS
3,resource_tag,create,Default,dns_zone,example.local,IT-Operations
4,resource_tag,delete,Default,ip4_network,10.2.0.0/24,Development
```

---

## Access Control

### Access Control Lists (`acl`)

DNS access control lists for controlling host access.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `config` | Yes | string | Configuration name |
| `name` | Yes | string | ACL name |
| `match_elements` | No | string | Pipe-separated IPs/CIDRs |

> **Note:** ACL updates replace the entire match elements list (no append mode).

#### Example

```csv
row_id,object_type,action,config,name,match_elements
1,acl,create,Default,internal-networks,10.0.0.0/8|172.16.0.0/12|192.168.0.0/16
2,acl,create,Default,trusted-partners,203.0.113.0/24|198.51.100.0/24
3,acl,update,Default,internal-networks,10.0.0.0/8|172.16.0.0/12|192.168.0.0/16|100.64.0.0/10
4,acl,delete,Default,deprecated-acl,
```

---

### Access Rights (`access_right`)

Control user and group permissions on BAM resources.

#### Headers

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `user_type` | Yes | string | `user` or `group` |
| `user_name` | Yes | string | Username or group name |
| `resource_type` | No | string | BAM resource type (e.g., `Configuration`) |
| `resource_path` | No | string | Path to resource |
| `config` | No | string | Configuration (when resource needs context) |
| `default_access_level` | Yes | string | Access level: `HIDE`, `VIEW`, `CHANGE`, `ADD`, `FULL` |
| `deployments_allowed` | No | bool | Allow full deployments |
| `quick_deployments_allowed` | No | bool | Allow quick DNS deployments |
| `selective_deployments_allowed` | No | bool | Allow selective deployments |
| `workflow_level` | No | string | `NONE`, `RECOMMEND`, or `APPROVE` |
| `access_overrides` | No | string | Pipe-separated type:level pairs |

#### Access Levels

| Level | Description |
|-------|-------------|
| `HIDE` | Resource is hidden |
| `VIEW` | Read-only access |
| `CHANGE` | Can modify existing resources |
| `ADD` | Can create new resources |
| `FULL` | Complete control including delete |

#### Workflow Levels

| Level | Description |
|-------|-------------|
| `NONE` | No workflow approval needed |
| `RECOMMEND` | Changes are recommendations |
| `APPROVE` | User can approve workflow requests |

#### Example

```csv
row_id,object_type,action,user_type,user_name,resource_type,resource_path,config,default_access_level,deployments_allowed,workflow_level,access_overrides
1,access_right,create,user,operator,Configuration,Default,,VIEW,false,NONE,
2,access_right,create,group,NetworkAdmins,Configuration,Production,,ADD,true,APPROVE,
3,access_right,create,user,developer,,,Default,VIEW,false,NONE,IPv4Address:FULL|HostRecord:ADD
```

---

## Multi-Section CSVs

For complex imports involving multiple object types, use multi-section CSVs with different headers per section:

```csv
# Section 1: Network Infrastructure
row_id,object_type,action,config,cidr,name,description
1,ip4_block,create,Default,10.0.0.0/8,Corporate,Corporate address space
2,ip4_network,create,Default,10.1.1.0/24,Production,Production servers

# Section 2: DNS Records (different headers)
row_id,object_type,action,config,view_path,name,addresses,ttl
10,host_record,create,Default,Internal,www.example.local,10.1.1.10,3600
11,host_record,create,Default,Internal,api.example.local,10.1.1.11,3600

# Section 3: DHCP Configuration
row_id,object_type,action,config,network_path,range,name
20,ipv4_dhcp_range,create,Default,Default/10.0.0.0/8/10.1.1.0/24,10.1.1.100-10.1.1.200,Production-DHCP
```

The importer automatically detects header changes and processes each section independently.

---

## Common Conventions

### Path Notation

| Path Type | Format | Example |
|-----------|--------|---------|
| IPv4 Block Path | `/IPv4/cidr` | `/IPv4/10.0.0.0/8` |
| IPv4 Network Path | `/IPv4/parent_cidr/network_cidr` | `/IPv4/10.0.0.0/8/10.1.0.0/24` |
| IPv6 Block Path | `/IPv6/cidr` | `/IPv6/2001:db8::/32` |
| Zone Path | `view/zone` | `Internal/example.local` |
| Network Path (DHCP) | `config/parent_cidr/network_cidr` | `Default/10.0.0.0/8/10.1.0.0/24` |

### Recommended Naming Conventions

- **Configurations**: `Default`, `Production`, `Development`
- **Views**: `Internal`, `External`, `DMZ`
- **Domains**: Use RFC 2606 reserved domains for examples (`.local`, `.example`, `.test`)
- **IP Space**: Use RFC 1918 (IPv4) or RFC 3849 (IPv6) for examples
- **Resource Names**: Use descriptive, lowercase names with hyphens (e.g., `web-server-01`)

---

## Troubleshooting

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Invalid CIDR notation` | Incorrect CIDR format | Use `x.x.x.x/prefix` format |
| `Resource not found` | Parent doesn't exist | Create parent resources first |
| `Invalid MAC address format` | Wrong MAC format | Use `XX:XX:XX:XX:XX:XX` |
| `Invalid state` | Wrong IP state value | Use valid state: `STATIC`, `RESERVED`, etc. |
| `Parent code required` | Missing location parent | Locations need parent_code |

### Validation Steps

```bash
# 1. Validate CSV syntax and schema
bluecat-import validate my_import.csv

# 2. Test with dry-run (no changes made)
bluecat-import apply my_import.csv --dry-run

# 3. Review the dry-run output before proceeding
# 4. Execute the import
bluecat-import apply my_import.csv
```

### Tips

1. **Unique row_id**: Every row needs a unique identifier for tracking
2. **Case Sensitivity**: Object types are case-sensitive (`ip4_network`, not `IP4_Network`)
3. **Path Separators**: Use forward slashes (`/`) in paths
4. **Empty Values**: Leave optional fields empty (not `null` or `N/A`)
5. **Dependencies**: Import parent resources before children
6. **Whitespace**: Leading/trailing whitespace is automatically trimmed

---

## See Also

- [TUTORIAL.md](TUTORIAL.md) - Step-by-step tutorial
- [CLI_REFERENCE.md](CLI_REFERENCE.md) - Command-line reference
- [EXPORT_GUIDE.md](EXPORT_GUIDE.md) - Exporting data from BAM
- [samples/](../samples/) - Example CSV files
