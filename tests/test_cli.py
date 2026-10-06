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
"""Unit tests for dhcpt CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import mock_open, patch

import pytest

import dhcpt.cli as dhcpt_mod
from dhcpt.cli import (
    DHCPOffer,
    DHCPOptionItem,
    DhcptLogFormatter,
    build_dhcp_discover,
    build_option_82,
    build_parser,
    decode_rfc3397_domain_search,
    format_duration,
    format_offers_json,
    format_offers_text,
    format_options_summary,
    format_packet_tree,
    get_mac_for_ip,
    is_layer3_interface,
    mac_to_bytes,
    main,
    normalize_value,
    parse_classless_routes,
    parse_dhcp_packet,
    parse_option_82,
    parse_requested_options,
    parse_server_ips,
    resolve_mac_via_arp,
    validate_and_normalize_mac,
)


def test_validate_and_normalize_mac_valid() -> None:
    assert validate_and_normalize_mac("AA:BB:CC:DD:EE:FF") == "aa:bb:cc:dd:ee:ff"
    assert validate_and_normalize_mac("00-11-22-33-44-55") == "00:11:22:33:44:55"
    assert validate_and_normalize_mac("  01:23:45:67:89:ab  ") == "01:23:45:67:89:ab"


def test_validate_and_normalize_mac_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid MAC address format"):
        validate_and_normalize_mac("invalid-mac")

    with pytest.raises(ValueError, match="Invalid MAC address format"):
        validate_and_normalize_mac("00:11:22:33:44")

    with pytest.raises(ValueError, match="Invalid MAC address format"):
        validate_and_normalize_mac("00:11:22:33:44:55:66")


def test_mac_to_bytes() -> None:
    raw = mac_to_bytes("aa:bb:cc:11:22:33")
    assert raw == b"\xaa\xbb\xcc\x11\x22\x33"
    assert len(raw) == 6


def test_format_duration() -> None:
    assert format_duration(86400) == "86400s (1d 0h 0m 0s)"
    assert format_duration(3665) == "3665s (1h 1m 5s)"
    assert format_duration(60) == "60s (1m 0s)"
    assert format_duration(42) == "42s (42s)"
    assert format_duration(-1) == "-1s"


def test_build_and_parse_option_82_cisco_simulation() -> None:
    raw_opt82 = build_option_82(
        circuit_id="Vlan50",
        remote_id="cisco-sw01",
        link_selection="10.50.1.1",
    )
    assert raw_opt82.startswith(b"\x01\x06Vlan50\x02\ncisco-sw01\x05\x04")

    parsed = parse_option_82(raw_opt82)
    assert parsed.get("circuit_id") == "Vlan50"
    assert parsed.get("remote_id") == "cisco-sw01"
    assert parsed.get("link_selection") == "10.50.1.1"


def test_build_option_82_invalid_link_selection() -> None:
    with pytest.raises(ValueError, match="Invalid IP address for link_selection"):
        build_option_82(link_selection="not-an-ip")


def test_build_option_82_oversized_suboption() -> None:
    oversized = "a" * 256
    with pytest.raises(ValueError, match="circuit_id exceeds maximum length"):
        build_option_82(circuit_id=oversized)

    with pytest.raises(ValueError, match="remote_id exceeds maximum length"):
        build_option_82(remote_id=oversized)


def test_parse_classless_routes_tuples() -> None:
    data = [(24, "10.1.2.0", "192.168.1.1"), (16, "172.16.0.0", "192.168.1.254")]
    routes = parse_classless_routes(data)
    assert routes == ["10.1.2.0/24 via 192.168.1.1", "172.16.0.0/16 via 192.168.1.254"]


def test_parse_classless_routes_scapy_strings() -> None:
    data = ["10.0.0.0/8:10.99.0.1", "192.168.50.0/24:10.99.0.254"]
    routes = parse_classless_routes(data)
    assert routes == ["10.0.0.0/8 via 10.99.0.1", "192.168.50.0/24 via 10.99.0.254"]


def test_parse_classless_routes_wire_bytes() -> None:
    data = bytes([8, 10, 192, 168, 1, 1, 12, 172, 16, 192, 168, 1, 254])
    routes = parse_classless_routes(data)
    assert routes == ["10.0.0.0/8 via 192.168.1.1", "172.16.0.0/12 via 192.168.1.254"]


def test_parse_classless_routes_malformed_mask() -> None:
    # Mask length 33 is invalid for IPv4 -> should abort parsing cleanly without crashing
    data = bytes([33, 10, 192, 168, 1, 1])
    assert parse_classless_routes(data) == []


def test_parse_requested_options() -> None:
    assert parse_requested_options("66, 67") == [66, 67]
    assert parse_requested_options("hostname, tftp_server_name, 43") == [12, 66, 43]
    assert parse_requested_options("routes, vpn_routes") == [121]

    with pytest.raises(ValueError, match="DHCP option code must be between 1 and 254"):
        parse_requested_options("0, 66")

    with pytest.raises(ValueError, match="DHCP option code must be between 1 and 254"):
        parse_requested_options("255")

    with pytest.raises(ValueError, match="Unknown DHCP option name"):
        parse_requested_options("totally_unknown_dhcp_option")


def test_parse_server_ips() -> None:
    servers = parse_server_ips("10.10.1.1, 10.10.1.2, 10.10.1.3 10.10.1.4")
    assert servers == ["10.10.1.1", "10.10.1.2", "10.10.1.3", "10.10.1.4"]

    with patch("socket.gethostbyname", return_value="192.0.2.1"):
        resolved = parse_server_ips("dhcp1.example.com, 10.1.1.1")
        assert resolved == ["192.0.2.1", "10.1.1.1"]

    with pytest.raises(ValueError, match="Invalid server IP address or unresolvable hostname"):
        parse_server_ips("10.10.1.1, invalid_unresolvable_hostname_xyz_123")


def test_resolve_mac_via_arp_success() -> None:
    from unittest.mock import MagicMock

    mock_rcv = MagicMock()
    mock_rcv.haslayer.return_value = True
    mock_rcv.__getitem__.return_value.hwsrc = "52:54:00:12:34:56"

    with patch.object(dhcpt_mod, "srp", return_value=([(None, mock_rcv)], [])):
        resolved = resolve_mac_via_arp("10.0.0.1", "eth0")
        assert resolved == "52:54:00:12:34:56"


def test_resolve_mac_via_arp_failure() -> None:
    with patch.object(dhcpt_mod, "srp", return_value=([], [])):
        resolved = resolve_mac_via_arp("10.0.0.1", "eth0")
        assert resolved is None


def test_get_mac_for_ip_cached() -> None:
    mock_arp_data = "IP address       HW type     Flags       HW address            Mask     Device\n10.0.0.1        0x1         0x2         52:54:00:aa:bb:cc     *        eth0\n"
    with patch("builtins.open", mock_open(read_data=mock_arp_data)):
        mac = get_mac_for_ip("10.0.0.1", "eth0", resolve_active=False)
        assert mac == "52:54:00:aa:bb:cc"


def test_get_mac_for_ip_fallback_active() -> None:
    with (
        patch("builtins.open", side_effect=OSError("No such file")),
        patch.object(dhcpt_mod, "resolve_mac_via_arp", return_value="52:54:00:dd:ee:ff"),
    ):
        mac = get_mac_for_ip("10.0.0.1", "eth0", resolve_active=True)
        assert mac == "52:54:00:dd:ee:ff"


def test_format_options_summary() -> None:
    summary = format_options_summary([1, 3, 6, 121])
    assert "1 (subnet_mask)" in summary
    assert "3 (router)" in summary
    assert "121 (classless_static_routes)" in summary


def test_normalize_value() -> None:
    assert normalize_value(b"test string") == "test string"
    assert normalize_value(b"\xff\xfe") == "fffe"
    assert normalize_value(["192.168.1.1", b"dns.local"]) == ["192.168.1.1", "dns.local"]
    assert normalize_value(12345) == 12345


def test_build_dhcp_discover_standard() -> None:
    pkt = build_dhcp_discover("00:11:22:33:44:55", xid=0x12345678, broadcast=True)
    assert pkt[dhcpt_mod.BOOTP].xid == 0x12345678
    assert pkt[dhcpt_mod.BOOTP].flags == 0x8000
    assert pkt[dhcpt_mod.BOOTP].chaddr[:6] == b"\x00\x11\x22\x33\x44\x55"
    assert pkt[dhcpt_mod.UDP].sport == 68
    assert pkt[dhcpt_mod.UDP].dport == 67


def test_build_dhcp_discover_cisco_relay_simulation() -> None:
    opt82_raw = build_option_82(circuit_id="Vlan100", remote_id="cisco-sw01")
    pkt = build_dhcp_discover(
        mac_str="00:11:22:33:44:55",
        xid=0x12345678,
        dst_ip="10.10.1.1",
        dst_mac="00:aa:bb:cc:dd:ee",
        src_ip="10.0.0.20",
        giaddr="10.50.1.1",
        hops=1,
        option_82_data=opt82_raw,
    )
    assert pkt[dhcpt_mod.IP].dst == "10.10.1.1"
    assert pkt[dhcpt_mod.IP].src == "10.0.0.20"
    assert pkt[dhcpt_mod.UDP].sport == 67
    assert pkt[dhcpt_mod.UDP].dport == 67
    assert pkt[dhcpt_mod.BOOTP].giaddr == "10.50.1.1"
    assert pkt[dhcpt_mod.BOOTP].hops == 1

    options = dict(pkt[dhcpt_mod.DHCP].options[:-1])
    assert options.get(82) == opt82_raw


def test_parse_dhcp_packet() -> None:
    ether = dhcpt_mod.Ether(src="00:aa:bb:cc:dd:ee", dst="ff:ff:ff:ff:ff:ff")
    ip = dhcpt_mod.IP(src="192.168.1.1", dst="255.255.255.255")
    udp = dhcpt_mod.UDP(sport=67, dport=68)
    bootp = dhcpt_mod.BOOTP(
        xid=0x55AA55AA,
        yiaddr="192.168.1.150",
        siaddr="192.168.1.1",
        giaddr="0.0.0.0",
    )
    dhcp = dhcpt_mod.DHCP(
        options=[
            ("message-type", "offer"),
            ("server_id", "192.168.1.1"),
            ("subnet_mask", "255.255.255.0"),
            ("router", "192.168.1.1"),
            ("name_server", "1.1.1.1", "8.8.8.8"),
            ("domain", "corp.internal"),
            ("domain_search", "corp.internal", "example.com"),
            ("lease_time", 86400),
            ("renewal_time", 43200),
            ("rebinding_time", 75600),
            ("relay_agent_information", b"\x01\x04eth1"),
            ("classless_static_routes", [(24, "10.0.1.0", "192.168.1.1")]),
            "end",
        ]
    )
    pkt = ether / ip / udp / bootp / dhcp

    offer = parse_dhcp_packet(pkt)
    assert offer.server_ip == "192.168.1.1"
    assert offer.server_mac == "00:aa:bb:cc:dd:ee"
    assert offer.offered_ip == "192.168.1.150"
    assert offer.subnet_mask == "255.255.255.0"
    assert offer.prefixlen == 24
    assert offer.routers == ["192.168.1.1"]
    assert offer.dns_servers == ["1.1.1.1", "8.8.8.8"]
    assert offer.domain_name == "corp.internal"
    assert offer.domain_search == ["corp.internal", "example.com"]
    assert offer.lease_time == 86400
    assert offer.renewal_time == 43200
    assert offer.rebinding_time == 75600
    assert offer.server_id == "192.168.1.1"
    assert offer.xid == 0x55AA55AA
    assert offer.message_type == "offer"
    assert offer.relay_info.get("circuit_id") == "eth1"
    assert offer.classless_routes == ["10.0.1.0/24 via 192.168.1.1"]


def test_is_layer3_interface() -> None:
    from pathlib import Path

    with patch.object(Path, "exists", return_value=True), patch.object(Path, "read_text", return_value="65534\n"):
        assert is_layer3_interface("vpn0") is True

    with patch.object(Path, "exists", return_value=True), patch.object(Path, "read_text", return_value="1\n"):
        assert is_layer3_interface("eth0") is False

    with patch.object(Path, "exists", return_value=False):
        assert is_layer3_interface("nonexistent") is False


def test_build_dhcp_discover_layer3() -> None:
    pkt = build_dhcp_discover(
        mac_str="02:11:22:33:44:55",
        xid=0x12345678,
        dst_ip="198.51.100.1",
        src_ip="192.0.2.100",
        giaddr="192.0.2.100",
        hops=1,
        is_l3=True,
    )
    assert not pkt.haslayer(dhcpt_mod.Ether)
    assert pkt.haslayer(dhcpt_mod.IP)
    assert pkt.haslayer(dhcpt_mod.UDP)
    assert pkt.haslayer(dhcpt_mod.BOOTP)
    assert pkt.haslayer(dhcpt_mod.DHCP)
    assert pkt[dhcpt_mod.IP].dst == "198.51.100.1"
    assert pkt[dhcpt_mod.IP].src == "192.0.2.100"
    assert pkt[dhcpt_mod.BOOTP].giaddr == "192.0.2.100"
    assert pkt[dhcpt_mod.BOOTP].hops == 1


def test_parse_dhcp_packet_layer3_without_ether() -> None:
    ip = dhcpt_mod.IP(src="198.51.100.1", dst="192.0.2.100")
    udp = dhcpt_mod.UDP(sport=67, dport=67)
    bootp = dhcpt_mod.BOOTP(op=2, xid=0x1234, yiaddr="10.50.1.150", giaddr="192.0.2.100")
    dhcp = dhcpt_mod.DHCP(options=[("message-type", "offer"), ("server_id", "198.51.100.1"), "end"])
    pkt = ip / udp / bootp / dhcp

    offer = parse_dhcp_packet(pkt)
    assert offer.server_ip == "198.51.100.1"
    assert offer.server_mac == "n/a (Layer 3)"
    assert offer.offered_ip == "10.50.1.150"


def test_send_and_receive_dhcp_layer3_uses_sr() -> None:
    from unittest.mock import MagicMock

    mock_rcv = MagicMock()
    mock_rcv.haslayer.side_effect = lambda layer: layer in (dhcpt_mod.IP, dhcpt_mod.BOOTP, dhcpt_mod.DHCP)
    mock_rcv.__getitem__.side_effect = lambda layer: {
        dhcpt_mod.IP: MagicMock(src="10.0.0.1"),
        dhcpt_mod.BOOTP: MagicMock(yiaddr="10.0.0.100", giaddr="10.0.0.2", siaddr="10.0.0.1", xid=123),
        dhcpt_mod.DHCP: MagicMock(options=[("message-type", "offer"), ("server_id", "10.0.0.1"), "end"]),
    }[layer]

    with (
        patch.object(dhcpt_mod, "is_layer3_interface", return_value=True),
        patch.object(dhcpt_mod, "get_if_addr", return_value="10.0.0.2"),
        patch.object(dhcpt_mod, "sr", return_value=([(None, mock_rcv)], [])) as mock_sr,
        patch.object(dhcpt_mod, "srp") as mock_srp,
    ):
        offers = dhcpt_mod.send_and_receive_dhcp(
            interface="vpn0",
            mac_str="02:11:22:33:44:55",
            servers=["10.0.0.1"],
        )
        assert len(offers) == 1
        assert mock_sr.called
        assert not mock_srp.called


def test_send_and_receive_dhcp_interface_not_found_fallback() -> None:
    from unittest.mock import MagicMock

    mock_rcv = MagicMock()
    mock_rcv.haslayer.side_effect = lambda layer: layer in (dhcpt_mod.IP, dhcpt_mod.BOOTP, dhcpt_mod.DHCP)
    mock_rcv.__getitem__.side_effect = lambda layer: {
        dhcpt_mod.IP: MagicMock(src="10.0.0.1"),
        dhcpt_mod.BOOTP: MagicMock(yiaddr="10.0.0.100", giaddr="0.0.0.0", siaddr="10.0.0.1", xid=123),
        dhcpt_mod.DHCP: MagicMock(options=[("message-type", "offer"), ("server_id", "10.0.0.1"), "end"]),
    }[layer]

    with (
        patch.object(dhcpt_mod, "is_layer3_interface", return_value=True),
        patch.object(dhcpt_mod, "get_if_addr", side_effect=ValueError("Interface 'nonexistent0' not found !")),
        patch.object(dhcpt_mod, "sr", return_value=([(None, mock_rcv)], [])) as mock_sr,
        patch.object(dhcpt_mod, "srp") as mock_srp,
    ):
        offers = dhcpt_mod.send_and_receive_dhcp(
            interface="nonexistent0",
            mac_str="02:11:22:33:44:55",
            servers=["10.0.0.1"],
        )
        assert len(offers) == 1
        assert mock_sr.called
        assert not mock_srp.called


def test_send_and_receive_dhcp_layer2_uses_srp() -> None:
    from unittest.mock import MagicMock

    mock_rcv = MagicMock()
    mock_rcv.haslayer.side_effect = lambda layer: layer in (dhcpt_mod.IP, dhcpt_mod.BOOTP, dhcpt_mod.DHCP)
    mock_rcv.__getitem__.side_effect = lambda layer: {
        dhcpt_mod.IP: MagicMock(src="192.168.1.1"),
        dhcpt_mod.BOOTP: MagicMock(yiaddr="192.168.1.100", giaddr="0.0.0.0", siaddr="192.168.1.1", xid=123),
        dhcpt_mod.DHCP: MagicMock(options=[("message-type", "offer"), ("server_id", "192.168.1.1"), "end"]),
    }[layer]

    with (
        patch.object(dhcpt_mod, "is_layer3_interface", return_value=False),
        patch.object(dhcpt_mod, "get_if_addr", return_value="192.168.1.50"),
        patch.object(dhcpt_mod, "srp", return_value=([(None, mock_rcv)], [])) as mock_srp,
        patch.object(dhcpt_mod, "sr") as mock_sr,
    ):
        offers = dhcpt_mod.send_and_receive_dhcp(
            interface="eth0",
            mac_str="00:11:22:33:44:55",
            timeout=2.0,
        )
        assert len(offers) == 1
        assert mock_srp.called
        assert not mock_sr.called


def test_decode_rfc3397_domain_search() -> None:
    # Standard labels: 'example.com' and 'corp.lan'
    raw = b"\x07example\x03com\x00\x04corp\x03lan\x00"
    domains = decode_rfc3397_domain_search(raw)
    assert domains == ["example.com", "corp.lan"]

    # Compressed domain pointers: 'eng.example.com' then 'mkt.<ptr to example.com>'
    compressed_raw = b"\x03eng\x07example\x03com\x00\x03mkt\xc0\x04"
    compressed_domains = decode_rfc3397_domain_search(compressed_raw)
    assert compressed_domains == ["eng.example.com", "mkt.example.com"]


def test_format_offers_text_single_with_routes() -> None:
    offer = DHCPOffer(
        server_ip="10.0.0.1",
        server_mac="00:11:22:33:44:55",
        offered_ip="10.0.0.100",
        subnet_mask="255.255.0.0",
        prefixlen=16,
        routers=["10.0.0.1"],
        dns_servers=["10.0.0.2"],
        domain_name="test.local",
        lease_time=3600,
        server_id="10.0.0.1",
        xid=0x1234,
        classless_routes=["10.100.0.0/16 via 10.0.0.254"],
        options=[DHCPOptionItem(code=1, name="subnet_mask", value="255.255.0.0", raw_str="255.255.0.0")],
    )
    text = format_offers_text([offer], "eth0", {"operstate": "up"}, 5.0, requested_options=[1, 3, 121])
    assert "DHCP OFFER #1 (Server: 10.0.0.1)" in text
    assert "Offered IP (yiaddr)" in text
    assert "10.0.0.100" in text
    assert "(RFC 2131)" in text
    assert "(RFC 2132)" in text
    assert "255.255.0.0 (/16)" in text
    assert "10.0.0.1" in text
    assert "3600s (1h 0m 0s)" in text
    assert "Classless Static Routes (RFC 3442 / VPN & Enterprise):" in text
    assert "10.100.0.0/16 via 10.0.0.254" in text
    assert "Multiple" not in text


def test_format_packet_tree_l2() -> None:
    pkt = build_dhcp_discover(
        mac_str="00:11:22:33:44:55",
        xid=0x12345678,
        broadcast=True,
        param_req_list=[1, 3, 6],
        dst_ip="255.255.255.255",
        dst_mac="ff:ff:ff:ff:ff:ff",
        is_l3=False,
    )
    tree = format_packet_tree(pkt, direction=">", title="Outgoing Test Discover")
    assert "> Outgoing Test Discover" in tree
    assert "Ethernet : 00:11:22:33:44:55 -> ff:ff:ff:ff:ff:ff" in tree
    assert "IPv4     : 0.0.0.0 -> 255.255.255.255 (Broadcast)" in tree
    assert "UDP      : 68 -> 67" in tree
    assert "BOOTP    : op=1 (BOOTREQUEST), xid=0x12345678" in tree
    assert "DHCP" in tree
    assert "Option 53 (Message Type): Discover" in tree


def test_format_packet_tree_l3() -> None:
    pkt = build_dhcp_discover(
        mac_str="00:11:22:33:44:55",
        xid=0x12345678,
        broadcast=False,
        param_req_list=[1, 3],
        dst_ip="10.1.1.1",
        src_ip="10.50.1.20",
        giaddr="10.50.1.20",
        is_l3=True,
    )
    tree = format_packet_tree(pkt, direction=">", title="Outgoing L3 Discover")
    assert "> Outgoing L3 Discover" in tree
    assert "Ethernet" not in tree
    assert "IPv4     : 10.50.1.20 -> 10.1.1.1 (Unicast)" in tree
    assert "UDP      : 67 -> 67" in tree


def test_dhcpt_log_formatter() -> None:
    import logging

    formatter = DhcptLogFormatter()
    rec_debug_star = logging.LogRecord("test", logging.DEBUG, "path", 10, "* [dns] Resolved", (), None)
    assert formatter.format(rec_debug_star) == "* [dns] Resolved"

    rec_debug_plain = logging.LogRecord("test", logging.DEBUG, "path", 10, "plain message", (), None)
    assert formatter.format(rec_debug_plain) == "* plain message"

    rec_info_star = logging.LogRecord("test", logging.INFO, "path", 10, "* Interface: eth0", (), None)
    assert formatter.format(rec_info_star) == "* Interface: eth0"

    rec_info_send = logging.LogRecord("test", logging.INFO, "path", 10, "> DHCPDISCOVER #1", (), None)
    assert formatter.format(rec_info_send) == "> DHCPDISCOVER #1"

    rec_info_recv = logging.LogRecord("test", logging.INFO, "path", 10, "< DHCPOFFER #1", (), None)
    assert formatter.format(rec_info_recv) == "< DHCPOFFER #1"

    rec_info_plain = logging.LogRecord("test", logging.INFO, "path", 10, "info message", (), None)
    assert formatter.format(rec_info_plain) == "* info message"

    rec_warn = logging.LogRecord("test", logging.WARNING, "path", 10, "warning message", (), None)
    assert formatter.format(rec_warn) == "* [WARN] warning message"

    rec_err = logging.LogRecord("test", logging.ERROR, "path", 10, "error message", (), None)
    assert formatter.format(rec_err) == "dhcpt: error: error message"


def test_format_offers_text_cisco_relay_simulation_header() -> None:
    offer = DHCPOffer(
        server_ip="10.10.1.1",
        server_mac="00:11:22:33:44:55",
        offered_ip="10.50.1.100",
        server_id="10.10.1.1",
    )
    text = format_offers_text(
        [offer],
        interface="eth0",
        diagnostics={"operstate": "up"},
        timeout=5.0,
        servers=["10.10.1.1", "10.10.1.2"],
        circuit_id="Vlan50",
        remote_id="cisco-sw01",
        relay_subnet="10.50.1.1",
    )
    assert "DHCP RELAY AGENT & IP-HELPER SIMULATION PARAMETERS" in text
    assert "Target DHCP Servers   : 10.10.1.1, 10.10.1.2" in text
    assert "Target Relay Subnet   : 10.50.1.1" in text
    assert "Circuit-ID (Opt 82 s1): Vlan50" in text
    assert "Remote-ID  (Opt 82 s2): cisco-sw01" in text
    assert "Server Query Status:" in text
    assert "[OK] 10.10.1.1" in text
    assert "[--] 10.10.1.2" in text


def test_format_offers_text_multiple_servers() -> None:
    offer1 = DHCPOffer(
        server_ip="192.168.1.1",
        server_mac="00:11:22:33:44:01",
        offered_ip="192.168.1.50",
        server_id="192.168.1.1",
    )
    offer2 = DHCPOffer(
        server_ip="192.168.1.254",
        server_mac="00:11:22:33:44:fe",
        offered_ip="192.168.1.60",
        server_id="192.168.1.254",
    )
    text = format_offers_text([offer1, offer2], "eth0", {"operstate": "up"}, 5.0)
    assert "[WARN] Multiple (2) distinct DHCP servers replied" in text
    assert "Server 192.168.1.1" in text
    assert "Server 192.168.1.254" in text


def test_format_offers_text_failure() -> None:
    diag = {
        "exists": True,
        "operstate": "down",
        "carrier": "0",
        "address": "00:11:22:33:44:55",
        "mtu": "1500",
    }
    text = format_offers_text([], "eth0", diag, 5.0, requested_options=[1, 3, 6])
    assert "dhcpt: timeout after 5.0s waiting for DHCP offers on interface 'eth0'" in text
    assert "interface 'eth0' is administratively DOWN" in text
    assert "Troubleshooting Checklist:" not in text

    # Also test with specific servers
    text_servers = format_offers_text([], "eth0", {"operstate": "up", "carrier": "1"}, 3.0, servers=["10.1.1.1"])
    assert "dhcpt: timeout after 3.0s waiting for DHCP offers from 10.1.1.1 on interface 'eth0'" in text_servers


def test_format_offers_json() -> None:
    offer = DHCPOffer(
        server_ip="192.168.1.1",
        server_mac="00:11:22:33:44:55",
        offered_ip="192.168.1.100",
        server_id="192.168.1.1",
        xid=0x12345678,
        classless_routes=["10.0.0.0/8 via 192.168.1.1"],
    )
    json_str = format_offers_json(
        [offer],
        "eth0",
        {"operstate": "up"},
        5.0,
        requested_options=[1, 3, 121],
        servers=["192.168.1.1"],
        circuit_id="Vlan50",
    )
    data = json.loads(json_str)
    assert data["interface"] == "eth0"
    assert data["offers_count"] == 1
    assert data["distinct_servers_count"] == 1
    assert data["servers"] == ["192.168.1.1"]
    assert data["cisco_relay_simulation"]["circuit_id"] == "Vlan50"
    assert data["requested_options"] == [1, 3, 121]
    assert data["offers"][0]["offered_ip"] == "192.168.1.100"
    assert data["offers"][0]["xid_hex"] == "0x12345678"
    assert data["offers"][0]["classless_routes"] == ["10.0.0.0/8 via 192.168.1.1"]


def test_build_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "eth0",
            "-s",
            "10.1.1.1,10.1.1.2",
            "--circuit-id",
            "Vlan50",
            "--remote-id",
            "sw01",
            "--relay-subnet",
            "10.50.1.1",
            "-t",
            "10",
            "-o",
            "66,67",
            "--debug",
            "--all",
            "--json",
        ]
    )
    assert args.interface_pos == "eth0"
    assert (args.interface or args.interface_pos) == "eth0"
    assert args.servers == "10.1.1.1,10.1.1.2"
    assert args.circuit_id == "Vlan50"
    assert args.remote_id == "sw01"
    assert args.relay_subnet == "10.50.1.1"
    assert args.timeout == 10.0
    assert args.request_options == "66,67"
    assert args.debug is True
    assert args.all is True
    assert args.json is True

    args_flag = parser.parse_args(["-i", "ens3"])
    assert args_flag.interface == "ens3"
    assert (args_flag.interface or args_flag.interface_pos) == "ens3"

    args_verbose = parser.parse_args(["eth0", "-vv"])
    assert args_verbose.verbose == 2

    help_text = parser.format_help()
    assert "DHCP Relay & IP-Helper Simulation" in help_text
    assert "Protocol & DHCP Packet Options" in help_text
    assert "Timing, Detection & Output Format" in help_text
    assert "Utilities & Shell Completion" in help_text


def test_setup_logging_levels() -> None:
    import logging

    dhcpt_mod.setup_logging(verbose=0, debug=False)
    assert dhcpt_mod.LOGGER.level == logging.WARNING

    dhcpt_mod.setup_logging(verbose=1, debug=False)
    assert dhcpt_mod.LOGGER.level == logging.INFO

    dhcpt_mod.setup_logging(verbose=2, debug=False)
    assert dhcpt_mod.LOGGER.level == logging.DEBUG

    dhcpt_mod.setup_logging(verbose=0, debug=True)
    assert dhcpt_mod.LOGGER.level == logging.DEBUG


def test_main_list_interfaces(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(
        dhcpt_mod,
        "get_available_interfaces",
        return_value=[
            {"name": "eth0", "operstate": "up", "carrier": "1", "address": "00:11:22:33:44:55", "mtu": "1500"}
        ],
    ):
        exit_code = main(["--list-interfaces"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Available Network Interfaces:" in captured.out
        assert "eth0" in captured.out


def test_main_list_options(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--list-options"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Supported / Known DHCP Options (RFC Reference):" in captured.out
    assert "classless_static_routes" in captured.out
    assert "RFC 3442" in captured.out
    assert "router" in captured.out


def test_main_missing_interface(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "Missing required network interface" in captured.err
    assert "Available network interfaces on this system:" in captured.err


def test_main_invalid_timeout(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["-i", "eth0", "-t", "0"])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "Timeout must be a positive number greater than 0" in captured.err

    exit_code_neg = main(["-i", "eth0", "-t", "-5"])
    assert exit_code_neg == 2


def test_main_with_interface_flag(capsys: pytest.CaptureFixture[str]) -> None:
    mock_offer = DHCPOffer(
        server_ip="192.168.1.1",
        server_mac="00:11:22:33:44:55",
        offered_ip="192.168.1.100",
        server_id="192.168.1.1",
    )
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "up"}),
        patch.object(dhcpt_mod, "get_if_hwaddr", return_value="00:11:22:33:44:55"),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", return_value=[mock_offer]),
    ):
        exit_code = main(["-i", "eth0"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "DHCP OFFER #1" in captured.out


def test_main_permission_denied(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "up"}),
        patch.object(dhcpt_mod, "get_if_hwaddr", return_value="00:11:22:33:44:55"),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", side_effect=PermissionError("Operation not permitted")),
    ):
        exit_code = main(["-i", "eth0"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Permission denied opening raw network socket on 'eth0'" in captured.err
        assert "Root privileges required to open Layer 2 raw network sockets" in captured.err


def test_main_permission_denied_layer3(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "up"}),
        patch.object(dhcpt_mod, "is_layer3_interface", return_value=True),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", side_effect=PermissionError("Operation not permitted")),
    ):
        exit_code = main(["-i", "vpn0", "-s", "10.1.1.1"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Permission denied opening raw network socket on 'vpn0'" in captured.err
        assert "Root privileges (or CAP_NET_RAW) required to open Layer 3 raw network sockets (AF_INET)" in captured.err
        assert "Try running with sudo: sudo dhcpt -i vpn0 -s 10.1.1.1" in captured.err


def test_main_interface_does_not_exist(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": False}),
        patch.object(dhcpt_mod, "print_interfaces_table"),
    ):
        exit_code = main(["-i", "nonexistent0"])
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "Interface 'nonexistent0' does not exist on this host." in captured.err


def test_main_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert f"dhcpt {dhcpt_mod.__version__}" in captured.out


def test_main_keyboard_interrupt(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("dhcpt.cli._run", side_effect=KeyboardInterrupt):
        exit_code = main(["-i", "eth0"])
        assert exit_code == 130
        captured = capsys.readouterr()
        assert "Interrupted by user (SIGINT)" in captured.err


def test_main_invalid_mac(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["-i", "eth0", "--mac", "invalid-mac"])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "Invalid MAC address format" in captured.err


def test_main_invalid_server_ip(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["-i", "eth0", "-s", "invalid_ip"])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "Invalid server IP address or unresolvable hostname" in captured.err


def test_main_invalid_target_gateway(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["-i", "eth0", "--target-gateway", "not-an-ip"])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "Invalid IPv4 address for --target-gateway" in captured.err


def test_main_invalid_request_options(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["-i", "eth0", "-o", "invalid_option_xyz"])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "Unknown DHCP option name" in captured.err


def test_main_cisco_relay_simulation_flow(capsys: pytest.CaptureFixture[str]) -> None:
    mock_offer1 = DHCPOffer(
        server_ip="10.1.1.1",
        server_mac="00:11:22:33:44:55",
        offered_ip="10.50.1.150",
        server_id="10.1.1.1",
    )
    mock_offer2 = DHCPOffer(
        server_ip="10.1.1.2",
        server_mac="00:11:22:33:44:56",
        offered_ip="10.50.1.151",
        server_id="10.1.1.2",
    )
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "up"}),
        patch.object(dhcpt_mod, "get_if_hwaddr", return_value="00:11:22:33:44:55"),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", return_value=[mock_offer1, mock_offer2]) as mock_send,
    ):
        exit_code = main(
            [
                "-i",
                "eth0",
                "-s",
                "10.1.1.1,10.1.1.2",
                "--circuit-id",
                "Vlan50",
                "--remote-id",
                "sw-cisco01",
                "--relay-subnet",
                "10.50.1.1",
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "DHCP RELAY AGENT & IP-HELPER SIMULATION PARAMETERS" in captured.out
        assert "Target DHCP Servers   : 10.1.1.1, 10.1.1.2" in captured.out
        assert "Circuit-ID (Opt 82 s1): Vlan50" in captured.out

        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs.get("servers") == ["10.1.1.1", "10.1.1.2"]
        assert call_kwargs.get("circuit_id") == "Vlan50"
        assert call_kwargs.get("remote_id") == "sw-cisco01"
        assert call_kwargs.get("relay_subnet") == "10.50.1.1"


def test_main_cisco_relay_simulation_target_gateway(capsys: pytest.CaptureFixture[str]) -> None:
    mock_offer = DHCPOffer(
        server_ip="10.1.1.1",
        server_mac="00:11:22:33:44:55",
        offered_ip="10.50.1.150",
        server_id="10.1.1.1",
    )
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "up"}),
        patch.object(dhcpt_mod, "get_if_hwaddr", return_value="00:11:22:33:44:55"),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", return_value=[mock_offer]) as mock_send,
    ):
        exit_code = main(["-i", "eth0", "-s", "10.1.1.1", "--target-gateway", "10.50.1.1"])
        assert exit_code == 0
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs.get("relay_subnet") == "10.50.1.1"


def test_main_server_and_dhcp_server_flags(capsys: pytest.CaptureFixture[str]) -> None:
    mock_offer = DHCPOffer(
        server_ip="10.1.1.1",
        server_mac="00:11:22:33:44:55",
        offered_ip="10.50.1.150",
        server_id="10.1.1.1",
    )
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "up"}),
        patch.object(dhcpt_mod, "get_if_hwaddr", return_value="00:11:22:33:44:55"),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", return_value=[mock_offer]) as mock_send,
    ):
        exit_code = main(["-i", "eth0", "--dhcp-server", "10.1.1.1", "--target-gateway", "10.50.1.1"])
        assert exit_code == 0
        assert mock_send.call_args.kwargs.get("servers") == ["10.1.1.1"]

        exit_code2 = main(["-i", "eth0", "--server", "10.2.2.2", "--target-gateway", "10.50.1.1"])
        assert exit_code2 == 0
        assert mock_send.call_args.kwargs.get("servers") == ["10.2.2.2"]


def test_main_completion_zsh(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--completion", "zsh"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "#compdef dhcpt" in captured.out
    assert "_dhcpt_servers" in captured.out
    assert "--install-skill" in captured.out
    assert "--force" in captured.out


def test_main_completion_bash(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--completion", "bash"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "_dhcpt_bash" in captured.out
    assert "complete -F _dhcpt_bash dhcpt" in captured.out
    assert "--install-skill" in captured.out
    assert "--force" in captured.out
    assert "DHCPT_SERVER_PATTERNS" in captured.out


def test_main_completion_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(dhcpt_mod, "get_completion_script", return_value=None):
        exit_code = main(["--completion", "zsh"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Completion script for 'zsh' not found" in captured.err


def test_main_no_offers(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "down"}),
        patch.object(dhcpt_mod, "get_if_hwaddr", return_value="00:11:22:33:44:55"),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", return_value=[]),
    ):
        exit_code = main(["-i", "eth0"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "dhcpt: timeout after" in captured.err
        assert "administratively DOWN" in captured.err


def test_main_multi_server_partial_failure(capsys: pytest.CaptureFixture[str]) -> None:
    mock_offer = DHCPOffer(
        server_ip="10.1.1.1",
        server_mac="00:11:22:33:44:55",
        offered_ip="10.50.1.150",
        server_id="10.1.1.1",
    )
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "up"}),
        patch.object(dhcpt_mod, "get_if_hwaddr", return_value="00:11:22:33:44:55"),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", return_value=[mock_offer]),
    ):
        exit_code = main(["-i", "eth0", "-s", "10.1.1.1,10.1.1.2"])
        assert exit_code == 3
        captured = capsys.readouterr()
        assert "10.1.1.2 timed out" in captured.err


def test_main_multi_server_all_success(capsys: pytest.CaptureFixture[str]) -> None:
    mock_offer1 = DHCPOffer(
        server_ip="10.1.1.1",
        server_mac="00:11:22:33:44:55",
        offered_ip="10.50.1.150",
        server_id="10.1.1.1",
    )
    mock_offer2 = DHCPOffer(
        server_ip="10.1.1.2",
        server_mac="00:11:22:33:44:56",
        offered_ip="10.50.1.151",
        server_id="10.1.1.2",
    )
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "up"}),
        patch.object(dhcpt_mod, "get_if_hwaddr", return_value="00:11:22:33:44:55"),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", return_value=[mock_offer1, mock_offer2]),
    ):
        exit_code = main(["-i", "eth0", "-s", "10.1.1.1,10.1.1.2"])
        assert exit_code == 0


def test_parser_epilog_references_man_and_url() -> None:
    parser = dhcpt_mod.build_parser()
    epilog = parser.epilog or ""
    assert "man dhcpt" in epilog
    assert "https://github.com/epicade/dhcpt" in epilog
    assert "README.md" not in epilog


def test_get_skill_content() -> None:
    content = dhcpt_mod.get_skill_content()
    assert content is not None
    assert "name: dhcpt" in content
    assert "dhcpt - DHCP Testing & Troubleshooting Guide" in content


def test_install_agent_skill_single(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    exit_code = dhcpt_mod.install_agent_skill("gemini")
    assert exit_code == 0
    skill_file = tmp_path / ".gemini" / "skills" / "dhcpt" / "SKILL.md"
    assert skill_file.is_file()
    assert "name: dhcpt" in skill_file.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    assert "[OK] Installed Gemini CLI skill" in captured.out


def test_install_agent_skill_all_only_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # Simulate that only ~/.gemini exists on the system
    (tmp_path / ".gemini").mkdir()

    exit_code = dhcpt_mod.install_agent_skill("all")
    assert exit_code == 0

    assert (tmp_path / ".gemini" / "skills" / "dhcpt" / "SKILL.md").is_file()
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".vibe").exists()

    captured = capsys.readouterr()
    assert "[OK] Installed Gemini CLI skill" in captured.out
    assert "Claude" not in captured.out
    assert "Mistral" not in captured.out


def test_install_agent_skill_all_none_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(dhcpt_mod.shutil, "which", lambda _cmd: None)
    # No directories exist and no CLI binaries in PATH
    exit_code = dhcpt_mod.install_agent_skill("all")
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Error: No supported AI assistant environments detected" in captured.err


def test_install_agent_skill_refuses_overwrite_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    dest_dir = tmp_path / ".gemini" / "skills" / "dhcpt"
    dest_dir.mkdir(parents=True)
    existing_file = dest_dir / "SKILL.md"
    existing_file.write_text("existing custom content", encoding="utf-8")

    # Attempt install without force -> should refuse and return error
    exit_code = dhcpt_mod.install_agent_skill("gemini", force=False)
    assert exit_code == 1
    assert existing_file.read_text(encoding="utf-8") == "existing custom content"
    captured = capsys.readouterr()
    assert "Error: Skill file already exists" in captured.err
    assert "Refusing to overwrite" in captured.err

    # Attempt install with force -> should overwrite
    exit_code = dhcpt_mod.install_agent_skill("gemini", force=True)
    assert exit_code == 0
    assert "name: dhcpt" in existing_file.read_text(encoding="utf-8")


def test_main_install_skill_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    exit_code = main(["--install-skill", "claude"])
    assert exit_code == 0
    skill_file = tmp_path / ".claude" / "skills" / "dhcpt" / "SKILL.md"
    assert skill_file.is_file()
    captured = capsys.readouterr()
    assert "[OK] Installed Claude Code skill" in captured.out


def test_main_install_skill_cli_existing_refuses_unless_forced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    dest_dir = tmp_path / ".claude" / "skills" / "dhcpt"
    dest_dir.mkdir(parents=True)
    (dest_dir / "SKILL.md").write_text("old", encoding="utf-8")

    exit_code = main(["--install-skill", "claude"])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Refusing to overwrite" in captured.err

    exit_code_forced = main(["--install-skill", "claude", "--force"])
    assert exit_code_forced == 0
    assert (dest_dir / "SKILL.md").read_text(encoding="utf-8") != "old"


def test_package_public_api() -> None:
    import dhcpt

    expected_symbols = [
        "DHCPOffer",
        "DHCPOptionItem",
        "build_dhcp_discover",
        "build_option_82",
        "decode_rfc3397_domain_search",
        "get_route_egress_interface",
        "is_layer3_interface",
        "parse_classless_routes",
        "parse_dhcp_packet",
        "parse_option_82",
        "send_and_receive_dhcp",
        "__version__",
    ]
    for symbol in expected_symbols:
        assert hasattr(dhcpt, symbol), f"Expected symbol '{symbol}' in dhcpt package exports"
    assert dhcpt.__all__ == expected_symbols


def test_get_route_egress_interface() -> None:
    egress = dhcpt_mod.get_route_egress_interface("127.0.0.1")
    assert egress == "lo"


def test_get_route_egress_interface_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["ip", "route", "get", "10.77.0.1"],
            returncode=0,
            stdout="10.77.0.1 dev tun-client src 10.88.0.2 uid 1000\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert dhcpt_mod.get_route_egress_interface("10.77.0.1") == "tun-client"


def test_send_and_receive_dhcp_l3_route_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(dhcpt_mod, "SCAPY_AVAILABLE", True)
    monkeypatch.setattr(dhcpt_mod, "is_layer3_interface", lambda _: True)
    monkeypatch.setattr(dhcpt_mod, "get_if_addr", lambda _: "10.88.0.2")
    monkeypatch.setattr(dhcpt_mod, "get_route_egress_interface", lambda _: "eth0")
    monkeypatch.setattr(dhcpt_mod, "sr", lambda *args, **kwargs: ([], []))

    with caplog.at_level("WARNING"):
        dhcpt_mod.send_and_receive_dhcp(
            interface="wg0",
            mac_str="00:11:22:33:44:55",
            servers=["10.1.1.1"],
            timeout=0.1,
        )

    assert any("Target DHCP server 10.1.1.1 is routed via 'eth0'" in r.message for r in caplog.records)


def test_send_and_receive_dhcp_l3_no_servers_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dhcpt_mod, "SCAPY_AVAILABLE", True)
    monkeypatch.setattr(dhcpt_mod, "is_layer3_interface", lambda _: True)
    monkeypatch.setattr(dhcpt_mod, "get_if_addr", lambda _: "10.88.0.2")

    with pytest.raises(ValueError, match="without broadcast capability"):
        dhcpt_mod.send_and_receive_dhcp(
            interface="wg0",
            mac_str="00:11:22:33:44:55",
            servers=None,
            timeout=0.1,
        )


def test_run_l3_without_servers_exit_code_2(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(dhcpt_mod, "SCAPY_AVAILABLE", True)
    monkeypatch.setattr(dhcpt_mod, "is_layer3_interface", lambda _: True)
    monkeypatch.setattr(dhcpt_mod, "get_interface_diagnostics", lambda _: {"exists": True})

    with caplog.at_level("ERROR"):
        exit_code = dhcpt_mod._run(["-i", "wg0"])

    assert exit_code == 2
    assert any("without broadcast capability" in r.message for r in caplog.records)


def test_get_gateway_ip_success(monkeypatch: pytest.MonkeyPatch) -> None:
    # 0101A8C0 in little-endian hex is 192.168.1.1
    route_content = (
        "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT\n"
        "eth0\t00000000\t0101A8C0\t0003\t0\t0\t100\t00000000\t0\t0\t0\n"
        "eth0\t0001A8C0\t00000000\t0001\t0\t0\t100\t00FFFFFF\t0\t0\t0\n"
    )
    with patch("builtins.open", mock_open(read_data=route_content)):
        gw = dhcpt_mod.get_gateway_ip("eth0")
    assert gw == "192.168.1.1"


def test_get_gateway_ip_no_default_gateway() -> None:
    # Gateway is 00000000 (direct subnet without gateway)
    route_content = (
        "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT\n"
        "eth0\t00000000\t00000000\t0001\t0\t0\t100\t00000000\t0\t0\t0\n"
    )
    with patch("builtins.open", mock_open(read_data=route_content)):
        assert dhcpt_mod.get_gateway_ip("eth0") is None


def test_get_gateway_ip_missing_or_error() -> None:
    def fake_open(*args: Any, **kwargs: Any) -> None:
        raise OSError("File not found")

    with patch("builtins.open", fake_open):
        assert dhcpt_mod.get_gateway_ip("eth0") is None


def test_get_interface_diagnostics_existing() -> None:
    diag = dhcpt_mod.get_interface_diagnostics("lo")
    assert diag["exists"] is True
    assert diag["address"] == "00:00:00:00:00:00"
    assert diag["mtu"] != "unknown"
    assert "operstate" in diag


def test_get_interface_diagnostics_not_found() -> None:
    diag = dhcpt_mod.get_interface_diagnostics("non_existent_dummy_999")
    assert diag["exists"] is False
    assert diag["operstate"] == "unknown"
    assert diag["address"] == "unknown"


def test_is_agent_present_directory_match(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    gemini_home = tmp_path / ".gemini"
    gemini_home.mkdir()

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(dhcpt_mod.shutil, "which", lambda _: None)

    assert dhcpt_mod.is_agent_present("gemini") is True
    assert dhcpt_mod.is_agent_present("claude") is False


def test_is_agent_present_cli_binary_match(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    def fake_which(cmd: str) -> str | None:
        return "/usr/local/bin/claude" if cmd == "claude" else None

    monkeypatch.setattr(dhcpt_mod.shutil, "which", fake_which)
    assert dhcpt_mod.is_agent_present("claude") is True
    assert dhcpt_mod.is_agent_present("mistral") is False


def test_parse_option_82_extended() -> None:
    # Suboption 5 (link_selection, len 4): 10.50.1.1
    # Suboption 1 (circuit_id, len 4): "eth0"
    # Suboption 99 (unknown, len 2): invalid utf-8 0xffff
    raw = b"\x05\x04\x0a\x32\x01\x01\x01\x04eth0\x63\x02\xff\xff"
    parsed = dhcpt_mod.parse_option_82(raw)
    assert parsed["link_selection"] == "10.50.1.1"
    assert parsed["circuit_id"] == "eth0"
    assert parsed["subopt_99"] == "ffff"


def test_parse_option_82_truncated() -> None:
    # Header says length is 10, but only 2 bytes provided
    raw = b"\x01\x0a\x01\x02"
    parsed = dhcpt_mod.parse_option_82(raw)
    # Parser should safely terminate without throwing IndexError
    assert isinstance(parsed, dict)


def test_build_option_82_with_remote_id() -> None:
    raw = dhcpt_mod.build_option_82(remote_id="sw-core-01", circuit_id="Vlan100")
    parsed = dhcpt_mod.parse_option_82(raw)
    assert parsed["remote_id"] == "sw-core-01"
    assert parsed["circuit_id"] == "Vlan100"


def test_main_remote_id_and_circuit_id(capsys: pytest.CaptureFixture[str]) -> None:
    mock_offer = DHCPOffer(server_ip="10.1.1.1", server_mac="00:11:22:33:44:55", offered_ip="10.1.1.50")
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "up"}),
        patch.object(dhcpt_mod, "get_if_hwaddr", return_value="00:11:22:33:44:55"),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", return_value=[mock_offer]) as mock_send,
    ):
        exit_code = main(["-i", "eth0", "-s", "10.1.1.1", "--remote-id", "sw-core-01", "--circuit-id", "Vlan100"])
        assert exit_code == 0
        kwargs = mock_send.call_args.kwargs
        assert kwargs.get("remote_id") == "sw-core-01"
        assert kwargs.get("circuit_id") == "Vlan100"


def test_main_clear_default_options(capsys: pytest.CaptureFixture[str]) -> None:
    mock_offer = DHCPOffer(server_ip="10.1.1.1", server_mac="00:11:22:33:44:55", offered_ip="10.1.1.50")
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "up"}),
        patch.object(dhcpt_mod, "get_if_hwaddr", return_value="00:11:22:33:44:55"),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", return_value=[mock_offer]) as mock_send,
    ):
        # 1. With -o 26: strictly requested options only
        exit_code = main(["-i", "eth0", "--clear-default-options", "-o", "26"])
        assert exit_code == 0
        assert mock_send.call_args.kwargs.get("param_req_list") == [26]

        # 2. Without -o: empty list
        exit_code2 = main(["-i", "eth0", "--clear-default-options"])
        assert exit_code2 == 0
        assert mock_send.call_args.kwargs.get("param_req_list") == []


def test_main_mac_spoofing(capsys: pytest.CaptureFixture[str]) -> None:
    mock_offer = DHCPOffer(server_ip="10.1.1.1", server_mac="00:11:22:33:44:55", offered_ip="10.1.1.50")
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "up"}),
        patch.object(dhcpt_mod, "get_if_hwaddr", return_value="00:00:00:00:00:01"),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", return_value=[mock_offer]) as mock_send,
    ):
        exit_code = main(["-i", "eth0", "--mac", "aa:bb:cc:dd:ee:ff"])
        assert exit_code == 0
        assert mock_send.call_args.kwargs.get("mac_str") == "aa:bb:cc:dd:ee:ff"


def test_main_no_broadcast(capsys: pytest.CaptureFixture[str]) -> None:
    mock_offer = DHCPOffer(server_ip="10.1.1.1", server_mac="00:11:22:33:44:55", offered_ip="10.1.1.50")
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "up"}),
        patch.object(dhcpt_mod, "get_if_hwaddr", return_value="00:11:22:33:44:55"),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", return_value=[mock_offer]) as mock_send,
    ):
        exit_code = main(["-i", "eth0", "--no-broadcast"])
        assert exit_code == 0
        assert mock_send.call_args.kwargs.get("broadcast") is False


def test_main_giaddr_override(capsys: pytest.CaptureFixture[str]) -> None:
    mock_offer = DHCPOffer(server_ip="10.1.1.1", server_mac="00:11:22:33:44:55", offered_ip="10.50.1.50")
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "up"}),
        patch.object(dhcpt_mod, "get_if_hwaddr", return_value="00:11:22:33:44:55"),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", return_value=[mock_offer]) as mock_send,
    ):
        exit_code = main(["-i", "eth0", "-s", "10.1.1.1", "--giaddr", "10.50.1.1"])
        assert exit_code == 0
        assert mock_send.call_args.kwargs.get("giaddr") == "10.50.1.1"


def test_main_positional_interface(capsys: pytest.CaptureFixture[str]) -> None:
    mock_offer = DHCPOffer(server_ip="10.1.1.1", server_mac="00:11:22:33:44:55", offered_ip="10.1.1.50")
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "up"}),
        patch.object(dhcpt_mod, "get_if_hwaddr", return_value="00:11:22:33:44:55"),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", return_value=[mock_offer]) as mock_send,
    ):
        exit_code = main(["eth0"])
        assert exit_code == 0
        assert mock_send.call_args.kwargs.get("interface") == "eth0"


def test_main_timeout_and_all(capsys: pytest.CaptureFixture[str]) -> None:
    mock_offer = DHCPOffer(server_ip="10.1.1.1", server_mac="00:11:22:33:44:55", offered_ip="10.1.1.50")
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "up"}),
        patch.object(dhcpt_mod, "get_if_hwaddr", return_value="00:11:22:33:44:55"),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", return_value=[mock_offer]) as mock_send,
    ):
        exit_code = main(["-i", "eth0", "--timeout", "4.5", "--all"])
        assert exit_code == 0
        assert mock_send.call_args.kwargs.get("timeout") == 4.5
        assert mock_send.call_args.kwargs.get("listen_all") is True


def test_main_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    mock_offer = DHCPOffer(server_ip="10.1.1.1", server_mac="00:11:22:33:44:55", offered_ip="10.1.1.50")
    with (
        patch.object(dhcpt_mod, "get_interface_diagnostics", return_value={"exists": True, "operstate": "up"}),
        patch.object(dhcpt_mod, "get_if_hwaddr", return_value="00:11:22:33:44:55"),
        patch.object(dhcpt_mod, "send_and_receive_dhcp", return_value=[mock_offer]),
    ):
        exit_code = main(["-i", "eth0", "--json"])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["interface"] == "eth0"
        assert data["offers_count"] == 1
        assert data["offers"][0]["server_ip"] == "10.1.1.1"


def test_bash_runtime_tab_completion() -> None:
    import shutil
    import subprocess

    bash_bin = shutil.which("bash")
    if not bash_bin:
        pytest.skip("bash not found")

    zsh_comp_path = Path("completions/bash/dhcpt").resolve()
    script = f"""
source "{zsh_comp_path}"
COMP_WORDS=(dhcpt --)
COMP_CWORD=1
cur="--"
prev="dhcpt"
_dhcpt_bash
echo "${{COMPREPLY[*]}}"
"""
    res = subprocess.run([bash_bin, "-c", script], capture_output=True, text=True, check=True)
    completions = res.stdout.strip().split()
    assert "--target-gateway" in completions
    assert "--interface" in completions
    assert "--timeout" in completions


def test_zsh_runtime_tab_completion() -> None:
    import os
    import pty
    import select
    import shutil
    import subprocess

    zsh_bin = shutil.which("zsh")
    if not zsh_bin:
        pytest.skip("zsh not found")

    zsh_comp_path = Path("completions/zsh/_dhcpt").resolve()

    master, slave = pty.openpty()
    proc = subprocess.Popen([zsh_bin, "-f"], stdin=slave, stdout=slave, stderr=slave, close_fds=True)
    os.close(slave)

    def send(cmd: str) -> None:
        os.write(master, cmd.encode("utf-8") + b"\n")

    send("autoload -Uz compinit && compinit -D -u")
    send(f'source "{zsh_comp_path}"')
    send("compdef _dhcpt dhcpt")
    # Simulate typing 'dhcpt <TAB>' in an interactive terminal
    os.write(master, b"dhcpt \t")
    send("")
    send("exit")

    output = b""
    while True:
        r, _, _ = select.select([master], [], [], 1.5)
        if not r:
            break
        try:
            data = os.read(master, 1024)
            if not data:
                break
            output += data
        except OSError:
            break

    os.close(master)
    proc.wait()
    out = output.decode("utf-8", errors="replace")

    assert "_arguments:" not in out, f"Zsh _arguments error found: {out}"
    assert "comparguments:" not in out, f"Zsh comparguments error found: {out}"
    assert "invalid argument" not in out, f"Zsh syntax error found: {out}"
