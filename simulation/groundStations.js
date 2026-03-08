import * as THREE from 'three';
import { EARTH_RADIUS, SCALE, EARTH_ROTATION_RATE, GROUND_STATION_SCOPE_ALTITUDE, GROUND_STATION_CONE_ANGLE, LINK_COLORS } from '../constants.js';
import { checkLineOfSight } from '../utils/raytracing.js';
import { clearSceneObjects } from './constellation.js';

let groundStations = [];
let groundStationMeshes = [];
let groundScopeCones = []; // Cônes de visibilité des stations
let groundSatelliteLinks = []; // Liens dynamiques ground station → satellites
let earthRotationAngle = 0; // Angle de rotation actuel de la Terre

// Tracking state: chaque station suit un satellite spécifique
let stationTrackingState = {}; // { stationId: { trackedSatelliteIndex, lastHandoverTime } }

// Convertir des coordonnées géographiques (lat, lon) en position 3D
// Prend en compte la rotation de la Terre
function latLonToCartesian(lat, lon, altitude = 0, rotationOffset = 0) {
    const radius = (EARTH_RADIUS + altitude) * SCALE;
    const phi = (90 - lat) * Math.PI / 180; // Latitude (converti en angle polaire)
    const theta = (lon + 180) * Math.PI / 180 + rotationOffset; // Longitude + rotation Terre

    const x = -radius * Math.sin(phi) * Math.cos(theta);
    const y = radius * Math.cos(phi);
    const z = radius * Math.sin(phi) * Math.sin(theta);

    return new THREE.Vector3(x, y, z);
}

// Convertir position 3D en coordonnées géographiques (lat, lon)
export function cartesianToLatLon(x, y, z) {
    // Convertir de l'échelle de visualisation aux km
    const posX = x / SCALE;
    const posY = y / SCALE;
    const posZ = z / SCALE;

    // Calculer la latitude
    const radius = Math.sqrt(posX * posX + posY * posY + posZ * posZ);
    const lat = 90 - (Math.acos(posY / radius) * 180 / Math.PI);

    // Calculer la longitude
    let lon = Math.atan2(posZ, -posX) * 180 / Math.PI - 180;
    if (lon < -180) lon += 360;
    if (lon > 180) lon -= 360;

    return { lat, lon };
}

// Ajouter une station au sol
export function addGroundStation(scene) {
    const name = document.getElementById('station-name').value.trim();
    const lat = parseFloat(document.getElementById('station-lat').value);
    const lon = parseFloat(document.getElementById('station-lon').value);

    if (!name) {
        alert('Veuillez entrer un nom pour la station');
        return;
    }

    if (isNaN(lat) || lat < -90 || lat > 90) {
        alert('Latitude invalide (doit être entre -90 et 90)');
        return;
    }

    if (isNaN(lon) || lon < -180 || lon > 180) {
        alert('Longitude invalide (doit être entre -180 et 180)');
        return;
    }

    const station = {
        id: groundStations.length,
        name,
        lat,
        lon
    };

    groundStations.push(station);
    createGroundStationMesh(scene, station);
    updateGroundStationList();

    // Réinitialiser les champs
    document.getElementById('station-name').value = '';
    document.getElementById('station-lat').value = '';
    document.getElementById('station-lon').value = '';
}

// Ajouter une station sans passer par le formulaire (utilisé pour l'import)
export function addGroundStationDirect(scene, name, lat, lon) {
    // Validation
    if (!name || typeof name !== 'string') {
        console.error('Nom de station invalide:', name);
        return false;
    }

    if (isNaN(lat) || lat < -90 || lat > 90) {
        console.error('Latitude invalide:', lat);
        return false;
    }

    if (isNaN(lon) || lon < -180 || lon > 180) {
        console.error('Longitude invalide:', lon);
        return false;
    }

    const station = {
        id: groundStations.length,
        name: name.trim(),
        lat: parseFloat(lat),
        lon: parseFloat(lon)
    };

    groundStations.push(station);
    createGroundStationMesh(scene, station);
    return true;
}

// Créer le mesh 3D d'une station au sol
function createGroundStationMesh(scene, station) {
    const position = latLonToCartesian(station.lat, station.lon, 0, earthRotationAngle);

    // Créer un cône pour représenter la station
    const geometry = new THREE.ConeGeometry(0.4, 0.8, 8);
    const material = new THREE.MeshPhongMaterial({
        color: 0xff6600,
        emissive: 0xff6600,
        emissiveIntensity: 0.5,
        shininess: 100
    });
    const cone = new THREE.Mesh(geometry, material);
    cone.position.copy(position);

    // Orienter le cône perpendiculairement à la surface de la Terre
    cone.lookAt(0, 0, 0);
    cone.rotateX(Math.PI / 2);

    // Ajouter un label (optionnel, simplifié pour la performance)
    const stationGroup = new THREE.Group();
    stationGroup.add(cone);
    stationGroup.userData = {
        stationId: station.id,
        lat: station.lat,
        lon: station.lon
    };

    scene.add(stationGroup);
    groundStationMeshes.push(stationGroup);

    // Créer le cône de visibilité (invisible par défaut)
    createScopeCone(scene, station);
}

// Créer le cône de visibilité d'une station au sol
function createScopeCone(scene, station) {
    const position = latLonToCartesian(station.lat, station.lon, 0, earthRotationAngle);

    // Calculer le cône de visibilité jusqu'aux satellites
    const horizonDistance = Math.sqrt(
        Math.pow(EARTH_RADIUS + GROUND_STATION_SCOPE_ALTITUDE, 2) - Math.pow(EARTH_RADIUS, 2)
    );

    // Hauteur du cône = distance radiale jusqu'aux satellites
    const coneHeight = GROUND_STATION_SCOPE_ALTITUDE * SCALE;

    // Rayon du cône basé sur l'angle de visibilité
    const halfAngle = GROUND_STATION_CONE_ANGLE * Math.PI / 180;
    const coneRadius = Math.tan(halfAngle) * coneHeight;

    const geometry = new THREE.ConeGeometry(coneRadius, coneHeight, 32, 1, true);
    const material = new THREE.MeshBasicMaterial({
        color: 0x00ff00,
        transparent: true,
        opacity: 0.2,
        side: THREE.DoubleSide,
        wireframe: false,
        depthWrite: false
    });

    const cone = new THREE.Mesh(geometry, material);

    // Positionner le cône au sommet de la station (base du cône)
    // On décale le cône de la moitié de sa hauteur pour que la base soit à la surface
    const direction = position.clone().normalize();
    const offset = direction.clone().multiplyScalar(coneHeight / 2);
    cone.position.copy(position).add(offset);

    // Orienter le cône vers l'extérieur de la Terre
    cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, -1, 0), direction);

    cone.visible = false; // Invisible par défaut
    cone.userData = { stationId: station.id };

    scene.add(cone);
    groundScopeCones.push(cone);
}

// Mettre à jour les positions des stations au sol (suivent la rotation de la Terre)
export function updateGroundStations(deltaTime, speedFactor) {
    // Mettre à jour l'angle de rotation de la Terre
    const acceleratedDeltaTime = deltaTime * speedFactor;
    earthRotationAngle += EARTH_ROTATION_RATE * acceleratedDeltaTime;

    // Recalculer les positions de toutes les stations
    groundStationMeshes.forEach(mesh => {
        const lat = mesh.userData.lat;
        const lon = mesh.userData.lon;
        const newPosition = latLonToCartesian(lat, lon, 0, earthRotationAngle);

        // Mettre à jour la position du cône de la station
        const cone = mesh.children[0];
        cone.position.copy(newPosition);

        // Réorienter le cône perpendiculairement à la surface
        cone.lookAt(0, 0, 0);
        cone.rotateX(Math.PI / 2);
    });

    // NOTE: Les cônes de visibilité sont maintenant mis à jour dans updateGroundSatelliteLinks()
    // pour suivre le satellite tracké. On ne les oriente plus vers l'extérieur ici.
}

// Afficher/masquer les cônes de visibilité des stations
export function toggleGroundScope(visible) {
    groundScopeCones.forEach(cone => {
        cone.visible = visible;
    });
}

// Créer un lien visuel entre une station et un satellite
function createGroundSatelliteLink(stationPosition, satellitePosition) {
    const points = [stationPosition, satellitePosition];
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({
        color: LINK_COLORS.GROUND_SATELLITE,
        transparent: true,
        opacity: 0.6
    });
    return new THREE.Line(geometry, material);
}

// Calculer l'angle d'élévation entre une station et un satellite
function calculateElevation(stationPosition, satellitePosition) {
    const toSatellite = satellitePosition.clone().sub(stationPosition);
    const stationToCenter = stationPosition.clone().normalize().multiplyScalar(-1);

    // Angle entre la direction vers le satellite et la verticale locale
    const cosAngle = toSatellite.normalize().dot(stationToCenter);
    const elevationAngle = Math.acos(cosAngle) * 180 / Math.PI - 90; // Convertir en élévation

    return elevationAngle;
}

// Trouver le meilleur satellite pour une station (élévation maximale)
function findBestSatellite(stationPosition, satellites, minElevation = 25) {
    let bestSatellite = null;
    let bestElevation = minElevation;

    const stationObj = {
        position: stationPosition.clone()
    };

    satellites.forEach((satellite, index) => {
        if (checkLineOfSight(stationObj, satellite)) {
            const elevation = calculateElevation(stationPosition, satellite.position);

            if (elevation > bestElevation) {
                bestElevation = elevation;
                bestSatellite = index;
            }
        }
    });

    return { satelliteIndex: bestSatellite, elevation: bestElevation };
}

// Mettre à jour les liens dynamiques entre stations et satellites visibles
// Chaque station suit UN seul satellite (handover automatique)
export function updateGroundSatelliteLinks(scene, satellites, currentTime = 0) {
    // Supprimer les anciens liens
    clearSceneObjects(scene, groundSatelliteLinks);

    const MIN_ELEVATION = 10; // Élévation minimale en degrés
    const HANDOVER_HYSTERESIS = 15; // Différence d'élévation pour forcer un handover
    const MIN_HANDOVER_INTERVAL = 10; // Délai minimum entre handovers (secondes)

    // Créer les nouveaux liens (un seul par station)
    groundStationMeshes.forEach(stationMesh => {
        const stationId = stationMesh.userData.stationId;
        const stationPosition = stationMesh.children[0].position;

        // Initialiser le tracking state si nécessaire
        if (!stationTrackingState[stationId]) {
            stationTrackingState[stationId] = {
                trackedSatelliteIndex: null,
                lastHandoverTime: -MIN_HANDOVER_INTERVAL
            };
        }

        const trackingState = stationTrackingState[stationId];
        const trackedIndex = trackingState.trackedSatelliteIndex;

        // Créer un objet temporaire avec position pour le raycast
        const stationObj = {
            position: stationPosition.clone()
        };

        // Vérifier si le satellite actuellement tracké est toujours valide
        let currentSatValid = false;
        let currentElevation = 0;

        if (trackedIndex !== null && satellites[trackedIndex]) {
            if (checkLineOfSight(stationObj, satellites[trackedIndex])) {
                currentElevation = calculateElevation(stationPosition, satellites[trackedIndex].position);
                currentSatValid = currentElevation >= MIN_ELEVATION;
            }
        }

        // Trouver le meilleur satellite disponible
        const best = findBestSatellite(stationPosition, satellites, MIN_ELEVATION);

        // Décision de handover
        let targetSatellite = trackedIndex;
        const timeSinceLastHandover = currentTime - trackingState.lastHandoverTime;

        if (!currentSatValid || trackedIndex === null) {
            // Pas de satellite valide actuellement, prendre le meilleur (handover forcé)
            targetSatellite = best.satelliteIndex;
            if (best.satelliteIndex !== null && best.satelliteIndex !== trackedIndex) {
                trackingState.lastHandoverTime = currentTime;
                console.log(`Station ${stationId}: Handover to sat${best.satelliteIndex} (elev: ${best.elevation.toFixed(1)}°)`);
            }
        } else if (best.satelliteIndex !== null && best.satelliteIndex !== trackedIndex) {
            // Un meilleur satellite est disponible
            // Vérifier l'hystérésis ET le délai minimum
            if (best.elevation - currentElevation > HANDOVER_HYSTERESIS &&
                timeSinceLastHandover >= MIN_HANDOVER_INTERVAL) {
                targetSatellite = best.satelliteIndex;
                trackingState.lastHandoverTime = currentTime;
                console.log(`Station ${stationId}: Handover sat${trackedIndex}→sat${best.satelliteIndex} (${currentElevation.toFixed(1)}°→${best.elevation.toFixed(1)}°)`);
            }
        }

        // Mettre à jour le tracking state
        trackingState.trackedSatelliteIndex = targetSatellite;

        // Créer le lien vers le satellite tracké
        if (targetSatellite !== null && satellites[targetSatellite]) {
            const link = createGroundSatelliteLink(stationPosition, satellites[targetSatellite].position);
            link.userData = {
                stationId: stationId,
                satelliteIndex: targetSatellite
            };
            scene.add(link);
            groundSatelliteLinks.push(link);

            // Orienter le cône de visibilité vers le satellite tracké
            updateScopeOrientation(stationId, stationPosition, satellites[targetSatellite].position);
        }
    });
}

// Orienter le cône de visibilité vers un satellite spécifique
function updateScopeOrientation(stationId, stationPosition, satellitePosition) {
    const scopeCone = groundScopeCones.find(cone => cone.userData.stationId === stationId);
    if (!scopeCone) return;

    // Direction vers le satellite
    const toSatellite = satellitePosition.clone().sub(stationPosition).normalize();

    // Positionner le cône (milieu entre station et satellite)
    const coneHeight = GROUND_STATION_SCOPE_ALTITUDE * SCALE;
    const offset = toSatellite.clone().multiplyScalar(coneHeight / 2);
    scopeCone.position.copy(stationPosition).add(offset);

    // Orienter le cône vers le satellite
    scopeCone.quaternion.setFromUnitVectors(new THREE.Vector3(0, -1, 0), toSatellite);
}

// Supprimer tous les liens ground-satellite
export function clearGroundSatelliteLinks(scene) {
    clearSceneObjects(scene, groundSatelliteLinks);
}


// Supprimer une station au sol
export function removeGroundStation(scene, stationId) {
    // Trouver l'index de la station
    const index = groundStations.findIndex(s => s.id === stationId);
    if (index === -1) return;

    // Retirer le mesh de la scène
    const meshIndex = groundStationMeshes.findIndex(m => m.userData.stationId === stationId);
    if (meshIndex !== -1) {
        scene.remove(groundStationMeshes[meshIndex]);
        groundStationMeshes.splice(meshIndex, 1);
    }

    // Retirer le cône de visibilité
    const coneIndex = groundScopeCones.findIndex(c => c.userData.stationId === stationId);
    if (coneIndex !== -1) {
        scene.remove(groundScopeCones[coneIndex]);
        groundScopeCones.splice(coneIndex, 1);
    }

    // Retirer de la liste
    groundStations.splice(index, 1);
    updateGroundStationList();
}

// Mettre à jour la liste des stations au sol dans l'UI
export function updateGroundStationList() {
    const listContainer = document.getElementById('station-list');
    listContainer.innerHTML = '';

    if (groundStations.length === 0) {
        listContainer.innerHTML = '<div style="color: #888; font-size: 11px; padding: 10px;">Aucune station</div>';
        return;
    }

    groundStations.forEach(station => {
        const trackingState = stationTrackingState[station.id];
        const trackedSat = trackingState?.trackedSatelliteIndex;
        const trackingInfo = trackedSat !== null && trackedSat !== undefined
            ? `<span style="color: #00ff00; font-size: 10px;">📡 Tracking sat${trackedSat}</span>`
            : '<span style="color: #888; font-size: 10px;">⏸ No satellite</span>';

        const item = document.createElement('div');
        item.className = 'station-item';
        item.innerHTML = `
            <div>
                <strong>${station.name}</strong><br>
                <span style="color: #888;">${station.lat.toFixed(2)}°, ${station.lon.toFixed(2)}°</span><br>
                ${trackingInfo}
            </div>
            <button class="delete-btn" onclick="removeGroundStation(${station.id})">×</button>
        `;
        listContainer.appendChild(item);
    });
}

// Calculer la distance entre une position de station et un satellite
export function calculateGSToSatelliteDistance(stationPosition, satellitePosition) {
    // Convertir de l'échelle de visualisation aux km
    const dx = (stationPosition.x - satellitePosition.x) / SCALE;
    const dy = (stationPosition.y - satellitePosition.y) / SCALE;
    const dz = (stationPosition.z - satellitePosition.z) / SCALE;

    return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

// Getters
export function getGroundStations() {
    return groundStations;
}

export function getGroundStationMeshes() {
    return groundStationMeshes;
}

export function getStationTrackingState() {
    return stationTrackingState;
}

