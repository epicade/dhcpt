#!/usr/bin/env bash
# E2E Test: RFC 3442 Classless Static Routes (Option 121) and Domain Search (Option 119)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"

DHCPT="${DHCPT_CMD:-ip netns exec workstation env PYTHONPATH=src python3 -m dhcpt}"
IFACE="${CLIENT_WORKSTATION_L2_IFACE:-veth-client}"
SERVER="${DHCP_SERVER_LEGIT_IP:-10.99.0.1}"

# Query legitimate server via unicast to inspect decoded options
set +e
json_out=$($DHCPT --interface "$IFACE" -s "$SERVER" --json 2>&1)
exit_code=$?
set -e

assert_exit_code "Classless routes query" 0 "$exit_code" "$json_out"

# 1. Assert Classless Static Routes decoding (Option 121)
routes=$(echo "$json_out" | jq --raw-output --arg srv "$SERVER" '.offers[]? | select(.server_ip==$srv) | .classless_routes[]?' 2>/dev/null || true)
assert_contains "Route 1 decoded" "10.0.0.0/8 via 10.99.0.1" "$routes"
assert_contains "Route 2 decoded" "192.168.50.0/24 via 10.99.0.254" "$routes"

# 2. Assert Domain Search List decoding (Option 119)
domains=$(echo "$json_out" | jq --raw-output --arg srv "$SERVER" '.offers[]? | select(.server_ip==$srv) | .domain_search[]?' 2>/dev/null || true)
assert_contains "Domain Search entry 1" "example.com" "$domains"
assert_contains "Domain Search entry 2" "corp.internal" "$domains"
