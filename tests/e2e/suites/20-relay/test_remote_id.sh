#!/usr/bin/env bash
# E2E Test: Unicast Relay with Option 82 Remote ID & Switch MAC Policy Enforcement
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"

DHCPT="${DHCPT_CMD:-ip netns exec workstation env PYTHONPATH=src python3 -m dhcpt}"
IFACE="${CLIENT_WORKSTATION_L2_IFACE:-veth-client}"
SERVER="${DHCP_SERVER_LEGIT_IP:-10.99.0.1}"
GATEWAY="${DHCP_TARGET_GATEWAY:-10.50.1.1}"
SECURE_GATEWAY="10.60.1.1"
AUTHORIZED_SWITCH_MAC="00:11:22:33:44:aa"

# 1. Basic Remote-ID Echoing Test
set +e
json_out=$($DHCPT --interface "$IFACE" --dhcp-servers "$SERVER" --target-gateway "$GATEWAY" --remote-id switch-core-01 --json 2>&1)
exit_echo=$?
set -e

assert_exit_code "Remote-ID query exit code" 0 "$exit_echo" "$json_out"
remote_id=$(echo "$json_out" | jq --raw-output '.offers[0]?.relay_info?.remote_id // empty')
assert_equals "Option 82 Remote-ID" "switch-core-01" "$remote_id"

# 2. Switch MAC Authorization Policy Test:
# Subnet 10.60.1.0/24 in Kea requires client-class 'switch-authorized' (Remote ID == 00:11:22:33:44:aa)
set +e
json_secure=$($DHCPT --interface "$IFACE" --dhcp-servers "$SERVER" --target-gateway "$SECURE_GATEWAY" --remote-id "$AUTHORIZED_SWITCH_MAC" --json 2>&1)
exit_secure=$?
set -e

assert_exit_code "Authorized switch query exit code" 0 "$exit_secure" "$json_secure"
secure_offered_ip=$(echo "$json_secure" | jq --raw-output '.offers[0]?.offered_ip // empty')
assert_contains "Authorized switch offered IP matches 10.60.1.x" "10.60.1." "$secure_offered_ip"

# 3. Unauthorized Switch Access Test:
# Supplying an unauthorized Remote ID must result in Kea rejecting the allocation (exit code 1)
set +e
output_unauth=$($DHCPT --interface "$IFACE" --dhcp-servers "$SERVER" --target-gateway "$SECURE_GATEWAY" --remote-id "00:99:99:99:99:99" --timeout 1 2>&1)
exit_unauth=$?
set -e

assert_exit_code "Unauthorized Remote-ID timeout exit code" 1 "$exit_unauth" "$output_unauth"
