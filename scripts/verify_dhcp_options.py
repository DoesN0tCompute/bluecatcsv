
import asyncio
import csv
import os
import httpx
from typing import Dict, Any, List

# Configuration from env or defaults
BAM_URL = os.environ.get("BAM_URL", "https://192.168.40.23")
BAM_USERNAME = os.environ.get("BAM_USERNAME", "admin")
BAM_PASSWORD = os.environ.get("BAM_PASSWORD", "admin")
BAM_VERIFY_SSL = os.environ.get("BAM_VERIFY_SSL", "false").lower() == "true"
CSV_PATH = "samples/dhcpv4_client_deployment_option.csv"

# API Endpoints
API_BASE = f"{BAM_URL.rstrip('/')}/api/v2"
TOKENS_ENDPOINT = f"{API_BASE}/sessions"
NETWORKS_ENDPOINT = f"{API_BASE}/networks"

async def authenticate() -> tuple[str, str]:
    """Authenticate and return (token, basic_creds)."""
    async with httpx.AsyncClient(verify=BAM_VERIFY_SSL) as client:
        print(f"Authenticating to {BAM_URL}...")
        resp = await client.post(
            TOKENS_ENDPOINT,
            json={"username": BAM_USERNAME, "password": BAM_PASSWORD}
        )
        if resp.status_code != 201:
            print(f"Authentication failed: {resp.status_code} {resp.text}")
            exit(1)
        data = resp.json()
        return data["apiToken"], data["basicAuthenticationCredentials"]

async def find_test_network(client: httpx.AsyncClient, auth_header: Dict[str, str]):
    """Find a suitable network to test on."""
    # Try to find the network used in samples "10.1.1.0/24"
    # Using filter syntax
    print("Finding test network 10.1.1.0/24...")
    resp = await client.get(
        NETWORKS_ENDPOINT,
        headers=auth_header,
        params={"filter": "range:'10.1.1.0/24'"}
    )
    
    if resp.status_code == 200:
        data = resp.json().get("data", [])
        if data:
            net = data[0]
            print(f"Found network: {net['name']} (ID: {net['id']})")
            return net['id']
            
    # Fallback to any IPv4 network
    print("Specific network not found, fetching ANY IPv4 network...")
    # We can't easily filter by type in all BAM versions via 'filter' query param on /networks unique to v2 sometimes.
    # But we can fetch list and filter client side.
    resp = await client.get(NETWORKS_ENDPOINT, headers=auth_header, params={"limit": 20})
    if resp.status_code == 200:
        data = resp.json().get("data", [])
        for net in data:
            if net.get("type") == "IPv4Network":
                print(f"Using fallback IPv4 network: {net['name']} (ID: {net['id']})")
                return net['id']
            
    print("No networks found in BAM. Cannot proceed.")
    exit(1)

async def test_option(
    client: httpx.AsyncClient, 
    auth_header: Dict[str, str], 
    network_id: int, 
    row: Dict[str, str]
):
    """Test creating a single DHCP option."""
    endpoint = f"{API_BASE}/networks/{network_id}/deploymentOptions"
    
    val = row["value"]
    
    val = row["value"]
    
    # Mirror OperationFactory logic: Try parsing as JSON, fallback to string
    import json
    try:
        final_value = json.loads(val)
    except (json.JSONDecodeError, TypeError):
        final_value = val

    payload = {
        "type": "DHCPv4ClientOption",
        "name": row["name"],
        "code": int(row["code"]),
        "value": final_value
        # "serverScope": row["server_scope"]  # Removed/Empty in CSV now
    }
    
    print(f"Testing Option Code {row['code']} ({row['name']})... ", end="", flush=True)
    
    try:
        resp = await client.post(endpoint, headers=auth_header, json=payload)
        
        if resp.status_code == 201:
            print("SUCCESS")
            return True, None
        elif resp.status_code == 409:
             print(f"ALREADY EXISTS (Assume Success for format check)")
             return True, "Already Exists"
        else:
            print(f"FAILED ({resp.status_code})")
            print(f"  Error: {resp.text}")
            return False, resp.text
            
    except Exception as e:
        print(f"EXCEPTION: {e}")
        return False, str(e)

async def main():
    token, creds = await authenticate()
    auth_header = {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(verify=BAM_VERIFY_SSL, timeout=10.0) as client:
        network_id = await find_test_network(client, auth_header)
        
        # Read CSV
        with open(CSV_PATH, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
        print(f"Starting verification of {len(rows)} options...")
        print("-" * 60)
        
        failures = []
        
        for row in rows:
            success, error = await test_option(client, auth_header, network_id, row)
            if not success:
                failures.append({
                    "code": row["code"],
                    "name": row["name"],
                    "value": row["value"],
                    "error": error
                })
        
        print("-" * 60)
        print(f"Verification Complete. {len(failures)} failures found.")
        
        if failures:
            print("\nFailures Detail:")
            for f in failures:
                print(f"Code {f['code']} ({f['name']}): {f['error']}")

if __name__ == "__main__":
    asyncio.run(main())
