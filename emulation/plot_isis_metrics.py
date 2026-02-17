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
        axes[1].set_title("Max LSP Propagation per Satellite")
        axes[1].grid(True, alpha=.3, axis="y")

    fig.tight_layout()
    fig.savefig(os.path.join(out, "lsp_propagation.png"), dpi=200)
    plt.close(fig)
    print("  -> lsp_propagation.png")


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


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    data, tag = load_metrics(path)
    out = make_output_dir(tag)
    print(f"Saving plots to: {out}/\n")

    summary = data.get("summary", {})
    convergence = data.get("convergence_events", [])
    lsp = data.get("lsp_measurements", [])

    plot_summary_table(summary, out)
    plot_convergence_timeline(convergence, out)
    plot_convergence_histogram(convergence, out)
    plot_convergence_per_gs(convergence, out)
    plot_handover_frequency(convergence, out)
    plot_adjacency_vs_route(convergence, out)
    plot_connect_vs_handover(convergence, out)
    plot_lsp_propagation(lsp, out)

    print(f"\nDone! {len(os.listdir(out))} plots saved to {out}/")


if __name__ == "__main__":
    main()
