# Architecture du Pipeline de Simulation et Émulation de Constellation Satellite

## Vue d'ensemble du workflow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    PHASE 1 : SIMULATION ORBITALE                        │
│                         (JavaScript + Three.js)                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
        ┌───────────────────────────────────────────────┐
        │  Interface Web Interactive (index.html)       │
        │  • Visualisation 3D (Three.js)                │
        │  • Contrôles constellation (Walker Delta)     │
        │  • Paramètres : altitude, inclinaison, phase  │
        └───────────────────────────────────────────────┘
                                    │
                                    ▼
        ┌───────────────────────────────────────────────┐
        │  Calcul des Positions Orbitales               │
        │  (simulation/constellation.js)                │
        │  • Formules képlériennes                      │
        │  • Propagation GM, vitesse angulaire          │
        │  • Update positions à chaque frame            │
        └───────────────────────────────────────────────┘
                                    │
                                    ▼
        ┌───────────────────────────────────────────────┐
        │  Détection des Liens Voisins                  │
        │  (utils/raytracing.js)                        │
        │  • Line-of-sight check                        │
        │  • Calcul distance entre satellites           │
        │  • Vérification occultation Terre             │
        └───────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   PHASE 2 : COLLECTE DE MÉTRIQUES                       │
│                    (datas/metricsCollector.js)                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
        ┌───────────────────────────────────────────────┐
        │  Échantillonnage Temporel                     │
        │  • Intervalle : 20 secondes                   │
        │  • Durée : 5 périodes orbitales               │
        │  • Accélération temps : speedFactor (1-1000x) │
        └───────────────────────────────────────────────┘
                                    │
                                    ▼
        ┌───────────────────────────────────────────────┐
        │  Collecte Contact Plan                        │
        │  (datas/contactMetrics.js)                    │
        │  • Timestamp contact start/end                │
        │  • Distance moyenne (km)                      │
        │  • Latence moyenne (ms)                       │
        │  • Liens voisins actifs                       │
        └───────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      PHASE 3 : EXPORT DONNÉES                           │
│                      (datas/exporters.js)                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
            ┌─────────────┐ ┌─────────────┐ ┌──────────────┐
            │  Format CSV │ │ Format JSON │ │Format Mininet│
            │             │ │             │ │    (JSON)    │
            │ • Contacts  │ │ • Métadatas │ │ • Topology   │
            │ • Timestamps│ │ • Stats     │ │ • Contact    │
            │ • Périodes  │ │             │ │   Plan       │
            └─────────────┘ └─────────────┘ └──────────────┘
                    │                               │
                    ▼                               │
            ┌─────────────┐                         │
            │   Analyse   │                         │
            │   Python    │                         │
            │  (analyze_  │                         │
            │  contacts)  │                         │
            │             │                         │
            │ • Variance  │                         │
            │ • Timelines │                         │
            │ • Graphiques│                         │
            └─────────────┘                         │
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  PHASE 4 : ÉMULATION RÉSEAU RÉELLE                      │
│              (mininet_satellite_emulation.py)                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
        ┌───────────────────────────────────────────────┐
        │  Chargement Contact Plan JSON                 │
        │  • Parse métadonnées constellation            │
        │  • Extract contact schedule                   │
        │  • Calcul topologie réseau                    │
        └───────────────────────────────────────────────┘
                                    │
                                    ▼
        ┌───────────────────────────────────────────────┐
        │  Création Réseau Mininet                      │
        │  • N hosts = N satellites                     │
        │  • IPs : 10.0.0.1 à 10.0.0.N                  │
        │  • Liens avec latence et bande passante       │
        └───────────────────────────────────────────────┘


## Flux de données détaillé

### 1. Simulation → Métriques

```
Satellite Position (x, y, z)
         │
         ▼
  Line-of-Sight Check ──────┐
         │                   │
         ▼                   ▼
   Visible ?            Distance (km)
    (bool)                   │
         │                   ▼
         └──────────────> Latency (ms)
                              │
                              ▼
                        Contact Record
                        {
                          satA: 0,
                          satB: 5,
                          startTime: 120.5,
                          duration: 245.2,
                          avgLatency: 4.17
                        }
```

### 2. Contact Plan → Mininet

```
JSON Export
{
  "metadata": {
    "constellation": {
      "totalSatellites": 24,
      "altitude_km": 550,
      "planes": 6
    }
  },
  "contactPlan": [
    {
      "satA": 0,
      "satB": 5,
      "startTime": 0.0,
      "endTime": 150.2,
      "avgLatency_ms": 4.17,
      "bandwidth_mbps": 10
    },
    ...
  ]
}
         │
         ▼
  Python Parser
         │
         ▼
  Mininet Network
    sat0 ←─────→ sat5
     │            │
    10ms        10ms
     │            │
    sat1 ←──────→ sat8
```

## Architecture technique

### Frontend (Browser)

```
┌─────────────────────────────────────┐
│         index.html                  │
│  ┌───────────────────────────────┐  │
│  │  Canvas Three.js (WebGL)      │  │
│  │  • Rendu 3D Terre + Satellites│  │
│  │  • Liens ISL et voisins       │  │
│  └───────────────────────────────┘  │
│                                     │
│  ┌───────────────────────────────┐  │
│  │  UI Controls                  │  │
│  │  • Paramètres constellation   │  │
│  │  • Collecte données           │  │
│  │  • Export JSON/CSV/Mininet    │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

### Backend (Python + Mininet)

```
┌──────────────────────────────────────┐
│   Linux Kernel Network Stack         │
│                                      │
│  ┌────────────────────────────────┐  │
│  │  Network Namespaces            │  │
│  │  ┌──────┐ ┌──────┐ ┌──────┐   │  │
│  │  │ sat0 │ │ sat1 │ │ sat2 │   │  │
│  │  └──┬───┘ └───┬──┘ └───┬──┘   │  │
│  │     │         │        │       │  │
│  │  ┌──┴─────────┴────────┴────┐  │  │
│  │  │  Virtual Ethernet (veth) │  │  │
│  │  │  • Latency control (tc)  │  │  │
│  │  │  • Bandwidth limit (tc)  │  │  │
│  │  └──────────────────────────┘  │  │
│  └────────────────────────────────┘  │
└──────────────────────────────────────┘
```

## Composants par fichier

### JavaScript (Simulation)

| Fichier | Responsabilité | Lignes |
|---------|---------------|--------|
| `simulation/main.js` | Boucle animation, handlers UI | ~310 |
| `simulation/constellation.js` | Calcul orbites, création satellites | ~280 |
| `simulation/groundStations.js` | Stations sol | ~140 |
| `utils/raytracing.js` | Line-of-sight, visibilité | ~65 |
| `datas/contactMetrics.js` | Détection/tracking contacts | ~150 |
| `datas/metricsCollector.js` | Orchestration collecte | ~211 |
| `datas/exporters.js` | Exports JSON/CSV/Mininet | ~142 |
| `constants.js` | Constantes physiques | ~25 |

**Total JavaScript**: ~1323 lignes

### Python (Émulation)

| Fichier | Responsabilité | Lignes |
|---------|---------------|--------|
| `mininet_satellite_emulation.py` | Création réseau Mininet | ~113 |
| `analyze_contacts.py` | Analyse variance, graphiques | ~227 |

**Total Python**: ~340 lignes

### HTML/CSS

| Fichier | Responsabilité | Lignes |
|---------|---------------|--------|
| `index.html` | Interface utilisateur | ~730 |

## Métriques clés

### Performance

- **Simulation**: 60 FPS (temps réel) à 60,000 FPS (speedFactor=1000x)
- **Collecte**: 20 secondes d'intervalle, 5 périodes orbitales (~95 min réel)
- **Échantillons**: ~286 samples par test (24 satellites, 5 périodes)
- **Contacts**: ~8,500 contacts détectés (24 satellites, 5 périodes)

### Scalabilité

| Constellation | Satellites | RAM Mininet | Temps collecte (1000x) |
|---------------|-----------|-------------|------------------------|
| 24/6/1 | 24 | 8 GB | ~6 secondes |
| 48/6/1 | 48 | 16 GB | ~24 secondes |
| 80/8/1 | 80 | 32 GB | ~67 secondes |

## Technologies utilisées

```
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│  Visualisation   │   │    Simulation    │   │    Émulation     │
│                  │   │                  │   │                  │
│  • Three.js      │   │  • JavaScript    │   │  • Python 3      │
│  • WebGL         │   │  • ES6 Modules   │   │  • Mininet 2.3+  │
│  • HTML5 Canvas  │   │  • Formules      │   │  • Linux tc      │
│                  │   │    képlériennes  │   │  • Namespaces    │
└──────────────────┘   └──────────────────┘   └──────────────────┘
```

## Points forts de l'architecture

✅ **Séparation des concerns**: Simulation ≠ Émulation
✅ **Interactivité**: Visualisation 3D temps réel
✅ **Reproductibilité**: Export JSON figé
✅ **Flexibilité**: Facile d'ajouter protocoles routage
✅ **Performance**: Accélération temporelle (1-1000×)
✅ **Simplicité**: ~1660 lignes total, pas de serveur

## Évolutions futures possibles

1. **Routage dynamique**: Implémentation OSPF/BGP/CGR
2. **Topologie dynamique**: Liens créés/détruits en temps réel dans Mininet
3. **Stations sol**: Intégration dans l'émulation réseau
4. **Grande échelle**: Migration vers ns-3 pour > 100 satellites
5. **Métriques avancées**: Collecte débit, latence, perte de paquets
