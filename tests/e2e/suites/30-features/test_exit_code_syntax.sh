#!/usr/bin/env bash
# E2E Test: CLI Usage & Syntax Errors (Exit-Code 2)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"

DHCPT="${DHCPT_CMD:-ip netns exec workstation env PYTHONPATH=src python3 -m dhcpt}"
IFACE="${CLIENT_WORKSTATION_L2_IFACE:-veth-client}"

# 1. Invalid MAC address format
set +e
output=$($DHCPT --interface "$IFACE" --mac "invalid-mac-string" 2>&1)
code=$?
set -e
assert_exit_code "Invalid MAC" 2 "$code" "$output"
assert_contains "Invalid MAC error message" "Invalid MAC address" "$output"

# 2. Invalid DHCP Server IP
set +e
output=$($DHCPT --interface "$IFACE" -s "999.999.999.999" 2>&1)
code=$?
set -e
assert_exit_code "Invalid Server IP" 2 "$code" "$output"
assert_contains "Invalid Server IP error message" "Invalid server IP address or unresolvable hostname" "$output"

# 3. Invalid Target Gateway IP
set +e
output=$($DHCPT --interface "$IFACE" -s "10.99.0.1" --target-gateway "not-an-ip" 2>&1)
code=$?
set -e
assert_exit_code "Invalid Target Gateway" 2 "$code" "$output"
assert_contains "Invalid Target Gateway error message" "Invalid IPv4 address for --target-gateway" "$output"

# 4. Interface does not exist
set +e
output=$($DHCPT --interface "dev_does_not_exist_99" 2>&1)
code=$?
set -e
assert_exit_code "Interface does not exist" 2 "$code" "$output"
assert_contains "Non-existent interface error message" "does not exist" "$output"

# 5. Invalid Timeout (negative float)
set +e
output=$($DHCPT --interface "$IFACE" --timeout "-1.0" 2>&1)
code=$?
set -e
assert_exit_code "Negative timeout" 2 "$code" "$output"
assert_contains "Invalid timeout error message" "Timeout must be a positive number" "$output"

# 6. Force flag without --install-skill
set +e
output=$($DHCPT --interface "$IFACE" --force 2>&1)
code=$?
set -e
assert_exit_code "--force without --install-skill" 2 "$code" "$output"
assert_contains "--force validation error message" "only valid when combined with '--install-skill'" "$output"

