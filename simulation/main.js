import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { SPEED_FACTORS, DEFAULT_SAMPLING_INTERVAL, DEFAULT_ORBITAL_PERIODS } from '../constants.js';
import { createEarth, rotateEarth, createStars } from './earth.js';
import { createConstellation, updateSatellites, createISL, getOrbits, getLinks, getSatellites, getOrbitalPeriod, createNeighborLinks, updateNeighborLinks, getNeighborLinks, clearSceneObjects } from './constellation.js';
import { updateSatelliteGrid, highlightSatellite } from './grid.js';
import { addGroundStation, removeGroundStation, updateGroundStationList, updateGroundStations, toggleGroundScope, updateGroundSatelliteLinks, clearGroundSatelliteLinks, addGroundStationDirect } from './groundStations.js';
import { showSatelliteInfo, closeSatelliteInfo, updateSelectedSatelliteInfo, getSelectedSatelliteIndex } from './ui.js';
import MetricsCollector from '../datas/metricsCollector.js';

// Variables globales
let scene, camera, renderer, controls;
let simulationTime = 0;
let metricsCollector = null;

// Paramètres de la constellation
let params = {
    altitude: 550,
    inclination: 55,
    numSats: 24,
    numPlanes: 6,
    phase: 1,
    showOrbits: true,
    showLinks: false,
    showNeighborLinks: false,
    showGroundScope: false,
    animate: true,
    showGrid: true,
    speedFactor: 1
};

// Initialisation
function init() {
    // Créer la scène
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x000000);

    // Créer la caméra
    camera = new THREE.PerspectiveCamera(
        60,
        window.innerWidth / window.innerHeight,
        0.1,
        100000
    );
    camera.position.set(50, 30, 50);

    // Créer le renderer
    const container = document.getElementById('canvas-container');
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    // Contrôles de la caméra
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.minDistance = 10;
    controls.maxDistance = 200;

    // Ajouter les lumières
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 1);
    directionalLight.position.set(50, 50, 50);
    scene.add(directionalLight);

    // Créer la Terre
    createEarth(scene);

    // Ajouter les étoiles
    createStars(scene);

    // Créer la constellation initiale
    createConstellation(scene, params);

    // Mettre à jour la grille de visualisation
    updateSatelliteGrid(params, (satIndex) => {
        highlightSatellite(satIndex, showSatelliteInfo);
    });

    // Gérer le redimensionnement
    window.addEventListener('resize', onWindowResize);

    // Connecter les contrôles
    setupControls();

    // Initialiser la liste des stations
    updateGroundStationList();

    // Initialiser le collecteur de métriques
    metricsCollector = new MetricsCollector();
    setupMetricsControls();

    // Mettre à jour l'affichage des paramètres de collecte
    document.getElementById('orbital-periods-value').textContent = DEFAULT_ORBITAL_PERIODS;
    document.getElementById('sampling-interval-value').textContent = DEFAULT_SAMPLING_INTERVAL;

    // Démarrer l'animation
    animate();
}

// Animation principale
let lastTime = 0;
let frameCount = 0;
let fpsTime = 0;

function animate() {
    requestAnimationFrame(animate);

    const currentTime = performance.now();
    const deltaTime = (currentTime - lastTime) / 1000;
    lastTime = currentTime;

    // Calculer les FPS
    frameCount++;
    fpsTime += deltaTime;
    if (fpsTime >= 1) {
        document.getElementById('fps').textContent = frameCount;
        frameCount = 0;
        fpsTime = 0;
    }

    // Mettre à jour les satellites
    if (params.animate) {
        updateSatellites(deltaTime, params.speedFactor);

        // Mettre à jour les liens voisins si activés
        if (params.showNeighborLinks) {
            updateNeighborLinks(scene);
        }
    }

    // Mettre à jour le temps de simulation (accéléré par speedFactor)
    if (params.animate) {
        simulationTime += deltaTime * params.speedFactor;
    }

    // Mettre à jour les infos du satellite sélectionné en temps réel
    if (getSelectedSatelliteIndex() !== -1) {
        updateSelectedSatelliteInfo(params);
    }

    // Rotation de la Terre à vitesse réelle (accélérée par speedFactor)
    if (params.animate) {
        rotateEarth(deltaTime, params.speedFactor);
    }

    // Mettre à jour les positions des stations au sol (suivent la Terre)
    if (params.animate) {
        updateGroundStations(deltaTime, params.speedFactor);
    }

    // Mettre à jour les liens dynamiques ground-satellite si activés
    if (params.showGroundScope) {
        const satellites = getSatellites();
        updateGroundSatelliteLinks(scene, satellites);
    }

    // Mettre à jour la collecte de métriques si elle est active
    if (metricsCollector && metricsCollector.isCollecting) {
        const satellites = getSatellites();
        metricsCollector.update(satellites, simulationTime);
    }

    controls.update();
    renderer.render(scene, camera);
}

// Gérer le redimensionnement de la fenêtre
function onWindowResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}

// Configurer les contrôles de l'interface
function setupControls() {
    // Sliders normaux (sans numSats, on le gère séparément)
    const sliders = ['altitude', 'inclination', 'phase'];
    sliders.forEach(id => {
        const slider = document.getElementById(id);
        const display = document.getElementById(`${id}-value`);

        slider.addEventListener('input', (e) => {
            params[id] = parseFloat(e.target.value);
            display.textContent = e.target.value;
        });
    });

    // Sliders numSats et numPlanes avec synchronisation
    const numSatsSlider = document.getElementById('numSats');
    const numSatsDisplay = document.getElementById('numSats-value');
    const numPlanesSlider = document.getElementById('numPlanes');
    const numPlanesDisplay = document.getElementById('numPlanes-value');
    const phaseSlider = document.getElementById('phase');
    const phaseDisplay = document.getElementById('phase-value');

    // Fonction pour ajuster numSats au multiple le plus proche de numPlanes
    function adjustNumSatsToMultiple(numSats, numPlanes) {
        const satsPerPlane = Math.round(numSats / numPlanes);
        return Math.max(numPlanes, satsPerPlane * numPlanes); // Minimum 1 satellite par plan
    }

    // Fonction pour mettre à jour l'affichage du nombre de satellites
    function updateNumSatsDisplay(numSats, numPlanes) {
        const satsPerPlane = numSats / numPlanes;
        numSatsDisplay.textContent = `${numSats} (${satsPerPlane} sat/plan)`;
    }

    // Fonction pour ajuster le max de phase
    function updatePhaseMax(numPlanes) {
        const maxPhase = numPlanes - 1;
        phaseSlider.max = maxPhase;

        // Si la phase actuelle dépasse le nouveau max, l'ajuster
        if (params.phase > maxPhase) {
            params.phase = maxPhase;
            phaseSlider.value = maxPhase;
            phaseDisplay.textContent = maxPhase;
        }
    }

    // Initialiser le max de phase au chargement
    updatePhaseMax(params.numPlanes);

    // Initialiser l'affichage du nombre de satellites au chargement
    updateNumSatsDisplay(params.numSats, params.numPlanes);

    // Listener pour numSats - ajuste au multiple de numPlanes
    numSatsSlider.addEventListener('input', (e) => {
        let numSats = parseFloat(e.target.value);
        const adjustedNumSats = adjustNumSatsToMultiple(numSats, params.numPlanes);

        params.numSats = adjustedNumSats;
        numSatsSlider.value = adjustedNumSats;
        updateNumSatsDisplay(adjustedNumSats, params.numPlanes);
    });

    // Listener pour numPlanes - ajuste numSats et phase
    numPlanesSlider.addEventListener('input', (e) => {
        const numPlanes = parseFloat(e.target.value);
        params.numPlanes = numPlanes;
        numPlanesDisplay.textContent = e.target.value;

        // Ajuster le max de phase à numPlanes - 1
        updatePhaseMax(numPlanes);

        // Ajuster numSats pour rester un multiple
        const adjustedNumSats = adjustNumSatsToMultiple(params.numSats, numPlanes);
        params.numSats = adjustedNumSats;
        numSatsSlider.value = adjustedNumSats;
        updateNumSatsDisplay(adjustedNumSats, numPlanes);
    });

    // Slider pour la vitesse de simulation (avec mapping spécial)
    const speedSlider = document.getElementById('speedFactor');
    const speedDisplay = document.getElementById('speedFactor-value');

    speedSlider.addEventListener('input', (e) => {
        const index = parseInt(e.target.value);
        params.speedFactor = SPEED_FACTORS[index];
        speedDisplay.textContent = params.speedFactor;
    });

    // Checkboxes
    document.getElementById('showOrbits').addEventListener('change', (e) => {
        params.showOrbits = e.target.checked;
        const orbits = getOrbits();
        orbits.forEach(orbit => orbit.visible = e.target.checked);
    });

    document.getElementById('showLinks').addEventListener('change', (e) => {
        params.showLinks = e.target.checked;
        if (e.target.checked) {
            createISL(scene, params);
        } else {
            clearSceneObjects(scene, getLinks());
        }
    });

    document.getElementById('showNeighborLinks').addEventListener('change', (e) => {
        params.showNeighborLinks = e.target.checked;
        if (e.target.checked) {
            createNeighborLinks(scene);
        } else {
            clearSceneObjects(scene, getNeighborLinks());
        }
    });

    document.getElementById('showGroundScope').addEventListener('change', (e) => {
        params.showGroundScope = e.target.checked;
        toggleGroundScope(e.target.checked);

        // Nettoyer les liens si désactivé
        if (!e.target.checked) {
            clearGroundSatelliteLinks(scene);
        }
    });

    document.getElementById('animate').addEventListener('change', (e) => {
        params.animate = e.target.checked;
    });

    document.getElementById('showGrid').addEventListener('change', (e) => {
        params.showGrid = e.target.checked;
        document.getElementById('grid-view').style.display = e.target.checked ? 'block' : 'none';
        if (e.target.checked) {
            updateSatelliteGrid(params, (satIndex) => {
                highlightSatellite(satIndex, showSatelliteInfo);
            });
        }
    });

    document.getElementById('showMetricsPanel').addEventListener('change', (e) => {
        document.getElementById('metrics-panel').style.display = e.target.checked ? 'block' : 'none';
    });

    document.getElementById('showGroundStationsPanel').addEventListener('change', (e) => {
        document.getElementById('ground-stations').style.display = e.target.checked ? 'block' : 'none';
    });

    // Bouton de mise à jour
    document.getElementById('updateBtn').addEventListener('click', () => {
        createConstellation(scene, params);
        updateSatelliteGrid(params, (satIndex) => {
            highlightSatellite(satIndex, showSatelliteInfo);
        });
    });
}

// Configurer les contrôles de collecte de métriques
function setupMetricsControls() {
    const startBtn = document.getElementById('start-collection-btn');
    const exportJSONBtn = document.getElementById('export-json-btn');
    const exportCSVBtn = document.getElementById('export-csv-btn');
    const exportMininetBtn = document.getElementById('export-mininet-btn');
    const exportSummaryBtn = document.getElementById('export-summary-btn');
    const progressDiv = document.getElementById('collection-progress');

    // Bouton démarrer la collecte
    startBtn.addEventListener('click', () => {
        if (!metricsCollector.isCollecting) {
            const orbitalPeriod = getOrbitalPeriod();
            if (orbitalPeriod === 0) {
                alert('Veuillez créer une constellation d\'abord.');
                return;
            }

            metricsCollector.startCollection(orbitalPeriod);
            startBtn.textContent = 'Collecte en cours...';
            startBtn.disabled = true;
            progressDiv.style.display = 'block';

            // Désactiver les boutons d'export pendant la collecte
            exportJSONBtn.disabled = true;
            exportCSVBtn.disabled = true;
            exportMininetBtn.disabled = true;
            exportSummaryBtn.disabled = true;
        }
    });

    // Hook pour réactiver le bouton quand la collecte est terminée
    const originalOnComplete = metricsCollector.onCollectionComplete.bind(metricsCollector);
    metricsCollector.onCollectionComplete = function() {
        originalOnComplete();
        startBtn.textContent = 'Démarrer la collecte';
        startBtn.disabled = false;
    };

    // Boutons d'export
    exportJSONBtn.addEventListener('click', () => {
        metricsCollector.exportJSON();
    });

    exportCSVBtn.addEventListener('click', () => {
        metricsCollector.exportCSV();
    });

    exportMininetBtn.addEventListener('click', () => {
        // Récupérer les paramètres de la constellation
        const constellation = {
            numSats: params.numSats,
            numPlanes: params.numPlanes,
            phase: params.phase,
            altitude: params.altitude,
            inclination: params.inclination
        };
        metricsCollector.exportMininet(constellation);
    });

    exportSummaryBtn.addEventListener('click', () => {
        metricsCollector.exportSummary();
    });
}

// Fonction pour importer des stations depuis un fichier TXT
window.handleStationsFileImport = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        const content = e.target.result;
        const lines = content.split('\n');

        let successCount = 0;
        let errorCount = 0;
        const errors = [];

        lines.forEach((line, index) => {
            // Ignorer les lignes vides
            const trimmedLine = line.trim();
            if (!trimmedLine) return;

            // Parser la ligne: nom lat lon
            // Peut être séparé par espace, tabulation ou plusieurs espaces
            const parts = trimmedLine.split(/\s+/);

            if (parts.length < 3) {
                errors.push(`Ligne ${index + 1}: format invalide (besoin de: nom lat lon)`);
                errorCount++;
                return;
            }

            // Le nom peut contenir plusieurs mots (tous sauf les deux derniers éléments)
            const lon = parseFloat(parts[parts.length - 1]);
            const lat = parseFloat(parts[parts.length - 2]);
            const name = parts.slice(0, parts.length - 2).join(' ');

            if (addGroundStationDirect(scene, name, lat, lon)) {
                successCount++;
            } else {
                errors.push(`Ligne ${index + 1}: "${trimmedLine}" - valeurs invalides`);
                errorCount++;
            }
        });

        // Mettre à jour la liste des stations
        updateGroundStationList();

        // Afficher le résultat
        let message = `Import terminé:\n✓ ${successCount} station(s) ajoutée(s)`;
        if (errorCount > 0) {
            message += `\n✗ ${errorCount} erreur(s)`;
            if (errors.length <= 5) {
                message += '\n\n' + errors.join('\n');
            } else {
                message += '\n\n' + errors.slice(0, 5).join('\n') + `\n... et ${errors.length - 5} autre(s) erreur(s)`;
            }
        }
        alert(message);

        // Réinitialiser le input file pour permettre de réimporter le même fichier
        event.target.value = '';
    };

    reader.onerror = () => {
        alert('Erreur lors de la lecture du fichier');
        event.target.value = '';
    };

    reader.readAsText(file);
};

// Fonction pour importer une constellation depuis un fichier TXT
window.handleConstellationFileImport = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        const content = e.target.result.trim();

        // Parser le format: altitude:inclinaison:nbr_sat/nbr_plans/phase
        // Exemple: 550:55:24/6/1
        const parts = content.split(':');

        if (parts.length !== 3) {
            alert('Format invalide. Format attendu: altitude:inclinaison:nbr_sat/nbr_plans/phase\nExemple: 550:55:24/6/1');
            event.target.value = '';
            return;
        }

        const altitude = parseFloat(parts[0]);
        const inclination = parseFloat(parts[1]);
        const walkerParts = parts[2].split('/');

        if (walkerParts.length !== 3) {
            alert('Format Walker Delta invalide. Format attendu: nbr_sat/nbr_plans/phase\nExemple: 24/6/1');
            event.target.value = '';
            return;
        }

        const numSats = parseInt(walkerParts[0]);
        const numPlanes = parseInt(walkerParts[1]);
        const phase = parseInt(walkerParts[2]);

        // Validation des valeurs (pas de limites max pour l'import)
        if (isNaN(altitude) || altitude < 0) {
            alert('Altitude invalide.');
            event.target.value = '';
            return;
        }

        if (isNaN(inclination) || inclination < 0 || inclination > 180) {
            alert('Inclinaison invalide. Doit être entre 0 et 180 degrés.');
            event.target.value = '';
            return;
        }

        if (isNaN(numSats) || numSats < 1) {
            alert('Nombre de satellites invalide. Doit être au moins 1.');
            event.target.value = '';
            return;
        }

        if (isNaN(numPlanes) || numPlanes < 1) {
            alert('Nombre de plans invalide. Doit être au moins 1.');
            event.target.value = '';
            return;
        }

        // Vérifier que numSats est un multiple de numPlanes
        if (numSats % numPlanes !== 0) {
            alert(`Le nombre de satellites (${numSats}) doit être un multiple du nombre de plans (${numPlanes}).\nSatellites par plan: ${numSats / numPlanes}`);
            event.target.value = '';
            return;
        }

        if (isNaN(phase) || phase < 0 || phase >= numPlanes) {
            alert(`Phase invalide. Doit être entre 0 et ${numPlanes - 1}.`);
            event.target.value = '';
            return;
        }

        // Mettre à jour les paramètres
        params.altitude = altitude;
        params.inclination = inclination;
        params.numSats = numSats;
        params.numPlanes = numPlanes;
        params.phase = phase;

        // Mettre à jour les sliders et affichages
        document.getElementById('altitude').value = altitude;
        document.getElementById('altitude-value').textContent = altitude;

        document.getElementById('inclination').value = inclination;
        document.getElementById('inclination-value').textContent = inclination;

        document.getElementById('numSats').value = numSats;
        document.getElementById('numSats-value').textContent = `${numSats} (${numSats / numPlanes} sat/plan)`;

        document.getElementById('numPlanes').value = numPlanes;
        document.getElementById('numPlanes-value').textContent = numPlanes;

        document.getElementById('phase').value = phase;
        document.getElementById('phase').max = numPlanes - 1;
        document.getElementById('phase-value').textContent = phase;

        // Créer la constellation
        createConstellation(scene, params);
        updateSatelliteGrid(params, (satIndex) => {
            highlightSatellite(satIndex, showSatelliteInfo);
        });

        alert(`Constellation importée avec succès!\n\nAltitude: ${altitude} km\nInclinaison: ${inclination}°\nSatellites: ${numSats} (${numSats / numPlanes} par plan)\nPlans: ${numPlanes}\nPhase: ${phase}`);

        // Réinitialiser le input file
        event.target.value = '';
    };

    reader.onerror = () => {
        alert('Erreur lors de la lecture du fichier');
        event.target.value = '';
    };

    reader.readAsText(file);
};

// Rendre les fonctions globales pour les appels depuis HTML
window.addGroundStation = () => addGroundStation(scene);
window.removeGroundStation = (stationId) => removeGroundStation(scene, stationId);
window.closeSatelliteInfo = closeSatelliteInfo;

// Démarrer l'application
init();

// Les panels sont maintenant positionnés en CSS - plus besoin de draggable
