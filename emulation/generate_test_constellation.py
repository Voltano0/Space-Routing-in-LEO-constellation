#!/usr/bin/env python3
"""
Generate a small test constellation JSON for quick ISIS metrics validation.

Constellation: 8 satellites, 2 orbital planes, 2 ground stations
Orbital period: 600s (10 minutes)
Format: v4.0 (compatible with mininet_gs_timeseries.py)

Usage:
    python3 generate_test_constellation.py
    -> produces test_8sat_10min.json

Then run:
    sudo python3 mininet_gs_timeseries.py test_8sat_10min.json
    mininet> routing isis-areas
    mininet> metrics start
    mininet> start
    (auto-stops after 10 min and exports metrics)
"""

import json
import math
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────

NUM_PLANES = 2
SATS_PER_PLANE = 4
TOTAL_SATS = NUM_PLANES * SATS_PER_PLANE  # 8
ALTITUDE_KM = 550
INCLINATION_DEG = 55
ORBITAL_PERIOD_S = 600  # 10 minutes
SAMPLING_INTERVAL_S = 20  # sample every 20s
NUM_SAMPLES = ORBITAL_PERIOD_S // SAMPLING_INTERVAL_S + 1  # 31

# ISL bandwidth
ISL_BW_MBPS = 1000
ISL_BASE_LATENCY_INTRA = 3.0   # ms, intra-plane base
ISL_BASE_LATENCY_INTER = 8.0   # ms, inter-plane base

# Ground stations
GROUND_STATIONS = [
    {"id": "gs0", "name": "Paris",    "lat": 48.8566, "lon": 2.3522},
    {"id": "gs1", "name": "New York", "lat": 40.7128, "lon": -74.0060},
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_latency_timeseries(base_latency_ms, variation_ms=1.5):
    """
    Generate a realistic latency timeseries with sinusoidal variation.
    Simulates orbital motion causing slight latency changes.
    """
    samples = []
    for i in range(NUM_SAMPLES):
        t = i * SAMPLING_INTERVAL_S
        # Sinusoidal variation over the orbit
        phase = 2 * math.pi * t / ORBITAL_PERIOD_S
        latency = base_latency_ms + variation_ms * math.sin(phase)
        latency = max(0.5, latency)  # minimum 0.5ms
        samples.append({
            "timestamp": t,
            "latency_ms": round(latency, 3),
            "distance_km": round(latency * 200, 1),  # rough c approximation
        })
    return samples


def make_gs_events():
    """
    Generate GS link events: connects, handovers, disconnects.
    Designed to produce ~4-6 convergence events in 10 min.

    gs0 (Paris):  connects sat0 at t=20, handover to sat1 at t=200, to sat2 at t=400
    gs1 (New York): connects sat4 at t=60, handover to sat5 at t=300, to sat6 at t=500
    """
    events = [
        # gs0: connect -> handover -> handover -> disconnect
        {"t": 20,  "action": "connect",    "gsId": "gs0", "satId": 0, "latency_ms": 5.0},
        {"t": 200, "action": "handover",   "gsId": "gs0", "fromSatId": 0, "toSatId": 1, "latency_ms": 4.5},
        {"t": 400, "action": "handover",   "gsId": "gs0", "fromSatId": 1, "toSatId": 2, "latency_ms": 5.2},
        {"t": 560, "action": "disconnect", "gsId": "gs0"},

        # gs1: connect -> handover -> handover -> disconnect
        {"t": 60,  "action": "connect",    "gsId": "gs1", "satId": 4, "latency_ms": 6.0},
        {"t": 300, "action": "handover",   "gsId": "gs1", "fromSatId": 4, "toSatId": 5, "latency_ms": 5.8},
        {"t": 500, "action": "handover",   "gsId": "gs1", "fromSatId": 5, "toSatId": 6, "latency_ms": 6.1},
        {"t": 570, "action": "disconnect", "gsId": "gs1"},
    ]
    return events


def make_gs_timeline():
    """Generate GS latency timeline for each connection period."""
    timeline = []

    # gs0 -> sat0 (t=20 to t=200)
    timeline.append({
        "gsId": "gs0", "satId": 0, "startTime": 20, "endTime": 200,
        "samples": [{"t": t, "latency_ms": round(5.0 + 0.5 * math.sin(t / 50), 3)}
                    for t in range(20, 200, 20)]
    })
    # gs0 -> sat1 (t=200 to t=400)
    timeline.append({
        "gsId": "gs0", "satId": 1, "startTime": 200, "endTime": 400,
        "samples": [{"t": t, "latency_ms": round(4.5 + 0.8 * math.sin(t / 60), 3)}
                    for t in range(200, 400, 20)]
    })
    # gs0 -> sat2 (t=400 to t=560)
    timeline.append({
        "gsId": "gs0", "satId": 2, "startTime": 400, "endTime": 560,
        "samples": [{"t": t, "latency_ms": round(5.2 + 0.6 * math.sin(t / 40), 3)}
                    for t in range(400, 560, 20)]
    })

    # gs1 -> sat4 (t=60 to t=300)
    timeline.append({
        "gsId": "gs1", "satId": 4, "startTime": 60, "endTime": 300,
        "samples": [{"t": t, "latency_ms": round(6.0 + 0.7 * math.sin(t / 55), 3)}
                    for t in range(60, 300, 20)]
    })
    # gs1 -> sat5 (t=300 to t=500)
    timeline.append({
        "gsId": "gs1", "satId": 5, "startTime": 300, "endTime": 500,
        "samples": [{"t": t, "latency_ms": round(5.8 + 0.5 * math.sin(t / 45), 3)}
                    for t in range(300, 500, 20)]
    })
    # gs1 -> sat6 (t=500 to t=570)
    timeline.append({
        "gsId": "gs1", "satId": 6, "startTime": 500, "endTime": 570,
        "samples": [{"t": t, "latency_ms": round(6.1 + 0.4 * math.sin(t / 50), 3)}
                    for t in range(500, 570, 20)]
    })

    return timeline


# ── Build the full JSON ──────────────────────────────────────────────────────

def generate():
    # Satellites
    satellites = []
    for i in range(TOTAL_SATS):
        satellites.append({
            "id": i,
            "name": f"sat{i}",
            "type": "satellite",
            "plane": i // SATS_PER_PLANE,
        })

    # Ground stations
    ground_stations = [
        {"id": gs["id"], "name": gs["name"], "type": "groundStation",
         "lat": gs["lat"], "lon": gs["lon"]}
        for gs in GROUND_STATIONS
    ]

    # ISL links
    isl_links = []

    # Intra-plane rings: 0-1-2-3-0, 4-5-6-7-4
    for plane in range(NUM_PLANES):
        base = plane * SATS_PER_PLANE
        for j in range(SATS_PER_PLANE):
            satA = base + j
            satB = base + (j + 1) % SATS_PER_PLANE
            if satA < satB:  # avoid duplicates
                isl_links.append({
                    "satA": satA,
                    "satB": satB,
                    "type": "intra-plane",
                    "bandwidth_mbps": ISL_BW_MBPS,
                    "timeSeries": make_latency_timeseries(ISL_BASE_LATENCY_INTRA, 0.8),
                })
            else:
                # Ring closure (e.g., 3->0): satA > satB
                isl_links.append({
                    "satA": satB,
                    "satB": satA,
                    "type": "intra-plane",
                    "bandwidth_mbps": ISL_BW_MBPS,
                    "timeSeries": make_latency_timeseries(ISL_BASE_LATENCY_INTRA, 0.8),
                })

    # Inter-plane links: sat_i <-> sat_{i + SATS_PER_PLANE}
    for j in range(SATS_PER_PLANE):
        satA = j
        satB = j + SATS_PER_PLANE
        isl_links.append({
            "satA": satA,
            "satB": satB,
            "type": "inter-plane",
            "bandwidth_mbps": ISL_BW_MBPS,
            "timeSeries": make_latency_timeseries(ISL_BASE_LATENCY_INTER, 2.0),
        })

    # Deduplicate (satA, satB) pairs
    seen = set()
    deduped = []
    for link in isl_links:
        key = (min(link["satA"], link["satB"]), max(link["satA"], link["satB"]))
        if key not in seen:
            seen.add(key)
            deduped.append(link)
    isl_links = deduped

    # Full data structure
    data = {
        "metadata": {
            "exportDate": datetime.now().isoformat(),
            "format": "mininet-isl-gs-timeseries",
            "version": "4.0",
            "mode": "timeseries",
            "hasGroundStations": True,
            "constellation": {
                "totalSatellites": TOTAL_SATS,
                "planes": NUM_PLANES,
                "phase": 1,
                "altitude_km": ALTITUDE_KM,
                "inclination_deg": INCLINATION_DEG,
            },
            "simulation": {
                "orbitalPeriod_min": ORBITAL_PERIOD_S / 60,
                "samplingInterval_s": SAMPLING_INTERVAL_S,
                "numPeriods": 1,
                "duration_s": ORBITAL_PERIOD_S,
            },
        },
        "topology": {
            "satellites": satellites,
            "groundStations": ground_stations,
        },
        "islLinks": isl_links,
        "gsLinks": {
            "events": make_gs_events(),
            "timeline": make_gs_timeline(),
        },
        "statistics": {
            "totalISLLinks": len(isl_links),
            "totalGSEvents": len(make_gs_events()),
        },
    }

    outfile = "test_8sat_10min.json"
    with open(outfile, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Generated: {outfile}")
    print(f"  Satellites:    {TOTAL_SATS} ({NUM_PLANES} planes x {SATS_PER_PLANE})")
    print(f"  Ground stations: {len(GROUND_STATIONS)}")
    print(f"  ISL links:     {len(isl_links)}")
    print(f"  GS events:     {len(data['gsLinks']['events'])}")
    print(f"  Orbital period: {ORBITAL_PERIOD_S}s ({ORBITAL_PERIOD_S // 60} min)")
    print()
    print("To run:")
    print(f"  sudo python3 mininet_gs_timeseries.py {outfile}")
    print("  mininet> routing isis-areas")
    print("  mininet> metrics start")
    print("  mininet> start")
    print("  (auto-stops after 10 min, exports metrics, then run plot_isis_metrics.py)")


if __name__ == "__main__":
    generate()
