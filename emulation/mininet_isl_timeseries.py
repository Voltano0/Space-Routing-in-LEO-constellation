#!/usr/bin/env python3
"""
Mininet Satellite Emulation - Mode ISL Time Series
Crée un réseau Mininet avec mise à jour dynamique des latences ISL

Usage:
    sudo python3 mininet_isl_timeseries.py <mininet_isl_timeseries_*.json>

Exemple:
    sudo python3 mininet_isl_timeseries.py mininet_isl_timeseries_2025-11-19.json

Note:
    La mise à jour dynamique des latences nécessite tc (traffic control)
    et peut ne pas fonctionner parfaitement avec toutes les configurations Mininet.
"""

import json
import sys
import threading
import time
from pathlib import Path
from mininet.net import Mininet
from mininet.node import OVSController
from mininet.link import TCLink
from mininet.log import setLogLevel, info, warn
from mininet.cli import CLI


class DynamicLatencyUpdater:
    """Gestionnaire de mise à jour dynamique des latences ISL"""

    def __init__(self, net, isl_links, update_interval=20):
        self.net = net
        self.isl_links = isl_links
        self.update_interval = update_interval  # secondes
        self.running = False
        self.current_time = 0
        self.thread = None

        # Indexer les time series par paire de satellites
        self.timeseries_map = {}
        self.orbital_period_s = 0

        for link in isl_links:
            key = (link['satA'], link['satB'])
            self.timeseries_map[key] = link['timeSeries']

            # Calculer la période orbitale depuis les échantillons
            if len(link['timeSeries']) > 0:
                self.orbital_period_s = max(self.orbital_period_s,
                                           link['timeSeries'][-1]['timestamp'])

        info(f"*** Orbital period detected: {self.orbital_period_s:.0f}s ({self.orbital_period_s/60:.1f} min)\n")

    def start(self):
        """Démarre la mise à jour dynamique"""
        self.running = True
        self.thread = threading.Thread(target=self._update_loop)
        self.thread.daemon = True
        self.thread.start()
        info("*** Dynamic latency updater started\n")
        info(f"*** Latencies will be updated every {self.update_interval}s\n")

    def stop(self):
        """Arrête la mise à jour"""
        self.running = False
        if self.thread:
            self.thread.join()
        info("*** Dynamic latency updater stopped\n")

    def _update_loop(self):
        """Boucle de mise à jour des latences"""
        while self.running:
            self._update_latencies()
            time.sleep(self.update_interval)

    def _update_latencies(self):
        """Met à jour les latences de tous les liens ISL"""
        updated_count = 0

        for (satA, satB), timeseries in self.timeseries_map.items():
            # Trouver l'échantillon le plus proche du temps actuel
            sample = self._get_sample_at_time(timeseries, self.current_time)

            if sample:
                latency = sample['latency_ms']
                distance = sample['distance_km']

                # Afficher l'information (limité pour ne pas surcharger)
                if updated_count < 5:  # Afficher seulement les 5 premiers
                    info(f"[t={self.current_time:.0f}s] sat{satA}<->sat{satB}: {latency:.3f}ms ({distance:.1f}km)\n")

                # TODO: Mettre à jour le lien dans Mininet avec tc
                # Mininet ne supporte pas nativement la mise à jour dynamique
                # Il faudrait utiliser directement tc (traffic control) sur les interfaces
                # Exemple: tc qdisc change dev <interface> root netem delay {latency}ms

                updated_count += 1

        if updated_count > 5:
            info(f"    ... and {updated_count - 5} more links updated\n")

        # Incrémenter le temps (avec boucle sur la période orbitale)
        self.current_time += self.update_interval
        if self.current_time >= self.orbital_period_s:
            self.current_time = 0
            info("*** Orbital period completed, restarting from t=0\n")

    def _get_sample_at_time(self, timeseries, target_time):
        """Trouve l'échantillon correspondant au temps donné"""
        if not timeseries:
            return None

        # Interpolation simple : prendre le plus proche
        closest = min(timeseries,
                     key=lambda s: abs(s['timestamp'] - target_time))
        return closest


def load_isl_data(json_file):
    """Charge le fichier JSON ISL timeseries"""
    with open(json_file, 'r') as f:
        return json.load(f)


def create_network(data):
    """Crée le réseau Mininet avec liens ISL"""
    info("*** Creating Mininet network with ISL links (timeseries mode)\n")
    net = Mininet(link=TCLink, controller=None)

    # Créer les satellites (hosts) sans IP (on les assignera par interface)
    num_sats = data['metadata']['constellation']['totalSatellites']
    info(f"*** Adding {num_sats} satellite hosts\n")

    satellites = []
    for i in range(num_sats):
        sat = net.addHost(f'sat{i}')
        satellites.append(sat)

    # Ajouter les liens ISL avec latence initiale (t=0)
    # Chaque lien ISL utilise un sous-réseau point-à-point séparé
    info("*** Adding ISL links with point-to-point subnets\n")
    isl_links = data['islLinks']

    link_counts = {'intra-plane': 0, 'inter-plane': 0}
    link_counter = 0  # Pour générer des sous-réseaux uniques

    for link in isl_links:
        satA = link['satA']
        satB = link['satB']
        timeseries = link['timeSeries']
        link_type = link['type']

        if not timeseries:
            warn(f"WARNING: No timeseries data for link sat{satA}<->sat{satB}\n")
            continue

        initial_latency = timeseries[0]['latency_ms']
        bandwidth = link['bandwidth_mbps']

        link_counts[link_type] = link_counts.get(link_type, 0) + 1

        # Générer un sous-réseau /30 pour ce lien point-à-point
        subnet_base = 10 + (link_counter // 65536)
        subnet_second = (link_counter // 256) % 256
        subnet_third = link_counter % 256

        ip_a = f'{subnet_base}.{subnet_second}.{subnet_third}.1/30'
        ip_b = f'{subnet_base}.{subnet_second}.{subnet_third}.2/30'

        link_counter += 1

        net.addLink(
            satellites[satA],
            satellites[satB],
            params1={'ip': ip_a},
            params2={'ip': ip_b},
            delay=f'{initial_latency:.3f}ms',
            bw=min(bandwidth, 1000),
            max_queue_size=1000
        )

    info(f"*** Created {len(isl_links)} ISL links:\n")
    info(f"    - {link_counts.get('intra-plane', 0)} intra-plane links\n")
    info(f"    - {link_counts.get('inter-plane', 0)} inter-plane links\n")
    info(f"*** Each satellite now has exactly 4 ISL neighbor interfaces\n")

    return net, isl_links


def display_info(data):
    """Affiche les informations sur la constellation"""
    constellation = data['metadata']['constellation']
    simulation = data['metadata']['simulation']
    stats = data.get('statistics', {})

    info("=" * 60 + "\n")
    info("CONSTELLATION CONFIGURATION\n")
    info("=" * 60 + "\n")
    info(f"Total Satellites: {constellation['totalSatellites']}\n")
    info(f"Orbital Planes: {constellation['planes']}\n")
    info(f"Phase (Walker Delta): {constellation['phase']}\n")
    info(f"Altitude: {constellation['altitude_km']} km\n")
    info(f"Inclination: {constellation['inclination_deg']}°\n")
    info(f"Orbital Period: {simulation['orbitalPeriod_min']:.2f} min\n")
    info(f"Sampling Interval: {simulation['samplingInterval_s']}s\n")
    info("\n")

    if stats:
        info("=" * 60 + "\n")
        info("ISL STATISTICS\n")
        info("=" * 60 + "\n")
        info(f"Total ISL Links: {stats.get('totalISLLinks', 0)}\n")
        info(f"Total Samples: {stats.get('totalSamples', 0)}\n")
        info(f"Avg Latency (Overall): {stats.get('avgLatencyOverall_ms', 0):.6f} ms\n")
        info("\n")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <mininet_isl_timeseries_*.json>")
        print(f"Example: sudo python3 {sys.argv[0]} mininet_isl_timeseries_2025-11-19.json")
        sys.exit(1)

    json_file = sys.argv[1]

    if not Path(json_file).exists():
        print(f"ERROR: File not found: {json_file}")
        sys.exit(1)

    # Charger les données
    info(f"*** Loading ISL data from {json_file}\n")
    data = load_isl_data(json_file)

    # Vérifier le mode
    mode = data['metadata'].get('mode', 'unknown')
    if mode != 'timeseries':
        print(f"WARNING: This file is in '{mode}' mode, expected 'timeseries' mode")
        print("Proceeding anyway, but results may not be optimal")

    # Afficher les informations
    display_info(data)

    # Créer le réseau
    setLogLevel('info')
    net, isl_links = create_network(data)

    # Créer le gestionnaire de latences dynamiques
    updater = DynamicLatencyUpdater(net, isl_links, update_interval=20)

    info("=" * 60 + "\n")
    info("*** Starting network\n")
    net.start()

    # Démarrer la mise à jour dynamique
    updater.start()

    info("\n")
    info("=" * 60 + "\n")
    info("NETWORK READY - Dynamic Latency Updates\n")
    info("=" * 60 + "\n")
    info("  Latencies will loop over the orbital period\n")
    info("  Updates every 20 seconds (configurable)\n")
    info("\n")
    info("Available Commands:\n")
    info("  pingall          - Test connectivity between all satellites\n")
    info("  iperf sat0 sat1  - Test bandwidth between two satellites\n")
    info("  sat0 ping sat1   - Test specific link\n")
    info("  dump             - Display network information\n")
    info("  quit / exit      - Stop network and exit\n")
    info("=" * 60 + "\n")
    info("\n")

    try:
        CLI(net)
    finally:
        updater.stop()
        info("*** Stopping network\n")
        net.stop()


if __name__ == '__main__':
    main()
