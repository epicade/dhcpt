#!/usr/bin/env bash
# E2E Test: Custom Options Request & Option Clearing (--request-options & --clear-default-options)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"

DHCPT="${DHCPT_CMD:-ip netns exec workstation env PYTHONPATH=src python3 -m dhcpt}"
IFACE="${CLIENT_WORKSTATION_L2_IFACE:-veth-client}"
LEGIT_SERVER="${DHCP_SERVER_LEGIT_IP:-10.99.0.1}"

# 1. Custom options request (-o 26,67 -> MTU & Bootfile)
set +e
json_out=$($DHCPT --interface "$IFACE" --request-options 26,67 --all --timeout 1 --json 2>&1)
exit_code1=$?
set -e

assert_exit_code "Custom options query" 0 "$exit_code1" "$json_out"
mtu_val=$(echo "$json_out" | jq --raw-output --arg srv "$LEGIT_SERVER" '[.offers[]? | select(.server_ip==$srv) | .options[]? | select(.code==26) | .value] | .[0] // empty')
boot_val=$(echo "$json_out" | jq --raw-output --arg srv "$LEGIT_SERVER" '[.offers[]? | select(.server_ip==$srv) | .options[]? | select(.code==67) | .value] | .[0] // empty')

assert_equals "Option 26 (MTU)" "1400" "$mtu_val"
assert_equals "Option 67 (Bootfile)" "pxelinux.0" "$boot_val"

# 2. Clear default options (--clear-default-options -o 26):
set +e
json_clear=$($DHCPT --interface "$IFACE" -s 10.99.0.1 --clear-default-options --request-options 26 --timeout 1 --json 2>&1)
exit_code2=$?
set -e

assert_exit_code "Clear default options query" 0 "$exit_code2" "$json_clear"
req_opts=$(echo "$json_clear" | jq --compact-output '.requested_options // []')
assert_equals "Requested options list" "[26]" "$req_opts"

has_opt67=$(echo "$json_clear" | jq --raw-output '.offers[]? | select(.server_ip=="10.99.0.1") | any(.options[]; .code==67)')
assert_equals "Option 67 absent when omitted from PRL" "false" "$has_opt67"
