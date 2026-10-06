#!/usr/bin/env bash
# E2E Test: Layer 3 Point-to-Point VPN Tunnel Testing (tun-client routed via vpn-gw)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"

DHCPT="${DHCPT_CMD:-ip netns exec workstation env PYTHONPATH=src python3 -m dhcpt}"
TUN_IFACE="${CLIENT_WORKSTATION_L3_IFACE:-tun-client}"
TUN_SERVER="${DHCP_SERVER_L3_ROUTED_IP:-10.77.0.1}"
TUN_GATEWAY="${CLIENT_VPNGW_L3_IP:-10.88.0.1}"
REMOTE_GATEWAY="${DHCP_TARGET_GATEWAY:-10.50.1.1}"

# 1. Query L3 Tunnel Subnet Pool (10.88.0.x via router tunnel gateway)
set +e
json_out=$($DHCPT --interface "$TUN_IFACE" --dhcp-servers "$TUN_SERVER" --target-gateway "$TUN_GATEWAY" --json 2>&1)
exit_code=$?
set -e

assert_exit_code "L3 VPN tunnel query" 0 "$exit_code" "$json_out"

offered_ip=$(echo "$json_out" | jq --raw-output '.offers[0]?.offered_ip // empty')
server_ip=$(echo "$json_out" | jq --raw-output '.offers[0]?.server_ip // empty')
server_mac=$(echo "$json_out" | jq --raw-output '.offers[0]?.server_mac // empty')

assert_contains "Offered IP in VPN pool 10.88.0.x" "10.88.0." "$offered_ip"
assert_equals "Server MAC framing on L3" "n/a (Layer 3)" "$server_mac"
assert_equals "Responding Server IP" "$TUN_SERVER" "$server_ip"

# 2. Query Remote Relay Subnet Pool across the L3 Tunnel (10.50.1.x via remote datacenter gateway)
set +e
json_remote=$($DHCPT --interface "$TUN_IFACE" --dhcp-servers "$TUN_SERVER" --target-gateway "$REMOTE_GATEWAY" --json 2>&1)
exit_code_remote=$?
set -e

assert_exit_code "L3 remote pool query" 0 "$exit_code_remote" "$json_remote"

offered_remote_ip=$(echo "$json_remote" | jq --raw-output '.offers[0]?.offered_ip // empty')
server_remote_ip=$(echo "$json_remote" | jq --raw-output '.offers[0]?.server_ip // empty')
server_remote_mac=$(echo "$json_remote" | jq --raw-output '.offers[0]?.server_mac // empty')

assert_contains "Offered IP across tunnel for remote pool 10.50.1.x" "10.50.1." "$offered_remote_ip"
assert_equals "Server MAC framing on remote L3 query" "n/a (Layer 3)" "$server_remote_mac"
assert_equals "Responding Server IP on remote L3 query" "$TUN_SERVER" "$server_remote_ip"
