# DHCP Relay Architecture & RFC 3527 Link Selection

> ⚠️ **Technical Review & AI Authorship Disclosure:**  
> This architectural guide was drafted with AI assistance (Google Gemini CLI) based on RFC 2131, RFC 3046, and RFC 3527 specifications. While carefully reviewed against standard protocol definitions, real-world network switch/router behaviors (e.g. Cisco, Juniper, Arista) and vendor-specific edge cases may vary.  
> **TODO:** Technical peer review of AI-documented vendor relay behaviors and packet flows (Gegenlesen / review against official vendor documentation).

This guide provides an in-depth technical explanation of how DHCP Relay Agents work across enterprise networks, why remote troubleshooting across Layer 3 boundaries and VPNs traditionally fails, and how `dhcpt` implements **RFC 3527 Link Selection** to solve this problem.

---

## 1. Vendor Terminology Comparison

Across different network hardware vendors and operating systems, DHCP relay forwarding is referred to by different names, but all implement the same core protocol standards (RFC 2131, RFC 3046, RFC 3527):

| Platform | Configuration Directive | Notes |
|:---|:---|:---|
| **Cisco IOS / NX-OS** | `ip helper-address <dhcp-server-ip>` | Configured on the Switch Virtual Interface (SVI / VLAN) |
| **Juniper Junos** | `set forwarding-options dhcp-relay server-group ...` | Configured on Routed VLAN Interfaces (RVI) or IRB |
| **Arista EOS** | `ip helper-address <dhcp-server-ip>` | Configured on VLAN interfaces |
| **Linux (ISC / Kea / systemd)** | `dhcrelay <dhcp-server-ip>` | Forwarding daemon listening on network interfaces |

---

## 2. How Relay Agents Work (RFC 2131 & RFC 3046)

In an enterprise network or data center, client machines (servers, VMs, workstations, VoIP phones) reside in distinct VLANs separated by routers and Layer 3 switches. Because DHCP Discover packets are Layer 2 broadcasts (`255.255.255.255`), routers deliberately block them from crossing broadcast domains.

To allow clients to receive configuration from central DHCP servers, the default gateway router or switch acts as a **DHCP Relay Agent**:

```text
  [ Client (VLAN 100) ]
           │
           │  1. DHCP Discover (Broadcast: UDP sport 68 -> dport 67)
           ▼
  [ Router / L3 Switch (Gateway: 10.50.1.1) ]
           │
           │  2. Converts broadcast into Layer 3 Unicast (UDP sport 67 -> dport 67)
           │     Sets giaddr = 10.50.1.1, hops = 1
           │     Injects Option 82 (Circuit-ID = 'Vlan100', Remote-ID = switch hostname)
           ▼
  [ Central DHCP Server (192.0.2.1) ]
```

### Relay Step-by-Step Flow:
1. **Intercept Broadcast:** The switch SVI intercepts the client's Layer 2 DHCP Discover broadcast on port 67.
2. **Convert to Unicast:** The switch wraps the payload into a Layer 3 unicast UDP packet (from UDP source port 67 to destination port 67) directed to the configured helper IP (`192.0.2.1`).
3. **Inject Header & Option 82 Fields:**
   * **`giaddr` (Gateway IP Address):** Set to the switch's interface IP on that subnet (e.g. `10.50.1.1`).
   * **`hops = 1`:** Incremented to prevent routing loops.
   * **Option 82 Sub-option 1 (`circuit-id`):** Identifies the incoming port or VLAN (e.g. `Vlan100`, `ge-0/0/1`).
   * **Option 82 Sub-option 2 (`remote-id`):** Identifies the switch hardware or hostname (e.g. `sw-core01.dc2`).
4. **Server Pool Selection & Response:** The central DHCP server reads `giaddr`, identifies the matching subnet pool (`10.50.1.0/24`), assigns an IP address, and unicasts the `DHCPOFFER` back to `giaddr`.

---

## 3. The Troubleshooting Dilemma: Why Classic Relaying Fails Across VPNs

Network administrators and DevOps engineers frequently need to troubleshoot whether a central DHCP server is functioning properly for a remote VLAN or subnet (e.g., verifying if an address pool is exhausted, checking lease parameters, or confirming DHCP reservations) without having physical access to that specific rack or broadcast domain.

### The RFC 2131 Routing Problem:
RFC 2131 §4.1 dictates that the DHCP server **must deliver the unicast `DHCPOFFER` back to the IP address specified in the `giaddr` field**:

```text
  [ Tester Workstation / VPN ] ──────> [ Central DHCP Server ]
       IP: 10.23.254.244                     IP: 192.0.2.1
       giaddr: 10.50.1.1                      │
                                              │  DHCP Offer (Unicast to giaddr: 10.50.1.1)
                                              ▼
                                 [ Physical Router in Datacenter ]
                                      (IP: 10.50.1.1)
                                      *Tester NEVER receives the reply!*
```

If a testing tool running on your workstation simply sets `giaddr = 10.50.1.1` to tell the DHCP server which pool to select:
1. The DHCP server selects the correct pool (`10.50.1.0/24`).
2. **However, it transmits the `DHCPOFFER` to `10.50.1.1`** (the physical switch interface in the data center)!
3. Your workstation never sees the reply, causing the test to falsely time out.

---

## 4. The RFC 3527 Solution: Link Selection (Sub-option 5)

To solve this exact routing challenge in modern multi-homed, MPLS, and VRF networks, the IETF standardized **RFC 3527 (Link Selection sub-option for the DHCP Relay Agent Information Option)**.

RFC 3527 decouples **subnet pool selection** from **reply packet routing**:

| Packet Field | Value | Purpose |
|:---|:---|:---|
| **`giaddr` (BOOTP Header)** | Tester's local IP (e.g. `10.23.254.244`) | Instructs the DHCP server **where to route the reply** |
| **Option 82 Sub-option 5 (`link_selection`)** | Target subnet gateway (e.g. `10.50.1.1`) | Instructs the DHCP server **which address pool to allocate from** |

### How `dhcpt` Automates RFC 3527:
When you pass `--target-gateway` (or alias `--relay-subnet`):
1. `dhcpt` automatically queries the local IP address of your outgoing interface (e.g. `vpn0` or `eth0`).
2. It sets `giaddr` to your local machine IP.
3. It encodes Option 82 Sub-option 5 with the target subnet gateway IP.
4. The DHCP server receives the request, evaluates Sub-option 5, allocates an IP from the requested VLAN pool, and unicasts the reply directly back to your workstation IP!

```bash
# Verify DHCP pool allocation for VLAN 100 on remote server 192.0.2.1:
sudo dhcpt -i eth0 --dhcp-servers 192.0.2.1 --target-gateway 10.50.1.1 --circuit-id Vlan100
```

---

## 5. Dynamic Egress Interface Discovery for VPNs

When testing from a laptop or home office over a corporate VPN (e.g. WireGuard, OpenVPN, Cisco AnyConnect), the remote DHCP server is typically not reachable via your local physical Ethernet card (`eth0` or `wlan0`), but through a virtual tunnel interface (`vpn0`, `tun0`, `wg0`).

To determine the outgoing interface dynamically without guessing interface names, use `ip route get`:

```bash
# Query the Linux kernel for the egress interface towards the DHCP server:
IFACE=$(ip route get 192.0.2.1 | grep -oP 'dev \K\S+')

# Run dhcpt over the discovered tunnel interface:
sudo dhcpt -i "$IFACE" --dhcp-servers 192.0.2.1 --target-gateway 10.50.1.1 --circuit-id Vlan100
```

---

## 6. Layer 3 WireGuard & TUN Interface Support

Standard DHCP test tools rely exclusively on Layer 2 Ethernet raw sockets (`AF_PACKET`). On Layer 3 interfaces without hardware MAC addresses like WireGuard (`wg0`) or OpenVPN TUN (`tun0`), there are **no Ethernet headers and no MAC addresses**. Traditional tools fail immediately with kernel socket errors.

`dhcpt` automatically inspects the interface type via sysfs (`/sys/class/net/<iface>/type`). If `ARPHRD_NONE` (65534) is detected, `dhcpt` dynamically transitions to raw IP sockets (`AF_INET`):
* Omits the Ethernet header entirely.
* Transmits pure Layer 3 IP/UDP packets directly over the point-to-point link.
* Decodes incoming replies without expecting Layer 2 framing.

*Privilege Requirement:* Both Layer 2 (`AF_PACKET`) and Layer 3 (`AF_INET`) raw socket operations require superuser privileges (`sudo`) or the `CAP_NET_RAW` capability because opening raw network sockets in the Linux kernel is restricted to privileged processes.

```bash
sudo dhcpt -i wg0 --dhcp-servers 10.1.1.1 --target-gateway 10.50.1.1
```

---

## 7. Standards References

* **RFC 2131:** Dynamic Host Configuration Protocol (DHCP)
* **RFC 2132:** DHCP Options and BOOTP Vendor Extensions
* **RFC 3046:** DHCP Relay Agent Information Option (Option 82)
* **RFC 3527:** Link Selection sub-option for the DHCP Relay Agent Information Option
* **IANA Registry:** [BOOTP and DHCP Parameters](https://www.iana.org/assignments/bootp-dhcp-parameters)
