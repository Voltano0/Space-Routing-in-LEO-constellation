#!/usr/bin/env python3
"""
Mininet Satellite Emulation - Mode ISL Average
Crée un réseau Mininet avec liens ISL à latence moyenne statique

Usage:
    sudo python3 mininet_isl_average.py <mininet_isl_average_*.json>

Exemple:
    sudo python3 mininet_isl_average.py mininet_isl_average_2025-11-19.json
"""

import json
import sys
from pathlib import Path
from mininet.net import Mininet
from mininet.node import OVSController
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.cli import CLI


def load_isl_data(json_file):
    """Charge le fichier JSON ISL average"""
    with open(json_file, 'r') as f:
        return json.load(f)


def create_network(data):
    """Crée le réseau Mininet avec liens ISL à latence moyenne"""
    info("*** Creating Mininet network with ISL links (average mode)\n")
    net = Mininet(link=TCLink, controller=None)

    # Créer les satellites (hosts) sans IP (on les assignera par interface)
    num_sats = data['metadata']['constellation']['totalSatellites']
    info(f"*** Adding {num_sats} satellite hosts\n")

    satellites = []
    for i in range(num_sats):
        sat = net.addHost(f'sat{i}')
        satellites.append(sat)

    # Ajouter les liens ISL avec latence moyenne
    # Chaque lien ISL utilise un sous-réseau point-à-point séparé
    info("*** Adding ISL links with point-to-point subnets\n")
    isl_links = data['islLinks']

    link_counts = {'intra-plane': 0, 'inter-plane': 0}
    link_counter = 0  # Pour générer des sous-réseaux uniques

    for link in isl_links:
        satA = link['satA']
        satB = link['satB']
        avg_latency = link['avgLatency_ms']
        bandwidth = link['bandwidth_mbps']
        link_type = link['type']

        link_counts[link_type] = link_counts.get(link_type, 0) + 1

        # Générer un sous-réseau /30 pour ce lien point-à-point
        # Format: 10.X.Y.0/30 où X.Y est dérivé du link_counter
        # Chaque /30 donne 2 IPs utilisables (.1 et .2)
        subnet_base = 10 + (link_counter // 65536)
        subnet_second = (link_counter // 256) % 256
        subnet_third = link_counter % 256

        ip_a = f'{subnet_base}.{subnet_second}.{subnet_third}.1/30'
        ip_b = f'{subnet_base}.{subnet_second}.{subnet_third}.2/30'

        link_counter += 1

        # Créer le lien avec IPs point-à-point
        net.addLink(
            satellites[satA],
            satellites[satB],
            params1={'ip': ip_a},
            params2={'ip': ip_b},
            delay=f'{avg_latency:.3f}ms',
            bw=min(bandwidth, 1000),
            max_queue_size=1000
        )

    info(f"*** Created {len(isl_links)} ISL links:\n")
    info(f"    - {link_counts.get('intra-plane', 0)} intra-plane links\n")
    info(f"    - {link_counts.get('inter-plane', 0)} inter-plane links\n")
    info(f"*** Each satellite now has exactly 4 ISL neighbor interfaces\n")

    return net


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
    info("\n")

    if stats:
        info("=" * 60 + "\n")
        info("ISL STATISTICS\n")
        info("=" * 60 + "\n")
        info(f"Total ISL Links: {stats.get('totalISLLinks', 0)}\n")
        info(f"Intra-plane Links: {stats.get('intraPlaneLinks', 0)}\n")
        info(f"Inter-plane Links: {stats.get('interPlaneLinks', 0)}\n")
        info(f"Avg Latency (Intra-plane): {stats.get('avgLatencyIntraPlane_ms', 0):.6f} ms\n")
        info(f"Avg Latency (Inter-plane): {stats.get('avgLatencyInterPlane_ms', 0):.6f} ms\n")
        info(f"Avg Latency (Overall): {stats.get('avgLatencyOverall_ms', 0):.6f} ms\n")
        info("\n")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <mininet_isl_average_*.json>")
        print(f"Example: sudo python3 {sys.argv[0]} mininet_isl_average_2025-11-19.json")
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
    if mode != 'average':
        print(f"WARNING: This file is in '{mode}' mode, expected 'average' mode")
        print("Proceeding anyway, but results may not be optimal")

    # Afficher les informations
    display_info(data)

    # Créer et démarrer le réseau
    setLogLevel('info')
    net = create_network(data)

    info("=" * 60 + "\n")
    info("*** Starting network\n")
    net.start()

    info("\n")
    info("=" * 60 + "\n")
    info("NETWORK READY - Available Commands\n")
    info("=" * 60 + "\n")
    info("  pingall          - Test connectivity between all satellites\n")
    info("  iperf sat0 sat1  - Test bandwidth between two satellites\n")
    info("  sat0 ping sat1   - Test specific link\n")
    info("  dump             - Display network information\n")
    info("  net              - Show network topology\n")
    info("  links            - Show all links\n")
    info("  quit / exit      - Stop network and exit\n")
    info("=" * 60 + "\n")
    info("\n")

    CLI(net)

    info("*** Stopping network\n")
    net.stop()


if __name__ == '__main__':
    main()
