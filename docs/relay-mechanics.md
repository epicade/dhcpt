# DHCP Relay Architecture & RFC 3527 Link Selection

> ⚠️ **AI Authorship Notice & Review Request:**  
> This architectural guide was drafted with AI assistance (Google Gemini CLI).  
> **TODO:** A human network engineer should peer-review these explanations and vendor behaviors against live environments.

This document explains how DHCP Relay Agents forward network requests across routers.
It describes why testing remote subnets over VPNs often fails and how `dhcpt` solves this problem.

---

## 1. Vendor Configuration Commands

Routers use different command names for DHCP relay forwarding.
However, all vendors follow the same open Internet standards (RFC 2131, RFC 3046, RFC 3527):

| Platform | Configuration Command | Notes |
| :--- | :--- | :--- |
| **Cisco IOS / NX-OS** | `ip helper-address <server-ip>` | Configured on the VLAN interface (SVI) |
| **Juniper Junos** | `set forwarding-options dhcp-relay server-group ...` | Configured on routed VLAN interfaces (IRB) |
| **Arista EOS** | `ip helper-address <server-ip>` | Configured on VLAN interfaces |
| **Linux (ISC / Kea / systemd)** | `dhcrelay <server-ip>` | Forwarding daemon listening on network interfaces |

---

## 2. How DHCP Relay Agents Work

In enterprise networks, client computers live in separate VLANs.
Routers deliberately block Layer 2 broadcast packets from crossing these network boundaries.

To let clients reach a central DHCP server, the default gateway router acts as a relay agent:

```text
  [ Client (VLAN 100) ]
           │
           │  1. DHCP Discover (Layer 2 Local Broadcast: UDP port 67)
           ▼
  [ Router / Default Gateway (10.50.1.1) ]
           │
           │  2. Converts Layer 2 broadcast into Layer 3 Unicast packet
           │     Sets giaddr = 10.50.1.1 (Gateway IP Address)
           │     Adds Option 82 Relay Information:
           │       - Link Selection: Target Gateway = 10.50.1.1 (Sub-option 5)
           │       - Circuit-ID = 'Vlan100' (Sub-option 1)
           │       - Remote-ID = Router hostname (Sub-option 2)
           ▼
  [ Central DHCP Server (192.0.2.1) ]
```

### Step-by-Step Packet Flow

1. **Intercept Broadcast (Layer 2):** The switch SVI or router interface intercepts the client's Layer 2 DHCP Discover broadcast (destination UDP port 67).
2. **Convert to Unicast (Layer 3):** The router wraps the payload into a Layer 3 unicast UDP packet (from source port 67 to destination port 67) directed to the configured helper IP (`192.0.2.1`).
3. **Inject Header & Option 82 Fields:**
   * **`giaddr` (Gateway IP Address):** Set to the switch interface IP on that subnet (e.g. `10.50.1.1`).
   * **`hops = 1`:** Incremented by the relay agent to prevent routing loops.
   * **Option 82 Sub-option 1 (`circuit-id`):** Identifies the incoming port or VLAN (e.g. `Vlan100`, `ge-0/0/1`).
   * **Option 82 Sub-option 2 (`remote-id`):** Identifies the switch hardware or hostname (e.g. `sw-core01`).
   * **Option 82 Sub-option 5 (`link-selection`):** Identifies the target subnet IP pool (`10.50.1.1`) per RFC 3527 (`--target-gateway`).
4. **Server Pool Selection & Response:** The central DHCP server reads `giaddr` or Link Selection, selects the matching subnet pool (`10.50.1.0/24`), assigns an IP address, and unicasts the DHCP Offer back to `giaddr`.

---

## 3. Why Remote Testing Over VPNs Fails

Administrators often need to test whether a remote DHCP pool has available addresses.
However, testing from a remote laptop or VPN tunnel traditionally fails.

### The RFC 2131 Return-Path Conflict: One Field for Two Tasks

In the original RFC 2131 specification, the `giaddr` field is forced to serve two conflicting purposes at the same time:
1. **Subnet Identifier:** Tells the DHCP server which address pool to allocate from.
2. **Return Routing Destination:** Tells the DHCP server where to unicast the DHCP Offer reply.

In standard on-site networks, this dual role works because the router is directly attached to the client VLAN.
However, when testing remotely over a VPN or routed connection, this design breaks:

```text
  [ Admin Laptop on VPN ] ──────> [ Central DHCP Server ]
       IP: 192.168.1.50                  IP: 192.0.2.1
       giaddr: 10.50.1.1                      │
                                              │  DHCP Offer (Sent to giaddr: 10.50.1.1)
                                              ▼
                                 [ Physical Router in Datacenter ]
                                      (IP: 10.50.1.1)
                                      *The admin laptop NEVER receives the reply!*
```

If a testing tool sets `giaddr` to `10.50.1.1` to select the remote pool:
1. The DHCP server selects the correct address pool (`10.50.1.0/24`).
2. The server sends its reply to `10.50.1.1` (the physical router in the data center).
3. The reply never reaches your laptop. The test falsely times out.

---

## 4. The RFC 3527 Solution: Link Selection

RFC 3527 introduces the **Link Selection sub-option** (Option 82, sub-option 5).
This standard separates **which pool to allocate** from **where to send the reply**:

| Packet Field | Value | Purpose |
| :--- | :--- | :--- |
| **`giaddr` (BOOTP Header)** | Admin Laptop IP (e.g. `192.168.1.50`) | Tells the server **where to route the reply** |
| **Option 82 Sub-option 5** | Target Subnet Gateway (`10.50.1.1`) | Tells the server **which address pool to pick** |

### How `dhcpt` Automates RFC 3527

When you pass `--target-gateway 10.50.1.1`:
1. `dhcpt` finds the local IP address of your outgoing network card.
2. It sets `giaddr` to your local machine IP.
3. It encodes the target gateway into Option 82 Sub-option 5.
4. The server picks an IP from the remote pool and routes the reply directly back to your laptop!

```bash
# Test remote pool allocation for VLAN 100:
sudo dhcpt -i eth0 -s 192.0.2.1 --target-gateway 10.50.1.1 --circuit-id Vlan100
```

---

## 5. Automatic Outgoing Interface Detection

When working over a VPN, traffic flows through a virtual tunnel interface like `wg0` or `tun0`.
To find your active outgoing interface automatically, query the Linux routing table:

```bash
# Find interface used to reach the DHCP server:
IFACE=$(ip route get 192.0.2.1 | grep -oP 'dev \K\S+')

# Run dhcpt over the discovered interface:
sudo dhcpt -i "$IFACE" -s 192.0.2.1 --target-gateway 10.50.1.1
```

---

## 6. Layer 3 VPN Tunnel Support (WireGuard / OpenVPN)

Layer 3 tunnel interfaces do not have hardware MAC addresses or Ethernet headers.
Standard tools fail on these links with socket errors.

`dhcpt` inspects the interface type in Linux sysfs (`/sys/class/net/<iface>/type`).
If a raw Layer 3 tunnel is detected, `dhcpt` automatically uses raw IP sockets (`AF_INET`):
* It strips Ethernet headers from the packet.
* It transmits pure IP packets directly into the tunnel.
* It decodes incoming replies without expecting Ethernet framing.

### Routing Requirements for Layer 3 Testing

Layer 3 interfaces cannot send local broadcasts.
You must specify the target server IP with `-s`:

```bash
# Verify route points to tunnel:
ip route get 10.1.1.1

# Run test across tunnel:
sudo dhcpt -i wg0 -s 10.1.1.1 --target-gateway 10.50.1.1
```

`dhcpt` checks kernel routing automatically and warns you if traffic would leave through the wrong card.

---

## 7. Standards References

* **RFC 2131:** Dynamic Host Configuration Protocol (DHCP)
* **RFC 2132:** DHCP Options and BOOTP Vendor Extensions
* **RFC 3046:** DHCP Relay Agent Information Option (Option 82)
* **RFC 3527:** Link Selection sub-option for DHCP Relay Information Option
* **IANA Registry:** [BOOTP and DHCP Parameters](https://www.iana.org/assignments/bootp-dhcp-parameters)
