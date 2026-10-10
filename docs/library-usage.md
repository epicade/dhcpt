# Using `dhcpt` as a Python Library

`dhcpt` exports its core packet-crafting routines, decoders, dataclasses, and routing utilities under the top-level `dhcpt` namespace.
This allows network engineers and automation developers to embed lease-safe DHCP testing into custom Python scripts, diagnostic daemons, or CI test harnesses without invoking the CLI via subshell.

---

## Prerequisites & Permissions

`dhcpt` uses Scapy to craft and inspect raw network frames:
* **Layer 2 (Ethernet):** Requires `AF_PACKET` raw sockets.
* **Layer 3 (TUN / WireGuard):** Requires `AF_INET` raw sockets.

Both socket types require the Linux **`CAP_NET_RAW`** capability or superuser execution (`sudo`).
If run without sufficient privileges, `send_and_receive_dhcp()` raises a `PermissionError`.

---

## Quickstart: Basic DHCP Discover

Send a standard broadcast DHCP Discover on a local network interface and inspect incoming DHCP Offers:

```python
import sys
import dhcpt

try:
    offers = dhcpt.send_and_receive_dhcp(
        interface="eth0",
        timeout=3.0,
    )
except PermissionError:
    print("Error: CAP_NET_RAW or root privileges required.", file=sys.stderr)
    sys.exit(1)

if not offers:
    print("No DHCP offer received.")
    sys.exit(1)

for idx, offer in enumerate(offers, start=1):
    print(f"Offer #{idx} from {offer.server_ip} (Server ID: {offer.server_id}):")
    print(f"  Offered IP   : {offer.offered_ip}")
    print(f"  Subnet Mask  : {offer.subnet_mask}")
    print(f"  Router/GW    : {offer.router}")
    print(f"  DNS Servers  : {', '.join(offer.dns_servers)}")
    print(f"  Domain Name  : {offer.domain_name}")
    print(f"  Lease Time   : {offer.lease_time}s")
```

---

## Simulating DHCP Relay Agent & IP-Helper (RFC 3527)

Simulate a router or switch relay agent forwarding unicast DHCP packets to remote servers on behalf of a target VLAN:

```python
import dhcpt

offers = dhcpt.send_and_receive_dhcp(
    interface="eth0",
    servers=["10.99.0.1", "10.99.0.2"],  # Unicast target DHCP servers
    target_gateway="10.50.1.1",  # RFC 3527 Link Selection gateway
    circuit_id="Vlan100",  # Option 82 Sub-option 1
    remote_id="sw-core-01",  # Option 82 Sub-option 2
    timeout=4.0,
)

for offer in offers:
    print(f"Server {offer.server_id} offered {offer.offered_ip}")
```

*Note on backward compatibility:* The parameter `relay_subnet` is supported as an alias for `target_gateway` for backward compatibility with v0.1.0/v0.1.1 code.

---

## Detecting Rogue DHCP Servers

By default, `send_and_receive_dhcp()` returns as soon as the first valid response is received (or after querying all unicast servers).
Set `listen_all=True` to listen across the entire timeout window and capture all responding servers on the broadcast domain:

```python
import dhcpt

# Listen for 5 full seconds across the local broadcast domain
offers = dhcpt.send_and_receive_dhcp(
    interface="eth0",
    listen_all=True,
    timeout=5.0,
)

distinct_servers = {offer.server_id or offer.server_ip for offer in offers}
if len(distinct_servers) > 1:
    print(f"WARNING: Multiple ({len(distinct_servers)}) DHCP servers detected!")
    for s_ip in distinct_servers:
        print(f" - Server: {s_ip}")
```

---

## Layer 3 Tunnel / Point-to-Point Interfaces (WireGuard, TUN)

`dhcpt` automatically handles Layer 3 devices where Ethernet framing is absent:

```python
import dhcpt

iface = "wg0"

if dhcpt.is_layer3_interface(iface):
    print(f"{iface} is a Layer 3 point-to-point interface.")

    # Layer 3 interfaces require explicit target servers (broadcast is unavailable)
    offers = dhcpt.send_and_receive_dhcp(
        interface=iface,
        servers=["10.77.0.1"],
        target_gateway="10.88.0.1",
        timeout=3.0,
    )
```

---

## Linux Kernel Routing Lookups (`RouteInfo`)

Query the Linux kernel FIB routing table using `get_route_for_ip()` to inspect next-hop gateways, egress interfaces, and source IPs:

```python
import dhcpt

route = dhcpt.get_route_for_ip("10.99.0.1")

print(f"Egress interface : {route.interface}")
print(f"Next-hop gateway : {route.gateway}")
print(f"Preferred source : {route.src_ip}")

# Helper to resolve just the egress interface:
egress = dhcpt.get_route_egress_interface("10.99.0.1")
```

---

## Inspecting Decoded DHCP Options

The `DHCPOffer` object contains parsed attributes for common parameters and an `options_list` of `DHCPOptionItem` objects for full option transparency:

```python
import dhcpt

offers = dhcpt.send_and_receive_dhcp(interface="eth0", timeout=3.0)

if offers:
    offer = offers[0]

    # Access Classless Static Routes (RFC 3442 / Option 121)
    if offer.classless_static_routes:
        print("Static Routes:")
        for destination, router in offer.classless_static_routes:
            print(f"  * {destination} via {router}")

    # Access Domain Search List (RFC 3397 / Option 119)
    if offer.domain_search:
        print(f"Search Domains: {', '.join(offer.domain_search)}")

    # Iterate over all raw received DHCP options
    for opt in offer.options_list:
        print(f"Option {opt.code:<3} ({opt.name:<25}): {opt.value}")
```

---

## Exported Public Symbols Reference

All exported symbols are declared in `dhcpt.__all__`:

| Symbol | Type | Description |
| :--- | :--- | :--- |
| `send_and_receive_dhcp()` | Function | Core I/O function to transmit Discover and collect Offers. |
| `build_dhcp_discover()` | Function | Crafts Scapy Layer 2 or Layer 3 Discover packets. |
| `build_option_82()` | Function | Encodes Type-Length-Value (TLV) payload for Option 82. |
| `parse_dhcp_packet()` | Function | Decodes raw Scapy packet into a `DHCPOffer` instance. |
| `parse_option_82()` | Function | Decodes raw Option 82 payload bytes into sub-options. |
| `parse_classless_routes()` | Function | Decodes RFC 3442 / Option 121 route wire data. |
| `decode_rfc3397_domain_search()` | Function | Decodes RFC 3397 DNS search wire format. |
| `is_layer3_interface()` | Function | Checks sysfs device type for Layer 3 point-to-point status. |
| `get_route_for_ip()` | Function | Queries Linux FIB for egress device, next-hop gateway, and source IP. |
| `get_route_egress_interface()` | Function | Resolves egress interface name for a destination IP. |
| `DHCPOffer` | Dataclass | Decoded representation of a DHCP Offer packet. |
| `DHCPOptionItem` | Dataclass | Individual decoded DHCP option name, code, and value. |
| `RouteInfo` | Dataclass | Kernel route lookup details (`interface`, `gateway`, `src_ip`). |
| `__version__` | String | Package version string (SemVer). |
