#!/bin/bash
export BAM_URL="https://192.168.40.23"
export BAM_USERNAME=admin
export BAM_PASSWORD=admin
export BAM_VERIFY_SSL=false

FILES=(
"samples/location.csv"
"samples/ip6_block.csv"
"samples/ip6_network.csv"
"samples/ipv6_dhcp_range.csv"
"samples/ip6_address.csv"
"samples/location_associations.csv"
"samples/generic_record.csv"
)

echo "=== STARTING REMAINING SAMPLES VALIDATION ==="
FAILURES=0

for f in "${FILES[@]}"; do
    echo "Processing $f..."
    # We do dry run then live run for each, similar to validate_samples.sh
    echo "  [Dry Run] $f"
    ./venv/bin/python3 import.py apply --dry-run "$f"
    if [ $? -ne 0 ]; then
        echo "BS_ERROR: Dry run failed for $f"
        FAILURES=$((FAILURES+1))
        continue
    fi
    
    echo "  [Live Run] $f"
    ./venv/bin/python3 import.py apply "$f"
    if [ $? -ne 0 ]; then
        echo "BS_ERROR: Live run failed for $f"
        FAILURES=$((FAILURES+1))
    fi
    echo "--------------------------------"
done

if [ $FAILURES -ne 0 ]; then
    echo "There were $FAILURES failures."
    exit 1
else
    echo "All remaining samples passed."
    exit 0
fi
