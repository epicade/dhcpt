#!/usr/bin/env python3
# Copyright (C) 2026 Emilian Schweikert
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""dhcpt - Comprehensive DHCP tester, troubleshooting, and diagnostic CLI utility.

Sends DHCP Discover packets on a specified network interface and analyzes
received DHCP Offer responses. Designed for Linux (Ubuntu, Debian, RHEL, Rocky, Alma, OL)
running Python 3.9+.

Note on AI Authorship & Collaboration:
This tool was collaboratively designed, implemented, and tested with Gemini CLI
(Google Gemini) as an AI development partner for Emilian Schweikert (@epicade).

Features:
- Explicit interface targeting: Target interfaces explicitly via -i/--interface
  or positionally. If omitted, displays an interface table with diagnostics and exits cleanly.
- Validates network interface existence and operational state via sysfs.
- DHCP Relay Agent & IP-Helper simulation (Cisco, Juniper, Arista, Linux):
  * Target specific dedicated DHCP servers via Layer 3 unicast (-s / --server).
  * Simulate Option 82 Relay Agent parameters (--circuit-id, --remote-id).
  * Simulate target subnets via RFC 3527 Link Selection (--relay-subnet).
  * Direct BOOTP relay agent gateway IP specification (--giaddr).
- Generates standards-compliant DHCP Discover packets with configurable
  Parameter Request List (Option 55) and Client Identifier (Option 61).
- Default requested options cover core RFC network parameters, enterprise/VPN
  routing (RFC 3442 Classless Static Routes, Option 121 and 249), DNS, NTP, and WPAD.
- Supports adding custom DHCP option codes or names via CLI (-o / --request-options).
- Captures single or multiple DHCP Offer responses (rogue DHCP detection).
- Parses essential network parameters (IP, Subnet Mask, Gateway, DNS, Lease Time).
- Decodes Option 82 (DHCP Relay Agent Information, Circuit-ID, Remote-ID).
- Decodes RFC 3442 / Option 121 / Option 249 Classless Static Routes for VPN/enterprise routing.
- Detailed debug logging for Layer 2/3 frame assembly and option decoding.
- Structured text and JSON output formats without emoji decorations.
- Built-in shell completion generation for Zsh and Bash (--completion {zsh,bash}).
- Diagnostic troubleshooting hints if no response is received.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import logging
import random
import re
import socket
import struct
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    from dhcpt import __version__
except ImportError:
    __version__ = "0.1.0"

# Scapy is required for Layer 2 and Layer 3 packet crafting and sniffing
try:
    from scapy.all import (
        ARP,
        BOOTP,
        DHCP,
        IP,
        UDP,
        Ether,
        conf,
        get_if_addr,
        get_if_hwaddr,
        sr,
        srp,
    )
    from scapy.error import Scapy_Exception
    from scapy.layers.dhcp import DHCPOptions, DHCPRevOptions, DHCPTypes

    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False

    class Scapy_Exception(Exception):  # type: ignore[no-redef]
        pass

    ARP = Any  # type: ignore[misc,assignment]
    BOOTP = Any  # type: ignore[misc,assignment]
    DHCP = Any  # type: ignore[misc,assignment]
    Ether = Any  # type: ignore[misc,assignment]
    IP = Any  # type: ignore[misc,assignment]
    UDP = Any  # type: ignore[misc,assignment]
    conf = Any  # type: ignore[misc,assignment]
    get_if_addr = Any  # type: ignore[misc,assignment]
    get_if_hwaddr = Any  # type: ignore[misc,assignment]
    sr = Any  # type: ignore[misc,assignment]
    srp = Any  # type: ignore[misc,assignment]
    DHCPOptions = {}  # type: ignore[misc,assignment]
    DHCPRevOptions = {}  # type: ignore[misc,assignment]
    DHCPTypes = {}  # type: ignore[misc,assignment]

LOGGER = logging.getLogger("dhcpt")

MAC_REGEX = re.compile(r"^([0-9a-fA-F]{2}[:-]){5}([0-9a-fA-F]{2})$")

# Known DHCP Options registry: code -> (canonical_name, rfc_description)
KNOWN_DHCP_OPTIONS: dict[int, tuple[str, str]] = {
    1: ("subnet_mask", "Subnet Mask (RFC 2132)"),
    3: ("router", "Default Gateway / Router (RFC 2132)"),
    6: ("name_server", "Domain Name Server (DNS) (RFC 2132)"),
    12: ("hostname", "Host Name (RFC 2132)"),
    15: ("domain", "Domain Name (RFC 2132)"),
    26: ("interface_mtu", "Interface MTU (RFC 2132)"),
    28: ("broadcast_address", "Broadcast Address (RFC 2132)"),
    31: ("perform_router_discovery", "Perform Router Discovery (RFC 2132)"),
    33: ("static_routes", "Static Routes (RFC 2132)"),
    42: ("ntp_servers", "Network Time Protocol (NTP) Servers (RFC 2132)"),
    43: ("vendor_specific", "Vendor Specific Information (RFC 2132)"),
    50: ("requested_ip", "Requested IP Address (RFC 2132)"),
    51: ("lease_time", "IP Address Lease Time (RFC 2132)"),
    53: ("message_type", "DHCP Message Type (RFC 2132)"),
    54: ("server_id", "DHCP Server Identifier (RFC 2132)"),
    58: ("renewal_time", "Renewal Time Value T1 (RFC 2132)"),
    59: ("rebinding_time", "Rebinding Time Value T2 (RFC 2132)"),
    60: ("vendor_class_id", "Vendor Class Identifier (RFC 2132)"),
    61: ("client_id", "Client Identifier (RFC 2132)"),
    66: ("tftp_server_name", "TFTP Server Name (RFC 2132)"),
    67: ("bootfile_name", "Bootfile Name (RFC 2132)"),
    81: ("client_fqdn", "Client FQDN (RFC 4702)"),
    82: ("relay_agent_information", "Relay Agent Information (RFC 3046)"),
    119: ("domain_search", "Domain Search List (RFC 3397)"),
    121: ("classless_static_routes", "Classless Static Routes (RFC 3442 / VPN)"),
    249: ("ms_classless_static_routes", "Microsoft Classless Static Routes (RFC 3442 equiv / VPN)"),
    252: ("wpad", "Web Proxy Auto-Discovery (PAC URL)"),
}

# Mapping of names/aliases to option codes
NAME_TO_OPTION_CODE: dict[str, int] = {
    name.lower().replace("-", "_"): code for code, (name, _) in KNOWN_DHCP_OPTIONS.items()
}
# Helpful aliases
NAME_TO_OPTION_CODE.update(
    {
        "dns": 6,
        "gateway": 3,
        "routes": 121,
        "vpn_routes": 121,
        "classless_routes": 121,
        "mtu": 26,
        "ntp": 42,
        "tftp": 66,
        "pxe": 67,
        "proxy": 252,
    }
)

# Standard RFC options always requested by default in Option 55 Parameter Request List
DEFAULT_REQUEST_OPTIONS: list[int] = [
    1,  # Subnet Mask (RFC 2132)
    3,  # Router / Gateway (RFC 2132)
    6,  # DNS Servers (RFC 2132)
    15,  # Domain Name (RFC 2132)
    28,  # Broadcast Address (RFC 2132)
    33,  # Static Routes (RFC 2132)
    42,  # NTP Servers (RFC 2132)
    43,  # Vendor-Specific Info (RFC 2132)
    119,  # Domain Search (RFC 3397)
    121,  # Classless Static Routes (RFC 3442 / VPN)
    249,  # MS Classless Static Routes (RFC 3442 equivalent / VPN)
    252,  # Web Proxy Auto-Discovery (WPAD)
]


@dataclass
class DHCPOptionItem:
    """Representation of an individual DHCP option."""

    code: int | None
    name: str
    value: Any
    raw_str: str


@dataclass
class DHCPOffer:
    """Representation of a received DHCP Offer."""

    server_ip: str
    server_mac: str
    offered_ip: str
    subnet_mask: str | None = None
    prefixlen: int | None = None
    routers: list[str] = field(default_factory=list)
    dns_servers: list[str] = field(default_factory=list)
    domain_name: str | None = None
    domain_search: list[str] = field(default_factory=list)
    lease_time: int | None = None
    renewal_time: int | None = None
    rebinding_time: int | None = None
    server_id: str | None = None
    giaddr: str | None = None
    siaddr: str | None = None
    xid: int = 0
    message_type: str = "offer"
    relay_info: dict[str, str] = field(default_factory=dict)
    classless_routes: list[str] = field(default_factory=list)
    options: list[DHCPOptionItem] = field(default_factory=list)
    raw_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert offer to dictionary suitable for JSON serialization."""
        data = asdict(self)
        data["xid_hex"] = f"0x{self.xid:08x}"
        return data


class DhcptLogFormatter(logging.Formatter):
    """Custom log formatter supporting layered tree and categorized diagnostic messages."""

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        if record.levelno == logging.DEBUG:
            if msg.startswith(("*", ">", "<", " ")):
                return msg
            return f"* {msg}"
        lvl = "WARN" if record.levelname == "WARNING" else record.levelname
        return f"[{lvl}] {msg}"


def setup_logging(debug: bool = False, verbose: bool = False) -> None:
    """Configure stream logging with structured prefixes and no emojis."""
    level = logging.WARNING
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO

    formatter = DhcptLogFormatter()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    LOGGER.setLevel(level)
    LOGGER.handlers.clear()
    LOGGER.addHandler(handler)


def validate_and_normalize_mac(mac: str) -> str:
    """Validate MAC address format and return normalized lowercase string."""
    cleaned = mac.strip()
    if not MAC_REGEX.match(cleaned):
        raise ValueError(f"Invalid MAC address format: '{mac}'. Expected format: aa:bb:cc:dd:ee:ff")
    return cleaned.lower().replace("-", ":")


def mac_to_bytes(mac_str: str) -> bytes:
    """Convert MAC string (aa:bb:cc:dd:ee:ff) to 6 raw bytes."""
    normalized = validate_and_normalize_mac(mac_str)
    return bytes.fromhex(normalized.replace(":", ""))


def format_duration(seconds: int) -> str:
    """Format duration in seconds into human-readable string (e.g. 1d 2h 3m 4s)."""
    if seconds < 0:
        return f"{seconds}s"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or hours > 0 or days > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return f"{seconds}s ({' '.join(parts)})"


def build_option_82(
    circuit_id: str | None = None,
    remote_id: str | None = None,
    link_selection: str | None = None,
) -> bytes:
    """Construct raw Option 82 (Relay Agent Information) bytes."""
    raw = bytearray()
    if circuit_id:
        c_bytes = circuit_id.encode("utf-8")
        if len(c_bytes) > 255:
            raise ValueError(f"circuit_id exceeds maximum length of 255 bytes ({len(c_bytes)} bytes)")
        raw.extend([1, len(c_bytes)])
        raw.extend(c_bytes)
    if remote_id:
        r_bytes = remote_id.encode("utf-8")
        if len(r_bytes) > 255:
            raise ValueError(f"remote_id exceeds maximum length of 255 bytes ({len(r_bytes)} bytes)")
        raw.extend([2, len(r_bytes)])
        raw.extend(r_bytes)
    if link_selection:
        try:
            l_bytes = socket.inet_aton(link_selection.strip())
            raw.extend([5, len(l_bytes)])
            raw.extend(l_bytes)
        except OSError as err:
            raise ValueError(f"Invalid IP address for link_selection: '{link_selection}'") from err
    return bytes(raw)


def parse_option_82(data: bytes) -> dict[str, str]:
    """Parse DHCP Option 82 (Relay Agent Information) sub-options."""
    suboptions: dict[str, str] = {}
    known_subopts = {
        1: "circuit_id",
        2: "remote_id",
        5: "link_selection",
        6: "subscriber_id",
        11: "server_id_override",
    }
    i = 0
    while i + 2 <= len(data):
        code = data[i]
        length = data[i + 1]
        val = data[i + 2 : i + 2 + length]
        i += 2 + length
        sub_name = known_subopts.get(code, f"subopt_{code}")
        if sub_name == "link_selection" and len(val) == 4:
            suboptions[sub_name] = socket.inet_ntoa(val)
        else:
            try:
                suboptions[sub_name] = val.decode("utf-8")
            except UnicodeDecodeError:
                suboptions[sub_name] = val.hex()
    return suboptions


def parse_classless_routes(raw_data: Any) -> list[str]:
    """Parse RFC 3442 (Option 121) / Microsoft (Option 249) Classless Static Routes."""
    routes: list[str] = []

    if isinstance(raw_data, (list, tuple)):
        for item in raw_data:
            if isinstance(item, (tuple, list)) and len(item) == 3:
                mask_len, prefix, router = item
                routes.append(f"{prefix}/{mask_len} via {router}")
        return routes

    if not isinstance(raw_data, bytes):
        return routes

    i = 0
    while i < len(raw_data):
        mask_len = raw_data[i]
        i += 1
        if mask_len > 32:
            break
        prefix_bytes_len = (mask_len + 7) // 8
        if i + prefix_bytes_len + 4 > len(raw_data):
            break
        prefix_octets = list(raw_data[i : i + prefix_bytes_len])
        i += prefix_bytes_len
        while len(prefix_octets) < 4:
            prefix_octets.append(0)
        prefix_ip = ".".join(str(b) for b in prefix_octets)
        router_ip = socket.inet_ntoa(raw_data[i : i + 4])
        i += 4
        routes.append(f"{prefix_ip}/{mask_len} via {router_ip}")

    return routes


def decode_rfc3397_domain_search(raw: bytes) -> list[str]:
    """Decode RFC 3397 Domain Search Option bytes into a list of domain strings."""
    domains: list[str] = []
    i = 0
    total = len(raw)
    while i < total:
        labels: list[str] = []
        visited: set[int] = set()
        curr = i
        advanced = False
        while curr < total:
            length = raw[curr]
            if length == 0:
                if not advanced:
                    i = curr + 1
                break
            if (length & 0xC0) == 0xC0:
                if curr + 1 >= total:
                    break
                ptr = ((length & 0x3F) << 8) | raw[curr + 1]
                if not advanced:
                    i = curr + 2
                    advanced = True
                if ptr in visited or ptr >= total:
                    break
                visited.add(ptr)
                curr = ptr
                continue
            curr += 1
            if curr + length > total:
                break
            label = raw[curr : curr + length].decode("ascii", errors="replace")
            labels.append(label)
            curr += length
            if not advanced:
                i = curr
        if labels:
            domains.append(".".join(labels))
        else:
            if not advanced:
                i += 1
    return domains


def format_packet_tree(pkt: Any, direction: str = ">", title: str = "") -> str:
    """Format a Scapy packet into a clean, human-readable layered ASCII tree."""
    lines: list[str] = []
    prefix = ">" if direction == ">" else "<"
    pkt_len = len(bytes(pkt)) if hasattr(pkt, "__bytes__") or hasattr(pkt, "__len__") else 0
    header = f"{prefix} {title} ({pkt_len} bytes):" if title else f"{prefix} DHCP Packet ({pkt_len} bytes):"
    lines.append(header)

    layers: list[tuple[str, str, list[str] | None]] = []

    if pkt.haslayer(Ether):
        src_mac = getattr(pkt[Ether], "src", "unknown")
        dst_mac = getattr(pkt[Ether], "dst", "unknown")
        layers.append(("Ethernet", f"{src_mac} -> {dst_mac}", None))

    if pkt.haslayer(IP):
        src_ip = getattr(pkt[IP], "src", "unknown")
        dst_ip = getattr(pkt[IP], "dst", "unknown")
        proto_desc = "Unicast" if dst_ip != "255.255.255.255" else "Broadcast"
        layers.append(("IPv4", f"{src_ip} -> {dst_ip} ({proto_desc})", None))

    if pkt.haslayer(UDP):
        sport = getattr(pkt[UDP], "sport", 0)
        dport = getattr(pkt[UDP], "dport", 0)
        layers.append(("UDP", f"{sport} -> {dport}", None))

    if pkt.haslayer(BOOTP):
        bootp = pkt[BOOTP]
        op = getattr(bootp, "op", 1)
        op_str = "BOOTREQUEST" if op == 1 else ("BOOTREPLY" if op == 2 else str(op))
        xid = getattr(bootp, "xid", 0)
        hops = getattr(bootp, "hops", 0)
        giaddr = getattr(bootp, "giaddr", "0.0.0.0")
        yiaddr = getattr(bootp, "yiaddr", "0.0.0.0")
        details = f"op={op} ({op_str}), xid=0x{xid:08x}, hops={hops}, giaddr={giaddr}"
        if yiaddr and yiaddr != "0.0.0.0":
            details += f", yiaddr={yiaddr}"
        layers.append(("BOOTP", details, None))

    if pkt.haslayer(DHCP):
        dhcp_sub: list[str] = []
        options = getattr(pkt[DHCP], "options", [])
        for opt in options:
            if opt in ("end", "pad"):
                continue
            if isinstance(opt, tuple):
                name = str(opt[0])
                vals = opt[1:]
                val_repr = ", ".join(map(str, vals)) if len(vals) > 1 else (str(vals[0]) if vals else "")
                if name in ("message-type", "message_type") and vals:
                    msg_type = DHCPTypes.get(vals[0], str(vals[0])) if isinstance(vals[0], int) else str(vals[0])
                    dhcp_sub.append(f"Option 53 (Message Type): {msg_type.capitalize()}")
                elif name == "client_id" and vals and isinstance(vals[0], bytes):
                    cid_hex = ":".join(f"{b:02x}" for b in vals[0])
                    dhcp_sub.append(f"Option 61 (Client ID)   : {cid_hex}")
                elif name in ("param_req_list", "parameter_request_list") and vals:
                    prl_codes = ", ".join(map(str, vals[0])) if isinstance(vals[0], (list, tuple)) else str(vals[0])
                    dhcp_sub.append(f"Option 55 (PRL)         : {prl_codes}")
                elif (name in ("relay_agent_Information", "relay_agent_information") or name == "82") and vals:
                    raw_r = vals[0] if isinstance(vals[0], bytes) else None
                    if raw_r:
                        parsed_r = parse_option_82(raw_r)
                        r_parts = [f"{k}={v}" for k, v in parsed_r.items()]
                        dhcp_sub.append(f"Option 82 (Relay Info)  : {', '.join(r_parts)}")
                elif name == "server_id" and vals:
                    dhcp_sub.append(f"Option 54 (Server ID)   : {val_repr}")
                else:
                    opt_title = name.replace("_", "-")
                    dhcp_sub.append(f"Option {opt_title:<17}: {val_repr}")
        layers.append(("DHCP", "", dhcp_sub if dhcp_sub else None))

    for idx, (layer_name, layer_info, sub_items) in enumerate(layers):
        is_last_layer = idx == len(layers) - 1
        branch = "└──" if is_last_layer else "├──"
        cont_branch = "    " if is_last_layer else "│   "

        if layer_info:
            lines.append(f"  {branch} {layer_name:<8} : {layer_info}")
        else:
            lines.append(f"  {branch} {layer_name}")

        if sub_items:
            for s_idx, s_item in enumerate(sub_items):
                s_is_last = s_idx == len(sub_items) - 1
                s_branch = "└──" if s_is_last else "├──"
                lines.append(f"  {cont_branch}  {s_branch} {s_item}")

    return "\n".join(lines)


def normalize_value(val: Any) -> Any:
    """Normalize binary or nested data into serializable / displayable format."""
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except UnicodeDecodeError:
            return val.hex()
    if isinstance(val, (list, tuple)):
        return [normalize_value(x) for x in val]
    return val


def parse_requested_options(opt_str: str) -> list[int]:
    """Parse comma-separated option codes or names into a list of integers."""
    options: list[int] = []
    for part in opt_str.split(","):
        p = part.strip().lower().replace("-", "_")
        if not p:
            continue
        if p.isdigit():
            code = int(p)
            if 1 <= code <= 254:
                if code not in options:
                    options.append(code)
            else:
                raise ValueError(f"DHCP option code must be between 1 and 254: {code}")
        elif p in NAME_TO_OPTION_CODE:
            code = NAME_TO_OPTION_CODE[p]
            if code not in options:
                options.append(code)
        else:
            raise ValueError(
                f"Unknown DHCP option name: '{part.strip()}'. "
                "Use numeric code (1-254) or run 'dhcpt --list-options' to see known names."
            )
    return options


def parse_server_ips(server_input: str) -> list[str]:
    """Parse comma-separated or space-separated list of server IP addresses or hostnames."""
    servers: list[str] = []
    for part in re.split(r"[,;\s]+", server_input.strip()):
        cleaned = part.strip()
        if not cleaned:
            continue
        try:
            ipaddress.IPv4Address(cleaned)
            if cleaned not in servers:
                servers.append(cleaned)
        except ValueError:
            try:
                resolved_ip = socket.gethostbyname(cleaned)
                LOGGER.debug("* [dns] Resolved server hostname '%s' -> %s", cleaned, resolved_ip)
                if resolved_ip not in servers:
                    servers.append(resolved_ip)
            except OSError as err:
                raise ValueError(f"Invalid server IP address or unresolvable hostname: '{cleaned}'") from err
    return servers


def format_options_summary(codes: list[int]) -> str:
    """Generate a clean summary string of option codes and names."""
    items: list[str] = []
    for c in codes:
        name = KNOWN_DHCP_OPTIONS.get(c, (f"option_{c}", ""))[0]
        items.append(f"{c} ({name})")
    return ", ".join(items)


def get_interface_diagnostics(interface: str) -> dict[str, Any]:
    """Read interface link details from sysfs (/sys/class/net/<iface>)."""
    sysfs_path = Path("/sys/class/net") / interface
    info: dict[str, Any] = {
        "exists": sysfs_path.exists(),
        "operstate": "unknown",
        "carrier": "unknown",
        "address": "unknown",
        "mtu": "unknown",
        "flags": "unknown",
    }
    if not sysfs_path.exists():
        return info

    for key in ("operstate", "carrier", "address", "mtu", "flags"):
        p = sysfs_path / key
        if p.exists():
            try:
                info[key] = p.read_text().strip()
            except (OSError, PermissionError):
                pass
    return info


def get_available_interfaces() -> list[dict[str, Any]]:
    """List all local network interfaces and their status."""
    interfaces: list[dict[str, Any]] = []
    try:
        if_list = socket.if_nameindex()
    except OSError:
        if_list = []

    for _, name in sorted(if_list, key=lambda x: x[1]):
        diag = get_interface_diagnostics(name)
        interfaces.append(
            {
                "name": name,
                "operstate": diag.get("operstate", "unknown"),
                "carrier": diag.get("carrier", "unknown"),
                "address": diag.get("address", "-"),
                "mtu": diag.get("mtu", "-"),
            }
        )
    return interfaces


def resolve_mac_via_arp(ip: str, iface: str, timeout: float = 1.0) -> str | None:
    """Actively resolve MAC address for an IP address via Scapy ARP ping."""
    if not SCAPY_AVAILABLE:
        return None
    try:
        ans, _ = srp(
            Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=ip),
            iface=iface,
            timeout=timeout,
            verbose=False,
        )
        for _, rcv in ans:
            if rcv.haslayer(ARP) and getattr(rcv[ARP], "hwsrc", None):
                resolved = str(rcv[ARP].hwsrc).lower()
                LOGGER.debug("* [arp] Resolved MAC for IP %s via active ARP: %s", ip, resolved)
                return resolved
    except (OSError, ValueError, Scapy_Exception) as err:
        LOGGER.debug("* [arp] Active ARP resolution failed for %s on '%s': %s", ip, iface, err)
    return None


def get_gateway_ip(iface: str) -> str | None:
    """Read IPv4 default gateway for interface from /proc/net/route."""
    try:
        with open("/proc/net/route") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 3 and parts[0] == iface and parts[1] == "00000000":
                    gw_hex = int(parts[2], 16)
                    if gw_hex != 0:
                        return socket.inet_ntoa(struct.pack("<L", gw_hex))
    except (OSError, ValueError):
        pass
    return None


def get_mac_for_ip(ip: str, iface: str, resolve_active: bool = True) -> str | None:
    """Resolve MAC address for an IP address via /proc/net/arp or active ARP ping."""
    try:
        with open("/proc/net/arp") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 6 and parts[0] == ip and parts[5] == iface:
                    mac = parts[3]
                    if mac != "00:00:00:00:00:00" and MAC_REGEX.match(mac):
                        return mac.lower()
    except OSError:
        pass

    if resolve_active:
        return resolve_mac_via_arp(ip, iface)

    return None


def is_layer3_interface(interface: str) -> bool:
    """Check if interface is a pure Layer 3 interface (no Ethernet framing, e.g. WireGuard/tun/ppp)."""
    type_file = Path("/sys/class/net") / interface / "type"
    if type_file.exists():
        try:
            # 1 is ARPHRD_ETHER (Ethernet). 65534 is ARPHRD_NONE (tun/WireGuard/Point-to-Point).
            return int(type_file.read_text().strip()) != 1
        except (ValueError, OSError):
            pass
    return False


def parse_dhcp_packet(pkt: Any) -> DHCPOffer:
    """Extract and structure DHCP offer parameters from a received Scapy frame."""
    server_ip = str(pkt[IP].src) if pkt.haslayer(IP) else "unknown"
    server_mac = str(pkt[Ether].src) if pkt.haslayer(Ether) else "n/a (Layer 3)"
    offered_ip = str(pkt[BOOTP].yiaddr) if pkt.haslayer(BOOTP) else "0.0.0.0"
    giaddr = str(pkt[BOOTP].giaddr) if pkt.haslayer(BOOTP) else "0.0.0.0"
    siaddr = str(pkt[BOOTP].siaddr) if pkt.haslayer(BOOTP) else "0.0.0.0"
    xid = int(pkt[BOOTP].xid) if pkt.haslayer(BOOTP) else 0

    subnet_mask: str | None = None
    prefixlen: int | None = None
    routers: list[str] = []
    dns_servers: list[str] = []
    domain_name: str | None = None
    domain_search: list[str] = []
    lease_time: int | None = None
    renewal_time: int | None = None
    rebinding_time: int | None = None
    server_id: str | None = None
    message_type: str = "offer"
    relay_info: dict[str, str] = {}
    classless_routes: list[str] = []
    options_list: list[DHCPOptionItem] = []

    if pkt.haslayer(DHCP):
        for opt in pkt[DHCP].options:
            if opt in ("end", "pad"):
                continue

            if isinstance(opt, tuple):
                opt_name = str(opt[0])
                opt_vals = opt[1:]

                opt_code: int | None = None
                if opt_name.isdigit():
                    opt_code = int(opt_name)
                elif opt_name in NAME_TO_OPTION_CODE:
                    opt_code = NAME_TO_OPTION_CODE[opt_name]
                else:
                    rev_entry = DHCPRevOptions.get(opt_name)
                    if rev_entry:
                        opt_code = rev_entry[0]

                if opt_code and opt_code in KNOWN_DHCP_OPTIONS:
                    canonical_name = KNOWN_DHCP_OPTIONS[opt_code][0]
                else:
                    canonical_name = opt_name

                if canonical_name in ("message_type", "message-type") and opt_vals:
                    raw_type = opt_vals[0]
                    if isinstance(raw_type, int):
                        message_type = DHCPTypes.get(raw_type, str(raw_type))
                    else:
                        message_type = str(raw_type)

                elif canonical_name == "server_id" and opt_vals:
                    server_id = str(opt_vals[0])

                elif canonical_name == "subnet_mask" and opt_vals:
                    subnet_mask = str(opt_vals[0])
                    try:
                        prefixlen = ipaddress.IPv4Network(f"0.0.0.0/{subnet_mask}").prefixlen
                    except ValueError:
                        prefixlen = None

                elif canonical_name == "router":
                    routers = [str(r) for r in opt_vals if r]

                elif canonical_name == "name_server":
                    dns_servers = [str(ns) for ns in opt_vals if ns]

                elif canonical_name == "domain" and opt_vals:
                    val = opt_vals[0]
                    domain_name = val.decode("utf-8", errors="replace") if isinstance(val, bytes) else str(val)

                elif canonical_name == "domain_search":
                    for ds in opt_vals:
                        if isinstance(ds, bytes):
                            domain_search.extend(decode_rfc3397_domain_search(ds))
                        elif isinstance(ds, (list, tuple)):
                            domain_search.extend(str(item) for item in ds)
                        else:
                            domain_search.append(str(ds))

                elif canonical_name == "lease_time" and opt_vals:
                    try:
                        lease_time = int(opt_vals[0])
                    except (ValueError, TypeError):
                        pass

                elif canonical_name == "renewal_time" and opt_vals:
                    try:
                        renewal_time = int(opt_vals[0])
                    except (ValueError, TypeError):
                        pass

                elif canonical_name == "rebinding_time" and opt_vals:
                    try:
                        rebinding_time = int(opt_vals[0])
                    except (ValueError, TypeError):
                        pass

                elif (canonical_name == "relay_agent_information" or opt_code == 82) and opt_vals:
                    if isinstance(opt_vals[0], bytes):
                        relay_info = parse_option_82(opt_vals[0])

                elif canonical_name in ("classless_static_routes", "ms_classless_static_routes") or opt_code in (
                    121,
                    249,
                ):
                    parsed_routes = parse_classless_routes(opt_vals[0] if len(opt_vals) == 1 else opt_vals)
                    for r in parsed_routes:
                        if r not in classless_routes:
                            classless_routes.append(r)

                if canonical_name == "domain_search" and domain_search:
                    norm_val = domain_search
                    val_str = ", ".join(domain_search)
                else:
                    norm_val = normalize_value(opt_vals[0] if len(opt_vals) == 1 else opt_vals)
                    val_str = ", ".join(map(str, norm_val)) if isinstance(norm_val, list) else str(norm_val)

                options_list.append(
                    DHCPOptionItem(
                        code=opt_code,
                        name=canonical_name,
                        value=norm_val,
                        raw_str=val_str,
                    )
                )
            else:
                options_list.append(
                    DHCPOptionItem(
                        code=None,
                        name=str(opt),
                        value=str(opt),
                        raw_str=str(opt),
                    )
                )

    return DHCPOffer(
        server_ip=server_ip,
        server_mac=server_mac,
        offered_ip=offered_ip,
        subnet_mask=subnet_mask,
        prefixlen=prefixlen,
        routers=routers,
        dns_servers=dns_servers,
        domain_name=domain_name,
        domain_search=domain_search,
        lease_time=lease_time,
        renewal_time=renewal_time,
        rebinding_time=rebinding_time,
        server_id=server_id or server_ip,
        giaddr=giaddr,
        siaddr=siaddr,
        xid=xid,
        message_type=message_type,
        relay_info=relay_info,
        classless_routes=classless_routes,
        options=options_list,
        raw_summary=pkt.summary() if hasattr(pkt, "summary") else "",
    )


def build_dhcp_discover(
    mac_str: str,
    xid: int,
    broadcast: bool = True,
    param_req_list: list[int] | None = None,
    dst_ip: str = "255.255.255.255",
    dst_mac: str = "ff:ff:ff:ff:ff:ff",
    src_ip: str = "0.0.0.0",
    giaddr: str = "0.0.0.0",
    hops: int = 0,
    option_82_data: bytes | None = None,
    is_l3: bool = False,
) -> Any:
    """Build a Scapy Layer 2 or Layer 3 DHCP Discover packet with requested options and relay fields."""
    if param_req_list is None:
        param_req_list = list(DEFAULT_REQUEST_OPTIONS)

    mac_raw = mac_to_bytes(mac_str)
    chaddr = mac_raw + b"\x00" * 10
    flags = 0x8000 if broadcast else 0x0000

    dhcp_options: list[Any] = [
        ("message-type", "discover"),
        ("client_id", b"\x01" + mac_raw),
        ("param_req_list", param_req_list),
    ]

    if option_82_data:
        dhcp_options.append((82, option_82_data))

    dhcp_options.append("end")

    sport = 67 if giaddr != "0.0.0.0" else 68

    ip_pkt = (
        IP(src=src_ip, dst=dst_ip)
        / UDP(sport=sport, dport=67)
        / BOOTP(op=1, hops=hops, xid=xid, flags=flags, giaddr=giaddr, chaddr=chaddr)
        / DHCP(options=dhcp_options)
    )

    if is_l3:
        return ip_pkt

    return Ether(dst=dst_mac, src=mac_str) / ip_pkt


def send_and_receive_dhcp(
    interface: str,
    mac_str: str,
    timeout: float = 5.0,
    listen_all: bool = False,
    broadcast: bool = True,
    param_req_list: list[int] | None = None,
    servers: list[str] | None = None,
    giaddr: str | None = None,
    relay_subnet: str | None = None,
    circuit_id: str | None = None,
    remote_id: str | None = None,
) -> list[DHCPOffer]:
    """Transmit DHCP Discover (broadcast or unicast relay simulation) and collect Offer responses."""
    if not SCAPY_AVAILABLE:
        raise RuntimeError("Scapy is not installed. Please install python3-scapy via your package manager.")

    if param_req_list is None:
        param_req_list = list(DEFAULT_REQUEST_OPTIONS)

    conf.checkIPaddr = False

    local_ip = "0.0.0.0"
    try:
        local_ip = get_if_addr(interface) or "0.0.0.0"
    except (OSError, ValueError, Scapy_Exception) as err:
        LOGGER.debug("Could not determine local IP on '%s': %s", interface, err)

    option_82_data: bytes | None = None
    if circuit_id or remote_id or relay_subnet:
        option_82_data = build_option_82(
            circuit_id=circuit_id,
            remote_id=remote_id,
            link_selection=relay_subnet,
        )
        LOGGER.debug("* [opt82] Option 82 payload assembled: %s", option_82_data.hex())

    effective_giaddr = "0.0.0.0"
    hops = 0
    if giaddr:
        effective_giaddr = giaddr
        hops = 1
    elif relay_subnet:
        effective_giaddr = local_ip if local_ip != "0.0.0.0" else "0.0.0.0"
        hops = 1

    xid_base = random.randint(1, 0xFFFFFF00)
    is_l3 = is_layer3_interface(interface)
    if is_l3:
        LOGGER.debug("* [sysfs] Interface '%s' is a Layer 3 tunnel/point-to-point device (IP-level I/O)", interface)

    packets_to_send: list[Any] = []
    if servers:
        gw_ip = get_gateway_ip(interface) if not is_l3 else None
        gw_mac = get_mac_for_ip(gw_ip, interface) if gw_ip and not is_l3 else None
        if not is_l3 and gw_ip:
            LOGGER.debug("* [route] Interface default gateway: %s (MAC: %s)", gw_ip, gw_mac or "unresolved")

        for idx, server_ip in enumerate(servers):
            server_mac = "ff:ff:ff:ff:ff:ff"
            if not is_l3:
                server_mac = get_mac_for_ip(server_ip, interface) or gw_mac
                if not server_mac:
                    LOGGER.warning(
                        "Could not resolve Layer 2 MAC address for server %s or gateway %s on '%s'. "
                        "Falling back to broadcast MAC (ff:ff:ff:ff:ff:ff), which switches/routers may drop.",
                        server_ip,
                        gw_ip or "<unknown>",
                        interface,
                    )
                    server_mac = "ff:ff:ff:ff:ff:ff"
            src_ip = local_ip if local_ip != "0.0.0.0" else "0.0.0.0"
            xid = xid_base + idx
            pkt = build_dhcp_discover(
                mac_str=mac_str,
                xid=xid,
                broadcast=broadcast,
                param_req_list=param_req_list,
                dst_ip=server_ip,
                dst_mac=server_mac,
                src_ip=src_ip,
                giaddr=effective_giaddr,
                hops=hops,
                option_82_data=option_82_data,
                is_l3=is_l3,
            )
            packets_to_send.append(pkt)
    else:
        xid = xid_base
        pkt = build_dhcp_discover(
            mac_str=mac_str,
            xid=xid,
            broadcast=broadcast,
            param_req_list=param_req_list,
            dst_ip="255.255.255.255",
            dst_mac="ff:ff:ff:ff:ff:ff",
            src_ip="0.0.0.0",
            giaddr=effective_giaddr,
            hops=hops,
            option_82_data=option_82_data,
            is_l3=is_l3,
        )
        packets_to_send.append(pkt)

    for idx, p in enumerate(packets_to_send, start=1):
        target_info = f" -> {servers[idx - 1]}" if servers and idx - 1 < len(servers) else ""
        LOGGER.debug(
            "%s",
            format_packet_tree(
                p,
                direction=">",
                title=f"Outgoing DHCP Discover #{idx}{target_info} via '{interface}'",
            ),
        )

    LOGGER.info(
        "Sending DHCP Discover on '%s' (timeout: %.1fs, packets: %d, requested options: %d, L3: %s)...",
        interface,
        timeout,
        len(packets_to_send),
        len(param_req_list),
        is_l3,
    )
    if servers:
        LOGGER.info("Target DHCP Servers: %s", ", ".join(servers))
    if circuit_id:
        LOGGER.info("Option 82 Circuit-ID: '%s'", circuit_id)
    if remote_id:
        LOGGER.info("Option 82 Remote-ID: '%s'", remote_id)
    if relay_subnet:
        LOGGER.info("Option 82 Link Selection Subnet: '%s'", relay_subnet)

    start_time = time.monotonic()
    filter_exp = "udp and (port 67 or port 68)"
    LOGGER.debug("* [capture] Listening on '%s' (BPF filter: '%s', timeout: %.1fs)...", interface, filter_exp, timeout)
    if is_l3:
        import warnings

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning, message=r".*iface.*has no effect on L3.*")
            ans, _ = sr(
                packets_to_send if len(packets_to_send) > 1 else packets_to_send[0],
                timeout=timeout,
                verbose=False,
                multi=listen_all or len(packets_to_send) > 1,
                filter=filter_exp,
            )
    else:
        ans, _ = srp(
            packets_to_send if len(packets_to_send) > 1 else packets_to_send[0],
            iface=interface,
            timeout=timeout,
            verbose=False,
            multi=listen_all or len(packets_to_send) > 1,
            filter=filter_exp,
        )
    elapsed = time.monotonic() - start_time
    LOGGER.debug(
        "* [capture] Packet capture completed in %.2fs. Responses received: %d",
        elapsed,
        len(ans),
    )

    offers: list[DHCPOffer] = []
    seen_keys: set[tuple[str, str]] = set()

    for f_idx, (_, rcv) in enumerate(ans, start=1):
        offer = parse_dhcp_packet(rcv)
        LOGGER.debug(
            "%s",
            format_packet_tree(
                rcv,
                direction="<",
                title=f"Incoming DHCP Packet #{f_idx} from {offer.server_ip}",
            ),
        )

        key = (offer.server_id or offer.server_ip, offer.offered_ip)
        if key in seen_keys:
            LOGGER.debug("* [filter] Skipping duplicate offer from %s for %s", key[0], key[1])
            continue
        seen_keys.add(key)
        offers.append(offer)

    return offers


def format_offers_text(
    offers: list[DHCPOffer],
    interface: str,
    diagnostics: dict[str, Any],
    timeout: float,
    requested_options: list[int] | None = None,
    servers: list[str] | None = None,
    circuit_id: str | None = None,
    remote_id: str | None = None,
    relay_subnet: str | None = None,
) -> str:
    """Format offers into a human-readable text report."""
    lines: list[str] = []

    if servers or circuit_id or remote_id or relay_subnet:
        lines.append("=" * 70)
        lines.append("DHCP RELAY AGENT & IP-HELPER SIMULATION PARAMETERS")
        lines.append("=" * 70)
        if servers:
            lines.append(f"  Target DHCP Servers   : {', '.join(servers)}")
        if relay_subnet:
            lines.append(f"  Target Relay Subnet   : {relay_subnet}  (RFC 3527 Link Selection)")
        if circuit_id:
            lines.append(f"  Circuit-ID (Opt 82 s1): {circuit_id}  (Interface / VLAN Identifier)")
        if remote_id:
            lines.append(f"  Remote-ID  (Opt 82 s2): {remote_id}  (Relay Agent / Switch Identifier)")
        lines.append("")

    if servers:
        lines.append("Server Query Status:")
        for s in servers:
            matched_offers = [o for o in offers if (o.server_id == s or o.server_ip == s)]
            if matched_offers:
                off = matched_offers[0]
                lines.append(f"  [OK] {s:<18}: Replied (Offered: {off.offered_ip}, Server ID: {off.server_id})")
            else:
                lines.append(f"  [--] {s:<18}: No response within {timeout:.1f}s")
        lines.append("")

    if not offers:
        lines.append("=" * 70)
        lines.append(f"[FAILURE] No DHCP Offer received on '{interface}'")
        lines.append("=" * 70)
        lines.append(f"Wait duration: {timeout:.1f} seconds")
        if requested_options:
            lines.append(f"Requested DHCP Options (Option 55): {format_options_summary(requested_options)}")
        lines.append("Interface Diagnostics:")
        lines.append(f"  - Operstate : {diagnostics.get('operstate', 'unknown')}")
        lines.append(f"  - Carrier   : {diagnostics.get('carrier', 'unknown')}")
        lines.append(f"  - MAC       : {diagnostics.get('address', 'unknown')}")
        lines.append(f"  - MTU       : {diagnostics.get('mtu', 'unknown')}")
        lines.append("")
        lines.append("Troubleshooting Checklist:")
        if diagnostics.get("operstate") == "down":
            lines.append(f"  * Interface '{interface}' is administratively DOWN.")
            lines.append(f"    Run: sudo ip link set {interface} up")
        if diagnostics.get("carrier") == "0":
            lines.append(f"  * Interface '{interface}' has NO CARRIER (cable disconnected or switch port down).")
        lines.append("  * Verify VLAN tagging: Is the interface on the expected VLAN/PVID?")
        lines.append("  * Verify DHCP Relay / IP-Helper: Is 'ip helper-address <ip>' configured on the Cisco SVI?")
        lines.append(
            "  * Verify routing / firewall: Ensure UDP port 67 and 68 are permitted between client/relay and DHCP server."
        )
        lines.append("  * Verify DHCP server: Check DHCP server logs and address pool utilization.")
        lines.append("=" * 70)
        return "\n".join(lines)

    server_count = len({o.server_id or o.server_ip for o in offers})

    for idx, offer in enumerate(offers, start=1):
        lines.append("=" * 70)
        lines.append(f"DHCP OFFER #{idx} (Server: {offer.server_id or offer.server_ip})")
        lines.append("=" * 70)

        subnet_display = (
            f"{offer.subnet_mask} (/{offer.prefixlen})"
            if offer.subnet_mask and offer.prefixlen is not None
            else (offer.subnet_mask or "-")
        )
        gw_display = ", ".join(offer.routers) if offer.routers else "-"
        dns_display = ", ".join(offer.dns_servers) if offer.dns_servers else "-"
        search_display = ", ".join(offer.domain_search) if offer.domain_search else "-"

        lines.append("Network Configuration:")
        lines.append(f"  Offered IP (yiaddr)     : {offer.offered_ip}  (RFC 2131)")
        lines.append(f"  Subnet Mask (Opt 1)     : {subnet_display}  (RFC 2132)")
        lines.append(f"  Default Gateway (Opt 3) : {gw_display}  (RFC 2132)")
        lines.append(f"  DNS Servers (Opt 6)     : {dns_display}  (RFC 2132)")
        lines.append(f"  Domain Name (Opt 15)    : {offer.domain_name or '-'}  (RFC 2132)")
        lines.append(f"  Domain Search (Opt 119) : {search_display}  (RFC 3397)")
        lines.append("")

        if offer.classless_routes:
            lines.append("Classless Static Routes (RFC 3442 / VPN & Enterprise):")
            for r in offer.classless_routes:
                lines.append(f"  - {r}")
            lines.append("")

        lines.append("Lease Information:")
        lines.append(
            f"  Lease Time (Opt 51)     : {format_duration(offer.lease_time) if offer.lease_time is not None else '-'}  (RFC 2132)"
        )
        lines.append(
            f"  Renewal Time T1 (Opt 58): {format_duration(offer.renewal_time) if offer.renewal_time is not None else '-'}  (RFC 2132)"
        )
        lines.append(
            f"  Rebind Time T2 (Opt 59) : {format_duration(offer.rebinding_time) if offer.rebinding_time is not None else '-'}  (RFC 2132)"
        )
        lines.append("")

        giaddr_display = (
            f"{offer.giaddr} (Relayed via Option 82 / RFC 3046)"
            if offer.giaddr and offer.giaddr != "0.0.0.0"
            else f"{offer.giaddr or '0.0.0.0'} (Direct Layer 2)"
        )
        lines.append("Server & Layer Details:")
        lines.append(f"  DHCP Server ID (Opt 54) : {offer.server_id}  (RFC 2132)")
        lines.append(f"  Server IP (Layer 3)     : {offer.server_ip}")
        lines.append(f"  Server MAC (Layer 2)    : {offer.server_mac}")
        lines.append(f"  Relay Agent (giaddr)    : {giaddr_display}  (RFC 2131)")
        lines.append(f"  Transaction ID (XID)    : 0x{offer.xid:08x}  (RFC 2131)")
        lines.append("")

        if offer.relay_info:
            lines.append("Relay Agent Information (Option 82 / RFC 3046):")
            for sub_k, sub_v in sorted(offer.relay_info.items()):
                lines.append(f"  - {sub_k:<22}: {sub_v}")
            lines.append("")

        lines.append("Raw DHCP Options Received:")
        for opt in offer.options:
            code_str = f"[{opt.code:3d}]" if opt.code is not None else "[---]"
            rfc_suffix = ""
            if opt.code and opt.code in KNOWN_DHCP_OPTIONS:
                desc = KNOWN_DHCP_OPTIONS[opt.code][1]
                rfc_match = re.search(r"\bRFC\s+\d+\b", desc)
                if rfc_match:
                    rfc_suffix = f"  ({rfc_match.group(0)})"
            lines.append(f"  {code_str} {opt.name:<26}: {opt.raw_str}{rfc_suffix}")

        lines.append("=" * 70)

    if server_count > 1:
        lines.append("")
        lines.append(f"[WARN] Multiple ({server_count}) distinct DHCP servers replied on interface '{interface}'!")
        for o in offers:
            lines.append(f"       Server {o.server_id} (MAC: {o.server_mac}, Offered IP: {o.offered_ip})")
        lines.append("       Check for unauthorized/rogue DHCP servers or overlapping DHCP relays.")

    return "\n".join(lines)


def format_offers_json(
    offers: list[DHCPOffer],
    interface: str,
    diagnostics: dict[str, Any],
    timeout: float,
    requested_options: list[int] | None = None,
    servers: list[str] | None = None,
    circuit_id: str | None = None,
    remote_id: str | None = None,
    relay_subnet: str | None = None,
) -> str:
    """Format offers into structured JSON output."""
    payload = {
        "interface": interface,
        "diagnostics": diagnostics,
        "timeout": timeout,
        "requested_options": requested_options or DEFAULT_REQUEST_OPTIONS,
        "servers": servers or [],
        "cisco_relay_simulation": {
            "circuit_id": circuit_id,
            "remote_id": remote_id,
            "relay_subnet": relay_subnet,
        },
        "offers_count": len(offers),
        "distinct_servers_count": len({o.server_id or o.server_ip for o in offers}),
        "offers": [o.to_dict() for o in offers],
    }
    return json.dumps(payload, indent=2)


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="dhcpt",
        description="dhcpt - DHCP tester, troubleshooting, and diagnostic CLI utility.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  sudo dhcpt -i eth0                               # Standard broadcast check on eth0
  sudo dhcpt -i eth0 -s 192.0.2.1 --relay-subnet 10.50.1.1 # Relay / IP-Helper simulation (RFC 3527)
  sudo dhcpt -i eth0 --all --timeout 5             # Listen for all answering servers (detect rogue DHCP)
  sudo dhcpt -i eth0 --json                        # Structured JSON output for monitoring / scripts
  dhcpt --list-options                             # Show all supported RFC DHCP options (Option 55)
  dhcpt --list-interfaces                          # Show local network interfaces and link states

Documentation & Relay Mechanics:
  See README.md for full RFC 3527 Link Selection details and Cisco/Juniper configuration examples.
""",
    )
    parser.add_argument(
        "interface_pos",
        nargs="?",
        default=None,
        metavar="interface",
        help="Network interface to send DHCP Discover on (e.g. eth0, ens3, bond0). Alternatively use -i/--interface.",
    )
    parser.add_argument(
        "-i",
        "--interface",
        dest="interface",
        type=str,
        default=None,
        help="Network interface to send DHCP Discover on (e.g. eth0, ens3, bond0).",
    )

    relay_group = parser.add_argument_group("DHCP Relay & IP-Helper Simulation (Cisco, Juniper, Arista, Linux)")
    relay_group.add_argument(
        "-s",
        "--server",
        "--servers",
        dest="servers",
        type=str,
        default=None,
        help="Target dedicated DHCP server IP(s) or hostnames, comma-separated (e.g. -s 10.1.1.1,10.1.1.2). Simulates relay unicast forwarding.",
    )
    relay_group.add_argument(
        "--relay-subnet",
        type=str,
        default=None,
        help="Target subnet gateway IP to request pool from (RFC 3527 Option 82 Sub-option 5 Link Selection).",
    )
    relay_group.add_argument(
        "--circuit-id",
        type=str,
        default=None,
        help="Simulate Option 82 Sub-option 1 Circuit ID (e.g. 'Vlan100', 'ge-0/0/1', RFC 3046).",
    )
    relay_group.add_argument(
        "--remote-id",
        type=str,
        default=None,
        help="Simulate Option 82 Sub-option 2 Remote ID (e.g. switch hostname, MAC, or DUID, RFC 3046).",
    )
    relay_group.add_argument(
        "--giaddr",
        type=str,
        default=None,
        help="Explicitly override BOOTP Relay Agent Gateway IP (giaddr). Defaults to local IP when simulating relay.",
    )

    proto_group = parser.add_argument_group("Protocol & DHCP Packet Options")
    proto_group.add_argument(
        "-o",
        "--request-options",
        type=str,
        default=None,
        help=(
            "Additional DHCP option codes or names to request in Option 55 (PRL), comma-separated "
            "(e.g. -o 12,26,66,67 or -o hostname,tftp_server_name). Added to default RFC options."
        ),
    )
    proto_group.add_argument(
        "--clear-default-options",
        action="store_true",
        help="Do not include default RFC options; request only options explicitly passed via -o/--request-options.",
    )
    proto_group.add_argument(
        "--no-broadcast",
        action="store_true",
        help="Do not set the BOOTP broadcast flag (requests unicast Offer from server).",
    )
    proto_group.add_argument(
        "-m",
        "--mac",
        type=str,
        default=None,
        help="Override client MAC address to send (format: aa:bb:cc:dd:ee:ff).",
    )

    diag_group = parser.add_argument_group("Timing, Detection & Output Format")
    diag_group.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=5.0,
        help="Timeout in seconds to wait for DHCP Offers (default: 5.0).",
    )
    diag_group.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Listen for the full timeout duration to capture all DHCP Offers (detects rogue DHCP servers).",
    )
    diag_group.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output results in JSON format.",
    )
    diag_group.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enable detailed debug logging (socket setup, requested options, XID generation, frame decode).",
    )
    diag_group.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable informational logging.",
    )

    util_group = parser.add_argument_group("Utilities & Shell Completion")
    util_group.add_argument(
        "-l",
        "--list-interfaces",
        action="store_true",
        help="List available network interfaces and link states, then exit.",
    )
    util_group.add_argument(
        "--list-options",
        action="store_true",
        help="List known RFC DHCP options and their default request status, then exit.",
    )
    util_group.add_argument(
        "--completion",
        choices=["zsh", "bash"],
        default=None,
        help="Generate shell completion script for zsh or bash, then exit.",
    )
    util_group.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show program's version number and exit.",
    )
    return parser


def print_interfaces_table() -> None:
    """Print formatted table of available local network interfaces."""
    interfaces = get_available_interfaces()
    if not interfaces:
        print("[WARN] No network interfaces detected.")
        return

    print("Available Network Interfaces:")
    print(f"  {'Interface':<16} {'State':<10} {'Carrier':<9} {'MAC Address':<19} {'MTU':<6}")
    print("  " + "-" * 64)
    for iface in interfaces:
        print(
            f"  {iface['name']:<16} "
            f"{iface['operstate']:<10} "
            f"{iface['carrier']:<9} "
            f"{iface['address']:<19} "
            f"{iface['mtu']:<6}"
        )


def print_options_table() -> None:
    """Print formatted table of known RFC DHCP options and their default status."""
    print("Supported / Known DHCP Options (RFC Reference):")
    print(f"  {'Code':<6} {'Name':<28} {'Default':<9} {'RFC / Description'}")
    print("  " + "-" * 78)
    for code, (name, rfc) in sorted(KNOWN_DHCP_OPTIONS.items()):
        is_default = "Yes" if code in DEFAULT_REQUEST_OPTIONS else "No"
        if code == 82:
            is_default = "(Recv)"
        print(f"  {code:<6} {name:<28} {is_default:<9} {rfc}")
    print("\nTip: Pass additional options using -o/--request-options (e.g. dhcpt eth0 -o 66,67)")


def get_completion_script(shell: str) -> str | None:
    """Retrieve completion script content for zsh or bash."""
    filename = "_dhcpt" if shell == "zsh" else "dhcpt"

    # 1. Standard packaging in wheels / site-packages via importlib.resources
    try:
        import importlib.resources as pkg_resources

        traversable = pkg_resources.files("dhcpt").joinpath("completions", shell, filename)
        if traversable.is_file():
            return traversable.read_text(encoding="utf-8")
    except Exception as err:
        LOGGER.debug("importlib.resources resolution failed for %s: %s", shell, err)

    # 2. Adjacent package directory (e.g. site-packages/dhcpt/completions/...)
    candidate1 = Path(__file__).resolve().parent / "completions" / shell / filename
    if candidate1.is_file():
        try:
            return candidate1.read_text(encoding="utf-8")
        except OSError as err:
            LOGGER.debug("Reading %s failed: %s", candidate1, err)

    # 3. Repository root directory (when running directly from git checkout src/dhcpt/cli.py)
    candidate2 = Path(__file__).resolve().parent.parent.parent / "completions" / shell / filename
    if candidate2.is_file():
        try:
            return candidate2.read_text(encoding="utf-8")
        except OSError as err:
            LOGGER.debug("Reading %s failed: %s", candidate2, err)

    return None


def print_completion_script(shell: str) -> bool:
    """Print shell completion script for zsh or bash. Returns True on success."""
    script = get_completion_script(shell)
    if script:
        print(script.rstrip())
        return True
    LOGGER.error("Completion script for '%s' not found.", shell)
    return False


def _run(argv: list[str] | None = None) -> int:
    """Internal main execution entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(debug=args.debug, verbose=args.verbose)

    if args.completion:
        success = print_completion_script(args.completion)
        return 0 if success else 1

    if args.list_options:
        print_options_table()
        return 0

    if args.list_interfaces:
        print_interfaces_table()
        return 0

    server_list: list[str] | None = None
    if args.servers:
        try:
            server_list = parse_server_ips(args.servers)
        except ValueError as err:
            LOGGER.error("%s", err)
            return 2

    if args.relay_subnet:
        try:
            ipaddress.IPv4Address(args.relay_subnet.strip())
        except ValueError:
            LOGGER.error("Invalid IPv4 address for --relay-subnet: '%s'", args.relay_subnet)
            return 2

    if args.giaddr:
        try:
            ipaddress.IPv4Address(args.giaddr.strip())
        except ValueError:
            LOGGER.error("Invalid IPv4 address for --giaddr: '%s'", args.giaddr)
            return 2

    if args.timeout <= 0:
        LOGGER.error("Timeout must be a positive number greater than 0.")
        return 2

    interface = args.interface or args.interface_pos
    if not interface:
        print(
            "[ERROR] Missing required network interface. Specify with -i/--interface <name> or positional argument.",
            file=sys.stderr,
        )
        print("\nAvailable network interfaces on this system:", file=sys.stderr)
        print_interfaces_table()
        print("\nUsage example: sudo dhcpt -i <interface>", file=sys.stderr)
        print("Run 'dhcpt --help' for full options.", file=sys.stderr)
        return 2

    client_mac: str | None = None
    if args.mac:
        try:
            client_mac = validate_and_normalize_mac(args.mac)
        except ValueError as err:
            LOGGER.error("%s", err)
            return 2

    req_options: list[int] = [] if args.clear_default_options else list(DEFAULT_REQUEST_OPTIONS)
    if args.request_options:
        try:
            extra_opts = parse_requested_options(args.request_options)
        except ValueError as err:
            LOGGER.error("%s", err)
            return 2
        for opt in extra_opts:
            if opt not in req_options:
                req_options.append(opt)

    if not req_options:
        LOGGER.warning("Option 55 Parameter Request List is empty (no options requested).")

    if not SCAPY_AVAILABLE:
        LOGGER.error("Python module 'scapy' is required but not installed.")
        LOGGER.error("Install scapy via package manager: 'pip install scapy' or 'apt/dnf install python3-scapy'.")
        return 1

    diagnostics = get_interface_diagnostics(interface)

    if not diagnostics.get("exists", False):
        LOGGER.error("Interface '%s' does not exist on this host.", interface)
        print_interfaces_table()
        return 2

    is_l3 = is_layer3_interface(interface)

    if not client_mac:
        if is_l3:
            # Layer 3 point-to-point / tunnel interface (e.g. WireGuard/tun) has no hardware MAC.
            # Generate a locally administered unicast MAC for BOOTP chaddr
            client_mac = "02:" + ":".join(f"{random.randint(0, 255):02x}" for _ in range(5))
            LOGGER.debug(
                "Layer 3 interface '%s' has no hardware MAC; generated client MAC for BOOTP: %s",
                interface,
                client_mac,
            )
        else:
            try:
                client_mac = get_if_hwaddr(interface)
            except (PermissionError, OSError, ValueError, RuntimeError, Scapy_Exception) as err:
                err_str = str(err).lower()
                if (
                    isinstance(err, PermissionError)
                    or "operation not permitted" in err_str
                    or "permission denied" in err_str
                ):
                    LOGGER.error("Permission denied retrieving hardware address on '%s'.", interface)
                    LOGGER.error("Root privileges required to open Layer 2 raw network sockets (AF_PACKET).")
                    LOGGER.error("Try running with sudo: sudo dhcpt -i %s", interface)
                    return 1
                LOGGER.error("Failed to retrieve MAC address for interface '%s': %s", interface, err)
                return 1

    if not client_mac or client_mac == "00:00:00:00:00:00":
        if is_l3:
            client_mac = "02:" + ":".join(f"{random.randint(0, 255):02x}" for _ in range(5))
            LOGGER.debug(
                "Layer 3 interface '%s' had empty/zero MAC; generated client MAC for BOOTP: %s",
                interface,
                client_mac,
            )
        else:
            LOGGER.warning(
                "Interface '%s' has an empty or zero MAC address. You can specify a MAC using --mac.",
                interface,
            )

    try:
        offers = send_and_receive_dhcp(
            interface=interface,
            mac_str=client_mac,
            timeout=args.timeout,
            listen_all=args.all,
            broadcast=not args.no_broadcast,
            param_req_list=req_options,
            servers=server_list,
            giaddr=args.giaddr,
            relay_subnet=args.relay_subnet,
            circuit_id=args.circuit_id,
            remote_id=args.remote_id,
        )
    except (PermissionError, OSError, RuntimeError, Scapy_Exception) as err:
        err_str = str(err).lower()
        if isinstance(err, PermissionError) or "operation not permitted" in err_str or "permission denied" in err_str:
            LOGGER.error("Permission denied opening raw network socket on '%s'.", interface)
            LOGGER.error("Root privileges required to open Layer 2 raw network sockets (AF_PACKET).")
            LOGGER.error("Try running with sudo: sudo dhcpt -i %s", interface)
            return 1
        LOGGER.error("DHCP transaction failed on interface '%s': %s", interface, err)
        LOGGER.debug("Exception traceback:", exc_info=True)
        return 1

    if args.json:
        print(
            format_offers_json(
                offers,
                interface,
                diagnostics,
                args.timeout,
                requested_options=req_options,
                servers=server_list,
                circuit_id=args.circuit_id,
                remote_id=args.remote_id,
                relay_subnet=args.relay_subnet,
            )
        )
    else:
        print(
            format_offers_text(
                offers,
                interface,
                diagnostics,
                args.timeout,
                requested_options=req_options,
                servers=server_list,
                circuit_id=args.circuit_id,
                remote_id=args.remote_id,
                relay_subnet=args.relay_subnet,
            )
        )

    if not offers:
        return 1

    if server_list and len(server_list) > 1:
        replied_servers = {o.server_id or o.server_ip for o in offers}
        missing = [
            s
            for s in server_list
            if s not in replied_servers and not any(o.server_id == s or o.server_ip == s for o in offers)
        ]
        if missing:
            LOGGER.warning(
                "Partial response: %d/%d servers replied (%s timed out).",
                len(server_list) - len(missing),
                len(server_list),
                ", ".join(missing),
            )
            return 3

    return 0


def main(argv: list[str] | None = None) -> int:
    """Main execution entry point with graceful signal handling."""
    try:
        return _run(argv)
    except KeyboardInterrupt:
        print("\n[WARN] Interrupted by user (SIGINT).", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
