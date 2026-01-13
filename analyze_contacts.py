#!/usr/bin/env python3
"""
Script d'analyse avancée des métriques de contacts ISL de constellation satellite.
Compatible avec l'ancien et le nouveau format CSV.

Format ancien: sat_A,sat_B,contact_start,contact_duration,distance_avg,latency_avg
Format nouveau: sat_A,sat_B,timestamp,orbital_period,contact_start,contact_duration,distance_avg,latency_avg

Usage:
    python analyze_contacts.py contacts_2025-11-18T16-36-26.csv
"""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import sys
from pathlib import Path
from collections import defaultdict

# Configuration de style
sns.set_theme(style="whitegrid")
plt.rcParams['figure.figsize'] = (14, 8)
plt.rcParams['font.size'] = 10

def load_data(csv_path):
    """Charge les données CSV avec support des deux formats."""
    print(f"📂 Chargement de {csv_path}...")
    df = pd.read_csv(csv_path)
    print(f"✓ {len(df)} contacts chargés")
    print(f"Colonnes: {list(df.columns)}")

    # Normaliser les colonnes
    if 'timestamp' not in df.columns and 'contact_start' in df.columns:
        df['timestamp'] = df['contact_start']
        print("ℹ️  Colonne 'timestamp' créée depuis 'contact_start'")

    # Vérifier si on a les périodes orbitales
    if 'orbital_period' in df.columns:
        print(f"✓ Périodes orbitales détectées: {df['orbital_period'].nunique()} périodes")
    else:
        print("⚠️  Pas de colonne 'orbital_period' - fonctionnalités limitées")
        # Estimer la période orbitale depuis les données
        max_time = df['contact_start'].max()
        # Supposer ~95 min = 5700s par période pour LEO
        estimated_period = 5700
        df['orbital_period'] = (df['contact_start'] / estimated_period).astype(int) + 1
        print(f"ℹ️  Périodes orbitales estimées (période ~{estimated_period/60:.1f}min)")

    return df

def plot_variance_between_periods(df, output_dir):
    """
    Analyse de la variance entre les périodes orbitales.
    Compare les métriques (durée, distance, latence) entre chaque période.
    """
    if 'orbital_period' not in df.columns:
        print("⚠️  Pas de colonne 'orbital_period' - graphique ignoré")
        return

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # 1. Nombre de contacts par période
    ax1 = axes[0, 0]
    contacts_per_period = df.groupby('orbital_period').size()
    periods = contacts_per_period.index
    ax1.bar(periods, contacts_per_period.values, alpha=0.7, color='steelblue', edgecolor='black')
    ax1.set_xlabel('Période orbitale', fontsize=12)
    ax1.set_ylabel('Nombre de contacts', fontsize=12)
    ax1.set_title('Nombre de contacts par période', fontsize=14, fontweight='bold')
    ax1.grid(axis='y', alpha=0.3)

    # Ajouter moyenne et variance
    mean_contacts = contacts_per_period.mean()
    std_contacts = contacts_per_period.std()
    ax1.axhline(mean_contacts, color='red', linestyle='--', linewidth=2,
                label=f'Moyenne: {mean_contacts:.1f} ± {std_contacts:.1f}')
    ax1.legend()

    # 2. Durée moyenne des contacts par période
    ax2 = axes[0, 1]
    duration_stats = df.groupby('orbital_period')['contact_duration'].agg(['mean', 'std'])
    ax2.errorbar(duration_stats.index, duration_stats['mean'], yerr=duration_stats['std'],
                 marker='o', markersize=8, linewidth=2, capsize=5, capthick=2,
                 color='orange', ecolor='gray', alpha=0.8)
    ax2.set_xlabel('Période orbitale', fontsize=12)
    ax2.set_ylabel('Durée moyenne (s)', fontsize=12)
    ax2.set_title('Durée moyenne des contacts par période (avec écart-type)', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3)

    # Ajouter la variance globale
    global_mean = df['contact_duration'].mean()
    ax2.axhline(global_mean, color='red', linestyle='--', linewidth=1.5,
                label=f'Moyenne globale: {global_mean:.1f}s')
    ax2.legend()

    # 3. Distance moyenne par période
    ax3 = axes[1, 0]
    distance_stats = df.groupby('orbital_period')['distance_avg'].agg(['mean', 'std'])
    ax3.errorbar(distance_stats.index, distance_stats['mean'], yerr=distance_stats['std'],
                 marker='s', markersize=8, linewidth=2, capsize=5, capthick=2,
                 color='green', ecolor='gray', alpha=0.8)
    ax3.set_xlabel('Période orbitale', fontsize=12)
    ax3.set_ylabel('Distance moyenne (km)', fontsize=12)
    ax3.set_title('Distance moyenne des contacts par période (avec écart-type)', fontsize=14, fontweight='bold')
    ax3.grid(True, alpha=0.3)

    global_mean_dist = df['distance_avg'].mean()
    ax3.axhline(global_mean_dist, color='red', linestyle='--', linewidth=1.5,
                label=f'Moyenne globale: {global_mean_dist:.1f}km')
    ax3.legend()

    # 4. Latence moyenne par période
    ax4 = axes[1, 1]
    latency_stats = df.groupby('orbital_period')['latency_avg'].agg(['mean', 'std'])
    ax4.errorbar(latency_stats.index, latency_stats['mean'], yerr=latency_stats['std'],
                 marker='^', markersize=8, linewidth=2, capsize=5, capthick=2,
                 color='purple', ecolor='gray', alpha=0.8)
    ax4.set_xlabel('Période orbitale', fontsize=12)
    ax4.set_ylabel('Latence moyenne (ms)', fontsize=12)
    ax4.set_title('Latence moyenne des contacts par période (avec écart-type)', fontsize=14, fontweight='bold')
    ax4.grid(True, alpha=0.3)

    global_mean_lat = df['latency_avg'].mean()
    ax4.axhline(global_mean_lat, color='red', linestyle='--', linewidth=1.5,
                label=f'Moyenne globale: {global_mean_lat:.4f}ms')
    ax4.legend()

    plt.suptitle('Analyse de variance entre les périodes orbitales', fontsize=16, fontweight='bold', y=0.995)
    plt.tight_layout()
    plt.savefig(output_dir / 'variance_between_periods.png', dpi=300, bbox_inches='tight')
    print("✓ Graphique: variance_between_periods.png")
    plt.close()

    # Calculer et afficher les coefficients de variation
    print("\n📊 Coefficients de variation (CV) entre périodes:")
    cv_contacts = (contacts_per_period.std() / contacts_per_period.mean()) * 100
    cv_duration = (duration_stats['mean'].std() / duration_stats['mean'].mean()) * 100
    cv_distance = (distance_stats['mean'].std() / distance_stats['mean'].mean()) * 100
    cv_latency = (latency_stats['mean'].std() / latency_stats['mean'].mean()) * 100

    print(f"  • Nombre de contacts: {cv_contacts:.2f}%")
    print(f"  • Durée des contacts: {cv_duration:.2f}%")
    print(f"  • Distance: {cv_distance:.2f}%")
    print(f"  • Latence: {cv_latency:.2f}%")

def plot_satellite_contact_timeline(df, output_dir, satellite_id, max_periods=None, limit_neighbors=True):
    """
    Graphique de contact pour un satellite spécifique.
    X = Temps, Y = Satellites en contact, barres colorées par période.

    Args:
        limit_neighbors: Si True, limite aux 30 voisins les plus fréquents. Si False, affiche TOUS les voisins.
    """
    # Filtrer les contacts du satellite
    contacts = df[(df['sat_A'] == satellite_id) | (df['sat_B'] == satellite_id)].copy()

    if len(contacts) == 0:
        print(f"  ⚠️  Aucun contact pour satellite {satellite_id}")
        return

    # Identifier les voisins
    contacts['neighbor'] = contacts.apply(
        lambda row: row['sat_B'] if row['sat_A'] == satellite_id else row['sat_A'],
        axis=1
    )

    # Trier par fréquence de contact (ou par ID si on veut tous les voisins)
    if limit_neighbors:
        # Top N voisins par fréquence
        neighbor_order = contacts['neighbor'].value_counts().head(30).index.tolist()
        contacts = contacts[contacts['neighbor'].isin(neighbor_order)]
        title_suffix = f"(Top 30 voisins)"
    else:
        # TOUS les voisins, triés par ID satellite
        neighbor_order = sorted(contacts['neighbor'].unique())
        title_suffix = f"(TOUS les {len(neighbor_order)} voisins)"

    # Créer le graphique
    fig, ax = plt.subplots(figsize=(18, max(10, len(neighbor_order) * 0.25)))

    # Colormap par période orbitale
    if 'orbital_period' in df.columns:
        n_periods = df['orbital_period'].nunique()
        colors = plt.cm.tab10(np.linspace(0, 1, min(n_periods, 10)))
        period_colors = {period: colors[i % 10] for i, period in enumerate(sorted(df['orbital_period'].unique()))}
    else:
        period_colors = {1: 'steelblue'}

    # Dessiner chaque contact
    for _, row in contacts.iterrows():
        neighbor = row['neighbor']
        start = row['contact_start']
        duration = row['contact_duration']
        y_pos = neighbor_order.index(neighbor)

        period = row.get('orbital_period', 1)
        color = period_colors.get(period, 'gray')

        ax.barh(y_pos, duration, left=start, height=0.8,
                color=color, alpha=0.7, edgecolor='black', linewidth=0.3)

    # Configuration
    ax.set_yticks(range(len(neighbor_order)))
    ax.set_yticklabels([f'Sat {n}' for n in neighbor_order], fontsize=8)
    ax.set_xlabel('Temps de simulation (s)', fontsize=12)
    ax.set_ylabel('Satellites en contact', fontsize=12)
    ax.set_title(f'Timeline des contacts du Satellite {satellite_id} {title_suffix}\n'
                 f'Total: {len(contacts)} contacts avec {len(neighbor_order)} satellites différents',
                 fontsize=14, fontweight='bold')
    ax.grid(axis='x', alpha=0.3, linestyle='--')

    # Légende des périodes
    if 'orbital_period' in df.columns and len(period_colors) <= 10:
        from matplotlib.patches import Patch
        legend_elements = [Patch(facecolor=period_colors[p], label=f'Période {p}')
                          for p in sorted(period_colors.keys())]
        ax.legend(handles=legend_elements, loc='upper right', fontsize=10)

    # Statistiques
    total_duration = contacts['contact_duration'].sum()
    avg_duration = contacts['contact_duration'].mean()
    stats_text = (f'Statistiques:\n'
                 f'• Contacts: {len(contacts)}\n'
                 f'• Voisins uniques: {len(neighbor_order)}\n'
                 f'• Durée totale: {total_duration:.0f}s\n'
                 f'• Durée moyenne: {avg_duration:.1f}s')

    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
            fontsize=10, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7))

    plt.tight_layout()
    suffix = "all" if not limit_neighbors else "top30"
    filename = f'satellite_{satellite_id}_contact_timeline_{suffix}.png'
    plt.savefig(output_dir / filename, dpi=300, bbox_inches='tight')
    print(f"✓ Graphique: {filename}")
    plt.close()

def plot_all_satellites_timelines(df, output_dir, sample_size=12):
    """
    Génère des timelines pour un échantillon représentatif de satellites.
    """
    # Sélectionner les satellites les plus actifs
    sat_counts = pd.concat([
        df['sat_A'].value_counts(),
        df['sat_B'].value_counts()
    ]).groupby(level=0).sum().sort_values(ascending=False)

    selected = sat_counts.head(sample_size).index.tolist()

    print(f"\n📊 Génération des timelines pour {len(selected)} satellites (top 30 voisins)...")
    for sat_id in selected:
        plot_satellite_contact_timeline(df, output_dir, sat_id, limit_neighbors=True)

def plot_contact_density_heatmap(df, output_dir):
    """
    Heatmap de densité de contacts dans le temps.
    X = Temps, Y = Période orbitale, couleur = nombre de contacts actifs.
    """
    if 'orbital_period' not in df.columns:
        print("⚠️  Pas de colonne 'orbital_period' - graphique ignoré")
        return

    # Créer des bins temporels
    max_time = (df['contact_start'] + df['contact_duration']).max()
    time_bins = np.arange(0, max_time + 100, 100)  # bins de 100s

    # Matrice: période x temps
    periods = sorted(df['orbital_period'].unique())
    density_matrix = np.zeros((len(periods), len(time_bins) - 1))

    for i, period in enumerate(periods):
        period_contacts = df[df['orbital_period'] == period]
        for j in range(len(time_bins) - 1):
            t_start = time_bins[j]
            t_end = time_bins[j + 1]
            # Compter contacts actifs dans cette fenêtre
            active = ((period_contacts['contact_start'] < t_end) &
                     (period_contacts['contact_start'] + period_contacts['contact_duration'] > t_start)).sum()
            density_matrix[i, j] = active

    # Graphique
    fig, ax = plt.subplots(figsize=(16, 8))
    im = ax.imshow(density_matrix, aspect='auto', cmap='YlOrRd', interpolation='nearest')

    ax.set_yticks(range(len(periods)))
    ax.set_yticklabels([f'Période {p}' for p in periods])
    ax.set_xlabel('Temps de simulation (s)', fontsize=12)
    ax.set_ylabel('Période orbitale', fontsize=12)
    ax.set_title('Densité de contacts actifs par période et temps', fontsize=14, fontweight='bold')

    # Colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Nombre de contacts actifs', fontsize=11)

    # X ticks (temps)
    n_xticks = 10
    xtick_indices = np.linspace(0, len(time_bins) - 2, n_xticks, dtype=int)
    ax.set_xticks(xtick_indices)
    ax.set_xticklabels([f'{time_bins[i]:.0f}' for i in xtick_indices], rotation=45)

    plt.tight_layout()
    plt.savefig(output_dir / 'contact_density_heatmap.png', dpi=300, bbox_inches='tight')
    print("✓ Graphique: contact_density_heatmap.png")
    plt.close()

def plot_period_comparison_boxplots(df, output_dir):
    """
    Box plots comparant les distributions de métriques entre périodes.
    """
    if 'orbital_period' not in df.columns:
        print("⚠️  Pas de colonne 'orbital_period' - graphique ignoré")
        return

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    # 1. Durée des contacts
    ax1 = axes[0]
    df.boxplot(column='contact_duration', by='orbital_period', ax=ax1, patch_artist=True)
    ax1.set_xlabel('Période orbitale', fontsize=11)
    ax1.set_ylabel('Durée de contact (s)', fontsize=11)
    ax1.set_title('Distribution des durées par période', fontsize=12, fontweight='bold')
    ax1.get_figure().suptitle('')  # Enlever le titre auto

    # 2. Distance
    ax2 = axes[1]
    df.boxplot(column='distance_avg', by='orbital_period', ax=ax2, patch_artist=True)
    ax2.set_xlabel('Période orbitale', fontsize=11)
    ax2.set_ylabel('Distance (km)', fontsize=11)
    ax2.set_title('Distribution des distances par période', fontsize=12, fontweight='bold')
    ax2.get_figure().suptitle('')

    # 3. Latence
    ax3 = axes[2]
    df.boxplot(column='latency_avg', by='orbital_period', ax=ax3, patch_artist=True)
    ax3.set_xlabel('Période orbitale', fontsize=11)
    ax3.set_ylabel('Latence (ms)', fontsize=11)
    ax3.set_title('Distribution des latences par période', fontsize=12, fontweight='bold')
    ax3.get_figure().suptitle('')

    plt.suptitle('Comparaison des distributions entre périodes', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(output_dir / 'period_comparison_boxplots.png', dpi=300, bbox_inches='tight')
    print("✓ Graphique: period_comparison_boxplots.png")
    plt.close()

def plot_network_graph_snapshot(df, output_dir, time_snapshot=None):
    """
    Graphe de réseau à un instant T montrant les connexions actives.
    """
    try:
        import networkx as nx
    except ImportError:
        print("⚠️  networkx non installé - graphique de réseau ignoré")
        print("   Installez avec: pip install networkx")
        return

    # Choisir un instant avec beaucoup de contacts
    if time_snapshot is None:
        # Trouver l'instant avec le plus de contacts actifs
        times = np.linspace(df['contact_start'].min(), df['contact_start'].max(), 100)
        max_active = 0
        best_time = times[0]
        for t in times:
            active = ((df['contact_start'] <= t) &
                     (df['contact_start'] + df['contact_duration'] >= t)).sum()
            if active > max_active:
                max_active = active
                best_time = t
        time_snapshot = best_time

    # Filtrer contacts actifs à cet instant
    active_contacts = df[(df['contact_start'] <= time_snapshot) &
                        (df['contact_start'] + df['contact_duration'] >= time_snapshot)]

    if len(active_contacts) == 0:
        print(f"⚠️  Pas de contacts actifs à t={time_snapshot:.1f}s")
        return

    # Créer le graphe
    G = nx.Graph()
    for _, row in active_contacts.iterrows():
        G.add_edge(row['sat_A'], row['sat_B'],
                  weight=row['contact_duration'],
                  distance=row['distance_avg'])

    # Layout
    pos = nx.spring_layout(G, k=0.5, iterations=50)

    # Graphique
    fig, ax = plt.subplots(figsize=(14, 14))

    # Dessiner nœuds
    node_colors = ['lightblue'] * len(G.nodes())
    nx.draw_networkx_nodes(G, pos, node_color=node_colors,
                          node_size=500, alpha=0.9, ax=ax)

    # Dessiner arêtes
    nx.draw_networkx_edges(G, pos, alpha=0.5, width=2, ax=ax)

    # Labels
    nx.draw_networkx_labels(G, pos, font_size=8, font_weight='bold', ax=ax)

    ax.set_title(f'Graphe du réseau à t={time_snapshot:.1f}s\n'
                f'{len(G.nodes())} satellites, {len(G.edges())} connexions actives',
                fontsize=14, fontweight='bold')
    ax.axis('off')

    plt.tight_layout()
    plt.savefig(output_dir / 'network_graph_snapshot.png', dpi=300, bbox_inches='tight')
    print(f"✓ Graphique: network_graph_snapshot.png (t={time_snapshot:.1f}s)")
    plt.close()

def plot_contact_duration_distribution(df, output_dir):
    """Distribution des durées de contact."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Histogramme
    ax1.hist(df['contact_duration'], bins=50, edgecolor='black', alpha=0.7, color='steelblue')
    ax1.set_xlabel('Durée de contact (s)')
    ax1.set_ylabel('Fréquence')
    ax1.set_title('Distribution des durées de contact ISL')
    ax1.axvline(df['contact_duration'].mean(), color='red', linestyle='--',
                label=f'Moyenne: {df["contact_duration"].mean():.1f}s')
    ax1.axvline(df['contact_duration'].median(), color='green', linestyle='--',
                label=f'Médiane: {df["contact_duration"].median():.1f}s')
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3)

    # Box plot
    ax2.boxplot(df['contact_duration'], vert=True, patch_artist=True,
                boxprops=dict(facecolor='lightblue', alpha=0.7),
                medianprops=dict(color='red', linewidth=2))
    ax2.set_ylabel('Durée de contact (s)')
    ax2.set_title('Box Plot des durées')
    ax2.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / 'contact_duration_distribution.png', dpi=300, bbox_inches='tight')
    print("✓ Graphique: contact_duration_distribution.png")
    plt.close()

def plot_distance_vs_latency(df, output_dir):
    """Relation distance vs latence."""
    fig, ax = plt.subplots(figsize=(10, 6))

    scatter = ax.scatter(df['distance_avg'], df['latency_avg'],
                        alpha=0.5, s=30, c=df['contact_duration'],
                        cmap='viridis', edgecolors='black', linewidth=0.5)

    # Ligne théorique (vitesse de la lumière)
    distances = np.linspace(df['distance_avg'].min(), df['distance_avg'].max(), 100)
    c = 299792.458  # km/s
    theoretical_latency = distances / c * 1000  # en ms
    ax.plot(distances, theoretical_latency, 'r--', linewidth=2,
            label='Latence théorique (vitesse lumière)')

    ax.set_xlabel('Distance moyenne (km)')
    ax.set_ylabel('Latence moyenne (ms)')
    ax.set_title('Distance vs Latence des contacts ISL')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Colorbar
    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label('Durée contact (s)')

    plt.tight_layout()
    plt.savefig(output_dir / 'distance_vs_latency.png', dpi=300, bbox_inches='tight')
    print("✓ Graphique: distance_vs_latency.png")
    plt.close()

def generate_detailed_summary(df, output_dir):
    """Génère un résumé statistique détaillé avec analyse par période."""
    stats = []
    stats.append("=" * 70)
    stats.append("ANALYSE DÉTAILLÉE DES CONTACTS ISL - CONSTELLATION SATELLITE")
    stats.append("=" * 70)
    stats.append("")

    # Informations générales
    stats.append("📊 STATISTIQUES GÉNÉRALES")
    stats.append("-" * 70)
    stats.append(f"Nombre total de contacts: {len(df)}")
    stats.append(f"Durée de simulation: {df['contact_start'].max():.2f} s ({df['contact_start'].max()/60:.2f} min)")

    n_satellites = len(set(df['sat_A'].unique()) | set(df['sat_B'].unique()))
    stats.append(f"Nombre de satellites: {n_satellites}")

    if 'orbital_period' in df.columns:
        n_periods = df['orbital_period'].nunique()
        stats.append(f"Nombre de périodes orbitales: {n_periods}")
    stats.append("")

    # Analyse par période
    if 'orbital_period' in df.columns:
        stats.append("🔄 ANALYSE PAR PÉRIODE ORBITALE")
        stats.append("-" * 70)
        for period in sorted(df['orbital_period'].unique()):
            period_data = df[df['orbital_period'] == period]
            stats.append(f"\nPériode {period}:")
            stats.append(f"  • Contacts: {len(period_data)}")
            stats.append(f"  • Durée moyenne: {period_data['contact_duration'].mean():.2f} s")
            stats.append(f"  • Distance moyenne: {period_data['distance_avg'].mean():.2f} km")
            stats.append(f"  • Latence moyenne: {period_data['latency_avg'].mean():.4f} ms")
        stats.append("")

    # Métriques globales
    stats.append("📈 MÉTRIQUES GLOBALES")
    stats.append("-" * 70)

    stats.append("\nDurée des contacts:")
    stats.append(f"  • Moyenne: {df['contact_duration'].mean():.2f} s")
    stats.append(f"  • Médiane: {df['contact_duration'].median():.2f} s")
    stats.append(f"  • Écart-type: {df['contact_duration'].std():.2f} s")
    stats.append(f"  • Min: {df['contact_duration'].min():.2f} s")
    stats.append(f"  • Max: {df['contact_duration'].max():.2f} s")

    stats.append("\nDistance:")
    stats.append(f"  • Moyenne: {df['distance_avg'].mean():.2f} km")
    stats.append(f"  • Médiane: {df['distance_avg'].median():.2f} km")
    stats.append(f"  • Écart-type: {df['distance_avg'].std():.2f} km")
    stats.append(f"  • Min: {df['distance_avg'].min():.2f} km")
    stats.append(f"  • Max: {df['distance_avg'].max():.2f} km")

    stats.append("\nLatence:")
    stats.append(f"  • Moyenne: {df['latency_avg'].mean():.4f} ms")
    stats.append(f"  • Médiane: {df['latency_avg'].median():.4f} ms")
    stats.append(f"  • Écart-type: {df['latency_avg'].std():.4f} ms")
    stats.append(f"  • Min: {df['latency_avg'].min():.4f} ms")
    stats.append(f"  • Max: {df['latency_avg'].max():.4f} ms")
    stats.append("")

    # Satellites les plus actifs
    sat_counts = pd.concat([
        df['sat_A'].value_counts(),
        df['sat_B'].value_counts()
    ]).groupby(level=0).sum().sort_values(ascending=False)

    stats.append("🛰️  TOP 10 SATELLITES LES PLUS ACTIFS")
    stats.append("-" * 70)
    for i, (sat_id, count) in enumerate(sat_counts.head(10).items(), 1):
        stats.append(f"{i:2d}. Satellite {sat_id:3d}: {count:4d} contacts")
    stats.append("")

    stats.append("=" * 70)

    # Écrire le fichier
    summary_text = "\n".join(stats)
    output_file = output_dir / 'detailed_analysis_summary.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(summary_text)

    print("✓ Résumé détaillé: detailed_analysis_summary.txt")
    return summary_text

def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_contacts.py <contacts_csv_file>")
        print("Exemple: python analyze_contacts.py contacts_2025-11-18T16-36-26.csv")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f"❌ Erreur: Le fichier {csv_path} n'existe pas")
        sys.exit(1)

    # Créer dossier de sortie
    output_dir = csv_path.parent / f'analysis_{csv_path.stem}'
    output_dir.mkdir(exist_ok=True)
    print(f"\n📁 Résultats seront sauvegardés dans: {output_dir}\n")

    # Charger données
    df = load_data(csv_path)
    print()

    # Générer tous les graphiques
    print("🎨 Génération des graphiques d'analyse...\n")

    # Graphiques principaux demandés
    print("1️⃣  Analyse de variance entre périodes...")
    plot_variance_between_periods(df, output_dir)

    print("\n2️⃣  Comparaison des distributions par période...")
    plot_period_comparison_boxplots(df, output_dir)

    print("\n3️⃣  Heatmap de densité de contacts...")
    plot_contact_density_heatmap(df, output_dir)

    print("\n4️⃣  Timelines de contacts par satellite...")

    # Graphique spécial pour le satellite 1 avec TOUS ses voisins
    print("  📡 Génération timeline COMPLÈTE pour satellite 1...")
    plot_satellite_contact_timeline(df, output_dir, satellite_id=1, limit_neighbors=False)

    # Graphiques pour un échantillon de satellites (top 10)
    plot_all_satellites_timelines(df, output_dir, sample_size=10)

    print("\n5️⃣  Graphe de réseau (snapshot)...")
    plot_network_graph_snapshot(df, output_dir)

    print("\n6️⃣  Distribution des durées...")
    plot_contact_duration_distribution(df, output_dir)

    print("\n7️⃣  Distance vs Latence...")
    plot_distance_vs_latency(df, output_dir)

    # Résumé statistique
    print("\n📄 Génération du résumé statistique...")
    summary = generate_detailed_summary(df, output_dir)
    print("\n" + summary)

    print(f"\n✅ Analyse terminée ! Tous les résultats sont dans: {output_dir}")
    print(f"   Total: {len(list(output_dir.glob('*.png')))} graphiques générés")

if __name__ == '__main__':
    main()
