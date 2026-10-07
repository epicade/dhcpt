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
"""dhcpt - Comprehensive DHCP tester, troubleshooting, and diagnostic library and CLI utility."""

from __future__ import annotations

from dhcpt.cli import (
    DHCPOffer,
    DHCPOptionItem,
    RouteInfo,
    build_dhcp_discover,
    build_option_82,
    decode_rfc3397_domain_search,
    get_route_egress_interface,
    get_route_for_ip,
    is_layer3_interface,
    parse_classless_routes,
    parse_dhcp_packet,
    parse_option_82,
    send_and_receive_dhcp,
)

__version__ = "0.1.1"

__all__ = [
    "DHCPOffer",
    "DHCPOptionItem",
    "RouteInfo",
    "build_dhcp_discover",
    "build_option_82",
    "decode_rfc3397_domain_search",
    "get_route_egress_interface",
    "get_route_for_ip",
    "is_layer3_interface",
    "parse_classless_routes",
    "parse_dhcp_packet",
    "parse_option_82",
    "send_and_receive_dhcp",
    "__version__",
]
