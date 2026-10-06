#!/usr/bin/env bash
# E2E Test: Full Human-Readable Text Table Formatting
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"

DHCPT="${DHCPT_CMD:-ip netns exec workstation env PYTHONPATH=src python3 -m dhcpt}"
IFACE="${CLIENT_WORKSTATION_L2_IFACE:-veth-client}"
SERVER="${DHCP_SERVER_LEGIT_IP:-10.99.0.1}"

# Query legitimate server without --json flag to inspect human text table output
set +e
output=$($DHCPT --interface "$IFACE" -s "$SERVER" 2>&1)
exit_code=$?
set -e

assert_exit_code "Text mode query exit code" 0 "$exit_code" "$output"

# Assert table headers and core sections
assert_contains "Offer table header" "DHCP OFFER #1 (Server: ${SERVER})" "$output"
assert_contains "Offered IP field" "Offered IP (yiaddr)" "$output"
assert_contains "Subnet mask & CIDR" "255.255.255.0 (/24)" "$output"
assert_contains "Default Gateway field" "Default Gateway (Opt 3)" "$output"
assert_contains "DNS Servers field" "DNS Servers (Opt 6)" "$output"
assert_contains "Classless routes section" "Classless Static Routes (RFC 3442 / VPN & Enterprise):" "$output"
assert_contains "Route 1 entry" "10.0.0.0/8 via 10.99.0.1" "$output"
assert_contains "Route 2 entry" "192.168.50.0/24 via 10.99.0.254" "$output"
assert_contains "Lease section" "Lease Information:" "$output"
assert_contains "Lease time field" "Lease Time (Opt 51)" "$output"
assert_contains "Server ID field" "DHCP Server ID (Opt 54)" "$output"
