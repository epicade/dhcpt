#!/usr/bin/env bash
# E2E Test: Unicast Relay Simulation via RFC 3527 Link Selection (--target-gateway)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"

DHCPT="${DHCPT_CMD:-ip netns exec workstation env PYTHONPATH=src python3 -m dhcpt}"
IFACE="${CLIENT_WORKSTATION_L2_IFACE:-veth-client}"
SERVER="${DHCP_SERVER_LEGIT_IP:-10.99.0.1}"
GATEWAY="${DHCP_TARGET_GATEWAY:-10.50.1.1}"

set +e
json_out=$($DHCPT --interface "$IFACE" --dhcp-servers "$SERVER" --target-gateway "$GATEWAY" --json 2>&1)
exit_code=$?
set -e

assert_exit_code "Target gateway query exit code" 0 "$exit_code" "$json_out"
offered_ip=$(echo "$json_out" | jq --raw-output '.offers[0]?.offered_ip // empty')
assert_contains "Offered IP matches target gateway subnet 10.50.1.x" "10.50.1." "$offered_ip"
