#!/usr/bin/env bash
#
# tests/e2e/test_live.sh - Modular E2E test runner executing all test cases in suites/
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SUITES_DIR="${SCRIPT_DIR}/suites"

# Terminal color palette (only active when connected to a terminal and NO_COLOR is unset)
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_GREEN="\033[1;32m"
    C_RED="\033[1;31m"
    C_YELLOW="\033[1;33m"
    C_CYAN="\033[1;36m"
    C_BOLD="\033[1m"
    C_RESET="\033[0m"
else
    C_GREEN=""
    C_RED=""
    C_YELLOW=""
    C_CYAN=""
    C_BOLD=""
    C_RESET=""
fi

PASSED_COUNT=0
FAILED_COUNT=0
FAILED_TESTS=()

export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"
export DHCPT_CMD="ip netns exec workstation env PYTHONPATH=${PROJECT_ROOT}/src python3 -m dhcpt"

# Client Namespace Interfaces & Endpoints
export CLIENT_WORKSTATION_L2_IFACE="veth-client"
export CLIENT_WORKSTATION_L3_IFACE="tun-client"
export CLIENT_VPNGW_L3_IP="10.88.0.1"

# DHCP Servers
export DHCP_SERVER_LEGIT_IP="10.99.0.1"
export DHCP_SERVER_ROGUE_IP="10.99.0.254"
export DHCP_SERVER_TIMEOUT_IP="10.99.0.99"
export DHCP_SERVER_L3_ROUTED_IP="10.77.0.1"

# DHCP Parameters & Pool Gateways
export DHCP_TARGET_GATEWAY="10.50.1.1"
export DHCP_RESERVED_CLIENT_MAC="00:11:22:33:44:55"
export DHCP_RESERVED_OFFERED_IP="10.99.0.42"

# Server Logs
export DHCP_SERVER_LOG_LEGIT="${DHCP_SERVER_LOG_LEGIT:-/tmp/dhcpt-kea-run/dhcpt-kea-legit.log}"
export DHCP_SERVER_LOG_ROGUE="${DHCP_SERVER_LOG_ROGUE:-/tmp/dhcpt-kea-run/dhcpt-kea-rogue.log}"

echo ""
echo -e "${C_BOLD}======================================================================${C_RESET}"
echo -e "${C_BOLD}Discovering and executing live test suites in ${SUITES_DIR}...${C_RESET}"
echo -e "${C_BOLD}======================================================================${C_RESET}"

# Find all test scripts in suites/ sorted by path name
while IFS= read -r test_file; do
    [ -f "$test_file" ] || continue

    rel_name="${test_file#"$SUITES_DIR"/}"
    echo ""
    echo -e "--- Test Suite: ${C_CYAN}${rel_name}${C_RESET} ---"

    test_output=""
    if test_output=$(bash "$test_file" 2>&1); then
        PASSED_COUNT=$((PASSED_COUNT + 1))
        echo -e "  ${C_GREEN}[PASS]${C_RESET} ${rel_name}"
    else
        FAILED_COUNT=$((FAILED_COUNT + 1))
        FAILED_TESTS+=("${rel_name}")
        echo -e "  ${C_RED}[FAIL]${C_RESET} ${rel_name}" >&2
        echo -e "${C_YELLOW}--- Failure Output for ${rel_name} ---${C_RESET}" >&2
        while IFS= read -r line; do
            echo "    $line" >&2
        done <<< "$test_output"
        echo -e "${C_YELLOW}--------------------------------------${C_RESET}" >&2
    fi
done < <(find "$SUITES_DIR" -type f -name "*.sh" | sort)

echo ""
echo -e "${C_BOLD}======================================================================${C_RESET}"
if [ "${FAILED_COUNT}" -gt 0 ]; then
    echo -e "${C_RED}[FAIL]${C_RESET} Live E2E Test Summary: ${PASSED_COUNT} Passed, ${FAILED_COUNT} Failed"
    echo -e "${C_BOLD}======================================================================${C_RESET}"
    echo "Failed tests:" >&2
    for t in "${FAILED_TESTS[@]}"; do
        echo -e "  - ${C_RED}${t}${C_RESET}" >&2
    done
    exit 1
fi

echo -e "${C_GREEN}[OK]${C_RESET} Live E2E Test Summary: ${PASSED_COUNT} Passed, ${FAILED_COUNT} Failed"
echo -e "${C_BOLD}======================================================================${C_RESET}"
echo -e "${C_GREEN}[OK]${C_RESET} All ${PASSED_COUNT} live E2E network tests passed successfully!"
exit 0
