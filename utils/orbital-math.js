/**
 * utils/orbital-math.js
 * Fonctions de mécanique orbitale keplérienne — sans dépendances Three.js.
 * Importé par simulation/constellation.js et les tests.
 */
import { EARTH_RADIUS, GM } from '../constants.js';

/** Vitesse angulaire orbitale (rad/s) */
export function calculateAngularVelocity(altitude) {
    const radius = EARTH_RADIUS + altitude;
    return Math.sqrt(GM / Math.pow(radius, 3));
}

/** Vitesse orbitale linéaire (km/s) */
export function calculateOrbitalVelocity(altitude) {
    const radius = EARTH_RADIUS + altitude;
    return Math.sqrt(GM / radius);
}

/** Période orbitale (minutes) */
export function calculateOrbitalPeriod(altitude) {
    const radius = EARTH_RADIUS + altitude;
    const periodSeconds = 2 * Math.PI * Math.sqrt(Math.pow(radius, 3) / GM);
    return periodSeconds / 60;
}

