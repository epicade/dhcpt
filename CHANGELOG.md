# CHANGELOG

All notable changes to this project will be documented in this file.
This project adheres to [Semantic Versioning](http://semver.org/) and [Keep a Changelog](http://keepachangelog.com/).



## Unreleased
---

### New
* Add dynamic DIM autocompletion to Bash completion script (DHCPT_SERVER_PATTERNS, circuit-ids, relay-subnets)
* Add shared-data mappings in pyproject.toml for automatic shell completion installation in system and global environments
* Add assistant auto-detection and overwrite protection (--force) to --install-skill
* Add UNIX manpage dhcpt(1) with shared-data installation for pipx and Linux package managers
* Add --install-skill CLI flag to deploy agent skills for Gemini CLI, Claude Code, or Mistral Vibe

### Changes
* Add shell script validation (bash -n and shellcheck) to pre-commit git hook
* Add ENVIRONMENT section in manpage documenting DHCPT_SERVER_PATTERNS and DIM integration
* Format DIM reference as [DIM - DNS and IP Management](https://github.com/ionos-core/dim) in README
* Document both automatic system-wide and user-level shell completion setup in README
* Expand public SKILL.md and README with comprehensive Layer 3, WireGuard, and dynamic interface testing recipes
* Replace README reference in --help with 'man dhcpt' and GitHub documentation URL

### Fixes

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


