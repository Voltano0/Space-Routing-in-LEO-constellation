#!/usr/bin/env python3
"""
Mininet Satellite Emulation - Mode ISL + Ground Stations Time Series
Crée un réseau Mininet avec satellites et ground stations,
mise à jour dynamique des latences ISL et gestion des handovers GS

Usage:
    sudo python3 mininet_gs_timeseries.py <mininet_isl_gs_timeseries_*.json>

Exemple:
    sudo python3 mininet_gs_timeseries.py mininet_isl_gs_timeseries_2025-11-19.json

Format JSON v4.0:
    - metadata.hasGroundStations: true/false
    - topology.satellites: liste des satellites
    - topology.groundStations: liste des GS (optionnel)
    - islLinks: liens ISL avec timeSeries
    - gsLinks.events: événements connect/handover/disconnect
    - gsLinks.timeline: échantillons de latence GS
"""

import json
import sys
import threading
import time
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.log import setLogLevel, info, warn, error
from mininet.cli import CLI

from mininet_common import (
    load_json_data,
    get_metadata,
    has_ground_stations,
    get_satellites,
    get_ground_stations,
    get_isl_links,
    get_gs_links,
    display_constellation_info,
    update_link_latency_tc,
    find_interface_for_link,
    LinkLatencyCache
)


class DynamicGSLinkManager:
    """
    Gestionnaire des liens dynamiques Ground Station <-> Satellite
    Gère les connexions, déconnexions et handovers
    """

    def __init__(self, net, gs_hosts, sat_hosts):
        self.net = net
        self.gs_hosts = gs_hosts        # {gs_id: host}
        self.sat_hosts = sat_hosts      # {sat_id: host}
        self.active_links = {}          # {gs_id: {'sat_id': int, 'link': Link, 'intf_gs': str, 'intf_sat': str}}
        self.link_counter = 50000       # Compteur pour les sous-réseaux GS (éviter collision avec ISL)

    def connect(self, gs_id, sat_id, latency_ms):
        """
        Créer un lien entre une GS et un satellite

        Args:
            gs_id: ID de la ground station (ex: 'gs0')
            sat_id: Index du satellite (ex: 42)
            latency_ms: Latence initiale en ms
        """
        if gs_id in self.active_links:
            warn(f"GS {gs_id} already connected, disconnecting first\n")
            self.disconnect(gs_id)

        gs_host = self.gs_hosts.get(gs_id)
        sat_host = self.sat_hosts.get(sat_id)

        if not gs_host or not sat_host:
            error(f"Cannot find hosts for link {gs_id} <-> sat{sat_id}\n")
            return False

        # Générer les IPs pour ce lien
        self.link_counter += 1
        subnet_base = 192
        subnet_second = 168 + (self.link_counter // 256) % 87  # Reste dans 192.168.x.x
        subnet_third = self.link_counter % 256

        ip_gs = f'{subnet_base}.{subnet_second}.{subnet_third}.1/30'
        ip_sat = f'{subnet_base}.{subnet_second}.{subnet_third}.2/30'

        try:
            # Créer le lien avec latence initiale
            link = self.net.addLink(
                gs_host,
                sat_host,
                params1={'ip': ip_gs},
                params2={'ip': ip_sat},
                delay=f'{latency_ms:.3f}ms',
                bw=100,  # 100 Mbps pour les liens GS
                max_queue_size=500
            )

            # Récupérer les noms des interfaces
            intf_gs = link.intf1.name
            intf_sat = link.intf2.name

            # Activer les interfaces
            gs_host.cmd(f'ifconfig {intf_gs} up')
            sat_host.cmd(f'ifconfig {intf_sat} up')

            # Stocker les informations du lien
            self.active_links[gs_id] = {
                'sat_id': sat_id,
                'link': link,
                'intf_gs': intf_gs,
                'intf_sat': intf_sat,
                'ip_gs': ip_gs,
                'ip_sat': ip_sat
            }

            info(f"[GS CONNECT] {gs_id} <-> sat{sat_id} (latency: {latency_ms:.3f}ms)\n")
            return True

        except Exception as e:
            error(f"Failed to create link {gs_id} <-> sat{sat_id}: {e}\n")
            return False

    def disconnect(self, gs_id):
        """
        Déconnecter une GS de son satellite actuel

        Args:
            gs_id: ID de la ground station
        """
        if gs_id not in self.active_links:
            warn(f"GS {gs_id} not connected\n")
            return False

        link_info = self.active_links[gs_id]
        sat_id = link_info['sat_id']

        try:
            # Supprimer le lien
            link = link_info['link']
            self.net.removeLink(link)

            del self.active_links[gs_id]

            info(f"[GS DISCONNECT] {gs_id} </> sat{sat_id}\n")
            return True

        except Exception as e:
            error(f"Failed to disconnect {gs_id}: {e}\n")
            return False

    def handover(self, gs_id, from_sat_id, to_sat_id, latency_ms):
        """
        Effectuer un handover atomique: déconnexion ancien sat + connexion nouveau sat

        Args:
            gs_id: ID de la ground station
            from_sat_id: Index de l'ancien satellite
            to_sat_id: Index du nouveau satellite
            latency_ms: Latence vers le nouveau satellite
        """
        info(f"[GS HANDOVER] {gs_id}: sat{from_sat_id} -> sat{to_sat_id}\n")

        # Déconnexion
        self.disconnect(gs_id)

        # Connexion au nouveau satellite
        return self.connect(gs_id, to_sat_id, latency_ms)

    def update_latency(self, gs_id, latency_ms):
        """
        Mettre à jour la latence d'un lien GS actif

        Args:
            gs_id: ID de la ground station
            latency_ms: Nouvelle latence
        """
        if gs_id not in self.active_links:
            return False

        link_info = self.active_links[gs_id]
        intf_gs = link_info['intf_gs']
        intf_sat = link_info['intf_sat']

        # Mettre à jour les deux directions
        success_gs = update_link_latency_tc(intf_gs, latency_ms)
        success_sat = update_link_latency_tc(intf_sat, latency_ms)

        return success_gs and success_sat

    def get_active_connections(self):
        """Retourne les connexions actives"""
        return {gs_id: info['sat_id'] for gs_id, info in self.active_links.items()}


class DynamicLatencyUpdater:
    """
    Gestionnaire de mise à jour dynamique des latences ISL et GS
    Boucle sur la période orbitale et applique les mises à jour tc
    """

    def __init__(self, net, isl_links, gs_links_data, gs_manager, update_interval=20):
        self.net = net
        self.isl_links = isl_links
        self.gs_links_data = gs_links_data
        self.gs_manager = gs_manager
        self.update_interval = update_interval
        self.running = False
        self.current_time = 0
        self.thread = None
        self.latency_cache = LinkLatencyCache()

        # Indexer les time series ISL
        self.isl_timeseries_map = {}
        self.orbital_period_s = 0

        for link in isl_links:
            key = (link['satA'], link['satB'])
            self.isl_timeseries_map[key] = link['timeSeries']

            if link['timeSeries']:
                self.orbital_period_s = max(
                    self.orbital_period_s,
                    link['timeSeries'][-1]['timestamp']
                )

        # Indexer les événements GS par temps
        self.gs_events = gs_links_data.get('events', [])
        self.gs_events_sorted = sorted(self.gs_events, key=lambda e: e['t'])

        # Indexer les timelines GS
        self.gs_timeline_map = {}  # {gs_id: [{satId, samples}]}
        for entry in gs_links_data.get('timeline', []):
            gs_id = entry['gsId']
            if gs_id not in self.gs_timeline_map:
                self.gs_timeline_map[gs_id] = []
            self.gs_timeline_map[gs_id].append(entry)

        info(f"*** Orbital period detected: {self.orbital_period_s:.0f}s ({self.orbital_period_s/60:.1f} min)\n")
        info(f"*** GS Events loaded: {len(self.gs_events)}\n")

    def start(self):
        """Démarre la mise à jour dynamique"""
        self.running = True
        self.thread = threading.Thread(target=self._update_loop)
        self.thread.daemon = True
        self.thread.start()
        info("*** Dynamic latency updater started\n")
        info(f"*** Updates every {self.update_interval}s\n")
        info("*** tc netem updates ENABLED\n")

    def stop(self):
        """Arrête la mise à jour"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        info("*** Dynamic latency updater stopped\n")

    def _update_loop(self):
        """Boucle principale de mise à jour"""
        while self.running:
            self._process_gs_events()
            self._update_isl_latencies()
            self._update_gs_latencies()

            time.sleep(self.update_interval)

            # Incrémenter le temps
            self.current_time += self.update_interval
            if self.current_time >= self.orbital_period_s:
                self.current_time = 0
                info("*** Orbital period completed, restarting from t=0\n")
                self.latency_cache.clear()

    def _process_gs_events(self):
        """Traite les événements GS pour le temps courant"""
        window_start = self.current_time
        window_end = self.current_time + self.update_interval

        for event in self.gs_events_sorted:
            event_time = event['t']

            # Événements dans la fenêtre de temps actuelle
            if window_start <= event_time < window_end:
                action = event['action']
                gs_id = event['gsId']

                if action == 'connect':
                    self.gs_manager.connect(
                        gs_id,
                        event['satId'],
                        event.get('latency_ms', 5.0)
                    )
                elif action == 'disconnect':
                    self.gs_manager.disconnect(gs_id)
                elif action == 'handover':
                    self.gs_manager.handover(
                        gs_id,
                        event['fromSatId'],
                        event['toSatId'],
                        event.get('latency_ms', 5.0)
                    )

    def _update_isl_latencies(self):
        """Met à jour les latences ISL via tc netem"""
        updated_count = 0
        skipped_count = 0

        for (satA, satB), timeseries in self.isl_timeseries_map.items():
            sample = self._get_sample_at_time(timeseries, self.current_time)

            if sample:
                latency = sample['latency_ms']

                # Trouver les interfaces
                sat_a_host = self.net.get(f'sat{satA}')
                sat_b_host = self.net.get(f'sat{satB}')

                if sat_a_host and sat_b_host:
                    intf_a = find_interface_for_link(sat_a_host, sat_b_host)
                    intf_b = find_interface_for_link(sat_b_host, sat_a_host)

                    if intf_a and intf_b:
                        # Vérifier le cache pour éviter les mises à jour inutiles
                        if self.latency_cache.should_update(intf_a, latency):
                            update_link_latency_tc(intf_a, latency)
                            update_link_latency_tc(intf_b, latency)
                            self.latency_cache.update(intf_a, latency)
                            self.latency_cache.update(intf_b, latency)
                            updated_count += 1
                        else:
                            skipped_count += 1

        if updated_count > 0 or skipped_count > 0:
            info(f"[t={self.current_time:.0f}s] ISL: {updated_count} updated, {skipped_count} unchanged\n")

    def _update_gs_latencies(self):
        """Met à jour les latences GS via tc netem"""
        active_connections = self.gs_manager.get_active_connections()

        for gs_id, sat_id in active_connections.items():
            # Trouver le timeline actif pour cette connexion
            if gs_id in self.gs_timeline_map:
                for entry in self.gs_timeline_map[gs_id]:
                    if entry['satId'] == sat_id:
                        start_time = entry.get('startTime', 0)
                        end_time = entry.get('endTime')

                        # Vérifier si cette entrée est active
                        if start_time <= self.current_time:
                            if end_time is None or self.current_time < end_time:
                                sample = self._get_sample_at_time(
                                    entry['samples'],
                                    self.current_time,
                                    time_key='t'
                                )
                                if sample:
                                    self.gs_manager.update_latency(
                                        gs_id,
                                        sample['latency_ms']
                                    )
                                break

    def _get_sample_at_time(self, timeseries, target_time, time_key='timestamp'):
        """Trouve l'échantillon le plus proche du temps donné"""
        if not timeseries:
            return None

        closest = min(
            timeseries,
            key=lambda s: abs(s.get(time_key, s.get('t', 0)) - target_time)
        )
        return closest


def create_network(data):
    """
    Crée le réseau Mininet avec satellites et ground stations

    Args:
        data: Données JSON parsées

    Returns:
        tuple: (net, sat_hosts, gs_hosts, isl_links, gs_manager)
    """
    info("*** Creating Mininet network with ISL + GS support\n")
    net = Mininet(link=TCLink, controller=None)

    # Créer les satellites
    satellites = get_satellites(data)
    num_sats = len(satellites)
    info(f"*** Adding {num_sats} satellite hosts\n")

    sat_hosts = {}
    for sat in satellites:
        sat_id = sat['id']
        host = net.addHost(f'sat{sat_id}')
        sat_hosts[sat_id] = host

    # Créer les ground stations si présentes
    gs_hosts = {}
    ground_stations = get_ground_stations(data)

    if ground_stations:
        info(f"*** Adding {len(ground_stations)} ground station hosts\n")
        for gs in ground_stations:
            gs_id = gs['id']
            host = net.addHost(gs_id)
            gs_hosts[gs_id] = host

    # Ajouter les liens ISL
    isl_links = get_isl_links(data)
    info(f"*** Adding {len(isl_links)} ISL links\n")

    link_counts = {'intra-plane': 0, 'inter-plane': 0}
    link_counter = 0

    for link in isl_links:
        satA = link['satA']
        satB = link['satB']
        timeseries = link.get('timeSeries', [])
        link_type = link.get('type', 'unknown')

        if not timeseries:
            warn(f"No timeseries for link sat{satA}<->sat{satB}\n")
            continue

        initial_latency = timeseries[0]['latency_ms']
        bandwidth = link.get('bandwidth_mbps', 1000)

        link_counts[link_type] = link_counts.get(link_type, 0) + 1

        # Générer les IPs
        subnet_base = 10 + (link_counter // 65536)
        subnet_second = (link_counter // 256) % 256
        subnet_third = link_counter % 256

        ip_a = f'{subnet_base}.{subnet_second}.{subnet_third}.1/30'
        ip_b = f'{subnet_base}.{subnet_second}.{subnet_third}.2/30'
        link_counter += 1

        net.addLink(
            sat_hosts[satA],
            sat_hosts[satB],
            params1={'ip': ip_a},
            params2={'ip': ip_b},
            delay=f'{initial_latency:.3f}ms',
            bw=min(bandwidth, 1000),
            max_queue_size=1000
        )

    info(f"*** ISL links created:\n")
    info(f"    - {link_counts.get('intra-plane', 0)} intra-plane\n")
    info(f"    - {link_counts.get('inter-plane', 0)} inter-plane\n")

    # Créer le gestionnaire de liens GS (les liens seront créés dynamiquement)
    gs_manager = DynamicGSLinkManager(net, gs_hosts, sat_hosts)

    return net, sat_hosts, gs_hosts, isl_links, gs_manager


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <mininet_isl_gs_timeseries_*.json>")
        print(f"Example: sudo python3 {sys.argv[0]} mininet_isl_gs_timeseries_2025-11-19.json")
        sys.exit(1)

    json_file = sys.argv[1]

    # Charger les données
    try:
        data = load_json_data(json_file)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # Vérifier le format
    metadata = get_metadata(data)
    version = metadata.get('version', 'unknown')
    mode = metadata.get('mode', 'unknown')

    if version < '4.0' and has_ground_stations(data):
        warn(f"File version {version} may not fully support GS features\n")

    if mode != 'timeseries':
        warn(f"File is in '{mode}' mode, expected 'timeseries'\n")

    # Afficher les informations
    setLogLevel('info')
    info(f"*** Loading data from {json_file}\n")
    display_constellation_info(data)

    # Créer le réseau
    net, sat_hosts, gs_hosts, isl_links, gs_manager = create_network(data)

    # Créer le gestionnaire de latences dynamiques
    gs_links_data = get_gs_links(data) if has_ground_stations(data) else {}
    updater = DynamicLatencyUpdater(
        net, isl_links, gs_links_data, gs_manager,
        update_interval=20
    )

    info("=" * 60 + "\n")
    info("*** Starting network\n")
    net.start()

    # Démarrer la mise à jour dynamique
    updater.start()

    info("\n")
    info("=" * 60 + "\n")
    info("NETWORK READY - ISL + Ground Stations\n")
    info("=" * 60 + "\n")

    if gs_hosts:
        info(f"Ground Stations: {list(gs_hosts.keys())}\n")
        info("GS links will be created/removed dynamically based on events\n")

    info("\n")
    info("Available Commands:\n")
    info("  pingall          - Test connectivity between all nodes\n")
    info("  sat0 ping sat1   - Test specific satellite link\n")
    info("  gs0 ping sat42   - Test GS to satellite (if connected)\n")
    info("  iperf sat0 sat1  - Test bandwidth between satellites\n")
    info("  dump             - Display network information\n")
    info("  nodes            - List all nodes\n")
    info("  links            - List all links\n")
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
