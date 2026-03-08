"""
test_algorithms.py
Tests unitaires des fonctions pures de l'émulation.
Importe directement les modules sources via emulation_utils.py et generate_test_constellation.py.
Aucune dépendance Mininet requise.
"""

import math
import sys
from pathlib import Path

import pytest

EMULATION_DIR = Path(__file__).parent.parent.parent / "emulation"
sys.path.insert(0, str(EMULATION_DIR))

from emulation_utils import (
    compute_net_address,
    compute_link_utilization,
    compute_convergence_time,
    compute_packet_loss,
    compute_isl_subnet,
    compute_gs_subnet,
)


# ── Test 1 : make_latency_timeseries ─────────────────────────────────────────

class TestMakeLatencyTimeseries:
    """Tests de la fonction make_latency_timeseries dans generate_test_constellation.py."""

    @pytest.fixture(scope="class")
    def make_ts(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "gen", EMULATION_DIR / "generate_test_constellation.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.make_latency_timeseries

    def test_num_samples(self, make_ts):
        ts = make_ts(3.0, 0.8)
        assert len(ts) == 31

    def test_t0_latency_equals_base(self, make_ts):
        """À t=0, sin(0)=0 donc latency == base."""
        ts = make_ts(3.0, 0.8)
        assert abs(ts[0]["latency_ms"] - 3.0) < 0.001

    def test_t140_latency_near_max(self, make_ts):
        """À t=140s (index 7, le plus proche de π/2): sin(2π×140/600) ≈ 0.994."""
        ts = make_ts(3.0, 0.8)
        sample = ts[7]  # t = 7 × 20 = 140s
        assert sample["timestamp"] == 140
        expected = 3.0 + 0.8 * math.sin(2 * math.pi * 140 / 600)
        assert abs(sample["latency_ms"] - round(expected, 3)) < 0.001
        assert sample["latency_ms"] > 3.0 + 0.7

    def test_t300_latency_near_base(self, make_ts):
        """À t=300s : sin(π) ≈ 0 → latency ≈ base."""
        ts = make_ts(3.0, 0.8)
        sample_at_300 = [s for s in ts if s["timestamp"] == 300][0]
        expected = 3.0 + 0.8 * math.sin(2 * math.pi * 300 / 600)
        assert abs(sample_at_300["latency_ms"] - round(expected, 3)) < 0.01

    def test_all_latencies_above_minimum(self, make_ts):
        """Toutes les valeurs ≥ 0.5ms (plancher dans le source)."""
        ts = make_ts(3.0, 0.8)
        bad = [s for s in ts if s["latency_ms"] < 0.5]
        assert bad == []


# ── Test 2 : Calcul utilisation liens ────────────────────────────────────────

class TestLinkUtilization:
    """Tests de compute_link_utilization depuis emulation_utils.py."""

    def test_basic_utilization(self):
        """125 000 bytes, dt=1s, bw=1000 Mbps → 1 Mbps → 0.1%"""
        tx, rx, util = compute_link_utilization(125_000, 125_000, 1.0, 1000)
        assert abs(tx - 1.0) < 0.0001
        assert abs(rx - 1.0) < 0.0001
        assert abs(util - 0.1) < 0.01

    def test_utilization_uses_max(self):
        """Utilisation = max(tx, rx) / bw."""
        _, _, util = compute_link_utilization(1_000_000, 500_000, 1.0, 1000)
        # tx_rate = 8 Mbps, rx_rate = 4 Mbps → max = 8 → 0.8%
        assert abs(util - 0.8) < 0.01

    def test_zero_bandwidth_returns_zero(self):
        _, _, util = compute_link_utilization(100, 100, 1.0, 0)
        assert util == 0

    def test_high_utilization(self):
        """500 000 000 bytes in 1s = 4000 Mbps → 400% sur 1 Gbps"""
        tx, rx, util = compute_link_utilization(500_000_000, 0, 1.0, 1000)
        assert abs(tx - 4000.0) < 0.1
        assert abs(util - 400.0) < 0.1


# ── Test 3 : Temps de convergence ────────────────────────────────────────────

class TestConvergenceTime:
    """Tests de compute_convergence_time depuis emulation_utils.py."""

    def test_route_dominates(self):
        assert compute_convergence_time(2.5, 7.3) == 7.3

    def test_adj_dominates(self):
        assert compute_convergence_time(5.0, 3.1) == 5.0

    def test_equal_times(self):
        assert compute_convergence_time(4.0, 4.0) == 4.0

    def test_zero_route_time(self):
        assert compute_convergence_time(3.0, 0.0) == 3.0


# ── Test 4 : Perte de paquets ─────────────────────────────────────────────────

class TestPacketLoss:
    """Tests de compute_packet_loss depuis emulation_utils.py."""

    def test_30_percent_loss(self):
        lost, pct = compute_packet_loss(10, 7)
        assert lost == 3
        assert pct == 30.0

    def test_zero_loss(self):
        lost, pct = compute_packet_loss(10, 10)
        assert lost == 0
        assert pct == 0.0

    def test_100_percent_loss(self):
        lost, pct = compute_packet_loss(10, 0)
        assert lost == 10
        assert pct == 100.0

    def test_zero_sent(self):
        _, pct = compute_packet_loss(0, 0)
        assert pct == 0.0


# ── Test 5 : Adresses NET ISIS ────────────────────────────────────────────────

class TestNETAddress:
    """Tests de compute_net_address depuis emulation_utils.py.
    Même logique que generate_isis_config() dans isis_routing.py."""

    def test_sat0_flat(self):
        assert compute_net_address("sat0", is_gs=False) == "49.0001.0000.0001.0000.00"

    def test_gs0_flat(self):
        assert compute_net_address("gs0", is_gs=True) == "49.0001.0000.0000.0000.00"

    def test_sat0_plane0_with_areas(self):
        assert compute_net_address("sat0", is_gs=False, plane_id=0) == "49.0001.0000.0001.0000.00"

    def test_sat4_plane1_with_areas(self):
        assert compute_net_address("sat4", is_gs=False, plane_id=1) == "49.0002.0000.0001.0004.00"

    def test_gs1_flat(self):
        assert compute_net_address("gs1", is_gs=True) == "49.0001.0000.0000.0001.00"

    def test_net_starts_with_49(self):
        for hostname, is_gs in [("sat0", False), ("sat7", False), ("gs0", True), ("gs1", True)]:
            assert compute_net_address(hostname, is_gs).startswith("49.")

    def test_net_ends_with_00(self):
        for hostname, is_gs in [("sat0", False), ("sat7", False), ("gs0", True), ("gs1", True)]:
            assert compute_net_address(hostname, is_gs).endswith(".00")


# ── Test 6 : Allocation IP des liens ─────────────────────────────────────────

class TestIPAllocation:
    """Tests de compute_isl_subnet et compute_gs_subnet depuis emulation_utils.py.
    Miroir de la logique dans create_network() et DynamicGSLinkManager.connect()."""

    def test_isl_starts_with_10(self):
        for i in range(12):
            assert compute_isl_subnet(i).startswith("10.")

    def test_gs_starts_with_192(self):
        # link_counter de DynamicGSLinkManager commence à 50000, pré-incrémenté → 50001
        for i in range(4):
            assert compute_gs_subnet(50001 + i).startswith("192.")

    def test_no_overlap_isl_gs(self):
        isl_subnets = {compute_isl_subnet(i) for i in range(12)}
        gs_subnets = {compute_gs_subnet(50001 + i) for i in range(4)}
        overlap = isl_subnets & gs_subnets
        assert overlap == set(), f"Chevauchement IP: {overlap}"

    def test_isl_subnets_unique(self):
        subnets = [compute_isl_subnet(i) for i in range(12)]
        assert len(subnets) == len(set(subnets)), "Sous-réseaux ISL dupliqués"
