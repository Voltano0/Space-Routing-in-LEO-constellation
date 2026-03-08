#!/usr/bin/env python3
"""
ISIS Metrics Collector for Mininet LEO Satellite Emulation

Collects ISIS routing metrics during emulation:
- Convergence time after handovers
- Packet loss during handovers
- Service interruption duration
- SPF computation logs
- LSP flooding delay measurements

Usage:
    Instantiated and controlled from mininet_gs_timeseries.py via 'metrics' commands.
"""

import json
import re
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from emulation_utils import compute_link_utilization, compute_convergence_time, compute_packet_loss


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ISISConvergenceEvent:
    """Measures how long ISIS takes to converge after a topology change."""
    timestamp: float              # simulation time (s)
    trigger: str                  # 'handover' | 'connect' | 'disconnect'
    gs_id: str
    from_sat: Optional[int]
    to_sat: Optional[int]
    convergence_time_s: float     # seconds until route is back
    adjacency_up_time_s: float    # seconds until adjacency is UP
    route_present_time_s: float   # seconds until ISIS route present


@dataclass
class PacketLossEvent:
    """Packet loss measured during a handover."""
    timestamp: float
    gs_id: str
    from_sat: Optional[int]
    to_sat: Optional[int]
    packets_sent: int
    packets_received: int
    packets_lost: int
    loss_percent: float


@dataclass
class ServiceInterruption:
    """Gap between last successful ping and first successful ping after handover."""
    timestamp: float
    gs_id: str
    last_ping_ok: float           # wall-clock time of last OK ping before outage
    first_ping_ok: float          # wall-clock time of first OK ping after outage
    interruption_s: float


@dataclass
class SPFEvent:
    """A single SPF computation logged by ISIS on a node."""
    timestamp: float              # simulation time when collected
    node: str
    spf_duration_ms: float
    spf_trigger: str              # e.g. 'topology change'
    when: str                     # raw 'when' string from spf-log


@dataclass
class LSPFloodingMeasurement:
    """Measures how fast an LSP propagates across the network."""
    timestamp: float
    lsp_id: str
    sequence: str
    origin_node: str
    propagation: dict             # {node: delay_s} from first detection


@dataclass
class LinkUtilizationSnapshot:
    """Measures link utilization on a satellite interface."""
    timestamp: float           # simulation time
    link_id: str               # ex: "12.3" (sat12, inter-plane link #1)
    sat_id: int
    peer_sat: object           # int for ISL, str (e.g. "gs0") for GS links
    link_type: str             # 'intra-plane', 'inter-plane', 'gs'
    tx_bytes: int              # bytes transmitted since last snapshot
    rx_bytes: int              # bytes received since last snapshot
    tx_rate_mbps: float        # TX rate in Mbps
    rx_rate_mbps: float        # RX rate in Mbps
    utilization_pct: float     # max(tx,rx) / bandwidth * 100


@dataclass
class MetricsSummary:
    """Aggregated summary of all collected metrics."""
    total_handovers: int = 0
    avg_convergence_s: float = 0.0
    max_convergence_s: float = 0.0
    min_convergence_s: float = 0.0
    avg_packet_loss_pct: float = 0.0
    avg_interruption_s: float = 0.0
    max_interruption_s: float = 0.0
    total_spf_events: int = 0
    avg_spf_duration_ms: float = 0.0
    total_lsp_measurements: int = 0
    avg_lsp_propagation_s: float = 0.0
    avg_utilization_pct: float = 0.0
    max_utilization_pct: float = 0.0
    most_loaded_links: list = field(default_factory=list)  # top 5 [{link_id, avg_pct}]
    collection_duration_s: float = 0.0


# ---------------------------------------------------------------------------
# Helper: vtysh command execution
# ---------------------------------------------------------------------------

def vtysh_cmd(host, command):
    """Execute a vtysh command on a Mininet host via the FRR socket."""
    hostname = host.name
    return host.cmd(
        f'vtysh --vty_socket /tmp/frr_pids/{hostname} -c "{command}"'
    )


# ---------------------------------------------------------------------------
# Main collector class
# ---------------------------------------------------------------------------

class ISISMetricsCollector:
    """
    Background collector for ISIS routing metrics.

    - Periodically polls SPF logs and LSP databases.
    - Provides a handover hook that spawns measurement threads.
    - Exports results to JSON.
    """

    def __init__(self, net, sat_hosts, gs_hosts, gs_manager, link_map=None):
        self.net = net
        self.sat_hosts = sat_hosts    # {sat_id: host}
        self.gs_hosts = gs_hosts      # {gs_id: host}
        self.gs_manager = gs_manager
        self.link_map = link_map or {}  # {sat_id: {label: {peer, intf, type, bandwidth_mbps}}}

        # Collected events
        self.convergence_events: list[ISISConvergenceEvent] = []
        self.packet_loss_events: list[PacketLossEvent] = []
        self.service_interruptions: list[ServiceInterruption] = []
        self.spf_events: list[SPFEvent] = []
        self.lsp_measurements: list[LSPFloodingMeasurement] = []
        self.link_utilization_snapshots: list[LinkUtilizationSnapshot] = []

        # State
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._handover_threads: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._start_time: Optional[float] = None

        # SPF tracking: last seen count per node to detect new entries
        self._spf_counts: dict[str, int] = {}
        # LSP tracking: last seen sequence per lsp_id on reference node
        self._lsp_sequences: dict[str, str] = {}

        # Build node subsets for polling
        sat_ids = sorted(self.sat_hosts.keys())
        self._spf_poll_sats = [sid for i, sid in enumerate(sat_ids) if i % 8 == 0]
        self._lsp_poll_sats = [sid for i, sid in enumerate(sat_ids) if i % 4 == 0]
        self._lsp_ref_node = sat_ids[0] if sat_ids else None

        # Simulation time reference (will be set externally)
        self.get_sim_time = lambda: 0.0

        # Link utilization tracking
        self._prev_bytes = {}   # {intf_name: {'tx': int, 'rx': int, 'time': float}}
        self._gs_bandwidth_mbps = 100  # GS link bandwidth

        # Debug: track poll stats
        self._poll_count = 0
        self._vtysh_ok = False  # True once we confirm vtysh works
        self._spf_cmd = None    # Detected SPF log command (None if unavailable)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, get_sim_time=None):
        """Start background polling."""
        if self._running:
            print("*** Metrics collector already running.", flush=True)
            return
        if get_sim_time:
            self.get_sim_time = get_sim_time
        self._running = True
        self._start_time = time.time()

        # Run diagnostic before starting
        self._run_diagnostic()

        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        print("*** ISIS metrics collector started (poll every 2s).", flush=True)

    def stop(self):
        """Stop background polling and wait for threads."""
        if not self._running:
            return
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=5)
        # Wait for in-flight handover measurement threads
        for t in self._handover_threads:
            t.join(timeout=2)
        self._handover_threads.clear()
        print("*** ISIS metrics collector stopped.", flush=True)
        print(f"*** Total polls done: {self._poll_count}", flush=True)
        print(f"*** SPF events collected: {len(self.spf_events)}", flush=True)
        print(f"*** LSP measurements collected: {len(self.lsp_measurements)}", flush=True)
        print(f"*** Convergence events collected: {len(self.convergence_events)}", flush=True)
        print(f"*** Link utilization snapshots: {len(self.link_utilization_snapshots)}", flush=True)

    def handover_callback(self, gs_id, from_sat, to_sat, latency_ms):
        """
        Called BEFORE the actual handover disconnect/connect.
        Spawns a measurement thread that monitors convergence.
        """
        if not self._running:
            return
        sim_time = self.get_sim_time()
        print(f"*** [METRICS] Handover callback: {gs_id} sat{from_sat}->sat{to_sat} at t={sim_time:.0f}s", flush=True)
        t = threading.Thread(
            target=self._measure_handover,
            args=(gs_id, from_sat, to_sat, sim_time),
            daemon=True,
        )
        t.start()
        with self._lock:
            self._handover_threads.append(t)

    def connect_callback(self, gs_id, sat_id, latency_ms):
        """
        Called AFTER a GS connect (link is up).
        Spawns a measurement thread to measure ISIS convergence time.
        """
        if not self._running:
            return
        sim_time = self.get_sim_time()
        print(f"*** [METRICS] Connect callback: {gs_id} -> sat{sat_id} at t={sim_time:.0f}s", flush=True)
        t = threading.Thread(
            target=self._measure_connect,
            args=(gs_id, sat_id, sim_time),
            daemon=True,
        )
        t.start()
        with self._lock:
            self._handover_threads.append(t)

    def status(self):
        """Print current collection status."""
        elapsed = time.time() - self._start_time if self._start_time else 0
        print(f"*** Metrics collector running: {self._running}", flush=True)
        print(f"*** vtysh working: {self._vtysh_ok}", flush=True)
        print(f"*** Collection time: {elapsed:.0f}s", flush=True)
        print(f"*** Poll cycles done: {self._poll_count}", flush=True)
        print(f"*** Convergence events: {len(self.convergence_events)}", flush=True)
        print(f"*** Packet loss events:  {len(self.packet_loss_events)}", flush=True)
        print(f"*** Service interruptions: {len(self.service_interruptions)}", flush=True)
        print(f"*** SPF events:          {len(self.spf_events)}", flush=True)
        print(f"*** LSP measurements:    {len(self.lsp_measurements)}", flush=True)
        print(f"*** Link util snapshots: {len(self.link_utilization_snapshots)}", flush=True)

    def print_summary(self):
        """Print a human-readable summary of collected metrics."""
        summary = self._build_summary()
        print("=" * 60, flush=True)
        print("ISIS METRICS SUMMARY", flush=True)
        print("=" * 60, flush=True)
        print(f"Collection duration:       {summary.collection_duration_s:.0f}s", flush=True)
        print(f"Total handovers measured:  {summary.total_handovers}", flush=True)
        print("", flush=True)

        if summary.total_handovers > 0:
            print("-- Convergence Time --", flush=True)
            print(f"  Average: {summary.avg_convergence_s:.3f}s", flush=True)
            print(f"  Min:     {summary.min_convergence_s:.3f}s", flush=True)
            print(f"  Max:     {summary.max_convergence_s:.3f}s", flush=True)
            print("", flush=True)
            print("-- Packet Loss --", flush=True)
            print(f"  Average loss: {summary.avg_packet_loss_pct:.1f}%", flush=True)
            print("", flush=True)
            print("-- Service Interruption --", flush=True)
            print(f"  Average: {summary.avg_interruption_s:.3f}s", flush=True)
            print(f"  Max:     {summary.max_interruption_s:.3f}s", flush=True)
        else:
            print("  No handover events measured yet.", flush=True)

        print("", flush=True)
        print("-- SPF Computations --", flush=True)
        print(f"  Total events: {summary.total_spf_events}", flush=True)
        if summary.total_spf_events > 0:
            print(f"  Avg duration: {summary.avg_spf_duration_ms:.2f}ms", flush=True)

        print("", flush=True)
        print("-- LSP Flooding --", flush=True)
        print(f"  Measurements: {summary.total_lsp_measurements}", flush=True)
        if summary.total_lsp_measurements > 0:
            print(f"  Avg propagation: {summary.avg_lsp_propagation_s:.3f}s", flush=True)

        print("", flush=True)
        print("-- Link Utilization --", flush=True)
        print(f"  Snapshots: {len(self.link_utilization_snapshots)}", flush=True)
        if summary.avg_utilization_pct > 0:
            print(f"  Avg utilization: {summary.avg_utilization_pct:.2f}%", flush=True)
            print(f"  Max utilization: {summary.max_utilization_pct:.2f}%", flush=True)
            if summary.most_loaded_links:
                print(f"  Top loaded links:", flush=True)
                for entry in summary.most_loaded_links:
                    print(f"    {entry['link_id']}: {entry['avg_pct']:.2f}%", flush=True)

        print("=" * 60, flush=True)

    def export_json(self, filepath=None):
        """Export all metrics to a JSON file."""
        if filepath is None:
            ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            filepath = f"isis_metrics_{ts}.json"

        summary = self._build_summary()
        data = {
            "metadata": {
                "export_time": datetime.now().isoformat(),
                "collection_duration_s": summary.collection_duration_s,
            },
            "summary": asdict(summary),
            "convergence_events": [asdict(e) for e in self.convergence_events],
            "packet_loss_events": [asdict(e) for e in self.packet_loss_events],
            "service_interruptions": [asdict(e) for e in self.service_interruptions],
            "spf_events": [asdict(e) for e in self.spf_events],
            "lsp_measurements": [asdict(e) for e in self.lsp_measurements],
            "link_utilization": [asdict(e) for e in self.link_utilization_snapshots],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        print(f"*** Metrics exported to {filepath}", flush=True)
        return filepath

    # ------------------------------------------------------------------
    # Diagnostic: verify vtysh actually works
    # ------------------------------------------------------------------

    def _run_diagnostic(self):
        """Run a diagnostic check on the first available node to verify vtysh works."""
        print("*** [METRICS DIAG] Running vtysh diagnostic...", flush=True)

        # Try a satellite first
        test_host = None
        test_name = None
        for sid in sorted(self.sat_hosts.keys())[:1]:
            test_host = self.sat_hosts[sid]
            test_name = f"sat{sid}"
            break

        if not test_host:
            for gs_id, host in self.gs_hosts.items():
                test_host = host
                test_name = gs_id
                break

        if not test_host:
            print("*** [METRICS DIAG] ERROR: No hosts available!", flush=True)
            return

        pid_dir = f"/tmp/frr_pids/{test_name}"

        # Step 1: Check if PID files exist and processes are alive
        print(f"*** [METRICS DIAG] Checking {pid_dir}/...", flush=True)
        dir_contents = test_host.cmd(f'ls -la {pid_dir}/ 2>&1')
        print(f"    {dir_contents.strip()}", flush=True)

        zebra_pid = test_host.cmd(f'cat {pid_dir}/zebra.pid 2>/dev/null').strip()
        isisd_pid = test_host.cmd(f'cat {pid_dir}/isisd.pid 2>/dev/null').strip()
        print(f"*** [METRICS DIAG] zebra PID: '{zebra_pid}', isisd PID: '{isisd_pid}'", flush=True)

        if zebra_pid and zebra_pid.isdigit():
            alive = test_host.cmd(f'kill -0 {zebra_pid} 2>&1').strip()
            print(f"    zebra alive: {'YES' if not alive else 'NO - ' + alive}", flush=True)
        else:
            print(f"    zebra: NO PID FILE - daemon never started or crashed!", flush=True)

        if isisd_pid and isisd_pid.isdigit():
            alive = test_host.cmd(f'kill -0 {isisd_pid} 2>&1').strip()
            print(f"    isisd alive: {'YES' if not alive else 'NO - ' + alive}", flush=True)
        else:
            print(f"    isisd: NO PID FILE - daemon never started or crashed!", flush=True)

        # Step 2: Check VTY socket files specifically
        zebra_vty = test_host.cmd(f'ls {pid_dir}/zebra.vty 2>&1').strip()
        isisd_vty = test_host.cmd(f'ls {pid_dir}/isisd.vty 2>&1').strip()
        print(f"*** [METRICS DIAG] VTY sockets:", flush=True)
        print(f"    zebra.vty: {'EXISTS' if 'No such' not in zebra_vty else 'MISSING'}", flush=True)
        print(f"    isisd.vty: {'EXISTS' if 'No such' not in isisd_vty else 'MISSING'}", flush=True)

        if 'No such' in zebra_vty and 'No such' in isisd_vty:
            print("*** [METRICS DIAG] FATAL: No VTY sockets found!", flush=True)
            print("    Daemons likely crashed at startup. Trying to restart zebra to see error...", flush=True)
            conf_dir = f"/tmp/frr_configs/{test_name}"
            # Find FRR binaries
            frr_bin = None
            for d in ["/usr/lib/frr", "/usr/sbin", "/usr/local/sbin"]:
                check = test_host.cmd(f'ls {d}/zebra 2>/dev/null').strip()
                if check and 'No such' not in check:
                    frr_bin = d
                    break
            if not frr_bin:
                print("    ERROR: Cannot find FRR binaries (zebra/isisd)!", flush=True)
                print("    Install FRR: sudo apt-get install frr", flush=True)
                return
            print(f"    FRR binaries at: {frr_bin}", flush=True)
            # Run zebra in foreground briefly to see the error
            err_output = test_host.cmd(
                f'timeout 3 {frr_bin}/zebra -f {conf_dir}/zebra.conf '
                f'-i {pid_dir}/zebra_test.pid '
                f'-z {pid_dir}/zebra_test.sock '
                f'--vty_socket {pid_dir} 2>&1'
            )
            print(f"    zebra stderr: {err_output.strip()}", flush=True)

            err_output2 = test_host.cmd(
                f'timeout 3 {frr_bin}/isisd -f {conf_dir}/isisd.conf '
                f'-i {pid_dir}/isisd_test.pid '
                f'-z {pid_dir}/zebra.sock '
                f'--vty_socket {pid_dir} 2>&1'
            )
            print(f"    isisd stderr: {err_output2.strip()}", flush=True)
            # Clean up test files
            test_host.cmd(f'rm -f {pid_dir}/zebra_test.* {pid_dir}/isisd_test.*')
            print("*** [METRICS DIAG] Fix the above errors then re-run 'routing isis'.", flush=True)
            return

        # Step 3: Test vtysh connection
        print(f"*** [METRICS DIAG] Testing vtysh connection to {test_name}...", flush=True)
        test_output = vtysh_cmd(test_host, "show isis neighbor")
        print(f"    Raw output ({len(test_output)} chars):", flush=True)
        for line in test_output.strip().split('\n')[:5]:
            print(f"    | {line}", flush=True)

        if 'failed to connect' in test_output.lower() or 'error' in test_output.lower():
            print("*** [METRICS DIAG] vtysh still fails despite sockets existing.", flush=True)
            print("    Trying direct isisd vty socket with socat...", flush=True)
            socat_test = test_host.cmd(
                f'echo "show isis neighbor" | socat - UNIX-CONNECT:{pid_dir}/isisd.vty 2>&1'
            )
            print(f"    socat result: {socat_test.strip()[:200]}", flush=True)
            return

        self._vtysh_ok = True

        # Step 4: Detect SPF log command
        spf_candidates = [
            "show isis spf-log",
            "show isis spf-log level-2",
        ]
        for cmd in spf_candidates:
            print(f"*** [METRICS DIAG] Trying '{cmd}'...", flush=True)
            spf_output = vtysh_cmd(test_host, cmd)
            if 'Unknown command' in spf_output or 'error' in spf_output.lower():
                print(f"    Not supported.", flush=True)
                continue
            for line in spf_output.strip().split('\n')[:8]:
                print(f"    | {line}", flush=True)
            parsed = self._parse_spf_log(spf_output)
            print(f"    Parsed SPF entries: {len(parsed)}", flush=True)
            if parsed:
                print(f"    First: {parsed[0]}", flush=True)
                self._spf_cmd = cmd
                print(f"    -> Using '{cmd}' for SPF collection.", flush=True)
                break
            # No entries yet but command exists — accept it if output
            # contains SPF-related headers (data will appear after topo changes)
            if 'Duration' in spf_output or 'SPF' in spf_output:
                self._spf_cmd = cmd
                print(f"    -> Using '{cmd}' (no entries yet, but format detected).", flush=True)
                break
            print(f"    Command exists but no SPF data or headers found.", flush=True)

        if not self._spf_cmd:
            print("*** [METRICS DIAG] WARNING: No SPF log command available. SPF collection disabled.", flush=True)

        print(f"*** [METRICS DIAG] Testing 'show isis database'...", flush=True)
        db_output = vtysh_cmd(test_host, "show isis database")
        for line in db_output.strip().split('\n')[:8]:
            print(f"    | {line}", flush=True)
        parsed_lsps = self._parse_lsp_database(db_output)
        print(f"    Parsed LSPs: {len(parsed_lsps)}", flush=True)
        if parsed_lsps:
            first_key = next(iter(parsed_lsps))
            print(f"    Example: {first_key} -> {parsed_lsps[first_key]}", flush=True)

        print("*** [METRICS DIAG] Diagnostic complete.", flush=True)

    # ------------------------------------------------------------------
    # Background polling
    # ------------------------------------------------------------------

    def _poll_loop(self):
        """Periodic polling of SPF logs and LSP databases."""
        while self._running:
            self._poll_count += 1
            try:
                self._collect_spf_logs()
                self._collect_lsp_flooding()
                self._collect_link_utilization()
            except Exception as e:
                print(f"*** Metrics poll error (cycle {self._poll_count}): {e}", flush=True)
                import traceback
                traceback.print_exc()

            # Log progress every 30 polls (~60s)
            if self._poll_count % 30 == 0:
                print(
                    f"*** [METRICS] Poll #{self._poll_count}: "
                    f"SPF={len(self.spf_events)} LSP={len(self.lsp_measurements)} "
                    f"HO={len(self.convergence_events)} LU={len(self.link_utilization_snapshots)}",
                    flush=True,
                )

            # Sleep in small increments so we can stop quickly
            for _ in range(20):
                if not self._running:
                    return
                time.sleep(0.1)

    # ------------------------------------------------------------------
    # SPF log collection
    # ------------------------------------------------------------------

    def _collect_spf_logs(self):
        """Parse SPF logs on a subset of nodes."""
        if not self._spf_cmd:
            return  # SPF log not available on this FRR version

        sim_time = self.get_sim_time()

        nodes_to_poll = []
        # All GS
        for gs_id, host in self.gs_hosts.items():
            nodes_to_poll.append((gs_id, host))
        # Subset of satellites
        for sid in self._spf_poll_sats:
            host = self.sat_hosts.get(sid)
            if host:
                nodes_to_poll.append((f"sat{sid}", host))

        for node_name, host in nodes_to_poll:
            try:
                output = vtysh_cmd(host, self._spf_cmd)
                if not output or not output.strip():
                    continue
                entries = self._parse_spf_log(output)
                prev_count = self._spf_counts.get(node_name, 0)
                if len(entries) > prev_count:
                    new_entries = entries[prev_count:]
                    for entry in new_entries:
                        evt = SPFEvent(
                            timestamp=sim_time,
                            node=node_name,
                            spf_duration_ms=entry['duration_ms'],
                            spf_trigger=entry.get('trigger', 'unknown'),
                            when=entry.get('when', ''),
                        )
                        with self._lock:
                            self.spf_events.append(evt)
                    self._spf_counts[node_name] = len(entries)
            except Exception as e:
                # Log first few errors per node, not every 2s
                if self._poll_count <= 3:
                    print(f"*** [METRICS] SPF poll error on {node_name}: {e}", flush=True)

    def _parse_spf_log(self, output):
        """
        Parse the output of 'show isis spf-log'.
        Returns list of dicts with duration_ms, trigger, when.

        FRR output formats seen:
          Area 49.0001:
          Level 2 SPF:
          Duration (msec)    When         Trigger
                        1    00:00:10 ago  topology change
                        0    00:00:05 ago  periodic

        Some FRR versions also show:
          Timestamp          Duration (msec)  Nodes  Trigger
          2025-01-01T...     1                5      topology change
        """
        entries = []
        lines = output.strip().split('\n')
        for line in lines:
            # Format 1: "   1    00:00:10 ago  topology change"
            m = re.match(
                r'\s*(\d+)\s+(\d+:\d+:\d+\s+ago)\s+(.*)',
                line
            )
            if m:
                entries.append({
                    'duration_ms': float(m.group(1)),
                    'when': m.group(2).strip(),
                    'trigger': m.group(3).strip(),
                })
                continue

            # Format 2: "2025-01-01T... 1 5 topology change" (timestamp, duration, nodes, trigger)
            m2 = re.match(
                r'\s*\d{4}-\d{2}-\d{2}T\S+\s+(\d+)\s+\d+\s+(.*)',
                line
            )
            if m2:
                entries.append({
                    'duration_ms': float(m2.group(1)),
                    'when': '',
                    'trigger': m2.group(2).strip(),
                })
                continue

            # Format 3: just duration and trigger with variable spacing
            m3 = re.match(
                r'\s*(\d+)\s+\d+\s+(.*\S)',
                line
            )
            if m3 and not line.strip().startswith('Duration') and not line.strip().startswith('Level'):
                entries.append({
                    'duration_ms': float(m3.group(1)),
                    'when': '',
                    'trigger': m3.group(2).strip(),
                })

        return entries

    # ------------------------------------------------------------------
    # LSP flooding measurement
    # ------------------------------------------------------------------

    def _collect_lsp_flooding(self):
        """
        Check for new LSPs on reference node, then measure propagation
        delay by re-polling other nodes after a short delay.
        """
        if self._lsp_ref_node is None:
            return

        sim_time = self.get_sim_time()
        ref_host = self.sat_hosts.get(self._lsp_ref_node)
        if not ref_host:
            return

        try:
            ref_output = vtysh_cmd(ref_host, "show isis database")
            if not ref_output or not ref_output.strip():
                return
            ref_lsps = self._parse_lsp_database(ref_output)
        except Exception as e:
            if self._poll_count <= 3:
                print(f"*** [METRICS] LSP ref poll error: {e}", flush=True)
            return

        if not ref_lsps:
            return

        # First poll: record baseline without measuring
        if not self._lsp_sequences:
            self._lsp_sequences = dict(ref_lsps)
            print(f"*** [METRICS] LSP baseline recorded: {len(ref_lsps)} LSPs", flush=True)
            return

        # Detect new/updated LSPs
        new_lsps = {}
        for lsp_id, seq in ref_lsps.items():
            if self._lsp_sequences.get(lsp_id) != seq:
                new_lsps[lsp_id] = seq
                self._lsp_sequences[lsp_id] = seq

        if not new_lsps:
            return

        # Wait 500ms then poll other nodes
        time.sleep(0.5)

        # Build list of nodes to check
        check_nodes = []
        for sid in self._lsp_poll_sats:
            if sid != self._lsp_ref_node:
                host = self.sat_hosts.get(sid)
                if host:
                    check_nodes.append((f"sat{sid}", host))
        for gs_id, host in self.gs_hosts.items():
            check_nodes.append((gs_id, host))

        t0 = time.time()

        for lsp_id, seq in new_lsps.items():
            propagation = {}
            for node_name, host in check_nodes:
                try:
                    out = vtysh_cmd(host, "show isis database")
                    node_lsps = self._parse_lsp_database(out)
                    t_check = time.time() - t0
                    if node_lsps.get(lsp_id) == seq:
                        propagation[node_name] = round(t_check, 3)
                    else:
                        propagation[node_name] = -1  # not yet propagated
                except Exception:
                    propagation[node_name] = -1

            measurement = LSPFloodingMeasurement(
                timestamp=sim_time,
                lsp_id=lsp_id,
                sequence=seq,
                origin_node=f"sat{self._lsp_ref_node}",
                propagation=propagation,
            )
            with self._lock:
                self.lsp_measurements.append(measurement)

    def _parse_lsp_database(self, output):
        """
        Parse 'show isis database' output.
        Returns {lsp_id: sequence_number}.

        FRR formats:
        Area 49.0001:
        IS-IS Level-2 link-state database:
        LSP ID                  PduLen  SeqNumber   Chksum  Holdtime  ATT/P/OL
        sat0.00-00           *    452  0x00000005  0xabcd     720    0/0/0
        sat1.00-00                320  0x00000003  0x1234     718    0/0/0
        """
        lsps = {}
        for line in output.strip().split('\n'):
            # Skip header/title lines
            stripped = line.strip()
            if not stripped or stripped.startswith('Area') or stripped.startswith('IS-IS') or stripped.startswith('LSP'):
                continue

            # Match LSP lines: name possibly followed by *, then numbers
            # Example: "sat0.00-00           *    452  0x00000005  0xabcd     720    0/0/0"
            # Example: "sat0.00-00                320  0x00000003  0x1234     718    0/0/0"
            m = re.match(
                r'\s*(\S+\.00-\d+)\s+\*?\s+\d+\s+(0x[0-9a-fA-F]+)',
                line
            )
            if m:
                lsp_id = m.group(1)
                seq = m.group(2)
                lsps[lsp_id] = seq

        return lsps

    # ------------------------------------------------------------------
    # Link utilization measurement
    # ------------------------------------------------------------------

    def _parse_proc_net_dev(self, output):
        """
        Parse /proc/net/dev output.
        Returns {intf_name: {'rx_bytes': int, 'tx_bytes': int}}.

        Format:
        Inter-|   Receive                                                |  Transmit
         face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets ...
          eth0: 1234567  1234  0  0  0  0  0  0  7654321  1234  0  0  0  0  0  0
        """
        result = {}
        for line in output.strip().split('\n'):
            if ':' not in line or line.strip().startswith('Inter') or line.strip().startswith('face'):
                continue
            parts = line.split(':')
            if len(parts) < 2:
                continue
            intf_name = parts[0].strip()
            fields = parts[1].split()
            if len(fields) >= 9:
                result[intf_name] = {
                    'rx_bytes': int(fields[0]),
                    'tx_bytes': int(fields[8]),
                }
        return result

    def _collect_link_utilization(self):
        """
        Collect link utilization for all satellites by reading /proc/net/dev
        once per host. Compute delta bytes, rate, and utilization percentage.
        """
        if not self.link_map:
            return

        sim_time = self.get_sim_time()
        now = time.time()

        for sat_id, links in self.link_map.items():
            host = self.sat_hosts.get(sat_id)
            if not host:
                continue

            # Read all interfaces in one command
            try:
                raw = host.cmd('cat /proc/net/dev')
                intf_stats = self._parse_proc_net_dev(raw)
            except Exception:
                continue

            for label, link_info in links.items():
                intf_name = link_info['intf']
                if intf_name not in intf_stats:
                    continue

                current = intf_stats[intf_name]
                prev = self._prev_bytes.get(intf_name)

                if prev is None:
                    # First reading: store baseline, no snapshot
                    self._prev_bytes[intf_name] = {
                        'tx': current['tx_bytes'],
                        'rx': current['rx_bytes'],
                        'time': now,
                    }
                    continue

                dt = now - prev['time']
                if dt <= 0:
                    continue

                delta_tx = current['tx_bytes'] - prev['tx']
                delta_rx = current['rx_bytes'] - prev['rx']

                # Handle counter wrap (unlikely but safe)
                if delta_tx < 0:
                    delta_tx = 0
                if delta_rx < 0:
                    delta_rx = 0

                bandwidth = link_info['bandwidth_mbps']
                tx_rate_mbps, rx_rate_mbps, utilization = compute_link_utilization(
                    delta_tx, delta_rx, dt, bandwidth
                )

                snapshot = LinkUtilizationSnapshot(
                    timestamp=sim_time,
                    link_id=label,
                    sat_id=sat_id,
                    peer_sat=link_info['peer'],
                    link_type=link_info['type'],
                    tx_bytes=delta_tx,
                    rx_bytes=delta_rx,
                    tx_rate_mbps=round(tx_rate_mbps, 4),
                    rx_rate_mbps=round(rx_rate_mbps, 4),
                    utilization_pct=round(utilization, 2),
                )
                with self._lock:
                    self.link_utilization_snapshots.append(snapshot)

                # Update baseline
                self._prev_bytes[intf_name] = {
                    'tx': current['tx_bytes'],
                    'rx': current['rx_bytes'],
                    'time': now,
                }

        # Also collect GS link utilization (label .5)
        self._collect_gs_link_utilization(sim_time, now)

    def _collect_gs_link_utilization(self, sim_time, now):
        """Collect utilization for active GS<->satellite links (label x.5)."""
        active_links = self.gs_manager.active_links
        for gs_id, link_info in active_links.items():
            sat_id = link_info['sat_id']
            intf_sat = link_info['intf_sat']

            host = self.sat_hosts.get(sat_id)
            if not host:
                continue

            try:
                raw = host.cmd('cat /proc/net/dev')
                intf_stats = self._parse_proc_net_dev(raw)
            except Exception:
                continue

            if intf_sat not in intf_stats:
                continue

            current = intf_stats[intf_sat]
            prev = self._prev_bytes.get(intf_sat)

            if prev is None:
                self._prev_bytes[intf_sat] = {
                    'tx': current['tx_bytes'],
                    'rx': current['rx_bytes'],
                    'time': now,
                }
                continue

            dt = now - prev['time']
            if dt <= 0:
                continue

            delta_tx = max(0, current['tx_bytes'] - prev['tx'])
            delta_rx = max(0, current['rx_bytes'] - prev['rx'])

            bandwidth = self._gs_bandwidth_mbps
            tx_rate_mbps, rx_rate_mbps, utilization = compute_link_utilization(
                delta_tx, delta_rx, dt, bandwidth
            )

            label = f"{sat_id}.5"
            snapshot = LinkUtilizationSnapshot(
                timestamp=sim_time,
                link_id=label,
                sat_id=sat_id,
                peer_sat=gs_id,
                link_type='gs',
                tx_bytes=delta_tx,
                rx_bytes=delta_rx,
                tx_rate_mbps=round(tx_rate_mbps, 4),
                rx_rate_mbps=round(rx_rate_mbps, 4),
                utilization_pct=round(utilization, 2),
            )
            with self._lock:
                self.link_utilization_snapshots.append(snapshot)

            self._prev_bytes[intf_sat] = {
                'tx': current['tx_bytes'],
                'rx': current['rx_bytes'],
                'time': now,
            }

    # ------------------------------------------------------------------
    # Handover measurement thread
    # ------------------------------------------------------------------

    def _check_adjacency_up(self, host, host_name, debug_polls, poll_num):
        """
        Check if ISIS adjacency is Up on a host.
        Returns True if at least one adjacency is in 'Up' state.
        Logs raw output for first few polls for debugging.
        """
        try:
            adj_output = vtysh_cmd(host, "show isis neighbor")
            # Debug: log first few polls to see what FRR returns
            if poll_num <= debug_polls:
                trimmed = adj_output.strip().replace('\n', ' | ')[:200]
                print(f"    [DEBUG adj {host_name} #{poll_num}] {trimmed}", flush=True)

            if not adj_output or not adj_output.strip():
                return False

            # Check for errors
            lower = adj_output.lower()
            if 'failed' in lower or 'error' in lower or 'not found' in lower:
                return False

            # FRR shows adjacency state as "Up", check case-insensitively
            # Also handle: "Up", "UP", "up"
            # Typical line: "sat42  gs0-eth0  2  Up  28  ca02..."
            for line in adj_output.split('\n'):
                # Skip header lines
                stripped = line.strip()
                if not stripped or stripped.startswith('Area') or stripped.startswith('System'):
                    continue
                # Match state column — look for "Up" as a word
                if re.search(r'\bUp\b', line, re.IGNORECASE):
                    return True

            return False
        except Exception:
            return False

    def _check_isis_routes(self, host, host_name, debug_polls, poll_num,
                           expected_subnet=None, check_connected=False):
        """
        Check if ISIS routes are present on a host.
        Tries multiple methods in order:
          1. vtysh 'show ip route isis'       (FRR filtered view)
          2. vtysh 'show ip route'            (full table, grep for ISIS)
          3. 'ip route show proto isis'       (kernel table, no vtysh needed)
          4. 'ip route' + grep proto isis/187 (kernel fallback)
          5. (if check_connected) 'show ip route' for connected subnet
        If expected_subnet is set (e.g. "192.168."), only match routes containing that prefix.
        check_connected: also accept connected routes matching expected_subnet
                         (for satellite side where GS subnet is directly connected).
        Returns True if at least one ISIS-learned route is found.
        """

        def _has_route(text):
            """Check if text contains an ISIS route (optionally matching expected_subnet)."""
            for line in text.split('\n'):
                stripped = line.strip()
                if not stripped:
                    continue
                if expected_subnet:
                    if expected_subnet in stripped and re.search(r'\d+\.\d+\.\d+\.\d+', stripped):
                        return True
                else:
                    if re.search(r'\d+\.\d+\.\d+\.\d+', stripped):
                        return True
            return False

        # --- Method 1: show ip route isis ---
        try:
            route_output = vtysh_cmd(host, "show ip route isis")
            if poll_num <= debug_polls:
                trimmed = route_output.strip().replace('\n', ' | ')[:300]
                print(f"    [DEBUG route-m1 {host_name} #{poll_num}] {trimmed}", flush=True)

            if route_output and route_output.strip():
                lower = route_output.lower()
                if 'failed' not in lower and 'error' not in lower and 'unknown' not in lower:
                    # FRR formats: "I>* 10.0.0.0/30", "I L2 10.0.0.0", "I  10.0.0.0"
                    if _has_route(route_output):
                        return True
        except Exception:
            pass

        # --- Method 2: show ip route (full table, filter ISIS lines) ---
        try:
            full_output = vtysh_cmd(host, "show ip route")
            if poll_num <= debug_polls:
                isis_lines = [l.strip() for l in full_output.split('\n')
                              if l.strip() and re.match(r'\s*[Ii][>* ]', l)]
                print(f"    [DEBUG route-m2 {host_name} #{poll_num}] ISIS lines ({len(isis_lines)}): {isis_lines[:3]}", flush=True)

            if full_output and full_output.strip():
                isis_text = '\n'.join(
                    l for l in full_output.split('\n')
                    if l.strip() and l.strip()[0] in ('I', 'i')
                    and not l.strip().startswith('I -')  # skip legend "I - IS-IS"
                )
                if isis_text and _has_route(isis_text):
                    return True

                # Method 2b: for satellite side, check if GS subnet is connected
                # (satellite has the GS link as a directly connected route)
                if check_connected and expected_subnet and full_output:
                    connected_lines = '\n'.join(
                        l for l in full_output.split('\n')
                        if l.strip() and l.strip()[0] in ('C', 'c')
                    )
                    if connected_lines and expected_subnet in connected_lines:
                        if poll_num <= debug_polls:
                            print(f"    [DEBUG route-m2b {host_name} #{poll_num}] "
                                  f"GS subnet found as CONNECTED route", flush=True)
                        return True
        except Exception:
            pass

        # --- Method 3: kernel routing table (no FRR/vtysh dependency) ---
        try:
            kern_output = host.cmd('ip route show proto isis 2>/dev/null')
            if poll_num <= debug_polls:
                trimmed = kern_output.strip().replace('\n', ' | ')[:200]
                print(f"    [DEBUG route-m3 {host_name} #{poll_num}] {trimmed}", flush=True)

            if kern_output and kern_output.strip() and _has_route(kern_output):
                return True
        except Exception:
            pass

        # --- Method 4: kernel routing table, grep proto isis/187 ---
        try:
            kern_all = host.cmd('ip route')
            isis_kern_lines = [l for l in kern_all.strip().split('\n')
                               if 'proto isis' in l or 'proto 187' in l]
            if poll_num <= debug_polls:
                print(f"    [DEBUG route-m4 {host_name} #{poll_num}] proto isis lines: {len(isis_kern_lines)}", flush=True)

            if isis_kern_lines and _has_route('\n'.join(isis_kern_lines)):
                return True

            # Method 4b: for satellite side, check connected routes in kernel
            if check_connected and expected_subnet:
                connected_lines = [l for l in kern_all.strip().split('\n')
                                   if expected_subnet in l and 'proto kernel' in l]
                if connected_lines:
                    if poll_num <= debug_polls:
                        print(f"    [DEBUG route-m4b {host_name} #{poll_num}] "
                              f"GS subnet found as kernel connected", flush=True)
                    return True
        except Exception:
            pass

        return False

    def _measure_handover(self, gs_id, from_sat, to_sat, sim_time):
        """
        Dedicated thread to measure convergence during a handover.
        Runs pings in background and polls adjacency/routes separately.

        This callback fires BEFORE disconnect. We wait for the handover
        to complete (adjacency goes down then back up to new sat).
        """
        gs_host = self.gs_hosts.get(gs_id)
        if not gs_host:
            print(f"*** [METRICS] ERROR: GS host {gs_id} not found!", flush=True)
            return

        # Find a target to ping
        target_ip = self._find_ping_target(gs_id)
        if not target_ip:
            print(f"*** [METRICS] WARNING: No ping target found for {gs_id}, measuring adjacency/route only", flush=True)

        handover_wall_time = time.time()
        timeout = 30.0
        adj_poll_interval = 0.5
        debug_polls = 10  # Log raw output for first N polls

        # Ping tracking
        pings_sent = 0
        pings_received = 0
        last_ping_ok_time = handover_wall_time
        first_ping_ok_after = None

        # Adjacency/route tracking — we need to see adjacency go DOWN then UP
        saw_adjacency_down = False
        adjacency_up_time = None
        route_present_time = None

        # Target satellite host (check its side too if GS vtysh fails)
        to_sat_host = self.sat_hosts.get(to_sat)

        poll_num = 0
        start = time.time()

        # Wait a bit for the handover to start (callback fires BEFORE disconnect)
        time.sleep(0.5)

        while (time.time() - start) < timeout:
            if not self._running:
                break

            now = time.time()
            elapsed = now - start
            poll_num += 1

            # --- Ping (non-blocking: short timeout) ---
            if target_ip:
                pings_sent += 1
                result = gs_host.cmd(f'ping -c 1 -W 0.3 {target_ip}')
                if ' 0% packet loss' in result or '1 received' in result:
                    pings_received += 1
                    if first_ping_ok_after is None and saw_adjacency_down:
                        first_ping_ok_after = now
                    last_ping_ok_time = now
                else:
                    # If we haven't seen adjacency down yet, the handover is happening
                    if not saw_adjacency_down:
                        saw_adjacency_down = True

            # --- Adjacency poll ---
            if adjacency_up_time is None:
                # Check GS side
                gs_adj_up = self._check_adjacency_up(gs_host, gs_id, debug_polls, poll_num)

                if not gs_adj_up:
                    saw_adjacency_down = True
                elif saw_adjacency_down:
                    # Adjacency went down then came back up — convergence!
                    adjacency_up_time = elapsed
                    print(f"*** [METRICS] {gs_id} adjacency UP at {elapsed:.3f}s (GS side)", flush=True)

                # If GS vtysh is failing, also check the satellite side
                if adjacency_up_time is None and to_sat_host and saw_adjacency_down:
                    sat_adj_up = self._check_adjacency_up(to_sat_host, f"sat{to_sat}", debug_polls, poll_num)
                    if sat_adj_up:
                        # Verify the neighbor is actually the GS
                        try:
                            adj_out = vtysh_cmd(to_sat_host, "show isis neighbor")
                            if gs_id in adj_out.lower() or 'Up' in adj_out:
                                adjacency_up_time = elapsed
                                print(f"*** [METRICS] {gs_id} adjacency UP at {elapsed:.3f}s (sat side)", flush=True)
                        except Exception:
                            pass

            # --- Route poll (try GS, then satellite side with subnet filter) ---
            if route_present_time is None and adjacency_up_time is not None:
                gs_routes = self._check_isis_routes(gs_host, gs_id, debug_polls, poll_num)
                if gs_routes:
                    route_present_time = elapsed
                    print(f"*** [METRICS] {gs_id} ISIS routes present at {elapsed:.3f}s (GS side)", flush=True)
                elif to_sat_host:
                    gs_subnet = None
                    if gs_id in self.gs_manager.active_links:
                        gs_ip = self.gs_manager.active_links[gs_id].get('ip_gs', '')
                        parts = gs_ip.split('.')
                        if len(parts) >= 3:
                            gs_subnet = f"{parts[0]}.{parts[1]}.{parts[2]}"
                    sat_routes = self._check_isis_routes(
                        to_sat_host, f"sat{to_sat}", debug_polls, poll_num,
                        expected_subnet=gs_subnet,
                        check_connected=True
                    )
                    if sat_routes:
                        route_present_time = elapsed
                        print(f"*** [METRICS] {gs_id} ISIS routes present at {elapsed:.3f}s (sat side, subnet={gs_subnet})", flush=True)

            # Both up = convergence done
            if adjacency_up_time is not None and route_present_time is not None:
                if first_ping_ok_after is not None:
                    break
                if elapsed > (route_present_time + 2.0):
                    break

            time.sleep(adj_poll_interval)

        # --- Record results ---
        convergence = compute_convergence_time(
            adjacency_up_time or timeout,
            route_present_time or timeout,
        )

        conv_event = ISISConvergenceEvent(
            timestamp=sim_time,
            trigger='handover',
            gs_id=gs_id,
            from_sat=from_sat,
            to_sat=to_sat,
            convergence_time_s=round(convergence, 3),
            adjacency_up_time_s=round(adjacency_up_time or timeout, 3),
            route_present_time_s=round(route_present_time or timeout, 3),
        )

        packets_lost, loss_pct = compute_packet_loss(pings_sent, pings_received)

        loss_event = PacketLossEvent(
            timestamp=sim_time,
            gs_id=gs_id,
            from_sat=from_sat,
            to_sat=to_sat,
            packets_sent=pings_sent,
            packets_received=pings_received,
            packets_lost=packets_lost,
            loss_percent=round(loss_pct, 1),
        )

        if first_ping_ok_after:
            interruption_duration = first_ping_ok_after - handover_wall_time
        else:
            interruption_duration = time.time() - handover_wall_time

        interruption = ServiceInterruption(
            timestamp=sim_time,
            gs_id=gs_id,
            last_ping_ok=round(last_ping_ok_time - handover_wall_time, 3),
            first_ping_ok=round(
                (first_ping_ok_after - handover_wall_time)
                if first_ping_ok_after else timeout, 3
            ),
            interruption_s=round(interruption_duration, 3),
        )

        with self._lock:
            self.convergence_events.append(conv_event)
            self.packet_loss_events.append(loss_event)
            self.service_interruptions.append(interruption)

        print(
            f"*** [METRICS] Handover {gs_id}: sat{from_sat}->sat{to_sat} "
            f"convergence={convergence:.3f}s loss={loss_pct:.1f}% "
            f"interruption={interruption_duration:.3f}s "
            f"(adj={adjacency_up_time or timeout:.3f}s route={route_present_time or timeout:.3f}s "
            f"polls={poll_num})",
            flush=True,
        )

    def _measure_connect(self, gs_id, sat_id, sim_time):
        """
        Measure ISIS convergence after a new GS-satellite link is created.
        Polls adjacency and route tables until ISIS converges.
        Also checks the satellite side as fallback if GS vtysh fails.
        """
        gs_host = self.gs_hosts.get(gs_id)
        if not gs_host:
            return

        sat_host = self.sat_hosts.get(sat_id)

        timeout = 30.0
        poll_interval = 0.5
        debug_polls = 10  # Log first N polls for debugging
        adjacency_up_time = None
        route_present_time = None

        # Start timer BEFORE waiting, so adjacency setup time is captured
        start = time.time()

        # Wait for isisd to start and VTY socket to be ready
        # (setup_isis_gs takes ~1s: zebra 0.5s + isisd 0.3s + margin)
        time.sleep(1.5)

        poll_num = 0
        while (time.time() - start) < timeout:
            if not self._running:
                break

            elapsed = time.time() - start
            poll_num += 1

            # Check ISIS adjacency — try GS first, fallback to satellite side
            if adjacency_up_time is None:
                gs_adj_up = self._check_adjacency_up(gs_host, gs_id, debug_polls, poll_num)
                if gs_adj_up:
                    adjacency_up_time = elapsed
                    print(f"*** [METRICS] {gs_id} adjacency UP at {elapsed:.3f}s (GS side)", flush=True)
                elif sat_host:
                    sat_adj_up = self._check_adjacency_up(sat_host, f"sat{sat_id}", debug_polls, poll_num)
                    if sat_adj_up:
                        adjacency_up_time = elapsed
                        print(f"*** [METRICS] {gs_id} adjacency UP at {elapsed:.3f}s (sat side)", flush=True)

            # Check ISIS routes — try GS first, then satellite side
            # GS side: any ISIS route = good (GS had none before)
            # Sat side: must filter for the GS subnet (sat already has other ISIS routes)
            #           use check_connected=True because GS subnet is a connected route on the sat
            if route_present_time is None:
                gs_routes = self._check_isis_routes(gs_host, gs_id, debug_polls, poll_num)
                if gs_routes:
                    route_present_time = elapsed
                    print(f"*** [METRICS] {gs_id} ISIS routes present at {elapsed:.3f}s (GS side)", flush=True)
                elif sat_host:
                    # Find GS subnet to filter satellite's pre-existing routes
                    gs_subnet = None
                    if gs_id in self.gs_manager.active_links:
                        gs_ip = self.gs_manager.active_links[gs_id].get('ip_gs', '')
                        # Extract e.g. "192.168" from "192.168.50001.1/30"
                        parts = gs_ip.split('.')
                        if len(parts) >= 3:
                            gs_subnet = f"{parts[0]}.{parts[1]}.{parts[2]}"
                    sat_routes = self._check_isis_routes(
                        sat_host, f"sat{sat_id}", debug_polls, poll_num,
                        expected_subnet=gs_subnet,
                        check_connected=True
                    )
                    if sat_routes:
                        route_present_time = elapsed
                        print(f"*** [METRICS] {gs_id} ISIS routes present at {elapsed:.3f}s (sat side, subnet={gs_subnet})", flush=True)

            # Both up = converged
            if adjacency_up_time is not None and route_present_time is not None:
                break

            time.sleep(poll_interval)

        convergence = compute_convergence_time(
            adjacency_up_time or timeout,
            route_present_time or timeout,
        )

        conv_event = ISISConvergenceEvent(
            timestamp=sim_time,
            trigger='connect',
            gs_id=gs_id,
            from_sat=None,
            to_sat=sat_id,
            convergence_time_s=round(convergence, 3),
            adjacency_up_time_s=round(adjacency_up_time or timeout, 3),
            route_present_time_s=round(route_present_time or timeout, 3),
        )

        with self._lock:
            self.convergence_events.append(conv_event)

        print(
            f"*** [METRICS] Connect {gs_id}->sat{sat_id} "
            f"adj={adjacency_up_time or timeout:.3f}s "
            f"route={route_present_time or timeout:.3f}s "
            f"convergence={convergence:.3f}s (polls={poll_num})",
            flush=True,
        )

    def _find_ping_target(self, exclude_gs_id):
        """Find an IP to ping from a GS (another connected GS or a satellite)."""
        # Try another connected GS
        active = self.gs_manager.get_active_connections()
        for gs_id, _ in active.items():
            if gs_id != exclude_gs_id and gs_id in self.gs_manager.active_links:
                link_info = self.gs_manager.active_links[gs_id]
                # Return the GS IP (without /30 mask)
                return link_info['ip_gs'].split('/')[0]

        # Fallback: ping a satellite
        for _, host in self.sat_hosts.items():
            ip = host.IP()
            if ip and ip != '127.0.0.1':
                return ip

        return None

    # ------------------------------------------------------------------
    # Summary builder
    # ------------------------------------------------------------------

    def _build_summary(self):
        """Build an aggregated MetricsSummary."""
        s = MetricsSummary()
        elapsed = time.time() - self._start_time if self._start_time else 0
        s.collection_duration_s = round(elapsed, 1)

        # Convergence
        s.total_handovers = len(self.convergence_events)
        if self.convergence_events:
            times = [e.convergence_time_s for e in self.convergence_events]
            s.avg_convergence_s = round(sum(times) / len(times), 3)
            s.min_convergence_s = round(min(times), 3)
            s.max_convergence_s = round(max(times), 3)

        # Packet loss
        if self.packet_loss_events:
            losses = [e.loss_percent for e in self.packet_loss_events]
            s.avg_packet_loss_pct = round(sum(losses) / len(losses), 1)

        # Interruptions
        if self.service_interruptions:
            ints = [e.interruption_s for e in self.service_interruptions]
            s.avg_interruption_s = round(sum(ints) / len(ints), 3)
            s.max_interruption_s = round(max(ints), 3)

        # SPF
        s.total_spf_events = len(self.spf_events)
        if self.spf_events:
            durations = [e.spf_duration_ms for e in self.spf_events]
            s.avg_spf_duration_ms = round(sum(durations) / len(durations), 2)

        # LSP flooding
        s.total_lsp_measurements = len(self.lsp_measurements)
        if self.lsp_measurements:
            avg_props = []
            for m in self.lsp_measurements:
                valid = [v for v in m.propagation.values() if v >= 0]
                if valid:
                    avg_props.append(sum(valid) / len(valid))
            if avg_props:
                s.avg_lsp_propagation_s = round(sum(avg_props) / len(avg_props), 3)

        # Link utilization
        if self.link_utilization_snapshots:
            all_pcts = [snap.utilization_pct for snap in self.link_utilization_snapshots]
            s.avg_utilization_pct = round(sum(all_pcts) / len(all_pcts), 2)
            s.max_utilization_pct = round(max(all_pcts), 2)

            # Top 5 most loaded links (by average utilization)
            from collections import defaultdict
            per_link = defaultdict(list)
            for snap in self.link_utilization_snapshots:
                per_link[snap.link_id].append(snap.utilization_pct)
            link_avgs = [
                {'link_id': lid, 'avg_pct': round(sum(pcts) / len(pcts), 2)}
                for lid, pcts in per_link.items()
            ]
            link_avgs.sort(key=lambda x: x['avg_pct'], reverse=True)
            s.most_loaded_links = link_avgs[:5]

        return s
