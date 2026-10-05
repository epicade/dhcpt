"""dhcpt - Comprehensive DHCP tester, troubleshooting, and diagnostic library and CLI utility."""

from __future__ import annotations

from dhcpt.cli import (
    DHCPOffer,
    DHCPOptionItem,
    build_dhcp_discover,
    build_option_82,
    decode_rfc3397_domain_search,
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
    "build_dhcp_discover",
    "build_option_82",
    "decode_rfc3397_domain_search",
    "is_layer3_interface",
    "parse_classless_routes",
    "parse_dhcp_packet",
    "parse_option_82",
    "send_and_receive_dhcp",
    "__version__",
]
