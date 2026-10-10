# dhcpt - AI Developer Guidelines & Context

## Project Overview
`dhcpt` is a standalone, high-performance DHCP testing, troubleshooting, and diagnostic CLI utility for Linux. It crafts and inspects raw Layer 2/3 DHCP packets using Scapy and provides vendor-neutral DHCP Relay Agent / IP-Helper simulation.

- **Author / Maintainer:** Emilian Schweikert ([@epicade](https://github.com/epicade))
- **AI Collaborative Partner:** Gemini CLI (Google Gemini)

---

## Core Engineering Mandates

### 1. Licensing & Legal Integrity
- **License:** GNU General Public License v2.0 or later (**GPL-2.0-or-later**).
- **Rationale:** The core network crafting dependency is `scapy`, which is licensed under GPLv2. All code in this repository MUST remain compatible with GPLv2+.
- **Prohibition:** NEVER introduce Apache-2.0 or proprietary code that conflicts with GPLv2 copyleft terms.

### 2. Dependency & Architecture Standards
- **Zero Heavy Dependencies:** The project relies strictly on the **Python standard library** and **`scapy>=2.5.0`**.
- Do NOT introduce heavy CLI frameworks (e.g. `click`, `typer`) or HTTP libraries (`requests`, `urllib3`).
- **Python Compatibility:** Code must remain strictly compatible with **Python 3.9+** (tested up to Python 3.13/3.14). Do not use Python 3.10+ syntax (such as `match/case` or un-annotated union types) without `from __future__ import annotations`.

### 3. Lease-Safety
- `dhcpt` is a diagnostic tool, not a full client daemon.
- It MUST ONLY perform the **DHCP Discover -> DHCP Offer** cycle.
- NEVER implement or send a DHCP Request in standard test mode to avoid committing leases or exhausting IP address pools on DHCP servers.

### 4. Output & Formatting Standards
- **No Emojis:** Terminal output, debug logs, error messages, and reports must be clean, ASCII/Unicode text without emoji decorations.
- **RFC Standards Transparency:** Explicitly reference relevant RFCs (RFC 2131, RFC 2132, RFC 3046, RFC 3397, RFC 3442, RFC 3527) in help texts, output tables, and docstrings.
- **Vendor Neutrality:** Do not hardcode company-internal or vendor-specific domain names or IP addresses into the core repository. Use RFC documentation subnets (RFC 5737 / RFC 1918) and example domains.

### 5. Interface, Permission & Exit-Code Standards
- **Explicit Interface:** Target interfaces explicitly via `-i / --interface` (or positional argument). Do not implement interactive prompt-based guessing in headless or non-interactive environments.
- **Permissions & Error Handling:** Rely on socket-level permission error handling (`try/except PermissionError`) rather than hard `geteuid() == 0` checks, allowing containerized execution or ambient capabilities.
- **Standard Exit Codes:**
  * `0`: Success (all queried DHCP servers replied, or local Offer captured).
  * `1`: Failure / Timeout (0 DHCP Offers received, or permission denied).
  * `2`: CLI Usage / Syntax error (missing interface, invalid IP/MAC, unknown option).
  * `3`: Partial response (multi-server query where some servers replied but at least one timed out).

---

## Development & Live-Testing Workflow

### 1. Instant Live-Testing via `make install-dev`
Running `make install-dev` automatically sets up the global symlink `/usr/local/bin/dhcpt -> src/dhcpt/cli.py`.
This enables instant live-testing with `sudo dhcpt` without having to reinstall the package or run pip installs after every edit:
```bash
# Automated via Makefile (recommended):
make install-dev

# Or manual symlink into /usr/local/bin (accessible in sudo secure_path):
sudo ln -sf "$(pwd)/src/dhcpt/cli.py" /usr/local/bin/dhcpt

# Or symlink to your personal scripte directory:
ln -sf "$(pwd)/src/dhcpt/cli.py" ~/scripte/dhcpt
```

### 2. Verifying Active Installation & Binary Resolution
To verify whether `dhcpt` is properly installed and to confirm which exact script is executed by both your regular user and `sudo`:
```bash
# 1. Check user-level resolution:
which dhcpt
readlink -f "$(which dhcpt)"

# 2. Check sudo resolution (respecting /etc/sudoers secure_path):
sudo which dhcpt
sudo readlink -f "$(sudo which dhcpt)"

# 3. Verify execution without sending network traffic:
dhcpt --version
dhcpt --list-interfaces
dhcpt --list-options
```
If `sudo readlink -f "$(sudo which dhcpt)"` points to `.../src/dhcpt/cli.py`, every edit you save in the repository is immediately executed by `sudo dhcpt`.

---

## Testing & Quality Assurance

### 1. Developer Makefile Commands
- Run all linters (Ruff, ShellCheck, Pandoc, Kea config) and unit tests:
  ```bash
  make check
  ```
- Install full development environment (system tools + Python dependencies):
  ```bash
  make install-dev
  ```

### 2. Live E2E Network Testbed (ISC Kea in Network Namespaces)
For verifying raw socket packet crafting, kernel routing, and DHCP options against active daemons:
- **Prerequisites:** `kea-dhcp4-server` and `jq` installed (`make install-dev`).
- **Start Testbed:**
  ```bash
  make testbed-start
  ```
  Spins up isolated namespaces (`workstation`, `vpn-gw`, `dhcp-server`, `dhcp-rogue`), a Linux bridge (`br-dhcpt`), and launches legitimate and rogue Kea servers with 100% host isolation.
- **Run Live Test Suites:**
  ```bash
  make testbed-run
  ```
  Executes all modular test suites under `tests/e2e/suites/` (Broadcast, MAC reservations, unicast relays, L3 tunnels, timeouts, rogue detection).
- **Check Status & Live Logs:**
  ```bash
  make testbed-status
  tail -f /tmp/dhcpt-kea-run/dhcpt-kea-legit.log
  ```
- **Stop & Clean Up:**
  ```bash
  make testbed-stop
  ```
*Detailed Architecture:* See [`docs/testing-infrastructure.md`](docs/testing-infrastructure.md) for full topology diagrams and policy details.

### 3. Pre-Commit Git Hook
The repository includes an automated pre-commit hook in `.githooks/pre-commit` that validates Ruff, ShellCheck, Zsh completion syntax, Pandoc manpage freshness, Kea configuration schemas, and Pytest on every commit. Ensure it is active locally:
```bash
git config core.hooksPath .githooks
```

---

## Git & Commit Conventions
- Commit messages must be written in **English**, following Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`).
- **Logical Topic Splitting**: Group changes into multiple focused, topic-oriented commits (at least one commit per distinct topic/theme, e.g. core functionality, test suites/harnesses, documentation/changelog, and build/pre-commit tooling). Never create monolithic all-in-one commits.
- Every AI-assisted commit must include the collaborative co-author attribution:
  ```text
  Co-authored-by: Gemini <gemini@local>
  ```
