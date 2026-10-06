#!/usr/bin/env bash
# E2E Test: Static IP Reservation via MAC spoofing (--mac 00:11:22:33:44:55 -> 10.99.0.42)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"

DHCPT="${DHCPT_CMD:-ip netns exec workstation env PYTHONPATH=src python3 -m dhcpt}"
IFACE="${CLIENT_WORKSTATION_L2_IFACE:-veth-client}"
TARGET_MAC="${DHCP_RESERVED_CLIENT_MAC:-00:11:22:33:44:55}"
EXPECTED_IP="${DHCP_RESERVED_OFFERED_IP:-10.99.0.42}"
LEGIT_SERVER="${DHCP_SERVER_LEGIT_IP:-10.99.0.1}"

# Use --all to collect offers from both legitimate and rogue servers on the bridge
set +e
json_out=$($DHCPT --interface "$IFACE" --mac "$TARGET_MAC" --all --timeout 1 --json 2>&1)
exit_code=$?
set -e

assert_exit_code "MAC reservation query" 0 "$exit_code" "$json_out"
reserved_ip=$(echo "$json_out" | jq --raw-output --arg srv "$LEGIT_SERVER" '.offers[]? | select(.server_ip==$srv) | .offered_ip // empty')
assert_equals "Reserved IP for MAC ${TARGET_MAC}" "$EXPECTED_IP" "$reserved_ip"
