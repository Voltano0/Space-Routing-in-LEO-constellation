#!/usr/bin/env python3
"""
ISIS Routing Configuration for Satellite Constellation Mininet
Uses FRRouting (FRR) to enable IS-IS routing protocol on all satellites and ground stations

Prerequisites:
    sudo apt-get install frr frr-pythontools

Usage:
    Called automatically from mininet_gs_timeseries.py after network creation
"""

import os
import time
from pathlib import Path
from mininet.log import info, warn, error


FRR_CONF_DIR = "/tmp/frr_configs"


def check_frr_installed():
    """Check if FRRouting is installed"""
    # Check common FRR paths
    frr_paths = [
        "/usr/lib/frr/isisd",
        "/usr/sbin/isisd",
        "/usr/local/sbin/isisd",
    ]

    for path in frr_paths:
        if os.path.exists(path):
            return path

    # Try which as fallback
    result = os.system("which isisd > /dev/null 2>&1")
    if result == 0:
        return "isisd"

    warn("FRRouting (isisd) not found. Install with: sudo apt-get install frr\n")
    warn("Then enable ISIS: sudo sed -i 's/isisd=no/isisd=yes/' /etc/frr/daemons\n")
    return None


def generate_isis_config(hostname: str, interfaces: list, is_gs: bool = False) -> str:
    """
    Generate FRR ISIS configuration for a node

    Args:
        hostname: Node hostname (sat0, gs1, etc.)
        interfaces: List of interface names
        is_gs: True if this is a ground station

    Returns:
        FRR configuration string
    """
    # ISIS NET address format: 49.0001.XXXX.XXXX.XXXX.00
    # We use the hostname to generate a unique system ID
    if is_gs:
        # Ground stations: gs1 -> 0000.0000.0001
        gs_num = int(hostname.replace('gs', ''))
        sys_id = f"0000.0000.{gs_num:04d}"
    else:
        # Satellites: sat42 -> 0000.0000.1042
        sat_num = int(hostname.replace('sat', ''))
        sys_id = f"0000.0001.{sat_num:04d}"

    net_address = f"49.0001.{sys_id}.00"

    config = f"""! FRR configuration for {hostname}
frr version 8.1
frr defaults traditional
hostname {hostname}
log syslog informational
no ipv6 forwarding
!
router isis SAT
  net {net_address}
  is-type level-2-only
  metric-style wide
  lsp-gen-interval 1
  spf-interval 1
!
"""

    # Add interface configurations
    for intf in interfaces:
        if intf != 'lo':
            config += f"""interface {intf}
  ip router isis SAT
  isis circuit-type level-2-only
  isis metric 10
  isis hello-interval 1
  isis hello-multiplier 3
!
"""

    return config


def generate_zebra_config(hostname: str) -> str:
    """Generate Zebra (FRR base) configuration"""
    return f"""! Zebra configuration for {hostname}
frr version 8.1
frr defaults traditional
hostname {hostname}
log syslog informational
!
"""


def generate_daemons_config() -> str:
    """Generate FRR daemons configuration"""
    return """# FRR daemons configuration
zebra=yes
isisd=yes
staticd=no
bgpd=no
ospfd=no
ospf6d=no
ripd=no
ripngd=no
"""


def setup_isis_node(host, is_gs: bool = False):
    """
    Configure ISIS routing on a single Mininet host

    Args:
        host: Mininet host object
        is_gs: True if this is a ground station
    """
    hostname = host.name

    # Get all interfaces except loopback
    interfaces = []
    for intf in host.intfList():
        if intf.name != 'lo':
            interfaces.append(intf.name)

    if not interfaces:
        # No interfaces yet (GS before connection)
        return False

    # Create config directory for this host
    conf_dir = Path(f"{FRR_CONF_DIR}/{hostname}")
    conf_dir.mkdir(parents=True, exist_ok=True)

    # Generate configurations
    isis_conf = generate_isis_config(hostname, interfaces, is_gs)
    zebra_conf = generate_zebra_config(hostname)
    daemons_conf = generate_daemons_config()

    # Write configurations
    (conf_dir / "isisd.conf").write_text(isis_conf)
    (conf_dir / "zebra.conf").write_text(zebra_conf)
    (conf_dir / "daemons").write_text(daemons_conf)

    # Enable IP forwarding
    host.cmd('sysctl -w net.ipv4.ip_forward=1')

    # Start FRR daemons in the host's namespace
    # Note: This requires FRR to be installed on the system
    pid_dir = f"/tmp/frr_pids/{hostname}"
    host.cmd(f'mkdir -p {pid_dir}')

    # Start zebra first (required by other daemons)
    host.cmd(f'zebra -d -f {conf_dir}/zebra.conf '
             f'-i {pid_dir}/zebra.pid '
             f'-z {pid_dir}/zebra.sock '
             f'--vty_socket {pid_dir}')

    time.sleep(0.5)  # Wait for zebra to start

    # Start isisd
    host.cmd(f'isisd -d -f {conf_dir}/isisd.conf '
             f'-i {pid_dir}/isisd.pid '
             f'-z {pid_dir}/zebra.sock '
             f'--vty_socket {pid_dir}')

    return True


def setup_isis_network(net, sat_hosts: dict, gs_hosts: dict):
    """
    Configure ISIS routing on all nodes in the network

    Args:
        net: Mininet network
        sat_hosts: Dictionary of satellite hosts {sat_id: host}
        gs_hosts: Dictionary of ground station hosts {gs_id: host}
    """
    if not check_frr_installed():
        warn("*** ISIS setup skipped - FRR not installed\n")
        return False

    info("*** Setting up ISIS routing on all nodes...\n")

    # Clean up any previous FRR configs
    os.system(f"rm -rf {FRR_CONF_DIR}")
    os.system("rm -rf /tmp/frr_pids")
    os.makedirs(FRR_CONF_DIR, exist_ok=True)

    configured_count = 0

    # Configure satellites
    for sat_id, host in sat_hosts.items():
        if setup_isis_node(host, is_gs=False):
            configured_count += 1

    # Configure ground stations (if they have interfaces)
    for gs_id, host in gs_hosts.items():
        if setup_isis_node(host, is_gs=True):
            configured_count += 1

    info(f"*** ISIS configured on {configured_count} nodes\n")
    info("*** Waiting for ISIS convergence (10s)...\n")
    time.sleep(10)

    return True


def stop_isis_network(net):
    """Stop all FRR daemons"""
    info("*** Stopping ISIS daemons...\n")

    for host in net.hosts:
        host.cmd('pkill -f "zebra.*-i /tmp/frr_pids"')
        host.cmd('pkill -f "isisd.*-i /tmp/frr_pids"')

    os.system(f"rm -rf {FRR_CONF_DIR}")
    os.system("rm -rf /tmp/frr_pids")


def update_isis_for_new_link(host):
    """
    Update ISIS configuration when a new link is added (GS connection)
    Restarts isisd to pick up new interfaces
    """
    hostname = host.name
    is_gs = hostname.startswith('gs')

    # Get current interfaces
    interfaces = [intf.name for intf in host.intfList() if intf.name != 'lo']

    if not interfaces:
        return

    # Regenerate config
    conf_dir = Path(f"{FRR_CONF_DIR}/{hostname}")
    conf_dir.mkdir(parents=True, exist_ok=True)

    isis_conf = generate_isis_config(hostname, interfaces, is_gs)
    (conf_dir / "isisd.conf").write_text(isis_conf)

    pid_dir = f"/tmp/frr_pids/{hostname}"

    # Restart isisd to pick up new config
    host.cmd('pkill -f "isisd.*-i /tmp/frr_pids"')
    time.sleep(0.2)

    host.cmd(f'isisd -d -f {conf_dir}/isisd.conf '
             f'-i {pid_dir}/isisd.pid '
             f'-z {pid_dir}/zebra.sock '
             f'--vty_socket {pid_dir}')


class SimpleRoutingManager:
    """
    Alternative: Simple static routing based on topology
    Use this if FRR is not available or too complex
    """

    def __init__(self, net):
        self.net = net
        self.routes = {}

    def compute_routes_from_json(self, data):
        """
        Compute static routes based on JSON topology
        Uses simple shortest path calculation
        """
        from collections import defaultdict
        import heapq

        # Build adjacency list from ISL links
        graph = defaultdict(list)

        for link in data.get('islLinks', []):
            sat_a = f"sat{link['satA']}"
            sat_b = f"sat{link['satB']}"
            timeseries = link.get('timeSeries', [])
            latency = timeseries[0]['latency_ms'] if timeseries else 5.0

            graph[sat_a].append((sat_b, latency))
            graph[sat_b].append((sat_a, latency))

        # Compute shortest paths from each node using Dijkstra
        nodes = list(graph.keys())

        for source in nodes:
            dist = {node: float('inf') for node in nodes}
            dist[source] = 0
            prev = {node: None for node in nodes}
            pq = [(0, source)]

            while pq:
                d, u = heapq.heappop(pq)
                if d > dist[u]:
                    continue
                for v, w in graph[u]:
                    if dist[u] + w < dist[v]:
                        dist[v] = dist[u] + w
                        prev[v] = u
                        heapq.heappush(pq, (dist[v], v))

            # Store next-hop for each destination
            self.routes[source] = {}
            for dest in nodes:
                if dest != source and prev[dest]:
                    # Trace back to find first hop
                    hop = dest
                    while prev[hop] != source:
                        hop = prev[hop]
                    self.routes[source][dest] = hop

    def install_routes(self):
        """Install computed routes on all hosts"""
        info("*** Installing static routes...\n")

        for source, destinations in self.routes.items():
            host = self.net.get(source)
            if not host:
                continue

            for dest, next_hop in destinations.items():
                next_host = self.net.get(next_hop)
                if not next_host:
                    continue

                # Find the interface to next_hop
                for intf in host.intfList():
                    if intf.link:
                        link = intf.link
                        peer = link.intf2.node if link.intf1.node == host else link.intf1.node
                        if peer.name == next_hop:
                            # Get next-hop IP
                            peer_intf = link.intf2 if link.intf1.node == host else link.intf1
                            next_hop_ip = peer_intf.IP()
                            if next_hop_ip:
                                # Get destination network
                                dest_host = self.net.get(dest)
                                for dest_intf in dest_host.intfList():
                                    dest_ip = dest_intf.IP()
                                    if dest_ip and dest_ip != '127.0.0.1':
                                        # Add route
                                        host.cmd(f'ip route add {dest_ip}/32 via {next_hop_ip}')
                            break

        info("*** Static routes installed\n")


def setup_simple_routing(net, data):
    """
    Setup simple static routing as alternative to ISIS
    Faster and simpler, but doesn't adapt to topology changes
    """
    info("*** Setting up simple static routing...\n")

    # Enable IP forwarding on all hosts
    for host in net.hosts:
        host.cmd('sysctl -w net.ipv4.ip_forward=1')

    manager = SimpleRoutingManager(net)
    manager.compute_routes_from_json(data)
    manager.install_routes()

    return manager
