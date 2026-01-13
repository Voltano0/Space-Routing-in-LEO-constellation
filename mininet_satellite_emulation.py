#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from mininet.net import Mininet
from mininet.node import OVSController
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.cli import CLI

def load_json(json_file):
    """Charge le fichier JSON de contact plan"""
    with open(json_file, 'r') as f:
        return json.load(f)


def create_network(data):
    info("*** Creating Mininet network\n")
    net = Mininet(link=TCLink, controller=None)

    # Créer les satellites (hosts)
    num_satellites = data['metadata']['constellation']['totalSatellites']
    info(f"*** Adding {num_satellites} satellite hosts\n")

    satellites = []
    for i in range(num_satellites):
        sat = net.addHost(f'sat{i}', ip=f'10.0.0.{i+1}/24')
        satellites.append(sat)

    # Ajouter les liens initiaux (on prend juste les premiers contacts actifs)
    info("*** Adding initial links based on contact plan\n")
    contacts = data['contactPlan']

    # Regrouper les contacts par paire de satellites
    link_map = {}
    for contact in contacts:
        satA = contact['satA']
        satB = contact['satB']
        key = tuple(sorted([satA, satB]))

        if key not in link_map:
            # Premier contact pour cette paire
            latency = contact['avgLatency_ms']
            bandwidth = contact['bandwidth_mbps']

            info(f"  sat{satA} <-> sat{satB} (latency={latency:.2f}ms, bw={bandwidth}Mbps)\n")
            # Limiter la bande passante pour éviter les warnings HTB quantum
            # ISL satellites typiquement 10-100 Mbps
            bw_limited = min(bandwidth, 10)
            net.addLink(
                satellites[satA],
                satellites[satB],
                delay=f'{latency}ms',
                bw=bw_limited,
                max_queue_size=1000
            )
            link_map[key] = True

    info(f"*** Created {len(link_map)} unique satellite links\n")

    return net


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <contact_plan.json>")
        print(f"Example: sudo python3 {sys.argv[0]} mininet_2025-11-19.json")
        sys.exit(1)

    json_file = sys.argv[1]

    # Vérifier que le fichier existe
    if not Path(json_file).exists():
        print(f"ERROR: File not found: {json_file}")
        sys.exit(1)

    # Charger les données
    info(f"*** Loading contact plan from {json_file}\n")
    data = load_json(json_file)

    # Afficher les infos de constellation
    metadata = data['metadata']
    constellation = metadata['constellation']
    info(f"*** Constellation: {constellation['totalSatellites']} satellites, ")
    info(f"{constellation['planes']} planes, {constellation['altitude_km']}km altitude\n")

    # Créer le réseau
    setLogLevel('info')
    net = create_network(data)

    info("*** Starting network\n")
    net.start()
    CLI(net)
    info("*** Stopping network\n")
    net.stop()


if __name__ == '__main__':
    main()
