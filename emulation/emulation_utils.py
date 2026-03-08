#!/usr/bin/env python3
"""
emulation_utils.py
Fonctions de calcul pures — sans dépendances externes (pas de Mininet, pas de FRR).
Importées par isis_routing.py, isis_metrics_collector.py, mininet_gs_timeseries.py
et les tests unitaires.
"""


# ── Adressage ISIS ────────────────────────────────────────────────────────────

def compute_net_address(hostname: str, is_gs: bool, plane_id: int = None) -> str:
    """
    Calcule l'adresse NET IS-IS pour un nœud.
    Format : 49.{area_id}.{sys_id}.00
      - GS  : sys_id = 0000.0000.{gs_num:04d}
      - SAT : sys_id = 0000.0001.{sat_num:04d}
      - area_id = plane_id+1 si défini, sinon 0001 (mode flat)
    """
    if is_gs:
        gs_num = int(hostname.replace('gs', ''))
        sys_id = f"0000.0000.{gs_num:04d}"
    else:
        sat_num = int(hostname.replace('sat', ''))
        sys_id = f"0000.0001.{sat_num:04d}"

    area_id = f"{plane_id + 1:04d}" if plane_id is not None else "0001"
    return f"49.{area_id}.{sys_id}.00"


# ── Utilisation des liens ─────────────────────────────────────────────────────

def compute_link_utilization(delta_tx: int, delta_rx: int,
                             dt: float, bandwidth_mbps: float):
    """
    Calcule le débit et le taux d'utilisation d'un lien.

    Args:
        delta_tx: octets transmis depuis la dernière mesure
        delta_rx: octets reçus depuis la dernière mesure
        dt:       intervalle de temps (secondes)
        bandwidth_mbps: bande passante nominale (Mbps)

    Returns:
        (tx_rate_mbps, rx_rate_mbps, utilization_pct)
    """
    tx_rate = (delta_tx * 8) / (dt * 1_000_000)
    rx_rate = (delta_rx * 8) / (dt * 1_000_000)
    utilization = max(tx_rate, rx_rate) / bandwidth_mbps * 100 if bandwidth_mbps > 0 else 0
    return round(tx_rate, 4), round(rx_rate, 4), round(utilization, 2)


# ── Convergence ISIS ──────────────────────────────────────────────────────────

def compute_convergence_time(adjacency_up_time_s: float,
                             route_present_time_s: float) -> float:
    """
    Temps de convergence = max(temps adjacence, temps route).
    Correspond à l'instant où le réseau est à nouveau opérationnel.
    """
    return max(adjacency_up_time_s, route_present_time_s)


# ── Perte de paquets ──────────────────────────────────────────────────────────

def compute_packet_loss(packets_sent: int, packets_received: int):
    """
    Calcule le nombre et le pourcentage de paquets perdus.

    Returns:
        (packets_lost, loss_percent)
    """
    lost = packets_sent - packets_received
    pct = (lost / packets_sent * 100) if packets_sent > 0 else 0.0
    return lost, round(pct, 1)


# ── Allocation IP des liens ISL ───────────────────────────────────────────────

def compute_isl_subnet(link_counter: int) -> str:
    """
    Calcule le préfixe de sous-réseau ISL (10.x.y) depuis un compteur.
    Chaque lien ISL reçoit un /30 : .1 côté satA, .2 côté satB.

    Args:
        link_counter: index du lien (commence à 0)
    """
    base = 10 + (link_counter // 65536)
    second = (link_counter // 256) % 256
    third = link_counter % 256
    return f"{base}.{second}.{third}"


def compute_gs_subnet(link_counter: int) -> str:
    """
    Calcule le préfixe de sous-réseau GS (192.168.x ou 192.169.x…).
    link_counter est la valeur POST-incrément du compteur GS
    (self.link_counter dans DynamicGSLinkManager, initialisé à 50000,
    pré-incrémenté avant chaque appel → première valeur = 50001).

    Args:
        link_counter: valeur courante du compteur après incrément
    """
    second = 168 + (link_counter // 256) % 87
    third = link_counter % 256
    return f"192.{second}.{third}"
