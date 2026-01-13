import * as THREE from 'three';
import { EARTH_RADIUS, SCALE, GM, PLANE_COLORS, LINK_COLORS } from '../constants.js';
import { checkLineOfSight } from '../utils/raytracing.js';

let satellites = [];
let orbits = [];
let links = [];
let neighborLinks = [];
let currentOrbitalPeriod = 0;

// Helper pour nettoyer les objets de la scène
export function clearSceneObjects(scene, objects) {
    objects.forEach(obj => scene.remove(obj));
    objects.length = 0;
}

// Calculer la vitesse angulaire réaliste d'un satellite (rad/s)
export function calculateAngularVelocity(altitude) {
    const radius = EARTH_RADIUS + altitude; // km
    // Vitesse angulaire ω = sqrt(GM/r³) en rad/s
    const angularVelocity = Math.sqrt(GM / Math.pow(radius, 3));
    return angularVelocity;
}

// Calculer la vitesse orbitale linéaire (km/s)
export function calculateOrbitalVelocity(altitude) {
    const radius = EARTH_RADIUS + altitude; // km
    // v = sqrt(GM/r) en km/s
    const velocity = Math.sqrt(GM / radius);
    return velocity;
}

// Calculer la période orbitale (minutes)
export function calculateOrbitalPeriod(altitude) {
    const radius = EARTH_RADIUS + altitude; // km
    // T = 2π * sqrt(r³/GM) en secondes
    const period = 2 * Math.PI * Math.sqrt(Math.pow(radius, 3) / GM);
    return period / 60; // Convertir en minutes
}

// Calculer la position d'un satellite en coordonnées cartésiennes
export function getSatellitePosition(altitude, inclination, raan, trueAnomaly) {
    const radius = (EARTH_RADIUS + altitude) * SCALE;
    const incRad = inclination * Math.PI / 180;
    const raanRad = raan * Math.PI / 180;
    const taRad = trueAnomaly * Math.PI / 180;

    // Position dans le plan orbital
    const x_orbital = radius * Math.cos(taRad);
    const z_orbital = radius * Math.sin(taRad);

    // Rotation par l'inclinaison et le RAAN
    // Dans Three.js, Y est l'axe vertical (pôles)
    const x = x_orbital * Math.cos(raanRad) - z_orbital * Math.cos(incRad) * Math.sin(raanRad);
    const y = z_orbital * Math.sin(incRad);
    const z = x_orbital * Math.sin(raanRad) + z_orbital * Math.cos(incRad) * Math.cos(raanRad);

    return new THREE.Vector3(x, y, z);
}

// Créer une orbite
function createOrbit(altitude, inclination, raan, color = 0x444444) {
    const points = [];
    const numPoints = 128;

    for (let i = 0; i <= numPoints; i++) {
        const trueAnomaly = (i / numPoints) * 360;
        const pos = getSatellitePosition(altitude, inclination, raan, trueAnomaly);
        points.push(pos);
    }

    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({
        color: color,
        transparent: true,
        opacity: 0.4
    });

    return new THREE.Line(geometry, material);
}

// Générer une constellation Walker Delta
export function createConstellation(scene, params) {
    // Nettoyer les satellites et orbites existants
    clearSceneObjects(scene, satellites);
    clearSceneObjects(scene, orbits);
    clearSceneObjects(scene, links);

    const { altitude, inclination, numSats, numPlanes, phase, satelliteSize } = params;
    const satsPerPlane = Math.floor(numSats / numPlanes);
    const extraSats = numSats % numPlanes; // Satellites restants à distribuer

    // Calculer les paramètres orbitaux réalistes
    const angularVelocity = calculateAngularVelocity(altitude);
    const orbitalVelocity = calculateOrbitalVelocity(altitude);
    const orbitalPeriod = calculateOrbitalPeriod(altitude);
    currentOrbitalPeriod = orbitalPeriod;

    // Notation Walker Delta
    const notation = `${numSats}/${numPlanes}/${phase}`;
    document.getElementById('notation').textContent = notation;
    document.getElementById('satsPerPlane').textContent = `${satsPerPlane}${extraSats > 0 ? '-' + (satsPerPlane + 1) : ''}`;
    document.getElementById('orbitalRadius').textContent = (EARTH_RADIUS + altitude).toFixed(0);
    document.getElementById('orbitalVelocity').textContent = orbitalVelocity.toFixed(2);
    document.getElementById('orbitalPeriod').textContent = orbitalPeriod.toFixed(1);

    // Créer les satellites
    for (let p = 0; p < numPlanes; p++) {
        const raan = (p * 360) / numPlanes; // Right Ascension of Ascending Node

        // Nombre de satellites dans ce plan (les premiers plans ont un satellite supplémentaire)
        const satsInThisPlane = satsPerPlane + (p < extraSats ? 1 : 0);

        // Couleur pour ce plan orbital
        const planeColor = PLANE_COLORS[p % PLANE_COLORS.length];

        // Créer l'orbite si demandé
        if (params.showOrbits) {
            const orbit = createOrbit(altitude, inclination, raan, planeColor);
            scene.add(orbit);
            orbits.push(orbit);
        }

        for (let s = 0; s < satsInThisPlane; s++) {
            // Calcul de l'anomalie vraie avec le phasage Walker Delta
            const trueAnomaly = (s * 360) / satsInThisPlane + (p * phase * 360) / numSats;

            // Créer le satellite avec la couleur du plan
            const satGeometry = new THREE.SphereGeometry(satelliteSize || 0.3, 16, 16);
            const satMaterial = new THREE.MeshPhongMaterial({
                color: planeColor,
                emissive: planeColor,
                emissiveIntensity: 0.3,
                shininess: 100
            });
            const satellite = new THREE.Mesh(satGeometry, satMaterial);

            // Stocker les paramètres orbitaux pour l'animation
            satellite.userData = {
                altitude,
                inclination,
                raan,
                trueAnomaly,
                angularVelocity: angularVelocity, // vitesse angulaire réaliste en rad/s
                index: satellites.length // Index du satellite dans le tableau
            };

            // Positionner le satellite
            const pos = getSatellitePosition(altitude, inclination, raan, trueAnomaly);
            satellite.position.copy(pos);

            scene.add(satellite);
            satellites.push(satellite);
        }
    }

    // Créer les liens ISL si demandé
    if (params.showLinks) {
        createISL(scene, params);
    }

    return satellites;
}

// Créer les liens Inter-Satellite (ISL)
export function createISL(scene, params) {
    clearSceneObjects(scene, links);

    const { numPlanes, numSats } = params;
    const satsPerPlane = Math.floor(numSats / numPlanes);
    const extraSats = numSats % numPlanes;

    // Calculer les infos de chaque plan
    const planeInfo = [];
    let satIndexOffset = 0;
    for (let p = 0; p < numPlanes; p++) {
        const satsInThisPlane = satsPerPlane + (p < extraSats ? 1 : 0);
        planeInfo.push({
            startIndex: satIndexOffset,
            count: satsInThisPlane
        });
        satIndexOffset += satsInThisPlane;
    }

    // Créer les liens pour chaque plan
    for (let p = 0; p < numPlanes; p++) {
        const currentPlane = planeInfo[p];

        // Liens intra-plan (satellite suivant dans le même plan)
        for (let s = 0; s < currentPlane.count; s++) {
            const satIndex = currentPlane.startIndex + s;
            const nextSatIndex = currentPlane.startIndex + ((s + 1) % currentPlane.count);

            const link = createLink(satellites[satIndex], satellites[nextSatIndex], LINK_COLORS.ISL_INTRA_PLANE);
            scene.add(link);
            links.push(link);
        }

        // Liens inter-plan (satellite dans le plan adjacent)
        if (p < numPlanes - 1) {
            const nextPlane = planeInfo[p + 1];
            const minCount = Math.min(currentPlane.count, nextPlane.count);

            for (let s = 0; s < minCount; s++) {
                const satIndex = currentPlane.startIndex + s;
                const nextSatIndex = nextPlane.startIndex + s;

                const link = createLink(satellites[satIndex], satellites[nextSatIndex], LINK_COLORS.ISL_INTER_PLANE);
                scene.add(link);
                links.push(link);
            }
        }
    }
}

// Créer un lien entre deux satellites
function createLink(sat1, sat2, color) {
    const points = [sat1.position, sat2.position];
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({
        color: color,
        transparent: true,
        opacity: 0.3
    });
    return new THREE.Line(geometry, material);
}

// La fonction checkLineOfSight est maintenant importée depuis utils/raytracing.js

// Créer les liens voisins (basés sur visibilité instantanée)
export function createNeighborLinks(scene) {
    // Nettoyer les anciens liens
    clearSceneObjects(scene, neighborLinks);

    // Vérifier toutes les paires de satellites
    for (let i = 0; i < satellites.length; i++) {
        for (let j = i + 1; j < satellites.length; j++) {
            if (checkLineOfSight(satellites[i], satellites[j])) {
                // Couleur pour les liens voisins
                const link = createLink(satellites[i], satellites[j], LINK_COLORS.NEIGHBOR);
                scene.add(link);
                neighborLinks.push(link);
            }
        }
    }
}

// Mettre à jour les positions des liens voisins
export function updateNeighborLinks(scene) {
    // Nettoyer et recréer les liens (peut être optimisé plus tard)
    clearSceneObjects(scene, neighborLinks);

    // Recréer les liens avec positions actuelles
    for (let i = 0; i < satellites.length; i++) {
        for (let j = i + 1; j < satellites.length; j++) {
            if (checkLineOfSight(satellites[i], satellites[j])) {
                const link = createLink(satellites[i], satellites[j], LINK_COLORS.NEIGHBOR);
                scene.add(link);
                neighborLinks.push(link);
            }
        }
    }
}

// Mettre à jour les positions des satellites (animation)
export function updateSatellites(deltaTime, speedFactor) {
    // Appliquer le facteur d'accélération
    const acceleratedDeltaTime = deltaTime * speedFactor;

    satellites.forEach(satellite => {
        const { altitude, inclination, raan, angularVelocity } = satellite.userData;

        // Mettre à jour l'anomalie vraie
        // angularVelocity est en rad/s, on convertit en degrés/s puis multiplie par deltaTime
        const angularVelocityDegPerSec = angularVelocity * (180 / Math.PI);
        satellite.userData.trueAnomaly += angularVelocityDegPerSec * acceleratedDeltaTime;

        if (satellite.userData.trueAnomaly > 360) {
            satellite.userData.trueAnomaly -= 360;
        }

        // Calculer la nouvelle position
        const pos = getSatellitePosition(altitude, inclination, raan, satellite.userData.trueAnomaly);
        satellite.position.copy(pos);
    });

    // Mettre à jour les liens ISL
    if (links.length > 0) {
        links.forEach((link, index) => {
            const positions = link.geometry.attributes.position.array;
            const sat1Pos = satellites[Math.floor(index / 2)].position;
            const sat2Pos = satellites[Math.floor(index / 2) + 1].position;

            if (sat1Pos && sat2Pos) {
                positions[0] = sat1Pos.x;
                positions[1] = sat1Pos.y;
                positions[2] = sat1Pos.z;
                positions[3] = sat2Pos.x;
                positions[4] = sat2Pos.y;
                positions[5] = sat2Pos.z;
                link.geometry.attributes.position.needsUpdate = true;
            }
        });
    }
}

// Getters pour accéder aux satellites/orbites/liens depuis d'autres modules
export function getSatellites() {
    return satellites;
}

export function getOrbits() {
    return orbits;
}

export function getLinks() {
    return links;
}

export function getNeighborLinks() {
    return neighborLinks;
}

export function getOrbitalPeriod() {
    return currentOrbitalPeriod;
}
