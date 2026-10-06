#!/usr/bin/env bash
#
# tests/e2e/testbed.sh - Manage isolated Linux network namespaces for Kea DHCP live testing
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
KEA_CONF_LEGIT="${SCRIPT_DIR}/kea-dhcp4.json"
KEA_CONF_ROGUE="${SCRIPT_DIR}/kea-rogue.json"

RUN_DIR="/tmp/dhcpt-kea-run"
PID_FILE_LEGIT="${RUN_DIR}/dhcpt-kea-legit.pid"
PID_FILE_ROGUE="${RUN_DIR}/dhcpt-kea-rogue.pid"
LOG_FILE_LEGIT="${RUN_DIR}/dhcpt-kea-legit.log"
LOG_FILE_ROGUE="${RUN_DIR}/dhcpt-kea-rogue.log"

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

find_kea() {
    for bin in "/usr/sbin/kea-dhcp4" "/usr/local/sbin/kea-dhcp4" "$(command -v kea-dhcp4 2>/dev/null || true)"; do
        if [ -n "$bin" ] && [ -x "$bin" ]; then
            echo "$bin"
            return 0
        fi
    done
    return 1
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${C_RED}[ERROR]${C_RESET} This command requires root privileges for 'ip netns' and raw sockets." >&2
        echo "        Please run with sudo: sudo $0 [start|stop|status|run|shell]" >&2
        exit 1
    fi
}

check_dependencies() {
    local missing_tools=()

    if ! find_kea >/dev/null 2>&1; then
        missing_tools+=("kea-dhcp4-server (install via: sudo apt install -y kea-dhcp4-server / sudo dnf install -y kea)")
    fi

    if ! command -v jq >/dev/null 2>&1; then
        missing_tools+=("jq (install via: sudo apt install -y jq / sudo dnf install -y jq)")
    fi

    if [ ${#missing_tools[@]} -gt 0 ]; then
        echo -e "${C_RED}[ERROR]${C_RESET} Missing required testbed dependencies:" >&2
        for tool in "${missing_tools[@]}"; do
            echo "  * $tool" >&2
        done
        exit 1
    fi
}

start_testbed() {
    check_root
    check_dependencies

    # If the testbed is already fully running and healthy, inform user and exit cleanly
    if is_testbed_running; then
        echo -e "${C_YELLOW}[INFO]${C_RESET} Testbed is already running and active."
        echo "       Run 'make e2e' to execute test suites, or 'make testbed-stop' to stop."
        exit 0
    fi

    local kea_bin
    kea_bin=$(find_kea)

    echo -e "${C_CYAN}==>${C_RESET} Cleaning up any existing testbed resources..."
    stop_testbed_quiet

    # Prepare runtime directories for per-instance PID and lockfile isolation
    mkdir --parents "${RUN_DIR}/legit" "${RUN_DIR}/rogue"
    chmod 777 "${RUN_DIR}" "${RUN_DIR}/legit" "${RUN_DIR}/rogue"

    # Use aa-exec to run unconfined if AppArmor is available (official Ubuntu standard)
    local aa_prefix=()
    if command -v aa-exec >/dev/null 2>&1; then
        aa_prefix=(aa-exec -p unconfined --)
    fi

    echo -e "${C_CYAN}==>${C_RESET} Creating isolated network namespaces (workstation, vpn-gw, dhcp-server, dhcp-rogue)..."
    ip netns add workstation
    ip netns add vpn-gw
    ip netns add dhcp-server
    ip netns add dhcp-rogue

    echo -e "${C_CYAN}==>${C_RESET} Creating virtual Linux bridge (br-dhcpt)..."
    ip link delete br-dhcpt 2>/dev/null || true
    ip link add br-dhcpt type bridge
    ip link set br-dhcpt up

    echo -e "${C_CYAN}==>${C_RESET} Wiring Layer 2 interfaces into bridge..."
    # Connect workstation (testing client, interface max 15 chars for Linux IFNAMSIZ)
    ip link delete veth-w-br 2>/dev/null || true
    ip link delete veth-client 2>/dev/null || true
    ip link add veth-client type veth peer name veth-w-br
    ip link set veth-w-br master br-dhcpt
    ip link set veth-w-br up
    ip link set veth-client netns workstation
    ip -netns workstation address add 10.99.0.2/24 dev veth-client
    ip -netns workstation link set veth-client up
    ip -netns workstation link set lo up
    ip -netns workstation route add default via 10.99.0.1 dev veth-client
    ip netns exec workstation sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null
    ip netns exec workstation sysctl -w net.ipv4.conf.default.rp_filter=0 >/dev/null

    # Connect VPN gateway / router (vpn-gw)
    ip link delete veth-gw-br 2>/dev/null || true
    ip link delete veth-gw 2>/dev/null || true
    ip link add veth-gw type veth peer name veth-gw-br
    ip link set veth-gw-br master br-dhcpt
    ip link set veth-gw-br up
    ip link set veth-gw netns vpn-gw
    ip -netns vpn-gw address add 10.99.0.10/24 dev veth-gw
    ip -netns vpn-gw link set veth-gw up
    ip -netns vpn-gw link set lo up
    ip netns exec vpn-gw sysctl -w net.ipv4.ip_forward=1 >/dev/null
    ip netns exec vpn-gw sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null
    ip netns exec vpn-gw sysctl -w net.ipv4.conf.default.rp_filter=0 >/dev/null
    # Route traffic for remote corporate datacenter network (10.77.0.0/24) via dhcp-server
    ip -netns vpn-gw route add 10.77.0.0/24 via 10.99.0.1 dev veth-gw
    ip -netns vpn-gw route add default via 10.99.0.1 dev veth-gw

    # Connect legitimate server (dhcp-server)
    ip link delete veth-s-br 2>/dev/null || true
    ip link delete veth-server 2>/dev/null || true
    ip link add veth-server type veth peer name veth-s-br
    ip link set veth-s-br master br-dhcpt
    ip link set veth-s-br up
    ip link set veth-server netns dhcp-server
    ip -netns dhcp-server address add 10.99.0.1/24 dev veth-server
    # Secondary routed IP on server: simulated enterprise corporate service IP
    ip -netns dhcp-server address add 10.77.0.1/32 dev veth-server
    ip -netns dhcp-server link set veth-server up
    ip -netns dhcp-server link set lo up
    ip netns exec dhcp-server sysctl -w net.ipv4.ip_forward=1 >/dev/null
    ip netns exec dhcp-server sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null
    ip netns exec dhcp-server sysctl -w net.ipv4.conf.default.rp_filter=0 >/dev/null
    # Route return traffic for VPN client tunnel subnet back via vpn-gw
    ip -netns dhcp-server route add 10.88.0.0/24 via 10.99.0.10 dev veth-server

    # Connect rogue server (dhcp-rogue)
    ip link delete veth-r-br 2>/dev/null || true
    ip link delete veth-rogue 2>/dev/null || true
    ip link add veth-rogue type veth peer name veth-r-br
    ip link set veth-r-br master br-dhcpt
    ip link set veth-r-br up
    ip link set veth-rogue netns dhcp-rogue
    ip -netns dhcp-rogue address add 10.99.0.254/24 dev veth-rogue
    ip -netns dhcp-rogue link set veth-rogue up
    ip -netns dhcp-rogue link set lo up

    echo -e "${C_CYAN}==>${C_RESET} Creating Layer 3 point-to-point VPN tunnel (tun-client <-> tun-gw via vpn-gw)..."
    # Create IPIP tunnel interfaces (pure Layer 3, ARPHRD_TUNNEL != 1, no MAC)
    ip -netns workstation link add name tun-client type ipip local 10.99.0.2 remote 10.99.0.10
    ip -netns workstation address add 10.88.0.2/30 dev tun-client
    ip -netns workstation link set tun-client up
    # Route dedicated remote server IP strictly across the VPN tunnel
    ip -netns workstation route add 10.77.0.1/32 dev tun-client

    ip -netns vpn-gw link add name tun-gw type ipip local 10.99.0.10 remote 10.99.0.2
    ip -netns vpn-gw address add 10.88.0.1/30 dev tun-gw
    ip -netns vpn-gw link set tun-gw up

    echo -e "${C_CYAN}==>${C_RESET} Starting Legitimate Kea DHCPv4 server (10.99.0.1 / 10.77.0.1)..."
    ip netns exec dhcp-server env \
        KEA_PIDFILE_DIR="${RUN_DIR}/legit" \
        KEA_LOCKFILE_DIR="${RUN_DIR}/legit" \
        "${aa_prefix[@]}" "$kea_bin" -c "$KEA_CONF_LEGIT" > "$LOG_FILE_LEGIT" 2>&1 &
    echo $! > "$PID_FILE_LEGIT"

    echo -e "${C_CYAN}==>${C_RESET} Starting Rogue Kea DHCPv4 server (10.99.0.254)..."
    ip netns exec dhcp-rogue env \
        KEA_PIDFILE_DIR="${RUN_DIR}/rogue" \
        KEA_LOCKFILE_DIR="${RUN_DIR}/rogue" \
        "${aa_prefix[@]}" "$kea_bin" -c "$KEA_CONF_ROGUE" > "$LOG_FILE_ROGUE" 2>&1 &
    echo $! > "$PID_FILE_ROGUE"

    # Wait up to 3 seconds for servers to start listening
    local ready_legit=0
    local ready_rogue=0
    for _ in $(seq 1 30); do
        if ip netns exec dhcp-server ss --udp --listening --numeric 2>/dev/null | grep --quiet ':67 '; then
            ready_legit=1
        fi
        if ip netns exec dhcp-rogue ss --udp --listening --numeric 2>/dev/null | grep --quiet ':67 '; then
            ready_rogue=1
        fi
        if [ "$ready_legit" -eq 1 ] && [ "$ready_rogue" -eq 1 ]; then
            break
        fi
        sleep 0.1
    done

    if [ "$ready_legit" -eq 1 ] && [ "$ready_rogue" -eq 1 ]; then
        local pid_legit pid_rogue
        pid_legit=$(cat "$PID_FILE_LEGIT")
        pid_rogue=$(cat "$PID_FILE_ROGUE")

        echo ""
        echo -e "${C_BOLD}================================================================================${C_RESET}"
        echo -e "${C_BOLD}           dhcpt Live Testbed & Lab Environment (Kea DHCPv4)${C_RESET}"
        echo -e "${C_BOLD}================================================================================${C_RESET}"
        echo -e "${C_GREEN}[OK]${C_RESET} Namespaces:"
        echo "     * workstation    (Client namespace for running dhcpt)"
        echo "     * vpn-gw         (VPN gateway / router forwarding L3 tunnel to DC)"
        echo "     * dhcp-server    (Legitimate DHCP server: PID ${pid_legit})"
        echo "     * dhcp-rogue     (Rogue DHCP server: PID ${pid_rogue})"
        echo ""
        echo -e "${C_GREEN}[OK]${C_RESET} Interfaces for testing inside 'workstation':"
        echo "     * Layer 2 (Ethernet) : veth-client (10.99.0.2/24, has MAC)"
        echo "     * Layer 3 (VPN TUN)  : tun-client  (10.88.0.2/30, pure IP, routed via vpn-gw)"
        echo ""
        echo -e "${C_GREEN}[OK]${C_RESET} Configured DHCP Servers:"
        echo "     * Legitimate Server  : 10.99.0.1 (L2 broadcast & relay) / 10.77.0.1 (via VPN tunnel)"
        echo "     * Rogue Server       : 10.99.0.254 (L2 broadcast)"
        echo ""
        echo -e "${C_GREEN}[OK]${C_RESET} Live Server Logs:"
        echo "     * Legitimate Kea Log : ${LOG_FILE_LEGIT}"
        echo "                            tail --follow ${LOG_FILE_LEGIT}"
        echo "     * Rogue Kea Log      : ${LOG_FILE_ROGUE}"
        echo "                            tail --follow ${LOG_FILE_ROGUE}"
        echo ""
        echo -e "${C_GREEN}[OK]${C_RESET} Interactive Shell Access (Network Namespaces):"
        echo "     * Enter Workstation  : make testbed-workstation (or: sudo $0 shell workstation)"
        echo "     * Enter VPN Gateway  : make testbed-vpn-gw      (or: sudo $0 shell vpn-gw)"
        echo "     * Enter Server       : make testbed-server      (or: sudo $0 shell server)"
        echo "     * Enter Rogue        : make testbed-rogue       (or: sudo $0 shell rogue)"
        echo ""
        echo -e "${C_GREEN}[OK]${C_RESET} Direct Testing from Host:"
        echo "       sudo ip netns exec workstation dhcpt --interface veth-client"
        echo "       sudo ip netns exec workstation dhcpt --interface tun-client --dhcp-servers 10.77.0.1 --target-gateway 10.50.1.1"
        echo ""
        echo -e "${C_GREEN}[OK]${C_RESET} Automated Testing:"
        echo "     Run all automated tests : make e2e"
        echo "     Check testbed status    : make testbed-status"
        echo "     Stop and clean testbed  : make testbed-stop"
        echo -e "${C_BOLD}================================================================================${C_RESET}"
    else
        echo -e "${C_RED}[ERROR]${C_RESET} Kea DHCP servers failed to start within timeout." >&2
        if [ -f "$LOG_FILE_LEGIT" ]; then
            echo "--- Legitimate Kea Log (${LOG_FILE_LEGIT}) ---" >&2
            cat "$LOG_FILE_LEGIT" >&2
        fi
        if [ -f "$LOG_FILE_ROGUE" ]; then
            echo "--- Rogue Kea Log (${LOG_FILE_ROGUE}) ---" >&2
            cat "$LOG_FILE_ROGUE" >&2
        fi
        stop_testbed_quiet
        exit 1
    fi
}

stop_testbed_quiet() {
    for pid_file in "$PID_FILE_LEGIT" "$PID_FILE_ROGUE"; do
        if [ -f "$pid_file" ]; then
            local pid
            pid=$(cat "$pid_file")
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
                wait "$pid" 2>/dev/null || true
            fi
        fi
    done

    # Remove namespaces (this also unplumbs all virtual interfaces inside them)
    ip netns delete workstation 2>/dev/null || true
    ip netns delete vpn-gw 2>/dev/null || true
    ip netns delete dhcp-server 2>/dev/null || true
    ip netns delete dhcp-rogue 2>/dev/null || true

    # Remove legacy namespaces if present
    ip netns delete dhcpt-client 2>/dev/null || true

    # Remove any leftover host-side bridge and veth peer interfaces
    for iface in "veth-w-br" "veth-gw-br" "veth-s-br" "veth-r-br" "veth-c-br" "veth-workstation" "veth-gw" "veth-server" "veth-rogue" "veth-client" "tun-client" "tun-gw" "tun-server" "br-dhcpt"; do
        ip link delete "$iface" 2>/dev/null || true
    done

    # Clean temporary files
    rm --recursive --force "$RUN_DIR"
}

stop_testbed() {
    check_root
    echo -e "${C_CYAN}==>${C_RESET} Stopping Kea DHCPv4 servers and removing network namespaces..."
    stop_testbed_quiet
    echo -e "${C_GREEN}[OK]${C_RESET} Testbed stopped and network namespaces removed (host network 100% clean)."
}

status_testbed() {
    check_root
    local ns_count=0
    local ns_total=4
    local namespaces=("workstation" "vpn-gw" "dhcp-server" "dhcp-rogue")

    echo -e "${C_BOLD}Network Namespaces:${C_RESET}"
    for ns in "${namespaces[@]}"; do
        if ip netns list 2>/dev/null | grep --extended-regexp "(^|[[:space:]])${ns}([[:space:]]|\$)" >/dev/null 2>&1; then
            echo -e "  * Namespace '${ns}': ${C_GREEN}ACTIVE${C_RESET}"
            ns_count=$((ns_count + 1))
        else
            echo -e "  * Namespace '${ns}': ${C_YELLOW}INACTIVE${C_RESET}"
        fi
    done

    echo ""
    echo -e "${C_BOLD}DHCP Server Daemons:${C_RESET}"
    local legit_running=0
    if [ -f "$PID_FILE_LEGIT" ] && kill -0 "$(cat "$PID_FILE_LEGIT")" 2>/dev/null; then
        local pid_legit
        pid_legit=$(cat "$PID_FILE_LEGIT")
        local listen_legit=""
        if ip netns exec dhcp-server ss --udp --listening --numeric 2>/dev/null | grep --quiet ':67 '; then
            listen_legit=" (listening on UDP 67)"
            legit_running=1
        else
            listen_legit=" (NOT listening on UDP 67)"
        fi
        echo -e "  * Legitimate Kea (10.99.0.1 / 10.77.0.1) : ${C_GREEN}RUNNING${C_RESET} (PID ${pid_legit})${listen_legit}"
    else
        echo -e "  * Legitimate Kea (10.99.0.1 / 10.77.0.1) : ${C_RED}STOPPED${C_RESET}"
    fi

    local rogue_running=0
    if [ -f "$PID_FILE_ROGUE" ] && kill -0 "$(cat "$PID_FILE_ROGUE")" 2>/dev/null; then
        local pid_rogue
        pid_rogue=$(cat "$PID_FILE_ROGUE")
        local listen_rogue=""
        if ip netns exec dhcp-rogue ss --udp --listening --numeric 2>/dev/null | grep --quiet ':67 '; then
            listen_rogue=" (listening on UDP 67)"
            rogue_running=1
        else
            listen_rogue=" (NOT listening on UDP 67)"
        fi
        echo -e "  * Rogue Kea (10.99.0.254)               : ${C_GREEN}RUNNING${C_RESET} (PID ${pid_rogue})${listen_rogue}"
    else
        echo -e "  * Rogue Kea (10.99.0.254)               : ${C_RED}STOPPED${C_RESET}"
    fi

    echo ""
    if [ "$ns_count" -eq "$ns_total" ] && [ "$legit_running" -eq 1 ] && [ "$rogue_running" -eq 1 ]; then
        echo -e "${C_GREEN}[STATUS] Testbed is FULLY ACTIVE and ready for testing.${C_RESET}"
        echo ""
        echo -e "${C_GREEN}[OK]${C_RESET} Live Server Logs:"
        echo "  * Legitimate : tail --follow ${LOG_FILE_LEGIT}"
        echo "  * Rogue      : tail --follow ${LOG_FILE_ROGUE}"
        echo ""
        echo -e "${C_GREEN}[OK]${C_RESET} Shell Access (Namespaces):"
        echo "  * Workstation: make testbed-workstation (or: sudo $0 shell workstation)"
        echo "  * VPN Gateway: make testbed-vpn-gw      (or: sudo $0 shell vpn-gw)"
        echo "  * Server     : make testbed-server      (or: sudo $0 shell server)"
        echo "  * Rogue      : make testbed-rogue       (or: sudo $0 shell rogue)"
    elif [ "$ns_count" -eq 0 ] && [ "$legit_running" -eq 0 ] && [ "$rogue_running" -eq 0 ]; then
        echo -e "${C_YELLOW}[STATUS] Testbed is INACTIVE (stopped).${C_RESET}"
        echo "  Start with: make testbed-start"
    else
        echo -e "${C_RED}[STATUS] Testbed is DEGRADED / INCOMPLETE:${C_RESET}"
        [ "$ns_count" -lt "$ns_total" ] && echo "  * Missing namespaces: $((ns_total - ns_count))/${ns_total} missing"
        [ "$legit_running" -eq 0 ] && echo "  * Legitimate Kea server is NOT running or not listening on port 67"
        [ "$rogue_running" -eq 0 ] && echo "  * Rogue Kea server is NOT running or not listening on port 67"
        echo "  Recovery suggestion: make testbed-stop && make testbed-start"
    fi
}

is_testbed_running() {
    ip netns list 2>/dev/null | grep --extended-regexp "(^|[[:space:]])workstation([[:space:]]|\$)" >/dev/null 2>&1 && \
    ip netns list 2>/dev/null | grep --extended-regexp "(^|[[:space:]])vpn-gw([[:space:]]|\$)" >/dev/null 2>&1 && \
    ip netns list 2>/dev/null | grep --extended-regexp "(^|[[:space:]])dhcp-server([[:space:]]|\$)" >/dev/null 2>&1 && \
    ip netns list 2>/dev/null | grep --extended-regexp "(^|[[:space:]])dhcp-rogue([[:space:]]|\$)" >/dev/null 2>&1 && \
    [ -f "$PID_FILE_LEGIT" ] && kill -0 "$(cat "$PID_FILE_LEGIT")" 2>/dev/null && \
    [ -f "$PID_FILE_ROGUE" ] && kill -0 "$(cat "$PID_FILE_ROGUE")" 2>/dev/null && \
    ip netns exec dhcp-server ss --udp --listening --numeric 2>/dev/null | grep --quiet ':67 ' && \
    ip netns exec dhcp-rogue ss --udp --listening --numeric 2>/dev/null | grep --quiet ':67 '
}

run_e2e_suite() {
    check_root

    if ! is_testbed_running; then
        echo -e "${C_RED}[ERROR]${C_RESET} The testbed is not currently running." >&2
        echo "" >&2
        echo "Please start the testbed first before running E2E tests:" >&2
        echo "  make testbed-start" >&2
        echo "" >&2
        exit 1
    fi

    echo -e "${C_BOLD}================================================================================${C_RESET}"
    echo -e "${C_BOLD}Running Live End-to-End Test Suites against Kea DHCPv4${C_RESET}"
    echo -e "${C_BOLD}================================================================================${C_RESET}"

    # Execute the modular live test runner
    PYTHONPATH="${PROJECT_ROOT}/src" bash "${SCRIPT_DIR}/test_live.sh"
    local test_status=$?

    echo ""
    echo "Hint: The testbed remains active for interactive inspection and re-runs."
    echo "      To stop the testbed and clean up resources: make testbed-stop"

    return "$test_status"
}

check_kea_configs() {
    echo -e "${C_CYAN}==>${C_RESET} Validating Kea JSON configuration syntax..."
    local json_files
    json_files=$(find "${SCRIPT_DIR}" -type f -name "*.json")
    for f in $json_files; do
        if command -v jq >/dev/null 2>&1; then
            jq empty "$f"
        else
            python3 -m json.tool "$f" >/dev/null
        fi
        echo -e "  ${C_GREEN}[OK]${C_RESET} Valid JSON: $(basename "$f")"
    done

    local kea_bin
    if kea_bin=$(find_kea); then
        echo -e "${C_CYAN}==>${C_RESET} Validating Kea DHCPv4 schema and parameter declarations..."
        local aa_prefix=()
        if command -v aa-exec >/dev/null 2>&1; then
            aa_prefix=(aa-exec -p unconfined --)
        fi

        for f in "${KEA_CONF_LEGIT}" "${KEA_CONF_ROGUE}"; do
            [ -f "$f" ] || continue
            local tmp_cfg="/tmp/dhcpt-val-$$.json"
            # Strip interfaces during offline schema validation so it does not fail on unplumbed interfaces
            sed -E 's/"interfaces":\s*\[[^]]*\]/"interfaces": []/' "$f" > "$tmp_cfg"
            if ! env KEA_PIDFILE_DIR=/tmp KEA_LOCKFILE_DIR=/tmp "${aa_prefix[@]}" "$kea_bin" -t "$tmp_cfg" >/dev/null 2>&1; then
                echo -e "${C_RED}[ERROR]${C_RESET} Kea schema validation failed for $(basename "$f"):" >&2
                env KEA_PIDFILE_DIR=/tmp KEA_LOCKFILE_DIR=/tmp "${aa_prefix[@]}" "$kea_bin" -t "$tmp_cfg" >&2
                rm -f "$tmp_cfg"
                exit 1
            fi
            rm -f "$tmp_cfg"
            echo -e "  ${C_GREEN}[OK]${C_RESET} Valid Kea Schema: $(basename "$f")"
        done
    else
        echo "  [INFO] 'kea-dhcp4' not found locally; verified JSON syntax with jq (Kea schema check enforced in CI)."
    fi
    echo -e "${C_GREEN}[OK]${C_RESET} All Kea configurations validated successfully!"
}

shell_namespace() {
    check_root
    local target="${1:-workstation}"
    case "$target" in
        workstation|client)
            target="workstation"
            ;;
        vpn-gw|gw|router)
            target="vpn-gw"
            ;;
        dhcp-server|server|legit)
            target="dhcp-server"
            ;;
        dhcp-rogue|rogue)
            target="dhcp-rogue"
            ;;
        *)
            echo -e "${C_RED}[ERROR]${C_RESET} Unknown testbed namespace '${target}'." >&2
            echo "        Available namespaces: workstation, vpn-gw, dhcp-server, dhcp-rogue" >&2
            exit 1
            ;;
    esac

    if ! ip netns list | grep -E "(^|[[:space:]])${target}([[:space:]]|$)" >/dev/null 2>&1; then
        echo -e "${C_RED}[ERROR]${C_RESET} Testbed namespace '${target}' does not exist." >&2
        echo "        The testbed is not currently running. Please start it first:" >&2
        echo "        make testbed-start (or: sudo $0 start)" >&2
        exit 1
    fi

    echo -e "${C_CYAN}==>${C_RESET} Entering testbed namespace '${target}' (exit or Ctrl-D to return)..."
    exec ip netns exec "$target" bash
}

case "$1" in
    start)
        start_testbed
        ;;
    stop)
        stop_testbed
        ;;
    status)
        status_testbed
        ;;
    run)
        run_e2e_suite
        ;;
    shell|enter)
        shift
        shell_namespace "$@"
        ;;
    check-config|lint-config)
        check_kea_configs
        ;;
    *)
        echo "Usage: $0 {start|stop|status|run|shell [workstation|vpn-gw|server|rogue]|check-config}" >&2
        exit 1
        ;;
esac
