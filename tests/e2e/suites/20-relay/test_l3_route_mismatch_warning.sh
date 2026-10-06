#!/usr/bin/env bash
# E2E Test: Layer 3 Route Mismatch & Broadcast Warnings
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"

DHCPT="${DHCPT_CMD:-ip netns exec workstation env PYTHONPATH=src python3 -m dhcpt}"
TUN_IFACE="${CLIENT_WORKSTATION_L3_IFACE:-tun-client}"
MISMATCH_SERVER="${DHCP_SERVER_LEGIT_IP:-10.99.0.1}"

# 1. Test Route Egress Mismatch Warning
output_mismatch=$($DHCPT --interface "$TUN_IFACE" --dhcp-servers "$MISMATCH_SERVER" --timeout 0.5 2>&1 || true)
assert_contains "Route mismatch warning" "routed via 'veth-client', not specified Layer 3 interface 'tun-client'" "$output_mismatch"

# 2. Test Layer 3 Without Servers Broadcast Requirement
set +e
output_no_server=$($DHCPT --interface "$TUN_IFACE" 2>&1)
exit_code_no_server=$?
set -e

assert_exit_code "L3 without servers exit code" 2 "$exit_code_no_server" "$output_no_server"
assert_contains "L3 without broadcast capability error" "without broadcast capability" "$output_no_server"
