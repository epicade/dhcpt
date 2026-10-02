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

## Why `dhcpt`?

Traditional DHCP tools fall short in enterprise environments:
* **Nagios `check_dhcp`** is written in C, hard to extend, lacks modern Option 82/RFC 3442 decoding, and does not provide JSON output.
* **Standard OS clients** (`dhclient`, `dhcpcd`, `NetworkManager`) immediately bind and reconfigure the local network interface and routing tables — exactly what you *do not* want when troubleshooting or auditing network segments.
* **Lease-safe:** `dhcpt` only performs Step 1 (DHCP Discover) and analyzes Step 2 (DHCP Offer). It **never requests or consumes an IP lease** in your DHCP server database.

`dhcpt` is designed from the ground up for troubleshooting:
* **Explicit & Safe Interface Targeting:** Target network interfaces explicitly via `-i / --interface` (or positional) to avoid accidental packet injection on multi-homed or management links.
* **Lease-safe Testing:** Only exchanges Discover -> Offer; never requests or commits IP leases.
* **Layer 2 & Layer 3 Point-to-Point Support:** Tests physical Ethernet interfaces as well as Layer 3 point-to-point/VPN tunnel interfaces (WireGuard, OpenVPN, TUN) without requiring Ethernet framing.
* **Cisco IP-Helper & Relay Simulation:** Test whether dedicated central DHCP servers respond to a specific VLAN/subnet without being physically plugged into that VLAN.
* **Rogue DHCP Detection (`--all`):** Listens for the entire timeout window to identify rogue, unauthorized, or misconfigured DHCP servers on the broadcast domain.
* **Comprehensive RFC Option Decoder:** Decodes network parameters, Lease times, Option 82 (Circuit ID, Remote ID), and RFC 3442 Classless Static Routes.
* **Structured Output:** Clean, emoji-free terminal output and machine-readable JSON for monitoring and scripting.

---

## Installation

### Prerequisites
`dhcpt` requires Python 3.9+ and Scapy. Because crafting raw Layer 2 Ethernet frames (`AF_PACKET`) requires elevated privileges, run `dhcpt` with `sudo`.

```bash
# On Debian / Ubuntu:
sudo apt install python3-scapy

# On RHEL / Rocky / AlmaLinux / Oracle Linux:
sudo dnf install python3-scapy
```

### Install via pip / pipx
Because crafting raw network packets requires `sudo`, installing `dhcpt` system-wide to `/usr/local/bin` ensures it is accessible within `sudo`'s default `secure_path`:

```bash
# Recommended: System-wide pipx installation into /usr/local/bin
sudo PIPX_BIN_DIR=/usr/local/bin PIPX_HOME=/opt/pipx pipx install git+https://github.com/epicade/dhcpt.git

# Alternatively, standard system-wide pip install:
sudo pip install git+https://github.com/epicade/dhcpt.git

# Or install for your local user and create a symlink to /usr/local/bin:
pipx install git+https://github.com/epicade/dhcpt.git
sudo ln -s "$HOME/.local/bin/dhcpt" /usr/local/bin/dhcpt
```

### Local Development Installation
```bash
git clone https://github.com/epicade/dhcpt.git
cd dhcpt
python -m pip install -e .[dev]

# Optional: Directly symlink for immediate sudo testing without reinstalling:
sudo ln -sf "$(pwd)/src/dhcpt/cli.py" /usr/local/bin/dhcpt
```

To verify your installation and confirm which binary `sudo` executes:
```bash
sudo which dhcpt
readlink -f "$(sudo which dhcpt)"
```

### Passwordless Sudo for Automation & AI Agents (Optional)
Since raw Layer 2 socket packet crafting requires root privileges, automated background scripts, CI pipelines, or AI CLI assistants (such as Gemini CLI or Claude Code) might fail or block if prompted for a password.

To allow passwordless execution **exclusively** for `dhcpt` without granting broad root permissions:
```bash
echo "$USER ALL=(ALL) NOPASSWD: /usr/local/bin/dhcpt" | sudo tee /etc/sudoers.d/dhcpt
sudo chmod 0440 /etc/sudoers.d/dhcpt
```
This restricts the passwordless permission strictly to the `dhcpt` executable.

### UNIX Manual Page (`man dhcpt`)
When installed via `pipx` or standard system packages, `dhcpt` automatically provides an offline UNIX manual page:
```bash
man dhcpt
```

### AI Agent Skill Installation (Gemini CLI, Claude Code, Mistral Vibe)
`dhcpt` bundles ready-to-use agent skills for conversational CLI agents:
```bash
# Auto-detect installed assistants (~/.gemini, ~/.claude, ~/.vibe) and deploy:
dhcpt --install-skill

# Or install explicitly for a specific assistant:
dhcpt --install-skill gemini     # Installs to ~/.gemini/skills/dhcpt/SKILL.md
dhcpt --install-skill claude     # Installs to ~/.claude/skills/dhcpt/SKILL.md
dhcpt --install-skill mistral    # Installs to ~/.vibe/skills/dhcpt/SKILL.md

# Force overwrite if a skill file already exists:
dhcpt --install-skill --force
```

* **Intelligent Auto-Detection:** When running `--install-skill` without arguments (or with `all`), `dhcpt` checks for active assistant environments and only deploys to detected assistants. It never creates unneeded directories for missing tools.
* **Overwrite Protection:** If a `SKILL.md` file or symlink already exists at the destination, `dhcpt` refuses to overwrite it and returns an error. This protects customized skills or symlinked repositories. Pass `--force` to explicitly overwrite.

---

## Usage

### Standard Broadcast Check
Test whether any local DHCP server responds on an interface:
```bash
sudo dhcpt -i eth0
# or positionally:
sudo dhcpt eth0
```

### Layer 3 Point-to-Point & WireGuard / VPN Testing
On Layer 3 interfaces without Ethernet framing (WireGuard `wg0`, OpenVPN `tun0`), `dhcpt` automatically uses IP-level raw socket I/O:
```bash
sudo dhcpt -i wg0 -s 10.1.1.1 --relay-subnet 10.50.1.1
```

### Dynamic Egress Interface Discovery
When querying a remote server across routed corporate subnets or tunnels, discover the outgoing interface dynamically:
```bash
IFACE=$(ip route get 10.1.1.1 | grep -oP 'dev \K\S+')
sudo dhcpt -i "$IFACE" -s 10.1.1.1 --relay-subnet 10.50.1.1 --circuit-id Vlan100
```

### Test Dedicated DHCP Servers (Cisco IP-Helper Unicast Simulation)
Query one or multiple central DHCP servers directly by IP or FQDN:
```bash
# Single server:
sudo dhcpt -i eth0 -s 192.0.2.1 --relay-subnet 10.50.1.1 --circuit-id Vlan100

# Full Option 82 simulation (Circuit-ID + Remote-ID / switch hostname):
sudo dhcpt -i eth0 -s 192.0.2.1 --relay-subnet 10.50.1.1 --circuit-id Vlan100 --remote-id sw-core01

# Multiple dedicated DHCP servers simultaneously:
sudo dhcpt -i eth0 -s 10.1.1.1,10.1.1.2,10.1.1.3,10.1.1.4 --relay-subnet 10.50.1.1

# Override BOOTP Relay Agent Gateway IP (giaddr):
sudo dhcpt -i eth0 -s 192.0.2.1 --relay-subnet 10.50.1.1 --giaddr 10.50.1.254
```

### Client MAC Spoofing for Static Lease Verification
Verify whether static IP reservations or MAC filtering rules function as expected without changing physical network interface MACs:
```bash
sudo dhcpt -i eth0 -s 192.0.2.1 --relay-subnet 10.50.1.1 -m 00:11:22:33:44:55
```

### Detect Rogue DHCP Servers
Listen for the full timeout duration to capture all answering servers on the broadcast domain:
```bash
sudo dhcpt -i eth0 --all --timeout 5
```

### Request Additional DHCP Options
Default requests include Subnet Mask, Gateway, DNS, Domain, Static Routes, NTP, Vendor Info, and WPAD. Pass custom option numbers or names:
```bash
sudo dhcpt -i eth0 -o 12,26,66,67
# or by name:
sudo dhcpt -i eth0 -o hostname,interface_mtu,tftp_server_name
```

### Output JSON for Automation / Monitoring
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

## DHCP Relay Agent & IP-Helper Simulation (Cisco, Juniper, Arista, Linux)

### Vendor Terminology Comparison
Across enterprise vendors, DHCP relaying is named differently but implements the same RFC 2131/3046/3527 standards:

| Platform | Configuration Directive |
|:---|:---|
| **Cisco IOS / NX-OS** | `ip helper-address <dhcp-server-ip>` |
| **Juniper Junos** | `set forwarding-options dhcp-relay server-group ...` |
| **Arista EOS** | `ip helper-address <dhcp-server-ip>` |
| **Linux (ISC / Kea / systemd)** | `dhcrelay <dhcp-server-ip>` |

### How Relay Agents Work
When a network switch or router interface (SVI / VLAN / RVI) has DHCP relay enabled:
1. The relay intercepts Layer 2 DHCP Discover broadcasts (255.255.255.255, UDP 68 -> 67).
2. It converts the broadcast into a Layer 3 UDP unicast (sport 67 -> dport 67) sent to the helper IP(s).
3. It inserts:
   * **`giaddr` (Gateway IP):** The relay interface IP on that subnet (e.g. `10.50.1.1`).
   * **`hops = 1`**
   * **Option 82 Sub-option 1 (`circuit-id`):** e.g. `'Vlan100'`, `'ge-0/0/1'`, or interface name.
   * **Option 82 Sub-option 2 (`remote-id`):** Relay hostname or MAC address.
4. The DHCP server inspects `giaddr`, selects the matching pool/subnet, and replies to `giaddr`.

### The Networking Challenge & RFC 3527 Solution
RFC 2131 §4.1 dictates that the DHCP server routes the `DHCPOFFER` back to the IP specified in `giaddr`! If you set `giaddr=10.50.1.1` from your workstation, the DHCP server sends the reply to the physical switch/router — your workstation never sees it.

**The Solution:** `dhcpt` implements **RFC 3527 (Link Selection Sub-option 5)**:
* `giaddr` is set to **your workstation IP** (so the server routes the reply directly back to you).
* **Option 82 Sub-option 5 (`link_selection`)** is set to the target subnet gateway (`--relay-subnet 10.50.1.1`).
* The DHCP server allocates from the target pool, but delivers the Offer to your machine!

---

## Supported RFC DHCP Options

| Code | Option Name | Default PRL | RFC Reference |
|:---:|:---|:---:|:---|
| 1 | `subnet_mask` | Yes | RFC 2132 |
| 3 | `router` | Yes | RFC 2132 |
| 6 | `name_server` | Yes | RFC 2132 |
| 12 | `hostname` | No | RFC 2132 |
| 15 | `domain` | Yes | RFC 2132 |
| 26 | `interface_mtu` | No | RFC 2132 |
| 28 | `broadcast_address` | Yes | RFC 2132 |
| 33 | `static_routes` | Yes | RFC 2132 |
| 42 | `ntp_servers` | Yes | RFC 2132 |
| 43 | `vendor_specific` | Yes | RFC 2132 |
| 66 | `tftp_server_name` | No | RFC 2132 |
| 67 | `bootfile_name` | No | RFC 2132 |
| 81 | `client_fqdn` | No | RFC 4702 |
| 82 | `relay_agent_information` | (Received) | RFC 3046 |
| 119 | `domain_search` | Yes | RFC 3397 |
| 121 | `classless_static_routes` | Yes | RFC 3442 (VPN / Enterprise) |
| 249 | `ms_classless_static_routes` | Yes | Microsoft RFC 3442 equiv (VPN) |
| 252 | `wpad` | Yes | Web Proxy Auto-Discovery |

View all supported options directly from the CLI:
```bash
dhcpt --list-options
```

---

## Shell Completions (Zsh & Bash)

When installed via `pipx` or `pip`, Python CLI tools do not automatically install shell completion scripts into your system directories because Python package managers do not know which shell you use or where your `$fpath` points.

`dhcpt` solves this by generating its own completion scripts on demand with the `--completion` flag:

### Installation & Setup

#### For Zsh:
```bash
# 1. Create your user site-functions directory (if it doesn't exist yet):
mkdir -p ~/.local/share/zsh/site-functions

# 2. Save the completion script (lazy-loaded on demand, zero shell startup delay):
dhcpt --completion zsh > ~/.local/share/zsh/site-functions/_dhcpt

# 3. Ensure your site-functions directory is in your fpath in ~/.zshrc (before compinit):
#    fpath=(~/.local/share/zsh/site-functions $fpath)
#    autoload -Uz compinit && compinit

# 4. Reload completion in your current shell:
autoload -Uz compinit && compinit -C
```

#### For Bash:
```bash
# Save to the standard user bash-completion directory (auto-loaded on demand):
mkdir -p ~/.local/share/bash-completion/completions
dhcpt --completion bash > ~/.local/share/bash-completion/completions/dhcpt
```

### Features of the Shell Completion
* **Network Interfaces:** Autocompletes available physical/virtual interfaces from `/sys/class/net` (with link status and MAC preview).
* **DHCP Options (`-o <TAB>`):** Autocompletes RFC option codes and human-readable names (`subnet_mask`, `router`, `classless_static_routes`, etc.).
* **Dynamic DIM Integration:** If `ndcli` (the CLI for [DIM (DNS and IP Management)](https://github.com/ionos-core/dim)) is installed on your system, the completion script integrates with DIM:
  - **DHCP Servers (`-s / --server <TAB>`):** To avoid returning thousands of irrelevant DNS records from your DIM database, define your organization's DHCP server search patterns in `~/.zshrc`:
    ```bash
    export DHCPT_SERVER_PATTERNS="dhcp*.example.com dhcp*.corp.internal"
    ```
    *(If `ndcli` is detected but `$DHCPT_SERVER_PATTERNS` is unset, `dhcpt` displays an informative error on `stderr` explaining how to configure it, rather than querying an uncontrolled wildcard).*
  - **VLAN Circuit-IDs (`--circuit-id <TAB>`):** Autocompletes VLAN numbers and pool names from `ndcli list pools`.
  - **Relay Subnets (`--relay-subnet <TAB>`):** Autocompletes subnet CIDRs and gateways from `ndcli list pools`.
  *(Cache TTL is 24 hours in `~/.cache/dhcpt/` so tab completion is instantaneous and never lags. If `ndcli` is not installed, it falls back seamlessly to standard prompt completion).*

---

## Development & Testing

This project uses `pytest` and `ruff` for code quality and testing:

```bash
# Run tests
PYTHONPATH=src pytest -v

# Run linter
ruff check .

# Check formatting
ruff format --check .
```

### Git Hooks
Activate the pre-commit hook that automatically validates code formatting, linting, and tests before every commit:
```bash
git config core.hooksPath .githooks
```

---

## License

This project is licensed under the **GNU General Public License v2.0 or later (GPL-2.0-or-later)** to remain fully compatible with Scapy. See the [LICENSE](LICENSE) file for details.
