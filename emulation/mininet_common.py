#!/usr/bin/env python3
"""
Mininet Common Utilities
Fonctions partagées pour les scripts Mininet d'émulation satellite

Ce module fournit:
- Chargement et validation des fichiers JSON
- Création des hosts (satellites et ground stations)
- Gestion des liens avec tc netem
- Utilitaires d'affichage
"""

import json
import subprocess
from pathlib import Path
from mininet.log import info, warn, error


def load_json_data(json_file):
    """
    Charge et valide un fichier JSON d'export Mininet

    Args:
        json_file: Chemin vers le fichier JSON

    Returns:
        dict: Données JSON parsées

    Raises:
        FileNotFoundError: Si le fichier n'existe pas
        json.JSONDecodeError: Si le JSON est invalide
        ValueError: Si le format est incorrect
    """
    path = Path(json_file)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {json_file}")

    with open(json_file, 'r') as f:
        data = json.load(f)

    # Validation basique
    if 'metadata' not in data:
        raise ValueError("Invalid JSON format: missing 'metadata' section")

    if 'topology' not in data:
        raise ValueError("Invalid JSON format: missing 'topology' section")

    return data


def get_metadata(data):
    """Extrait et retourne les métadonnées du fichier"""
    return data.get('metadata', {})


def has_ground_stations(data):
    """Vérifie si le fichier contient des ground stations"""
    metadata = get_metadata(data)
    return metadata.get('hasGroundStations', False)


def get_satellites(data):
    """Retourne la liste des satellites de la topologie"""
    return data.get('topology', {}).get('satellites', [])


def get_ground_stations(data):
    """Retourne la liste des ground stations de la topologie"""
    return data.get('topology', {}).get('groundStations', [])


def get_isl_links(data):
    """Retourne la liste des liens ISL"""
    return data.get('islLinks', [])


def get_gs_links(data):
    """Retourne les liens GS (events et timeline)"""
    return data.get('gsLinks', {})


def display_constellation_info(data):
    """Affiche les informations sur la constellation"""
    metadata = get_metadata(data)
    constellation = metadata.get('constellation', {})
    simulation = metadata.get('simulation', {})
    stats = data.get('statistics', {})

    info("=" * 60 + "\n")
    info("CONSTELLATION CONFIGURATION\n")
    info("=" * 60 + "\n")
    info(f"Format Version: {metadata.get('version', 'unknown')}\n")
    info(f"Mode: {metadata.get('mode', 'unknown')}\n")
    info(f"Has Ground Stations: {metadata.get('hasGroundStations', False)}\n")
    info("\n")
    info(f"Total Satellites: {constellation.get('totalSatellites', 0)}\n")
    info(f"Orbital Planes: {constellation.get('planes', 0)}\n")
    info(f"Phase (Walker Delta): {constellation.get('phase', 0)}\n")
    info(f"Altitude: {constellation.get('altitude_km', 0)} km\n")
    info(f"Inclination: {constellation.get('inclination_deg', 0)} deg\n")
    info(f"Orbital Period: {simulation.get('orbitalPeriod_min', 0):.2f} min\n")
    info(f"Sampling Interval: {simulation.get('samplingInterval_s', 20)}s\n")
    info("\n")

    if stats:
        info("=" * 60 + "\n")
        info("ISL STATISTICS\n")
        info("=" * 60 + "\n")
        info(f"Total ISL Links: {stats.get('totalISLLinks', 0)}\n")
        info(f"  - Intra-plane: {stats.get('intraPlaneLinks', 0)}\n")
        info(f"  - Inter-plane: {stats.get('interPlaneLinks', 0)}\n")
        info(f"Total Samples: {stats.get('totalSamples', 0)}\n")
        info(f"Avg Latency (Overall): {stats.get('avgLatencyOverall_ms', 0):.6f} ms\n")
        info("\n")

    gs_stats = data.get('gsStatistics', {})
    if gs_stats:
        info("=" * 60 + "\n")
        info("GROUND STATION STATISTICS\n")
        info("=" * 60 + "\n")
        info(f"Total Ground Stations: {gs_stats.get('totalGroundStations', 0)}\n")
        info(f"Total Events: {gs_stats.get('totalEvents', 0)}\n")
        info(f"  - Connect: {gs_stats.get('connectEvents', 0)}\n")
        info(f"  - Handover: {gs_stats.get('handoverEvents', 0)}\n")
        info(f"  - Disconnect: {gs_stats.get('disconnectEvents', 0)}\n")
        info(f"Total Samples: {gs_stats.get('totalSamples', 0)}\n")
        info(f"Avg Latency: {gs_stats.get('avgLatency_ms', 0):.6f} ms\n")
        info("\n")


def update_link_latency_tc(interface, latency_ms, host=None):
    """
    Met à jour la latence d'une interface réseau avec tc netem

    Args:
        interface: Nom de l'interface (ex: 'sat0-eth0')
        latency_ms: Latence en millisecondes
        host: Host Mininet (si fourni, exécute via le namespace du host)

    Returns:
        bool: True si la mise à jour a réussi, False sinon
    """
    try:
        if host:
            # Exécuter via le namespace du host Mininet
            # Vérifier si une qdisc netem existe
            result = host.cmd(f'tc qdisc show dev {interface}')

            if 'netem' in result:
                cmd = f'tc qdisc change dev {interface} root netem delay {latency_ms:.3f}ms'
            else:
                # Supprimer l'existante et créer une nouvelle
                host.cmd(f'tc qdisc del dev {interface} root 2>/dev/null')
                cmd = f'tc qdisc add dev {interface} root netem delay {latency_ms:.3f}ms'

            result = host.cmd(cmd)
            if 'Error' in result or 'error' in result:
                # Silently ignore - interface may have been removed
                return False
            return True

        else:
            # Fallback: exécuter directement (ancien comportement)
            result = subprocess.run(
                ['tc', 'qdisc', 'show', 'dev', interface],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if 'netem' in result.stdout:
                cmd = ['tc', 'qdisc', 'change', 'dev', interface,
                       'root', 'netem', 'delay', f'{latency_ms:.3f}ms']
            else:
                subprocess.run(
                    ['tc', 'qdisc', 'del', 'dev', interface, 'root'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                cmd = ['tc', 'qdisc', 'add', 'dev', interface,
                       'root', 'netem', 'delay', f'{latency_ms:.3f}ms']

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if result.returncode != 0:
                # Silently ignore - don't spam logs
                return False

            return True

    except Exception as e:
        # Silently ignore errors
        return False


def get_host_interfaces(host):
    """
    Récupère la liste des interfaces d'un host Mininet

    Args:
        host: Host Mininet

    Returns:
        list: Liste des noms d'interfaces
    """
    interfaces = []
    for intf in host.intfList():
        if intf.name != 'lo':  # Ignorer loopback
            interfaces.append(intf.name)
    return interfaces


def generate_subnet(link_counter, base=10):
    """
    Génère un sous-réseau /30 unique pour un lien point-à-point

    Args:
        link_counter: Compteur de liens (pour générer des sous-réseaux uniques)
        base: Octet de base pour l'adresse (default: 10)

    Returns:
        tuple: (ip_a, ip_b) avec le masque /30
    """
    # Calculer les octets du sous-réseau
    subnet_base = base + (link_counter // 65536)
    subnet_second = (link_counter // 256) % 256
    subnet_third = link_counter % 256

    ip_a = f'{subnet_base}.{subnet_second}.{subnet_third}.1/30'
    ip_b = f'{subnet_base}.{subnet_second}.{subnet_third}.2/30'

    return ip_a, ip_b


def generate_gs_ip(gs_index):
    """
    Génère une IP pour une ground station

    Les GS utilisent le préfixe 192.168.X.Y pour les différencier des satellites

    Args:
        gs_index: Index de la ground station

    Returns:
        str: Adresse IP avec masque
    """
    # 192.168.100.X pour les GS
    return f'192.168.100.{gs_index + 1}/24'


def find_interface_for_link(host, peer_host):
    """
    Trouve l'interface d'un host connectée à un autre host

    Args:
        host: Host source
        peer_host: Host destination

    Returns:
        str: Nom de l'interface ou None si non trouvée
    """
    for intf in host.intfList():
        if intf.link:
            # Vérifier si le lien connecte au peer
            link = intf.link
            if link.intf1.node == peer_host or link.intf2.node == peer_host:
                return intf.name
    return None


class LinkLatencyCache:
    """Cache pour les latences des liens, évite les appels tc répétés"""

    def __init__(self):
        self.cache = {}  # {interface: last_latency_ms}
        self.tolerance = 0.001  # Tolérance de 1 microseconde

    def should_update(self, interface, new_latency_ms):
        """Vérifie si la latence a changé significativement"""
        if interface not in self.cache:
            return True

        old_latency = self.cache[interface]
        return abs(new_latency_ms - old_latency) > self.tolerance

    def update(self, interface, latency_ms):
        """Met à jour le cache"""
        self.cache[interface] = latency_ms

    def clear(self):
        """Vide le cache"""
        self.cache.clear()
