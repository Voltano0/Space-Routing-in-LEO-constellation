#!/usr/bin/env python3
"""Plot IS-IS routing metrics from emulation JSON data."""

import json
import sys
import os
import glob
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict

# ── Load data ────────────────────────────────────────────────────────────────

def load_metrics(path=None):
    """Load the most recent isis_metrics JSON file, or the one given."""
    if path is None:
        files = sorted(glob.glob(os.path.join(os.path.dirname(__file__),
                                               "isis_metrics_*.json")))
        if not files:
            print("No isis_metrics_*.json file found"); sys.exit(1)
        path = files[-1]
    with open(path) as f:
        data = json.load(f)
    print(f"Loaded: {path}")
    return data, os.path.splitext(os.path.basename(path))[0]


def make_output_dir(tag):
    out = os.path.join(os.path.dirname(__file__), "plots", tag)
    os.makedirs(out, exist_ok=True)
    return out


# ── Plots ────────────────────────────────────────────────────────────────────

def plot_convergence_timeline(events, out):
    """Convergence time over the simulation timeline, colored by GS."""
    if not events:
        return
    gs_ids = sorted(set(e["gs_id"] for e in events))
    colors = plt.cm.tab10(np.linspace(0, 1, max(len(gs_ids), 1)))
    gs_color = {gs: colors[i] for i, gs in enumerate(gs_ids)}

    fig, ax = plt.subplots(figsize=(14, 5))
    for e in events:
        ax.scatter(e["timestamp"], e["convergence_time_s"],
                   color=gs_color[e["gs_id"]], s=30, zorder=3)
    # legend
    for gs in gs_ids:
        ax.scatter([], [], color=gs_color[gs], label=gs, s=30)
    ax.set_xlabel("Simulation time (s)")
    ax.set_ylabel("Convergence time (s)")
    ax.set_title("IS-IS Convergence Time per Handover Event")
    ax.legend(fontsize=7, ncol=2, title="Ground station")
    ax.grid(True, alpha=.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "convergence_timeline.png"), dpi=200)
    plt.close(fig)
    print("  -> convergence_timeline.png")


def plot_convergence_histogram(events, out):
    """Distribution of convergence times."""
    if not events:
        return
    times = [e["convergence_time_s"] for e in events]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(times, bins=25, edgecolor="black", alpha=.75)
    ax.axvline(np.mean(times), color="red", ls="--",
               label=f"Mean = {np.mean(times):.2f} s")
    ax.axvline(np.median(times), color="orange", ls="--",
               label=f"Median = {np.median(times):.2f} s")
    ax.set_xlabel("Convergence time (s)")
    ax.set_ylabel("Count")
    ax.set_title("Distribution of IS-IS Convergence Times")
    ax.legend()
    ax.grid(True, alpha=.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "convergence_histogram.png"), dpi=200)
    plt.close(fig)
    print("  -> convergence_histogram.png")


def plot_convergence_per_gs(events, out):
    """Box plot of convergence time per ground station."""
    if not events:
        return
    gs_data = defaultdict(list)
    for e in events:
        gs_data[e["gs_id"]].append(e["convergence_time_s"])
    gs_ids = sorted(gs_data.keys())

    fig, ax = plt.subplots(figsize=(10, 5))
    bp = ax.boxplot([gs_data[gs] for gs in gs_ids], tick_labels=gs_ids, patch_artist=True)
    colors = plt.cm.tab10(np.linspace(0, 1, len(gs_ids)))
    for patch, c in zip(bp["boxes"], colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.6)
    ax.set_xlabel("Ground Station")
    ax.set_ylabel("Convergence time (s)")
    ax.set_title("IS-IS Convergence Time by Ground Station")
    ax.grid(True, alpha=.3, axis="y")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "convergence_per_gs.png"), dpi=200)
    plt.close(fig)
    print("  -> convergence_per_gs.png")


def plot_handover_frequency(events, out):
    """Number of handover events per ground station over time (bar + timeline)."""
    if not events:
        return
    gs_counts = defaultdict(int)
    for e in events:
        gs_counts[e["gs_id"]] += 1
    gs_ids = sorted(gs_counts.keys())

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Bar chart: total handovers per GS
    colors = plt.cm.tab10(np.linspace(0, 1, len(gs_ids)))
    axes[0].bar(gs_ids, [gs_counts[gs] for gs in gs_ids], color=colors)
    axes[0].set_xlabel("Ground Station")
    axes[0].set_ylabel("Number of handovers")
    axes[0].set_title("Total Handovers per Ground Station")
    axes[0].grid(True, alpha=.3, axis="y")

    # Timeline: event markers
    gs_color = {gs: colors[i] for i, gs in enumerate(gs_ids)}
    for i, gs in enumerate(gs_ids):
        ts = [e["timestamp"] for e in events if e["gs_id"] == gs]
        axes[1].scatter(ts, [i] * len(ts), color=gs_color[gs], s=20, zorder=3)
    axes[1].set_yticks(range(len(gs_ids)))
    axes[1].set_yticklabels(gs_ids)
    axes[1].set_xlabel("Simulation time (s)")
    axes[1].set_title("Handover Events Timeline")
    axes[1].grid(True, alpha=.3)

    fig.tight_layout()
    fig.savefig(os.path.join(out, "handover_frequency.png"), dpi=200)
    plt.close(fig)
    print("  -> handover_frequency.png")


def plot_lsp_propagation(lsp_measurements, out):
    """LSP propagation delay across satellite nodes over time."""
    if not lsp_measurements:
        return
    # Collect only satellite nodes (positive propagation values)
    sat_delays = defaultdict(list)  # node -> list of delays
    timestamps = []
    avg_delays = []

    for m in lsp_measurements:
        t = m["timestamp"]
        prop = m["propagation"]
        delays = [v for v in prop.values() if v > 0]
        if delays:
            timestamps.append(t)
            avg_delays.append(np.mean(delays))
        for node, d in prop.items():
            if d > 0:
                sat_delays[node].append(d)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Average LSP propagation over time
    axes[0].scatter(timestamps, avg_delays, s=8, alpha=0.5)
    if len(timestamps) > 20:
        # rolling average
        window = max(len(timestamps) // 20, 1)
        rolling = np.convolve(avg_delays, np.ones(window)/window, mode="valid")
        axes[0].plot(timestamps[window-1:], rolling, color="red", lw=1.5,
                     label=f"Rolling avg (w={window})")
        axes[0].legend()
    axes[0].set_xlabel("Simulation time (s)")
    axes[0].set_ylabel("Mean LSP propagation delay (s)")
    axes[0].set_title("LSP Propagation Delay Over Time")
    axes[0].grid(True, alpha=.3)

    # Distribution of per-node max propagation
    max_per_node = {n: max(ds) for n, ds in sat_delays.items()
                    if n.startswith("sat")}
    if max_per_node:
        nodes = sorted(max_per_node.keys(), key=lambda x: int(x[3:]))
        vals = [max_per_node[n] for n in nodes]
        axes[1].bar(range(len(nodes)), vals, color="steelblue", alpha=.7)
        axes[1].set_xticks(range(len(nodes)))
        axes[1].set_xticklabels(nodes, rotation=90, fontsize=6)
        axes[1].set_ylabel("Max LSP propagation delay (s)")
        axes[1].set_title("Max LSP Propagation per Satellite (polled)")
        axes[1].grid(True, alpha=.3, axis="y")

    fig.tight_layout()
    fig.savefig(os.path.join(out, "lsp_propagation.png"), dpi=200)
    plt.close(fig)
    print("  -> lsp_propagation.png")


def plot_lsp_max_all_sats(lsp_measurements, total_sats, out):
    """
    Max LSP propagation delay for EVERY satellite in the constellation.
    Satellites not polled are shown as 0 (gray).
    """
    if not lsp_measurements:
        return

    # Collect max delay per satellite node
    sat_max = {}
    for m in lsp_measurements:
        for node, d in m["propagation"].items():
            if not node.startswith("sat"):
                continue
            if d > 0:
                sat_max[node] = max(sat_max.get(node, 0), d)

    # Build full list: all satellites 0..total_sats-1
    all_nodes = [f"sat{i}" for i in range(total_sats)]
    vals = [sat_max.get(n, 0) for n in all_nodes]
    colors = ["#4472C4" if v > 0 else "#D0D0D0" for v in vals]

    polled = sum(1 for v in vals if v > 0)
    not_polled = total_sats - polled
    mean_polled = np.mean([v for v in vals if v > 0]) if polled else 0
    max_val = max(vals) if vals else 0

    fig_width = max(12, total_sats * 0.12)
    fig, ax = plt.subplots(figsize=(fig_width, 6))

    ax.bar(range(total_sats), vals, color=colors, edgecolor="none", width=1.0)
    ax.axhline(mean_polled, color="red", ls="--", lw=1.2,
               label=f"Mean (polled) = {mean_polled:.4f} s")
    if max_val > 0:
        ax.axhline(max_val, color="orange", ls=":", lw=1,
                    label=f"Max = {max_val:.4f} s")

    # X-axis: show labels only every N sats to avoid clutter
    step = max(1, total_sats // 40)
    tick_pos = list(range(0, total_sats, step))
    ax.set_xticks(tick_pos)
    ax.set_xticklabels([f"sat{i}" for i in range(0, total_sats, step)],
                        rotation=90, fontsize=6)
    ax.set_xlim(-0.5, total_sats - 0.5)
    ax.set_xlabel("Satellite")
    ax.set_ylabel("Max LSP Propagation Delay (s)")
    ax.set_title(f"Max LSP Propagation Delay per Satellite "
                 f"({polled} polled / {not_polled} not polled)")

    from matplotlib.patches import Patch
    legend_extra = [Patch(facecolor="#4472C4", label=f"Polled ({polled})"),
                    Patch(facecolor="#D0D0D0", label=f"Not polled ({not_polled})")]
    ax.legend(handles=[ax.lines[0]] + ([ax.lines[1]] if max_val > 0 else [])
              + legend_extra, fontsize=8, ncol=2)
    ax.grid(True, alpha=.3, axis="y")

    fig.tight_layout()
    fig.savefig(os.path.join(out, "lsp_max_all_sats.png"), dpi=200)
    plt.close(fig)
    print("  -> lsp_max_all_sats.png")


def plot_adjacency_vs_route(events, out):
    """Compare adjacency up time vs route present time (convergence breakdown)."""
    if not events:
        return
    adj = [e.get("adjacency_up_time_s", 0) for e in events]
    route = [e.get("route_present_time_s", 0) for e in events]
    idx = np.arange(len(events))

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.bar(idx, adj, label="Adjacency formation", color="steelblue")
    ax.bar(idx, [r - a for r, a in zip(route, adj)], bottom=adj,
           label="Route computation", color="coral")
    ax.set_xlabel("Handover event #")
    ax.set_ylabel("Time (s)")
    ax.set_title("Convergence Breakdown: Adjacency vs Route Computation")
    ax.legend()
    ax.grid(True, alpha=.3, axis="y")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "adjacency_vs_route.png"), dpi=200)
    plt.close(fig)
    print("  -> adjacency_vs_route.png")


def plot_summary_table(summary, out):
    """Summary metrics as a figure table."""
    rows = [
        ["Total handovers", str(summary.get("total_handovers", "N/A"))],
        ["Avg convergence", f"{summary.get('avg_convergence_s', 0):.3f} s"],
        ["Max convergence", f"{summary.get('max_convergence_s', 0):.3f} s"],
        ["Min convergence", f"{summary.get('min_convergence_s', 0):.3f} s"],
        ["Avg packet loss", f"{summary.get('avg_packet_loss_pct', 0):.1f} %"],
        ["Avg interruption", f"{summary.get('avg_interruption_s', 0):.3f} s"],
        ["Max interruption", f"{summary.get('max_interruption_s', 0):.3f} s"],
        ["Total SPF events", str(summary.get("total_spf_events", 0))],
        ["Total LSP measurements", str(summary.get("total_lsp_measurements", 0))],
        ["Avg LSP propagation", f"{summary.get('avg_lsp_propagation_s', 0):.3f} s"],
        ["Collection duration", f"{summary.get('collection_duration_s', 0):.0f} s"],
    ]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.axis("off")
    table = ax.table(cellText=rows, colLabels=["Metric", "Value"],
                     loc="center", cellLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.5)
    # header style
    for j in range(2):
        table[0, j].set_facecolor("#4472C4")
        table[0, j].set_text_props(color="white", fontweight="bold")
    ax.set_title("IS-IS Emulation Summary", fontweight="bold", pad=20)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "summary_table.png"), dpi=200)
    plt.close(fig)
    print("  -> summary_table.png")


def plot_connect_vs_handover(events, out):
    """Separate convergence stats for 'connect' vs 'handover' triggers."""
    if not events:
        return
    triggers = defaultdict(list)
    for e in events:
        triggers[e.get("trigger", "unknown")].append(e["convergence_time_s"])

    if len(triggers) < 2:
        # Only one trigger type, skip
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    labels = sorted(triggers.keys())
    bp = ax.boxplot([triggers[t] for t in labels], tick_labels=labels, patch_artist=True)
    colors = ["#4472C4", "#ED7D31", "#70AD47", "#FFC000"]
    for patch, c in zip(bp["boxes"], colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.6)
    for t in labels:
        vals = triggers[t]
        ax.annotate(f"n={len(vals)}\nμ={np.mean(vals):.2f}s",
                    xy=(labels.index(t) + 1, np.median(vals)),
                    xytext=(10, 20), textcoords="offset points",
                    fontsize=8, ha="left",
                    arrowprops=dict(arrowstyle="->", color="gray"))
    ax.set_xlabel("Trigger type")
    ax.set_ylabel("Convergence time (s)")
    ax.set_title("Convergence Time by Trigger Type (connect vs handover)")
    ax.grid(True, alpha=.3, axis="y")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "connect_vs_handover.png"), dpi=200)
    plt.close(fig)
    print("  -> connect_vs_handover.png")


def plot_all_links_utilization(link_data, out):
    """Bar chart of GS link (.5) avg throughput per satellite."""
    if not link_data:
        return
    # Only keep GS links (slot .5)
    gs_throughput = defaultdict(list)
    gs_peer = {}
    for entry in link_data:
        lid = entry["link_id"]
        slot = int(lid.split(".")[1])
        if slot != 5:
            continue
        sat = entry["sat_id"]
        gs_throughput[sat].append(entry["tx_rate_mbps"] + entry["rx_rate_mbps"])
        gs_peer[sat] = entry.get("peer_sat", "?")

    if not gs_throughput:
        return

    sat_ids = sorted(gs_throughput.keys())
    avg_vals = [np.mean(gs_throughput[s]) for s in sat_ids]
    labels = [f"sat{s}\n→{gs_peer[s]}" for s in sat_ids]

    mean_val = np.mean(avg_vals)
    median_val = np.median(avg_vals)

    fig, ax = plt.subplots(figsize=(max(10, len(sat_ids) * 0.8), 5))
    bars = ax.bar(range(len(sat_ids)), avg_vals, color="#70AD47", edgecolor="none",
                  alpha=0.85)
    ax.axhline(mean_val, color="red", ls="--", lw=1.2,
               label=f"Mean = {mean_val:.4f} Mbps")
    ax.axhline(median_val, color="orange", ls="--", lw=1.2,
               label=f"Median = {median_val:.4f} Mbps")
    # Annotate bar values
    for i, v in enumerate(avg_vals):
        ax.text(i, v + max(avg_vals) * 0.01, f"{v:.4f}", ha="center",
                fontsize=7, rotation=90)
    ax.set_xticks(range(len(sat_ids)))
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_xlabel("Satellite → Ground Station")
    ax.set_ylabel("Avg Throughput (tx+rx Mbps)")
    ax.set_title(f"Ground Station Link Throughput ({len(sat_ids)} GS links)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=.3, axis="y")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "all_links_utilization.png"), dpi=200)
    plt.close(fig)
    print("  -> all_links_utilization.png")


def plot_sat_total_load(link_data, out):
    """Total load per satellite (sum of avg utilization of all its links)."""
    if not link_data:
        return
    # Compute average utilization per link_id, then sum per sat
    link_utils = defaultdict(list)
    link_sat = {}
    for entry in link_data:
        link_utils[entry["link_id"]].append(entry["utilization_pct"])
        link_sat[entry["link_id"]] = entry["sat_id"]

    sat_load = defaultdict(float)
    for lid, vals in link_utils.items():
        sat_load[link_sat[lid]] += np.mean(vals)

    sat_ids = sorted(sat_load.keys())
    loads = [sat_load[s] for s in sat_ids]

    mean_load = np.mean(loads)
    median_load = np.median(loads)

    fig, ax = plt.subplots(figsize=(16, 6))
    p90 = np.percentile(loads, 90)
    bar_colors = ["#ED7D31" if l >= p90 else "#4472C4" for l in loads]
    ax.bar(range(len(sat_ids)), loads, color=bar_colors, edgecolor="none")
    ax.axhline(mean_load, color="red", ls="--", lw=1.2,
               label=f"Mean = {mean_load:.4f} %")
    ax.axhline(median_load, color="orange", ls="--", lw=1.2,
               label=f"Median = {median_load:.4f} %")
    ax.set_xticks(range(len(sat_ids)))
    ax.set_xticklabels([f"sat{s}" for s in sat_ids], rotation=90, fontsize=6)
    ax.set_xlabel("Satellite")
    ax.set_ylabel("Total Avg Utilization (%) (sum of links)")
    ax.set_title("Total Load per Satellite (sum of avg link utilization)")
    from matplotlib.patches import Patch
    legend_extra = [Patch(facecolor="#ED7D31", label="Top 10%"),
                    Patch(facecolor="#4472C4", label="Others")]
    ax.legend(handles=[ax.lines[0], ax.lines[1]] + legend_extra,
              labels=[f"Mean = {mean_load:.4f} %", f"Median = {median_load:.4f} %",
                      "Top 10%", "Others"],
              fontsize=8, ncol=2)
    ax.grid(True, alpha=.3, axis="y")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "sat_total_load.png"), dpi=200)
    plt.close(fig)
    print("  -> sat_total_load.png")


def plot_top_bottom_links(link_data, out):
    """Top 5 and bottom 5 most/least loaded links over time + stats."""
    if not link_data:
        return
    # Compute average utilization per link_id
    link_utils = defaultdict(list)
    link_ts = defaultdict(lambda: defaultdict(float))  # link_id -> {timestamp -> util}
    for entry in link_data:
        link_utils[entry["link_id"]].append(entry["utilization_pct"])
        link_ts[entry["link_id"]][entry["timestamp"]] = entry["utilization_pct"]

    avg_per_link = {lid: np.mean(vals) for lid, vals in link_utils.items()}
    sorted_by_load = sorted(avg_per_link.items(), key=lambda x: x[1])

    bottom5 = sorted_by_load[:5]
    top5 = sorted_by_load[-5:][::-1]

    # Also compute median
    all_avgs = list(avg_per_link.values())
    global_mean = np.mean(all_avgs)
    global_median = np.median(all_avgs)
    # Find the link closest to median
    median_link = min(avg_per_link.items(), key=lambda x: abs(x[1] - global_median))

    fig, axes = plt.subplots(1, 2, figsize=(18, 7))

    # Left: Top 5 over time
    colors_top = plt.cm.Reds(np.linspace(0.4, 0.9, 5))
    for i, (lid, avg) in enumerate(top5):
        ts_sorted = sorted(link_ts[lid].items())
        if ts_sorted:
            t, v = zip(*ts_sorted)
            axes[0].plot(t, v, color=colors_top[i], lw=1.2, alpha=0.8,
                         label=f"{lid} (avg={avg:.4f}%)")
    # median link
    ts_med = sorted(link_ts[median_link[0]].items())
    if ts_med:
        t, v = zip(*ts_med)
        axes[0].plot(t, v, color="gray", lw=1.5, ls="--",
                     label=f"Median link: {median_link[0]} ({median_link[1]:.4f}%)")
    axes[0].set_xlabel("Simulation time (s)")
    axes[0].set_ylabel("Utilization (%)")
    axes[0].set_title("Top 5 Most Loaded Links Over Time")
    axes[0].legend(fontsize=7)
    axes[0].grid(True, alpha=.3)

    # Right: Bottom 5 over time
    colors_bot = plt.cm.Greens(np.linspace(0.4, 0.9, 5))
    for i, (lid, avg) in enumerate(bottom5):
        ts_sorted = sorted(link_ts[lid].items())
        if ts_sorted:
            t, v = zip(*ts_sorted)
            axes[1].plot(t, v, color=colors_bot[i], lw=1.2, alpha=0.8,
                         label=f"{lid} (avg={avg:.4f}%)")
    if ts_med:
        t, v = zip(*ts_med)
        axes[1].plot(t, v, color="gray", lw=1.5, ls="--",
                     label=f"Median link: {median_link[0]} ({median_link[1]:.4f}%)")
    axes[1].set_xlabel("Simulation time (s)")
    axes[1].set_ylabel("Utilization (%)")
    axes[1].set_title("Bottom 5 Least Loaded Links Over Time")
    axes[1].legend(fontsize=7)
    axes[1].grid(True, alpha=.3)

    fig.suptitle(f"Link Utilization Extremes  |  Global mean={global_mean:.4f}%  "
                 f"median={global_median:.4f}%", fontsize=11, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(os.path.join(out, "top_bottom_links.png"), dpi=200)
    plt.close(fig)
    print("  -> top_bottom_links.png")


# ── Deduplication ─────────────────────────────────────────────────────────────

def deduplicate_events(data):
    """
    Remove duplicate events caused by handover triggering both
    handover_callback and connect_callback.

    For each handover event, a spurious 'connect' event is created at the
    same timestamp for the same gs_id/to_sat. We keep the 'handover' and
    drop the duplicate 'connect'.  Same logic for packet_loss and
    service_interruptions.
    """
    convergence = data.get("convergence_events", [])
    packet_loss = data.get("packet_loss_events", [])
    interruptions = data.get("service_interruptions", [])

    # Build set of (timestamp, gs_id) pairs that have a handover event
    handover_keys = {
        (e["timestamp"], e["gs_id"])
        for e in convergence
        if e.get("trigger") == "handover"
    }

    if not handover_keys:
        return convergence, packet_loss, interruptions

    before = len(convergence)
    convergence = [
        e for e in convergence
        if not (
            e.get("trigger") == "connect"
            and (e["timestamp"], e["gs_id"]) in handover_keys
        )
    ]
    removed = before - len(convergence)

    # Same filter for packet_loss and interruptions (keyed on timestamp + gs_id)
    packet_loss = [
        e for e in packet_loss
        if (e["timestamp"], e["gs_id"]) not in handover_keys
    ]
    interruptions = [
        e for e in interruptions
        if (e["timestamp"], e["gs_id"]) not in handover_keys
    ]

    if removed:
        print(f"  Deduplicated: removed {removed} spurious 'connect' events "
              f"(handover double-count)")

    return convergence, packet_loss, interruptions


def recompute_summary(summary, convergence, packet_loss, interruptions):
    """Recompute summary stats after deduplication."""
    s = dict(summary)
    s["total_handovers"] = len(convergence)

    if convergence:
        times = [e["convergence_time_s"] for e in convergence]
        s["avg_convergence_s"] = round(sum(times) / len(times), 3)
        s["min_convergence_s"] = round(min(times), 3)
        s["max_convergence_s"] = round(max(times), 3)

    if packet_loss:
        losses = [e["loss_percent"] for e in packet_loss]
        s["avg_packet_loss_pct"] = round(sum(losses) / len(losses), 1)

    if interruptions:
        ints = [e["interruption_s"] for e in interruptions]
        s["avg_interruption_s"] = round(sum(ints) / len(ints), 3)
        s["max_interruption_s"] = round(max(ints), 3)

    return s


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    data, tag = load_metrics(path)
    out = make_output_dir(tag)
    print(f"Saving plots to: {out}/\n")

    convergence, packet_loss, interruptions = deduplicate_events(data)
    summary = recompute_summary(
        data.get("summary", {}), convergence, packet_loss, interruptions
    )
    lsp = data.get("lsp_measurements", [])
    link_util = data.get("link_utilization", [])

    # Detect total satellites from summary or LSP data
    total_sats = summary.get("total_satellites", 0)
    if total_sats == 0 and lsp:
        # Infer from highest sat index seen in propagation data
        max_idx = 0
        for m in lsp:
            for node in m.get("propagation", {}):
                if node.startswith("sat"):
                    max_idx = max(max_idx, int(node[3:]))
        total_sats = max_idx + 1

    plot_summary_table(summary, out)
    plot_convergence_timeline(convergence, out)
    plot_convergence_histogram(convergence, out)
    plot_convergence_per_gs(convergence, out)
    plot_handover_frequency(convergence, out)
    plot_adjacency_vs_route(convergence, out)
    plot_connect_vs_handover(convergence, out)
    plot_lsp_propagation(lsp, out)
    plot_lsp_max_all_sats(lsp, total_sats, out)
    plot_all_links_utilization(link_util, out)
    plot_sat_total_load(link_util, out)
    plot_top_bottom_links(link_util, out)

    print(f"\nDone! {len(os.listdir(out))} plots saved to {out}/")


if __name__ == "__main__":
    main()
