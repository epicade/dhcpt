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

## Testing & Quality Assurance

Before committing any change:
1. Run linter:
   ```bash
   ruff check .
   ```
2. Check formatting:
   ```bash
   ruff format --check .
   ```
3. Run test suite:
   ```bash
   PYTHONPATH=src pytest
   ```

### Pre-Commit Git Hook
The repository includes a pre-commit hook in `.githooks/pre-commit`. Ensure it is active locally:
```bash
git config core.hooksPath .githooks
```

---

## Git & Commit Conventions
- Commit messages must be written in **English**, following Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`).
- Every AI-assisted commit must include the collaborative co-author attribution:
  ```text
  Co-authored-by: Gemini <gemini@local>
  ```
