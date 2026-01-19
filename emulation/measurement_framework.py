#!/usr/bin/env python3
"""
Measurement Framework for GS-Bounce Routing Research
Collects and analyzes metrics for comparing routing strategies

Research metrics:
1. Latency (RTT): ISL-only vs GS-bounce
2. Hop count reduction
3. Handover overhead
4. Path stability / convergence time
5. Throughput impact
"""

import json
import time
import threading
import statistics
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from enum import Enum

from path_comparator import ConstellationGraph


@dataclass
class LatencyMeasurement:
    """Single latency measurement"""
    timestamp: float
    source: str
    destination: str
    rtt_ms: float
    packet_loss: float = 0.0
    hop_count: int = 0
    routing_mode: str = ""


@dataclass
class HandoverEvent:
    """Records a handover event"""
    timestamp: float
    gs_id: str
    from_sat: int
    to_sat: int
    handover_duration_ms: float
    packets_lost: int = 0


@dataclass
class ExperimentMetrics:
    """Aggregated metrics for an experiment"""
    # Latency metrics
    latency_samples: List[LatencyMeasurement] = field(default_factory=list)
    avg_latency_ms: float = 0.0
    min_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    jitter_ms: float = 0.0

    # Hop metrics
    avg_hop_count: float = 0.0
    min_hop_count: int = 0
    max_hop_count: int = 0

    # Handover metrics
    handover_events: List[HandoverEvent] = field(default_factory=list)
    total_handovers: int = 0
    avg_handover_duration_ms: float = 0.0
    handover_packet_loss: int = 0

    # Throughput (if measured)
    avg_throughput_mbps: float = 0.0

    def compute_aggregates(self):
        """Compute aggregate statistics from samples"""
        if not self.latency_samples:
            return

        rtts = [s.rtt_ms for s in self.latency_samples if s.rtt_ms > 0]
        if not rtts:
            return

        self.avg_latency_ms = statistics.mean(rtts)
        self.min_latency_ms = min(rtts)
        self.max_latency_ms = max(rtts)
        self.p50_latency_ms = statistics.median(rtts)

        sorted_rtts = sorted(rtts)
        idx_95 = int(len(sorted_rtts) * 0.95)
        idx_99 = int(len(sorted_rtts) * 0.99)
        self.p95_latency_ms = sorted_rtts[idx_95] if idx_95 < len(sorted_rtts) else self.max_latency_ms
        self.p99_latency_ms = sorted_rtts[idx_99] if idx_99 < len(sorted_rtts) else self.max_latency_ms

        if len(rtts) > 1:
            self.jitter_ms = statistics.stdev(rtts)

        hops = [s.hop_count for s in self.latency_samples if s.hop_count > 0]
        if hops:
            self.avg_hop_count = statistics.mean(hops)
            self.min_hop_count = min(hops)
            self.max_hop_count = max(hops)

        self.total_handovers = len(self.handover_events)
        if self.handover_events:
            durations = [h.handover_duration_ms for h in self.handover_events]
            self.avg_handover_duration_ms = statistics.mean(durations)
            self.handover_packet_loss = sum(h.packets_lost for h in self.handover_events)


@dataclass
class ComparisonResult:
    """Result of comparing two routing modes"""
    source: str
    destination: str
    timestamp: str

    # ISL-only metrics
    isl_metrics: ExperimentMetrics = field(default_factory=ExperimentMetrics)

    # GS-bounce metrics
    gs_bounce_metrics: ExperimentMetrics = field(default_factory=ExperimentMetrics)

    # Comparison
    latency_improvement_ms: float = 0.0
    latency_improvement_percent: float = 0.0
    hop_reduction: float = 0.0
    gs_bounce_beneficial: bool = False

    def compute_comparison(self):
        """Compute comparison metrics"""
        if self.isl_metrics.avg_latency_ms > 0 and self.gs_bounce_metrics.avg_latency_ms > 0:
            self.latency_improvement_ms = (
                self.isl_metrics.avg_latency_ms - self.gs_bounce_metrics.avg_latency_ms
            )
            self.latency_improvement_percent = (
                self.latency_improvement_ms / self.isl_metrics.avg_latency_ms * 100
            )
            self.gs_bounce_beneficial = self.latency_improvement_ms > 0

        if self.isl_metrics.avg_hop_count > 0 and self.gs_bounce_metrics.avg_hop_count > 0:
            self.hop_reduction = (
                self.isl_metrics.avg_hop_count - self.gs_bounce_metrics.avg_hop_count
            )


class MeasurementCollector:
    """
    Collects measurements during experiment execution

    Thread-safe for use with dynamic topology updates
    """

    def __init__(self):
        self.measurements: List[LatencyMeasurement] = []
        self.handovers: List[HandoverEvent] = []
        self._lock = threading.Lock()
        self.start_time = time.time()

    def record_latency(self, source: str, destination: str, rtt_ms: float,
                       hop_count: int = 0, routing_mode: str = "",
                       packet_loss: float = 0.0):
        """Record a latency measurement"""
        with self._lock:
            self.measurements.append(LatencyMeasurement(
                timestamp=time.time() - self.start_time,
                source=source,
                destination=destination,
                rtt_ms=rtt_ms,
                packet_loss=packet_loss,
                hop_count=hop_count,
                routing_mode=routing_mode,
            ))

    def record_handover(self, gs_id: str, from_sat: int, to_sat: int,
                        duration_ms: float, packets_lost: int = 0):
        """Record a handover event"""
        with self._lock:
            self.handovers.append(HandoverEvent(
                timestamp=time.time() - self.start_time,
                gs_id=gs_id,
                from_sat=from_sat,
                to_sat=to_sat,
                handover_duration_ms=duration_ms,
                packets_lost=packets_lost,
            ))

    def get_metrics(self, routing_mode: str = None) -> ExperimentMetrics:
        """Get aggregated metrics, optionally filtered by routing mode"""
        with self._lock:
            metrics = ExperimentMetrics()

            if routing_mode:
                metrics.latency_samples = [
                    m for m in self.measurements if m.routing_mode == routing_mode
                ]
            else:
                metrics.latency_samples = list(self.measurements)

            metrics.handover_events = list(self.handovers)
            metrics.compute_aggregates()

            return metrics

    def clear(self):
        """Clear all measurements"""
        with self._lock:
            self.measurements.clear()
            self.handovers.clear()
            self.start_time = time.time()


class ExperimentRunner:
    """
    Runs experiments comparing ISL-only vs GS-bounce routing

    Coordinates measurement collection, test execution, and result analysis
    """

    def __init__(self, net=None, json_path: str = None):
        """
        Initialize experiment runner

        Args:
            net: Mininet network (optional, for integrated tests)
            json_path: Path to constellation JSON for analysis
        """
        self.net = net
        self.graph = ConstellationGraph()
        self.collector = MeasurementCollector()
        self.results: List[ComparisonResult] = []

        if json_path:
            self.graph.load_from_json(json_path)

    def run_latency_test(self, source: str, destination: str,
                         count: int = 20, interval_s: float = 0.5,
                         routing_mode: str = "isl_only") -> ExperimentMetrics:
        """
        Run latency test between two nodes

        If Mininet is available, uses actual ping.
        Otherwise, uses theoretical calculation from graph.
        """
        metrics = ExperimentMetrics()

        if self.net:
            # Real Mininet test
            metrics = self._run_mininet_ping(source, destination, count, routing_mode)
        else:
            # Theoretical calculation
            metrics = self._calculate_theoretical_latency(source, destination, routing_mode)

        return metrics

    def _run_mininet_ping(self, source: str, destination: str,
                          count: int, routing_mode: str) -> ExperimentMetrics:
        """Run actual ping test in Mininet"""
        src_host = self.net.get(source)
        dst_host = self.net.get(destination)

        if not src_host or not dst_host:
            return ExperimentMetrics()

        # Get destination IP
        dst_ip = None
        for intf in dst_host.intfList():
            if intf.name != 'lo' and intf.IP():
                dst_ip = intf.IP()
                break

        if not dst_ip:
            return ExperimentMetrics()

        # Run ping and collect individual results
        metrics = ExperimentMetrics()

        for i in range(count):
            result = src_host.cmd(f'ping -c 1 -W 2 {dst_ip}')

            rtt = self._parse_single_ping(result)
            if rtt is not None:
                self.collector.record_latency(
                    source, destination, rtt,
                    routing_mode=routing_mode
                )
                metrics.latency_samples.append(LatencyMeasurement(
                    timestamp=time.time(),
                    source=source,
                    destination=destination,
                    rtt_ms=rtt,
                    routing_mode=routing_mode,
                ))

            time.sleep(0.1)  # Small delay between pings

        metrics.compute_aggregates()
        return metrics

    def _parse_single_ping(self, output: str) -> Optional[float]:
        """Parse RTT from single ping output"""
        for line in output.split('\n'):
            if 'time=' in line:
                try:
                    time_part = line.split('time=')[1]
                    rtt = float(time_part.split()[0])
                    return rtt
                except:
                    pass
        return None

    def _calculate_theoretical_latency(self, source: str, destination: str,
                                       routing_mode: str) -> ExperimentMetrics:
        """Calculate theoretical latency from graph topology"""
        metrics = ExperimentMetrics()

        if routing_mode == "isl_only":
            path_result = self.graph.compute_isl_only_path(source, destination)
        else:
            path_result = self.graph.compute_gs_bounce_path(source, destination)

        if path_result:
            # Create synthetic measurement (one-way latency, RTT = 2x)
            rtt = path_result.total_latency_ms * 2

            metrics.latency_samples.append(LatencyMeasurement(
                timestamp=0,
                source=source,
                destination=destination,
                rtt_ms=rtt,
                hop_count=path_result.hop_count,
                routing_mode=routing_mode,
            ))
            metrics.compute_aggregates()

        return metrics

    def run_comparison(self, source: str, destination: str,
                       test_count: int = 20) -> ComparisonResult:
        """
        Run comparative test between routing modes

        Args:
            source: Source ground station
            destination: Destination ground station
            test_count: Number of tests per mode

        Returns:
            ComparisonResult with metrics for both modes
        """
        result = ComparisonResult(
            source=source,
            destination=destination,
            timestamp=datetime.now().isoformat(),
        )

        print(f"Testing {source} → {destination}")

        # ISL-only test
        print("  Running ISL-only test...")
        result.isl_metrics = self.run_latency_test(
            source, destination, test_count, routing_mode="isl_only"
        )

        # GS-bounce test
        print("  Running GS-bounce test...")
        result.gs_bounce_metrics = self.run_latency_test(
            source, destination, test_count, routing_mode="gs_bounce"
        )

        result.compute_comparison()
        self.results.append(result)

        return result

    def run_all_pairs(self, test_count: int = 20) -> List[ComparisonResult]:
        """Run comparison for all GS pairs"""
        gs_list = sorted(self.graph.ground_stations)

        print(f"\nRunning experiment for {len(gs_list)} ground stations")
        print("=" * 60)

        for i, gs_src in enumerate(gs_list):
            for gs_dst in gs_list[i+1:]:
                self.run_comparison(gs_src, gs_dst, test_count)

        return self.results

    def export_results(self, output_path: str):
        """Export results to JSON file"""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to serializable format
        data = {
            'timestamp': datetime.now().isoformat(),
            'summary': self.get_summary(),
            'results': []
        }

        for r in self.results:
            result_dict = {
                'source': r.source,
                'destination': r.destination,
                'timestamp': r.timestamp,
                'isl_only': {
                    'avg_latency_ms': r.isl_metrics.avg_latency_ms,
                    'min_latency_ms': r.isl_metrics.min_latency_ms,
                    'max_latency_ms': r.isl_metrics.max_latency_ms,
                    'p95_latency_ms': r.isl_metrics.p95_latency_ms,
                    'jitter_ms': r.isl_metrics.jitter_ms,
                    'avg_hop_count': r.isl_metrics.avg_hop_count,
                },
                'gs_bounce': {
                    'avg_latency_ms': r.gs_bounce_metrics.avg_latency_ms,
                    'min_latency_ms': r.gs_bounce_metrics.min_latency_ms,
                    'max_latency_ms': r.gs_bounce_metrics.max_latency_ms,
                    'p95_latency_ms': r.gs_bounce_metrics.p95_latency_ms,
                    'jitter_ms': r.gs_bounce_metrics.jitter_ms,
                    'avg_hop_count': r.gs_bounce_metrics.avg_hop_count,
                },
                'comparison': {
                    'latency_improvement_ms': r.latency_improvement_ms,
                    'latency_improvement_percent': r.latency_improvement_percent,
                    'hop_reduction': r.hop_reduction,
                    'gs_bounce_beneficial': r.gs_bounce_beneficial,
                },
            }
            data['results'].append(result_dict)

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"\nResults exported to: {output_path}")

    def export_csv(self, output_path: str):
        """Export results to CSV file"""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            # Header
            f.write("source,destination,")
            f.write("isl_avg_ms,isl_p95_ms,isl_hops,")
            f.write("gs_avg_ms,gs_p95_ms,gs_hops,")
            f.write("improvement_ms,improvement_pct,gs_bounce_better\n")

            for r in self.results:
                f.write(f"{r.source},{r.destination},")
                f.write(f"{r.isl_metrics.avg_latency_ms:.3f},")
                f.write(f"{r.isl_metrics.p95_latency_ms:.3f},")
                f.write(f"{r.isl_metrics.avg_hop_count:.1f},")
                f.write(f"{r.gs_bounce_metrics.avg_latency_ms:.3f},")
                f.write(f"{r.gs_bounce_metrics.p95_latency_ms:.3f},")
                f.write(f"{r.gs_bounce_metrics.avg_hop_count:.1f},")
                f.write(f"{r.latency_improvement_ms:.3f},")
                f.write(f"{r.latency_improvement_percent:.1f},")
                f.write(f"{'yes' if r.gs_bounce_beneficial else 'no'}\n")

        print(f"CSV exported to: {output_path}")

    def get_summary(self) -> Dict:
        """Get experiment summary"""
        if not self.results:
            return {}

        beneficial = [r for r in self.results if r.gs_bounce_beneficial]

        improvements = [r.latency_improvement_ms for r in beneficial]
        avg_improvement = statistics.mean(improvements) if improvements else 0

        return {
            'total_pairs': len(self.results),
            'gs_bounce_beneficial_count': len(beneficial),
            'gs_bounce_beneficial_percent': len(beneficial) / len(self.results) * 100,
            'avg_improvement_when_beneficial_ms': avg_improvement,
            'max_improvement_ms': max(improvements) if improvements else 0,
        }

    def print_summary(self):
        """Print experiment summary to console"""
        summary = self.get_summary()

        print("\n" + "=" * 70)
        print("EXPERIMENT SUMMARY: ISL-only vs GS-bounce Routing")
        print("=" * 70)

        print(f"\nTotal GS pairs tested: {summary.get('total_pairs', 0)}")
        print(f"GS-bounce beneficial: {summary.get('gs_bounce_beneficial_count', 0)} "
              f"({summary.get('gs_bounce_beneficial_percent', 0):.1f}%)")

        if summary.get('gs_bounce_beneficial_count', 0) > 0:
            print(f"Average improvement: {summary.get('avg_improvement_when_beneficial_ms', 0):.2f}ms")
            print(f"Maximum improvement: {summary.get('max_improvement_ms', 0):.2f}ms")

        print("\n" + "-" * 70)
        print(f"{'Pair':<20} {'ISL RTT':>12} {'GS RTT':>12} {'Improv.':>12} {'Better':>8}")
        print("-" * 70)

        for r in self.results:
            pair = f"{r.source}→{r.destination}"
            isl_rtt = f"{r.isl_metrics.avg_latency_ms:.2f}ms"
            gs_rtt = f"{r.gs_bounce_metrics.avg_latency_ms:.2f}ms"
            improv = f"{r.latency_improvement_ms:+.2f}ms"
            better = "GS" if r.gs_bounce_beneficial else "ISL"

            print(f"{pair:<20} {isl_rtt:>12} {gs_rtt:>12} {improv:>12} {better:>8}")

        print("=" * 70)


def main():
    """CLI interface for measurement framework"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python measurement_framework.py <constellation.json> [output_dir]")
        print("\nRuns theoretical analysis of ISL-only vs GS-bounce routing")
        sys.exit(1)

    json_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "results"

    # Run experiment
    runner = ExperimentRunner(json_path=json_path)

    if not runner.graph.ground_stations:
        print("Error: No ground stations found in JSON")
        sys.exit(1)

    runner.run_all_pairs(test_count=1)  # Theoretical only needs 1

    # Print and export results
    runner.print_summary()
    runner.export_results(f"{output_dir}/routing_comparison.json")
    runner.export_csv(f"{output_dir}/routing_comparison.csv")


if __name__ == "__main__":
    main()
