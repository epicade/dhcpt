#!/usr/bin/env bash
# E2E Test: Standard Layer 2 Broadcast Discover on local subnet
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"

DHCPT="${DHCPT_CMD:-ip netns exec workstation env PYTHONPATH=src python3 -m dhcpt}"
IFACE="${CLIENT_WORKSTATION_L2_IFACE:-veth-client}"

set +e
output=$($DHCPT --interface "$IFACE" 2>&1)
exit_code=$?
set -e

assert_exit_code "L2 Broadcast Discover on ${IFACE}" 0 "$exit_code" "$output"
assert_contains "Received DHCP OFFER #1" "DHCP OFFER #1" "$output"
