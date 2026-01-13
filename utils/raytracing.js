/**
 * Module de raytracing partagé
 * Utilisé pour vérifier la visibilité entre satellites (occlusion terrestre)
 */

import * as THREE from 'three';
import { EARTH_RADIUS, SCALE, MAX_ISL_DISTANCE, VISIBILITY_CACHE_LIFETIME } from '../constants.js';

// Cache global pour optimiser les calculs de visibilité
const visibilityCache = new Map();

/**
 * Vérifier si deux satellites ont une ligne de vue directe
 * (pas d'occlusion par la Terre)
 *
 * @param {THREE.Object3D} sat1 - Premier satellite
 * @param {THREE.Object3D} sat2 - Deuxième satellite
 * @param {number} currentTime - Temps actuel pour le cache (optionnel)
 * @returns {boolean} true si ligne de vue directe, false sinon
 */
export function checkLineOfSight(sat1, sat2, currentTime = null) {
    const pos1 = sat1.position;
    const pos2 = sat2.position;

    // Optimisation 1 : Vérification rapide de distance
    const distance = pos1.distanceTo(pos2);
    const maxDistance = MAX_ISL_DISTANCE * SCALE;

    if (distance > maxDistance) {
        return false;
    }

    // Optimisation 2 : Vérifier le cache (si currentTime fourni)
    if (currentTime !== null) {
        const sat1Index = sat1.userData?.index ?? sat1.name;
        const sat2Index = sat2.userData?.index ?? sat2.name;
        const minIndex = Math.min(sat1Index, sat2Index);
        const maxIndex = Math.max(sat1Index, sat2Index);
        const cacheKey = `${minIndex}-${maxIndex}`;

        const cached = visibilityCache.get(cacheKey);
        if (cached && (currentTime - cached.time) < VISIBILITY_CACHE_LIFETIME) {
            return cached.visible;
        }

        // Calculer et mettre en cache
        const visible = performRaycast(pos1, pos2, distance);
        visibilityCache.set(cacheKey, { visible, time: currentTime });
        return visible;
    }

    // Pas de cache : calcul direct
    return performRaycast(pos1, pos2, distance);
}

/**
 * Effectuer le raycasting pour vérifier l'occlusion terrestre
 *
 * @param {THREE.Vector3} pos1 - Position du premier satellite
 * @param {THREE.Vector3} pos2 - Position du deuxième satellite
 * @param {number} distance - Distance précalculée entre les deux positions
 * @returns {boolean} true si pas d'occlusion, false sinon
 */
function performRaycast(pos1, pos2, distance) {
    // Optimisation 3 : Test rapide du point milieu
    // Si le point milieu est au-dessus de la surface terrestre, probablement pas d'occlusion
    const midpoint = new THREE.Vector3().addVectors(pos1, pos2).multiplyScalar(0.5);
    const midpointDistance = midpoint.length();
    const earthRadiusScaled = EARTH_RADIUS * SCALE;

    // Si le milieu est clairement au-dessus de la surface, pas besoin de raycast
    if (midpointDistance > earthRadiusScaled * 1.1) {
        // Test supplémentaire : vérifier que les deux satellites sont du même côté
        const dot = pos1.dot(pos2);
        if (dot > 0) {
            return true; // Même hémisphère, pas d'occlusion
        }
    }

    // Raycast complet si nécessaire
    const direction = new THREE.Vector3().subVectors(pos2, pos1).normalize();
    const raycaster = new THREE.Raycaster(pos1, direction, 0, distance);

    // Sphère terrestre
    const earthSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), earthRadiusScaled);

    // Si le rayon intersecte la Terre, il y a occlusion
    const intersects = raycaster.ray.intersectsSphere(earthSphere);

    return !intersects;
}

/**
 * Calculer la distance 3D entre deux satellites en kilomètres
 *
 * @param {THREE.Object3D} sat1 - Premier satellite
 * @param {THREE.Object3D} sat2 - Deuxième satellite
 * @returns {number} Distance en kilomètres
 */
export function calculateDistance(sat1, sat2) {
    const pos1 = sat1.position;
    const pos2 = sat2.position;

    // Convertir de l'échelle de visualisation aux km
    const dx = (pos1.x - pos2.x) / SCALE;
    const dy = (pos1.y - pos2.y) / SCALE;
    const dz = (pos1.z - pos2.z) / SCALE;

    return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

/**
 * Nettoyer le cache de visibilité (utile pour libérer la mémoire)
 */
export function clearVisibilityCache() {
    visibilityCache.clear();
}

