#!/usr/bin/env bash
# E2E Test: MAC Reservation over Unicast Relay (--mac 00:11:22:33:44:55)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"

DHCPT="${DHCPT_CMD:-ip netns exec workstation env PYTHONPATH=src python3 -m dhcpt}"
IFACE="${CLIENT_WORKSTATION_L2_IFACE:-veth-client}"
SERVER="${DHCP_SERVER_LEGIT_IP:-10.99.0.1}"
TARGET_MAC="${DHCP_RESERVED_CLIENT_MAC:-00:11:22:33:44:55}"
EXPECTED_IP="${DHCP_RESERVED_OFFERED_IP:-10.99.0.42}"

set +e
json_out=$($DHCPT --interface "$IFACE" --dhcp-servers "$SERVER" --mac "$TARGET_MAC" --json 2>&1)
exit_code=$?
set -e

assert_exit_code "MAC reservation over relay exit code" 0 "$exit_code" "$json_out"
reserved_ip=$(echo "$json_out" | jq --raw-output --arg srv "$SERVER" '.offers[]? | select(.server_ip==$srv) | .offered_ip // empty')
assert_equals "Reserved IP for ${TARGET_MAC} over relay" "$EXPECTED_IP" "$reserved_ip"
