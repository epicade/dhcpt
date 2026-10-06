#!/usr/bin/env bash
# tests/e2e/helpers/assert.sh - Lightweight, readable assertion library for E2E suites
#
# Sourcing:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   # shellcheck source=tests/e2e/helpers/assert.sh
#   source "${SCRIPT_DIR}/../../helpers/assert.sh"
#
# Functions Overview:
#   assert_equals    <label> <expected> <actual>
#   assert_contains  <label> <needle>   <haystack>
#   assert_exit_code <label> <expected> <actual>   [<output>]
#   assert_not_empty <label> <actual>

# ------------------------------------------------------------------------------
# assert_equals <label> <expected> <actual>
#
# Asserts that the actual string matches the expected string exactly.
#
# Arguments:
#   $1 (label):    Description of the test or field being checked (e.g. "Interface")
#   $2 (expected): Expected target value / Soll-Wert (e.g. "eth0")
#   $3 (actual):   Actual value received / Ist-Wert (e.g. "$iface")
#
# Example:
#   assert_equals "Option 26 MTU" "1400" "$mtu_val"
# ------------------------------------------------------------------------------
assert_equals() {
    local label="$1"
    local expected="$2"
    local actual="$3"

    if [ "$actual" = "$expected" ]; then
        return 0
    fi

    echo "  [FAIL] $label assertion failed:" >&2
    echo "         Expected : $expected" >&2
    echo "         Received : ${actual:-<empty>}" >&2
    exit 1
}

# ------------------------------------------------------------------------------
# assert_contains <label> <needle> <haystack>
#
# Asserts that a text output contains a specific substring.
#
# Arguments:
#   $1 (label):    Description of the check (e.g. "Send arrow")
#   $2 (needle):   Substring expected to be present (e.g. "> DHCPDISCOVER")
#   $3 (haystack): Full output string to search within (e.g. "$output")
#
# Example:
#   assert_contains "Curl send arrow" "> DHCPDISCOVER" "$output"
# ------------------------------------------------------------------------------
assert_contains() {
    local label="$1"
    local needle="$2"
    local haystack="$3"

    if echo "$haystack" | grep --quiet --fixed-strings "$needle"; then
        return 0
    fi

    echo "  [FAIL] $label assertion failed:" >&2
    echo "         Expected to contain : $needle" >&2
    echo "         Received output snippet :" >&2
    echo "$haystack" | head --lines=3 | sed 's/^/           /' >&2
    exit 1
}

# ------------------------------------------------------------------------------
# assert_exit_code <label> <expected_code> <actual_code> [<output>]
#
# Asserts that a command finished with the expected integer exit code.
#
# Arguments:
#   $1 (label):         Description of the command (e.g. "Invalid MAC")
#   $2 (expected_code): Expected integer exit code / Soll (e.g. 0, 1, 2, 3)
#   $3 (actual_code):   Actual exit code received from $? / Ist (e.g. "$exit_code")
#   $4 (output):        (Optional) Command output string for failure snippet display
#
# Example:
#   assert_exit_code "Usage error on bad MAC" 2 "$exit_code" "$output"
# ------------------------------------------------------------------------------
assert_exit_code() {
    local label="$1"
    local expected_code="$2"
    local actual_code="$3"
    local output="${4:-}"

    if [ "$actual_code" -eq "$expected_code" ]; then
        return 0
    fi

    echo "  [FAIL] $label exit code assertion failed:" >&2
    echo "         Expected exit code : $expected_code" >&2
    echo "         Received exit code : $actual_code" >&2
    if [ -n "$output" ]; then
        echo "         Output snippet     : $(echo "$output" | head --lines=1)" >&2
    fi
    exit 1
}

# ------------------------------------------------------------------------------
# assert_not_empty <label> <actual>
#
# Asserts that a variable or string is non-empty.
#
# Arguments:
#   $1 (label):  Description of the checked variable (e.g. "Transaction ID")
#   $2 (actual): Value that must not be empty or null (e.g. "$xid")
#
# Example:
#   assert_not_empty "Received transaction ID" "$xid"
# ------------------------------------------------------------------------------
assert_not_empty() {
    local label="$1"
    local actual="$2"

    if [ -n "$actual" ]; then
        return 0
    fi

    echo "  [FAIL] $label assertion failed:" >&2
    echo "         Expected : non-empty value" >&2
    echo "         Received : <empty>" >&2
    exit 1
}
