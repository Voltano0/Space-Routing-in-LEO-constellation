"""
test_input_schema.py
Vérifie la structure et l'intégrité du JSON d'entrée généré.
"""

import pytest
from conftest import (
    TOTAL_SATS, ISL_TOTAL, ISL_INTRA_COUNT, ISL_INTER_COUNT,
    GS_EVENT_COUNT, NUM_SAMPLES, ISL_BW_MBPS,
)


@pytest.fixture
def data(generated_json):
    return generated_json


def test_sections_required(data):
    for section in ["metadata", "topology", "islLinks", "gsLinks", "statistics"]:
        assert section in data, f"Section '{section}' manquante"


def test_metadata_version(data):
    assert data["metadata"]["version"] == "4.0"


def test_metadata_format(data):
    assert data["metadata"]["format"] == "mininet-isl-gs-timeseries"


def test_metadata_mode(data):
    assert data["metadata"]["mode"] == "timeseries"


def test_metadata_has_ground_stations(data):
    assert data["metadata"]["hasGroundStations"] is True


def test_total_satellites_count(data):
    meta_count = data["metadata"]["constellation"]["totalSatellites"]
    topo_count = len(data["topology"]["satellites"])
    assert meta_count == TOTAL_SATS
    assert topo_count == TOTAL_SATS


def test_ground_stations_count(data):
    assert len(data["topology"]["groundStations"]) == 2


def test_isl_links_count_matches_statistics(data):
    assert len(data["islLinks"]) == data["statistics"]["totalISLLinks"]


def test_isl_links_total(data):
    assert len(data["islLinks"]) == ISL_TOTAL


def test_isl_intra_count(data):
    intra = [l for l in data["islLinks"] if l["type"] == "intra-plane"]
    assert len(intra) == ISL_INTRA_COUNT


def test_isl_inter_count(data):
    inter = [l for l in data["islLinks"] if l["type"] == "inter-plane"]
    assert len(inter) == ISL_INTER_COUNT


def test_isl_sat_ids_exist_in_topology(data):
    valid_ids = {s["id"] for s in data["topology"]["satellites"]}
    for link in data["islLinks"]:
        assert link["satA"] in valid_ids, f"satA={link['satA']} inexistant"
        assert link["satB"] in valid_ids, f"satB={link['satB']} inexistant"


def test_isl_canonical_order(data):
    """satA < satB pour chaque lien."""
    bad = [(l["satA"], l["satB"]) for l in data["islLinks"] if l["satA"] >= l["satB"]]
    assert bad == [], f"Liens mal ordonnés: {bad}"


def test_isl_no_duplicates(data):
    pairs = [(l["satA"], l["satB"]) for l in data["islLinks"]]
    assert len(pairs) == len(set(pairs)), "Doublons détectés dans islLinks"


def test_isl_sample_count(data):
    """Chaque ISL a exactement NUM_SAMPLES (31) échantillons."""
    bad = [
        (l["satA"], l["satB"], len(l.get("timeSeries", [])))
        for l in data["islLinks"]
        if len(l.get("timeSeries", [])) != NUM_SAMPLES
    ]
    assert bad == [], f"Liens avec mauvais nombre d'échantillons: {bad}"


def test_isl_valid_types(data):
    valid = {"intra-plane", "inter-plane"}
    bad = [l["type"] for l in data["islLinks"] if l["type"] not in valid]
    assert bad == [], f"Types invalides: {bad}"


def test_isl_bandwidth(data):
    bad = [l for l in data["islLinks"] if l.get("bandwidth_mbps") != ISL_BW_MBPS]
    assert bad == [], f"{len(bad)} liens avec bandwidth ≠ {ISL_BW_MBPS} Mbps"


def test_gs_events_count_matches_statistics(data):
    assert len(data["gsLinks"]["events"]) == data["statistics"]["totalGSEvents"]


def test_gs_events_total(data):
    assert len(data["gsLinks"]["events"]) == GS_EVENT_COUNT


def test_gs_timeline_present(data):
    assert isinstance(data["gsLinks"].get("timeline"), list)
    assert len(data["gsLinks"]["timeline"]) > 0
