# End-to-End Live Testing Infrastructure

This document describes how the `dhcpt` live network testbed works.
It covers the architecture, virtual network topology, and how to run tests.

---

## 1. Why Live Testing?

Unit tests alone cannot verify raw packet tools.
Mocking network sockets hides kernel routing rules, firewall behavior, and real DHCP server logic.

To guarantee that `dhcpt` works in production, we run live tests against real **ISC Kea DHCP servers** (`kea-dhcp4`).

### Key Benefits

* **Complete Isolation:** All test interfaces live inside Linux network namespaces (`ip netns`).
  Your physical network card, IP address, and default gateway are never touched.
* **Fast and Lightweight:** Uses native Linux namespaces instead of slow virtual machines.
  The testbed starts and stops in milliseconds.
* **Two Test Layers:**
  * **Unit Tests (`pytest`):** Run in ~2 seconds without root privileges.
    They check CLI arguments, option encoding, and data models.
  * **Live E2E Tests (`make e2e`):** Run against active DHCP servers.
    They verify real packet exchange over Layer 2 and Layer 3.
* **Realistic Topology:** Simulates enterprise networks with VPN tunnels, routers, and redundant DHCP servers.

---

## 2. Network Topology

The testbed creates four isolated network namespaces.
They connect through a Linux bridge (`br-dhcpt`) and a point-to-point VPN tunnel (`tun-client` to `tun-gw`):

```text
                        ┌────────────────────────────────────────────────────────┐
                        │                 Linux Bridge br-dhcpt                  │
                        │                 (0% Host Network Impact)               │
                        └──────▲──────────────▲────────────────▲──────────▲──────┘
                               │              │                │          │
            ┌──────────────────┘              │                │          └──────────────────┐
            │                                 │                │                             │
            ▼                                 ▼                ▼                             ▼
┌────────────────────────┐        ┌──────────────────────┐  ┌────────────────────────┐  ┌────────────────────────┐
│ Namespace: workstation │        │ Namespace: vpn-gw    │  │ Namespace: dhcp-server │  │ Namespace: dhcp-rogue  │
│                        │        │                      │  │                        │  │                        │
│ * veth-client (L2 Eth) │        │ * veth-gw (L2 Eth)   │  │ * veth-server (L2 Eth) │  │ * veth-rogue (L2 Eth)  │
│   IP: 10.99.0.2/24     │        │   IP: 10.99.0.10/24  │  │   IP: 10.99.0.1/24     │  │   IP: 10.99.0.254/24   │
│   MAC: Hardware-backed │        │   MAC: Hardware      │  │   IP: 10.77.0.1/32     │  │   MAC: Hardware-backed │
│                        │        │                      │  │   MAC: Hardware-backed │  │                        │
│ * tun-client (L3 VPN)  │        │ * tun-gw (L3 VPN)    │  │                        │  │ * Rogue Kea Server:    │
│   IP: 10.88.0.2/30     │        │   IP: 10.88.0.1/30   │  │ * Legitimate Server:   │  │   kea-dhcp4            │
│   MAC: None (Raw IP)   │        │   MAC: None (Raw IP) │  │   kea-dhcp4            │  │   Subnet: 10.99.0.0/24 │
│                        │        │                      │  │   Subnet: 10.99.0.0/24 │  │   (Pool: .220 - .240)  │
│ (dhcpt CLI Execution)  │        │ * IP Forwarding: ON  │  │   Subnet: 10.50.1.0/24 │  │   Gateway: 10.99.0.254 │
└───────────▲────────────┘        │   (net.ipv4.ip_      │  │   Subnet: 10.88.0.0/24 │  └────────────────────────┘
            │                     │    forward = 1)      │  │   Subnet: 10.77.0.0/24 │
            │                     └──────────▲───────────┘  │   Subnet: 10.60.1.0/24 │
            │     Point-to-Point VPN Tunnel  │              └────────────────────────┘
            └────────────────►───────────────┘
```

### Namespaces and Interfaces

| Namespace | Interface | Type | IP Address | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **`workstation`** | `veth-client` | Layer 2 Ethernet | `10.99.0.2/24` | Client interface where `dhcpt` runs |
| **`workstation`** | `tun-client` | Layer 3 VPN Tunnel | `10.88.0.2/30` | Tests raw IP socket mode without MAC address |
| **`vpn-gw`** | `veth-gw` | Layer 2 Ethernet | `10.99.0.10/24` | Router interface connected to bridge with IP forwarding enabled |
| **`vpn-gw`** | `tun-gw` | Layer 3 VPN Tunnel | `10.88.0.1/30` | Remote tunnel endpoint on the gateway router |
| **`dhcp-server`** | `veth-server` | Layer 2 Ethernet | `10.99.0.1/24`, `10.77.0.1/32` | Legitimate DHCP server running ISC Kea |
| **`dhcp-rogue`** | `veth-rogue` | Layer 2 Ethernet | `10.99.0.254/24` | Rogue DHCP server running ISC Kea |

### Point-to-Point Tunnel & Routing Architecture

The testbed simulates a real enterprise VPN client communicating across a router to a remote datacenter DHCP server:

1. **Virtual Point-to-Point Tunnel (`tun-client` $\leftrightarrow$ `tun-gw`):**
   * Interface `tun-client` in `workstation` has IP `10.88.0.2/30`.
   * Interface `tun-gw` in `vpn-gw` has IP `10.88.0.1/30`.
   * These interfaces have no MAC addresses (`ARPHRD_TUNNEL`). Traffic travels as raw IP packets.

2. **IP Forwarding on Gateway Router (`vpn-gw`):**
   * The `vpn-gw` router acts as an intermediary with Linux kernel forwarding enabled (`sysctl net.ipv4.ip_forward = 1`).
   * It routes packets between the tunnel link (`10.88.0.0/30`) and the datacenter bridge (`10.99.0.0/24`).

3. **Routing Tables & Packet Flow:**
   * **In `workstation`:** Traffic for the remote enterprise server IP (`10.77.0.1/32`) routes into the tunnel:
     ```bash
     ip route add 10.77.0.1/32 via 10.88.0.1 dev tun-client
     ```
   * **In `dhcp-server`:** Return traffic for the client tunnel subnet (`10.88.0.0/24`) routes back via the gateway:
     ```bash
     ip route add 10.88.0.0/24 via 10.99.0.10 dev veth-server
     ```

When running `dhcpt -i tun-client -s 10.77.0.1`:
1. `dhcpt` sends raw IP packets out of `tun-client` without Ethernet headers.
2. The packet travels through the tunnel to `tun-gw` on `vpn-gw`.
3. The router forwards the IP packet out of `veth-gw` onto the bridge `br-dhcpt`.
4. The legitimate Kea server receives the request on `veth-server` and sends its reply back through `vpn-gw` into the tunnel.

---

## 3. Server Pools and Policies

The testbed provisions two ISC Kea instances with dedicated policies to validate all core features of `dhcpt`:

### Legitimate Server (`10.99.0.1`)

* **Subnet 1: Local Dynamic Pool (`10.99.0.0/24`)**
  * Dynamic Range: `10.99.0.100 - 10.99.0.200`
  * Gateway (Option 3): `10.99.0.1`
  * DNS (Option 6): `10.99.0.1`
  * Classless Static Routes (Option 121): `10.0.0.0/8 via 10.99.0.1`, `192.168.50.0/24 via 10.99.0.254`
  * Domain Search (Option 119): `example.com, corp.internal`
* **Static MAC Reservation (`--mac`)**
  * MAC Address: `00:11:22:33:44:55`
  * Reserved IP: `10.99.0.42`
  * *Tests client MAC spoofing and static reservation verification.*
* **Custom Enterprise Options (`-o`)**
  * Interface MTU (Option 26): `1400`
  * Bootfile Name (Option 67): `pxelinux.0`
* **Subnet 2: Remote Relay Pool (`10.50.1.0/24`)**
  * Dynamic Range: `10.50.1.100 - 10.50.1.200`
  * Gateway (Option 3): `10.50.1.1`
  * *Tests RFC 3527 Link Selection (`--target-gateway 10.50.1.1`).*
* **Subnet 3: VPN Tunnel Pool (`10.88.0.0/24`)**
  * Dynamic Range: `10.88.0.100 - 10.88.0.200`
  * Gateway (Option 3): `10.88.0.1`
* **Subnet 4: Routed Enterprise Service Pool (`10.77.0.0/24`)**
  * Dynamic Range: `10.77.0.100 - 10.77.0.200`
  * Gateway (Option 3): `10.77.0.1`
* **Subnet 5: Switch-Protected Pool (`10.60.1.0/24`)**
  * Dynamic Range: `10.60.1.100 - 10.60.1.200`
  * Gateway (Option 3): `10.60.1.1`
  * Requires Option 82 Remote ID (`00:11:22:33:44:aa`).
  * *Tests switch authentication policies (`client-classes`).*

### Rogue Server (`10.99.0.254`)

* **Subnet: Rogue Dynamic Pool (`10.99.0.0/24`)**
  * Dynamic Range: `10.99.0.220 - 10.99.0.240`
  * Gateway (Option 3): `10.99.0.254`
  * *Rogue DHCP server used to test multi-server detection (`dhcpt --all`).*

---

## 4. Test Suite Organization

Tests live in category folders under `tests/e2e/suites/`.
The runner (`test_live.sh`) executes every `.sh` script automatically:

* **`10-broadcast/`:** Tests broadcast requests, MAC reservations, unicast offers, custom options, and classless routes.
* **`20-relay/`:** Tests remote servers (`-s`), target gateways, Circuit ID, Remote ID, L3 tunnels, and timeouts.
* **`30-features/`:** Tests JSON output, curl-style logging (`-v`, `-vv`), human text tables, exit code 2 on syntax errors, and Tab-Tab completion.
* **`40-rogue/`:** Tests capturing multiple answering servers simultaneously with `--all`.
* **`50-safety/`:** Empirically proves that `dhcpt` never commits an IP lease.
  It first verifies that a real client (`busybox udhcpc`) creates lease logs in Kea.
  Then it proves that `dhcpt` never produces these log lines.

### Writing Readable Tests with `assert.sh`

All test scripts source the reusable assertion helper library `tests/e2e/helpers/assert.sh`.
This keeps tests short, readable, and produces clear, actionable error messages.

#### How to Source `assert.sh`

To ensure tests run reliably whether executed directly or via the test runner, resolve paths dynamically relative to `BASH_SOURCE[0]`. Add the `# shellcheck source=...` directive so ShellCheck can follow the file:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"
```

#### Function Reference & Expected Parameters

| Function | Signature | Expected Parameters | Behavior on Failure |
| :--- | :--- | :--- | :--- |
| **`assert_equals`** | `assert_equals <label> <expected> <actual>` | 1. `<label>`: Test description string<br>2. `<expected>`: Target expected value<br>3. `<actual>`: Actual value received | Prints `Expected` vs. `Received` comparison and exits with `1`. |
| **`assert_contains`** | `assert_contains <label> <needle> <haystack>` | 1. `<label>`: Test description string<br>2. `<needle>`: Substring that must be present<br>3. `<haystack>`: Output string to search | Prints expected substring and output snippet, then exits with `1`. |
| **`assert_exit_code`** | `assert_exit_code <label> <expected> <actual> [<output>]` | 1. `<label>`: Command description<br>2. `<expected>`: Expected integer code (`0`, `1`, `2`, `3`)<br>3. `<actual>`: Actual `$?` exit code<br>4. `[<output>]`: Optional output for snippet display | Prints expected vs. actual exit code plus output snippet, then exits with `1`. |
| **`assert_not_empty`** | `assert_not_empty <label> <actual>` | 1. `<label>`: Test description string<br>2. `<actual>`: Variable that must not be empty | Prints that a non-empty value was expected and exits with `1`. |

#### Usage Examples

```bash
# 1. Check exact string equality:
assert_equals "Option 26 MTU" "1400" "$mtu_val"

# 2. Check if text output contains a substring:
assert_contains "Send arrow" "> DHCPDISCOVER" "$output"

# 3. Check program exit code:
assert_exit_code "Invalid MAC exit code" 2 "$exit_code" "$output"

# 4. Check that a variable is not empty:
assert_not_empty "Received transaction ID" "$xid"
```

If an assertion fails, it prints a clean comparison:
```text
  [FAIL] Option 26 MTU assertion failed:
         Expected : 1400
         Received : 1500
```

### Environment Variables & Naming Conventions in Test Suites

The test runner (`tests/e2e/test_live.sh`) exports standardized environment variables into every test script following clear naming conventions:
* **`DHCP_SERVER_*`**: IP addresses of DHCP server daemons (`DHCP_SERVER_LEGIT_IP`, `DHCP_SERVER_ROGUE_IP`, `DHCP_SERVER_TIMEOUT_IP`, `DHCP_SERVER_L3_ROUTED_IP`).
* **`DHCP_SERVER_LOG_*`**: Paths to server daemon log files (`DHCP_SERVER_LOG_LEGIT`, `DHCP_SERVER_LOG_ROGUE`).
* **`DHCP_*`**: DHCP protocol parameters, pools, and reservations (`DHCP_TARGET_GATEWAY`, `DHCP_RESERVED_CLIENT_MAC`, `DHCP_RESERVED_OFFERED_IP`).
* **`CLIENT_WORKSTATION_*`**: Network interfaces in the client namespace (`CLIENT_WORKSTATION_L2_IFACE`, `CLIENT_WORKSTATION_L3_IFACE`).
* **`CLIENT_VPNGW_*`**: Tunnel endpoint on the router (`CLIENT_VPNGW_L3_IP`).

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| **`$DHCPT_CMD`** | `ip netns exec workstation env PYTHONPATH=... python3 -m dhcpt` | Command wrapper executing `dhcpt` inside the `workstation` namespace |
| **`$CLIENT_WORKSTATION_L2_IFACE`** | `veth-client` | Layer 2 Ethernet broadcast client interface in `workstation` |
| **`$CLIENT_WORKSTATION_L3_IFACE`** | `tun-client` | Layer 3 VPN tunnel client interface without MAC address in `workstation` |
| **`$CLIENT_VPNGW_L3_IP`** | `10.88.0.1` | Remote tunnel endpoint IP on router `vpn-gw` (`tun-gw`) |
| **`$DHCP_SERVER_LEGIT_IP`** | `10.99.0.1` | Primary legitimate ISC Kea DHCP server IP on the bridge |
| **`$DHCP_SERVER_ROGUE_IP`** | `10.99.0.254` | Rogue ISC Kea DHCP server IP on the bridge |
| **`$DHCP_SERVER_TIMEOUT_IP`** | `10.99.0.99` | Non-existent server IP used to verify timeout handling and partial failure |
| **`$DHCP_SERVER_L3_ROUTED_IP`** | `10.77.0.1` | Secondary routed server IP reachable exclusively across the L3 VPN tunnel |
| **`$DHCP_TARGET_GATEWAY`** | `10.50.1.1` | Target gateway IP for remote relay tests (RFC 3527 Link Selection) |
| **`$DHCP_RESERVED_CLIENT_MAC`** | `00:11:22:33:44:55` | Test-client MAC address configured for static IP reservation |
| **`$DHCP_RESERVED_OFFERED_IP`** | `10.99.0.42` | IP address reserved in Kea for `$DHCP_RESERVED_CLIENT_MAC` |
| **`$DHCP_SERVER_LOG_LEGIT`** | `/tmp/dhcpt-kea-run/dhcpt-kea-legit.log` | Path to legitimate Kea DHCPv4 server log file |
| **`$DHCP_SERVER_LOG_ROGUE`** | `/tmp/dhcpt-kea-run/dhcpt-kea-rogue.log` | Path to rogue Kea DHCPv4 server log file |

#### Example Usage in a Test Script:

```bash
# Query the legitimate server over Layer 2 broadcast interface:
output=$($DHCPT_CMD --interface "$CLIENT_WORKSTATION_L2_IFACE" -s "$DHCP_SERVER_LEGIT_IP" --json)

# Query multiple pools over Layer 3 VPN tunnel:
output_vpn=$($DHCPT_CMD --interface "$CLIENT_WORKSTATION_L3_IFACE" -s "$DHCP_SERVER_L3_ROUTED_IP" --target-gateway "$CLIENT_VPNGW_L3_IP" --json)
output_remote=$($DHCPT_CMD --interface "$CLIENT_WORKSTATION_L3_IFACE" -s "$DHCP_SERVER_L3_ROUTED_IP" --target-gateway "$DHCP_TARGET_GATEWAY" --json)

# Inspect the legitimate Kea log file for events:
grep "DHCP4_PACKET_RECEIVED" "$DHCP_SERVER_LOG_LEGIT"
```

---

## 5. Daily Workflows

### Setup Development Environment

Install all needed system tools (Kea, Jq, ShellCheck, Pandoc, Zsh), Python dev dependencies, and link `src/dhcpt/cli.py` to `/usr/local/bin/dhcpt` for instant live-testing:

```bash
make install-dev
```

With `make install-dev`, any code edit you save in `src/dhcpt/cli.py` is immediately executed when running `dhcpt` or `sudo dhcpt` without having to reinstall.

### Running Tests

```bash
# 1. Start the testbed (creates namespaces and launches Kea):
make testbed-start

# 2. Check status and running PIDs:
make testbed-status

# 3. Run all live E2E test suites:
make e2e

# 4. Stop the testbed and clean up namespaces:
make testbed-stop
```

### Interactive Debugging Inside Namespaces

Enter any namespace with convenient Makefile commands:

```bash
# Open bash inside the client workstation:
make testbed-workstation

# Open bash inside the VPN gateway router:
make testbed-vpn-gw

# Open bash inside the legitimate DHCP server:
make testbed-server

# Open bash inside the rogue server:
make testbed-rogue
```

### Inspect Live Logs and Packets

```bash
# Follow Kea server logs live:
tail -f /tmp/dhcpt-kea-run/dhcpt-kea-legit.log

# Capture live DHCP packets on the server interface:
sudo ip netns exec dhcp-server tcpdump -ni veth-server -vvv port 67
```

---

## 6. Continuous Integration (CI)

In GitHub Actions:
* **Live Network E2E (`e2e-live-kea`):** Runs on **`ubuntu-26.04`** with native ISC Kea 3.0.
* **Linting & Documentation (`lint-shell-and-docs`):** Runs on **`ubuntu-26.04`** executing `make lint`.
* **Enterprise Linux Unit Tests (`test-enterprise-linux`):** Runs inside an official **`almalinux:9`** container validating native Python 3.9 on Enterprise Linux.
* **Ubuntu Python Matrix (`test-ubuntu`):** Runs on **`ubuntu-latest`** validating Python 3.10, 3.11, 3.12, and 3.13.

---

## 7. Adding New Tests

1. Create a script in `tests/e2e/suites/<category>/test_my_feature.sh`.
2. Make it executable (`chmod +x tests/e2e/suites/<category>/test_my_feature.sh`).
3. Include the assertion helper:
   ```bash
   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
   source "${SCRIPT_DIR}/../../helpers/assert.sh"
   ```
4. Verify your script with linters and run the test:
   ```bash
   make lint
   make e2e
   ```
