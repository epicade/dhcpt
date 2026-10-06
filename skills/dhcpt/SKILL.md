---
name: dhcpt
description: Test and troubleshoot DHCP servers, pools, and Option 82 relays — run DHCP discovers, simulate Cisco/Juniper IP-helpers, detect rogue servers, inspect offered IPs, leases, and Option 121 classless static routes.
---

# dhcpt - DHCP Testing & Troubleshooting Guide

`dhcpt` is a Layer 2/3 DHCP testing, troubleshooting, and diagnostic CLI utility written in Python. It crafts RFC-compliant DHCP Discover packets, listens for DHCP Offers, and analyzes network parameters, lease times, Option 82 relay information, and RFC 3442 routing options.

---

## When to Use `dhcpt`

Trigger this skill whenever you need to:
1. **Verify if a DHCP server is responding** on a network segment or VLAN without configuring an interface or consuming an IP lease.
2. **Simulate a DHCP Relay Agent (e.g. Cisco `ip helper-address`, Juniper `dhcp-relay`)** to test whether central DHCP servers (e.g. Anycast servers) have an active pool for a specific subnet.
3. **Detect Rogue DHCP Servers** on a local broadcast domain.
4. **Debug Option 82 / Circuit-ID routing** to check if DHCP servers apply the expected policies.
5. **Inspect pushed DHCP options** (Subnet Mask, Default Gateway, DNS, NTP, Domain Search List, RFC 3442 Classless Static Routes).

---

## Privileges & Prerequisites

* **Root Privileges:** Layer 2 raw packet crafting (`AF_PACKET`) requires `sudo`.
* **Path:** `/usr/local/bin/dhcpt` (system-wide) or user symlink from `~/.local/bin/dhcpt`.

### Installation (If `dhcpt` is not installed)
If `command -v dhcpt` fails on the target system, install it:
```bash
# 1. Install Scapy prerequisite:
# Debian / Ubuntu:
sudo apt update && sudo apt install -y python3-scapy
# RHEL / Rocky / AlmaLinux / Oracle Linux:
sudo dnf install -y python3-scapy

# 2. Install latest release tag globally via pipx (places binary into /usr/local/bin):
LATEST_TAG=$(git ls-remote --tags --refs https://github.com/epicade/dhcpt.git | tail -n1 | cut -d/ -f3)
sudo pipx install --global "git+https://github.com/epicade/dhcpt.git@${LATEST_TAG}"
# Or install a specific version tag (e.g. @v0.1.1):
# sudo pipx install --global git+https://github.com/epicade/dhcpt.git@<tag>
```

### Passwordless Execution for AI Agents / Automation
If running non-interactively from AI CLI agents (Gemini CLI, Claude Code), a scoped rule in `/etc/sudoers.d/dhcpt` prevents password prompt blocks:
```bash
echo "$USER ALL=(ALL) NOPASSWD: /usr/local/bin/dhcpt" | sudo tee /etc/sudoers.d/dhcpt
sudo chmod 0440 /etc/sudoers.d/dhcpt
```

---

## Common Workflows & Command Recipes

### 1. Standard Local Broadcast Check
Sends a DHCP Discover broadcast on a specific interface (flag or positional):
```bash
sudo dhcpt -i eth0
# or positional:
sudo dhcpt eth0
```

### 2. Layer 3 Tunnel / VPN Testing (WireGuard / OpenVPN TUN)
On Layer 3 interfaces without hardware MAC addresses, `dhcpt` automatically uses IP-level I/O (`AF_INET` raw sockets). Superuser privileges (`sudo`) are still required because raw socket creation requires the Linux `CAP_NET_RAW` capability. Always specify target server IPs (`-s`) and ensure your routing table directs traffic to the tunnel:
```bash
# 1. Verify routing table sends traffic to tunnel interface:
ip route get 10.1.1.1

# 2. Run test over the tunnel:
sudo dhcpt -i wg0 --dhcp-servers 10.1.1.1 --target-gateway 10.50.1.1
```

### 3. Rogue DHCP Server Detection (`--all`)
Listens for the full timeout duration to capture all answering DHCP servers on the segment:
```bash
sudo dhcpt -i eth0 --all --timeout 5
```
*If multiple distinct servers answer, `dhcpt` outputs a `[WARN]` and lists every server ID, MAC, and offered IP.*

### 4. DHCP Relay Agent & IP-Helper Simulation
When testing whether dedicated DHCP servers respond for a remote VLAN or subnet:
```bash
# Test target server (IP or FQDN) with RFC 3527 Link Selection for the target subnet:
sudo dhcpt -i eth0 --dhcp-servers 192.0.2.1 --target-gateway 10.50.1.1 --circuit-id Vlan100
sudo dhcpt -i eth0 --dhcp-servers dhcp1.example.com --target-gateway 10.50.1.1 --circuit-id Vlan100

# Test multiple dedicated DHCP servers simultaneously:
sudo dhcpt -i eth0 --dhcp-servers 10.1.1.1,10.1.1.2,10.1.1.3,10.1.1.4 --target-gateway 10.50.1.1 --circuit-id Vlan100 --remote-id sw-core01
```

* **Why `--target-gateway` (RFC 3527 Link Selection)?**
  RFC 2131 dictates that DHCP servers reply to `giaddr`. Setting `--target-gateway <gateway_ip>` (or alias `--relay-subnet`) tells the DHCP server which address pool to allocate from — specifically, the gateway IP configured as the identifier for that VLAN in the DHCP server's subnet declaration. Meanwhile, `dhcpt` sets `giaddr` to your local machine IP so the DHCP server routes the reply directly back to you across routed networks.

### 5. Fast-Path: Constructing Remote Relay Queries
When testing a remote subnet or VLAN without manually looking up the network device name:
1. **Identify the DHCP Server IP & Target Subnet Gateway:**
   Determine the DHCP server IP (e.g. `192.0.2.1` or enterprise Anycast IP) and the default gateway of the target subnet (e.g. `10.50.1.1`).
2. **Resolve the Outgoing Interface Automatically:**
   ```bash
   IFACE=$(ip route get <SERVER_IP> | grep -oP 'dev \K\S+')
   ```
3. **Execute the Relay Query Immediately:**
   ```bash
   sudo dhcpt -i "$IFACE" --dhcp-servers <SERVER_IP> --target-gateway <GATEWAY_IP> [-m <MAC>]
   ```

### 6. Request Custom DHCP Options (`-o`)
Standard options (Subnet Mask, Router, DNS, NTP, Domain, Classless Routes, WPAD) are included by default. To request additional options (e.g. for PXE netboot or VoIP):
```bash
sudo dhcpt -i eth0 -o 12,26,66,67
# or by name:
sudo dhcpt -i eth0 -o hostname,tftp_server_name,interface_mtu

# Request ONLY specific options without standard network defaults (e.g. for IoT/PXE):
sudo dhcpt -i eth0 --clear-default-options -o 26
```
*Tip: Run `dhcpt --list-options` to inspect all supported options and codes, or consult the [IANA BOOTP/DHCP Parameters Registry](https://www.iana.org/assignments/bootp-dhcp-parameters).*

### 7. Unicast Offer Delivery (`--no-broadcast`)
Test if the DHCP server correctly delivers offers via unicast to clients that reject broadcast packets:
```bash
sudo dhcpt -i eth0 --no-broadcast
```

### 8. Machine-Readable JSON Output
```bash
sudo dhcpt -i eth0 --json
```

---

## Exit Codes

* **`0` (Success):** All queried DHCP servers replied, or at least one Offer was captured on broadcast.
* **`1` (No Offer / Failure):** Timed out with 0 DHCP Offers received, or raw socket permission failure.
* **`2` (Usage / Syntax Error):** Missing required interface, invalid IP/MAC, or unknown DHCP option.
* **`3` (Partial Response):** Multi-server query (`-s`) where some servers replied but at least one timed out.

---

## Interpreting Output & Troubleshooting

### If No Offer is Received:
1. **Link State:** Check whether `operstate` is `up` and `carrier` is `1`. If down, run `sudo ip link set <iface> up`.
2. **UDP Port 67 Reachability (Netcat):** When testing remote servers (e.g. over VPN or routed networks), verify if UDP port 67 is accessible:
   ```bash
   # -u: UDP mode, -z: zero-I/O scanning, -v: verbose, -w 2: 2-second timeout
   nc -z -v -u -w 2 <server_ip> 67
   ```
   *(Note: Netcat on Linux/OpenBSD uses single-letter options; long options like `--udp` are not supported).*
3. **Pool Exhaustion & Server Rejection:** If Netcat succeeds (`Connection to <server_ip> 67 port [udp/bootps] succeeded!`) but `dhcpt` times out:
   * Is the address pool exhausted? Check server logs.
   * Does a pool exist for `--target-gateway <GW>` on the server?
   * Does the server require specific Option 82 attributes (`--circuit-id` or `--remote-id`)?
4. **VLAN Tagging:** Verify if the client port is on the correct access VLAN or trunk PVID.
5. **DHCP Relay Configuration:** On the upstream switch, check if `ip helper-address <server>` is configured on the SVI.
6. **Firewall:** Verify host and network firewalls permit incoming UDP port 67 and 68.

### If an Offer is Received:
* **`yiaddr` (Offered IP):** The IP address offered by the server.
* **`server_id` / Server IP:** Identifies which server answered.
* **`Option 82`:** Confirms if the relay agent forwarded Circuit-ID and Remote-ID.
* **`Option 121 / 249` (Classless Static Routes):** Shows static routes pushed for VPN or enterprise subnets (e.g. `10.0.0.0/8 via 192.168.1.1`).
