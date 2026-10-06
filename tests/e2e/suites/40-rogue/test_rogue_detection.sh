#!/usr/bin/env bash
# E2E Test: Rogue DHCP Detection (--all captures both legitimate 10.99.0.1 and rogue 10.99.0.254)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"

DHCPT="${DHCPT_CMD:-ip netns exec workstation env PYTHONPATH=src python3 -m dhcpt}"
IFACE="${CLIENT_WORKSTATION_L2_IFACE:-veth-client}"
LEGIT_SERVER="${DHCP_SERVER_LEGIT_IP:-10.99.0.1}"
ROGUE_SERVER="${DHCP_SERVER_ROGUE_IP:-10.99.0.254}"

set +e
json_out=$($DHCPT --interface "$IFACE" --all --timeout 2 --json 2>&1)
exit_code=$?
set -e

assert_exit_code "Rogue detection query exit code" 0 "$exit_code" "$json_out"
servers=$(echo "$json_out" | jq --raw-output '[.offers[]?.server_ip] | unique | sort | join(",")')

assert_contains "Captures legitimate server ${LEGIT_SERVER}" "$LEGIT_SERVER" "$servers"
assert_contains "Captures rogue server ${ROGUE_SERVER}" "$ROGUE_SERVER" "$servers"
