#!/usr/bin/env bash
# E2E Test: Curl-style Verbose (-v) and Debug (-vv / -d) Logging
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"

DHCPT="${DHCPT_CMD:-ip netns exec workstation env PYTHONPATH=src python3 -m dhcpt}"
IFACE="${CLIENT_WORKSTATION_L2_IFACE:-veth-client}"

# 1. Test -v (Verbose protocol milestones in curl style)
set +e
output_v=$($DHCPT --interface "$IFACE" -v 2>&1)
exit_v=$?
set -e

assert_exit_code "Verbose run exit code" 0 "$exit_v" "$output_v"
assert_contains "Interface state line" "* Interface: ${IFACE}" "$output_v"
assert_contains "Curl send arrow" "> DHCPDISCOVER" "$output_v"
assert_contains "Curl recv arrow" "< DHCPOFFER" "$output_v"
assert_contains "Completion line" "* Completed in" "$output_v"
assert_contains "Final offers table" "DHCP OFFER #1" "$output_v"

# 2. Test -vv / -d (Deep packet tree and layer breakdown)
set +e
output_vv=$($DHCPT --interface "$IFACE" -vv 2>&1)
exit_vv=$?
set -e

assert_exit_code "Debug run exit code" 0 "$exit_vv" "$output_vv"
assert_contains "Ethernet layer tree" "├── Ethernet" "$output_vv"
assert_contains "IPv4 layer tree" "├── IPv4" "$output_vv"
assert_contains "BOOTP layer tree" "├── BOOTP" "$output_vv"
assert_contains "DHCP layer tree" "DHCP" "$output_vv"
assert_contains "Outgoing tree title" "> Outgoing DHCP Discover" "$output_vv"
assert_contains "Incoming tree title" "< Incoming DHCP Packet" "$output_vv"
