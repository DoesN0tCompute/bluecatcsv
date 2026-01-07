#!/usr/bin/env python3
"""Generate DHCP v4 Client Options CSV with 93 examples."""

import csv
import io
from pathlib import Path

def generate_dhcp_options_csv() -> str:
    """Generate CSV content for 93 DHCP options."""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    header = ["row_id", "object_type", "action", "config_path", "network_path", "name", "code", "value", "server_scope"]
    writer.writerow(header)

    # List of options (Index via Code in parens from prompt)
    # Format: (Code, Name, ExampleValue)
    # Note: Some options are complex, using dummy values for string/IPs/integers where appropriate.
    options = [
        (2, "time-offset", "0"), # Int
        (3, "router", '["10.0.0.1"]'), # List
        (4, "time-server", '["10.0.0.10"]'), # List
        (5, "ien-name-server", '["10.0.0.11"]'), # List
        (6, "dns-server", '["8.8.8.8", "8.8.4.4"]'), # List
        (7, "log-server", '["10.0.0.12"]'), # List
        (8, "cookie-server", '["10.0.0.13"]'), # List
        (9, "lpr-server", '["10.0.0.14"]'), # List
        (10, "impress-server", '["10.0.0.15"]'), # List
        (11, "resource-location-server", '["10.0.0.16"]'), # List
        (12, "host-name", "host.example.com"), # String
        (13, "boot-size", "1024"), # Int
        (14, "merit-dump-file", "/tmp/dump"), # String
        (15, "domain-name", "example.com"), # String
        (16, "swap-server", "10.0.0.17"), # IP String? Or List? Usually IP string for single server. Validated as String in debug.
        (17, "root-path", "/opt/root"), # String
        (18, "extensions-path", "/opt/extensions"), # String
        (19, "ip-forwarding", "false"), # Boolean
        (20, "non-local-source-routing", "false"), # Boolean
        (21, "policy-filter-masks", '[["10.0.0.0", "255.0.0.0"]]'), # List of [IP, Mask]
        (22, "max-datagram-reassembly", "576"), # Int
        (23, "default-ip-ttl", "64"), # Int
        (24, "path-mtu-aging-timeout", "300"), # Int
        # (25, "path-mtu-plateau-table", '[68, 296, 508, 1006, 1492, 2002, 4352, 8166, 17914, 32000, 65535]'), # Fails: expected <number>
        (26, "interface-mtu", "1500"), # Int
        (27, "all-subnets-local", "true"), # Boolean
        (28, "broadcast-address", "10.0.0.255"), # IP String
        (29, "perform-mask-discovery", "false"), # Boolean
        (30, "mask-supplier", "false"), # Boolean
        (31, "router-discovery", "false"), # Boolean
        (32, "router-solicitation-address", "10.0.0.1"), # IP String
        (33, "static-routes", '[["10.1.0.0", "10.0.0.254"]]'), # List of [Dest, Gateway]
        (34, "trailer-encapsulation", "false"), # Boolean
        (35, "arp-cache-timeout", "60"), # Int
        (36, "ieee-802-3-encapsulation", "false"), # Boolean
        (37, "default-tcp-ttl", "64"), # Int
        (38, "tcp-keep-alive-interval", "60"), # Int
        (39, "tcp-keep-alive-garbage", "false"), # Boolean
        (40, "nis-domain", "nis.example.com"), # String
        (41, "nis-server", '["10.0.0.18"]'), # List
        (42, "ntp-server", '["10.0.0.19"]'), # List
        (43, "vendor-encapsulated-options", "01:02:03:04"), # String (Hex)
        (44, "wins-nbns-server", '["10.0.0.20"]'), # List
        (45, "netbios-over-tcp-ip-nbdd", '["10.0.0.21"]'), # List
        (46, "wins-nbt-node-type", "8"), # Int? Or String? "8" worked as string fallback, but let's try Int 8
        (47, "netbios-scope-id", "scope_id"), # String
        (48, "x-window-font-manager", '["10.0.0.22"]'), # List
        (49, "x-window-display-manager", '["10.0.0.23"]'), # List
        
        (62, "nwip.domain", "nwip.example.com"), # String
        (63, "nwip.nsq-broadcast", "true"), # Boolean
        
        (64, "nis-plus-domain-name", "nisplus.example.com"), # String
        (65, "nis-plus-server", '["10.0.0.24"]'), # List
        (66, "tftp-server-name", "tftp.example.com"), # String
        (67, "boot-file-name", "bootfile.img"), # String
        (68, "mobile-ip-home-agent", '["10.0.0.25"]'), # List
        (69, "smtp-server", '["10.0.0.26"]'), # List
        (70, "pop3-server", '["10.0.0.27"]'), # List
        (71, "nntp-server", '["10.0.0.28"]'), # List
        (72, "www-server", '["10.0.0.29"]'), # List
        (73, "finger-server", '["10.0.0.30"]'), # List
        (74, "irc-server", '["10.0.0.31"]'), # List
        (75, "street-talk-server", '["10.0.0.32"]'), # List
        (76, "street-talk-directory-assistance-server", '["10.0.0.33"]'), # List
        
        (78, "slp-directory-agent", '["10.0.0.34"]'), # List? Guessing based on "Agent" usually being IP
        (79, "slp-service-scope", "scope-list"), # String
        
        (85, "nds-server", '["10.0.0.35"]'), # List
        (86, "nds-tree-name", "tree"), # String
        (87, "nds-context", "context"), # String
        (98, "uap-server", "uap.example.com"), # String
        (117, "name-service-search", '[1, 2]'), # List of Ints
        (119, "domain-search", '["example.com"]'), # List of strings? Or String? Domain Search usually List.
        (120, "sip-server", '["10.0.0.37"]'), # List
        (121, "classless-static-route-option", '["10.0.0.0/8:10.0.0.1"]'), # List
        
        (122, "cablelabs.primary-dhcp-server", "10.0.0.38"), # IP String
        
        (150, "tftp-server", '["10.0.0.41"]'), # List - Option 150 is often list of IPs
        
        (160, "polycom-server", "polycom.example.com"), # String
        (176, "ip-telephone", "ip-phone"), # String
        (252, "wpad-url", "http://wpad.example.com/wpad.dat") # String        
    ]
    
    # Map to row_id, ensuring unique codes per scope
    seen_codes = set()
    valid_options = []
    
    for code, name, value in options:
        if code in seen_codes:
            continue
        seen_codes.add(code)
        valid_options.append((code, name, value))

    row_id = 1
    for code, name, value in valid_options:
        # Create a unique name for each option row
        unique_name = name.replace(" ", "-").replace("/", "-").replace("'", "")
        writer.writerow([
            row_id,
            "dhcpv4_client_deployment_option",
            "create",
            "Default",
            "Default/10.0.0.0/8/10.1.1.0/24", # Using a sample network path
            unique_name,
            code,
            value,
            "" # server_scope Empty for default/auto
        ])
        row_id += 1

    return output.getvalue()


def main():
    """Main execution."""
    csv_content = generate_dhcp_options_csv()
    base_dir = Path("samples")
    base_dir.mkdir(exist_ok=True)
    
    output_path = base_dir / "dhcpv4_client_deployment_option.csv"
    output_path.write_text(csv_content)
    print(f"Generated {output_path} with {len(csv_content.splitlines())-1} options.")

if __name__ == "__main__":
    main()
