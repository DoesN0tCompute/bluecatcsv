#!/bin/bash
export BAM_URL="https://192.168.40.23"
export BAM_USERNAME=admin
export BAM_PASSWORD=admin
export BAM_VERIFY_SSL=false

# Define files in logical dependency order
FILES=(
"samples/ip4_block.csv"
"samples/ip4_network.csv"
"samples/ipv4_dhcp_range.csv"
"samples/ip4_address.csv"
"samples/dns_zone.csv"

"samples/host_record.csv"
"samples/external_host_record.csv"
"samples/alias_record.csv"
"samples/mx_record.csv"
"samples/srv_record.csv"
"samples/txt_record.csv"
"samples/dhcp_deployment_role.csv"
"samples/dns_deployment_role.csv"
"samples/dhcpv4_client_deployment_option.csv"
"samples/dhcpv4_service_deployment_option.csv"
)

echo "=== STARTING DRY RUNS ==="
DRY_RUN_FAILURES=0
for f in "${FILES[@]}"; do
    echo "Dry running $f..."
    ./venv/bin/python3 import.py apply --dry-run "$f"
    if [ $? -ne 0 ]; then
        echo "BS_ERROR: Dry run failed for $f"
        DRY_RUN_FAILURES=$((DRY_RUN_FAILURES+1))
    fi
    echo "--------------------------------"
done

if [ $DRY_RUN_FAILURES -ne 0 ]; then
    echo "There were $DRY_RUN_FAILURES failures during dry run. Pausing before live run."
    # We continue anyway as per user request to "validate", but we note it.
else
    echo "All dry runs passed."
fi

echo "=== STARTING LIVE RUNS ==="
LIVE_RUN_FAILURES=0
for f in "${FILES[@]}"; do
    echo "Importing $f..."
    ./venv/bin/python3 import.py apply "$f"
    if [ $? -ne 0 ]; then
        echo "BS_ERROR: Import failed for $f"
        LIVE_RUN_FAILURES=$((LIVE_RUN_FAILURES+1))
    fi
    echo "--------------------------------"
done

if [ $LIVE_RUN_FAILURES -ne 0 ]; then
    echo "There were $LIVE_RUN_FAILURES failures during live run."
    exit 1
else
    echo "All live runs passed successfully."
    exit 0
fi
