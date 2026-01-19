#!/usr/bin/env python3
"""
Path Comparator for LEO Constellation Routing Research
Compares ISL-only paths vs GS-bounce paths

Research Question:
    Can GS-bounce routing (GS1 → Sat1 → GS_mid → SatN → GS2)
    be faster than pure ISL routing (GS1 → Sat1 → ... → SatN → GS2)?

This module provides:
- Graph representation of constellation topology
- Shortest path computation (ISL-only)
- GS-bounce path computation
- Path comparison metrics
"""

import json
import heapq
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict


# Physical constants
SPEED_OF_LIGHT_KM_S = 299792.458


@dataclass
class PathResult:
    """Result of a path computation"""
    path: List[str]  # Node IDs in order
    hop_count: int
    total_latency_ms: float
    path_type: str  # 'isl_only' or 'gs_bounce'
    gs_bounces: int = 0  # Number of intermediate GS bounces
    details: Dict = field(default_factory=dict)

    def __str__(self):
        path_str = " → ".join(self.path)
        return f"[{self.path_type}] {path_str} | {self.hop_count} hops | {self.total_latency_ms:.3f}ms"


@dataclass
class PathComparison:
    """Comparison between two routing approaches"""
    source: str
    destination: str
    isl_only: Optional[PathResult]
    gs_bounce: Optional[PathResult]

    @property
    def latency_improvement_ms(self) -> float:
        """Positive = GS-bounce is faster"""
        if not self.isl_only or not self.gs_bounce:
            return 0.0
        return self.isl_only.total_latency_ms - self.gs_bounce.total_latency_ms

    @property
    def latency_improvement_percent(self) -> float:
        if not self.isl_only or self.isl_only.total_latency_ms == 0:
            return 0.0
        return (self.latency_improvement_ms / self.isl_only.total_latency_ms) * 100

    @property
    def hop_reduction(self) -> int:
        """Positive = GS-bounce uses fewer hops"""
        if not self.isl_only or not self.gs_bounce:
            return 0
        return self.isl_only.hop_count - self.gs_bounce.hop_count

    @property
    def gs_bounce_beneficial(self) -> bool:
        """Is GS-bounce routing better?"""
        return self.latency_improvement_ms > 0


class ConstellationGraph:
    """
    Graph representation of LEO constellation for path computation

    Nodes: Satellites (sat0, sat1, ...) and Ground Stations (gs0, gs1, ...)
    Edges: ISL links (sat-sat) and GSL links (gs-sat)
    """

    def __init__(self):
        # Adjacency list: {node_id: [(neighbor_id, latency_ms), ...]}
        self.graph: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        self.satellites: Set[str] = set()
        self.ground_stations: Set[str] = set()

        # For GS-bounce: track which satellites are visible from each GS
        self.gs_visibility: Dict[str, List[Tuple[str, float]]] = defaultdict(list)

        # Metadata
        self.altitude_km: float = 550.0
        self.gs_sat_latency_ms: float = 3.67  # Default for 550km altitude

    def load_from_json(self, json_path: str, timestamp: float = 0.0):
        """
        Load topology from JSON export

        Args:
            json_path: Path to constellation JSON file
            timestamp: Time index for timeseries data (default: 0)
        """
        with open(json_path, 'r') as f:
            data = json.load(f)

        # Extract metadata
        metadata = data.get('metadata', {})
        constellation = metadata.get('constellation', {})
        self.altitude_km = constellation.get('altitude_km', 550.0)

        # Calculate default GS-Sat latency based on altitude
        self.gs_sat_latency_ms = (self.altitude_km / SPEED_OF_LIGHT_KM_S) * 1000

        # Load satellites
        topology = data.get('topology', {})
        for sat in topology.get('satellites', []):
            sat_id = f"sat{sat['id']}"
            self.satellites.add(sat_id)

        # Load ground stations
        for gs in topology.get('groundStations', []):
            gs_id = gs['id'] if gs['id'].startswith('gs') else f"gs{gs['id']}"
            self.ground_stations.add(gs_id)

        # Load ISL links
        for link in data.get('islLinks', []):
            sat_a = f"sat{link['satA']}"
            sat_b = f"sat{link['satB']}"

            # Get latency (from timeseries or average)
            if 'timeSeries' in link and link['timeSeries']:
                # Find closest timestamp
                ts = link['timeSeries']
                sample = min(ts, key=lambda s: abs(s.get('timestamp', 0) - timestamp))
                latency = sample.get('latency_ms', link.get('avgLatency_ms', 3.0))
            else:
                latency = link.get('avgLatency_ms', 3.0)

            # Add bidirectional edge
            self.graph[sat_a].append((sat_b, latency))
            self.graph[sat_b].append((sat_a, latency))

        # Load GS-Satellite visibility from gsLinks
        gs_links = data.get('gsLinks', {})
        self._load_gs_visibility(gs_links, timestamp)

        print(f"Loaded: {len(self.satellites)} satellites, {len(self.ground_stations)} GS")
        print(f"Altitude: {self.altitude_km}km, GS-Sat latency: {self.gs_sat_latency_ms:.2f}ms")

        # Debug: show GS visibility
        total_visibility = sum(len(v) for v in self.gs_visibility.values())
        print(f"GS-Sat visibility links: {total_visibility}")
        for gs_id, visible in self.gs_visibility.items():
            print(f"  {gs_id}: can see {len(visible)} satellites")

    def _load_gs_visibility(self, gs_links: Dict, timestamp: float):
        """Load GS visibility from gsLinks data"""
        timeline = gs_links.get('timeline', [])

        # Track unique GS-Sat pairs to avoid duplicates
        seen_pairs = set()

        for entry in timeline:
            gs_id = entry.get('gsId', '')
            if not gs_id.startswith('gs'):
                gs_id = f"gs{gs_id}"

            sat_id = f"sat{entry.get('satId', 0)}"

            # Skip if we've already seen this pair
            pair_key = (gs_id, sat_id)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            # Get average latency from samples
            samples = entry.get('samples', [])
            if samples:
                latencies = [s.get('latency_ms', self.gs_sat_latency_ms) for s in samples]
                latency = sum(latencies) / len(latencies)
            else:
                latency = self.gs_sat_latency_ms

            self.gs_visibility[gs_id].append((sat_id, latency))

        # Also load from events if timeline is sparse
        events = gs_links.get('events', [])
        for event in events:
            if event.get('action') == 'connect':
                gs_id = event.get('gsId', '')
                if not gs_id.startswith('gs'):
                    gs_id = f"gs{gs_id}"

                sat_id = f"sat{event.get('satId', 0)}"
                pair_key = (gs_id, sat_id)

                if pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)
                    latency = event.get('latency_ms', self.gs_sat_latency_ms)
                    self.gs_visibility[gs_id].append((sat_id, latency))

    def add_gs_satellite_link(self, gs_id: str, sat_id: str, latency_ms: float = None):
        """
        Manually add a GS-Satellite link

        Args:
            gs_id: Ground station ID
            sat_id: Satellite ID
            latency_ms: Link latency (default: altitude-based)
        """
        if latency_ms is None:
            latency_ms = self.gs_sat_latency_ms

        if not gs_id.startswith('gs'):
            gs_id = f"gs{gs_id}"
        if not sat_id.startswith('sat'):
            sat_id = f"sat{sat_id}"

        self.ground_stations.add(gs_id)
        self.gs_visibility[gs_id].append((sat_id, latency_ms))

        # Add to graph for path computation
        self.graph[gs_id].append((sat_id, latency_ms))
        self.graph[sat_id].append((gs_id, latency_ms))

    def set_all_gs_visibility(self, visible_sats_per_gs: Dict[str, List[int]]):
        """
        Set GS visibility manually (for testing/simulation)

        Args:
            visible_sats_per_gs: {gs_id: [sat_indices]}
        """
        for gs_id, sat_indices in visible_sats_per_gs.items():
            for sat_idx in sat_indices:
                self.add_gs_satellite_link(gs_id, f"sat{sat_idx}")

    def dijkstra(self, start: str, end: str, use_gs_links: bool = True) -> Optional[PathResult]:
        """
        Compute shortest path using Dijkstra's algorithm

        Args:
            start: Source node ID
            end: Destination node ID
            use_gs_links: Include GS-Satellite links in graph

        Returns:
            PathResult or None if no path exists
        """
        if start not in self.graph and start not in self.ground_stations:
            return None
        if end not in self.graph and end not in self.ground_stations:
            return None

        # Build working graph
        working_graph = dict(self.graph)

        # Add GS links if requested
        if use_gs_links:
            for gs_id, visible_sats in self.gs_visibility.items():
                for sat_id, latency in visible_sats:
                    if gs_id not in working_graph:
                        working_graph[gs_id] = []
                    working_graph[gs_id].append((sat_id, latency))
                    working_graph[sat_id].append((gs_id, latency))

        # Dijkstra
        distances = {node: float('inf') for node in working_graph}
        distances[start] = 0
        predecessors = {start: None}

        pq = [(0, start)]
        visited = set()

        while pq:
            current_dist, current = heapq.heappop(pq)

            if current in visited:
                continue
            visited.add(current)

            if current == end:
                break

            for neighbor, weight in working_graph.get(current, []):
                if neighbor in visited:
                    continue

                new_dist = current_dist + weight
                if new_dist < distances.get(neighbor, float('inf')):
                    distances[neighbor] = new_dist
                    predecessors[neighbor] = current
                    heapq.heappush(pq, (new_dist, neighbor))

        # Reconstruct path
        if end not in predecessors:
            return None

        path = []
        current = end
        while current is not None:
            path.append(current)
            current = predecessors.get(current)
        path.reverse()

        # Count GS bounces (GS nodes that are not start/end)
        gs_bounces = sum(1 for node in path[1:-1] if node.startswith('gs'))

        # Determine path type
        path_type = 'gs_bounce' if gs_bounces > 0 else 'isl_only'

        return PathResult(
            path=path,
            hop_count=len(path) - 1,
            total_latency_ms=distances[end],
            path_type=path_type,
            gs_bounces=gs_bounces,
        )

    def compute_isl_only_path(self, gs_src: str, gs_dst: str) -> Optional[PathResult]:
        """
        Compute path using only ISL links (GS used only as endpoints)

        The path goes: GS_src → nearest_sat → ISL chain → nearest_sat → GS_dst
        """
        if not gs_src.startswith('gs'):
            gs_src = f"gs{gs_src}"
        if not gs_dst.startswith('gs'):
            gs_dst = f"gs{gs_dst}"

        src_visible = self.gs_visibility.get(gs_src, [])
        dst_visible = self.gs_visibility.get(gs_dst, [])

        if not src_visible or not dst_visible:
            return None

        best_path = None
        best_latency = float('inf')

        # Try all combinations of entry/exit satellites
        for src_sat, src_latency in src_visible:
            for dst_sat, dst_latency in dst_visible:
                # Find ISL-only path between satellites
                sat_path = self._dijkstra_satellites_only(src_sat, dst_sat)

                if sat_path:
                    total_latency = src_latency + sat_path.total_latency_ms + dst_latency

                    if total_latency < best_latency:
                        best_latency = total_latency
                        full_path = [gs_src] + sat_path.path + [gs_dst]
                        best_path = PathResult(
                            path=full_path,
                            hop_count=len(full_path) - 1,
                            total_latency_ms=total_latency,
                            path_type='isl_only',
                            gs_bounces=0,
                            details={
                                'entry_sat': src_sat,
                                'exit_sat': dst_sat,
                                'isl_hops': sat_path.hop_count,
                                'isl_latency_ms': sat_path.total_latency_ms,
                            }
                        )

        return best_path

    def _dijkstra_satellites_only(self, start: str, end: str) -> Optional[PathResult]:
        """Dijkstra using only satellite-to-satellite links"""
        # Build satellite-only graph
        sat_graph = {node: [(n, l) for n, l in edges if n.startswith('sat')]
                     for node, edges in self.graph.items() if node.startswith('sat')}

        if start not in sat_graph or end not in sat_graph:
            return None

        distances = {node: float('inf') for node in sat_graph}
        distances[start] = 0
        predecessors = {start: None}

        pq = [(0, start)]
        visited = set()

        while pq:
            current_dist, current = heapq.heappop(pq)

            if current in visited:
                continue
            visited.add(current)

            if current == end:
                break

            for neighbor, weight in sat_graph.get(current, []):
                if neighbor in visited:
                    continue

                new_dist = current_dist + weight
                if new_dist < distances.get(neighbor, float('inf')):
                    distances[neighbor] = new_dist
                    predecessors[neighbor] = current
                    heapq.heappush(pq, (new_dist, neighbor))

        if end not in predecessors:
            return None

        path = []
        current = end
        while current is not None:
            path.append(current)
            current = predecessors.get(current)
        path.reverse()

        return PathResult(
            path=path,
            hop_count=len(path) - 1,
            total_latency_ms=distances[end],
            path_type='isl_only',
        )

    def compute_gs_bounce_path(self, gs_src: str, gs_dst: str,
                               max_bounces: int = 3) -> Optional[PathResult]:
        """
        Compute best path allowing intermediate GS bounces

        This finds paths like: GS_src → Sat → GS_mid → Sat → GS_dst
        """
        if not gs_src.startswith('gs'):
            gs_src = f"gs{gs_src}"
        if not gs_dst.startswith('gs'):
            gs_dst = f"gs{gs_dst}"

        # Use Dijkstra with full graph (including all GS links)
        return self.dijkstra(gs_src, gs_dst, use_gs_links=True)

    def compare_paths(self, gs_src: str, gs_dst: str) -> PathComparison:
        """
        Compare ISL-only vs GS-bounce routing

        Args:
            gs_src: Source ground station
            gs_dst: Destination ground station

        Returns:
            PathComparison with both results
        """
        isl_path = self.compute_isl_only_path(gs_src, gs_dst)
        gs_bounce_path = self.compute_gs_bounce_path(gs_src, gs_dst)

        return PathComparison(
            source=gs_src,
            destination=gs_dst,
            isl_only=isl_path,
            gs_bounce=gs_bounce_path,
        )

    def analyze_all_gs_pairs(self) -> List[PathComparison]:
        """Analyze all GS-to-GS pairs"""
        results = []
        gs_list = sorted(self.ground_stations)

        for i, gs_src in enumerate(gs_list):
            for gs_dst in gs_list[i+1:]:
                comparison = self.compare_paths(gs_src, gs_dst)
                results.append(comparison)

        return results

    def print_comparison_report(self, comparisons: List[PathComparison]):
        """Print detailed comparison report"""
        print("\n" + "=" * 80)
        print("PATH COMPARISON REPORT: ISL-only vs GS-bounce routing")
        print("=" * 80)

        beneficial_count = 0
        total_improvement_ms = 0

        for comp in comparisons:
            print(f"\n{comp.source} → {comp.destination}")
            print("-" * 40)

            if comp.isl_only:
                print(f"  ISL-only:  {comp.isl_only.hop_count} hops, {comp.isl_only.total_latency_ms:.3f}ms")
                print(f"             {' → '.join(comp.isl_only.path[:5])}{'...' if len(comp.isl_only.path) > 5 else ''}")
            else:
                print("  ISL-only:  No path found")

            if comp.gs_bounce:
                print(f"  GS-bounce: {comp.gs_bounce.hop_count} hops, {comp.gs_bounce.total_latency_ms:.3f}ms")
                print(f"             {' → '.join(comp.gs_bounce.path[:7])}{'...' if len(comp.gs_bounce.path) > 7 else ''}")
                print(f"             ({comp.gs_bounce.gs_bounces} intermediate GS)")
            else:
                print("  GS-bounce: No path found")

            if comp.gs_bounce_beneficial:
                print(f"  ✓ GS-bounce FASTER by {comp.latency_improvement_ms:.3f}ms ({comp.latency_improvement_percent:.1f}%)")
                beneficial_count += 1
                total_improvement_ms += comp.latency_improvement_ms
            elif comp.isl_only and comp.gs_bounce:
                print(f"  ✗ ISL-only faster by {-comp.latency_improvement_ms:.3f}ms")

        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total pairs analyzed: {len(comparisons)}")
        print(f"GS-bounce beneficial: {beneficial_count} ({beneficial_count/len(comparisons)*100:.1f}%)")
        if beneficial_count > 0:
            print(f"Average improvement: {total_improvement_ms/beneficial_count:.3f}ms")


def main():
    """CLI interface for path comparator"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python path_comparator.py <constellation.json> [gs_src] [gs_dst]")
        print("\nExamples:")
        print("  python path_comparator.py export.json              # Analyze all GS pairs")
        print("  python path_comparator.py export.json gs0 gs1      # Compare specific pair")
        sys.exit(1)

    json_path = sys.argv[1]

    # Load constellation
    graph = ConstellationGraph()
    graph.load_from_json(json_path)

    if len(sys.argv) >= 4:
        # Specific pair
        gs_src = sys.argv[2]
        gs_dst = sys.argv[3]

        comparison = graph.compare_paths(gs_src, gs_dst)
        graph.print_comparison_report([comparison])
    else:
        # All pairs
        comparisons = graph.analyze_all_gs_pairs()

        if not comparisons:
            print("No GS pairs found. Make sure JSON contains ground stations.")
            sys.exit(1)

        graph.print_comparison_report(comparisons)


if __name__ == "__main__":
    main()
