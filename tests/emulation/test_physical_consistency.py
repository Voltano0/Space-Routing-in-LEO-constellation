"""
test_physical_consistency.py
Vérifie la cohérence physique latence ↔ distance dans le JSON généré.

Note : le générateur utilise distance_km = latency_ms × 200 (approximation),
alors que la vraie vitesse de la lumière donne × 299.792. Écart ≈ 33%.
"""

import math
import pytest
from conftest import (
    DIST_FACTOR,
    INTRA_LATENCY_MIN, INTRA_LATENCY_MAX,
    INTER_LATENCY_MIN, INTER_LATENCY_MAX,
    INTRA_DIST_MIN, INTRA_DIST_MAX,
    INTER_DIST_MIN, INTER_DIST_MAX,
    ORBITAL_PERIOD_S, SAMPLING_INTERVAL_S,
)

SPEED_OF_LIGHT_KM_PER_S = 299.792  # km/ms (c en km/ms)
DIST_TOLERANCE_KM = 0.2


@pytest.fixture
def data(generated_json):
    return generated_json


def test_distance_uses_factor_200(data):
    """Le générateur calcule distance_km = latency_ms × 200 (et non × 299.792)."""
    for link in data["islLinks"]:
        for sample in link["timeSeries"]:
            expected = round(sample["latency_ms"] * DIST_FACTOR, 1)
            assert abs(sample["distance_km"] - expected) <= DIST_TOLERANCE_KM, (
                f"Link ({link['satA']},{link['satB']}) t={sample['timestamp']}s: "
                f"distance={sample['distance_km']} ≠ {expected} (latency×{DIST_FACTOR})"
            )


def test_approximation_vs_real_light_speed(data):
    """
    Documente l'écart entre l'approximation (×200) et la vraie physique (×299.792).
    L'écart attendu est ~33%.
    Ce test passe toujours ; il mesure et affirme l'existence de l'écart.
    """
    diffs = []
    for link in data["islLinks"]:
        for sample in link["timeSeries"]:
            approx = sample["distance_km"]
            real = sample["latency_ms"] * SPEED_OF_LIGHT_KM_PER_S
            if real > 0:
                diffs.append(abs(approx - real) / real * 100)

    avg_diff_pct = sum(diffs) / len(diffs) if diffs else 0
    # L'approximation doit être systématiquement ~33% inférieure à la réalité
    assert avg_diff_pct > 20, (
        f"Écart moyen approximation vs réalité trop faible ({avg_diff_pct:.1f}%), "
        "le générateur a peut-être été corrigé ?"
    )


def test_intra_plane_latency_in_range(data):
    intra = [l for l in data["islLinks"] if l["type"] == "intra-plane"]
    for link in intra:
        for sample in link["timeSeries"]:
            lat = sample["latency_ms"]
            assert INTRA_LATENCY_MIN - 0.01 <= lat <= INTRA_LATENCY_MAX + 0.01, (
                f"Intra link ({link['satA']},{link['satB']}) t={sample['timestamp']}s: "
                f"latency={lat}ms hors plage [{INTRA_LATENCY_MIN}, {INTRA_LATENCY_MAX}]"
            )


def test_inter_plane_latency_in_range(data):
    inter = [l for l in data["islLinks"] if l["type"] == "inter-plane"]
    for link in inter:
        for sample in link["timeSeries"]:
            lat = sample["latency_ms"]
            assert INTER_LATENCY_MIN - 0.01 <= lat <= INTER_LATENCY_MAX + 0.01, (
                f"Inter link ({link['satA']},{link['satB']}) t={sample['timestamp']}s: "
                f"latency={lat}ms hors plage [{INTER_LATENCY_MIN}, {INTER_LATENCY_MAX}]"
            )


def test_intra_plane_distance_in_range(data):
    intra = [l for l in data["islLinks"] if l["type"] == "intra-plane"]
    for link in intra:
        for sample in link["timeSeries"]:
            dist = sample["distance_km"]
            assert INTRA_DIST_MIN - 1 <= dist <= INTRA_DIST_MAX + 1, (
                f"Intra link ({link['satA']},{link['satB']}) t={sample['timestamp']}s: "
                f"distance={dist}km hors plage [{INTRA_DIST_MIN}, {INTRA_DIST_MAX}]"
            )


def test_timestamps_monotonically_increasing(data):
    for link in data["islLinks"]:
        ts = [s["timestamp"] for s in link["timeSeries"]]
        for i in range(1, len(ts)):
            assert ts[i] > ts[i - 1], (
                f"Link ({link['satA']},{link['satB']}): "
                f"timestamps non croissants: {ts[i - 1]} → {ts[i]}"
            )


def test_timestamps_interval(data):
    """Intervalle entre timestamps == SAMPLING_INTERVAL_S (20s)."""
    for link in data["islLinks"]:
        ts = [s["timestamp"] for s in link["timeSeries"]]
        for i in range(1, len(ts)):
            diff = ts[i] - ts[i - 1]
            assert diff == SAMPLING_INTERVAL_S, (
                f"Link ({link['satA']},{link['satB']}): "
                f"intervalle {diff}s ≠ {SAMPLING_INTERVAL_S}s entre t={ts[i-1]} et t={ts[i]}"
            )


def test_first_timestamp_is_zero(data):
    for link in data["islLinks"]:
        assert link["timeSeries"][0]["timestamp"] == 0, (
            f"Link ({link['satA']},{link['satB']}): premier timestamp ≠ 0"
        )


def test_last_timestamp_is_orbital_period(data):
    for link in data["islLinks"]:
        ts = link["timeSeries"]
        assert ts[-1]["timestamp"] == ORBITAL_PERIOD_S, (
            f"Link ({link['satA']},{link['satB']}): dernier timestamp {ts[-1]['timestamp']} ≠ {ORBITAL_PERIOD_S}"
        )


def test_all_latencies_positive(data):
    for link in data["islLinks"]:
        for sample in link["timeSeries"]:
            assert sample["latency_ms"] > 0, (
                f"Link ({link['satA']},{link['satB']}) t={sample['timestamp']}s: "
                f"latency={sample['latency_ms']}ms ≤ 0"
            )
