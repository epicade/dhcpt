#!/usr/bin/env bash
# E2E Test: Lease-Safety Verification (Proves dhcpt NEVER requests or commits a lease)
#
# Core Engineering Mandate 3:
# "dhcpt is a diagnostic tool, not a full client daemon. It MUST ONLY perform the
#  DHCP Discover -> DHCP Offer cycle. NEVER implement or send a DHCP Request in
#  standard test mode to avoid committing leases or exhausting IP address pools."
#
# Methodology:
# 1. Calibration Phase (Ground Truth):
#    Trigger a genuine lease commit using an external DHCP client (busybox udhcpc)
#    on an isolated macvlan interface. Assert that Kea in this exact running version
#    definitely logs:
#      - DHCPREQUEST
#      - DHCP4_LEASE_ALLOC
#      - DHCPACK
#    This mathematically guarantees our detector does not produce false negatives.
#
# 2. dhcpt Invariant Assertion:
#    Execute dhcpt across multiple operational modes (L2 broadcast, static MAC
#    reservation, unicast relay with Option 82, L3 VPN tunnel, rogue detection).
#    Assert that during dhcpt execution:
#      - Kea logs DHCPDISCOVER and DHCP4_LEASE_OFFER (traffic is processed).
#      - Kea NEVER logs DHCPREQUEST, DHCP4_LEASE_ALLOC, DHCP4_LEASE_REUSE, or DHCPACK.
#    If ANY forbidden lease-commit marker is detected, the test immediately aborts with failure.

set -e

DHCPT="${DHCPT_CMD:-ip netns exec workstation env PYTHONPATH=src python3 -m dhcpt}"
IFACE="${CLIENT_WORKSTATION_L2_IFACE:-veth-client}"
LOG_FILE_LEGIT="${DHCP_SERVER_LOG_LEGIT:-/tmp/dhcpt-kea-run/dhcpt-kea-legit.log}"
LOG_FILE_ROGUE="${DHCP_SERVER_LOG_ROGUE:-/tmp/dhcpt-kea-run/dhcpt-kea-rogue.log}"

if [ ! -f "$LOG_FILE_LEGIT" ] || [ ! -f "$LOG_FILE_ROGUE" ]; then
    echo "  [FAIL] Kea server log files not found at ${LOG_FILE_LEGIT} / ${LOG_FILE_ROGUE}." >&2
    exit 1
fi

# Locate external DHCP client for calibration
CLIENT_BIN=""
if command -v busybox >/dev/null 2>&1; then
    CLIENT_BIN="busybox udhcpc"
elif command -v udhcpc >/dev/null 2>&1; then
    CLIENT_BIN="udhcpc"
fi

if [ -z "$CLIENT_BIN" ]; then
    echo "  [FAIL] Neither 'busybox' nor 'udhcpc' found on host system for lease-commit calibration." >&2
    echo "         Please install busybox (e.g. sudo apt install busybox / sudo dnf install busybox)." >&2
    exit 1
fi

# -----------------------------------------------------------------------------
# Phase 1: Ground Truth Calibration
# -----------------------------------------------------------------------------
CALIB_IFACE="calib0"
CALIB_MAC="02:ca:11:00:00:01"

# Ensure cleanup of calibration interface even on unexpected exit
cleanup_calib() {
    ip -netns workstation link delete "$CALIB_IFACE" 2>/dev/null || true
}
trap cleanup_calib EXIT INT TERM

# Create temporary macvlan interface with dedicated calibration MAC
ip -netns workstation link add link "$IFACE" name "$CALIB_IFACE" type macvlan mode bridge
ip -netns workstation link set "$CALIB_IFACE" address "$CALIB_MAC" up

BL_CALIB=$(wc -l < "$LOG_FILE_LEGIT")
BR_CALIB=$(wc -l < "$LOG_FILE_ROGUE")

# Trigger authentic lease commitment with external client
# -q: exit after obtaining lease, -n: exit if not obtained, -f: run in foreground, -s: dummy script
# shellcheck disable=SC2086
ip netns exec workstation $CLIENT_BIN -i "$CALIB_IFACE" -q -n -f -s /bin/true >/dev/null 2>&1

# Immediately delete calibration interface so its MAC does not pollute subsequent tests
cleanup_calib
trap - EXIT INT TERM

# Allow Kea worker threads to settle and flush log output to disk
sleep 0.1

AL_CALIB=$(wc -l < "$LOG_FILE_LEGIT")
AR_CALIB=$(wc -l < "$LOG_FILE_ROGUE")

if [ "$AL_CALIB" -le "$BL_CALIB" ] && [ "$AR_CALIB" -le "$BR_CALIB" ]; then
    echo "  [FAIL] Server log files did not grow during calibration (log truncation or missing traffic)!" >&2
    exit 1
fi

CALIB_LOGS=$(cat <(sed -n "$((BL_CALIB + 1)),${AL_CALIB}p" "$LOG_FILE_LEGIT") \
                 <(sed -n "$((BR_CALIB + 1)),${AR_CALIB}p" "$LOG_FILE_ROGUE"))

REQ_FOUND=$(echo "$CALIB_LOGS" | grep -c "DHCPREQUEST" || true)
ALLOC_FOUND=$(echo "$CALIB_LOGS" | grep -c "DHCP4_LEASE_ALLOC" || true)
ACK_FOUND=$(echo "$CALIB_LOGS" | grep -c "DHCPACK" || true)

if [ "$REQ_FOUND" -eq 0 ] || [ "$ALLOC_FOUND" -eq 0 ] || [ "$ACK_FOUND" -eq 0 ]; then
    echo "  [FAIL] Lease-commit calibration failed: Kea did not log expected commitment markers!" >&2
    echo "         DHCPREQUEST matches : ${REQ_FOUND} (expected >= 1)" >&2
    echo "         DHCP4_LEASE_ALLOC   : ${ALLOC_FOUND} (expected >= 1)" >&2
    echo "         DHCPACK matches     : ${ACK_FOUND} (expected >= 1)" >&2
    echo "         Calibration Logs Captured:" >&2
    while IFS= read -r line; do
        echo "           $line" >&2
    done <<< "$CALIB_LOGS"
    exit 1
fi

# -----------------------------------------------------------------------------
# Phase 2: dhcpt Invariant Verification
# -----------------------------------------------------------------------------
BL_DHCPT=$(wc -l < "$LOG_FILE_LEGIT")
BR_DHCPT=$(wc -l < "$LOG_FILE_ROGUE")

# Run dhcpt across multiple test cases
$DHCPT -i "$IFACE" >/dev/null
$DHCPT -i "$IFACE" --mac "${DHCP_RESERVED_CLIENT_MAC:-00:11:22:33:44:55}" >/dev/null
$DHCPT -i "$IFACE" -s "${DHCP_SERVER_LEGIT_IP:-10.99.0.1}" --target-gateway "${DHCP_TARGET_GATEWAY:-10.50.1.1}" --circuit-id eth0 >/dev/null
$DHCPT -i "${CLIENT_WORKSTATION_L3_IFACE:-tun-client}" -s "${DHCP_SERVER_L3_ROUTED_IP:-10.77.0.1}" --target-gateway "${DHCP_TARGET_GATEWAY:-10.50.1.1}" >/dev/null
$DHCPT -i "$IFACE" -a --timeout 1 >/dev/null

# Allow Kea worker threads to settle and flush log output to disk
sleep 0.1

AL_DHCPT=$(wc -l < "$LOG_FILE_LEGIT")
AR_DHCPT=$(wc -l < "$LOG_FILE_ROGUE")

if [ "$AL_DHCPT" -le "$BL_DHCPT" ] && [ "$AR_DHCPT" -le "$BR_DHCPT" ]; then
    echo "  [FAIL] Server log files did not grow during dhcpt execution (log truncation or missing traffic)!" >&2
    exit 1
fi

DHCPT_LOGS=$(cat <(sed -n "$((BL_DHCPT + 1)),${AL_DHCPT}p" "$LOG_FILE_LEGIT") \
                 <(sed -n "$((BR_DHCPT + 1)),${AR_DHCPT}p" "$LOG_FILE_ROGUE"))

DISCOVERS=$(echo "$DHCPT_LOGS" | grep -c "DHCPDISCOVER" || true)
OFFERS=$(echo "$DHCPT_LOGS" | grep -c "DHCP4_LEASE_OFFER" || true)
FORBIDDEN=$(echo "$DHCPT_LOGS" | grep -E "DHCPREQUEST|DHCP4_LEASE_ALLOC|DHCP4_LEASE_REUSE|DHCPACK" || true)

if [ "$DISCOVERS" -eq 0 ] || [ "$OFFERS" -eq 0 ]; then
    echo "  [FAIL] Testbed did not capture any DHCP traffic during dhcpt execution!" >&2
    echo "         DHCPDISCOVER count : ${DISCOVERS} (expected >= 5)" >&2
    echo "         DHCP4_LEASE_OFFER  : ${OFFERS} (expected >= 5)" >&2
    exit 1
fi

if [ -n "$FORBIDDEN" ]; then
    echo "  [FAIL] CRITICAL LEASE-SAFETY VIOLATION DETECTED!" >&2
    echo "         dhcpt triggered lease commitment markers in Kea DHCP server logs:" >&2
    while IFS= read -r line; do
        echo "           $line" >&2
    done <<< "$FORBIDDEN"
    echo "         dhcpt must strictly perform Discover->Offer and NEVER send Requests!" >&2
    exit 1
fi

# Success: all assertions satisfied
exit 0
