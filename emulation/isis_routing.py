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

from emulation_utils import compute_net_address


FRR_CONF_DIR = "/tmp/frr_configs"
FRR_BIN_DIR = None  # Detected at runtime by check_frr_installed()

# Area-based routing state (set by setup_isis_network)
_area_config = {
    'enabled': False,
    'sat_planes': {},   # {sat_id: plane_id}
    'link_map': {},     # {sat_id: {label: {'intf': str, 'type': str, ...}}}
}


def check_frr_installed():
    """Check if FRRouting is installed, return and cache the bin directory."""
    global FRR_BIN_DIR

    frr_dirs = [
        "/usr/lib/frr",
        "/usr/sbin",
        "/usr/local/sbin",
    ]

    for d in frr_dirs:
        if os.path.exists(f"{d}/isisd") and os.path.exists(f"{d}/zebra"):
            FRR_BIN_DIR = d
            info(f"*** FRR binaries found in {d}\n")
            return d

    # Try which as fallback
    result = os.popen("which isisd 2>/dev/null").read().strip()
    if result:
        FRR_BIN_DIR = os.path.dirname(result)
        info(f"*** FRR binaries found via which: {FRR_BIN_DIR}\n")
        return FRR_BIN_DIR

    warn("FRRouting (isisd) not found. Install with: sudo apt-get install frr\n")
    warn("Then enable ISIS: sudo sed -i 's/isisd=no/isisd=yes/' /etc/frr/daemons\n")
    return None


def generate_isis_config(hostname: str, interfaces: list, is_gs: bool = False,
                         plane_id: int = None, intf_types: dict = None) -> str:
    """
    Generate FRR ISIS configuration for a node

    Args:
        hostname: Node hostname (sat0, gs1, etc.)
        interfaces: List of interface names
        is_gs: True if this is a ground station
        plane_id: Orbital plane ID (0-7) for area-based routing. None = flat L2-only.
        intf_types: Dict {intf_name: 'intra-plane'|'inter-plane'|'gs'} for per-interface circuit type.
                    Only used when plane_id is set.

    Returns:
        FRR configuration string
    """
    use_areas = plane_id is not None
    if intf_types is None:
        intf_types = {}

    # ISIS NET address — délégué à emulation_utils.compute_net_address
    net_address = compute_net_address(hostname, is_gs, plane_id if use_areas else None)

    # Node type: flat = L2-only, areas = L1/L2 for sats (they all have inter-plane links)
    # GS nodes are L1-only (they connect within one area)
    if use_areas:
        if is_gs:
            is_type = "level-1"
        else:
            is_type = "level-1-2"
    else:
        is_type = "level-2-only"

    config = f"""! FRR configuration for {hostname}
frr version 8.1
frr defaults traditional
hostname {hostname}
log syslog informational
no ipv6 forwarding
!
router isis SAT
  net {net_address}
  is-type {is_type}
  metric-style wide
  lsp-gen-interval 1
  spf-interval 1
!
"""

    # Add interface configurations
    for intf in interfaces:
        if intf == 'lo':
            continue

        # Determine circuit-type per interface
        if use_areas and intf in intf_types:
            link_type = intf_types[intf]
            if link_type == 'inter-plane':
                circuit_type = "level-2-only"
            else:
                # intra-plane and gs links are L1
                circuit_type = "level-1"
        else:
            circuit_type = is_type if not use_areas else "level-1"

        config += f"""interface {intf}
  ip router isis SAT
  isis circuit-type {circuit_type}
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


def setup_isis_node(host, is_gs: bool = False, plane_id: int = None,
                    intf_types: dict = None):
    """
    Configure ISIS routing on a single Mininet host

    Args:
        host: Mininet host object
        is_gs: True if this is a ground station
        plane_id: Orbital plane ID for area-based routing. None = flat L2-only.
        intf_types: Dict {intf_name: 'intra-plane'|'inter-plane'|'gs'}
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
    isis_conf = generate_isis_config(hostname, interfaces, is_gs,
                                     plane_id=plane_id, intf_types=intf_types)
    zebra_conf = generate_zebra_config(hostname)
    daemons_conf = generate_daemons_config()

    # Write configurations
    (conf_dir / "isisd.conf").write_text(isis_conf)
    (conf_dir / "zebra.conf").write_text(zebra_conf)
    (conf_dir / "daemons").write_text(daemons_conf)

    # Ensure frr user can read configs
    os.system(f"chown -R frr:frr {conf_dir}")

    # Enable IP forwarding
    host.cmd('sysctl -w net.ipv4.ip_forward=1')

    # Start FRR daemons in the host's namespace
    pid_dir = f"/tmp/frr_pids/{hostname}"
    host.cmd(f'mkdir -p {pid_dir}')
    host.cmd(f'chown -R frr:frr {pid_dir}')
    host.cmd(f'chmod 755 {pid_dir}')

    zebra_bin = f"{FRR_BIN_DIR}/zebra"
    isisd_bin = f"{FRR_BIN_DIR}/isisd"

    # Start zebra first (required by other daemons)
    # Capture stderr to detect startup failures
    zebra_out = host.cmd(f'{zebra_bin} -d -f {conf_dir}/zebra.conf '
                         f'-i {pid_dir}/zebra.pid '
                         f'-z {pid_dir}/zebra.sock '
                         f'--vty_socket {pid_dir} 2>&1')
    if zebra_out.strip():
        warn(f"*** [{hostname}] zebra output: {zebra_out.strip()}\n")

    time.sleep(0.5)  # Wait for zebra to start

    # Verify zebra actually started by checking PID file
    zebra_pid = host.cmd(f'cat {pid_dir}/zebra.pid 2>/dev/null').strip()
    if not zebra_pid or not zebra_pid.isdigit():
        error(f"*** [{hostname}] zebra FAILED to start! No PID file.\n")
        error(f"*** [{hostname}] Config was:\n{zebra_conf}\n")
        return False

    zebra_alive = host.cmd(f'kill -0 {zebra_pid} 2>&1').strip()
    if zebra_alive:
        error(f"*** [{hostname}] zebra PID {zebra_pid} is NOT running: {zebra_alive}\n")
        return False

    # Verify zebra VTY socket exists
    vty_check = host.cmd(f'ls {pid_dir}/zebra.vty 2>&1').strip()
    if 'No such file' in vty_check:
        warn(f"*** [{hostname}] zebra.vty socket not found, waiting 1s more...\n")
        time.sleep(1)
        vty_check = host.cmd(f'ls {pid_dir}/zebra.vty 2>&1').strip()
        if 'No such file' in vty_check:
            error(f"*** [{hostname}] zebra.vty still missing! Contents of {pid_dir}:\n")
            error(f"    {host.cmd(f'ls -la {pid_dir}/')}\n")
            return False

    # Start isisd
    isisd_out = host.cmd(f'{isisd_bin} -d -f {conf_dir}/isisd.conf '
                         f'-i {pid_dir}/isisd.pid '
                         f'-z {pid_dir}/zebra.sock '
                         f'--vty_socket {pid_dir} 2>&1')
    if isisd_out.strip():
        warn(f"*** [{hostname}] isisd output: {isisd_out.strip()}\n")

    time.sleep(0.3)

    # Verify isisd started
    isisd_pid = host.cmd(f'cat {pid_dir}/isisd.pid 2>/dev/null').strip()
    if not isisd_pid or not isisd_pid.isdigit():
        error(f"*** [{hostname}] isisd FAILED to start! No PID file.\n")
        return False

    return True


def setup_isis_network(net, sat_hosts: dict, gs_hosts: dict,
                       sat_planes: dict = None, link_map: dict = None):
    """
    Configure ISIS routing on all nodes in the network

    Args:
        net: Mininet network
        sat_hosts: Dictionary of satellite hosts {sat_id: host}
        gs_hosts: Dictionary of ground station hosts {gs_id: host}
        sat_planes: Dict {sat_id: plane_id} for area-based routing. None = flat L2-only.
        link_map: Dict {sat_id: {label: {'intf': str, 'type': str, ...}}} for interface types.
    """
    if not check_frr_installed():
        warn("*** ISIS setup skipped - FRR not installed\n")
        return False

    use_areas = sat_planes is not None and len(sat_planes) > 0

    # Store area config globally for dynamic link additions (GS connect/handover)
    _area_config['enabled'] = use_areas
    _area_config['sat_planes'] = sat_planes or {}
    _area_config['link_map'] = link_map or {}

    if use_areas:
        info("*** Setting up ISIS routing with AREAS (1 area per orbital plane)...\n")
        planes_set = sorted(set(sat_planes.values()))
        info(f"    Areas: {len(planes_set)} planes -> areas {['49.%04d' % (p+1) for p in planes_set]}\n")
    else:
        info("*** Setting up ISIS routing (flat L2-only)...\n")

    # Clean up any previous FRR configs
    os.system(f"rm -rf {FRR_CONF_DIR}")
    os.system("rm -rf /tmp/frr_pids")
    os.makedirs(FRR_CONF_DIR, exist_ok=True)
    os.makedirs("/tmp/frr_pids", exist_ok=True)
    os.system(f"chown -R frr:frr {FRR_CONF_DIR}")
    os.system("chown -R frr:frr /tmp/frr_pids")

    configured_count = 0

    # Build per-satellite interface type mapping from link_map
    sat_intf_types = {}  # {sat_id: {intf_name: link_type}}
    if use_areas and link_map:
        for sat_id, labels in link_map.items():
            sat_intf_types[sat_id] = {}
            for label, info_dict in labels.items():
                sat_intf_types[sat_id][info_dict['intf']] = info_dict['type']

    # Configure satellites
    for sat_id, host in sat_hosts.items():
        plane_id = sat_planes.get(sat_id) if use_areas else None
        intf_types = sat_intf_types.get(sat_id, {}) if use_areas else None
        if setup_isis_node(host, is_gs=False, plane_id=plane_id, intf_types=intf_types):
            configured_count += 1

    # Configure ground stations (if they have interfaces)
    # GS joins the area of its connected satellite
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
        hostname = host.name
        pid_dir = f"/tmp/frr_pids/{hostname}"
        # Kill by PID file for precision
        host.cmd(f'if [ -f {pid_dir}/isisd.pid ]; then kill $(cat {pid_dir}/isisd.pid) 2>/dev/null; fi')
        host.cmd(f'if [ -f {pid_dir}/zebra.pid ]; then kill $(cat {pid_dir}/zebra.pid) 2>/dev/null; fi')

    # Fallback: kill any remaining
    os.system('pkill -f "zebra.*-i /tmp/frr_pids" 2>/dev/null')
    os.system('pkill -f "isisd.*-i /tmp/frr_pids" 2>/dev/null')

    os.system(f"rm -rf {FRR_CONF_DIR}")
    os.system("rm -rf /tmp/frr_pids")


def _vtysh(host, command):
    """Execute a vtysh command on a host."""
    hostname = host.name
    return host.cmd(
        f'vtysh --vty_socket /tmp/frr_pids/{hostname} -c "{command}"'
    )


def _vtysh_config(host, commands):
    """Execute a list of vtysh configure-terminal commands on a host."""
    hostname = host.name
    cmd_str = ' '.join(f'-c "{c}"' for c in ['configure terminal'] + commands)
    return host.cmd(
        f'vtysh --vty_socket /tmp/frr_pids/{hostname} {cmd_str}'
    )


def add_interface_to_isis(host, intf_name, link_type: str = None):
    """
    Dynamically add an interface to ISIS via vtysh (no daemon restart).
    Used for satellites that already have ISIS running.

    Args:
        link_type: 'intra-plane', 'inter-plane', or 'gs'. Used for circuit-type in area mode.
    """
    # Determine circuit type
    if _area_config['enabled'] and link_type:
        if link_type == 'inter-plane':
            circuit_type = "level-2-only"
        else:
            circuit_type = "level-1"
    else:
        circuit_type = "level-2-only"

    result = _vtysh_config(host, [
        f'interface {intf_name}',
        'ip router isis SAT',
        f'isis circuit-type {circuit_type}',
        'isis metric 10',
        'isis hello-interval 1',
        'isis hello-multiplier 3',
    ])
    if 'error' in result.lower() or 'Unknown' in result:
        warn(f"*** [{host.name}] vtysh config error for {intf_name}: {result.strip()}\n")
        return False
    info(f"*** [{host.name}] Interface {intf_name} added to ISIS dynamically\n")
    return True


def setup_isis_gs(host, connected_sat_id: int = None):
    """
    Full ISIS setup for a ground station (first connect).
    Starts zebra + isisd from scratch.

    Args:
        connected_sat_id: Satellite ID the GS is connecting to (for area assignment).
    """
    hostname = host.name
    interfaces = [intf.name for intf in host.intfList() if intf.name != 'lo']

    if not interfaces:
        return

    pid_dir = f"/tmp/frr_pids/{hostname}"
    conf_dir = Path(f"{FRR_CONF_DIR}/{hostname}")
    conf_dir.mkdir(parents=True, exist_ok=True)

    zebra_bin = f"{FRR_BIN_DIR}/zebra" if FRR_BIN_DIR else "zebra"
    isisd_bin = f"{FRR_BIN_DIR}/isisd" if FRR_BIN_DIR else "isisd"

    # Determine area from connected satellite
    plane_id = None
    if _area_config['enabled'] and connected_sat_id is not None:
        plane_id = _area_config['sat_planes'].get(connected_sat_id)

    # Generate configs
    isis_conf = generate_isis_config(hostname, interfaces, is_gs=True, plane_id=plane_id)
    zebra_conf = generate_zebra_config(hostname)
    (conf_dir / "isisd.conf").write_text(isis_conf)
    (conf_dir / "zebra.conf").write_text(zebra_conf)
    os.system(f"chown -R frr:frr {conf_dir}")

    host.cmd(f'mkdir -p {pid_dir}')
    host.cmd(f'chown -R frr:frr {pid_dir}')

    # Check if zebra already running (from a previous connect)
    zebra_pid = host.cmd(f'cat {pid_dir}/zebra.pid 2>/dev/null').strip()
    zebra_running = False
    if zebra_pid and zebra_pid.isdigit():
        check = host.cmd(f'kill -0 {zebra_pid} 2>&1').strip()
        zebra_running = (check == '')

    if not zebra_running:
        host.cmd('sysctl -w net.ipv4.ip_forward=1')
        host.cmd(f'{zebra_bin} -d -f {conf_dir}/zebra.conf '
                 f'-i {pid_dir}/zebra.pid '
                 f'-z {pid_dir}/zebra.sock '
                 f'--vty_socket {pid_dir} 2>&1')
        time.sleep(0.5)
        info(f"*** [{hostname}] zebra started\n")

    # Kill existing isisd (if reconnect) then start fresh
    host.cmd(f'if [ -f {pid_dir}/isisd.pid ]; then kill $(cat {pid_dir}/isisd.pid) 2>/dev/null; fi')
    time.sleep(0.2)

    host.cmd(f'{isisd_bin} -d -f {conf_dir}/isisd.conf '
             f'-i {pid_dir}/isisd.pid '
             f'-z {pid_dir}/zebra.sock '
             f'--vty_socket {pid_dir} 2>&1')
    time.sleep(0.3)  # Wait for VTY socket

    info(f"*** [{hostname}] ISIS started ({len(interfaces)} interfaces)\n")


def update_isis_for_new_link(host, connected_sat_id: int = None):
    """
    Update ISIS when a new link is added.
    - For GS: full setup (start zebra + isisd if needed)
    - For satellites: dynamic interface add via vtysh (NO restart)

    Args:
        connected_sat_id: For GS nodes, the sat_id they're connecting to (for area assignment).
    """
    hostname = host.name

    if hostname.startswith('gs'):
        setup_isis_gs(host, connected_sat_id=connected_sat_id)
    else:
        # Satellite: ISIS already running, just add the new interface dynamically
        interfaces = [intf.name for intf in host.intfList() if intf.name != 'lo']
        if not interfaces:
            return

        # The newest interface is the last one
        new_intf = interfaces[-1]

        # Check if isisd is running
        pid_dir = f"/tmp/frr_pids/{hostname}"
        isisd_pid = host.cmd(f'cat {pid_dir}/isisd.pid 2>/dev/null').strip()
        if isisd_pid and isisd_pid.isdigit():
            check = host.cmd(f'kill -0 {isisd_pid} 2>&1').strip()
            if check == '':
                # isisd running, add interface dynamically
                # GS links are L1 in area mode
                add_interface_to_isis(host, new_intf, link_type='gs')
                return

        # isisd not running (shouldn't happen for satellites), fallback to full setup
        sat_id = int(hostname.replace('sat', ''))
        plane_id = _area_config['sat_planes'].get(sat_id) if _area_config['enabled'] else None
        warn(f"*** [{hostname}] isisd not running, doing full setup\n")
        setup_isis_node(host, is_gs=False, plane_id=plane_id)


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
