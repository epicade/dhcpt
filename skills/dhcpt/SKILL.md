---
name: dhcpt
description: Test and troubleshoot DHCP servers, pools, and Option 82 relays — run DHCP discovers, simulate Cisco/Juniper IP-helpers on Layer 2 and Layer 3 (WireGuard/VPN/TUN), detect rogue servers, inspect offered IPs, leases, and Option 121 classless static routes.
---

# dhcpt - DHCP Testing & Troubleshooting Guide

`dhcpt` is a Layer 2/3 DHCP testing, troubleshooting, and diagnostic CLI utility written in Python. It crafts RFC-compliant DHCP Discover packets, listens for DHCP Offers, and analyzes network parameters, lease times, Option 82 relay information, and RFC 3442 routing options.

---

## When to Use `dhcpt`

Trigger this skill whenever you need to:
1. **Verify if a DHCP server is responding** on a network segment or VLAN without configuring an interface or consuming an IP lease.
2. **Simulate a Cisco/Juniper/Arista/Linux DHCP Relay Agent (`ip helper-address`)** on Layer 2 interfaces or Layer 3 routed/VPN links (WireGuard, OpenVPN, TUN) to test whether central DHCP servers have an active pool for a specific subnet.
3. **Detect Rogue DHCP Servers** on a local broadcast domain.
4. **Debug Option 82 / Circuit-ID routing** to check if DHCP servers apply expected policies.
5. **Verify static IP reservations** by spoofing target client MAC addresses (`-m / --mac`).
6. **Inspect pushed DHCP options** (Subnet Mask, Default Gateway, DNS, NTP, Domain Search List, RFC 3442 Classless Static Routes).

---

## Privileges & Prerequisites

* **Root Privileges:** Layer 2 raw packet crafting (`AF_PACKET`) requires `sudo`.
* **Path:** `/usr/local/bin/dhcpt` (system-wide) or user symlink from `~/.local/bin/dhcpt`.

### Installation
```bash
# 1. Install Scapy prerequisite:
# Debian / Ubuntu:
sudo apt update && sudo apt install -y python3-scapy
# RHEL / Rocky / AlmaLinux / Oracle Linux:
sudo dnf install -y python3-scapy

# 2. Install dhcpt globally into /usr/local/bin:
sudo pipx install --global git+https://github.com/epicade/dhcpt.git
```

### Install Agent Skill for Gemini CLI, Claude Code, or Mistral Vibe
`dhcpt` includes a built-in installer for AI agent skills:
```bash
# Automatically detects installed assistants (~/.gemini, ~/.claude, ~/.vibe) and deploys:
dhcpt --install-skill

# Or target a specific assistant:
dhcpt --install-skill gemini     # ~/.gemini/skills/dhcpt/SKILL.md
dhcpt --install-skill claude     # ~/.claude/skills/dhcpt/SKILL.md
dhcpt --install-skill mistral    # ~/.vibe/skills/dhcpt/SKILL.md

# Force overwrite existing skill files:
dhcpt --install-skill --force
```

* **Safety & Protection:** Auto-detection ensures only active assistants on your system receive the skill. Existing skill files and symlinks are never overwritten without `--force`.

### Passwordless Execution for AI Agents / Automation
If running non-interactively from AI CLI agents (Gemini CLI, Claude Code), a scoped rule in `/etc/sudoers.d/dhcpt` prevents password prompt blocks:
```bash
echo "$USER ALL=(ALL) NOPASSWD: /usr/local/bin/dhcpt" | sudo tee /etc/sudoers.d/dhcpt
sudo chmod 0440 /etc/sudoers.d/dhcpt
```

---

## Common Workflows & Command Recipes

### 1. Interface Discovery & Pre-flight Diagnostics
List all available network interfaces, link states (`operstate`, `carrier`), IP addresses, and MAC addresses without sending traffic:
```bash
dhcpt -l
# or:
dhcpt --list-interfaces
```

### 2. Standard Local Broadcast Check
Sends a DHCP Discover broadcast on a specific interface (flag or positional):
```bash
sudo dhcpt -i eth0
# or positional:
sudo dhcpt eth0
```

### 3. Dynamic Egress Interface Discovery for Remote / VPN Testing
When testing a remote DHCP server across routed networks or VPNs (WireGuard, OpenVPN, corporate tunnels), determine the outgoing interface dynamically:
```bash
IFACE=$(ip route get 10.1.1.1 | grep -oP 'dev \K\S+')
sudo dhcpt -i "$IFACE" -s 10.1.1.1 --relay-subnet 10.50.1.1 --circuit-id Vlan100
```

### 4. Layer 3 Point-to-Point & VPN Testing (WireGuard / TUN)
On Layer 3 point-to-point interfaces without MAC addresses, `dhcpt` automatically switches to IP-level I/O (`AF_INET` raw sockets):
```bash
sudo dhcpt -i wg0 -s 10.1.1.1 --relay-subnet 10.50.1.1
```

### 5. DHCP Relay Agent & IP-Helper Simulation (Cisco, Juniper, Arista, Linux)
Simulate how network switches and routers forward client requests to central DHCP servers:

```bash
# Standard Cisco IP-Helper simulation with RFC 3527 Link Selection:
sudo dhcpt -i eth0 -s 192.0.2.1 --relay-subnet 10.50.1.1 --circuit-id Vlan100

# Full Option 82 simulation (Circuit-ID + Remote-ID / switch hostname):
sudo dhcpt -i eth0 -s 192.0.2.1 --relay-subnet 10.50.1.1 --circuit-id Vlan100 --remote-id sw-core01

# Test multiple redundant DHCP servers simultaneously:
sudo dhcpt -i eth0 -s 10.1.1.1,10.1.1.2,10.1.1.3 --relay-subnet 10.50.1.1

# Override BOOTP Relay Agent IP (giaddr):
sudo dhcpt -i eth0 -s 192.0.2.1 --relay-subnet 10.50.1.1 --giaddr 10.50.1.254
```

* **Why `--relay-subnet` (RFC 3527 Link Selection)?**
  RFC 2131 dictates that DHCP servers reply to `giaddr`. Setting `--relay-subnet <gateway_ip>` tells the DHCP server which pool to allocate from while directing the reply back to your machine's IP.

### 6. Client MAC Spoofing for Static Lease Verification
Verify whether static IP reservations or MAC filtering rules function as expected without changing physical network interface MACs:
```bash
sudo dhcpt -i eth0 -m 00:11:22:33:44:55
sudo dhcpt -i eth0 -s 192.0.2.1 --relay-subnet 10.50.1.1 -m 00:11:22:33:44:55
```

### 7. Rogue DHCP Server Detection (`--all`)
Listens for the full timeout duration to capture all answering DHCP servers on the segment:
```bash
sudo dhcpt -i eth0 --all --timeout 5
```
*If multiple distinct servers answer, `dhcpt` outputs a `[WARN]` and lists every server ID, MAC, and offered IP.*

### 8. Custom & Minimal Option Requests
Standard options (Subnet Mask, Router, DNS, NTP, Domain, Classless Routes, WPAD) are included by default.
```bash
# List all known RFC options and default request status:
dhcpt --list-options

# Request additional custom options:
sudo dhcpt -i eth0 -o 12,26,66,67
sudo dhcpt -i eth0 -o hostname,tftp_server_name,interface_mtu

# Minimal test query (request ONLY specific options, clearing defaults):
sudo dhcpt -i eth0 --clear-default-options -o 1,3,6
```

### 9. Unicast Offer Testing (`--no-broadcast`)
Do not set the BOOTP broadcast flag, requesting the server to send the DHCP Offer via unicast:
```bash
sudo dhcpt -i eth0 --no-broadcast
```

### 10. Machine-Readable JSON Output
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

## Interpreting Output & Troubleshooting Checklist

### If No Offer is Received (`[FAILURE]`):
1. **Link State:** Check whether `operstate` is `up` and `carrier` is `1` using `dhcpt -l`. If down, run `sudo ip link set <iface> up`.
2. **Egress Route:** For remote servers, verify routing with `ip route get <SERVER_IP>`. Make sure `-i` matches the outgoing interface (e.g. `vpn0` or `wg0` instead of `eth0`).
3. **VLAN Tagging:** Verify if the client port is on the correct access VLAN or trunk PVID.
4. **DHCP Relay Configuration:** On the upstream switch, check if `ip helper-address <server>` is configured on the SVI.
5. **Firewall:** Verify host and network firewalls do not drop UDP ports 67 and 68.
6. **Pool Exhaustion:** Check DHCP server logs to see if the address pool has available leases.

### If an Offer is Received:
* **`yiaddr` (Offered IP):** The IP address offered by the server.
* **`server_id` / Server IP:** Identifies which server answered.
* **`Option 82`:** Confirms if the relay agent forwarded Circuit-ID and Remote-ID.
* **`Option 121 / 249` (Classless Static Routes):** Shows static routes pushed for VPN or enterprise subnets (e.g. `10.0.0.0/8 via 192.168.1.1`).
