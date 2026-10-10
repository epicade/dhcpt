# CHANGELOG

All notable changes to this project will be documented in this file.
This project adheres to [Semantic Versioning](http://semver.org/) and [Keep a Changelog](http://keepachangelog.com/).



## Unreleased
---

### New
* Add comprehensive Python library documentation and usage guide (docs/library-usage.md)
* Add executable module entrypoint src/dhcpt/__main__.py for direct execution via python3 -m dhcpt
* Add UNIX manpage dhcpt(1) with shared-data installation for pipx and Linux package managers
* Add --install-skill CLI command to deploy agent skills for Gemini CLI, Claude Code, or Mistral Vibe
* Add live Kea DHCPv4 end-to-end testbed with 20-cycle pool exhaustion lease-safety verification (make testbed-run)
* Add developer Makefile for build, lint, and testbed automation (install, check, test, lint, format, testbed-*)
* Add dynamic DIM autocompletion to Bash and Zsh completion scripts (DHCPT_SERVER_PATTERNS, circuit-ids, relay-subnets)
* Add automated legal compliance test suite (tests/test_license_compliance.py) and version consistency validator (tests/test_version_consistency.py)
* Export public library networking functions and dataclasses in dhcpt.__init__

### Changes
* Include tests directory in source distribution (sdist) for downstream package builders
* Require explicit target DHCP servers (-s/--dhcp-servers) on Layer 3 interfaces and exit with code 2 if omitted
* Validate Linux kernel routing egress interface on Layer 3 devices and emit warning on mismatch
* Require --force flag to be used exclusively with --install-skill and exit with code 2 if supplied otherwise
* Mirror relay simulation JSON block under 'relay_simulation' and deprecate 'cisco_relay_simulation' for v1.0.0
* Standardize CLI options on -s/--dhcp-server/--dhcp-servers and --target-gateway, deprecating legacy --server and --relay-subnet with migration warnings
* Consolidate Linux kernel routing and next-hop gateway resolution via 'ip route get' (get_route_for_ip)
* Support multi-level verbosity (-v for INFO, -vv for DEBUG) alongside --debug
* Format verbose and debug logs with curl-style status indicators (* [state], > [send], < [recv])
* Redesign failure output to emit concise single-line error messages to stderr
* Rewrite documentation and manual page into clear, jargon-free plain language

### Fixes
* Resolve remote DHCP server next-hop MAC address on Layer 2 interfaces when reached via static route
* Add defensive target validation to --install-skill to prevent unhandled KeyError
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
