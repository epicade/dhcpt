# CHANGELOG

All notable changes to this project will be documented in this file.
This project adheres to [Semantic Versioning](http://semver.org/) and [Keep a Changelog](http://keepachangelog.com/).



## Unreleased
---

### New
* Add empirical 20-cycle pool exhaustion stress test to lease-safety verification suite
* Add live Kea DHCPv4 end-to-end testbed and automated lease-safety verification (make testbed-run)
* Add automated legal compliance test suite (tests/test_license_compliance.py) verifying GPL-2.0-or-later licensing and guarding against Apache-2.0 runtime dependencies
* Add Linux kernel FIB route egress validation (get_route_egress_interface) on Layer 3 interfaces and warn on device mismatch
* Require explicit target DHCP servers (-s/--dhcp-servers) on Layer 3 interfaces and abort immediately with exit code 2 if omitted
* Add project metadata and documentation version consistency validator (tests/test_version_consistency.py)
* Add Makefile testbed namespace shortcuts (make testbed-workstation, make testbed-vpn-gw, make testbed-server, make testbed-rogue)
* Add executable module entrypoint src/dhcpt/__main__.py for python3 -m dhcpt execution
* Add developer Makefile with help, install, test, lint, format, and check targets
* Export public library networking functions and dataclasses in dhcpt.__init__
* Add shared-data mappings in pyproject.toml for automatic shell completion installation in system and global environments
* Add dynamic DIM autocompletion to Bash completion script (DHCPT_SERVER_PATTERNS, circuit-ids, relay-subnets)
* Add assistant auto-detection and overwrite protection (--force) to --install-skill
* Add --install-skill CLI flag to deploy agent skills for Gemini CLI, Claude Code, or Mistral Vibe
* Add UNIX manpage dhcpt(1) with shared-data installation for pipx and Linux package managers

### Changes
* Unify Makefile target naming under testbed-run and testbed-shell, and group help synopsis
* Consolidate kernel routing and next-hop gateway resolution via ip route get (get_route_for_ip)
* Deprecate --server / --servers in favor of -s / --dhcp-server / --dhcp-servers and --relay-subnet in favor of --target-gateway
* Streamline developer Makefile and automatically configure Git pre-commit hooks in make install-dev
* Document installation workflows for latest stable release tags (with automated tag discovery) vs bleeding-edge development (main branch)
* Simplify documentation and manpage into clear, jargon-free plain language with short sentences
* Document Netcat UDP port 67 diagnostic reachability verification workflow in manpage, skill, and README
* Format verbose and debug output in curl style using unified state, send, and receive indicators
* Redesign failure output to emit concise single-line error messages to stderr without verbose checklist
* Include tests/ directory in source distribution (sdist) build target in pyproject.toml for downstream distribution packagers
* Bring Zsh shell completion to parity with Bash and CLI by adding --completion argument
* Support multi-level verbosity (-v for INFO, -vv for DEBUG) alongside --debug
* Add --dhcp-servers and --dhcp-server plural and singular aliases for -s / --servers
* Adopt --target-gateway as primary CLI option with --relay-subnet as backward-compatible alias
* Document both automatic system-wide and user-level shell completion setup in README
* Author UNIX manpage in Markdown (man/dhcpt.1.md) and compile to troff via pandoc
* Expand public SKILL.md and README with comprehensive Layer 3, WireGuard, and dynamic interface testing recipes
* Format DIM reference as [DIM - DNS and IP Management](https://github.com/ionos-core/dim) in README
* Simplify system-wide installation documentation to use native pipx --global flag
* Replace README reference in --help with 'man dhcpt' and GitHub documentation URL

### Fixes
* Add defensive target validation to --install-skill to prevent unhandled KeyError
* Resolve remote DHCP server next-hop MAC address on Layer 2 interfaces when reached via static route
* Differentiate Layer 2 and Layer 3 raw socket error messages and preserve CLI arguments in sudo recommendation
* Resolve Zsh completion syntax error on --target-gateway and add runtime tab-completion test
* Resolve decoding of RFC 3442 Classless Static Routes (Option 121) from Scapy string representations
* Resolve standalone execution version resolution in cli.py to prevent version drift when invoked via symlink
* Quiet Scapy internal runtime log warnings on Layer 3 tunnel interfaces during normal operation

### Breaks


## 0.1.1 - (2026-10-02)
---

### Fixes
* Bundle shell completion scripts in wheel packages and resolve via importlib.resources


## 0.1.0 - (2026-10-02)
---

### New
* Automated sysfs link diagnostics and troubleshooting checklist
* Dynamic shell completion generation for Zsh and Bash
* Machine-readable JSON output format via --json
* Layer 3 point-to-point interface support (WireGuard / TUN)
* Rogue DHCP server detection on local broadcast domains via --all
* RFC 3442 / Option 121 and 249 Classless Static Routes decoding
* RFC 3527 Link Selection (Option 82 Sub-option 5) support
* Vendor-neutral DHCP Relay Agent & IP-Helper simulation for Cisco, Juniper, Arista, and Linux
* Raw Layer 2 and Layer 3 DHCP Discover and Offer engine using Scapy

