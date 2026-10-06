# dhcpt (DHCP Tester)

[![CI](https://github.com/epicade/dhcpt/actions/workflows/ci.yml/badge.svg)](https://github.com/epicade/dhcpt/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-GPL_2.0-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html)
[![Co-Authored With AI](https://img.shields.io/badge/Co--Authored%20With-Google%20Gemini%20CLI-orange.svg)](#-ai-authorship--transparency-disclosure)

`dhcpt` is a standalone, lease-safe DHCP testing and diagnostic CLI utility for Linux.
It crafts raw Layer 2 and Layer 3 DHCP packets using Scapy to troubleshoot local networks, remote relays, and VPN tunnels.

> 📖 **Full Manual Page:**  
> Run **`man dhcpt`** or view **[`man/dhcpt.1.md`](man/dhcpt.1.md)** for exhaustive option documentation.

---

## Why `dhcpt`?

Standard DHCP clients like `dhclient` or `NetworkManager` bind IP addresses to your network card, overwrite default gateways, and replace `/etc/resolv.conf`. Nagios `check_dhcp` lacks modern relay options and provides no structured JSON output.

### How `dhcpt` Solves This

* **Lease-Safe:** Executes only the first two steps of the standard **DORA cycle** (Discover -> Offer). It never sends a DHCP Request and never consumes an IP lease.
* **Zero Network Changes:** Inspects DHCP offers without modifying your IP address, default gateway, or routing table.
* **Relay & IP-Helper Simulation:** Unicasts queries (`-s`) with Option 82 Sub-option 1 (Circuit ID), Sub-option 2 (Remote ID), and Sub-option 5 (RFC 3527 Link Selection).
* **Layer 2 & Layer 3 Support:** Runs on Ethernet adapters and point-to-point VPN tunnels (WireGuard `wg0`, OpenVPN `tun0`).
* **Catches Rogue Servers:** Listens across the full timeout window (`--all`) to capture all answering servers on the broadcast domain.
* **Decodes Advanced Options:** Formats Option 82, RFC 3442 Option 121 Classless Static Routes, and RFC 3397 Option 119 Domain Search lists.
* **Monitoring & Scripting Ready:** Clean text tables without emojis and machine-readable JSON output (`--json`).

---

## Example Output

Running a simple check against a DHCP server produces a clean, structured report:

```text
$ sudo dhcpt -i eth0 -s 10.99.0.1
================================================================================
DHCP OFFER #1 (Server: 10.99.0.1)
================================================================================
Network Configuration:
  Offered IP (yiaddr)     : 10.99.0.100
  Subnet Mask (Opt 1)     : 255.255.255.0 (/24)
  Default Gateway (Opt 3) : 10.99.0.1
  DNS Servers (Opt 6)     : 10.99.0.1
  Domain Name (Opt 15)    : example.com

Classless Static Routes (RFC 3442 / VPN & Enterprise):
  * 10.0.0.0/8 via 10.99.0.1
  * 192.168.50.0/24 via 10.99.0.254

Lease Information:
  Lease Time (Opt 51)     : 4000s (1h 6m 40s)
  DHCP Server ID (Opt 54) : 10.99.0.1
================================================================================
```

---

## Quickstart

### 1. Test Local Broadcast Network

Send a broadcast Discover on a local network interface:

```bash
sudo dhcpt -i eth0
# or positional:
sudo dhcpt eth0
```

### 2. Simulate Router Relay / IP-Helper (`-s`, `--target-gateway`)

Simulate a router relay agent forwarding traffic from a remote VLAN.
Pass the server IP and the target subnet gateway defined in the DHCP server pool:

```bash
sudo dhcpt -i eth0 -s 192.0.2.1 --target-gateway 10.50.1.1 --circuit-id Vlan100 --remote-id sw-core-01
```

*Deep Dive:* See the [DHCP Relay Architecture Guide](docs/relay-mechanics.md) for network diagrams.

### 3. Detect Rogue DHCP Servers (`--all`)

Listen for the full timeout duration to capture all answering servers on the segment:

```bash
sudo dhcpt -i eth0 --all --timeout 5
```

### 4. Output Formatted JSON (`--json`)

Generate machine-readable JSON for monitoring checks and automation scripts:

```bash
sudo dhcpt -i eth0 --json
```

---

## Quick Reference / Cheat Sheet

| Option | Description |
| :--- | :--- |
| **`-i, --interface <dev>`** | Target network interface (e.g. `eth0`, `ens3`, `wg0`). Also accepted as positional argument. |
| **`-s, --dhcp-servers <ips>`** | Comma-separated remote DHCP server IPs to query via unicast (e.g. `-s 10.1.1.1,10.1.1.2`). |
| **`--target-gateway <ip>`** | Target subnet gateway IP for RFC 3527 Link Selection (simulates remote VLAN pool). |
| **`--circuit-id <id>`** | Inject Option 82 Sub-option 1 Agent Circuit ID (e.g. `Vlan100`, `ge-0/0/1`). |
| **`--remote-id <id>`** | Inject Option 82 Sub-option 2 Agent Remote ID (e.g. switch hostname or MAC). |
| **`--giaddr <ip>`** | Override BOOTP relay agent gateway IP (defaults to local outgoing interface IP). |
| **`-o, --request-options <opts>`** | Append option codes or names to Parameter Request List (e.g. `-o 26,67` or `-o interface_mtu`). |
| **`--clear-default-options`** | Request ONLY options explicitly passed with `-o` (simulates minimal IoT/PXE ROMs). |
| **`--no-broadcast`** | Request unicast offer delivery without setting the BOOTP broadcast flag. |
| **`-m, --mac <mac>`** | Spoof client hardware MAC address to test static reservations (e.g. `-m 00:11:22:33:44:55`). |
| **`-a, --all`** | Listen for the full timeout duration to detect all answering (and rogue) servers. |
| **`-t, --timeout <sec>`** | Timeout in seconds to wait for offers (default: `5.0`). |
| **`-j, --json`** | Format results as structured JSON. |
| **`-v, -vv, -d`** | Verbose / debug logging (`*` state, `>` send, `<` recv). |
| **`-l, --list-interfaces`** | List available network interfaces with IP, MAC, carrier, and operstate. |
| **`--list-options`** | List supported DHCP option codes, names, and formats. |

---

## Installation

`dhcpt` requires Linux, Python 3.9+, and Scapy.
Because raw network sockets require `CAP_NET_RAW`, run `dhcpt` with `sudo`.

### 1. Prerequisites (Install Scapy)

```bash
# Debian / Ubuntu:
sudo apt install python3-scapy

# RHEL / Rocky / AlmaLinux / Oracle Linux:
sudo dnf install python3-scapy
```

### 2. Installation Options

#### Option A: Latest Stable Release (Recommended for Production)

Install a verified release tag. Check [GitHub Releases](https://github.com/epicade/dhcpt/releases) for available versions:

```bash
# Install a specific release tag (replace <tag> with your desired version, e.g. v0.1.1):
sudo pipx install --global git+https://github.com/epicade/dhcpt.git@<tag>

# Or install the latest release automatically in a single command:
LATEST_TAG=$(git ls-remote --tags --refs https://github.com/epicade/dhcpt.git | tail -n1 | cut -d/ -f3)
sudo pipx install --global "git+https://github.com/epicade/dhcpt.git@${LATEST_TAG}"
```

#### Option B: Development Version (Bleeding-Edge `main` Branch)

Install the latest commit directly from the development branch:

```bash
sudo pipx install --global git+https://github.com/epicade/dhcpt.git
```

#### Option C: From Local Source

```bash
git clone https://github.com/epicade/dhcpt.git
cd dhcpt
sudo make install
```

#### Option D: Direct Python Execution (No Binary Installation)

Run `dhcpt` directly from source or within container environments:

```bash
sudo python3 -m dhcpt -i eth0
```

---

## Exit Codes

`dhcpt` returns standard UNIX exit codes suitable for monitoring checks (Nagios, Icinga, Zabbix):

| Exit Code | Meaning | Description |
| :--- | :--- | :--- |
| **`0`** | **Success** | All queried DHCP servers replied, or local offer was captured. |
| **`1`** | **Timeout / Failure** | Zero DHCP offers received within timeout, or permission denied. |
| **`2`** | **Syntax / Usage Error** | Missing interface, invalid IP/MAC format, or unknown option. |
| **`3`** | **Partial Response** | Multi-server query (`-s`) where some servers answered but at least one timed out. |

---

## Shell Completions & AI Agent Integration

### Shell Completions (Bash & Zsh)

Global installations automatically copy completions to system directories.
You can also generate completions manually:

```bash
# System-wide installation:
sudo dhcpt --completion zsh | sudo tee /usr/local/share/zsh/site-functions/_dhcpt >/dev/null
sudo dhcpt --completion bash | sudo tee /usr/local/share/bash-completion/completions/dhcpt >/dev/null
```

*Dynamic DIM Integration:* If `ndcli` ([DIM - DNS and IP Management](https://github.com/ionos-core/dim)) is installed, completions dynamically autocomplete DHCP server hostnames (configured via `$DHCPT_SERVER_PATTERNS`), VLAN pools, and subnets. See [`man/dhcpt.1.md`](man/dhcpt.1.md#environment) for configuration details.

### AI Agent Skill Integration

`dhcpt` provides a built-in skill installer for terminal coding assistants:

```bash
# Auto-detect installed assistants (Gemini CLI, Claude Code, Mistral Vibe):
dhcpt --install-skill

# Or install for a specific assistant:
dhcpt --install-skill gemini
```

---

## Troubleshooting

### 1. Check UDP Port 67 Reachability with Netcat

Before debugging DHCP configurations across VPN tunnels or firewalls, test reachability on UDP port 67:

```bash
nc -z -v -u -w 2 <server_ip> 67
```

*Options:* `-u` (UDP mode), `-z` (port scan), `-v` (verbose), `-w 2` (timeout in seconds).

If Netcat succeeds but `dhcpt` times out, UDP traffic is permitted.
The server may be dropping queries due to pool exhaustion, unconfigured subnets, or Option 82 policies.

### 2. Inspect Detailed Packet Trees (`-vv`)

Inspect outgoing Discover frames and incoming server Offers in detail:

```bash
sudo dhcpt -i eth0 -s <server_ip> -vv
```

---

## Development & Contributing

```bash
# 1. Clone repository:
git clone https://github.com/epicade/dhcpt.git
cd dhcpt

# 2. Setup development environment:
# Installs system tools (Kea, Jq, ShellCheck, Pandoc, Zsh) and links /usr/local/bin/dhcpt
# directly to src/dhcpt/cli.py. Code edits in src/ are immediately live!
make install-dev

# 3. Run all linters and unit tests:
make check

# 4. Recompile manual page:
make man

# 5. Run live network testbed in isolated namespaces:
make testbed-start
make e2e
make testbed-stop
```

For full testbed architecture details, see the [Testing Infrastructure Guide](docs/testing-infrastruktur.md).

---

## 🤖 AI Authorship & Transparency Disclosure

This tool was designed by **Emilian Schweikert ([@epicade](https://github.com/epicade))**.
It was implemented, tested, and documented in collaboration with **Gemini CLI (Google Gemini)**.

* **Human Lead:** Architecture, network design, Cisco relay mechanics, and validation.
* **AI Developer:** Packet crafting routines, option decoders, test suites, and packaging.
* **Quality Assurance:** All code is human-reviewed and verified against live ISC Kea servers.
* **Commit History:** All AI-assisted commits include explicit co-author attribution.

---

## License

This project is licensed under the **GNU General Public License v2.0 or later (GPL-2.0-or-later)** to remain compatible with Scapy. See the [LICENSE](LICENSE) file for details.
