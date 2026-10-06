#!/usr/bin/env bash
# E2E Test: Unicast Offer Delivery (--no-broadcast)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"

DHCPT="${DHCPT_CMD:-ip netns exec workstation env PYTHONPATH=src python3 -m dhcpt}"
IFACE="${CLIENT_WORKSTATION_L2_IFACE:-veth-client}"

set +e
json_out=$($DHCPT --interface "$IFACE" --no-broadcast --json 2>&1)
exit_code=$?
set -e

assert_exit_code "Unicast delivery query exit code" 0 "$exit_code" "$json_out"
offers_count=$(echo "$json_out" | jq --raw-output '.offers_count // 0')
[ "$offers_count" -ge 1 ] 2>/dev/null || offers_count="0"
assert_not_empty "Offers received via unicast" "$offers_count"
