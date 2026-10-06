% DHCPT(1) dhcpt 0.1.1 | User Commands
% Emilian Schweikert
% October 2026

# NAME

dhcpt - comprehensive DHCP tester, troubleshooting, and diagnostic CLI utility

# SYNOPSIS

**dhcpt** [*OPTIONS*] [*INTERFACE*]  
**dhcpt** **-i** *INTERFACE* [*OPTIONS*]  
**dhcpt** **--list-interfaces**  
**dhcpt** **--list-options**  
**dhcpt** **--install-skill** [*TARGET*]

# DESCRIPTION

**dhcpt** is a Layer 2 and Layer 3 DHCP testing and diagnostic tool for Linux.
It crafts raw DHCP Discover packets and inspects incoming DHCP Offers.
The tool decodes network parameters, lease times, Option 82 fields, and Option 121 static routes.

**dhcpt** is strictly **lease-safe**:
Out of the four-step DORA exchange (Discover, Offer, Request, Acknowledge), it only executes the first two steps.
It never sends a DHCP Request or commits an IP address lease.

On Layer 2 Ethernet interfaces, **dhcpt** uses raw packet sockets (**AF_PACKET**).
On Layer 3 interfaces without MAC addresses (WireGuard **wg0**, OpenVPN **tun0**), it uses raw IP sockets (**AF_INET**).
Both modes require superuser privileges (**sudo**) for raw socket access.

On Layer 3 interfaces, broadcast packets are not supported.
You must specify target DHCP servers via **--dhcp-servers** (or **-s**).
Packet transmission on Layer 3 relies on Linux kernel routing.
Your routing table must direct traffic for the target server through the tunnel interface.
**dhcpt** checks kernel routing automatically and issues a warning if traffic would leave through another card.

# OPTIONS

## Interface Targeting

*interface*, **-i** *INTERFACE*, **--interface** *INTERFACE*
:   Target network interface to send DHCP Discovers on (e.g. `eth0`, `ens3`, `bond0`, `wg0`).
    May be passed as an option flag or as a single positional argument.
    Use this option to bind packet capture and transmission to a specific network device.

## DHCP Relay & IP-Helper Simulation

**--dhcp-servers** *DHCP_SERVERS*, **--dhcp-server** *DHCP_SERVERS*, **-s** *DHCP_SERVERS*
:   Target one or more remote DHCP servers directly via unicast (comma-separated, e.g. `-s 10.1.1.1,10.1.1.2`).
    Corresponds to the relay target on routers (e.g. Cisco *ip helper-address*).
    When querying remote servers, **dhcpt** sets the BOOTP gateway field (*giaddr*) to the local interface IP.
    This ensures the server routes the reply directly back to your machine.
    Aliases: **--dhcp-server**, **-s**.

**--target-gateway** *GATEWAY_IP*, **--relay-subnet** *GATEWAY_IP*
:   Simulate a remote subnet using RFC 3527 Link Selection (Option 82 Sub-option 5).
    Specify the gateway IP defined for that pool in the DHCP server configuration.
    This instructs the server which address pool to allocate from.
    Meanwhile, **dhcpt** keeps *giaddr* set to your local IP so the reply returns to you.
    Use this option to test VLAN-specific or subnet-specific DHCP allocation rules without physical access to that network segment.
    Aliases: **--relay-subnet**.

**--circuit-id** *CIRCUIT_ID*
:   Inject Option 82 Sub-option 1 (Agent Circuit ID) per RFC 3046 (e.g. `Vlan100`, `ge-0/0/1`).
    Represents the incoming VLAN name or switch port.
    Use this option to test VLAN-specific or port-specific DHCP allocation rules.

**--remote-id** *REMOTE_ID*
:   Inject Option 82 Sub-option 2 (Agent Remote ID) per RFC 3046 (e.g. switch hostname or MAC address).
    Represents the physical switch identity.
    Use this option to test switch-specific access policies or server client-classes.

**--giaddr** *GIADDR*
:   Explicitly override the BOOTP Relay Agent Gateway IP address (*giaddr*).
    By default, **dhcpt** sets *giaddr* to the local interface IP address.
    Use this option to test legacy servers that do not support RFC 3527 Link Selection.

## Protocol & DHCP Packet Options

**-o** *DHCP_OPTIONS*, **--request-options** *DHCP_OPTIONS*
:   Comma-separated list of additional DHCP option codes (e.g. `12,26,66,67`) or symbolic names
    (e.g. `hostname,tftp_server_name`) to append to the Parameter Request List (Option 55).
    Any numeric code between 1 and 254 is accepted.
    Standard network parameters (Subnet Mask, Router, DNS, NTP, Domain Search, Classless Static Routes) are requested by default.
    Use this option to verify special provisioning services that rely on specific DHCP options,
    such as PXE/netboot installation servers (Option 66 TFTP server, Option 67 bootfile name),
    VoIP telephone setups (Option 43 vendor info), or MTU discovery (Option 26).
    See **--list-options** to view locally supported options and symbolic names, or consult the
    official IANA registry: <https://www.iana.org/assignments/bootp-dhcp-parameters>.

**--clear-default-options**
:   Clear the default requested RFC options list. Requests only the options explicitly supplied
    with **-o**/**--request-options**.
    Use this option to simulate minimal embedded devices, IoT hardware, or bare-metal PXE ROMs
    that only request a minimal subset of options and might misbehave when offered large option payloads.

**--no-broadcast**
:   Do not set the BOOTP broadcast flag, requesting the DHCP server to send unicast Offers.
    Use this option to test whether the DHCP server correctly supports unicast delivery to clients that do not accept broadcast traffic.

**-m** *MAC*, **--mac** *MAC*
:   Override the client hardware MAC address (format: `aa:bb:cc:dd:ee:ff`).
    Use this option to test static DHCP reservations, MAC filtering rules, or captive portal bypasses without modifying the physical NIC.

## Timing, Detection & Output Format

**-t** *TIMEOUT*, **--timeout** *TIMEOUT*
:   Timeout in seconds to wait for DHCP Offers (default: `5.0`).

**-a**, **--all**
:   Listen for the full timeout duration to capture all answering DHCP servers on the segment.
    Use this option to detect rogue, misconfigured, or duplicate DHCP servers operating on the local broadcast domain.

**-j**, **--json**
:   Output results as formatted JSON.

**-v**, **--verbose**
:   Increase logging verbosity. Can be specified multiple times (e.g. **-v** for informational
    progress messages, **-vv** for full debug logging).

**-d**, **--debug**
:   Enable detailed debug logging (frame assembly, socket operations, ARP resolution, and binary option decoding).
    Shorthand alias for **-vv**.

## Utilities & AI Integration

**-l**, **--list-interfaces**
:   List available local network interfaces, operational states (`operstate`, `carrier`),
    IP addresses, and MAC addresses, then exit.

**--list-options**
:   Display all supported RFC DHCP options and their default request status, then exit.
    For the complete global registry of assigned options, see <https://www.iana.org/assignments/bootp-dhcp-parameters>.

**--install-skill** [*TARGET*]
:   Install the bundled AI agent skill for Gemini CLI, Claude Code, or Mistral Vibe.
    Supported targets are `gemini`, `claude`, `mistral`, or `all` (default).
    When `all` is selected, **dhcpt** automatically detects which AI assistants are present on the system
    (by inspecting configuration directories `~/.gemini`, `~/.claude`, `~/.vibe` or CLI binaries in `PATH`)
    and only deploys to active environments.
    If a skill file or symlink already exists at the destination, **dhcpt** refuses to overwrite it
    unless **--force** is explicitly specified.

**--force**
:   Force overwrite of existing skill files or symlinks during **--install-skill**.

**--completion** {*zsh*,*bash*}
:   Generate shell completion script for Zsh or Bash to standard output, then exit.

**--version**
:   Print version number and exit.

**-h**, **--help**
:   Show command-line usage summary and exit.

# DHCP RELAY & LAYER 3 SIMULATION

When diagnosing DHCP issues across switches and routers, standard broadcast testing fails
because broadcasts do not cross Layer 3 boundaries.

**dhcpt** simulates a network relay agent (e.g. Cisco *ip helper-address*) by:

1.  Sending a unicast UDP packet from source port 67 to destination port 67 (standard relay forwarding per RFC 2131) to the remote DHCP server (**--dhcp-servers** / **-s**).
2.  Setting *giaddr* to the tester's machine IP so the DHCP server routes the reply back.
3.  Injecting RFC 3527 Link Selection (Option 82 Sub-option 5) with the target gateway IP (**--target-gateway**)
    to instruct the DHCP server to allocate an address from that specific subnet/VLAN pool.

This allows network administrators to test remote subnets and VLANs from anywhere with Layer 3
connectivity (including over corporate VPNs and WireGuard tunnels) without physical access
to the target broadcast domain.

For detailed packet flow diagrams, vendor configuration directives (e.g. Cisco, Juniper, Arista, Linux),
and RFC 3527 routing mechanics, see the online guide at: <https://github.com/epicade/dhcpt/blob/main/docs/relay-mechanics.md>
(or locally installed under */usr/share/doc/dhcpt/relay-mechanics.md*).

# EXIT CODES

0
:   Success: all queried DHCP servers replied, or at least one Offer was captured on broadcast.

1
:   Failure / Timeout: zero DHCP Offers received, or permission denied.

2
:   CLI usage / syntax error: missing interface, invalid IP/MAC, or unknown option.

3
:   Partial response: multi-server query (**-s**) where some servers answered but at least one timed out.

# EXAMPLES

Standard local broadcast check:

```bash
sudo dhcpt -i eth0
```

Detect rogue DHCP servers on local network:

```bash
sudo dhcpt -i eth0 --all --timeout 5
```

Simulate DHCP relay (e.g. Cisco ip helper-address) for a remote VLAN using Option 82:

```bash
sudo dhcpt -i eth0 --dhcp-servers 192.0.2.1 --target-gateway 10.50.1.1 --circuit-id Vlan100
```

Automatically detect the outgoing VPN tunnel interface when querying a remote server from a workstation:

```bash
IFACE=$(ip route get 10.1.1.1 | grep -oP 'dev \K\S+')
sudo dhcpt -i "$IFACE" --dhcp-servers 10.1.1.1 --target-gateway 10.50.1.1
```

Test across Layer 3 interfaces without MAC addresses (WireGuard or OpenVPN TUN):

```bash
sudo dhcpt -i wg0 --dhcp-servers 10.1.1.1 --target-gateway 10.50.1.1
```

Verify static reservation by spoofing client MAC:

```bash
sudo dhcpt -i eth0 -m 00:11:22:33:44:55
```

# TROUBLESHOOTING

If **dhcpt** times out without receiving DHCP Offers, use the following steps to isolate the issue:

### 1. Verify UDP Port 67 Reachability (Netcat)

When testing remote DHCP servers (especially across VPN tunnels or routed firewalls), test if UDP port 67 is accessible:

```bash
nc -z -v -u -w 2 <server_ip> 67
```

Options: **-u** (UDP mode), **-z** (zero-I/O port scan), **-v** (verbose output), **-w 2** (2-second timeout). Note that standard Linux/OpenBSD Netcat does not support GNU-style long options.

If Netcat reports *Connection to <server_ip> 67 port [udp/bootps] succeeded!* but **dhcpt** times out, UDP traffic is permitted. The server may be dropping the query due to pool exhaustion, unconfigured subnets, or missing Option 82 policies.

### 2. Verify Interface Link State

Ensure the network interface is up and has carrier signal:

```bash
ip link show <interface>
```

### 3. Inspect Detailed Packet Trees

Run **dhcpt** with **-vv** to view outgoing and incoming packet trees and Option 82 payloads:

```bash
sudo dhcpt -i <interface> -s <server_ip> -vv
```

# RFC REFERENCES

**RFC 2131**
:   Dynamic Host Configuration Protocol

**RFC 2132**
:   DHCP Options and BOOTP Vendor Extensions

**RFC 3046**
:   DHCP Relay Agent Information Option (Option 82)

**RFC 3397**
:   Dynamic Host Configuration Protocol (DHCP) Domain Search Option

**RFC 3442**
:   Classless Static Route Option for DHCPv4 (Option 121)

**RFC 3527**
:   Link Selection sub-option for the DHCP Relay Agent Information Option

# ENVIRONMENT

DHCPT_SERVER_PATTERNS
:   Space-separated wildcard search patterns (e.g. `"dhcp*.example.com"`) defined in `~/.bashrc`
    or `~/.zshrc`. Used by the Bash and Zsh completion scripts to query DHCP servers from
    **DIM - DNS and IP Management** (<https://github.com/ionos-core/dim>) via **ndcli**(1).

# AUTHORS

Emilian Schweikert (<https://github.com/epicade>)

# REPORTING BUGS

Report bugs and submit feature requests at: <https://github.com/epicade/dhcpt/issues>

# SEE ALSO

**dhclient**(8), **dhcpd**(8), **scapy**(1), **ndcli**(1)

IANA BOOTP and DHCP Parameters Registry: <https://www.iana.org/assignments/bootp-dhcp-parameters>

DHCP Relay Architecture Guide: <https://github.com/epicade/dhcpt/blob/main/docs/relay-mechanics.md>
(installed locally at */usr/share/doc/dhcpt/relay-mechanics.md*)
