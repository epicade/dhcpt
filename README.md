# dhcpt (DHCP Tester)

[![CI](https://github.com/epicade/dhcpt/actions/workflows/ci.yml/badge.svg)](https://github.com/epicade/dhcpt/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-GPL_2.0-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html)
[![Co-Authored With AI](https://img.shields.io/badge/Co--Authored%20With-Google%20Gemini%20CLI-orange.svg)](#-ai-authorship--transparency-disclosure)

A modern, fast, and comprehensive DHCP troubleshooting, testing, and diagnostic CLI utility written in Python. Built for network engineers, sysadmins, and DevOps teams managing enterprise networks and data centers.

---

## 🤖 AI Authorship & Transparency Disclosure

**Full Transparency:** This tool was conceived, architected, and directed by **Emilian Schweikert ([@epicade](https://github.com/epicade))**, and **fully implemented, tested, and documented in collaboration with Gemini CLI (Google Gemini)**.

- **Human Lead & Architect:** Emilian Schweikert ([@epicade](https://github.com/epicade)) — requirements, network topology design, Cisco relay mechanics, and validation.
- **AI Collaborative Developer:** Google Gemini CLI — implementation of Scapy Layer 2/3 frame construction, Option 82 / RFC 3442 decoding, test suite, and packaging.
- **Quality Assurance & Verification:** All code and packet crafting routines are human-reviewed, verified against real enterprise topologies, and covered by a 100% passing automated test suite.
- **Commit History Attribution:** All code commits include explicit `Co-authored-by: Gemini <gemini@local>` attribution footers.

---

> 📖 **Full Manual & CLI Specification:**  
> For the complete manual covering all command-line options, relay mechanics, RFC specifications, and exit codes, run **`man dhcpt`** or read **[`man/dhcpt.1.md`](man/dhcpt.1.md)**.

---

## Why `dhcpt`?

Traditional DHCP tools fall short in enterprise environments:
* **Nagios `check_dhcp`** is written in C, hard to extend, lacks modern Option 82/RFC 3442 decoding, and does not provide JSON output.
* **Standard OS clients** (`dhclient`, `dhcpcd`, `NetworkManager`) immediately bind and reconfigure the local network interface and routing tables — exactly what you *do not* want when troubleshooting or auditing network segments.
* **Lease-safe:** Out of the standard four-step DORA exchange (Discover, Offer, Request, Acknowledge), `dhcpt` only sends a Discover and inspects incoming Offers. It never sends a Request or commits an IP lease in your DHCP server database.

### Key Highlights
* **Lease-Safe Testing:** Executes only Discover → Offer (DORA steps 1 & 2); never allocates IP leases.
* **DHCP Relay & IP-Helper Simulation:** Query remote DHCP servers directly via unicast (`--dhcp-servers` / `-s`) and simulate originating from remote subnets via RFC 3527 Link Selection (`--target-gateway`) and Option 82 (`--circuit-id`, `--remote-id`).
* **Layer 2 & Layer 3 Support:** Works on physical Ethernet interfaces (`AF_PACKET`) as well as MAC-less Layer 3 interfaces (WireGuard, OpenVPN TUN via `AF_INET`).
* **Rogue DHCP Detection (`--all`):** Listens across the full timeout window to catch rogue or duplicate servers.
* **Comprehensive RFC Option Decoder:** Decodes network parameters, Lease times, Option 82, and RFC 3442 / Option 121 / Option 249 Classless Static Routes.
* **AI Agent Integration:** Built-in skill installer (`--install-skill`) for Gemini CLI, Claude Code, and Mistral Vibe.
* **Machine-Readable:** Structured, emoji-free terminal output and formatted JSON (`--json`) for automation.

---

## Installation

### Prerequisites
`dhcpt` requires Python 3.9+ and Scapy. Because crafting raw network packets requires elevated privileges, run `dhcpt` with `sudo`.

```bash
# On Debian / Ubuntu:
sudo apt install python3-scapy

# On RHEL / Rocky / AlmaLinux / Oracle Linux:
sudo dnf install python3-scapy
```

### Install via pipx / pip
Installing globally with `pipx` ensures `dhcpt` is placed in `sudo`'s default `secure_path` (`/usr/local/bin`) and automatically provisions the system manpage:

```bash
# Recommended: Global installation accessible in sudo secure_path
sudo pipx install --global git+https://github.com/epicade/dhcpt.git

# Alternatively, standard system-wide pip:
sudo pip install git+https://github.com/epicade/dhcpt.git
```

### UNIX Manual Page
When installed, the offline manual page is immediately available:
```bash
man dhcpt
```

---

## Quickstart & Common Recipes

### 1. Standard Broadcast Check
Test whether any local DHCP server responds on an interface:
```bash
sudo dhcpt -i eth0
# or positionally:
sudo dhcpt eth0
```

### 2. Test Remote DHCP Servers (Relay / IP-Helper Simulation)
Query one or multiple remote servers directly via unicast, simulating a relay agent (e.g. Cisco *ip helper-address*, Juniper *forwarding-options dhcp-relay*):
```bash
# Single server: simulate originating from VLAN 100 via RFC 3527 Link Selection:
sudo dhcpt -i eth0 --dhcp-servers 192.0.2.1 --target-gateway 10.50.1.1 --circuit-id Vlan100

# Multiple redundant servers simultaneously:
sudo dhcpt -i eth0 --dhcp-servers 10.1.1.1,10.1.1.2,10.1.1.3 --target-gateway 10.50.1.1
```
*Deep Dive:* For full packet flow diagrams and vendor directives (e.g. Cisco, Juniper, Arista, Linux), see the [DHCP Relay Architecture & RFC 3527 Guide](docs/relay-mechanics.md).

### 3. Detect Rogue DHCP Servers
Listen for the full timeout duration to capture all answering servers on the broadcast domain:
```bash
sudo dhcpt -i eth0 --all --timeout 5
```

### 4. Layer 3 WireGuard / VPN Tunnel Testing
On Layer 3 interfaces without MAC addresses, `dhcpt` automatically uses raw IP sockets:
```bash
sudo dhcpt -i wg0 --dhcp-servers 10.1.1.1 --target-gateway 10.50.1.1
```

### 5. Request Custom DHCP Options (`-o`)
Default requests include Subnet Mask, Gateway, DNS, Domain, Static Routes, NTP, Vendor Info, and WPAD. Request custom option codes or names:
```bash
sudo dhcpt -i eth0 -o 12,26,66,67
# or by name:
sudo dhcpt -i eth0 -o hostname,interface_mtu,tftp_server_name
```
*Run `dhcpt --list-options` to inspect supported RFC options, or consult the [IANA BOOTP/DHCP Parameters Registry](https://www.iana.org/assignments/bootp-dhcp-parameters).*

### 6. JSON Output for Automation & Monitoring
```bash
sudo dhcpt -i eth0 --json
```

---

## Shell Completions (Zsh & Bash)

When installed globally via `sudo pipx install --global`, completions are automatically provisioned in system directories. You can also generate them on demand:

```bash
# System-wide (recommended, matching global installation):
sudo dhcpt --completion zsh | sudo tee /usr/local/share/zsh/site-functions/_dhcpt >/dev/null
sudo dhcpt --completion bash | sudo tee /usr/local/share/bash-completion/completions/dhcpt >/dev/null

# Or user-local:
mkdir -p ~/.local/share/zsh/site-functions ~/.local/share/bash-completion/completions
dhcpt --completion zsh > ~/.local/share/zsh/site-functions/_dhcpt
dhcpt --completion bash > ~/.local/share/bash-completion/completions/dhcpt
```

*Dynamic DIM Integration:* If `ndcli` ([DIM - DNS and IP Management](https://github.com/ionos-core/dim)) is installed, completions dynamically autocomplete DHCP server hostnames (configured via `$DHCPT_SERVER_PATTERNS`), VLAN pools, and subnets. See [`man/dhcpt.1.md`](man/dhcpt.1.md#environment) for configuration details.

---

## AI Agent Integration

`dhcpt` includes a built-in skill installer to teach conversational CLI agents how to diagnose DHCP:

```bash
# Auto-detect installed agents (Gemini CLI, Claude Code, Mistral Vibe) and install:
dhcpt --install-skill

# Or target a specific assistant:
dhcpt --install-skill gemini
```

---

## Development

```bash
# Clone and install in editable mode:
git clone https://github.com/epicade/dhcpt.git
cd dhcpt
python -m pip install -e .[dev]

# Run all linters (Ruff, Pandoc manpage freshness, ShellCheck) and pytest:
make check

# Recompile UNIX manpage from Markdown source:
make man
```

---

## License

This project is licensed under the **GNU General Public License v2.0 or later (GPL-2.0-or-later)** to remain fully compatible with Scapy. See the [LICENSE](LICENSE) file for details.
