#!/usr/bin/env python3
"""
Split a Mininet ISL+GS timeseries JSON (terrestrial period) into
one JSON file per orbital period.

Usage:
    python3 split_by_orbital_period.py <input.json> [output_dir]

Output:
    output_dir/orbital_period_01.json
    output_dir/orbital_period_02.json
    ...

Each output file is a self-contained Mininet JSON with:
  - metadata.simulation updated (numPeriods=1, duration_s = orbital period)
  - metadata.orbitalPeriodIndex added (0-based)
  - islLinks timeSeries filtered & timestamps shifted to [0, orbital_period]
  - gsLinks.events filtered & timestamps shifted
  - gsLinks.timeline entries filtered, trimmed & timestamps shifted
  - topology unchanged
"""

import copy
import json
import math
import os
import sys


def get_orbital_period_s(data):
    """Extract orbital period in seconds from metadata."""
    sim = data["metadata"]["simulation"]
    return sim["orbitalPeriod_min"] * 60


def get_actual_duration(data):
    """Find the actual max timestamp across all data."""
    max_t = 0

    for link in data.get("islLinks", []):
        for sample in link.get("timeSeries", []):
            max_t = max(max_t, sample["timestamp"])

    for event in data.get("gsLinks", {}).get("events", []):
        max_t = max(max_t, event["t"])

    for entry in data.get("gsLinks", {}).get("timeline", []):
        for sample in entry.get("samples", []):
            max_t = max(max_t, sample["t"])

    return max_t


def split_isl_links(isl_links, t_start, t_end, sampling_interval):
    """
    Filter ISL timeSeries to samples within [t_start, t_end)
    and shift timestamps so the period starts at sampling_interval.
    """
    result = []
    for link in isl_links:
        new_link = {
            "satA": link["satA"],
            "satB": link["satB"],
            "type": link.get("type", "unknown"),
            "bandwidth_mbps": link.get("bandwidth_mbps", 1000),
        }

        new_ts = []
        for sample in link.get("timeSeries", []):
            t = sample["timestamp"]
            if t_start <= t < t_end:
                new_ts.append({
                    "timestamp": round(t - t_start, 6),
                    "distance_km": sample["distance_km"],
                    "latency_ms": sample["latency_ms"],
                })

        new_link["timeSeries"] = new_ts
        # Only include links that have samples in this period
        if new_ts:
            result.append(new_link)

    return result


def split_gs_events(events, t_start, t_end):
    """
    Filter GS events to those within [t_start, t_end) and shift timestamps.
    For the first period slice, we also need to reconstruct initial connect
    events for GS that were already connected at t_start.
    """
    result = []
    for event in events:
        t = event["t"]
        if t_start <= t < t_end:
            new_event = dict(event)
            new_event["t"] = round(t - t_start, 6)
            result.append(new_event)

    return result


def find_active_gs_at_time(events, t_target):
    """
    Replay events up to t_target to determine which GS are connected
    and to which satellite at that moment.
    Returns {gs_id: {"satId": int, "latency_ms": float}}
    """
    active = {}
    for event in sorted(events, key=lambda e: e["t"]):
        if event["t"] >= t_target:
            break
        action = event["action"]
        gs_id = event["gsId"]
        if action == "connect":
            active[gs_id] = {
                "satId": event["satId"],
                "latency_ms": event.get("latency_ms", 5.0),
            }
        elif action == "disconnect":
            active.pop(gs_id, None)
        elif action == "handover":
            active[gs_id] = {
                "satId": event["toSatId"],
                "latency_ms": event.get("latency_ms", 5.0),
            }
    return active


def split_gs_events_with_initial_state(all_events, t_start, t_end):
    """
    Build the event list for a period [t_start, t_end).
    Injects synthetic 'connect' events at t=0 for GS that were already
    connected at t_start (from previous periods).
    """
    # Find what's connected at t_start
    active_at_start = find_active_gs_at_time(all_events, t_start)

    # Synthetic connect events at t=0
    initial_events = []
    for gs_id, info in sorted(active_at_start.items()):
        initial_events.append({
            "t": 0,
            "gsId": gs_id,
            "action": "connect",
            "satId": info["satId"],
            "latency_ms": info["latency_ms"],
        })

    # Actual events in this window
    period_events = split_gs_events(all_events, t_start, t_end)

    return initial_events + period_events


def split_gs_timeline(timeline, t_start, t_end):
    """
    Filter and trim GS timeline entries to [t_start, t_end).
    Shift timestamps so the period starts at 0.
    """
    result = []
    for entry in timeline:
        entry_start = entry.get("startTime") or 0
        entry_end = entry.get("endTime")
        if entry_end is None:
            entry_end = float("inf")

        # Check if this entry overlaps with our window
        if entry_end <= t_start or entry_start >= t_end:
            continue

        # Filter samples within window
        new_samples = []
        for sample in entry.get("samples", []):
            t = sample["t"]
            if t_start <= t < t_end:
                new_samples.append({
                    "t": round(t - t_start, 6),
                    "latency_ms": sample["latency_ms"],
                })

        if not new_samples:
            continue

        new_entry = {
            "gsId": entry["gsId"],
            "satId": entry["satId"],
            "startTime": round(max(entry_start, t_start) - t_start, 6),
            "endTime": round(min(entry_end, t_end) - t_start, 6),
            "samples": new_samples,
        }
        result.append(new_entry)

    return result


def build_period_json(data, period_index, t_start, t_end, orbital_period_s, sampling_interval):
    """Build a complete JSON for one orbital period."""
    out = {}

    # Metadata
    meta = copy.deepcopy(data["metadata"])
    meta["simulation"]["numPeriods"] = 1
    meta["simulation"]["duration_s"] = round(t_end - t_start, 6)
    meta["orbitalPeriodIndex"] = period_index
    meta["orbitalPeriodRange"] = {
        "start_s": round(t_start, 6),
        "end_s": round(t_end, 6),
    }
    out["metadata"] = meta

    # Topology (unchanged)
    out["topology"] = data["topology"]

    # ISL links
    out["islLinks"] = split_isl_links(
        data.get("islLinks", []), t_start, t_end, sampling_interval
    )

    # GS links
    all_events = data.get("gsLinks", {}).get("events", [])
    all_timeline = data.get("gsLinks", {}).get("timeline", [])

    out["gsLinks"] = {
        "events": split_gs_events_with_initial_state(all_events, t_start, t_end),
        "timeline": split_gs_timeline(all_timeline, t_start, t_end),
    }

    return out


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <input.json> [output_dir]")
        print(f"Example: python3 {sys.argv[0]} mininet_isl_gs_timeseries_2026-02-16.json")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) >= 3 else "orbital_periods"

    # Load data
    print(f"Loading {input_file}...")
    with open(input_file) as f:
        data = json.load(f)

    orbital_period_s = get_orbital_period_s(data)
    actual_duration = get_actual_duration(data)
    sampling_interval = data["metadata"]["simulation"].get("samplingInterval_s", 20)
    num_periods = math.ceil(actual_duration / orbital_period_s)

    print(f"Orbital period: {orbital_period_s:.1f}s ({orbital_period_s/60:.1f} min)")
    print(f"Actual data duration: {actual_duration:.0f}s ({actual_duration/3600:.1f}h)")
    print(f"Number of orbital periods: {num_periods}")
    print(f"Sampling interval: {sampling_interval}s")

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Split
    for i in range(num_periods):
        t_start = i * orbital_period_s
        t_end = min((i + 1) * orbital_period_s, actual_duration + sampling_interval)

        period_data = build_period_json(
            data, i, t_start, t_end, orbital_period_s, sampling_interval
        )

        # Stats
        n_isl = len(period_data["islLinks"])
        n_isl_samples = sum(
            len(link["timeSeries"]) for link in period_data["islLinks"]
        )
        n_events = len(period_data["gsLinks"]["events"])
        n_timeline = len(period_data["gsLinks"]["timeline"])

        filename = f"orbital_period_{i+1:02d}.json"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w") as f:
            json.dump(period_data, f, indent=2)

        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        print(
            f"  [{i+1:2d}/{num_periods}] {filename} "
            f"t=[{t_start:.0f}s, {t_end:.0f}s] "
            f"ISL={n_isl} ({n_isl_samples} samples) "
            f"GS events={n_events} timeline={n_timeline} "
            f"({size_mb:.1f} MB)"
        )

    print(f"\nDone. {num_periods} files written to {output_dir}/")


if __name__ == "__main__":
    main()
