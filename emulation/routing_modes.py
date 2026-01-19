#!/usr/bin/env python3
"""
Routing Modes for LEO Constellation Mininet Emulation
Supports ISL-only and GS-bounce routing for research comparison

This module provides:
- ISL-only routing: Traditional satellite-only paths
- GS-bounce routing: Allow intermediate GS hops
- Dynamic route installation in Mininet
- Route switching for A/B testing
"""

import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict
from enum import Enum

from path_comparator import ConstellationGraph, PathResult


class RoutingMode(Enum):
    """Available routing modes"""
    ISL_ONLY = "isl_only"       # Traditional: GS → Sat chain → GS
    GS_BOUNCE = "gs_bounce"    # Allow: GS → Sat → GS_mid → Sat → GS


@dataclass
class Route:
    """Represents a route in the network"""
    source: str
    destination: str
    path: List[str]
    next_hop: str
    interface: str
    latency_ms: float
    mode: RoutingMode


class MininetRouteManager:
    """
    Manages routes in Mininet network for routing mode experiments

    Integrates with path_comparator for route computation
    and installs routes dynamically in Mininet hosts
    """

    def __init__(self, net, graph: ConstellationGraph):
        """
        Initialize route manager

        Args:
            net: Mininet network instance
            graph: ConstellationGraph with topology
        """
        self.net = net
        self.graph = graph
        self.current_mode = RoutingMode.ISL_ONLY
        self.installed_routes: Dict[str, List[Route]] = defaultdict(list)

        # Map node IDs to Mininet hosts
        self.host_map: Dict[str, object] = {}
        self._build_host_map()

        # IP address mapping: {node_id: {neighbor_id: (local_ip, remote_ip)}}
        self.ip_map: Dict[str, Dict[str, Tuple[str, str]]] = defaultdict(dict)

    def _build_host_map(self):
        """Build mapping from node IDs to Mininet hosts"""
        for host in self.net.hosts:
            self.host_map[host.name] = host

    def discover_interfaces(self):
        """
        Discover IP addresses and interfaces from Mininet network

        Must be called after network is started
        """
        for host in self.net.hosts:
            host_id = host.name

            for intf in host.intfList():
                if intf.name == 'lo':
                    continue

                # Get IP and find connected peer
                ip = intf.IP()
                if not ip:
                    continue

                link = intf.link
                if link:
                    # Find peer interface
                    if link.intf1 == intf:
                        peer_intf = link.intf2
                    else:
                        peer_intf = link.intf1

                    peer_id = peer_intf.node.name
                    peer_ip = peer_intf.IP()

                    if peer_ip:
                        self.ip_map[host_id][peer_id] = (ip, peer_ip)

    def set_routing_mode(self, mode: RoutingMode):
        """
        Set the active routing mode

        Args:
            mode: RoutingMode to activate
        """
        if mode == self.current_mode:
            return

        print(f"Switching routing mode: {self.current_mode.value} → {mode.value}")
        self.current_mode = mode

        # Clear existing routes and recompute
        self.clear_all_routes()
        self.install_all_routes()

    def compute_routes_for_mode(self, mode: RoutingMode) -> Dict[str, List[Route]]:
        """
        Compute all routes for a given mode

        Args:
            mode: Routing mode

        Returns:
            Dict mapping source to list of routes
        """
        routes = defaultdict(list)

        # Get all GS pairs
        gs_list = sorted(self.graph.ground_stations)

        for gs_src in gs_list:
            for gs_dst in gs_list:
                if gs_src == gs_dst:
                    continue

                if mode == RoutingMode.ISL_ONLY:
                    path_result = self.graph.compute_isl_only_path(gs_src, gs_dst)
                else:
                    path_result = self.graph.compute_gs_bounce_path(gs_src, gs_dst)

                if path_result:
                    route = self._path_to_route(path_result, mode)
                    if route:
                        routes[gs_src].append(route)

        return routes

    def _path_to_route(self, path_result: PathResult, mode: RoutingMode) -> Optional[Route]:
        """Convert PathResult to Route with next-hop info"""
        if len(path_result.path) < 2:
            return None

        source = path_result.path[0]
        destination = path_result.path[-1]
        next_hop = path_result.path[1]

        # Find interface to next hop
        interface = self._find_interface(source, next_hop)

        return Route(
            source=source,
            destination=destination,
            path=path_result.path,
            next_hop=next_hop,
            interface=interface or "",
            latency_ms=path_result.total_latency_ms,
            mode=mode,
        )

    def _find_interface(self, host_id: str, neighbor_id: str) -> Optional[str]:
        """Find interface name connecting host to neighbor"""
        host = self.host_map.get(host_id)
        if not host:
            return None

        neighbor = self.host_map.get(neighbor_id)
        if not neighbor:
            return None

        for intf in host.intfList():
            if intf.link:
                link = intf.link
                if link.intf1.node == neighbor or link.intf2.node == neighbor:
                    return intf.name

        return None

    def install_all_routes(self):
        """Install routes for current mode on all hosts"""
        routes = self.compute_routes_for_mode(self.current_mode)

        installed_count = 0
        for source, route_list in routes.items():
            for route in route_list:
                if self._install_route(route):
                    self.installed_routes[source].append(route)
                    installed_count += 1

        print(f"Installed {installed_count} routes for mode: {self.current_mode.value}")

    def _install_route(self, route: Route) -> bool:
        """
        Install a single route in Mininet host

        Uses Linux ip route commands
        """
        host = self.host_map.get(route.source)
        if not host:
            return False

        # Get destination IP
        dest_host = self.host_map.get(route.destination)
        if not dest_host:
            return False

        # Get next-hop IP
        next_hop_info = self.ip_map.get(route.source, {}).get(route.next_hop)
        if not next_hop_info:
            return False

        _, next_hop_ip = next_hop_info

        # Get destination network (simplified: use first interface IP)
        dest_ip = None
        for intf in dest_host.intfList():
            if intf.name != 'lo' and intf.IP():
                dest_ip = intf.IP()
                break

        if not dest_ip:
            return False

        # Install route via ip command
        try:
            cmd = f"ip route add {dest_ip}/32 via {next_hop_ip}"
            host.cmd(cmd)
            return True
        except Exception as e:
            print(f"Failed to install route: {e}")
            return False

    def clear_all_routes(self):
        """Clear all installed routes"""
        for source, routes in self.installed_routes.items():
            host = self.host_map.get(source)
            if not host:
                continue

            for route in routes:
                self._remove_route(host, route)

        self.installed_routes.clear()
        print("Cleared all routes")

    def _remove_route(self, host, route: Route) -> bool:
        """Remove a route from host"""
        dest_host = self.host_map.get(route.destination)
        if not dest_host:
            return False

        dest_ip = None
        for intf in dest_host.intfList():
            if intf.name != 'lo' and intf.IP():
                dest_ip = intf.IP()
                break

        if not dest_ip:
            return False

        try:
            cmd = f"ip route del {dest_ip}/32"
            host.cmd(cmd)
            return True
        except:
            return False

    def get_route_info(self, source: str, destination: str) -> Optional[Route]:
        """Get current route between source and destination"""
        for route in self.installed_routes.get(source, []):
            if route.destination == destination:
                return route
        return None

    def compare_modes(self, source: str, destination: str) -> Dict:
        """
        Compare both routing modes for a specific pair

        Returns latency and hop count for each mode
        """
        isl_path = self.graph.compute_isl_only_path(source, destination)
        gs_path = self.graph.compute_gs_bounce_path(source, destination)

        return {
            'source': source,
            'destination': destination,
            'isl_only': {
                'latency_ms': isl_path.total_latency_ms if isl_path else None,
                'hops': isl_path.hop_count if isl_path else None,
                'path': isl_path.path if isl_path else None,
            },
            'gs_bounce': {
                'latency_ms': gs_path.total_latency_ms if gs_path else None,
                'hops': gs_path.hop_count if gs_path else None,
                'path': gs_path.path if gs_path else None,
                'gs_bounces': gs_path.gs_bounces if gs_path else 0,
            },
            'gs_bounce_beneficial': (
                gs_path and isl_path and
                gs_path.total_latency_ms < isl_path.total_latency_ms
            ),
        }


class RoutingExperiment:
    """
    Experiment runner for comparing routing modes

    Runs same traffic patterns under both modes and collects metrics
    """

    def __init__(self, net, graph: ConstellationGraph):
        self.net = net
        self.graph = graph
        self.route_manager = MininetRouteManager(net, graph)
        self.results: List[Dict] = []

    def setup(self):
        """Setup experiment after network is started"""
        self.route_manager.discover_interfaces()

    def run_ping_test(self, source: str, destination: str,
                      count: int = 10, mode: RoutingMode = None) -> Dict:
        """
        Run ping test between two nodes

        Args:
            source: Source node ID
            destination: Destination node ID
            count: Number of pings
            mode: Routing mode (None = current mode)

        Returns:
            Dict with ping results
        """
        if mode and mode != self.route_manager.current_mode:
            self.route_manager.set_routing_mode(mode)

        src_host = self.route_manager.host_map.get(source)
        dst_host = self.route_manager.host_map.get(destination)

        if not src_host or not dst_host:
            return {'error': 'Host not found'}

        # Get destination IP
        dst_ip = None
        for intf in dst_host.intfList():
            if intf.name != 'lo' and intf.IP():
                dst_ip = intf.IP()
                break

        if not dst_ip:
            return {'error': 'No destination IP'}

        # Run ping
        result = src_host.cmd(f'ping -c {count} -q {dst_ip}')

        # Parse results
        return self._parse_ping_output(result, source, destination)

    def _parse_ping_output(self, output: str, source: str, destination: str) -> Dict:
        """Parse ping command output"""
        result = {
            'source': source,
            'destination': destination,
            'mode': self.route_manager.current_mode.value,
        }

        lines = output.strip().split('\n')

        for line in lines:
            if 'packets transmitted' in line:
                parts = line.split(',')
                for part in parts:
                    if 'transmitted' in part:
                        result['packets_sent'] = int(part.strip().split()[0])
                    elif 'received' in part:
                        result['packets_received'] = int(part.strip().split()[0])
                    elif 'loss' in part:
                        result['packet_loss'] = part.strip()

            elif 'rtt min/avg/max' in line or 'round-trip' in line:
                # Parse: rtt min/avg/max/mdev = 1.234/2.345/3.456/0.123 ms
                try:
                    stats = line.split('=')[1].strip().split()[0]
                    values = stats.split('/')
                    result['rtt_min_ms'] = float(values[0])
                    result['rtt_avg_ms'] = float(values[1])
                    result['rtt_max_ms'] = float(values[2])
                    if len(values) > 3:
                        result['rtt_mdev_ms'] = float(values[3])
                except:
                    pass

        return result

    def run_comparative_test(self, source: str, destination: str,
                            ping_count: int = 20) -> Dict:
        """
        Run same test under both routing modes

        Args:
            source: Source GS
            destination: Destination GS
            ping_count: Pings per mode

        Returns:
            Comparative results
        """
        results = {
            'source': source,
            'destination': destination,
            'theoretical': self.route_manager.compare_modes(source, destination),
        }

        # Test ISL-only mode
        print(f"Testing ISL-only: {source} → {destination}")
        results['isl_only_measured'] = self.run_ping_test(
            source, destination, ping_count, RoutingMode.ISL_ONLY
        )

        # Test GS-bounce mode
        print(f"Testing GS-bounce: {source} → {destination}")
        results['gs_bounce_measured'] = self.run_ping_test(
            source, destination, ping_count, RoutingMode.GS_BOUNCE
        )

        # Compare
        isl_rtt = results['isl_only_measured'].get('rtt_avg_ms', float('inf'))
        gs_rtt = results['gs_bounce_measured'].get('rtt_avg_ms', float('inf'))

        results['measured_improvement_ms'] = isl_rtt - gs_rtt
        results['gs_bounce_faster'] = gs_rtt < isl_rtt

        self.results.append(results)
        return results

    def run_full_experiment(self, ping_count: int = 20) -> List[Dict]:
        """Run comparative tests for all GS pairs"""
        gs_list = sorted(self.graph.ground_stations)

        print(f"\nRunning full experiment with {len(gs_list)} ground stations")
        print("=" * 60)

        for i, gs_src in enumerate(gs_list):
            for gs_dst in gs_list[i+1:]:
                print(f"\n[{len(self.results)+1}] {gs_src} ↔ {gs_dst}")
                self.run_comparative_test(gs_src, gs_dst, ping_count)

        return self.results

    def print_summary(self):
        """Print experiment summary"""
        if not self.results:
            print("No results to summarize")
            return

        print("\n" + "=" * 80)
        print("EXPERIMENT SUMMARY")
        print("=" * 80)

        beneficial_count = 0
        total_improvement = 0

        for r in self.results:
            src = r['source']
            dst = r['destination']

            isl_rtt = r['isl_only_measured'].get('rtt_avg_ms', 'N/A')
            gs_rtt = r['gs_bounce_measured'].get('rtt_avg_ms', 'N/A')
            improvement = r.get('measured_improvement_ms', 0)

            status = "✓ GS-bounce FASTER" if r.get('gs_bounce_faster') else "✗ ISL-only faster"

            print(f"\n{src} → {dst}")
            print(f"  ISL-only RTT:  {isl_rtt:.2f}ms" if isinstance(isl_rtt, float) else f"  ISL-only RTT:  {isl_rtt}")
            print(f"  GS-bounce RTT: {gs_rtt:.2f}ms" if isinstance(gs_rtt, float) else f"  GS-bounce RTT: {gs_rtt}")
            print(f"  {status} ({improvement:+.2f}ms)")

            if r.get('gs_bounce_faster'):
                beneficial_count += 1
                total_improvement += improvement

        print("\n" + "=" * 80)
        print(f"Total pairs: {len(self.results)}")
        print(f"GS-bounce beneficial: {beneficial_count} ({beneficial_count/len(self.results)*100:.1f}%)")
        if beneficial_count > 0:
            print(f"Average improvement when beneficial: {total_improvement/beneficial_count:.2f}ms")


# CLI interface
if __name__ == "__main__":
    print("Routing Modes Module")
    print("This module is designed to be imported by mininet_gs_timeseries.py")
    print("\nUsage in Mininet script:")
    print("  from routing_modes import RoutingExperiment, RoutingMode")
    print("  experiment = RoutingExperiment(net, graph)")
    print("  experiment.setup()")
    print("  experiment.run_full_experiment()")
