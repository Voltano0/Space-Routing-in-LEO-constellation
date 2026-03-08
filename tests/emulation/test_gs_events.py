"""
test_gs_events.py
Vérifie le séquencement et la cohérence des événements Ground Station.
"""

import pytest
from collections import defaultdict


@pytest.fixture
def data(generated_json):
    return generated_json


@pytest.fixture
def events_by_gs(data):
    events = data["gsLinks"]["events"]
    by_gs = defaultdict(list)
    for e in sorted(events, key=lambda x: x["t"]):
        by_gs[e["gsId"]].append(e)
    return dict(by_gs)


@pytest.fixture
def timeline_by_gs(data):
    by_gs = defaultdict(list)
    for entry in data["gsLinks"].get("timeline", []):
        by_gs[entry["gsId"]].append(entry)
    return dict(by_gs)


def test_first_event_per_gs_is_connect(events_by_gs):
    for gs_id, events in events_by_gs.items():
        assert events[0]["action"] == "connect", (
            f"{gs_id}: premier événement '{events[0]['action']}' ≠ 'connect'"
        )


def test_last_event_per_gs_is_disconnect(events_by_gs):
    for gs_id, events in events_by_gs.items():
        assert events[-1]["action"] == "disconnect", (
            f"{gs_id}: dernier événement '{events[-1]['action']}' ≠ 'disconnect'"
        )


def test_valid_actions(data):
    valid = {"connect", "handover", "disconnect"}
    bad = [e for e in data["gsLinks"]["events"] if e["action"] not in valid]
    assert bad == [], f"Actions invalides: {[e['action'] for e in bad]}"


def test_connect_has_required_fields(data):
    for e in data["gsLinks"]["events"]:
        if e["action"] == "connect":
            assert "gsId" in e
            assert "satId" in e
            assert "latency_ms" in e


def test_handover_has_required_fields(data):
    for e in data["gsLinks"]["events"]:
        if e["action"] == "handover":
            assert "gsId" in e
            assert "fromSatId" in e
            assert "toSatId" in e
            assert "latency_ms" in e


def test_disconnect_has_gs_id(data):
    for e in data["gsLinks"]["events"]:
        if e["action"] == "disconnect":
            assert "gsId" in e


def test_timestamps_strictly_increasing_per_gs(events_by_gs):
    for gs_id, events in events_by_gs.items():
        times = [e["t"] for e in events]
        for i in range(1, len(times)):
            assert times[i] > times[i - 1], (
                f"{gs_id}: timestamps non strictement croissants: {times[i-1]} → {times[i]}"
            )


def test_gs0_expected_timestamps(events_by_gs):
    """gs0 : t=20 (connect), t=200 (handover), t=400 (handover), t=560 (disconnect)"""
    expected = [20, 200, 400, 560]
    ts = [e["t"] for e in events_by_gs.get("gs0", [])]
    assert ts == expected, f"gs0 timestamps: {ts} ≠ {expected}"


def test_gs1_expected_timestamps(events_by_gs):
    """gs1 : t=60, t=300, t=500, t=570"""
    expected = [60, 300, 500, 570]
    ts = [e["t"] for e in events_by_gs.get("gs1", [])]
    assert ts == expected, f"gs1 timestamps: {ts} ≠ {expected}"


def test_timeline_start_end_coherent(timeline_by_gs):
    """startTime < endTime pour chaque segment de timeline."""
    for gs_id, segments in timeline_by_gs.items():
        for seg in segments:
            assert seg["startTime"] < seg["endTime"], (
                f"{gs_id} sat{seg['satId']}: startTime={seg['startTime']} ≥ endTime={seg['endTime']}"
            )


def test_timeline_contiguous_per_gs(timeline_by_gs):
    """Les segments d'une même GS sont contigus (endTime[i] == startTime[i+1])."""
    for gs_id, segments in timeline_by_gs.items():
        sorted_segs = sorted(segments, key=lambda s: s["startTime"])
        for i in range(1, len(sorted_segs)):
            prev_end = sorted_segs[i - 1]["endTime"]
            next_start = sorted_segs[i]["startTime"]
            assert prev_end == next_start, (
                f"{gs_id}: gap entre segments: endTime={prev_end} ≠ startTime={next_start}"
            )


def test_no_overlap_per_gs(timeline_by_gs):
    """Pas de chevauchement temporel dans la timeline d'une GS."""
    for gs_id, segments in timeline_by_gs.items():
        sorted_segs = sorted(segments, key=lambda s: s["startTime"])
        for i in range(1, len(sorted_segs)):
            assert sorted_segs[i]["startTime"] >= sorted_segs[i - 1]["endTime"], (
                f"{gs_id}: chevauchement entre sat{sorted_segs[i-1]['satId']} "
                f"et sat{sorted_segs[i]['satId']}"
            )
