import { SCALE } from '../constants.js';
import { getSatellites } from './constellation.js';
import { calculateOrbitalVelocity, calculateOrbitalPeriod } from './constellation.js';
import { cartesianToLatLon } from './groundStations.js';

let selectedSatelliteIndex = -1;

// La fonction makeDraggable a été supprimée - les panels sont maintenant positionnés en CSS

// Afficher les informations détaillées d'un satellite
export function showSatelliteInfo(satIndex) {
    const satellites = getSatellites();
    if (satIndex >= satellites.length) return;

    const infoBox = document.getElementById('satellite-info');
    const infoId = document.getElementById('sat-info-id');

    infoId.textContent = `#${satIndex}`;

    // Définir l'index du satellite sélectionné pour mise à jour en temps réel
    selectedSatelliteIndex = satIndex;

    // Mettre à jour immédiatement les infos
    updateSelectedSatelliteInfo();

    infoBox.style.display = 'block';
}

// Mettre à jour les informations du satellite sélectionné en temps réel
export function updateSelectedSatelliteInfo(params) {
    const satellites = getSatellites();
    if (selectedSatelliteIndex === -1 || selectedSatelliteIndex >= satellites.length) {
        return;
    }

    const satellite = satellites[selectedSatelliteIndex];
    const { altitude, inclination, raan, trueAnomaly } = satellite.userData;
    const pos = satellite.position;

    // Convertir les positions en km
    const posX = (pos.x / SCALE).toFixed(2);
    const posY = (pos.y / SCALE).toFixed(2);
    const posZ = (pos.z / SCALE).toFixed(2);

    // Convertir en coordonnées géographiques
    const { lat, lon } = cartesianToLatLon(pos.x, pos.y, pos.z);

    // Calculer la distance au centre de la Terre
    const distanceFromCenter = Math.sqrt(pos.x * pos.x + pos.y * pos.y + pos.z * pos.z) / SCALE;

    // Calculer les infos orbitales
    const orbitalVelocity = calculateOrbitalVelocity(altitude);
    const orbitalPeriod = calculateOrbitalPeriod(altitude);

    // Trouver le plan orbital et la position dans le plan
    if (!params) return; // Besoin des params pour calculer le plan

    const satsPerPlane = Math.floor(params.numSats / params.numPlanes);
    const extraSats = params.numSats % params.numPlanes;

    let planeIndex = 0;
    let satCount = 0;

    for (let p = 0; p < params.numPlanes; p++) {
        const satsInThisPlane = satsPerPlane + (p < extraSats ? 1 : 0);
        if (selectedSatelliteIndex < satCount + satsInThisPlane) {
            planeIndex = p;
            break;
        }
        satCount += satsInThisPlane;
    }

    const infoContent = document.getElementById('sat-info-content');
    if (!infoContent) return;

    infoContent.innerHTML = `
        <div class="info-row">
            <span class="info-label">Plan orbital:</span>
            <span class="info-value">${planeIndex}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Latitude:</span>
            <span class="info-value">${lat.toFixed(4)}°</span>
        </div>
        <div class="info-row">
            <span class="info-label">Longitude:</span>
            <span class="info-value">${lon.toFixed(4)}°</span>
        </div>
        <div class="info-row">
            <span class="info-label">Position X:</span>
            <span class="info-value">${posX} km</span>
        </div>
        <div class="info-row">
            <span class="info-label">Position Y:</span>
            <span class="info-value">${posY} km</span>
        </div>
        <div class="info-row">
            <span class="info-label">Position Z:</span>
            <span class="info-value">${posZ} km</span>
        </div>
        <div class="info-row">
            <span class="info-label">Distance centre:</span>
            <span class="info-value">${distanceFromCenter.toFixed(2)} km</span>
        </div>
        <div class="info-row">
            <span class="info-label">Altitude:</span>
            <span class="info-value">${altitude} km</span>
        </div>
        <div class="info-row">
            <span class="info-label">Inclinaison:</span>
            <span class="info-value">${inclination}°</span>
        </div>
        <div class="info-row">
            <span class="info-label">RAAN:</span>
            <span class="info-value">${raan.toFixed(2)}°</span>
        </div>
        <div class="info-row">
            <span class="info-label">Anomalie vraie:</span>
            <span class="info-value">${trueAnomaly.toFixed(2)}°</span>
        </div>
        <div class="info-row">
            <span class="info-label">Vitesse orbitale:</span>
            <span class="info-value">${orbitalVelocity.toFixed(2)} km/s</span>
        </div>
        <div class="info-row">
            <span class="info-label">Période orbitale:</span>
            <span class="info-value">${orbitalPeriod.toFixed(1)} min</span>
        </div>
    `;
}

// Fermer la boîte d'informations du satellite
export function closeSatelliteInfo() {
    const satellites = getSatellites();
    selectedSatelliteIndex = -1;
    document.getElementById('satellite-info').style.display = 'none';

    // Réinitialiser tous les satellites
    satellites.forEach((sat) => {
        sat.material.emissiveIntensity = 0.3;
        sat.scale.set(1, 1, 1);
    });
}

// Getters
export function getSelectedSatelliteIndex() {
    return selectedSatelliteIndex;
}
