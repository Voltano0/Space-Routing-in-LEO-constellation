/**
 * Constantes globales du projet
 * Utilisées par la simulation, la collecte de métriques, et l'analyse
 */

// ========================================
// CONSTANTES PHYSIQUES
// ========================================

/** Rayon de la Terre en kilomètres */
export const EARTH_RADIUS = 6371; // km

/** Constante gravitationnelle standard de la Terre en km³/s² */
export const GM = 398600.4418; // km³/s²

/** Vitesse de la lumière en km/s */
export const SPEED_OF_LIGHT = 299792.458; // km/s

/** Vitesse de rotation de la Terre en rad/s (un tour en 24h) */
export const EARTH_ROTATION_RATE = (2 * Math.PI) / (24 * 60 * 60); // rad/s

// ========================================
// CONSTANTES DE SIMULATION
// ========================================

/** Échelle pour la visualisation 3D (km → unités Three.js) */
export const SCALE = 0.001;

/** Distance maximale pour les liens inter-satellites (ISL) en km */
export const MAX_ISL_DISTANCE = 5000; // km

/** Facteurs de vitesse disponibles pour la simulation */
export const SPEED_FACTORS = [1, 2, 5, 10, 20, 50, 100, 1000];

// ========================================
// CONSTANTES DE MÉTRIQUES
// ========================================

/** Durée de vie du cache de visibilité en secondes */
export const VISIBILITY_CACHE_LIFETIME = 1.0; // secondes

/** Intervalle d'échantillonnage par défaut pour la collecte de métriques en secondes */
export const DEFAULT_SAMPLING_INTERVAL = 20.0; // secondes

/** Nombre de périodes orbitales par défaut pour la collecte */
export const DEFAULT_ORBITAL_PERIODS = 1;

// ========================================
// CONSTANTES VISUELLES
// ========================================

/** Couleurs pour les différents plans orbitaux (max 20 plans) */
export const PLANE_COLORS = [
    0xff3333, // Rouge
    0x33ff33, // Vert
    0x3333ff, // Bleu
    0xffff33, // Jaune
    0xff33ff, // Magenta
    0x33ffff, // Cyan
    0xff9933, // Orange
    0x9933ff, // Violet
    0x33ff99, // Vert menthe
    0xff3399, // Rose
    0x99ff33, // Citron vert
    0x3399ff, // Bleu ciel
    0xff6633, // Orange rouge
    0x33ff66, // Vert émeraude
    0x6633ff, // Indigo
    0xffcc33, // Or
    0x33ffcc, // Turquoise
    0xcc33ff, // Violet foncé
    0xff33cc, // Fuchsia
    0xccff33  // Jaune vert
];

/** Couleurs pour les différents types de liens */
export const LINK_COLORS = {
    ISL_INTRA_PLANE: 0x00ffff,  // Cyan - liens intra-plan
    ISL_INTER_PLANE: 0xff00ff,  // Magenta - liens inter-plan
    NEIGHBOR: 0x00ff00,         // Vert - liens voisins (visibilité)
    GROUND_SATELLITE: 0xffaa00  // Orange - liens ground station vers satellite
};

// ========================================
// CONSTANTES DE STATIONS AU SOL
// ========================================

/** Altitude du cône de visibilité des stations au sol en km */
export const GROUND_STATION_SCOPE_ALTITUDE = 1000; // km

/** Demi-angle du cône de visibilité des stations au sol en degrés */
export const GROUND_STATION_CONE_ANGLE = 70; // degrés
