#!/usr/bin/env bash
# E2E Test: Multi-Server Unicast Query with Partial Failure (Exit-Code 3)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"

DHCPT="${DHCPT_CMD:-ip netns exec workstation env PYTHONPATH=src python3 -m dhcpt}"
IFACE="${CLIENT_WORKSTATION_L2_IFACE:-veth-client}"
SERVER_ALIVE="${DHCP_SERVER_LEGIT_IP:-10.99.0.1}"
SERVER_DEAD="${DHCP_SERVER_TIMEOUT_IP:-10.99.0.99}"

set +e
output=$($DHCPT --interface "$IFACE" --dhcp-servers "${SERVER_ALIVE},${SERVER_DEAD}" --timeout 1 2>&1)
exit_code=$?
set -e

assert_exit_code "Multi-server partial failure" 3 "$exit_code" "$output"
